"""
ConsiliumOrchestrator — Advanced Multi-Agent Debate and Consensus System.

Implements a highly collaborative Multi-Agent pattern where:
1. Executor performs the task inside the workspace.
2. Reviewer inspects the workspace, verifies findings, and writes `.consilium_review.md`.
3. Skeptic stress-tests assumptions, proposes alternatives, and writes `.consilium_skeptic.md`.
4. Workspace is checkpointed at every step using CheckpointManager for safe rollbacks.
5. The next revision automatically loads the previous outputs and selectively targets fixes.
"""
from __future__ import annotations

import os
import re
import json
import datetime
from typing import List, Optional, Set

from omni_agent.core.agent_engine import LangChainAgentEngine
from omni_agent.core.llm_profile_loader import load_llm_profile
from omni_agent.core.checkpoint_manager import CheckpointManager

# ── Default Team ──────────────────────────────────────────────────────────
DEFAULT_CONSILIUM_TEAM = {
    "executor": "Qwen3.5-397B-A17B",
    "reviewer": "DeepSeek-V3.1-vLLM",
    "skeptic":  "GLM-4.7",
}

# ── Read-only tools for Reviewer/Skeptic ──────────────────────────────────
READONLY_TOOLS: Set[str] = {
    "view_file", "list_directory", "search_files",
    "count_pattern_in_file", "read_docx", "read_pdf",
    "read_xlsx", "analyze_image",
}

# ── Prompt Templates ──────────────────────────────────────────────────────

REVIEW_PROMPT_TEMPLATE = """You are a CRITICAL REVIEWER in a multi-agent consilium.
Another AI model (the Executor, running {executor_model}) has performed the following task inside the workspace.

## ORIGINAL USER TASK
{original_task}

## EXECUTOR'S FINAL ANSWER
{executor_output}

## YOUR REVIEW INSTRUCTIONS
1. VERIFY ACCURACY: Check facts, logic, and calculations in the Executor's work.
2. ASSESS COMPLETENESS: Did the Executor address ALL aspects of the user's request?
3. FIND ERRORS: Identify logical errors, bugs, inconsistencies, or missed edge cases.
4. SUGGEST IMPROVEMENTS: Provide concrete, actionable suggestions (not vague advice).

Use your tools (view_file, list_directory, search_files) to inspect the workspace files and VERIFY the claims/changes the Executor made.
Do NOT modify files — only evaluate what was done.

At the end of your analysis, summarize your review and write a brief final comment.
Your response MUST end with exactly one of these lines:
- VERDICT: APPROVE — if the work is satisfactory and fully correct.
- VERDICT: REVISE — if issues exist (list the specific errors/omissions to fix).
"""

SKEPTIC_PROMPT_TEMPLATE = """You are the SKEPTIC (Devil's Advocate) in a multi-agent consilium.
You have seen both the Executor's work AND the Reviewer's evaluation.

## ORIGINAL USER TASK
{original_task}

## EXECUTOR'S FINAL ANSWER
{executor_output}

## REVIEWER'S EVALUATION
{review_output}

## YOUR SKEPTIC INSTRUCTIONS
1. CHALLENGE ASSUMPTIONS: What did BOTH the Executor and Reviewer take for granted?
2. FIND BLIND SPOTS: What perspectives, scenarios, or requirements were ignored?
3. STRESS TEST: Would this solution break under edge cases or unusual inputs?
4. ALTERNATIVE APPROACHES: Is there a fundamentally better approach they missed?

Be constructively critical. Your goal is NOT to reject everything, but to 
strengthen the final result by exposing weaknesses early.

At the end of your analysis, summarize your challenges and write a brief final comment.
Your response MUST end with exactly one of:
- VERDICT: APPROVE — if you agree the work is solid.
- VERDICT: REVISE — if critical issues or assumptions remain unaddressed.
"""

