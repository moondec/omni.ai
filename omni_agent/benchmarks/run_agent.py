#!/usr/bin/env python3
"""
PCSS LLM Agent Benchmark
Tests agent capabilities: tool selection, schema understanding, and complex workflows.
"""

import sys
import os
import json
import time
import argparse
import tempfile
import shutil
from typing import Dict, List, Any

# Local imports
from omni_agent.config import ConfigManager
from omni_agent.core.api_client import OmniApiClient
from omni_agent.core.agent_engine import LangChainAgentEngine
from omni_agent.benchmarks.tasks import AGENT_TASKS
from omni_agent.benchmarks import reporter

# To extract schemas from real tools
from langchain_core.utils.function_calling import convert_to_openai_function
from omni_agent.core.tools import (
    DocumentTools, WebSearchTools, SearchTools, 
    TerminalTool, ViewFileTool, ChartTools, PythonREPL, CountPatternTool
)

class MockAgentBenchmarkRunner:
    """Runs agent tasks using native OpenAI function calling with mocked execution."""
    def __init__(self, api_client: OmniApiClient, config: ConfigManager):
        self.api_client = api_client
        self.config = config
        self.schemas = self._generate_real_tool_schemas()
        
    def _generate_real_tool_schemas(self):
        """Extract OpenAI functions from actual app tools and wrap them for the PCSS API."""
        # Instantiate tools with dummy paths just for schema extraction
        tools = []
        tools.extend(DocumentTools(root_dir=".").get_tools())
        tools.extend(WebSearchTools().get_tools())
        tools.extend(SearchTools(root_dir=".").get_tools())
        tools.extend(TerminalTool(root_dir=".").get_tools())
        tools.extend(ViewFileTool(root_dir=".").get_tools())
        tools.extend(ChartTools(root_dir=".").get_tools())
        tools.extend(PythonREPL(root_dir=".").get_tools())
        tools.extend(ChartTools(root_dir=".").get_tools()) # Added missing tools if any or just re-ensure
        tools.extend(CountPatternTool(root_dir=".").get_tools())
        
        # PCSS (via litellm/vLLM) requires the "type": "function" wrapper
        schemas = [{"type": "function", "function": convert_to_openai_function(t)} for t in tools]
        return schemas
        
    def evaluate_task(self, model: str, task) -> dict:
        start_time = time.time()
        
        sys_prompt = "You are an AI assistant. Use the available tools to complete the user's task."
        
        # We test native function calling capability
        try:
            try:
                # First attempt: standard OpenAI tools format
                response = self.api_client.chat_completion(
                    model=model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": task.prompt}
                    ],
                    tools=self.schemas,
                    tool_choice="auto",
                    max_tokens=1024,
                    temperature=0.1
                )
            except Exception as first_err:
                # Fallback for models that might struggle with 'tools' but support 'functions'
                if "tools" in str(first_err) or "400" in str(first_err):
                    try:
                        unwrapped_schemas = [s["function"] for s in self.schemas]
                        response = self.api_client.chat_completion(
                            model=model,
                            messages=[
                                {"role": "system", "content": sys_prompt},
                                {"role": "user", "content": task.prompt}
                            ],
                            functions=unwrapped_schemas,
                            max_tokens=1024,
                            temperature=0.1
                        )
                    except Exception as second_err:
                        raise Exception(f"First attempt (tools) failed: {str(first_err)}. Fallback (functions) failed: {str(second_err)}")
                else:
                    raise first_err

            duration_ms = (time.time() - start_time) * 1000
            
            message = response.choices[0].message
            usage = response.usage
            
            tool_calls = message.tool_calls or []
            called_tools = [tc.function.name for tc in tool_calls]
            
            # Simple scoring
            tool_accuracy = 1.0 if any(expected in called_tools for expected in task.expected_tools) else 0.0
            call_accuracy = 1.0 if len(tool_calls) == task.expected_count else 0.0
            
            success = tool_accuracy > 0.0
            
            return {
                "task_id": task.id,
                "category": task.category,
                "success": success,
                "tool_accuracy": tool_accuracy,
                "call_accuracy": call_accuracy,
                "duration_ms": duration_ms,
                "tokens": usage.total_tokens,
                "called_tools": called_tools,
                "expected": task.expected_tools
            }
        except Exception as e:
            return {
                "task_id": task.id,
                "category": task.category,
                "success": False,
                "tool_accuracy": 0.0,
                "call_accuracy": 0.0,
                "error": str(e)
            }


class RealAgentBenchmarkRunner:
    """Runs agent using the actual LangChainAgentEngine on a sandboxed directory."""
    def __init__(self, api_client: OmniApiClient, config: ConfigManager):
        self.api_client = api_client
        self.config = config
        
    def evaluate_task(self, model: str, task) -> dict:
        # Create temp workspace
        temp_dir = tempfile.mkdtemp(prefix="pcss_bench_")
        start_time = time.time()
        
        try:
            engine = LangChainAgentEngine(
                api_key=self.config.get_api_key(),
                model_name=model,
                workspace_path=temp_dir,
                max_tokens=4096,
                context_window=32768
            )
            
            # Run the task through the actual ReAct loop
            final_answer_chunks = []
            for chunk in engine.run(task.prompt):
                final_answer_chunks.append(chunk)
            final_answer = "".join(final_answer_chunks)
            duration_ms = (time.time() - start_time) * 1000
            
            # Since we can't easily parse tool calls from the raw engine output without deep hooking,
            # we consider it a success if the engine didn't crash and returned an answer.
            # In a real rigorous test, we would write assertion functions per task (e.g., check if file exists)
            
            file_created = False
            # Verification:
            # 1. Check if expected files were created
            files_ok = True
            missing_files = []
            if getattr(task, "expected_files", None):
                for f in task.expected_files:
                    full_f = os.path.join(temp_dir, f)
                    if not os.path.exists(full_f):
                        files_ok = False
                        missing_files.append(f)
            
            # 2. Check for basic response quality
            has_response = len(final_answer) > 20 and "Error" not in final_answer[:50]
            
            success = files_ok and has_response
            
            # Calculate a pseudo tool accuracy based on goals
            tool_acc = 1.0 if success else (0.5 if has_response else 0.0)
            
            error_msg = f"Missing files: {missing_files}" if missing_files else None
            
            return {
                "task_id": task.id,
                "category": task.category,
                "success": success,
                "tool_accuracy": tool_acc,
                "duration_ms": duration_ms,
                "tokens": 0,
                "response_preview": final_answer[:200],
                "error": error_msg
            }
            
        except Exception as e:
            return {
                "task_id": task.id,
                "category": task.category,
                "success": False,
                "tool_accuracy": 0.0,
                "error": str(e)
            }
        finally:
            shutil.rmtree(temp_dir)


