#!/usr/import/env python3
"""
PCSS LLM Chat Benchmark
Tests chat models without tools for raw speed and generation capability.
"""

import sys
import time
import argparse
from typing import Dict, List, Any

# Local imports
from pcss_llm_app.config import ConfigManager
from pcss_llm_app.core.api_client import PcssApiClient
from pcss_llm_app.benchmarks.tasks import CHAT_TASKS
from pcss_llm_app.benchmarks import reporter

def run_chat_benchmark(models: List[str]):
    config = ConfigManager()
    api_client = PcssApiClient(config)
    
    if not api_client.is_configured():
        print("ERROR: API Client not configured. Ensure PCSS_API_KEY is set or stored in keyring.")
        sys.exit(1)

    print(f"Starting chat benchmark for models: {', '.join(models)}")
    print(f"Total tasks: {len(CHAT_TASKS)}")
    
    results = {
        "metadata": {
            "mode": "chat",
            "models_tested": models,
            "total_tasks": len(CHAT_TASKS)
        },
        "model_metrics": {},
        "task_results": {}
    }
    
    for model in models:
        print(f"\nEvaluating model: {model}")
        metrics = {
            "total_tasks": len(CHAT_TASKS),
            "successful_tasks": 0,
            "total_time_ms": 0,
            "total_tokens": 0,
        }
        
        results["task_results"][model] = []
        
        for task in CHAT_TASKS:
            try:
                start_time = time.time()
                response = api_client.chat_completion(
                    model=model,
                    messages=[{"role": "user", "content": task.prompt}],
                    max_tokens=2048,
                    temperature=0.3
                )
                duration_ms = (time.time() - start_time) * 1000
                
                content = response.choices[0].message.content
                usage = response.usage
                
                metrics["successful_tasks"] += 1
                metrics["total_time_ms"] += duration_ms
                metrics["total_tokens"] += usage.total_tokens
                
                task_res = {
                    "task_id": task.id,
                    "category": task.category,
                    "success": True,
                    "duration_ms": duration_ms,
                    "tokens": usage.total_tokens,
                    "response_preview": content[:200]
                }
                
                print(f"  [✓] {task.id:<10} | {duration_ms:>6.0f}ms | {usage.total_tokens:>4} tok")
            except Exception as e:
                task_res = {
                    "task_id": task.id,
                    "category": task.category,
                    "success": False,
                    "error": str(e)
                }
                print(f"  [✗] {task.id:<10} | Error: {str(e)[:50]}")
                
            results["task_results"][model].append(task_res)
            
        success_rate = metrics["successful_tasks"] / metrics["total_tasks"] if metrics["total_tasks"] > 0 else 0
        avg_time = metrics["total_time_ms"] / metrics["successful_tasks"] if metrics["successful_tasks"] > 0 else 0
        
        metrics["success_rate"] = success_rate
        metrics["avg_response_time_ms"] = avg_time
        
        results["model_metrics"][model] = metrics

    # Save to JSON
    json_path = reporter.save_json_results(results, prefix="benchmark_chat")
    print(f"\nJSON results saved to: {json_path}")
    
    # Render Markdown table
    md_table = "### Chat Metrics\n\n| Model | Success Rate | Avg Time (ms) | Total Tokens |\n|-------|-------------|---------------|-------------|\n"
    for model, m in results["model_metrics"].items():
        md_table += f"| {model} | {m.get('success_rate',0)*100:.1f}% | {m.get('avg_response_time_ms',0):.1f} | {m.get('total_tokens',0)} |\n"
        
    md_header = f"## 🏋️ Chat Benchmark Run (Date: {reporter.datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"
    
    # Save isolated MD report
    md_report = f"# Chat Benchmark Report\n\n{md_table}\n"
    md_path = reporter.save_md_results(md_report, prefix="benchmark_chat")
    print(f"Markdown report saved to: {md_path}")
    
    # Append to cumulative
    reporter.append_to_benchmark_results(md_header + "\n" + md_table)
    
    # Print console
    reporter.print_console_summary(results, mode="chat")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Chat Benchmark")
    parser.add_argument("--models", nargs="+", help="Space or comma separated list of models to test", default=["bielik_11b", "Qwen3.5-397B-A17B-GPTQ-Int4"])
    parser.add_argument("--list-models", action="store_true", help="List all available chat models from PCSS and exit")
    args = parser.parse_args()
    
    if args.list_models:
        config = ConfigManager()
        client = PcssApiClient(config)
        print("Dostępne modele:", ", ".join(client.list_models()))
        sys.exit(0)
    
    models_to_test = []
    if isinstance(args.models, str):
        args.models = [args.models]
    for m in args.models:
        for sub_m in m.split(","):
            if sub_m.strip():
                models_to_test.append(sub_m.strip())
                
    run_chat_benchmark(models_to_test)