REVISION_PROMPT_TEMPLATE = """You previously worked on this task and produced a result.
Your work has been audited and analyzed by two independent AI agents: the Reviewer and the Skeptic.

The full review reports have been generated and saved directly in your workspace:
- Reviewer Report: `.consilium_review.md`
- Skeptic Report: `.consilium_skeptic.md`

Please inspect these files in your workspace using `view_file` to see the complete evaluation.

## ORIGINAL TASK
{original_task}

## YOUR PREVIOUS ANSWER
{executor_output}

## BRIEF SUMMARY OF REVIEWER FEEDBACK
{review_summary}

## BRIEF SUMMARY OF SKEPTIC FEEDBACK
{skeptic_summary}

## REVISION INSTRUCTIONS
1. Use `view_file` to read `.consilium_review.md` and `.consilium_skeptic.md` inside your workspace.
2. Fix all errors, bugs, or missing requirements identified by the Reviewer.
3. Address the challenged assumptions and alternative solutions highlighted by the Skeptic.
4. Execute the required code/file modifications in the workspace to fix these issues.
5. Produce an improved, fully complete, and correct final answer.
"""


class ConsiliumOrchestrator:
    """
    Manages multi-LLM collaboration for a single task using the Debate and Consensus patterns.
    
    Creates three LangChainAgentEngine instances:
    - Executor: full toolset, performs/modifies the task
    - Reviewer: read-only tools, evaluates the Executor's work
    - Skeptic: read-only tools, challenges assumptions
    
    Uses CheckpointManager for robust workspace rollback.
    Uses workspace files (.consilium_review.md, .consilium_skeptic.md) for context preservation.
    """
    
    def __init__(
        self,
        api_key: str,
        workspace_path: str,
        executor_model: str = None,
        reviewer_model: str = None,
        skeptic_model: str = None,
        max_rounds: int = 2,
        log_callback=None,
        executor_instructions: str = "",
        base_url: str = "https://llm.hpc.pcss.pl/v1"
    ):
        self.api_key = api_key
        self.workspace_path = workspace_path
        self.base_url = base_url
        self.max_rounds = max_rounds
        self._log_callback = log_callback
        self._is_cancelled = False
        
        # Initialize the CheckpointManager
        self.checkpoint_manager = CheckpointManager(workspace_path)
        
        # Resolve model names (use defaults if not provided)
        self.executor_model = executor_model or DEFAULT_CONSILIUM_TEAM["executor"]
        self.reviewer_model = reviewer_model or DEFAULT_CONSILIUM_TEAM["reviewer"]
        self.skeptic_model = skeptic_model or DEFAULT_CONSILIUM_TEAM["skeptic"]
        
        self._log(f"🏛️ Consilium initialized: Executor={self.executor_model}, "
                  f"Reviewer={self.reviewer_model}, Skeptic={self.skeptic_model}, "
                  f"Rounds={self.max_rounds} (Workspace: {self.workspace_path})")
        
        # Load LLM profiles for each model
        llm_profiles_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "llm_profiles")
        )
        
        # Load agent profile instructions for consilium roles
        agent_profiles_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "agent_profiles")
        )
        reviewer_instructions = self._load_agent_profile(agent_profiles_dir, "consilium_roles/consilium_reviewer.yaml")
        skeptic_instructions = self._load_agent_profile(agent_profiles_dir, "consilium_roles/consilium_skeptic.yaml")
        
        # === Create Executor Engine (full toolset) ===
        ex_llm_rules, ex_max_tokens, ex_sys_prompt, ex_ctx = load_llm_profile(
            self.executor_model, llm_profiles_dir
        )
        self.executor = LangChainAgentEngine(
            api_key=api_key,
            model_name=self.executor_model,
            workspace_path=workspace_path,
            log_callback=self._make_prefixed_callback("[EXECUTOR]"),
            custom_instructions=executor_instructions,
            llm_instructions=ex_llm_rules,
            max_tokens=ex_max_tokens,
            system_prompt_additions=ex_sys_prompt,
            context_window=ex_ctx,
            base_url=self.base_url,
        )
        
        # === Create Reviewer Engine (read-only tools) ===
        rv_llm_rules, rv_max_tokens, rv_sys_prompt, rv_ctx = load_llm_profile(
            self.reviewer_model, llm_profiles_dir
        )
        self.reviewer = LangChainAgentEngine(
            api_key=api_key,
            model_name=self.reviewer_model,
            workspace_path=workspace_path,
            log_callback=self._make_prefixed_callback("[REVIEWER]"),
            custom_instructions=reviewer_instructions,
            llm_instructions=rv_llm_rules,
            max_tokens=rv_max_tokens,
            system_prompt_additions=rv_sys_prompt,
            context_window=rv_ctx,
            tool_filter=READONLY_TOOLS,
            base_url=self.base_url,
        )
        
        # === Create Skeptic Engine (read-only tools) ===
        sk_llm_rules, sk_max_tokens, sk_sys_prompt, sk_ctx = load_llm_profile(
            self.skeptic_model, llm_profiles_dir
        )
        self.skeptic = LangChainAgentEngine(
            api_key=api_key,
            model_name=self.skeptic_model,
            workspace_path=workspace_path,
            log_callback=self._make_prefixed_callback("[SKEPTIC]"),
            custom_instructions=skeptic_instructions,
            llm_instructions=sk_llm_rules,
            max_tokens=sk_max_tokens,
            system_prompt_additions=sk_sys_prompt,
            context_window=sk_ctx,
            tool_filter=READONLY_TOOLS,
            base_url=self.base_url,
        )
    
    # ── Public API ────────────────────────────────────────────────────────
    
    def run(self, task: str, chat_history: List = None):
        """
        Execute the consilium workflow. Generator that yields streamed chunks.
        
        If the chat_history indicates this is follow-up feedback on a previous result,
        runs a lightweight refinement path (Executor only) instead of the full debate cycle.
        
        Returns the final executor result via StopIteration.value.
        """
        if chat_history is None:
            chat_history = []
        
        # Get original task from history if available
        original_task = chat_history[0].content if chat_history else task
        
        # Construct unified task if this is follow-up
        is_followup = self._is_followup_feedback(task, chat_history)
        
        # Check for simple acknowledgment/filler messages
        is_filler = False
        if is_followup:
            task_clean = task.lower().strip().strip('.').strip('!').strip()
            # If it's a short message or just a friendly filler/acknowledgement
            filler_words = {"dzięki", "dzieki", "super", "ok", "okay", "yes", "tak", "nie", "no",
                            "dziękuje", "dziękuję", "thanks", "thank you", "gotowe", "clear"}
            if len(task_clean) < 15 or task_clean in filler_words or any(w == task_clean for w in filler_words):
                is_filler = True
        
        # ── Follow-up Filler / Simple Refinement Path ───────────────────
        if is_followup and is_filler:
            self._log("💬 Consilium: Simple follow-up/filler detected. Running executor directly.")
            yield "\n\n---\n**🏛️ CONSILIUM — Tryb Poprawki (Refinement)**\n\n"
            yield f"**[EXECUTOR: {self.executor_model}]** odpowiada...\n\n"
            
            # Run only the Executor with full chat_history (contains the previous result context)
            executor_result = yield from self._run_engine(self.executor, task, chat_history)
            
            yield "\n\n**🏛️ CONSILIUM: ✅ Gotowe.**\n"
            self._log("✅ Consilium simple refinement completed.")
            return executor_result
        
        executor_result = ""
        last_checkpoint_id = None
        
        # Define unified task to keep Reviewer and Skeptic aligned on history
        if is_followup:
            unified_task = (
                f"Original Task: {original_task}\n"
                f"Follow-up Instructions / Feedback: {task}"
            )
        else:
            unified_task = task
        
        for round_num in range(1, self.max_rounds + 1):
            if self._is_cancelled:
                return "Consilium cancelled."
            
            self._log(f"\n{'='*60}")
            self._log(f"🏛️ CONSILIUM ROUND {round_num}/{self.max_rounds}")
            self._log(f"{'='*60}\n")
            
            # Create a checkpoint before Executor starts modifying files
            checkpoint_label = f"consilium_round_{round_num}_pre_executor"
            try:
                last_checkpoint_id = self.checkpoint_manager.create(checkpoint_label)
                self._log(f"🔖 Workspace checkpoint created: {last_checkpoint_id}")
            except Exception as ce:
                self._log(f"⚠️ Failed to create checkpoint: {ce}")
            
            # ── Phase 1: Executor ──
            self._log(f"📝 Phase 1: Executor ({self.executor_model}) working...")
            yield "\n\n---\n**🏛️ CONSILIUM** — "
            yield f"Runda {round_num}/{self.max_rounds}\n\n"
            yield f"**[EXECUTOR: {self.executor_model}]** pracuje...\n\n"
            
            executor_result = yield from self._run_engine(self.executor, task, chat_history)
            
            if self._is_cancelled:
                return executor_result
            
            # ── Phase 2: Reviewer ──
            self._log(f"🔍 Phase 2: Reviewer ({self.reviewer_model}) evaluating...")
            yield f"\n\n**[REVIEWER: {self.reviewer_model}]** ocenia pracę Executora...\n\n"
            
            review_prompt = REVIEW_PROMPT_TEMPLATE.format(
                executor_model=self.executor_model,
                original_task=unified_task,
                executor_output=executor_result,
            )
            review_result = yield from self._run_engine(self.reviewer, review_prompt, [])
            
            if self._is_cancelled:
                return executor_result
            
            # Save Reviewer's report directly to the workspace for the Executor's future reference
            self._write_workspace_file(".consilium_review.md", review_result)
            self._log("📄 Saved reviewer report to `.consilium_review.md` in workspace.")
            
            # ── Phase 3: Skeptic ──
            self._log(f"🤔 Phase 3: Skeptic ({self.skeptic_model}) challenging...")
            yield f"\n\n**[SKEPTIC: {self.skeptic_model}]** szuka luk...\n\n"
            
            skeptic_prompt = SKEPTIC_PROMPT_TEMPLATE.format(
                original_task=unified_task,
                executor_output=executor_result,
                review_output=review_result,
            )
            skeptic_result = yield from self._run_engine(self.skeptic, skeptic_prompt, [])
            
            if self._is_cancelled:
                return executor_result
            
            # Save Skeptic's report directly to the workspace for the Executor's future reference
            self._write_workspace_file(".consilium_skeptic.md", skeptic_result)
            self._log("📄 Saved skeptic report to `.consilium_skeptic.md` in workspace.")
            
            # ── Phase 4: Consensus & Verdict Checking ──
            verdict = self._parse_verdict(review_result, skeptic_result)
            self._log(f"⚖️ Consilium verdict: {verdict}")
            
            if verdict == "APPROVE":
                yield f"\n\n**🏛️ CONSILIUM VERDICT: ✅ APPROVE** — Runda {round_num}\n"
                self._log(f"✅ Consilium approved the result in round {round_num}.")
                
                # Cleanup workspace communication files on approval to keep workspace tidy
                self._delete_workspace_file(".consilium_review.md")
                self._delete_workspace_file(".consilium_skeptic.md")
                break
            
            if round_num < self.max_rounds:
                yield f"\n\n**🏛️ CONSILIUM VERDICT: 🔄 REVISE** — Rozpoczynam rundę {round_num + 1}\n"
                self._log(f"🔄 Revision requested. Starting round {round_num + 1}.")
                
                # Build concise feedback summaries to pass inside the prompt
                review_summary = self._make_brief_summary(review_result)
                skeptic_summary = self._make_brief_summary(skeptic_result)
                
                # Build revision prompt for next round pointing to workspace report files
                task = REVISION_PROMPT_TEMPLATE.format(
                    original_task=unified_task,
                    executor_output=executor_result,
                    review_summary=review_summary,
                    skeptic_summary=skeptic_summary,
                )
            else:
                yield f"\n\n**🏛️ CONSILIUM: Max rounds reached** — Zwracam ostatni wynik Executora.\n"
                self._log(f"⚠️ Max rounds ({self.max_rounds}) reached. Returning last result.")
                
                # Keep reports in workspace in case user needs to debug maximum rounds failure
        
        return executor_result
    
    def cancel(self):
        """Cancel all engines."""
        self._is_cancelled = True
        if hasattr(self.executor, 'cancel'):
            self.executor.cancel()
        if hasattr(self.reviewer, 'cancel'):
            self.reviewer.cancel()
        if hasattr(self.skeptic, 'cancel'):
            self.skeptic.cancel()
    
    # ── Private helpers ───────────────────────────────────────────────────
    
    def _is_followup_feedback(self, task: str, chat_history: List) -> bool:
        """
        Detect whether the user's message is follow-up feedback on a previous result
        rather than a genuinely new task.
        
        Heuristic: if chat_history contains at least one Q/A pair AND the current
        message doesn't start with a "new task" marker, treat it as feedback.
        """
        if len(chat_history) < 2:
            return False
        
        # Check if there's at least one AI answer in history
        from langchain_core.messages import AIMessage
        has_ai_answer = any(isinstance(msg, AIMessage) for msg in chat_history)
        if not has_ai_answer:
            return False
        
        # Check for explicit "new task" markers
        new_task_markers = [
            "zrób nowy", "nowe zadanie", "new task", "start fresh", "nowy projekt", "fresh start"
        ]
        task_lower = task.lower().strip()
        looks_like_new_task = any(task_lower.startswith(m) for m in new_task_markers)
        
        if looks_like_new_task:
            return False
        
        self._log(f"💬 Follow-up detection: chat_history has {len(chat_history)} messages, "
                  f"task doesn't match new-task markers → treating as feedback.")
        return True
    
    def _run_engine(self, engine: LangChainAgentEngine, task: str, chat_history: List):
        """
        Run a single engine and yield its streamed chunks.
        Returns the final answer via generator return.
        """
        import time
        max_retries = 2
        for attempt in range(max_retries):
            try:
                gen = engine.run(task, chat_history)
                final_result = ""
                
                if hasattr(gen, '__next__'):
                    while True:
                        try:
                            chunk = next(gen)
                            if self._is_cancelled:
                                return final_result
                            if chunk:
                                yield chunk
                        except StopIteration as e:
                            if e.value is not None:
                                final_result = e.value
                            break
                else:
                    # Fallback if run() returns a plain string
                    final_result = gen
                
                return final_result
                
            except Exception as e:
                err_msg = str(e)
                self._log(f"⚠️ Exception in {engine.model_name}: {err_msg}")
                if "500" in err_msg or "InternalServerError" in err_msg or "Connection error" in err_msg:
                    if attempt < max_retries - 1:
                        self._log(f"🔄 Retrying {engine.model_name} in 3 seconds... (Attempt {attempt + 2}/{max_retries})")
                        yield f"\n\n**[SYSTEM]** Serwer zwrócił błąd dla modelu {engine.model_name}. Ponawiam próbę (za 3 sekundy)...\n\n"
                        time.sleep(3)
                        continue
                
                # If we exhausted retries or it's not a generic retryable error, log it and return it
                yield f"\n\n**[ERROR]** Krytyczny błąd połączenia z modelem {engine.model_name}: {err_msg}\n\n"
                return f"[Internal Error in {engine.model_name}]"
    
    def _parse_verdict(self, review: str, critique: str) -> str:
        """
        Parse VERDICT using semantic analyses and negative-sentiment weight checking.
        """
        review_lower = (review or "").lower()
        critique_lower = (critique or "").lower()
        
        # 1. Look for explicit VERDICT matches
        if "verdict: revise" in review_lower or "verdict: revise" in critique_lower:
            return "REVISE"
        if "verdict: reject" in review_lower or "verdict: reject" in critique_lower:
            return "REVISE"
            
        # 2. Look for semantic negative signals that bypass standard positive formats
        critical_keywords = [
            "must fix", "critical issue", "syntax error", "failed", 
            "does not work", "incorrectly", "flaw", "broken", 
            "correction is needed", "bug", "missing aspect"
        ]
        
        reasons_to_revise = 0
        for kw in critical_keywords:
            if kw in review_lower:
                reasons_to_revise += 1
            if kw in critique_lower:
                reasons_to_revise += 1
                
        if reasons_to_revise >= 2:
            self._log(f"⚠️ Detected multiple critical issues semantically: Revise requested ({reasons_to_revise} matches)")
            return "REVISE"
            
        # 3. Explicit Approve Check
        if "verdict: approve" in review_lower and "verdict: approve" in critique_lower:
            return "APPROVE"
            
        # Default safety: if any is uncertain or has minor comments, it's safer to request one revision
        if "verdict: approve" in review_lower or "verdict: approve" in critique_lower:
             # If one approves and one hasn't explicitly rejected, we can approve
             if "revise" not in review_lower and "revise" not in critique_lower:
                 return "APPROVE"
                 
        return "REVISE"
    
    def _make_brief_summary(self, text: str) -> str:
        """Extract a short, high-density summary from the agent feedback."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        summary_lines = []
        for line in lines:
            if line.startswith("-") or line.startswith("*") or line.startswith("1.") or line.startswith("2.") or line.startswith("3."):
                summary_lines.append(line)
            if len(summary_lines) >= 8:
                break
        if not summary_lines:
            # Fallback to the first 4 lines if no list items found
            summary_lines = lines[:4]
        return "\n".join(summary_lines)

    def _write_workspace_file(self, filename: str, content: str):
        """Write a helper communication file directly to the workspace."""
        path = os.path.join(self.workspace_path, filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            self._log(f"Warning: Failed to write {filename}: {e}")

    def _delete_workspace_file(self, filename: str):
        """Delete helper communication file from workspace."""
        path = os.path.join(self.workspace_path, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                self._log(f"Warning: Failed to delete {filename}: {e}")
    
    def _load_agent_profile(self, profiles_dir: str, filename: str) -> str:
        """Load instructions from a consilium agent profile YAML."""
        path = os.path.join(profiles_dir, filename)
        if not os.path.exists(path):
            self._log(f"Warning: Consilium profile not found: {path}")
            return ""
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return data.get("instructions", "") if isinstance(data, dict) else ""
        except Exception as e:
            self._log(f"Warning: Failed to load consilium profile {filename}: {e}")
            return ""
    
    def _make_prefixed_callback(self, prefix: str):
        """Create a log callback that prefixes all messages."""
        def callback(msg: str):
            if self._log_callback:
                self._log_callback(f"{prefix} {msg}")
        return callback
    
    def _log(self, message: str):
        """Log a message through the callback and to the file log."""
        prefix_msg = f"[CONSILIUM] {message}"
        if self._log_callback:
            self._log_callback(prefix_msg)
        try:
            app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            log_path = os.path.join(app_dir, "agent_debug.log")
            if os.path.exists(log_path) and os.path.getsize(log_path) > 5 * 1024 * 1024:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(f"[LOG ROTATED at {datetime.datetime.now().isoformat()}]\n")
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}]{prefix_msg}\n")
        except Exception:
            pass
