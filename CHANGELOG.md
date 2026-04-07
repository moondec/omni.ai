# Changelog

All notable changes to the Bielik (PCSS LLM Client) project will be documented in this file.

## [0.5.0] - 2026-04-07
### Added
- **Multi-LLM Consilium Mode**: A new collaborative mode where multiple LLMs work together to solve complex tasks using the "Debate" pattern.
  - **Executor Role**: Primary model that performs the task with full tool access (default: Qwen3.5-397B).
  - **Reviewer Role**: Evaluates the Executor's output for accuracy and completeness (default: DeepSeek-V3.1).
  - **Skeptic Role**: Acts as a Devil's Advocate, challenging assumptions and finding edge cases (default: GLM-4.7).
  - **Read-Only Tool Filter**: Reviewer and Skeptic models are programmatically restricted to non-destructive tools (`view_file`, `search_files`, etc.) to prevent workspace conflicts.
  - **UI Integration**: New toggle in the Agent tab to activate Consilium Mode and select models for each role. Debug console prefixes (`[EXECUTOR]`, `[REVIEWER]`, `[SKEPTIC]`) trace the collaboration.

### Changed
- **Consilium Profiles**: Moved Consilium-specific agent profiles (`consilium_reviewer.yaml`, `consilium_skeptic.yaml`) into a dedicated `consilium_roles/` subdirectory to declutter the main profile selection menu in the UI.

### Fixed
- **Agent Feedback Loops**: Added definitive "Conversation Rules" to strict agent profiles (`reviewer.yaml`, `bielik_pisarz.yaml`, and consilium roles). This "Mode Switching" prevents agents from restarting their hardcoded procedural workflows from step zero when the user provides conversational feedback or argues with their analysis.

## [0.4.2] - 2026-04-07

### Enhanced

- **`search_files` — Binary Document Search**: The `search_files` tool now natively searches inside `.docx`, `.pdf`, and `.xlsx`/`.xls` files by extracting text content using `python-docx`, `pdfplumber`/`pypdf`, and `openpyxl`. Previously, these binary files were opened as raw UTF-8 text, producing garbage results.
  - **Regex support**: New `use_regex` parameter allows searching with regular expressions.
  - **Case sensitivity**: New `case_sensitive` parameter (default: `False` for intuitive matching).
  - **DOCX tables**: Extracts text from both paragraphs and table cells.
  - **Statistics**: Results now include a count of text vs. document files searched.
  - **Zero new dependencies**: Uses libraries already present in `requirements.txt`.

## [0.4.1] - 2026-04-06

### Added

- **Server Latency Diagnostics**: Added exact Time-to-First-Token (TTFT) and overall generation throughput (approx. tokens/sec) instrumentation to `LangChainAgentEngine._log`. This separates HPC prefill server latency wait times from local execution stream speed, enabling true performance benchmarking of high-capacity models like DeepSeek.
- **Modular UI Components**: Extracted chat and agent text inputs from `main_window.py` event filters into a standalone `ChatInputWidget` component (`ui/components/chat_input.py`), improving code decoupling.
- **Graceful Shutdown Flags**: Implemented boolean cancellation flags in `Worker` threads and `LangChainAgentEngine` to allow gentle interrupting of long generation loops.

### Fixed

- **App Freezes / SQLite Corruption**: Removed forceful `QThread.terminate()` calls when clicking the "Stop" button, resolving background instability.
- **Agent Loops on Document Reading**: Raised similarity loop threshold to 0.99 for file-reading tools to avoid false positives during incremental reading.
- **Playwright MCP Missing TypeError**: Added proper `None`-checks for Playwright initializations handling edge cases where the MCP sub-process fails to load.

## [0.4.0] - 2026-04-02

### Added

- **Benchmark Integration**: Integrated `benchmark_pcss.py` and `benchmark_agents_pcss.py` from `test_tmp/` into the main `pcss_llm_app/benchmarks/` module.
  - **Mock & Real Modes**: Agent benchmark now supports testing via fast OpenAI native function calling (mock mode) or full `LangChainAgentEngine` execution in a temporary sandboxed workspace (real mode).
  - **Tool Schema Reflection**: Benchmark tasks use the exact OpenAI function schemas generated recursively from the active `pcss_llm_app.core.tools` library.
- **Reporting System**: Standalone `BENCHMARK_RESULTS.md` table added, and detailed historical runs are archived as Markdown files in `pcss_llm_app/benchmarks/results/`.

## [0.3.0] - 2026-04-01

### Added

- **Qwen3-VL-235B Profile**: New specialized YAML profile for vision-language tasks with autonomous image analysis rules.

### Changed

- **LLM Profile Engine (Bug-fix)**:
  - Fixed `_get_llm_profile_data` in `ui/main_window.py` to correctly load `system_prompt_additions`.
  - Updated `LangChainAgentEngine` in `core/agent_engine.py` to inject these additions at the start of the system prompt.
