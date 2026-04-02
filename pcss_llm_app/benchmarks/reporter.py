import json
import os
import datetime
from pathlib import Path

def get_project_root() -> Path:
    """Gets the absolute path to the project root (the directory containing pcss_llm_app)."""
    return Path(__file__).resolve().parent.parent.parent

def save_json_results(results_data: dict, prefix: str = "benchmark") -> str:
    """Saves the full JSON results in the benchmarks/results/ archive directory."""
    root = get_project_root()
    results_dir = root / "pcss_llm_app" / "benchmarks" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    filepath = results_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=4, ensure_ascii=False)
        
    return str(filepath)

def save_md_results(markdown_content: str, prefix: str = "benchmark") -> str:
    """Saves a detailed markdown report for a specific run in the benchmarks/results/ archive directory."""
    root = get_project_root()
    results_dir = root / "pcss_llm_app" / "benchmarks" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.md"
    filepath = results_dir / filename
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown_content)
        
    return str(filepath)

def append_to_benchmark_results(markdown_fragment: str):
    """Appends to the cumulative BENCHMARK_RESULTS.md at the project root."""
    root = get_project_root()
    filepath = root / "BENCHMARK_RESULTS.md"
    
    # Initialize the file if it doesn't exist
    if not filepath.exists():
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("# PCSS Benchmark Results\n\n")
            f.write("This file contains cumulative benchmark run results. Detailed logs per run are kept in `pcss_llm_app/benchmarks/results/`.\n\n")
            f.write("---\n")
            
    with open(filepath, "a", encoding="utf-8") as f:
        f.write("\n" + markdown_fragment + "\n")

def print_console_summary(results_data: dict, mode: str = "agent"):
    """Prints a formatted summary to the console."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK SUMMARY ({mode.upper()} MODE)")
    print(f"{'='*60}")
    
    if mode == "agent":
        print(f"| {'Model':<25} | {'Success Rate':<12} | {'Tool Acc':<10} | {'Time (ms)':<10} |")
        print(f"|{'-'*27}|{'-'*14}|{'-'*12}|{'-'*12}|")
        for model, metrics in results_data.get("model_metrics", {}).items():
            success = f"{metrics.get('success_rate', 0)*100:.1f}%"
            tool_acc = f"{metrics.get('tool_accuracy', 0)*100:.1f}%"
            avg_time = f"{metrics.get('avg_response_time_ms', 0):.1f}"
            print(f"| {model:<25} | {success:<12} | {tool_acc:<10} | {avg_time:<10} |")
    else:
        print(f"| {'Model':<25} | {'Success Rate':<12} | {'Time (ms)':<10} | {'Tokens':<8} |")
        print(f"|{'-'*27}|{'-'*14}|{'-'*12}|{'-'*10}|")
        for model, metrics in results_data.get("model_metrics", {}).items():
            success = f"{metrics.get('success_rate', 0)*100:.1f}%"
            avg_time = f"{metrics.get('avg_response_time_ms', 0):.1f}"
            tokens = metrics.get('total_tokens', 0)
            print(f"| {model:<25} | {success:<12} | {avg_time:<10} | {tokens:<8} |")
    print(f"{'='*60}\n")
