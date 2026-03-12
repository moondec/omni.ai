import os
import sys
import json
import subprocess
import threading
import atexit
import ast
from typing import Optional, List, Any

try:
    from langchain_core.tools import StructuredTool
    from pydantic import BaseModel, Field, create_model
except ImportError:
    from langchain.tools import StructuredTool
    from pydantic import BaseModel, Field, create_model

# ---------------------------------------------------------------------------
# PERSISTENT MCP SESSION
#
# The previous implementation spawned a NEW subprocess (and thus a new MCP
# server + browser) for EVERY tool call.  This meant navigate opened browser
# #1, closed it, then screenshot opened browser #2 (blank) and captured an
# empty page.
#
# This rewrite keeps a SINGLE background worker process alive.  All tool
# calls are sent to it via stdin (JSON) and results read from stdout (JSON).
# The MCP server and Playwright browser persist across calls.
# ---------------------------------------------------------------------------

_WORKER_SCRIPT = r'''
import asyncio
import json
import sys
import os

async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from langchain_mcp_adapters.tools import load_mcp_tools

    executable = json.loads(sys.argv[1])
    args_list  = json.loads(sys.argv[2])

    server_params = StdioServerParameters(
        command=executable,
        args=args_list,
        env=dict(os.environ),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            runtime_tools = await load_mcp_tools(session)
            tool_map = {t.name: t for t in runtime_tools}

            # Signal: worker is ready
            sys.stdout.write(json.dumps({"status": "ready", "tools": list(tool_map.keys())}) + "\n")
            sys.stdout.flush()

            # Request loop — read one JSON line at a time from stdin
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError:
                    sys.stdout.write(json.dumps({"error": "Invalid JSON"}) + "\n")
                    sys.stdout.flush()
                    continue

                if request.get("cmd") == "quit":
                    break

                tool_name = request.get("tool", "")
                tool_args = request.get("args", {})

                tool = tool_map.get(tool_name)
                if tool is None:
                    sys.stdout.write(json.dumps({"error": f"Tool '{tool_name}' not found"}) + "\n")
                    sys.stdout.flush()
                    continue

                try:
                    result = await tool.ainvoke(tool_args)
                    sys.stdout.write(json.dumps({"result": str(result)}) + "\n")
                    sys.stdout.flush()
                except Exception as e:
                    sys.stdout.write(json.dumps({"error": str(e)}) + "\n")
                    sys.stdout.flush()

asyncio.run(main())
'''


