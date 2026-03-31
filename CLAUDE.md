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
- **Environment**: Fully stable. Fixes implemented for macOS/Windows `RequestsDependencyWarning` and SSL cert resolution in `venv`. Resolved context starvation loop bugs by restoring the 200,000 character prompt limit.
- **UI Enhancements**: Added an integrated code editor with syntax highlighting and direct file manipulation access. Tool and file modification actions now prompt the user for graphical GUI approval (`QMessageBox`).
- **Capabilities**: Document reading capabilities expanded across all standard models. Specialized QA/Reviewer profiles implemented. `read_docx` completely extracts OMath equation text (`m:t`).
- **Next Steps**: Awaiting new feature iterations (e.g., further API integrations, expanded workspace capabilities for agents, or more UI enhancements).

*Note: This file serves as the primary system brief. If you are an AI assistant placed into this repository, refer to this context to understand the app's structure and current trajectory.*
