# PCSS LLM App - AI Assistant Context

## Project Overview

A Python desktop application (GUI) for interacting with the PCSS LLM Service, built with **PySide6 (Qt)** and **LangChain**.

It offers two main modes:

- **Chat Mode**: Pure conversational interface, without tools. Conversations are saved to an SQLite database (`conversations.db`).
- **Agent Mode**: Autonomous agent powered by LangChain/LangGraph with internet access, filesystem interaction, and python execution via a rich toolbox (`tools.py`, `mcp_tools.py`). It strictly operates within a secure chrooted workspace (default `~/Documents/Bielik_Workspace`). The agent dynamically adjusts to user preferences using highly-rated ("Thumbs Up") interactions from the local database as few-shot examples.

## Architecture & Modules

The codebase is cleanly separated into two primary layers:

- **`pcss_llm_app/ui/`**: Manages all PySide6 rendering. Includes `main_window.py` (tabs, input, interactions) and features like an integrated file tree (`QFileSystemModel`) and a code editor with `syntax_highlighter.py` (Monokai style).
- **`pcss_llm_app/core/`**: The brain of the application. Contains the SQLite `database.py`, `api_client.py` for PCSS network requests, and the autonomous `agent_engine.py` using ReAct prompting.
- **Tools Array (`core/tools.py` & `core/mcp_tools.py`)**: Massive suite of integrations including DuckDuckGo search, file operations, Playwright MCP browser automation, Python sandboxes, document OCR (Nanonets), and PDF/DOCX/XLSX readers.
- **`agent_profiles/`**: YAML files defining agent personas (e.g., Coder, Writer, and the newly added "Reviewer" for academic papers).

## Development Guidelines

- Always ensure new dependencies are synchronized across both `environment.yml` and `requirements.txt`.
- When modifying the UI, be aware of thread-safety between the PySide6 event loop and LangChain callbacks.
- The Agent's `mcp_tools.py` requires a functioning Node.js environment (`npx playwright-mcp-server`).
- On Windows using Conda, there is a known SSL/DLL loading quirk for PySide6 which is handled at the top of `main.py`. Do not remove these checks.

## Current Project Status

**Version 0.8.0** — major frontend modernization and backend robustness pass.

Key subsystems added in v0.6.x–v0.8.0 (see `CHANGELOG.md` for details):

- **Chat streaming** (v0.7.0): Chat mode now streams responses token-by-token via `ChatWorker.chunk_received`; unified renderer (`_render_chat_display`) across chat and agent tabs.
- **CoT Reasoning Panel** (v0.7.0): `<think>...</think>` blocks emitted by GLM-4/Qwen3/DeepSeek are extracted client-side and shown in a collapsible "Model Reasoning (CoT)" panel below the agent display.
- **Prompt Optimizer** (v0.7.0): "Optimize Prompt" button in both Chat and Agent tabs rewrites the current input using the active model.
- **Checkpoint system** (v0.7.0): `core/checkpoint_manager.py` creates a restore point before every agent task — git commit if the workspace is a git repo, `.agent_checkpoints/` file snapshot otherwise. UI: "Checkpoints" button → list + restore dialog.
- **Workspace context bootstrap** (v0.7.0): On the first agent run in a workspace, a structured `.agent_context.md` template is created from the first prompt. Internal status moved to hidden `.agent_status.md` to avoid colliding with Claude Code's `CLAUDE.md` convention.
- **Agent safety** (v0.7.1): `llm.stream()` wrapped in try/except with recovery observation; silent `except: pass` in function_call parser replaced with logging; worker cancellation polls `AgentToolAction.event.wait()` with timeout (Stop is now responsive); action-loop tracker rewritten as per-signature dict with hard cap; termination messages now include last action + last observation.
- **Profile discipline** (v0.7.2): Hard iteration limits in `reviewer.yaml` and `researcher.yaml`; `coder.yaml` retry rule clarified; shared behavioral rules moved to `llm_profiles/_shared.yaml` (`common_rules`); `context_window` declared in every LLM profile.
- **Frontend modernization** (v0.8.0): `setMinimumSize(1024, 600)` on main window; sidebar and splitters resizable/collapsible; `setFixedSize` replaced with `setMinimumSize` on buttons so text no longer clips; hardcoded inline stylesheets centralised into the `THEMES` dict (new `role="danger"`, `role="destructive"` and `#debugConsole` rules). `ChatInputWidget` height 80–240px (user-resizable). Reasoning panel header always visible so the feature is discoverable.

**Benchmarks**: `pcss_llm_app/benchmarks/` with mock and real UI modes; results archived in `pcss_llm_app/benchmarks/results/` and summarised in `BENCHMARK_RESULTS.md`.

*Note: This file serves as the primary system brief. If you are an AI assistant placed into this repository, refer to this context to understand the app's structure and current trajectory.*