- **LLM Token Optimization**:
  - Increased `max_tokens` for `llama3.3-70b` (8192) and `MiniMax-M2.5` (12288) to prevent output truncation.
  - Added mandatory **Incremental Writing** instructions to heavyweight models (Qwen3.5, MiniMax) to avoid tool-call truncation.
- **Profile Synchronization**: Renamed `qwen2.5.yaml` to `Qwen2.5-72b.yaml` to match API model naming.

## [0.2.3] - 2026-03-30

### Fixed

- **`deep_research` Pydantic validation error**: LLMs (especially GLM-4) send `{"query": "..."}` instead of `{"topic": "..."}`. Added automatic argument alias mapping (`query` → `topic`, `question` → `topic`) in the preflight section of `agent_engine.py`.
- **`save_document` Pydantic validation error**: Large HTML content with unescaped inner quotes breaks JSON parsing, causing only `file_path` to survive. Added three-layer defense:
  1. **Alias mapping**: Maps `text`/`body`/`html` → `content` before validation.
  2. **Content recovery**: Attempts to extract content from the raw `action_input` string when JSON parsing truncates it.
  3. **Graceful fallback**: If recovery fails, advises the agent to use `write_file` instead, preventing infinite retry loops.
- **Wasteful format correction loops**: Agent produced complete task summaries (with ✅ markers, structured lists, questions) but without the `Final Answer:` prefix. The old logic would trigger "Format error (1/4)" through "(4/4)" — wasting 3–5 extra LLM calls per task. Added **smart completion detection** that auto-promotes completion-like outputs to Final Answer immediately, based on:
  - Completion markers (✅, `gotowy`, `wykonane`, `completed`, etc.)
  - Structural signals (list items, substantial length >200 chars)
  - Question patterns (`Czy chcesz...?`)
- Also improved the format correction prompt to mention `Final Answer:` as an option (previously only showed `Action:` format), and reduced max retries from 4 to 3.

## [0.2.2] - 2026-03-29

### Added

- **Tool Action Approvals**: Introduced a GUI interception mechanism (`QMessageBox`) that requires user permission before the autonomous agent executes sensitive sandbox tools, like creating or editing files.

### Fixed

- **Context Starvation loops**: Restored `MAX_PROMPT_CHARS` to 200,000 in `agent_engine.py`. This resolves a severe regression where the agent would aggressively trim its own memory after generating large files, leading to "amnesia" and infinite similarity loops (repeating identical actions).

## [0.2.1] - 2026-03-25

### Fixed

- **Infinite Loop Prevention**: Added mechanisms to detect loop behavior (e.g., repeating the same tool context endlessly) and force a final answer format when consecutive errors exceed limits.
- **DOCX Extraction Improvement**: Enhanced `read_docx` to correctly extract formulas and `<m:oMath>` tags that were previously ignored by `python-docx`'s default `.text` property, preventing the agent from infinitely searching for missing equations.
- **MiniMax Parser Support**: Fixed parsing failures specific to the MiniMax model, capturing hybridized `Action Input:` injections inside native XML tags.

## [0.2.0] - 2026-03-17

### Added

- **File Explorer Panel**: New sidebar widget with a `QTreeView` and `QFileSystemModel` for navigating the current workspace.
- **Integrated Code Editor**: A dedicated tab for viewing and editing code files directly within the application.
- **Syntax Highlighting**: Real-time syntax highlighting in the editor via Pygments with the Monokai dark theme.
- **Language Detection**: Automatic detection of programming languages with a visual indicator in the editor toolbar.
- **Workspace Navigation**: Double-click files in the explorer to open them in the editor.
- **Dynamic Settings**: Workspace root directory can now be changed in Settings, with automatic tree refresh.
- **Reviewer Agent Profile**: Added a specialized "Recenzent - Reviewer" agent profile (`reviewer.yaml`) for formal reference and structural analysis.
- **Document Reading Capabilities**: Rolled out `read_pdf`, `read_docx`, and newly added `read_xlsx` tools to the new Reviewer and all standard model profiles.

### Changed

- Refactored `main_window.py` to support the new sidebar and tab structure.
- Enhanced `QPlainTextEdit` styling for a better developer experience (dark mode, monospace fonts).

### Fixed

- Fixed layout issues when resizing the main window with the new splitter-based sidebar.
- Fixed PySide6 Windows DLL loading issue by enforcing pip installation in `environment.yml`.
- Synchronized missing dependencies in `environment.yml` and `README.md` (`numpy`, `pandas`, `pygments`, `pydantic`, `duckduckgo-search`, `pypdf`).

## [0.1.0] - 2026-03-16

### Added

- Initial release of the PCSS LLM Client.
- Basic chat interface with Bielik model.
- Tool integration for file management and document creation.
- Settings management for API keys and workspace paths.
