import os
import re
import io
import ast
import json
import time
import difflib
import datetime
import traceback
import contextlib
import subprocess
from typing import List, Optional, Dict, Any, Union, Tuple
from dataclasses import dataclass

# Robust Message Imports
try:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
except ImportError:
    try:
        from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
    except ImportError:
        class BaseMessage: pass
        class HumanMessage(BaseMessage): pass
        class AIMessage(BaseMessage): pass
        class SystemMessage(BaseMessage): pass

try:
    from langchain_openai import ChatOpenAI
    from langchain_core.tools import StructuredTool
    from langchain_community.agent_toolkits import FileManagementToolkit
except ImportError:
    from langchain.chat_models import ChatOpenAI
    from langchain.tools import StructuredTool
    try:
        from langchain.agent_toolkits import FileManagementToolkit
    except ImportError:
        FileManagementToolkit = None 

# Local tool imports
from omni_agent.core.checkpoint_manager import CheckpointManager
from omni_agent.core.tools import (
    DocumentTools, OCRTools, CountPatternTool, FolderTools, 
    PandocTools, VisionTools, WebSearchTools, ChartTools, 
    PythonREPL, SearchTools, ViewFileTool, ReplaceFileContentTool, 
    TerminalTool, UpdateContextTool, AudioTools,
    GitTools, APITools, DatabaseTools
)

try:
    from omni_agent.core.mcp_tools import PlaywrightMCPTools
except ImportError:
    PlaywrightMCPTools = None

@dataclass
class ModelProfile:
    tier: int
    name: str
    context_window: int
    max_observation_chars: int
    max_read_blocks: int
    max_read_rows: int

def get_model_profile(model_name: str, custom_profiles: dict = None) -> ModelProfile:
    PROFILES = {
        1: ModelProfile(1, "ULTRA", 256_000, 60_000, 500, 200),
        2: ModelProfile(2, "LARGE", 262_144, 40_000, 300, 150),
        3: ModelProfile(3, "BASE",  64_000, 20_000, 150, 80),
        4: ModelProfile(4, "SMALL", 16_000, 8_000, 50, 20)
    }

    m_lower = model_name.lower()
    custom_profiles = custom_profiles or {}

    # 1. Check User Override (Exact or partial match)
    for custom_name, tier in custom_profiles.items():
        if custom_name.lower() == m_lower or custom_name.lower() in m_lower:
            return PROFILES.get(int(tier), PROFILES[3])

    # 2. Check Regex for Mixture of Experts (MoE), e.g., 8x7b
    moe_match = re.search(r'(\d+)x(\d+(?:\.\d+)?)b\b', m_lower)
    if moe_match:
        experts = float(moe_match.group(1))
        size_per_expert = float(moe_match.group(2))
        total_params = experts * size_per_expert
    else:
        # 3. Check Regex for Standard Models, e.g., 70b, 8.0b
        std_match = re.search(r'(\d+(?:\.\d+)?)b\b', m_lower)
        if std_match:
            total_params = float(std_match.group(1))
        else:
            total_params = None

    # Thresholds for Tiers
    if total_params is not None:
        if total_params >= 100:
            return PROFILES[1]
        elif total_params >= 35:
            return PROFILES[2]
        elif total_params >= 10:
            return PROFILES[3]
        else:
            return PROFILES[4]

    # 4. Fallback to Known Flagships (Commercial APIs / Models without 'B')
    if any(kw in m_lower for kw in ["deepseek-v3", "deepseek-r1", "o1-preview"]):
        return PROFILES[1]
    
    if any(kw in m_lower for kw in ["gpt-4", "claude-3-opus", "claude-3-5-sonnet", "claude-3.5-sonnet", "claude-3-7-sonnet", "claude-3.7-sonnet", "gemini-1.5-pro", "gemini-2.0-pro"]):
        return PROFILES[2]

    if any(kw in m_lower for kw in ["gpt-3.5", "gpt-4o-mini", "claude-3-haiku", "claude-3.5-haiku", "claude-3-5-haiku", "gemini-1.5-flash", "gemini-2.0-flash", "o1-mini"]):
        return PROFILES[3]

    # 5. Default Fallback
    return PROFILES[3]

