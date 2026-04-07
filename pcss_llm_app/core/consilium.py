"""
ConsiliumOrchestrator — Multi-LLM Debate System.

Implements a Debate pattern where an Executor model performs the task
and Reviewer/Skeptic models provide critical feedback to improve results.

Usage:
    orchestrator = ConsiliumOrchestrator(api_key, workspace, ...)
    for chunk in orchestrator.run("task description"):
        print(chunk)  # yields streamed text from all models
"""
from __future__ import annotations

import os
from typing import List, Optional, Set

from pcss_llm_app.core.agent_engine import LangChainAgentEngine
from pcss_llm_app.core.llm_profile_loader import load_llm_profile

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
Another AI model (the Executor, running {executor_model}) has performed the following task.

## ORIGINAL USER TASK
{original_task}

## EXECUTOR'S FINAL ANSWER
{executor_output}

## YOUR REVIEW INSTRUCTIONS
1. VERIFY ACCURACY: Check facts, logic, and calculations in the Executor's work.
2. ASSESS COMPLETENESS: Did the Executor address ALL aspects of the user's request?
3. FIND ERRORS: Logical errors, bugs, inconsistencies, or missed edge cases.
4. SUGGEST IMPROVEMENTS: Concrete, actionable suggestions (not vague advice).

Use your tools (view_file, list_directory, search_files) to VERIFY claims the Executor made.
Do NOT re-do the task — only evaluate what was done.

Your review MUST end with exactly one of these lines:
- VERDICT: APPROVE — if the work is satisfactory
- VERDICT: REVISE — if significant issues need fixing (list specific issues)
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

End with exactly one of:
- VERDICT: APPROVE — if you agree the work is solid
- VERDICT: REVISE — if critical issues remain (list them)
"""

REVISION_PROMPT_TEMPLATE = """You previously worked on this task and produced a result.
Your work was reviewed by two independent AI models. Please address their feedback.

## ORIGINAL TASK
{original_task}

## YOUR PREVIOUS ANSWER
{executor_output}

## REVIEWER FEEDBACK
{review_output}

## SKEPTIC FEEDBACK
{skeptic_output}

## REVISION INSTRUCTIONS
Address the specific issues raised above. Focus on:
1. Fix any errors or bugs identified
2. Add missing elements pointed out by reviewers
3. Strengthen weak areas highlighted by the Skeptic

Produce an improved, complete answer.
"""


class ConsiliumOrchestrator:
    """
    Manages multi-LLM collaboration for a single task using the Debate pattern.
    
    Creates three LangChainAgentEngine instances:
    - Executor: full toolset, performs the task
    - Reviewer: read-only tools, evaluates the Executor's work
    - Skeptic: read-only tools, challenges assumptions
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
        
        # Resolve model names (use defaults if not provided)
        self.executor_model = executor_model or DEFAULT_CONSILIUM_TEAM["executor"]
        self.reviewer_model = reviewer_model or DEFAULT_CONSILIUM_TEAM["reviewer"]
        self.skeptic_model = skeptic_model or DEFAULT_CONSILIUM_TEAM["skeptic"]
        
        self._log(f"🏛️ Consilium initialized: Executor={self.executor_model}, "
                  f"Reviewer={self.reviewer_model}, Skeptic={self.skeptic_model}, "
                  f"Rounds={self.max_rounds}")
        
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
        
        Returns the final executor result via StopIteration.value.
        """
        if chat_history is None:
            chat_history = []
        
        executor_result = ""
        
        for round_num in range(1, self.max_rounds + 1):
            if self._is_cancelled:
                return "Consilium cancelled."
            
            self._log(f"\n{'='*60}")
            self._log(f"🏛️ CONSILIUM ROUND {round_num}/{self.max_rounds}")
            self._log(f"{'='*60}\n")
            
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
                original_task=task,
                executor_output=executor_result,
            )
            review_result = yield from self._run_engine(self.reviewer, review_prompt, [])
            
            if self._is_cancelled:
                return executor_result
            
            # ── Phase 3: Skeptic ──
            self._log(f"🤔 Phase 3: Skeptic ({self.skeptic_model}) challenging...")
            yield f"\n\n**[SKEPTIC: {self.skeptic_model}]** szuka luk...\n\n"
            
            skeptic_prompt = SKEPTIC_PROMPT_TEMPLATE.format(
                original_task=task,
                executor_output=executor_result,
                review_output=review_result,
            )
            skeptic_result = yield from self._run_engine(self.skeptic, skeptic_prompt, [])
            
            if self._is_cancelled:
                return executor_result
            
            # ── Phase 4: Check verdict ──
            verdict = self._parse_verdict(review_result, skeptic_result)
            self._log(f"⚖️ Consilium verdict: {verdict}")
            
            if verdict == "APPROVE":
                yield f"\n\n**🏛️ CONSILIUM VERDICT: ✅ APPROVE** — Runda {round_num}\n"
                self._log(f"✅ Consilium approved the result in round {round_num}.")
                break
            
            if round_num < self.max_rounds:
                yield f"\n\n**🏛️ CONSILIUM VERDICT: 🔄 REVISE** — Rozpoczynam rundę {round_num + 1}\n"
                self._log(f"🔄 Revision requested. Starting round {round_num + 1}.")
                
                # Build revision prompt for next round
                task = REVISION_PROMPT_TEMPLATE.format(
                    original_task=task,
                    executor_output=executor_result,
                    review_output=review_result,
                    skeptic_output=skeptic_result,
                )
            else:
                yield f"\n\n**🏛️ CONSILIUM: Max rounds reached** — Zwracam ostatni wynik Executora.\n"
                self._log(f"⚠️ Max rounds ({self.max_rounds}) reached. Returning last result.")
        
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
        Parse VERDICT from reviewer and skeptic outputs.
        If either says REVISE, the overall verdict is REVISE.
        """
        review_lower = (review or "").lower()
        critique_lower = (critique or "").lower()
        
        if "verdict: revise" in review_lower or "verdict: revise" in critique_lower:
            return "REVISE"
        return "APPROVE"
    
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
        """Log a message through the callback."""
        if self._log_callback:
            self._log_callback(f"[CONSILIUM] {message}")