class PlaywrightMCPTools:

    def __init__(self, executable: str = "npx", args: List[str] = None):
        self.executable = executable
        self.args = args or ["-y", "@executeautomation/playwright-mcp-server"]
        self._sync_tools: List[Any] = []
        self._worker_proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._initialize_tools()

    # ------------------------------------------------------------------
    # Background worker lifecycle
    # ------------------------------------------------------------------
    def _ensure_worker(self):
        """Start (or restart) the persistent background worker if needed."""
        with self._lock:
            if self._worker_proc is not None and self._worker_proc.poll() is None:
                return  # still alive

            self._worker_proc = subprocess.Popen(
                [
                    sys.executable, "-c", _WORKER_SCRIPT,
                    json.dumps(self.executable),
                    json.dumps(self.args),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=os.environ.copy(),
            )

            # Wait for the "ready" signal (with timeout)
            import select
            ready_line = ""
            # Read lines until we get the ready signal (timeout 60s)
            import time
            deadline = time.time() + 60
            while time.time() < deadline:
                if self._worker_proc.poll() is not None:
                    stderr_out = self._worker_proc.stderr.read()
                    raise RuntimeError(
                        f"MCP worker process died during startup. stderr:\n{stderr_out[-2000:]}"
                    )
                # Non-blocking readline with small sleep
                line = self._worker_proc.stdout.readline()
                if line:
                    ready_line = line.strip()
                    break
                time.sleep(0.1)

            if not ready_line:
                self.shutdown()
                raise RuntimeError("MCP worker did not send ready signal within 60 seconds.")

            try:
                status = json.loads(ready_line)
                if status.get("status") != "ready":
                    raise RuntimeError(f"Unexpected worker status: {status}")
            except json.JSONDecodeError:
                raise RuntimeError(f"Worker sent invalid ready signal: {ready_line}")

            # Register cleanup
            atexit.register(self.shutdown)

    def _send_request(self, tool_name: str, tool_args: dict) -> str:
        """Send a tool request to the persistent worker and return the result."""
        self._ensure_worker()

        request = json.dumps({"tool": tool_name, "args": tool_args}) + "\n"

        with self._lock:
            try:
                self._worker_proc.stdin.write(request)
                self._worker_proc.stdin.flush()

                # Read one response line (with timeout via thread)
                response_line = [None]
                error_flag = [False]

                def _read():
                    try:
                        response_line[0] = self._worker_proc.stdout.readline()
                    except Exception:
                        error_flag[0] = True

                reader = threading.Thread(target=_read, daemon=True)
                reader.start()
                reader.join(timeout=120)

                if reader.is_alive() or error_flag[0] or not response_line[0]:
                    # Worker seems dead or timed out
                    self.shutdown()
                    return f"Error: MCP worker timed out or crashed for tool '{tool_name}'."

                resp = json.loads(response_line[0].strip())
                if "error" in resp:
                    return f"Error running MCP tool '{tool_name}': {resp['error']}"
                return resp.get("result", "")

            except (BrokenPipeError, OSError) as e:
                self.shutdown()
                return f"Error: MCP worker connection lost for tool '{tool_name}': {e}"

    def shutdown(self):
        """Terminate the background worker process."""
        with self._lock:
            if self._worker_proc is not None and self._worker_proc.poll() is None:
                try:
                    self._worker_proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
                    self._worker_proc.stdin.flush()
                    self._worker_proc.wait(timeout=5)
                except Exception:
                    try:
                        self._worker_proc.terminate()
                        self._worker_proc.wait(timeout=3)
                    except Exception:
                        self._worker_proc.kill()
            self._worker_proc = None

    # ------------------------------------------------------------------
    # Static tool definitions (unchanged from before)
    # ------------------------------------------------------------------
    def _initialize_tools(self):
        known_tools = [
            ("playwright_navigate", "Navigate to a URL", {"url": (str, Field(description="URL to navigate to"))}),
            ("playwright_screenshot", "Take a screenshot of the current page", {"name": (str, Field(description="Name for the screenshot"))}),
            ("playwright_click", "Click an element on the page. For radio buttons use the exact selector with value, e.g. input[name=\"Type\"][value=\"IsoBar\"]", {"selector": (str, Field(description="CSS selector of the element to click"))}),
            ("playwright_fill", "Fill a text input or textarea field (NOT for <select> dropdowns — use playwright_select_option for those)", {
                "selector": (str, Field(description="CSS selector of the input")),
                "value": (str, Field(description="Value to type into the input")),
            }),
            ("playwright_evaluate", "Evaluate JavaScript in the browser", {"script": (str, Field(description="JavaScript code to execute"))}),
            ("playwright_get_visible_text", "Get all visible text from the current page", {}),
            ("playwright_get_visible_html", "Get the HTML of the current page", {}),
        ]

        for t_name, t_desc, t_fields in known_tools:
            tool = self._make_tool(t_name, t_desc, t_fields)
            self._sync_tools.append(tool)

        # Add custom helper tools
        self._sync_tools.append(self._make_get_interactive_elements_tool())
        self._sync_tools.append(self._make_select_option_tool())

    # ------------------------------------------------------------------
    # playwright_select_option — select an <option> from a <select>
    # ------------------------------------------------------------------
    def _make_select_option_tool(self):
        tools_instance = self

        def _run(*args, **kwargs):
            if args and not kwargs:
                arg = args[0]
                if isinstance(arg, dict):
                    kwargs = arg
                elif isinstance(arg, str):
                    kwargs = {"selector": arg}
            selector = kwargs.get("selector", "")
            if isinstance(selector, str):
                selector = selector.replace('\\"', '"')
            
            # Support 'option' as an alias for 'value' due to LLM tendencies
            value = kwargs.get("value")
            if value is None:
                value = kwargs.get("option", "")
            # Use JS to select the option by value OR by visible text, and dispatch 'change' event
            safe_value = value.replace("'", "\\'")
            js = f"""
            (() => {{
                const sel = document.querySelector('{selector}');
                if (!sel) return 'Error: element not found: {selector}';
                
                // Try 1: Match by option value
                let found = false;
                for (let opt of sel.options) {{
                    if (opt.value === '{safe_value}') {{
                        sel.value = opt.value;
                        found = true;
                        break;
                    }}
                }}
                
                // Try 2: Match by option text (case-insensitive)
                if (!found) {{
                    const needle = '{safe_value}'.toLowerCase();
                    for (let opt of sel.options) {{
                        if (opt.text.toLowerCase().includes(needle)) {{
                            sel.value = opt.value;
                            found = true;
                            break;
                        }}
                    }}
                }}
                
                if (!found) {{
                    const available = Array.from(sel.options).map(o => o.text + ' (' + o.value + ')').slice(0, 10).join(', ');
                    return 'Error: option not found. Available: ' + available;
                }}
                
                sel.dispatchEvent(new Event('change', {{ bubbles: true }}));
                const selectedText = sel.options[sel.selectedIndex].text;
                return 'Selected: ' + selectedText + ' (value=' + sel.value + ')';
            }})();
            """
            raw_res = tools_instance._send_request("playwright_evaluate", {"script": js})
            try:
                if raw_res.startswith("[") and raw_res.endswith("]"):
                    blocks = ast.literal_eval(raw_res)
                    result_text = blocks[-1].get("text", raw_res)
                    if isinstance(result_text, str) and result_text.startswith('"') and result_text.endswith('"'):
                        result_text = json.loads(result_text)
                    return result_text
                return raw_res
            except Exception:
                return raw_res

        SchemaClass = create_model("playwright_select_option_Schema",
            selector=(str, Field(description="CSS selector of the <select> element")),
            value=(str, Field(default="", description="The option value OR visible text to select, e.g. 'Water' or 'C7732185'. Alias: 'option'")),
            option=(str, Field(default="", description="Alias for 'value'")),
        )
        return StructuredTool.from_function(
            func=_run,
            name="playwright_select_option",
            description="Select an option from a <select> dropdown. You can pass either the option's value attribute OR its visible text (e.g. 'Water'). This properly triggers the 'change' event. Use this instead of playwright_fill for <select> elements.",
            args_schema=SchemaClass,
        )

    # ------------------------------------------------------------------
    # playwright_get_interactive_elements — inspect the page DOM
    # ------------------------------------------------------------------
    def _make_get_interactive_elements_tool(self):
        js_script = r'''
        (() => {
            const elements = document.querySelectorAll('a, button, input, select, textarea, [role="button"]');
            const result = [];
            for (let el of elements) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                let tag = el.tagName.toLowerCase();
                let type = el.type || '';
                let name = el.name || '';
                let id = el.id || '';
                let value = el.value || '';
                let placeholder = el.placeholder || '';
                let text = (el.innerText || '').trim().substring(0, 60);
                let checked = (el.type === 'radio' || el.type === 'checkbox') ? el.checked : undefined;

                // Build a unique, precise selector
                let selector = tag;
                if (id) {
                    selector = tag + '#' + id;
                } else if (name && value && (type === 'radio' || type === 'checkbox')) {
                    selector = tag + '[name="' + name + '"][value="' + value + '"]';
                } else if (name) {
                    selector = tag + '[name="' + name + '"]';
                } else if (el.className && typeof el.className === 'string') {
                    const cls = el.className.split(' ').map(c => c.trim()).filter(c => c);
                    if (cls.length > 0) selector += '.' + cls[0];
                } else if (text && (tag === 'button' || tag === 'a')) {
                    let safeText = text.substring(0, 40).replace(/"/g, '');
                    selector = tag + ':has-text("' + safeText + '")';
                }

                // For <select>, list available options
                let options = undefined;
                if (tag === 'select') {
                    options = Array.from(el.options).map(o => o.value).filter(v => v);
                }

                let entry = {tag, selector};
                if (type) entry.type = type;
                if (name) entry.name = name;
                if (value && type !== 'hidden') entry.value = value;
                if (text && tag !== 'select') entry.text = text;
                if (placeholder) entry.placeholder = placeholder;
                if (checked !== undefined) entry.checked = checked;
                if (options) entry.options = options.slice(0, 15).join(', ') + (options.length > 15 ? '...' : '');

                result.push(entry);
            }
            return JSON.stringify(result);
        })();
        '''

        def _run(*args, **kwargs):
            raw_res = self._send_request("playwright_evaluate", {"script": js_script})
            try:
                if raw_res.startswith("[") and raw_res.endswith("]"):
                    blocks = ast.literal_eval(raw_res)
                    json_str = blocks[-1].get("text", "")
                    if isinstance(json_str, str) and json_str.startswith('"') and json_str.endswith('"'):
                        json_str = json.loads(json_str)
                else:
                    json_str = raw_res

                parsed = json.loads(json_str)
                if isinstance(parsed, str):
                    parsed = json.loads(parsed)

                if not parsed:
                    return "No interactive elements found on the page."

                lines = ["Interactive Elements on Page:"]
                for el in parsed:
                    parts = [f"[{el.get('tag')}]"]
                    if el.get('type'):
                        parts.append(f"type={el['type']}")
                    if el.get('name'):
                        parts.append(f"name={el['name']}")
                    if el.get('value'):
                        parts.append(f"value=\"{el['value']}\"")
                    if el.get('text'):
                        parts.append(f"text=\"{el['text']}\"")
                    if el.get('placeholder'):
                        parts.append(f"placeholder=\"{el['placeholder']}\"")
                    if el.get('checked') is True:
                        parts.append("✓CHECKED")
                    if el.get('options'):
                        parts.append(f"options=[{el['options']}]")
                    parts.append(f"→ {el.get('selector')}")
                    lines.append("  " + " | ".join(parts))
                return "\n".join(lines)
            except Exception as e:
                return f"Raw result (could not parse): {raw_res}\nError: {e}"

        SchemaClass = create_model("playwright_get_interactive_elements_Schema")
        return StructuredTool.from_function(
            func=_run,
            name="playwright_get_interactive_elements",
            description="Get a list of interactive elements (buttons, inputs, links) and their EXACT CSS selectors. ALWAYS use this to find the correct selector before using playwright_click or playwright_fill.",
            args_schema=SchemaClass,
        )

    # ------------------------------------------------------------------
    # Build a StructuredTool that delegates to the persistent worker
    # ------------------------------------------------------------------
    def _make_tool(self, tool_name: str, tool_desc: str, tool_schema_fields: dict):
        # Remember field names so we can map a bare positional string
        field_names = list(tool_schema_fields.keys()) if tool_schema_fields else []
        # Capture self for the closure
        tools_instance = self

        def _run(*args, **kwargs):
            """Synchronous function called by LangChain agent.

            The agent_engine calls `tool.run(tool_args)` where tool_args
            may be a string, a dict, or keyword args. We handle all cases.
            """
            # --- Normalize input into a dict ---
            if args and not kwargs:
                arg = args[0]
                if isinstance(arg, dict):
                    kwargs = arg
                elif isinstance(arg, str):
                    if field_names:
                        kwargs = {field_names[0]: arg}
                    else:
                        kwargs = {}
            elif args and kwargs:
                if isinstance(args[0], dict):
                    merged = dict(args[0])
                    merged.update(kwargs)
                    kwargs = merged

            # Sanitize selectors: remove literal backslash escapes for quotes which agents often incorrectly send
            for k, v in list(kwargs.items()):
                if k == "selector" and isinstance(v, str):
                    kwargs[k] = v.replace('\\"', '"')

            return tools_instance._send_request(tool_name, kwargs)

        # Create pydantic schema
        if tool_schema_fields:
            SchemaClass = create_model(f"{tool_name}_Schema", **tool_schema_fields)
        else:
            SchemaClass = create_model(f"{tool_name}_Schema")

        return StructuredTool.from_function(
            func=_run,
            name=tool_name,
            description=tool_desc,
            args_schema=SchemaClass,
        )

    def get_tools(self) -> List[Any]:
        return self._sync_tools