class LangChainAgentEngine:
    def __init__(self, api_key: str, model_name: str, workspace_path: str, 
                 log_callback=None, custom_instructions: str = None, 
                 llm_instructions: str = None, few_shot_examples: List[tuple] = None,
                 max_tokens: int = 4096, system_prompt_additions: str = None,
                 context_window: int = 0, tool_filter: set = None,
                 base_url: str = "https://llm.hpc.pcss.pl/v1",
                 transcription_model: str = "whisper-large-v3-turbo:0.8b"):
        self.api_key = api_key
        self.model_name = model_name
        self.workspace_path = workspace_path
        self.base_url = base_url
        self.transcription_model = transcription_model
        self.log_callback = log_callback
        self.custom_instructions = custom_instructions or ""
        self.llm_instructions = llm_instructions or ""
        self.system_prompt_additions = system_prompt_additions or ""
        self.few_shot_examples = few_shot_examples or []
        self.max_tokens = max_tokens
        
        # --- Tiered Model Profiling ---
        try:
            from omni_agent.config import ConfigManager
            config_mgr = ConfigManager()
            custom_profiles = config_mgr.get("custom_model_profiles", {})
        except ImportError:
            custom_profiles = {}
            
        self.profile = get_model_profile(self.model_name, custom_profiles)
        
        # Override context window if provided explicitly by user/profile
        self.context_window = context_window if context_window > 0 else self.profile.context_window

        self.tool_filter = tool_filter  # Consilium: restrict to read-only tools
        self.active_scratchpad = "" # Persistence layer for long tasks
        self._consecutive_format_errors = 0
        self._is_cancelled = False
        self.checkpoint_manager = CheckpointManager(workspace_path)
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
        # --- Persistent file logger ---
        # Writes every message to agent_debug.log in the APPLICATION directory
        # (next to omni_agent/), NOT in the user's workspace.
        try:
            app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            log_path = os.path.join(app_dir, "agent_debug.log")
            # Auto-rotate: if file exceeds 5 MB, truncate it.
            if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(f"[LOG ROTATED at {datetime.datetime.now().isoformat()}]\n")
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}][{self.model_name}] {message}\n")
        except Exception:
            pass  # Never let logger crash the agent

    def _write_status_file(self, status: str, details: str = ""):
        """Writes .agent_status.md to the workspace (hidden ephemeral status file).

        Named with a leading dot to stay out of the user's project files.
        CLAUDE.md is intentionally NOT used — it collides with Claude Code's
        project-instruction convention and is reserved for human-authored content.
        """
        try:
            status_path = os.path.join(self.workspace_path, ".agent_status.md")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content = "# Agent Status\n\n"
            content += f"- **Status:** {status}\n"
            content += f"- **Model:** {self.model_name}\n"
            content += f"- **Updated:** {ts}\n"
            if details:
                content += f"\n## Details\n\n{details}\n"
            with open(status_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass  # Never let status writer crash the agent

    def _bootstrap_context_file(self, first_prompt: str):
        """Creates .agent_context.md when it does not yet exist in the workspace.

        Generates a structured project-description template populated with the
        user's first prompt.  The agent is expected to keep the file updated via
        the update_context tool as the work progresses.
        """
        context_path = os.path.join(self.workspace_path, ".agent_context.md")
        if os.path.exists(context_path):
            return  # Already initialised — never overwrite

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Heuristic: is this a descriptive project task or a one-liner command?
        _words = first_prompt.strip().split()
        is_descriptive = len(_words) >= 6

        goal_text = first_prompt.strip() if is_descriptive else f"*(describe the project goal here)*\n\nFirst task: {first_prompt.strip()}"

        template = f"""# Project Context

**Created:** {ts}
**Model:** {self.model_name}

## Project Goal

{goal_text}

## Technology Stack

*(to be identified — e.g. Python 3.11, FastAPI, PostgreSQL, React …)*

## Current Status

🆕 Just started

## Completed

*(nothing yet)*

## Todo

- [ ] {_words[0].capitalize() + ' ' + ' '.join(_words[1:]) if _words else 'Initial task'}

## Architecture & Key Decisions

*(document important design choices here)*

## Notes

*(free-form notes, links, references)*
"""
        try:
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(template)
            self._log("📄 Initialised .agent_context.md with project template.")
        except Exception:
            pass

    def _initialize_agent(self):
        # 1. Initialize LLM with performance optimizations
        self.llm = ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            model=self.model_name,
            temperature=0.2,  # Small randomness to prevent deterministic loops
            max_tokens=self.max_tokens,  # Dynamic token limit based on LLM profile
            request_timeout=120  # 2 minute timeout
        )

        # 2. Initialize Tools
        toolkit = FileManagementToolkit(root_dir=str(self.workspace_path))

        # Filter out native read_file to force usage of our line-based view_file
        self.tools = [t for t in toolkit.get_tools() if t.name != "read_file"]
        
        # Add Document Tools with Profile limits
        doc_tools = DocumentTools(
            root_dir=str(self.workspace_path), 
            model_name=self.model_name,
            max_chars=self.profile.max_observation_chars,
            max_read_blocks=self.profile.max_read_blocks,
            max_rows=self.profile.max_read_rows
        )
        self.tools.extend(doc_tools.get_tools())

        # Add OCR Tools
        ocr_tools = OCRTools(root_dir=str(self.workspace_path), api_key=self.api_key, base_url=self.base_url)
        self.tools.extend(ocr_tools.get_tools())

        # Add Audio Tools
        audio_tools = AudioTools(root_dir=str(self.workspace_path), api_key=self.api_key, base_url=self.base_url, default_model=self.transcription_model)
        self.tools.extend(audio_tools.get_tools())

        # Add Counting Tool
        counting_tool = CountPatternTool(root_dir=str(self.workspace_path))
        self.tools.extend(counting_tool.get_tools())

        # Add Folder Tools
        folder_tools = FolderTools(root_dir=str(self.workspace_path))
        self.tools.extend(folder_tools.get_tools())

        # Add Pandoc Tools
        pandoc_tools = PandocTools(root_dir=str(self.workspace_path))
        self.tools.extend(pandoc_tools.get_tools())

        # Vision tools - specifically use Qwen3-VL for image analysis
        vision_model = "Qwen3-VL-235B-A22B-Instruct"
        vision_tools = VisionTools(root_dir=str(self.workspace_path), api_key=self.api_key, model_name=vision_model, base_url=self.base_url)
        self.tools.extend(vision_tools.get_tools())

        # Add Web Search Tools
        web_search_tools = WebSearchTools(
            api_key=self.api_key, 
            model_name=self.model_name,
            base_url=self.base_url
        )
        self.tools.extend(web_search_tools.get_tools())

        # Add Chart Generation Tools
        chart_tools = ChartTools(root_dir=str(self.workspace_path))
        self.tools.extend(chart_tools.get_tools())

        # Add Smart Document Tools (Docling-powered, optional)
        # Requires: pip install docling pillow
        try:
            from omni_agent.core.smart_doc_tools import SmartDocumentTools, DOCLING_AVAILABLE
            if DOCLING_AVAILABLE:
                smart_doc = SmartDocumentTools(
                    root_dir=str(self.workspace_path),
                    api_key=self.api_key,
                    base_url=self.base_url,
                    log_callback=self._log
                )
                self.tools.extend(smart_doc.get_tools())
                self._log("✓ Smart Document Tools (Docling) loaded")
            else:
                self._log("ℹ Smart Document Tools unavailable (install: pip install docling pillow)")
        except ImportError:
            self._log("ℹ Smart Document Tools unavailable (install: pip install docling pillow)")

        # Add Python REPL with Profile limits
        repl = PythonREPL(
            root_dir=str(self.workspace_path),
            max_chars=self.profile.max_observation_chars
        )
        self.tools.extend(repl.get_tools())

        # Add Search Tools
        search_tools = SearchTools(root_dir=str(self.workspace_path))
        self.tools.extend(search_tools.get_tools())

        # Add View File Tool with Profile limits
        view_file_tool = ViewFileTool(
            root_dir=str(self.workspace_path), 
            model_name=self.model_name,
            max_chars=self.profile.max_observation_chars
        )
        self.tools.extend(view_file_tool.get_tools())

        # Add Replace File Content Tool
        replace_file_tool = ReplaceFileContentTool(root_dir=str(self.workspace_path))
        self.tools.extend(replace_file_tool.get_tools())

        # Add Terminal Tool with Profile limits
        terminal_tool = TerminalTool(
            root_dir=str(self.workspace_path),
            max_chars=self.profile.max_observation_chars
        )
        self.tools.extend(terminal_tool.get_tools())

        # Add Context Tool
        context_tool = UpdateContextTool(root_dir=str(self.workspace_path))
        self.tools.extend(context_tool.get_tools())

        # Add Git Tools
        try:
            git_tools = GitTools(root_dir=str(self.workspace_path))
            self.tools.extend(git_tools.get_tools())
            self._log("✓ Git Tools loaded (git_status, git_diff, git_log)")
        except Exception as e:
            self._log(f"ℹ Git Tools unavailable: {e}")

        # Add API Tools
        try:
            api_tools = APITools()
            self.tools.extend(api_tools.get_tools())
            self._log("✓ API Tools loaded (http_request)")
        except Exception as e:
            self._log(f"ℹ API Tools unavailable: {e}")

        # Add Database Tools
        try:
            db_tools = DatabaseTools(root_dir=str(self.workspace_path))
            self.tools.extend(db_tools.get_tools())
            self._log("✓ Database Tools loaded (execute_sql_query)")
        except Exception as e:
            self._log(f"ℹ Database Tools unavailable: {e}")

        # Add MCP Tools (Playwright Server)
        if PlaywrightMCPTools is not None:
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

        # Consilium: filter to read-only tools if requested
        if self.tool_filter:
            self.tools = [t for t in self.tools if t.name in self.tool_filter]
            self._log(f"Tool filter active: {len(self.tools)} tools available ({', '.join(t.name for t in self.tools)})")

        self.tool_map = {t.name: t for t in self.tools}

    def run_step(self, prompt, stop=None):
         return self.llm.invoke(prompt, stop=stop).content

    # Intelligent Run method with loop detection and flexible limits
    def run(self, input_text: str, chat_history: List = None, initial_scratchpad: str = ""):
        # RESET format error counter on new user message to break stagnation loops
        self._consecutive_format_errors = 0
        self._hallucination_gate_fired = False  # Allow one gate check per run
        self._is_cancelled = False
        
        if chat_history is None:
            chat_history = []

        tool_names = ", ".join(self.tool_map.keys())
        tool_descriptions = "\n".join([f"{t.name}: {t.description}" for t in self.tools])
        
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")

        vision_rule = "- Use `analyze_image` to review UI screenshots, analyze charts, or understand mockups." if "Qwen3" in self.model_name else "- You DO NOT have vision capabilities. DO NOT use `analyze_image`."

        # Build Few-Shot Examples if any
        few_shot_text = ""
        if self.few_shot_examples:
            few_shot_text = "\n### OUTSTANDING EXAMPLES OF PREVIOUS INTERACTIONS TO EMULATE ###\n"
            for idx, (q, a) in enumerate(self.few_shot_examples, 1):
                few_shot_text += f"\n--- Example {idx} ---\nQuestion: {q}\nFinal Answer: {a}\n"
            few_shot_text += "################################################################\n"

        system_template = f"""You are an AI assistant with tools. Date: {current_date}
Current Workspace (Root Directory): {self.workspace_path}

{self.system_prompt_additions}

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
- You MUST output at most ONE 'Action:' and ONE matching 'Action Input:' block per step. After each Action you MUST wait for the Observation before deciding the next step.
- Before you claim that something was implemented, created, or verified (e.g., "aplikacja obsługuje X", "wszystkie wymagania zostały zaimplementowane"), you MUST first confirm it using appropriate tools such as `list_directory`, `view_file`, `run_python` or `run_terminal`. Never describe features that are not actually present in the code or files you have just created.

{self.llm_instructions}

{f"User Instructions: " + self.custom_instructions if self.custom_instructions else ""}

{self._load_workspace_context()}
{few_shot_text}
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

        # Continuation logic: if user says "continue" (or similar) and we have a scratchpad, resume.
        continue_keywords = ["kontynuuj", "continue", "wznów", "resume", "dalej", "go on"]
        # Only treat as structural continue if it's a short "continue" type message
        is_continuation_intent = any(kw in input_text.lower() for kw in continue_keywords) and len(input_text.strip().split()) <= 3
        
        if is_continuation_intent and initial_scratchpad:
            self.active_scratchpad = initial_scratchpad
            self._log("🔄 Resuming from saved scratchpad context.")
        else:
            self.active_scratchpad = ""  # Ensure clean start for genuinely new tasks
            
        # Bootstrap .agent_context.md on the very first run in this workspace
        if not is_continuation_intent:
            self._bootstrap_context_file(input_text)

        # Create a restore-point before the agent touches anything
        cp_id = self.checkpoint_manager.create(input_text[:120])
        if cp_id:
            mode = self.checkpoint_manager.mode()
            self._log(f"🔖 Checkpoint created [{mode}]: {cp_id[:14]}…")
        else:
            self._log("⚠️ Could not create checkpoint (workspace may be read-only).")

        self._write_status_file("🔄 Working", f"Processing: {input_text[:200]}")
        self._log(f"🚀 Execution started for model: {self.model_name} (Tier: {self.profile.tier})")
        self._log(f"📊 Profile Limits: Context={self.profile.context_window} | Observation={self.profile.max_observation_chars} | Blocks={self.profile.max_read_blocks} | Rows={self.profile.max_read_rows}")
        
        # Inject planning instructions for high-capability models (ULTRA/LARGE)
        if self.profile.tier <= 2:
            planning_block = (
                "\n- PLANNING (complex tasks): In your very first Thought, write a brief numbered plan "
                "before executing: 'Plan: 1. [action] → 2. [action] → 3. [verify]'. "
                "This reduces unnecessary back-and-forth significantly.\n"
            )
            system_template = system_template.replace("Begin!", planning_block + "Begin!")

        prompt = f"{system_template}\n{history_text}\nQuestion: {input_text}\nThought:"

        max_steps = 100
        self._consecutive_format_errors = 0  # Reset format error counter
        self._empty_response_count = 0       # Reset empty-response counter
        action_history = []
        thought_history = []
        observation_history = []
        action_loop_warnings = {}   # key: action signature → consecutive warning count
        total_loop_warnings = 0     # cumulative across all signatures (hard safety cap)
        consecutive_stream_errors = 0  # circuit breaker for back-to-back llm.stream() failures
        last_executed_tool = None
        
        i = 0
        while i < max_steps:
            # Reset variables at start of each iteration to prevent stale values
            action = None
            action_input = None
            tool_args = None
            match = None
            pending_observation_prefix = ""
            
            self._log(f"--- Step {i+1} ---")
            
            # ── Prompt Overflow Guard (sliding window) ──────────────────────
            # If the accumulated prompt exceeds MAX_PROMPT_CHARS we trim the
            # OLDEST Observation blocks from the scratchpad while keeping:
            # 1. The immutable header  (system prompt + "Question: …\nThought:")
            # 2. The most-recent steps (everything after the oldest trimmed block)
            # A notice is injected so the model knows history was compressed.
            #
            # Dynamic limit: if context_window is set in the profile, compute
            # a character budget that leaves room for max_tokens output.
            # We use ~3.5 chars per token as a safe average.
            if self.context_window > 0:
                available_input_tokens = self.context_window - self.max_tokens
                MAX_PROMPT_CHARS = max(10_000, int(available_input_tokens * 3.5))
            else:
                MAX_PROMPT_CHARS = 300_000
            
            # --- Dynamic Context Logging ---
            est_tokens = int(len(prompt) / 3.5)
            usage_pct = (len(prompt) / MAX_PROMPT_CHARS) * 100
            limit_tokens = int(MAX_PROMPT_CHARS / 3.5)
            self._log(f"Context: {len(prompt)} chars (~{est_tokens} tokens) | {usage_pct:.1f}% of {MAX_PROMPT_CHARS} chars (~{limit_tokens} tokens) limit")

            # ── Proactive Context Compression (60% threshold) ────────────────
            # Compresses BEFORE the buffer overflows to prevent TTFT spikes.
            # The reactive overflow guard below (at 100%) stays as safety net.
            PROACTIVE_THRESHOLD = 0.60
            usage_ratio = len(prompt) / MAX_PROMPT_CHARS
            if usage_ratio > PROACTIVE_THRESHOLD and not getattr(self, '_proactive_trim_done_this_step', False):
                self._proactive_trim_done_this_step = True
                _header_marker = "\nThought:"
                _header_end = prompt.find(_header_marker)
                if _header_end != -1:
                    _hdr = prompt[: _header_end + len(_header_marker)]
                    _body = prompt[_header_end + len(_header_marker):]
                    _obs_blocks = _body.split("\nObservation:")
                    _n_total = len(_obs_blocks)
                    _n_remove = max(1, min(8, _n_total // 4))  # remove ~25%, cap at 8 blocks
                    _removed = 0
                    while _removed < _n_remove and len(_obs_blocks) > 2:
                        _obs_blocks.pop(1)
                        _removed += 1
                    _trim_notice = (
                        f"\n[SYSTEM: {_removed} najstarszych kroków skompresowano "
                        f"(kontekst: {usage_ratio*100:.0f}% limitu). Kontynuuj normalnie.]\n"
                    )
                    prompt = _hdr + _trim_notice + "\nObservation:".join(_obs_blocks)
                    self.active_scratchpad = prompt[_header_end + len(_header_marker):]
                    self._log(
                        f"\U0001f5dc\ufe0f Proactive compression at {usage_ratio*100:.0f}%: "
                        f"removed {_removed}/{_n_total} obs blocks \u2192 {len(prompt):,} chars."
                    )
            else:
                self._proactive_trim_done_this_step = False
            # ─────────────────────────────────────────────────────────────────

            # ── Reactive overflow guard (100% threshold — safety net) ─────────
            if len(prompt) > MAX_PROMPT_CHARS:
                # Split at the first "\nThought:" that follows the Question line
                # Everything before (and including) that marker is the immutable header.
                header_marker = "\nThought:"
                header_end = prompt.find(header_marker)
                if header_end != -1:
                    header   = prompt[: header_end + len(header_marker)]
                    body     = prompt[header_end + len(header_marker):]
                    
                    # The body is a sequence of "…\nObservation: …\nThought:" blocks.
                    # Split on every "\nObservation:" boundary so we can drop blocks
                    # from the front until we fit within the limit.
                    obs_blocks = body.split("\nObservation:")
                    # obs_blocks[0]  = first Thought text (before first Observation)
                    # obs_blocks[1:] = each "obs_text\nThought:…" chunk
                    
                    trim_notice = (
                        "\n[SYSTEM: Earlier steps were trimmed to protect the context window. "
                        "The task and your most recent steps are shown below. Continue normally.]\n"
                    )
                    
                    # Drop blocks from the front (oldest first) until we fit
                    while len(obs_blocks) > 2 and \
                          len(header + trim_notice + "\nObservation:".join(obs_blocks)) > MAX_PROMPT_CHARS:
                        obs_blocks.pop(1)  # remove oldest Observation block (index 1)
                    
                    trimmed_body = "\nObservation:".join(obs_blocks)
                    prompt = header + trim_notice + trimmed_body
                    self._log(
                        f"⚠️ Prompt overflow: trimmed to {len(prompt):,} chars "
                        f"(original > {MAX_PROMPT_CHARS:,})."
                    )
            # ────────────────────────────────────────────────────────────────

            # Invoke LLM with stop sequence
            self._log("Thinking...")
            
            output = ""
            # Stop at "Observation:" — the intended ReAct stop marker.
            # Active stream-break: once we accumulate a complete Action + Action Input
            # pair in the buffer we break immediately, preventing models (e.g. MiniMax)
            # that ignore stop sequences from streaming indefinitely.
            _action_input_done_re = re.compile(
                # Matches a COMPLETE Action Input value. This regex is used to
                # break the LLM stream early once the model has finished writing
                # an action. It must NOT match incomplete JSON like `{` or `{"` —
                # those would cut the model off before it can write the filename.
                #
                # Alternatives (in order of priority):
                # 1. Complete JSON object with AT LEAST one key-value pair:
                #    {"key"  (we only require the key started, not the full pair,
                #    because the model might use a stop sequence before closing}
                # 2. Complete flat JSON:  {"key": value}  or  {}  (empty)
                # 3. Quoted string value: "some value"
                # 4. Plain unquoted value (not starting with { or "): ./path, tool_name
                r'Action Input:\s*('
                r'\{[^{}]*"[^"]+"[^{}]*\}'   # complete JSON with >=1 key: {"k": v}
                r'|\{\}'                        # empty JSON: {}
                r'|"[^"]+"'                     # quoted string: "value"
                r'|[^\n{"\s][^\n]+'             # plain unquoted value
                r')'
            )
            _stream_break_reason = "stop_sequence_or_eos"
            _t_stream_start = time.monotonic()
            _t_first_token = None
            _token_count = 0
            _stream_error = None
            try:
                for chunk in self.llm.stream(prompt, stop=["Observation:"]):
                    if self._is_cancelled:
                        _stream_break_reason = "user_cancelled"
                        break
                    if chunk.content:
                        # Record Time-to-First-Token
                        if _t_first_token is None:
                            _t_first_token = time.monotonic()
                            _ttft = _t_first_token - _t_stream_start
                            self._log(f"⏱️ TTFT (Time-to-First-Token): {_ttft:.2f}s")
                        _token_count += 1
                        output += chunk.content
                        yield chunk.content
                        # Break as soon as we have a parseable Action + Input pair
                        has_react = "Action:" in output and "Action Input:" in output
                        has_xml = "<invoke" in output

                        if has_react or has_xml:
                            if has_xml and "</invoke>" in output:
                                _stream_break_reason = "active_break_xml_invoke"
                                break
                            elif has_react and _action_input_done_re.search(output):
                                _stream_break_reason = "active_break_complete_action"
                                break
            except Exception as stream_exc:
                _stream_error = stream_exc
                _stream_break_reason = f"stream_exception:{type(stream_exc).__name__}"
                self._log(f"❌ LLM stream error: {type(stream_exc).__name__}: {stream_exc}")

            # If stream failed before producing any output, inject a recovery observation
            # instead of crashing — this preserves scratchpad and gives the agent a chance
            # to recover or the user a clean error message.
            # Circuit breaker: after N consecutive stream failures the server is effectively
            # unavailable — bail out with a rich diagnostic instead of retrying forever.
            if _stream_error is not None and not output.strip():
                consecutive_stream_errors += 1
                err_msg = f"{type(_stream_error).__name__}: {_stream_error}"[:300]

                _is_rate_limit = (
                    "429" in err_msg
                    or "rate limit" in err_msg.lower()
                    or "ratelimit" in err_msg.lower()
                    or "too many requests" in err_msg.lower()
                    or "RateLimitError" in err_msg
                )

                if _is_rate_limit:
                    # Detect the daily quota exhaustion
                    _err_lower = err_msg.lower()
                    _is_daily_limit = (
                        "per-day" in _err_lower
                        or "per_day" in _err_lower
                        or "daily" in _err_lower
                        or "requests per day" in _err_lower
                    )

                    if not hasattr(self, "_consecutive_rl_errors"):
                        self._consecutive_rl_errors = 0
                    self._consecutive_rl_errors += 1

                    if _is_daily_limit:
                        # Daily limit hit — waiting 5s WON'T help, stop now
                        self._log(
                            f"🚫 Daily free-tier limit exhausted for model '{self.model}'. "
                            "Stopping agent — please switch to a different model."
                        )
                        yield (
                            f"\n⚠️ **Dzienny limit darmowych żądań wyczerpany** dla modelu `{self.model}`.\n\n"
                            "OpenRouter nie zaakceptuje kolejnych żądań do północy UTC. "
                            "**Zmień model** na inny (np. `nvidia/llama-3.1-nemotron-70b-instruct` "
                            "lub inny darmowy model z inną pulą limitów) i utwórz nowego asystenta.\n"
                        )
                        return (
                            f"Agent zatrzymany: dzienny limit darmowych żądań wyczerpany "
                            f"dla modelu {self.model}.\n\n"
                            "Zmień model w panelu bocznym i kliknij 'Create Assistant' aby wznowić pracę."
                        )

                    # Per-minute limit — exponential backoff: 5s → 10s → 20s
                    _backoff_slot = min(self._consecutive_rl_errors, 3)
                    _wait_secs = 5 * (2 ** (_backoff_slot - 1))  # 5, 10, 20

                    if self._consecutive_rl_errors > 3:
                        # 3+ consecutive per-minute limits → daily cap likely hit indirectly
                        self._log(
                            f"🚫 {self._consecutive_rl_errors} kolejnych limitów 429 z rzędu "
                            f"dla '{self.model}'. Przerywam — zmień model."
                        )
                        yield (
                            f"\n⚠️ **Limit żądań (429) wystąpił {self._consecutive_rl_errors} razy z rzędu** "
                            f"dla modelu `{self.model}`.\n\n"
                            "Prawdopodobnie wyczerpałeś dzienny lub minutowy darmowy limit. "
                            "**Zmień model** na inny i utwórz nowego asystenta.\n"
                        )
                        return (
                            f"Agent zatrzymany po {self._consecutive_rl_errors} kolejnych błędach 429 "
                            f"dla modelu {self.model}.\n\n"
                            "Zmień model w panelu bocznym i kliknij 'Create Assistant'."
                        )

                    self._log(
                        f"⏳ Rate limited (429 per-min) — retry {self._consecutive_rl_errors}/3, "
                        f"waiting {_wait_secs}s..."
                    )
                    yield f"\n[Rate limit per-min — retry {self._consecutive_rl_errors}/3, czekam {_wait_secs}s...]\n"
                    import time as _time_mod
                    _time_mod.sleep(_wait_secs)
                    # Do NOT consume a circuit-breaker slot for rate limits
                    consecutive_stream_errors = max(0, consecutive_stream_errors - 1)
                    recovery_obs = (
                        f"\nObservation: [SYSTEM] Request was rate-limited (429 per-min). "
                        f"Waited {_wait_secs}s. Continue from where you left off.\nThought:"
                    )
                    prompt += recovery_obs
                    self.active_scratchpad += recovery_obs
                    continue
                # --- end rate-limit block ---

                # Reset rate-limit counter on non-rate-limit stream errors
                if hasattr(self, "_consecutive_rl_errors"):
                    self._consecutive_rl_errors = 0



                if consecutive_stream_errors >= 3:
                    self._log(f"⛔ Circuit breaker: {consecutive_stream_errors} consecutive stream errors — stopping.")
                    last_action = action_history[-1] if action_history else ("(none)", "")
                    recent_obs = observation_history[-1][:200] if observation_history else "(brak)"
                    return (
                        f"Agent zatrzymany: 3 błędy streamu LLM z rzędu.\n\n"
                        f"**Ostatni błąd:** {err_msg}\n"
                        f"**Ostatnia akcja:** {last_action[0]}({str(last_action[1])[:60]})\n"
                        f"**Ostatnia obserwacja:** {recent_obs}\n\n"
                        "Serwer LLM prawdopodobnie jest chwilowo niedostępny. "
                        "Spróbuj ponownie za chwilę lub wybierz inny model."
                    )

                recovery_obs = (
                    f"\nObservation: [SYSTEM] LLM stream failed ({err_msg}). "
                    f"Retry {consecutive_stream_errors}/3. The server may be temporarily unavailable. "
                    "If this keeps failing, emit: Final Answer: [brief explanation of the problem].\nThought:"
                )
                prompt += recovery_obs
                self.active_scratchpad += recovery_obs
                continue

            # Stream produced output successfully — reset the error counter.
            if output.strip():
                consecutive_stream_errors = 0

            _t_stream_end = time.monotonic()
            _total_gen = _t_stream_end - _t_stream_start
            _gen_only = _t_stream_end - _t_first_token if _t_first_token else 0
            _approx_tps = _token_count / _gen_only if _gen_only > 0 else 0
            self._log(
                f"[STREAM] Ended. Reason: {_stream_break_reason}. "
                f"Output: {len(output)} chars (~{_token_count} chunks). "
                f"Total: {_total_gen:.1f}s | TTFT: {(_t_first_token - _t_stream_start) if _t_first_token else 0:.1f}s | "
                f"Generation: {_gen_only:.1f}s | ~{_approx_tps:.1f} chunks/s"
            )

            # ── Strip <think> reasoning tags (GLM-4, Qwen3, DeepSeek, etc.) ──
            # CoT models emit <think>...</think> blocks that leak into the
            # raw output and confuse the ReAct format parser. Remove them
            # before any parsing happens.
            if '</think>' in output:
                # 1. Full <think>content</think> blocks
                output = re.sub(r'<think>.*?</think>\s*', '', output, flags=re.DOTALL)
                # 2. Orphaned closing tag at start (e.g. "wi.</think>...")
                output = re.sub(r'^[^<]*</think>\s*', '', output)
                output = output.strip()

            # print(f"--- Step {i} ---\nLLM Output:\n{output}\n----------------")
            self._log(f"Agent Thought:\n{output}")
            
            # Smart Loop Detection (Thoughts)
            # Normalize thought (remove whitespace/newlines for comparison)
            current_thought = output.replace("Thought:", "").strip()
            
            # Strict stop only after 5 consecutive identical thoughts
            if len(thought_history) >= 4 and all(current_thought == t for t in thought_history[-4:]):
                self._log("⚠️ Thought Loop detected! Agent is repeating itself 5 times.")
                stuck_thought = current_thought[:300]
                recent_obs = observation_history[-1][:200] if observation_history else "(brak)"
                return (
                    "Agent zatrzymany: wykryto pętlę myśli (5 identycznych 'Thought:' z rzędu).\n\n"
                    f"**Powtarzająca się myśl:** {stuck_thought}\n\n"
                    f"**Ostatnia obserwacja:** {recent_obs}\n\n"
                    "Prawdopodobnie zadanie jest ukończone lub agent utknął. Sprecyzuj pytanie lub podaj dodatkowy kontekst."
                )
            
            # Warning on 3rd identical thought
            if len(thought_history) >= 2 and current_thought == thought_history[-1] and current_thought == thought_history[-2]:
                 self._log("⚠️ Potential Thought Loop (3rd occurrence). Injecting warning.")
                 warning_msg = "\nObservation: Warning: You are repeating your exact same thought. Please move to the next step or change your approach.\nThought:"
                 prompt += warning_msg
                 self.active_scratchpad += warning_msg
            
            thought_history.append(current_thought)

            # ── Early output truncation ──────────────────────────────────────
            # Some models (e.g. MiniMax) keep streaming after "Action Input:"
            # MiniMax hallucination guard: the model sometimes emits multiple
            # Action blocks in a single stream. Truncate to the FIRST complete
            # Action+Input pair so the context never gets poisoned.
            #
            # IMPORTANT: Only activate when there are ≥2 "Action:" markers.
            # For a single Action (e.g. run_python with long code), do NOT truncate —
            # the old regex was matching the first } inside a JSON code string and
            # cutting the rest, producing "unterminated string literal" errors.
            action_block_count = output.count("Action:")
            invoke_block_count = output.count("<invoke")
            if (action_block_count >= 2 and "Action Input:" in output) or (invoke_block_count >= 2):
                if action_block_count >= 2 and "Action Input:" in output:
                    # Find where the FIRST Action Input value ends.
                    # Use a brace-depth counter to find the matching closing }
                    # for JSON objects, so we don't cut inside nested strings.
                    first_input_match = re.search(r'Action Input:\s*', output)
                    if first_input_match:
                        pos = first_input_match.end()
                        if pos < len(output) and output[pos] == '{':
                            # Walk forward counting brace depth
                            depth = 0
                            in_str = False
                            esc = False
                            end_pos = pos
                            for k in range(pos, len(output)):
                                ch = output[k]
                                if esc:
                                    esc = False
                                elif ch == '\\' and in_str:
                                    esc = True
                                elif ch == '"' and not esc:
                                    in_str = not in_str
                                elif not in_str:
                                    if ch == '{':
                                        depth += 1
                                    elif ch == '}':
                                        depth -= 1
                                        if depth == 0:
                                            end_pos = k + 1
                                            break
                            tail = output[end_pos:].strip()
                        else:
                            # Plain-text action input: take until end of line
                            eol = output.find('\n', pos)
                            end_pos = eol if eol != -1 else len(output)
                            tail = output[end_pos:].strip()
                        if len(tail) > 20:
                            self._log(
                                f"⚙️ stream truncation: removed {len(tail):,} trailing chars "
                                f"({tail[:80]!r}...)"
                            )
                            output = output[:end_pos].strip()
                elif invoke_block_count >= 2:
                    first_invoke_end = output.find("</invoke>")
                    if first_invoke_end != -1:
                        end_pos = first_invoke_end + len("</invoke>")
                        tail = output[end_pos:].strip()
                        if len(tail) > 20:
                            self._log(
                                f"⚙️ XML stream truncation: removed {len(tail):,} trailing chars "
                                f"({tail[:80]!r}...)"
                            )
                            output = output[:end_pos].strip()

            prompt += output
            self.active_scratchpad += output # Mirror to scratchpad
            
            # Parse Action
            # Safety check: enforce SINGLE Action per step.
            # If multiple "Action:" markers appear in one LLM turn, salvage progress by
            # executing ONLY the first action, and attach a warning to the Observation.
            action_markers = output.count("Action:")
            invoke_markers = output.count("<invoke")
            if (action_markers > 1 or invoke_markers > 1) and "Final Answer:" not in output:
                self._log(f"⚠️ Format error: detected multiple action blocks in a single step. Salvaging by executing ONLY the first action.")
                pending_observation_prefix = (
                    "SYSTEM WARNING: You produced multiple 'Action:' blocks in a single step. "
                    "I will execute ONLY the FIRST action and ignore the rest. "
                    "Next time, output exactly ONE 'Action:' and ONE 'Action Input:' pair, then wait for the Observation.\n"
                )
                # Truncate output to the first Action/Input pair so parsers don't pick up later actions.
                first_pair_pattern = r"(Action:\s*.+?\n+Action Input:\s*.+?)(?=\n+Thought:|\n+Final Answer:|$)"
                first_pair_match = re.search(first_pair_pattern, output, re.DOTALL)
                if first_pair_match:
                    output = first_pair_match.group(1).strip()
                else:
                    # If we can't reliably salvage, fall back to correction prompt.
                    fmt_obs = "\nObservation: Format error: You produced multiple 'Action:' blocks but I could not reliably extract the first one. Output exactly ONE action.\nThought:"
                    prompt += fmt_obs
                    self.active_scratchpad += fmt_obs
                    continue
                # IMPORTANT: this is a pure format issue, so we should not treat this
                # step as part of an action loop. Clear recent action history snapshot
                # to avoid accidental loop kills caused by long, repeated plans.
                if action_history:
                    action_history.pop()

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

                # Anti-hallucination gate: do not accept "done" claims without any verification tool usage.
                # IMPORTANT: This gate fires AT MOST ONCE per run() to prevent infinite loops
                # when the answer legitimately contains claim-like words (e.g. "Gotowe" as a UI button).
                verification_tools = {"list_directory", "view_file", "run_terminal", "run_python", "search_files", "update_context"}
                claim_markers = [
                    "utworzyłem", "stworzyłem", "zakończono", "zrobione", "gotowe jest",
                    "wszystkie wymagania", "spełnia wymagania", "zaimplementowano",
                    "completed the task", "done with the task", "task is done",
                    "plik został utworzony", "skrypt został", "aplikacja została"
                ]
                looks_like_claim = any(m in final_ans.lower() for m in claim_markers)
                if not hasattr(self, '_hallucination_gate_fired'):
                    self._hallucination_gate_fired = False
                if looks_like_claim and (last_executed_tool not in verification_tools) and not self._hallucination_gate_fired:
                    self._hallucination_gate_fired = True  # Fire only once
                    self._log("⚠️ Final Answer appears to claim completion without verification. Forcing validation step.")
                    gate_obs = (
                        "\nObservation: SYSTEM CHECK: You are claiming completion. "
                        "Before answering, you MUST verify the actual workspace state using tools "
                        "(e.g., list_directory and view_file). Do not claim files/features exist without verifying.\nThought:"
                    )
                    prompt += gate_obs
                    self.active_scratchpad += gate_obs
                    continue
                
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
                
                self._write_status_file("✅ Completed", f"{final_ans[:300]}")
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
                     except (json.JSONDecodeError, KeyError, TypeError, ValueError) as fc_err:
                         self._log(f"⚙️ function_call fallback parse failed: {type(fc_err).__name__}: {fc_err}")

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

            # Fallback 5: MiniMax XML-style tool call format
            # Fallback 5: MiniMax XML-style tool call format
            # MiniMax emits: <minimax:tool_call><invoke name="tool_name"><parameter name="arg">value</parameter></invoke></minimax:tool_call>
            if not match:
                minimax_invoke = re.search(
                    r'<(?:minimax:)?tool_call[^>]*>\s*<invoke\s+name=["\']?([a-zA-Z0-9_]+)["\']?[^>]*?>?([\s\S]*?)</invoke>',
                    output
                )
                if minimax_invoke:
                    action = minimax_invoke.group(1).strip()
                    params_block = minimax_invoke.group(2)
                    
                    # Handle case where MiniMax mixed ReAct inside the token:
                    # <invoke name="list_directory [newline] Action Input: {"dir": "..."} </invoke>
                    action_input_match = re.search(r'Action Input:\s*({.*})', params_block, re.DOTALL)
                    
                    if action_input_match:
                        action_input = action_input_match.group(1).strip()
                        match = True
                        self._log(f"⚙️ Using MiniMax Hybrid XML/ReAct parser for: {action}")
                    else:
                        # Standard <parameter> extraction
                        param_pairs = re.findall(
                            r'<parameter\s+name=["\']?([a-zA-Z0-9_]+)["\']?[^>]*>([\s\S]*?)</parameter>',
                            params_block
                        )
                        args_dict = {}
                        for pname, pvalue in param_pairs:
                            pvalue = pvalue.strip()
                            try:
                                args_dict[pname] = json.loads(pvalue)
                            except (json.JSONDecodeError, ValueError):
                                args_dict[pname] = pvalue
                        action_input = json.dumps(args_dict, ensure_ascii=False)
                        match = True
                        self._log(f"⚙️ Using MiniMax XML tool-call parser for: {action}")

            # Fallback 6: Broken MiniMax XML-style hybrid without closing tags
            # e.g. <invoke name="read_docx">\nAction Input: {"file_path": "..."}
            if not match:
                broken_invoke = re.search(
                    r'<invoke\s+name=["\']?([a-zA-Z0-9_]+)["\']?[^>]*>\s*Action Input:\s*({[\s\S]*?})(?:\s*```)?',
                    output
                )
                if broken_invoke:
                    action = broken_invoke.group(1).strip()
                    action_input = broken_invoke.group(2).strip()
                    match = True
                    self._log(f"⚙️ Using broken MiniMax XML parser for: {action}")

            if match:
                if hasattr(match, 'group'):
                    action = match.group(1).strip()
                    action_input = match.group(2).strip()

                # Backtick / markdown sanitizer for the action name.
                # Some models (e.g. nvidia/llama-3.1-nemotron) wrap tool names in
                # backticks: `view_file` → the raw string contains the backtick chars
                # and the tool lookup fails with "tool not found".
                # Strip all leading/trailing backticks, asterisks, spaces.
                if action:
                    action = action.strip().strip('`').strip('*').strip()
                
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

                self._consecutive_format_errors = 0
                
                # Remove surrounding quotes only if they wrap the whole thing
                if (action_input.startswith('"') and action_input.endswith('"')) or \
                   (action_input.startswith("'") and action_input.endswith("'")):
                    action_input = action_input[1:-1].strip()
                
                # Try parsing as JSON
                try:
                    tool_args = json.loads(action_input)
                except json.JSONDecodeError:
                    # JSON Repair Block: attempt to close unclosed JSON (common for truncated outputs)
                    # e.g. GLM-4 emits only `{` or `{"` when stop=Observation: interrupts mid-JSON.
                    try:
                        stripped = action_input.strip()
                        # Case 1: Missing closing brace
                        if stripped.count('{') > stripped.count('}'):
                            # Sub-case 1a: bare `{` — close it to produce `{}`
                            if stripped == '{':
                                tool_args = {}
                            # Sub-case 1b: `{"` — close immediately to produce `{}`
                            elif stripped == '{"':
                                tool_args = {}
                            else:
                                tool_args = json.loads(stripped + '}')
                        # Case 2: Missing closing quote and brace (especially in 'text' blocks)
                        elif not stripped.endswith('"') and stripped.startswith('{'):
                             tool_args = json.loads(stripped + '"}')
                        else:
                            raise json.JSONDecodeError("Manual trigger for fallback", action_input, 0)
                    except:
                        pass
                    # Only run further fallbacks if the repair above did NOT produce a valid dict/list.
                    # Without this guard, the ast / manual fallback would overwrite a correctly repaired {}.
                    if not isinstance(tool_args, (dict, list)):
                        try:
                            # Sometimes LLMs output Python dicts instead of JSON
                            tool_args = ast.literal_eval(action_input)
                        except (SyntaxError, ValueError):
                            fixed_input = action_input.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
                            # VERY common issue: LLMs output unescaped double quotes inside JSON strings
                            # We try to escape quotes that are followed by characters other than , or } or ] or end of string
                            # This is a bit risky but often helpful. Better yet: try to find the text block and escape it.
                            if '"text": "' in fixed_input or '"replacement_content": "' in fixed_input:
                                 # Regex to find the content between the start of a key and the end of the JSON object
                                 pass # We use a more robust fallback below
                            
                            try:
                                tool_args = json.loads(fixed_input)
                            except json.JSONDecodeError:
                                # Robust extraction: finding the outer-most JSON object if parsing failed
                                # Using manual string trimming instead of regex for speed on large strings
                                start_idx = fixed_input.find('{')
                                end_idx = fixed_input.rfind('}')
                                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                                    try:
                                        tool_args = json.loads(fixed_input[start_idx:end_idx+1])
                                    except:
                                        # Final attempt: try to manually extract the fields if it's still broken
                                        tool_args = fixed_input # Fallback to string for regex extractor below
                                else:
                                     tool_args = action_input

                # Heuristic Fallback for broken JSON (especially write_file with unescaped newlines/quotes)
                if isinstance(tool_args, str) and ("{" in tool_args or ":" in tool_args):
                    try:
                        # Try to manually regex out file_path and text for write_file/edit_file
                        fp_match = re.search(r'"(?:file_path|path|directory_path|source_path)"\s*:\s*"([^"]+)"', tool_args)
                        if fp_match:
                            extracted_path = fp_match.group(1)
                            # Now try to get the text/content field if it exists
                            # We consume the rest of the string to avoid CAT, then trim manually
                            text_match = re.search(r'"(?:text|content|file_text|body|data)"\s*:\s*"(.*)', tool_args, re.DOTALL)
                            if text_match:
                                extracted_text = text_match.group(1)
                                is_truncated_fallback = False
                                # Try to strip trailing braces, spaces, and the final quote
                                rstripped = extracted_text.rstrip(' \n\r\t}')
                                if rstripped.endswith('"'):
                                    extracted_text = rstripped[:-1]
                                else:
                                    is_truncated_fallback = True
                                    extracted_text = rstripped
                                
                                tool_args = {"file_path": extracted_path, "text": extracted_text}
                                if is_truncated_fallback:
                                    tool_args["_is_truncated"] = True
                            else:
                                # Maybe it only had a path (like read_file, create_directory)
                                tool_args = {"file_path": extracted_path}
                    except Exception:
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
                                except Exception as e:
                                    self._log(f"Error parsing nested JSON: {e}")
                            except Exception as e:
                                self._log(f"Error in nested JSON logic: {e}")

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

                    if action in ["write_file", "write_docx"] and "text" not in tool_args:
                         for old_key in ["content", "file_text", "body", "data"]:
                             if old_key in tool_args:
                                 tool_args["text"] = tool_args.pop(old_key)
                                 break

                    # deep_research: LLMs often send "query" instead of "topic"
                    if action == "deep_research":
                        if "query" in tool_args and "topic" not in tool_args:
                            tool_args["topic"] = tool_args.pop("query")
                        elif "question" in tool_args and "topic" not in tool_args:
                            tool_args["topic"] = tool_args.pop("question")

                    # save_document: LLMs occasionally send "text" or "body" instead of "content"
                    if action == "save_document" and "content" not in tool_args:
                        for old_key in ["text", "body", "html", "html_content", "data", "file_text"]:
                            if old_key in tool_args:
                                tool_args["content"] = tool_args.pop(old_key)
                                break
                         
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
                
                # ── FIX: Only check Thought + Action Input for question patterns ──
                # Do NOT scan file content (save_document, write_file, write_docx)
                # because long scientific/literary texts frequently contain Polish
                # words like "czy" in a non-question context, causing false positives
                # that trigger an interception loop → prompt overflow → empty response.
                check_text = (str(action_input) + " " + output.replace("Thought:", "")).lower()
                
                # ── FIX: Length guard ──
                # If check_text is longer than 500 chars it is almost certainly
                # a document body (action_input with full HTML/text), not a short
                # question directed at the user.  Skip question detection entirely.
                is_question = False
                if len(check_text) <= 500:
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
                is_identical_loop = len(action_history) >= 2 and action_history[-1] == current_action and action_history[-2] == current_action
                
                # Check for SIMILARITY loop (for long texts that might have tiny changes like timestamps)
                is_similarity_loop = False
                if not is_identical_loop and len(action_history) >= 1 and action == action_history[-1][0]:
                    prev_obs = str(observation_history[-1]) if len(observation_history) > 0 else ""
                    # Similarity loop detection: check if previous action was similar
                    # We trigger this even if previous was an error, but with a stricter threshold
                    # to prevent "hallucinating" a fix by repeating the same failing action.
                    prev_input = action_history[-1][1]
                    if len(action_input) > 100 and len(prev_input) > 100:
                        # Slice strings to 1000 chars to keep SequenceMatcher FAST (O(N^2) complexity)
                        similarity = difflib.SequenceMatcher(None, action_input[:1000], prev_input[:1000]).ratio()
                        
                        # Tools like read_docx can have identical long filepaths but different chunk numbers.
                        # Do not enforce similarity check on such tools, or enforce a much higher threshold.
                        threshold = 0.99 if action in ["read_docx", "read_pdf", "web_read", "read_file"] else 0.95
                        
                        if similarity > threshold:
                            is_similarity_loop = True
                            self._log(f"⚠️ Similarity Loop detected (ratio: {similarity:.2f})")

                # High-capacity models can handle more "retries" or larger context
                is_large_model = (
                    ("Qwen" in self.model_name and "397B" in self.model_name) or
                    "minimax" in self.model_name.lower() or
                    "deepseek" in self.model_name.lower() or
                    "glm" in self.model_name.lower()
                )
                loop_threshold = 5 if is_large_model else 3

                if is_identical_loop or is_similarity_loop:
                    # Per-signature tracking: A→B→A→B no longer evades the counter,
                    # because each (action, input-prefix) pair has its own counter.
                    sig = (action, str(action_input)[:80])
                    sig_count = action_loop_warnings.get(sig, 0) + 1
                    action_loop_warnings[sig] = sig_count
                    total_loop_warnings += 1

                    # Hard safety cap: if we've intervened too many times total across
                    # all signatures, the agent is clearly confused — stop for good.
                    hard_cap = loop_threshold * 3
                    if total_loop_warnings >= hard_cap:
                        self._log(f"⚠️ Action Loop HARD CAP reached ({total_loop_warnings} total interventions). Stopping.")
                        recent_actions = ", ".join(f"{a[0]}({str(a[1])[:30]})" for a in action_history[-5:])
                        recent_obs = observation_history[-1][:200] if observation_history else "(none)"
                        return (
                            f"Agent zatrzymany: wykryto złożoną pętlę akcji (łącznie {total_loop_warnings} interwencji).\n\n"
                            f"**Ostatnie akcje:** {recent_actions}\n"
                            f"**Ostatnia obserwacja:** {recent_obs}\n\n"
                            "Spróbuj fundamentalnie innego podejścia lub podaj więcej kontekstu."
                        )

                    if sig_count < loop_threshold:
                        self._log(f"⚠️ Action Loop detected! Intervention for '{action}' ({sig_count}/{loop_threshold}, total {total_loop_warnings}).")
                        observation = (
                            "SYSTEM INTERVENTION: You are repeating the same (or highly similar) tool action. "
                            "STOP repeating it. Do NOT call the same tool with similar input again. "
                            "Change strategy now (e.g., move to the next file/task, or validate results with list_directory/view_file/run_terminal). "
                            "If you are reading a long document, ENSURE YOU ARE INCREMENTING 'para_start' OR 'start_line' to progress."
                        )
                        observation_history.append(observation)
                        obs_text = f"\nObservation: {observation}\nThought:"
                        prompt += obs_text
                        self.active_scratchpad += obs_text
                        continue

                    # Per-signature threshold exceeded — stop with rich context.
                    self._log(f"⚠️ Action Loop: signature '{action}' exceeded threshold. Stopping.")
                    recent_actions = ", ".join(f"{a[0]}({str(a[1])[:30]})" for a in action_history[-5:])
                    recent_obs = observation_history[-1][:200] if observation_history else "(none)"
                    return (
                        f"Agent zatrzymany: pętla akcji '{action}' (próba {sig_count} po {loop_threshold} interwencjach).\n\n"
                        f"**Ostatnie akcje:** {recent_actions}\n"
                        f"**Ostatnia obserwacja:** {recent_obs}\n\n"
                        "Wypróbuj inne narzędzie lub inne argumenty."
                    )
                
                action_history.append(current_action)

                # Execute Tool
                if action in self.tool_map:
                    self._log(f"Executing Tool: {action} (Step {i+1}/{max_steps})")
                    tool = self.tool_map[action]
                    try:
                        # ----------------------------------------------------------------
                        # Preflight validation for common strict-schema tools.
                        # If required args are missing, do NOT call the tool (prevents
                        # repetitive Pydantic validation loops and forces strategy change).
                        # ----------------------------------------------------------------
                        if isinstance(tool_args, dict):
                            if action == "write_file":
                                missing = [k for k in ("file_path", "text") if k not in tool_args or tool_args.get(k) in (None, "")]
                                if missing:
                                    observation = (
                                        "Error: write_file requires a dict with BOTH keys: "
                                        "'file_path' and 'text'. "
                                        f"Missing/empty: {', '.join(missing)}. "
                                        "Fix your Action Input JSON. If the content is large, "
                                        "write a small skeleton first, then use replace_file_content in small blocks."
                                    )
                                    self._log(f"Error: {observation}")
                                    observation_history.append(observation)
                                    obs_text = f"\nObservation: {observation}\nThought:"
                                    prompt += obs_text
                                    self.active_scratchpad += obs_text
                                    continue

                            if action in ("read_pdf", "read_docx", "read_xlsx"):
                                if "file_path" not in tool_args or not tool_args.get("file_path"):
                                    observation = (
                                        f"Error: {action} requires 'file_path'. "
                                        "Your Action Input was incomplete (the JSON was cut off). "
                                        "Provide a complete Action Input, e.g.: "
                                        f'{{"file_path": "AGRFORMET-D-24-01426_reviewer.pdf"}}'
                                    )
                                    self._log(f"Preflight: {action} called with empty file_path. Correcting.")
                                    observation_history.append(observation)
                                    obs_text = f"\nObservation: {observation}\nThought:"
                                    prompt += obs_text
                                    self.active_scratchpad += obs_text
                                    continue

                            if action == "replace_file_content":
                                missing = [
                                    k for k in ("file_path", "start_line", "end_line", "replacement_content")
                                    if k not in tool_args or tool_args.get(k) in (None, "")
                                ]
                                if missing:
                                    observation = (
                                        "Error: replace_file_content requires: "
                                        "'file_path', 'start_line', 'end_line', 'replacement_content'. "
                                        f"Missing/empty: {', '.join(missing)}. "
                                        "Fix your Action Input JSON and ensure line numbers are integers."
                                    )
                                    self._log(f"Error: {observation}")
                                    observation_history.append(observation)
                                    obs_text = f"\nObservation: {observation}\nThought:"
                                    prompt += obs_text
                                    self.active_scratchpad += obs_text
                                    continue

                        # ── Preflight: save_document content recovery ──────────
                        # When the LLM writes massive HTML with inner quotes,
                        # the JSON parser often truncates the content field.
                        # Detect the situation (file_path present, content missing)
                        # and attempt to recover content from the raw action_input.
                        if action == "save_document" and isinstance(tool_args, dict):
                            if "content" not in tool_args or not tool_args.get("content"):
                                # Try to extract content from the raw action_input string
                                content_match = re.search(
                                    r'"content"\s*:\s*"(.*)',
                                    str(action_input),
                                    re.DOTALL
                                )
                                if content_match:
                                    recovered = content_match.group(1)
                                    is_truncated_fallback = False
                                    # Strip trailing JSON artifacts
                                    rstripped = recovered.rstrip(' \n\r\t}')
                                    if rstripped.endswith('"'):
                                        recovered = rstripped[:-1]
                                    else:
                                        is_truncated_fallback = True
                                        recovered = rstripped
                                        
                                    if len(recovered) > 50:
                                        tool_args["content"] = recovered
                                        self._log(f"⚙️ Recovered 'content' field for save_document ({len(recovered)} chars).")
                                        if is_truncated_fallback:
                                            tool_args["_is_truncated"] = True
                                # If still missing, fall back to write_file
                                if "content" not in tool_args or not tool_args.get("content"):
                                    observation = (
                                        "Error: save_document requires 'content' field but it was missing or empty. "
                                        "This usually happens when the HTML content is very large and breaks JSON parsing. "
                                        "Use write_file instead: Action: write_file, Action Input: {\"file_path\": \"file.html\", \"text\": \"<your content>\"}"
                                    )
                                    self._log(f"Preflight: save_document missing content. Advising write_file fallback.")
                                    observation_history.append(observation)
                                    obs_text = f"\nObservation: {observation}\nThought:"
                                    prompt += obs_text
                                    self.active_scratchpad += obs_text
                                    continue

                        # ── Preflight: Truncation Guard for massive content ────────
                        if isinstance(tool_args, dict) and tool_args.pop("_is_truncated", False):
                            if action in ["write_file", "save_document"]:
                                observation = (
                                    "Error: Your output was truncated because it exceeded the maximum token limit. "
                                    "The file was NOT saved because the text is incomplete. "
                                    "You MUST write this file in smaller chunks. "
                                    "Either use 'replace_file_content' to write it block by block, or write a Python script to generate it."
                                )
                                self._log("Preflight: Blocked tool creation due to truncated content limit hit.")
                                observation_history.append(observation)
                                obs_text = f"\nObservation: {observation}\nThought:"
                                prompt += obs_text
                                self.active_scratchpad += obs_text
                                continue

                        observation = tool.run(tool_args) if hasattr(tool, "run") else tool(tool_args)
                        last_executed_tool = action
                        if pending_observation_prefix:
                            observation = pending_observation_prefix + str(observation)
                        
                        # Observation Loop / Stagnation check
                        if len(observation_history) > 0 and observation == observation_history[-1]:
                            self._log("⚠️ Stagnation detected (Repeated Observation).")
                            _stagnation_count = getattr(self, '_stagnation_count', 0) + 1
                            self._stagnation_count = _stagnation_count

                            if _stagnation_count >= 3:
                                self._log(f"⚠️ Stagnation HARD STOP after {_stagnation_count} identical observations.")
                                _recent_obs = str(observation)[:400]
                                return (
                                    f"Agent zatrzymany: {_stagnation_count} identycznych obserwacji z rzędu.\n\n"
                                    f"**Ostatnie narzędzie:** {last_executed_tool}\n"
                                    f"**Obserwacja:** {_recent_obs}\n\n"
                                    "Zmień podejście, użyj innego narzędzia lub podaj więcej kontekstu."
                                )

                            observation += (
                                f"\n\n[SYSTEM WARNING: Identyczna obserwacja — powtórzenie {_stagnation_count}/3. "
                                "OBOWIĄZKOWO użyj INNEGO narzędzia z INNYMI argumentami. "
                                f"Jeszcze {3 - _stagnation_count} powtórzenie(a) i agent zostanie zatrzymany.]"
                            )
                        else:
                            self._stagnation_count = 0  # reset on new (different) observation
                            # ── Dynamic Step Limit Bonus ──
                            # If we reaching this point, we didn't loop or error out early.
                            # This was a "productive" step for the context.
                            if match and not is_identical_loop and not is_similarity_loop:
                                bonus = 2
                                old_limit = max_steps
                                max_steps = min(600, max_steps + bonus)
                                if max_steps > old_limit:
                                    self._log(f"--- Progress detected (Action: {action}). Limit extended: {max_steps} steps. ---")
                        
                        observation_history.append(observation)
                    except Exception as e:
                        observation = f"Error executing {action}: {e}"
                else:
                    available_tools = ", ".join(self.tool_map.keys())
                    observation = f"Error: Tool '{action}' not found. Available tools: {available_tools}. Use only these names!"
                
                # --- Observation Size Guard ---
                # Prevent context-window saturation from large tool outputs.
                # Large models (GLM, DeepSeek, Qwen 397B) have deep context and can handle 60k chars.
                MAX_OBS_CHARS = 60_000 if is_large_model else 15_000
                observation_str = str(observation)
                if len(observation_str) > MAX_OBS_CHARS:
                    truncated = observation_str[:MAX_OBS_CHARS]
                    chars_omitted = len(observation_str) - MAX_OBS_CHARS
                    observation_str = (
                        truncated +
                        f"\n\n[SYSTEM NOTICE: Output truncated. {chars_omitted} characters omitted to protect context window. "
                        "If you need more of the content, call the tool again with a smaller range or write it to a file first.]"
                    )
                    self._log(f"⚠️ Observation truncated: {chars_omitted} chars removed (limit: {MAX_OBS_CHARS}).")
                
                self._log(f"Observation: {observation_str}")
                
                obs_text = f"\nObservation: {observation_str}\nThought:"
                yield obs_text
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
                    # First empty response: inject a recovery hint instead of failing immediately.
                    # This often happens right after a very large observation saturates the context.
                    if not hasattr(self, '_empty_response_count'):
                        self._empty_response_count = 0
                    self._empty_response_count += 1
                    
                    if self._empty_response_count == 1:
                        self._log("⚠️ Empty response detected. Injecting recovery prompt (1/1 tries).")
                        recovery_msg = (
                            "\nObservation: [SYSTEM RECOVERY] Your last response was completely empty. "
                            "This can happen after processing very large content. "
                            "Please continue with the next logical step: output a Thought, then an Action/Action Input or Final Answer.\nThought:"
                        )
                        prompt += recovery_msg
                        self.active_scratchpad += recovery_msg
                        continue
                    else:
                        self._empty_response_count = 0
                        last_action = action_history[-1] if action_history else ("(none)", "")
                        recent_obs = observation_history[-1][:200] if observation_history else "(brak)"
                        return (
                            "Agent zatrzymany: model zwrócił dwie puste odpowiedzi z rzędu.\n\n"
                            f"**Ostatnia akcja:** {last_action[0]}({str(last_action[1])[:60]})\n"
                            f"**Ostatnia obserwacja:** {recent_obs}\n\n"
                            "Serwer mógł mieć chwilową awarię lub kontekst jest zbyt duży. Spróbuj ponownie lub uprość zadanie."
                        )

                # ----------------------------------------------------------------
                # Format correction: the model produced a natural-language response
                # without the ReAct format markers.
                # SMART DETECTION: If the output looks like a completed task summary
                # or a question to the user, auto-promote it to Final Answer
                # immediately instead of wasting 3+ LLM calls on format correction.
                # ----------------------------------------------------------------
                clean_output = output.replace("Thought:", "").strip()
                
                if not hasattr(self, '_consecutive_format_errors'):
                    self._consecutive_format_errors = 0
                
                # --- Smart Completion Detection ---
                # Detect outputs that are clearly final answers missing the prefix.
                # These are characterized by: completion markers, structured summaries,
                # questions to the user, or substantial length with summary patterns.
                completion_markers = [
                    "✅", "wykonane", "gotowy", "gotowe", "gotowa", "przygotował",
                    "kompletne", "zakończon", "zrobion", "completed", "done",
                    "all tasks", "summary", "podsumowanie",
                    "jak uruchomić", "instrukcja", "skopiuj",
                ]
                question_markers = ["czy", "pytanie", "question", "should i", "decide",
                                    "czy chcesz", "czy mam", "chciałbyś", "wolisz"]
                
                output_lower = clean_output.lower()
                has_completion_markers = sum(1 for m in completion_markers if m in output_lower) >= 2
                is_question_end = clean_output.rstrip().endswith("?")
                has_question_markers = any(m in output_lower for m in question_markers)
                is_substantial = len(clean_output) > 200
                has_list_structure = clean_output.count("- ") >= 3 or clean_output.count("✅") >= 2
                
                looks_like_final_answer = (
                    (has_completion_markers and is_substantial) or
                    (has_completion_markers and has_list_structure) or
                    (is_question_end and has_question_markers and is_substantial) or
                    (is_question_end and has_completion_markers)
                )
                
                if looks_like_final_answer:
                    self._log(f"🎯 Auto-promoting to Final Answer (completion detected: "
                              f"markers={has_completion_markers}, question={is_question_end}, "
                              f"len={len(clean_output)}). Saved ~3 LLM calls.")
                    self._consecutive_format_errors = 0
                    
                    # Context preservation: keep scratchpad if it's a question
                    if is_question_end or has_question_markers:
                        self._log("Context Preserved: Output ends with question to user.")
                    else:
                        self.active_scratchpad = ""
                    
                    self._write_status_file("✅ Completed", f"{clean_output[:300]}")
                    return clean_output
                
                # --- Standard format error path (for genuinely incomplete outputs) ---
                self._consecutive_format_errors += 1
                
                if self._consecutive_format_errors >= 3:
                    self._log("⚠️ Model ignored format rules repeatedly. Forwarding its raw thought to the user as a Final Answer.")
                    self._consecutive_format_errors = 0
                    
                    if is_question_end or has_question_markers:
                        self._log("Context Preserved: Raw output implies a question.")
                    else:
                        self.active_scratchpad = ""
                    return clean_output
                
                self._log(f"⚠️ Format error ({self._consecutive_format_errors}/3). Prompting for correction.")
                self._log(f"--- RAW OUTPUT CAUSING ERROR ---\n{output}\n--------------------------------")
                fmt_error = (
                    "\nObservation: SYSTEM: You did not produce an Action or Final Answer. You MUST use one of these formats:\n\n"
                    "FORMAT A (to use a tool):\n"
                    "Thought: I need to do X.\n"
                    "Action: tool_name\n"
                    "Action Input: {\"key\": \"value\"}\n\n"
                    "FORMAT B (to respond to the user):\n"
                    "Final Answer: [your complete response]\n\n"
                    "If your task is DONE, use Format B now. Otherwise use Format A:\n"
                    "Thought:"
                )
                prompt += fmt_error
                self.active_scratchpad += fmt_error

            i += 1

        safety_msg = f"Agent reached safety limit of {max_steps} steps without finishing. To prevent excessive API usage, I have stopped here. You can ask me to 'continue' if you believe more progress can be made."
        self._write_status_file("⚠️ Stopped", f"Safety limit of {max_steps} steps reached.")
        return safety_msg