def run_agent_benchmark(models: List[str], mode: str = "mock"):
    config = ConfigManager()
    api_client = OmniApiClient(config)
    
    if not api_client.is_configured():
        print("ERROR: API Client not configured.")
        sys.exit(1)

    print(f"Starting agent benchmark ({mode.upper()} mode) for models: {', '.join(models)}")
    
    if mode == "mock":
        runner = MockAgentBenchmarkRunner(api_client, config)
    else:
        runner = RealAgentBenchmarkRunner(api_client, config)
        
    results = {
        "metadata": {
            "mode": f"agent_{mode}",
            "models_tested": models,
            "total_tasks": len(AGENT_TASKS)
        },
        "model_metrics": {},
        "task_results": {}
    }
    
    for model in models:
        print(f"\nEvaluating model: {model}")
        metrics = {
            "total_tasks": len(AGENT_TASKS),
            "successful_tasks": 0,
            "total_time_ms": 0,
            "total_tool_acc": 0.0,
        }
        
        results["task_results"][model] = []
        
        for task in AGENT_TASKS:
            task_res = runner.evaluate_task(model, task)
            
            if task_res["success"]:
                metrics["successful_tasks"] += 1
            metrics["total_time_ms"] += task_res.get("duration_ms", 0)
            metrics["total_tool_acc"] += task_res.get("tool_accuracy", 0.0)
            
            status = "[✓]" if task_res["success"] else "[✗]"
            acc = task_res.get('tool_accuracy', 0)*100
            print(f"  {status} {task.id:<10} | Acc: {acc:>3.0f}% | {task_res.get('duration_ms',0):>6.0f}ms")
            
            results["task_results"][model].append(task_res)
            
        tc = metrics["total_tasks"]
        metrics["success_rate"] = metrics["successful_tasks"] / tc if tc > 0 else 0
        metrics["tool_accuracy"] = metrics["total_tool_acc"] / tc if tc > 0 else 0
        metrics["avg_response_time_ms"] = metrics["total_time_ms"] / tc if tc > 0 else 0
        
        results["model_metrics"][model] = metrics

    # Save to JSON archive
    json_path = reporter.save_json_results(results, prefix=f"benchmark_agent_{mode}")
    print(f"\nJSON results saved to: {json_path}")
    
    # Render Markdown table
    md_table = f"### Agent Metrics ({mode.upper()})\n\n| Model | Success | Tool Acc | Avg Time (ms) |\n|-------|---------|----------|---------------|\n"
    for model, m in results["model_metrics"].items():
        md_table += f"| {model} | {m.get('success_rate',0)*100:.1f}% | {m.get('tool_accuracy',0)*100:.1f}% | {m.get('avg_response_time_ms',0):.1f} |\n"
        
    md_header = f"## 🤖 Agent Benchmark Run (Mode: {mode}, Date: {reporter.datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"
    
    # Save standalone MD report to results archive
    md_report = f"# Agent Benchmark Report ({mode})\n\n{md_table}\n\n### Task Details\n\n"
    for model, task_list in results["task_results"].items():
        md_report += f"#### {model}\n"
        for t in task_list:
             md_report += f"- **{t['task_id']}**: Success={t['success']}, Acc={t.get('tool_accuracy',0)}\n"
             if "called_tools" in t:
                 md_report += f"  - Called: {t['called_tools']} (Expected: {t.get('expected',[])})\n"
             if "error" in t:
                 md_report += f"  - Error: {t['error']}\n"
    
    md_path = reporter.save_md_results(md_report, prefix=f"benchmark_agent_{mode}")
    print(f"Markdown report saved to: {md_path}")
    
    # Append to cumulative tracking file
    reporter.append_to_benchmark_results(md_header + "\n" + md_table)
    
    # Print console summary
    reporter.print_console_summary(results, mode="agent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Agent Benchmark")
    parser.add_argument("--models", nargs="+", help="Space or comma separated list of models to test", default=["bielik_11b"])
    parser.add_argument("--mode", type=str, choices=["mock", "real"], default="mock", help="Execution mode")
    parser.add_argument("--list-models", action="store_true", help="List all available chat models from PCSS and exit")
    args = parser.parse_args()
    
    if args.list_models:
        config = ConfigManager()
        client = OmniApiClient(config)
        print("Dostępne modele:", ", ".join(client.list_models()))
        sys.exit(0)
    
    models_to_test = []
    # robust parsing of models (handles space-separated, comma-separated, or mixed)
    raw_models = args.models if isinstance(args.models, list) else [args.models]
    for m in raw_models:
        # Split by comma and then strip spaces
        for part in m.split(","):
            if part.strip():
                models_to_test.append(part.strip())
                
    run_agent_benchmark(models_to_test, mode=args.mode)
