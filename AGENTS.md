# AGENTS.md — Quick Context for AI Assistants

## Project Summary
**omni.ai** — PySide6 desktop app for PCSS LLM Service with two modes:
- **Chat**: Stateless Q&A, no tools, history in `conversations.db`
- **Agent**: Autonomous LangChain/LangGraph agent with full toolbox (files, web, Python, Playwright MCP, OCR)

## Critical Architecture Notes

### Entry Points
- **Main app**: `python omni_agent/main.py`
- **Dictation utility**: `python voice_typing.py` (global hotkey: `Left Ctrl + Space`)
- **Benchmarks**: `python -m omni_agent.benchmarks.run_chat` or `run_agent --mode mock|real`

### Agent Engine (`omni_agent/core/agent_engine.py`)
- ReAct loop with strict **one Action per step** rule
- Tiered model profiling (ULTRA/LARGE/BASE/SMALL) based on parameter size regex
- Context compression at 60% threshold (proactive) + overflow guard at 100%
- Stagnation detector: terminates after 3 identical consecutive observations
- Circuit breaker: 3 consecutive stream errors → rich diagnostic, no infinite retry
- Checkpoint system: git commit if workspace is git repo, else `.agent_checkpoints/` file snapshot

### Tool Constraints
- **Workspace**: Agent strictly chrooted to `settings.json` → `workspace_path` (default `~/Documents/Bielik_Workspace`)
- **Line-based editing**: `replace_file_content` uses 1-indexed line numbers (NOT string matching)
- **Tool approvals**: GUI interception for file create/edit operations
- **Playwright MCP**: requires `npx playwright-mcp-server` + Node.js environment

### LLM Profiles
- **Shared rules**: `omni_agent/llm_profiles/_shared.yaml` (common_rules, tool_catalog)
- **Agent personas**: `omni_agent/agent_profiles/*.yaml` (coder, reviewer, researcher, document_writer)
- **Custom overrides**: `settings.json` → `custom_model_profiles` dict
- **Context window**: declared in every profile; prevents silent truncation loops

## Developer Commands

### Environment Setup
```bash
# Conda (recommended macOS/Linux)
conda env create -f environment.yml
conda activate bielik

# venv alternative
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Optional: Smart Document Intelligence (~1 GB)
pip install docling pillow
```

### Prerequisites (Non-Obvious)
- **Pandoc >= 3.0**: Required for `convert_document` tool
- **Node.js + npm**: Required for Playwright MCP (`npx playwright-mcp-server`)
- **Playwright browsers**: `npx playwright install chromium` (if browser tools fail)

### Testing & Verification
```bash
# List available PCSS models
python -m omni_agent.benchmarks.run_chat --list-models

# Chat benchmark (specific models)
python -m omni_agent.benchmarks.run_chat --models bielik_11b,Qwen3.5-397B-A17B-GPTQ-Int4

# Agent benchmark (fast, mock mode)
python -m omni_agent.benchmarks.run_agent --models bielik_11b --mode mock

# Agent benchmark (real, spawns LangChainAgentEngine in temp workspace)
python -m omni_agent.benchmarks.run_agent --models bielik_11b --mode real
```

### Dependency Sync
- Always update **both** `environment.yml` AND `requirements.txt` together
- `readability-lxml` is pip-only (required for `visit_page` / `deep_research`)

## Known Quirks & Gotchas

### Windows Conda + PySide6
- DLL loading issues handled in `main.py` (automatic `os.add_dll_directory`)
- SSL env vars (`SSL_CERT_FILE`, `CURL_CA_BUNDLE`) cleared if leaking from Conda base

### Thread Safety
- PySide6 event loop ↔ LangChain callbacks: use `QTimer.singleShot()` for post-show initialization
- Worker cancellation: polls `AgentToolAction.event.wait(0.5)` — Stop button now responsive

### Agent Loop Prevention
- Hard iteration limits in `reviewer.yaml` (2 verification attempts per reference)
- `researcher.yaml`: max 10 sources, 2–3 discovery rounds
- `coder.yaml`: max 2 retries per sub-problem, then switch tool or ask user

### File Logging
- All debug logs → `agent_debug.log` (exclusively via `agent_engine._log()`)
- Format: `[HH:MM:SS][model_name] message`
- UI callback `main_window.append_log()` does NOT write to file (prevents duplicates)

### Context Files (Agent Workspace Bootstrap)
- `.agent_context.md`: Structured project template (Goal, Tech Stack, Status, Todo) — created on first agent run, never overwritten
- `.agent_status.md`: Hidden internal status (renamed from `CLAUDE.md` to avoid collision with Claude Code)

## Model-Specific Behavior
- **GLM-4 / Qwen3 / DeepSeek**: Emit `<think>...</think>` CoT blocks → extracted client-side, shown in collapsible "Model Reasoning" panel
- **ULTRA/LARGE models (≥100B params)**: Receive planning directive → write numbered plan in first `Thought:` before executing
- **MiniMax**: Custom parser for hybrid XML + `Action Input:` format

## UI Frontend Notes
- Theme system: `THEMES` dict centralizes all colors (no inline stylesheets)
- `ChatInputWidget`: resizable 80–240px height
- Reasoning panel header always visible (discoverability)
- All buttons use `setMinimumSize()` (no text clipping)
- Sidebar: resizable 180–320px, collapsible

## Important File Boundaries
```
omni_agent/
├── core/
│   ├── agent_engine.py      # ReAct loop, context compression, error recovery
│   ├── tools.py             # Core toolbox (files, web, Python, OCR, documents)
│   ├── mcp_tools.py         # Playwright MCP (33+ browser tools)
│   ├── checkpoint_manager.py # Git/file snapshots
│   ├── database.py          # SQLite (conversations, few-shot examples)
│   └── api_client.py        # PCSS HTTP client
├── ui/
│   ├── main_window.py       # PySide6 tabs, input, file tree, code editor
│   └── syntax_highlighter.py # Monokai style (Pygments)
├── llm_profiles/            # Model-specific YAML (context_window, system prompts)
└── agent_profiles/          # Agent personas (coder, reviewer, researcher, writer)
```

## Testing Quirks
- **Agent benchmark real mode**: Spawns in temporary proxy directory (isolated workspace)
- **Similarity loop threshold**: 0.99 for file-reading tools (prevents false positives during incremental reading)
- **Flaky tests**: None documented; benchmark suite is deterministic (mock mode uses OpenAI native function-calling)

## Style Conventions
- Code comments, docstrings, documentation: **English only** (enforced in `_shared.yaml`)
- Search queries: **English** for technical/scientific topics (Polish only for Poland-specific culture/law/current events)
- Tool calls: **exactly one Action per step** (no multi-action blocks)
- File edits: **always** `view_file` before `replace_file_content` (line numbers required)

## References
- Full feature docs: `README.md`
- Model guide: `MODEL_GUIDE.md`
- Tool reference: `TOOLS_GUIDE.md` (if exists)
- Version history: `CHANGELOG.md` (v0.9.1 current)
- Existing AI context: `CLAUDE.md` (system brief)
