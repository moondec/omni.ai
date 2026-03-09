from typing import List, Dict, Any
import os
import re
import json
import datetime
from langchain_openai import ChatOpenAI
from langchain_community.agent_toolkits import FileManagementToolkit
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pcss_llm_app.core.tools import (
    DocumentTools, OCRTools, PandocTools, VisionTools, 
    WebSearchTools, ChartTools, FolderTools, PythonREPL,
    SearchTools, TerminalTool, UpdateContextTool,
    ViewFileTool, ReplaceFileContentTool
)
from pcss_llm_app.core.mcp_tools import PlaywrightMCPTools

class LangChainAgentEngine:
    def __init__(self, api_key: str, model_name: str, workspace_path: str, 
                 log_callback=None, custom_instructions: str = None, 
                 llm_instructions: str = None):
        self.api_key = api_key
        self.model_name = model_name
        self.workspace_path = workspace_path
        self.log_callback = log_callback
        self.custom_instructions = custom_instructions or ""
        self.llm_instructions = llm_instructions or ""
        self.active_scratchpad = "" # Persistence layer for long tasks
        self.consecutive_format_errors = 0
        self._initialize_agent()

    def _load_workspace_context(self) -> str:
        """Loads and returns a summary of the workspace state for injection into System Prompt."""
        context_header = "\n### CURRENT PROJECT CONTEXT (BOOTSTRAP)\n"
        context_body = ""
        
        # 1. Look for .agent_context.md
        context_file = os.path.join(self.workspace_path, ".agent_context.md")
        if os.path.exists(context_file):
            try:
                with open(context_file, "r", encoding="utf-8") as f:
                    context_body += f"--- FROM .agent_context.md ---\n{f.read()}\n"
            except Exception:
                pass
        
        # 2. Automated File Scan (Brief)
        try:
            items = os.listdir(self.workspace_path)
            # Prioritize files over directories, limit to first 30
            sorted_items = sorted(items, key=lambda x: os.path.isdir(os.path.join(self.workspace_path, x)))
            filtered = [f for f in sorted_items if not f.startswith('.') and f != "__pycache__" and f != "venv"]
            if filtered:
                context_body += f"--- WORKSPACE FILE LIST ---\n{', '.join(filtered[:30])}\n"
                
            # 3. Read README.md if present for high-level context
            readme_path = os.path.join(self.workspace_path, "README.md")
            if os.path.exists(readme_path):
                with open(readme_path, "r", encoding="utf-8") as f:
                    readme_content = f.read(1000) # Only first 1k chars
                    context_body += f"--- README.md (Teaser) ---\n{readme_content}...\n"
        except Exception:
            pass
            
        if not context_body:
            return ""
            
        return context_header + context_body + "### END OF CONTEXT\n"

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(message)

    def _initialize_agent(self):
        # 1. Initialize LLM with performance optimizations
        self.llm = ChatOpenAI(
            api_key=self.api_key,
            base_url="https://llm.hpc.pcss.pl/v1",
            model=self.model_name,
            temperature=0.2,  # Small randomness to prevent deterministic loops
            max_tokens=2048,  # Limit response length for faster generation
            request_timeout=120  # 2 minute timeout
        )

        # 2. Initialize Tools
        # print("DEBUG: Init FileToolkit", flush=True)
        toolkit = FileManagementToolkit(root_dir=str(self.workspace_path))

        # Filter out native read_file to force usage of our line-based view_file
        self.tools = [t for t in toolkit.get_tools() if t.name != "read_file"]
        
        # Add Document Tools
        doc_tools = DocumentTools(root_dir=str(self.workspace_path))
        self.tools.extend(doc_tools.get_tools())

        # Add OCR Tools
        ocr_tools = OCRTools(root_dir=str(self.workspace_path), api_key=self.api_key)
        self.tools.extend(ocr_tools.get_tools())

        # Add Folder Tools
        folder_tools = FolderTools(root_dir=str(self.workspace_path))
        self.tools.extend(folder_tools.get_tools())

        # Add Pandoc Tools
        pandoc_tools = PandocTools(root_dir=str(self.workspace_path))
        self.tools.extend(pandoc_tools.get_tools())

        # Vision tools - specifically use Qwen3-VL for image analysis
        vision_model = "Qwen3-VL-235B-A22B-Instruct"
        vision_tools = VisionTools(root_dir=str(self.workspace_path), api_key=self.api_key, model_name=vision_model)
        self.tools.extend(vision_tools.get_tools())

        # Add Web Search Tools
        web_search_tools = WebSearchTools(
            api_key=self.api_key, 
            model_name=self.model_name,
            base_url="https://llm.hpc.pcss.pl/v1"
        )
        self.tools.extend(web_search_tools.get_tools())

        # Add Chart Generation Tools
        chart_tools = ChartTools(root_dir=str(self.workspace_path))
        self.tools.extend(chart_tools.get_tools())

        # Add Python REPL
        repl = PythonREPL(root_dir=str(self.workspace_path))
        self.tools.extend(repl.get_tools())

        # Add Search Tools
        search_tools = SearchTools(root_dir=str(self.workspace_path))
        self.tools.extend(search_tools.get_tools())

        # Add View File Tool
        view_file_tool = ViewFileTool(root_dir=str(self.workspace_path))
        self.tools.extend(view_file_tool.get_tools())

        # Add Replace File Content Tool
        replace_file_tool = ReplaceFileContentTool(root_dir=str(self.workspace_path))
        self.tools.extend(replace_file_tool.get_tools())

        # Add Terminal Tool
        terminal_tool = TerminalTool(root_dir=str(self.workspace_path))
        self.tools.extend(terminal_tool.get_tools())

        # Add Context Tool
        context_tool = UpdateContextTool(root_dir=str(self.workspace_path))
        self.tools.extend(context_tool.get_tools())

        # Add MCP Tools (Playwright Server)
        try:
            mcp_playwright = PlaywrightMCPTools()
            mcp_tools = mcp_playwright.get_tools()
            if mcp_tools:
                self.tools.extend(mcp_tools)
                self._log("Successfully loaded Playwright MCP Tools.")
        except Exception as e:
            import traceback
            err_msg = traceback.format_exc()
            self._log(f"Warning: Failed to load Playwright MCP:\n{err_msg}")

        # print("DEBUG: Building map", flush=True)
        self.tool_map = {t.name: t for t in self.tools}

    def run_step(self, prompt, stop=None):
         return self.llm.invoke(prompt, stop=stop).content

    # Intelligent Run method with loop detection and flexible limits
    # Intelligent Run method with loop detection and flexible limits
    def run(self, input_text: str, chat_history: List = None):
        # RESET format error counter on new user message to break stagnation loops
        self.consecutive_format_errors = 0
        
        if chat_history is None:
            chat_history = []

        tool_names = ", ".join(self.tool_map.keys())
        tool_descriptions = "\n".join([f"{t.name}: {t.description}" for t in self.tools])
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        vision_rule = "- Use `analyze_image` to review UI screenshots, analyze charts, or understand mockups." if "Qwen3" in self.model_name else "- You DO NOT have vision capabilities. DO NOT use `analyze_image`."

        system_template = f"""You are an AI assistant with tools. Date: {current_date}

Tools:
{tool_descriptions}

Format:
Question: [user's question]
Thought: [your reasoning]
Action: [one of: {tool_names}]
Action Input: [JSON for multi-arg tools, string for single-arg]
Observation: [result]
... (repeat as needed)
Thought: I have the answer
Final Answer: [your response]

Examples:
- convert_document: {{"source_path": "report.html", "output_format": "docx"}}
- save_document: {{"file_path": "doc.html", "content": "<h1>Title</h1><p>...</p>", "title": "Doc"}}
- write_file: {{"file_path": "notes.txt", "text": "Details..."}}
- view_file: {{"file_path": "code.py", "start_line": 1, "end_line": 50}}
- replace_file_content: {{"file_path": "app.py", "start_line": 10, "end_line": 12, "replacement_content": "print('New context')"}}
- list_directory: {{"dir_path": "."}}
- search_web: {{"query": "news Poland"}}

Rules:
- Speak strictly POLISH to the user.
- Write Code, Comments, and Technical docs strictly in ENGLISH.
- NEVER guess CSS selectors for Playwright. ALWAYS use `playwright_get_interactive_elements` to inspect the page and find exact CSS selectors before using `playwright_click` or `playwright_fill`.
{vision_rule}
- Use `list_directory` to see what files are in the workspace.
- Use `view_file` with line numbers to read code before editing.
- Use `search_files` to find content within files.
- Use `replace_file_content` to modify existing code using line numbers.
- Use `run_terminal` to run scripts or check syntax.
- Use `run_python` for math, data analysis, or testing logic.
- Use `search_news` for current events, `search_web` for general info.
- Use `deep_research` for complex topics that need multiple sources and analysis.
- Use `visit_page` to read full content from URLs (2-3 max).
- For documents: use `save_document` with HTML content.
- Be efficient - stop when you have enough information.
- IF YOU NEED TO ASK THE USER A QUESTION: You MUST use "Final Answer: [your question]" to return control to the user. Do not just "think" the question.

{self.llm_instructions}

{f"User Instructions: " + self.custom_instructions if self.custom_instructions else ""}

{self._load_workspace_context()}
Begin!"""
        
        # Build conversation history
        history_text = ""
        for msg in chat_history:
            role = "Question" if isinstance(msg, HumanMessage) else "Final Answer" 
            content = msg.content if hasattr(msg, "content") else str(msg)
            if isinstance(msg, HumanMessage):
                history_text += f"Question: {content}\n"
            else:
                 history_text += f"Final Answer: {content}\n"

        # Stateful Continuation Logic
        # Smart Resume: If we have an active scratchpad from a previous turn (because we asked a question), resume automatically.
        if self.active_scratchpad:
            self._log("Resuming from persistent interaction state...")
            # We treat the user's new input as an observation/answer to the agent's previous state
            prompt = f"{system_template}\n{history_text}\n(Resuming task context...)\nThought: I should continue my work. Here is the history of my previous steps:\n{self.active_scratchpad}\nObservation: User Feedback/Answer: {input_text}\nNote: Decide if this answers your question or if you need to adjust your plan.\nThought:"
        else:
            self.active_scratchpad = "" # Ensure clean start
            prompt = f"{system_template}\n{history_text}\nQuestion: {input_text}\nThought:"

        max_steps = 50
        self._consecutive_format_errors = 0  # Reset format error counter
        action_history = []
        thought_history = []
        observation_history = []
        
        for i in range(max_steps):
            # Reset variables at start of each iteration to prevent stale values
            action = None
            action_input = None
            tool_args = None
            match = None
            
            self._log(f"--- Step {i+1} ---")
            
            # Invoke LLM with stop sequence
            self._log("Thinking...")
            response = self.llm.invoke(prompt, stop=["Observation:"])
            output = response.content
            # print(f"--- Step {i} ---\nLLM Output:\n{output}\n----------------")
            self._log(f"Agent Thought:\n{output}")
            
            # Smart Loop Detection (Thoughts)
            # Normalize thought (remove whitespace/newlines for comparison)
            current_thought = output.replace("Thought:", "").strip()
            
            # Strict stop only after 5 consecutive identical thoughts
            if len(thought_history) >= 4 and all(current_thought == t for t in thought_history[-4:]):
                 self._log("⚠️ Thought Loop detected! Agent is repeating itself 5 times.")
                 return "Agent stopped: Repetitive thought process detected. The task seems completed or the agent is stuck."
            
            # Warning on 3rd identical thought
            if len(thought_history) >= 2 and current_thought == thought_history[-1] and current_thought == thought_history[-2]:
                 self._log("⚠️ Potential Thought Loop (3rd occurrence). Injecting warning.")
                 warning_msg = "\nObservation: Warning: You are repeating your exact same thought. Please move to the next step or change your approach.\nThought:"
                 prompt += warning_msg
                 self.active_scratchpad += warning_msg
            
            thought_history.append(current_thought)
            
            prompt += output
            self.active_scratchpad += output # Mirror to scratchpad
            
            # Parse Action
            # Use non-greedy for Action and a more precise match for Input to allow trailing text
            pattern = r"Action:\s*(.+?)\n+Action Input:\s*(.+?)(?=\n+Thought:|\n+Final Answer:|$)"
            match = re.search(pattern, output, re.DOTALL)
            
            # Fallback for Bielik and others that fail to provide newlines
            if not match:
                # Try more aggressive search for Action/Input pairs
                bielik_pattern = r"Action:\s*([a-zA-Z0-9_]+)[\s\S]*?Action Input:\s*([\s\S]+)"
                match = re.search(bielik_pattern, output)
                if match:
                    action = match.group(1).strip()
                    raw_input = match.group(2).strip()
                    # Clean up trailing Thought/Final Answer markers from the greedy capture
                    raw_input = re.split(r'\nThought:|\nFinal Answer:|\nObservation:', raw_input)[0].strip()
                    # We store it for later processing
            
            # Priority: If we found an action, EXECUTE IT. Ignore Final Answer in this turn.
            if match:
                # Proceed to process action (logic moved down or kept here)
                pass
            elif "Final Answer:" in output:
                final_ans = output.split("Final Answer:")[-1].strip()
                
                # Context Preservation Logic
                # If Final Answer is a question, KEEP the scratchpad so we can resume next turn.
                is_question_end = final_ans.endswith("?")
                question_markers = ["czy", "pytanie", "question", "should i", "decide"]
                is_question_content = any(m in final_ans.lower() for m in question_markers)
                
                if is_question_end or is_question_content:
                    self._log("Context Preserved: Agent asked a question. Scratchpad kept for next turn.")
                    # Do not clear active_scratchpad
                else:
                    self._log("Task Completed. Clearing Context.")
                    self.active_scratchpad = "" # Task finished, clear scratchpad
                
                return final_ans
            
            # Fallback 1: Single-line format "Action: tool_name {args}"
            if not match:
                single_line_pattern = r"Action:\s*([a-z_]+)\s*(\{.*?\})"
                single_match = re.search(single_line_pattern, output, re.DOTALL)
                if single_match:
                    action = single_match.group(1).strip()
                    action_input = single_match.group(2).strip()
                    match = True  # Signal that we found action
                    self._log(f"⚙️ Using single-line format parser for: {action}")
            
            # Fallback 2: "function call" style
            if not match:
                 json_pattern = r'function call\s*({.*?})'
                 json_match = re.search(json_pattern, output, re.DOTALL)
                 if json_match:
                     try:
                         func_data = json.loads(json_match.group(1))
                         if "name" in func_data:
                             action = func_data["name"]
                             args = func_data.get("arguments", {})
                             action_input = json.dumps(args) if isinstance(args, dict) else str(args)
                             match = True 
                     except Exception: pass

            # Fallback 3: Python code block style (common for Qwen3)
            if not match:
                py_pattern = r'```(?:python)?\s*([a-zA-Z0-9_]+)\s*\(\s*(\{.*?\})\s*\)\s*```'
                py_match = re.search(py_pattern, output, re.DOTALL)
                if py_match:
                    action = py_match.group(1).strip()
                    action_input = py_match.group(2).strip()
                    match = True
                    self._log(f"⚙️ Using python block parser for: {action}")

            # Fallback 4: Ultra-greedy layout format for weak models (Bielik 11b)
            if not match:
                # Some weak models barely use newlines or omit "Thought:" entirely in loops
                bielik_pattern = r"Action:\s*([a-zA-Z0-9_]+)[\s\S]*?Action Input:\s*([\s\S]+)"
                bielik_match = re.search(bielik_pattern, output)
                if bielik_match:
                    action = bielik_match.group(1).strip()
                    # Clean up: If there's trailing garbage like 'Thought:' or 'Final Answer:' at the end, just strip it out manually
                    raw_input = bielik_match.group(2).strip()
                    raw_input = re.split(r'\nThought:|\nFinal Answer:|\nObservation:', raw_input)[0].strip()
                    
                    action_input = raw_input
                    match = True
                    self._log(f"⚙️ Using ultra-greedy fallback parser for: {action}")

            if match:
                if hasattr(match, 'group'):
                    action = match.group(1).strip()
                    action_input = match.group(2).strip()
                
                # Safe Sanitization: stripping markdown wrappers only if they encompass the whole input
                action_input = action_input.strip()
                if "```" in action_input:
                    # Look for a block that starts at the beginning and ends at the end
                    block_match = re.search(r"^```(?:json)?\s*(.*?)\s*```$", action_input, re.DOTALL)
                    if block_match:
                        action_input = block_match.group(1).strip()
                    else:
                        # If not a whole-block wrap, only strip if it explicitly starts and ends with backticks
                        if action_input.startswith("```") and action_input.endswith("```"):
                             action_input = re.sub(r"^```(?:json)?", "", action_input)
                             action_input = re.sub(r"```$", "", action_input).strip()

                # Remove surrounding quotes only if they wrap the whole thing
                if (action_input.startswith('"') and action_input.endswith('"')) or \
                   (action_input.startswith("'") and action_input.endswith("'")):
                    action_input = action_input[1:-1].strip()
                
                # Try parsing as JSON
                try:
                    tool_args = json.loads(action_input)
                except json.JSONDecodeError:
                    import ast
                    try:
                        # Sometimes LLMs output Python dicts instead of JSON
                        tool_args = ast.literal_eval(action_input)
                    except (SyntaxError, ValueError):
                        # Fix common unescaped control character issues (like \t or \n in strings)
                        fixed_input = action_input.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
                        try:
                            tool_args = json.loads(fixed_input)
                        except json.JSONDecodeError:
                            # Robust extraction: finding the outer-most JSON object if parsing failed
                            # This handles cases like: {"key": "val"}?? or text ending with garbage
                            json_obj_match = re.search(r"(\{.*\})", fixed_input, re.DOTALL)
                            if json_obj_match:
                                try:
                                    tool_args = json.loads(json_obj_match.group(1))
                                except:
                                    try:
                                        tool_args = ast.literal_eval(json_obj_match.group(1))
                                    except:
                                        tool_args = action_input
                            else:
                                 tool_args = action_input

                # Heuristic Fallback for broken JSON (especially write_file with unescaped newlines/quotes)
                if isinstance(tool_args, str):
                    try:
                        # Try to manually regex out file_path and text for write_file/edit_file
                        fp_match = re.search(r'"(?:file_path|path|directory_path|source_path)"\s*:\s*"([^"]+)"', tool_args)
                        if fp_match:
                            extracted_path = fp_match.group(1)
                            # Now try to get the text/content field if it exists
                            text_match = re.search(r'"(?:text|content)"\s*:\s*"(.*)"\s*\}?\s*$', tool_args, re.DOTALL)
                            if text_match:
                                extracted_text = text_match.group(1)
                                # The greedy match might include the closing "} at the very end, try to strip it
                                if extracted_text.endswith('"}'):
                                    extracted_text = extracted_text[:-2]
                                elif extracted_text.endswith('"\n}'):
                                    extracted_text = extracted_text[:-3]
                                elif extracted_text.endswith('"'):
                                    extracted_text = extracted_text[:-1]
                                
                                tool_args = {"file_path": extracted_path, "text": extracted_text}
                            else:
                                # Maybe it only had a path (like read_file, create_directory)
                                tool_args = {"file_path": extracted_path}
                    except Exception as e:
                        pass

                # Argument Mapping Fallback
                if isinstance(tool_args, dict):
                    # Handle nested JSON string in a single field (Agent hallucination)
                    if len(tool_args) == 1:
                        key = list(tool_args.keys())[0]
                        val = tool_args[key]
                        if isinstance(val, str) and val.strip().startswith("{"):
                            try:
                                nested = json.loads(val)
                                if isinstance(nested, dict):
                                    tool_args = nested
                            except json.JSONDecodeError:
                                # Try fixing common JSON string errors (unescaped newlines)
                                try:
                                    fixed_val = val.replace('\n', '\\n').replace('\r', '')
                                    nested = json.loads(fixed_val)
                                    if isinstance(nested, dict):
                                        tool_args = nested
                                except: pass
                            except: pass

                    # Tool-specific Alias Mapping
                    if action in ["list_directory", "create_directory"]:
                        # Standardize on 'dir_path' for these tools
                        for key in ["path", "directory_path", "file_path"]:
                            if key in tool_args and "dir_path" not in tool_args:
                                tool_args["dir_path"] = tool_args.pop(key)
                    
                    elif action in ["view_file", "replace_file_content", "write_file", "delete_file", "move_file", "copy_file", "read_docx", "read_pdf"]:
                        # Standardize on 'file_path' for file tools
                        if "path" in tool_args and "file_path" not in tool_args:
                            tool_args["file_path"] = tool_args.pop("path")
                    
                    elif action == "convert_document":
                        # Standardize on 'source_path'
                        for key in ["path", "file_path", "source_file"]:
                            if key in tool_args and "source_path" not in tool_args:
                                tool_args["source_path"] = tool_args.pop(key)

                    if action in ["write_file", "write_docx"] and "content" in tool_args and "text" not in tool_args:
                         tool_args["text"] = tool_args.pop("content")
                         
                    if action == "replace_file_content":
                        # Map common hallucinated arguments
                        for old_key in ["new_content", "updated_content", "replace_with", "content", "text"]:
                            if old_key in tool_args and "replacement_content" not in tool_args:
                                tool_args["replacement_content"] = tool_args.pop(old_key)

                # Heuristic Question Detection (Force Interaction)
                # Check if agent is trying to "write" a question to a file or "think" a question without asking
                question_patterns = [
                    "pytanie do ciebie", "czy mam", "should i", "do you want", 
                    "czy chcesz", "mam przystąpić", "mogę rozpocząć",
                    "czy mam teraz", "czy powinienem", "czy mogę",
                    "proszę o decyzję", "pytanie:", "decyzja:"
                ]
                
                # Combine Thought, Action Input, and potential File Content into one check string
                check_text = (str(action_input) + " " + output.replace("Thought:", "")).lower()
                
                # Explicitly check content if writing a file
                if action in ["write_file", "save_document", "write_docx"] and isinstance(tool_args, dict):
                    content = tool_args.get("text", "") or tool_args.get("content", "")
                    check_text += " " + str(content).lower()

                is_question = any(p in check_text for p in question_patterns)
                
                # Special check for Question Headers in artifacts
                if "<h2>pytanie" in check_text or "<h1>pytanie" in check_text or "### pytanie" in check_text:
                    is_question = True
                
                # If it looks like a question, but NOT a Final Answer, intercept it.
                if is_question and "Final Answer" not in output:
                     self._log("⚠️ Heuristic: Agent is trying to ask a question via Tool/Thought. Intercepting.")
                     interception_msg = "\nObservation: SYSTEM INTERVENTION: It looks like you want to ask the user a question (e.g., 'Czy mam...'). \nSTOP. Do not write this to a file or just think about it. \nYou MUST use the format: 'Final Answer: [your question]' to actually ask the user and get a response.\nThought:"
                     prompt += interception_msg
                     self.active_scratchpad += interception_msg
                     continue

                # Action Loop Detection
                current_action = (action, action_input)
                
                # Check for 3 consecutive identical actions
                if len(action_history) >= 2 and action_history[-1] == current_action and action_history[-2] == current_action:
                    self._log("⚠️ Action Loop detected! Stopping agent.")
                    return "Agent stopped: Repetitive action loop. I have tried this too many times."
                
                action_history.append(current_action)

                # Execute Tool
                if action in self.tool_map:
                    self._log(f"Executing Tool: {action} (Step {i+1}/{max_steps})")
                    tool = self.tool_map[action]
                    try:
                        observation = tool.run(tool_args) if hasattr(tool, "run") else tool(tool_args)
                        
                        # Observation Loop / Stagnation check
                        if len(observation_history) > 0 and observation == observation_history[-1]:
                             self._log("⚠️ Stagnation detected (Repeated Observation).")
                             observation += "\n\n[SYSTEM WARNING: You just received the EXACT SAME observation as your last step. You are stuck in a loop. YOU MUST USE A DIFFERENT TOOL OR DIFFERENT ARGUMENTS NOW. Do not repeat the same action.]"
                        
                        observation_history.append(observation)
                        self._log(f"Observation: {observation}")
                    except Exception as e:
                        observation = f"Error executing {action}: {e}"
                        self._log(f"Error: {observation}")
                else:
                    observation = f"Error: Tool '{action}' not found."
                
                obs_text = f"\nObservation: {observation}\nThought:"
                prompt += obs_text
                self.active_scratchpad += obs_text
            else:
                # No Action and no Final Answer found in output
                if "Action:" in output and "Action Input:" not in output:
                     # Model started an action but didn't provide input — help it complete
                     prompt += "\nAction Input:"
                     self.active_scratchpad += "\nAction Input:"
                     continue
                
                if not output.strip():
                    return "Error: Agent produced empty response."

                # ----------------------------------------------------------------
                # Format correction: the model produced a natural-language response
                # without the ReAct format markers. Force a format correction instead of
                # blindly assuming it's a final answer.
                # ----------------------------------------------------------------
                clean_output = output.replace("Thought:", "").strip()
                
                # If it's very short and not a final answer, give the model a chance to correct
                if not hasattr(self, '_consecutive_format_errors'):
                    self._consecutive_format_errors = 0
                self._consecutive_format_errors += 1
                
                if self._consecutive_format_errors >= 4:
                    self._log("⚠️ Model ignored format rules repeatedly. Forwarding its raw thought to the user as a Final Answer.")
                    self._consecutive_format_errors = 0
                    
                    # Preservation check identical to Final Answer
                    is_question_end = clean_output.endswith("?")
                    question_markers = ["czy", "pytanie", "question", "should i", "decide"]
                    is_question_content = any(m in clean_output.lower() for m in question_markers)
                    
                    if is_question_end or is_question_content:
                        self._log("Context Preserved: Raw output implies a question.")
                    else:
                        self.active_scratchpad = ""
                    return clean_output
                
                self._log(f"⚠️ Format error ({self._consecutive_format_errors}/4). Prompting for correction.")
                self._log(f"--- RAW OUTPUT CAUSING ERROR ---\n{output}\n--------------------------------")
                fmt_error = "\nObservation: You did not use a valid format. You MUST Output exactly ONE 'Action:' line followed by ONE 'Action Input:' line. Or if you are finished, use 'Final Answer:'. Do not just 'think'.\nThought:"
                prompt += fmt_error
                self.active_scratchpad += fmt_error


        return f"Agent reached safety limit of {max_steps} steps without finishing. To prevent excessive API usage, I have stopped here. You can ask me to 'continue' if you believe more progress can be made."
