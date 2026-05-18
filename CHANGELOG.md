# Changelog

All notable changes to the Bielik (omni.ai) project will be documented in this file.

## [0.10.0] - 2026-05-18

### Added
- **New LLM Profiles**: Added profiles for popular commercial and open-source models:
  - `gpt-4o.yaml` — GPT-4o (128K context, 16K max tokens)
  - `gpt-4o-mini.yaml` — GPT-4o Mini (fast, cost-effective)
  - `claude-3-5-sonnet.yaml` — Claude 3.5 Sonnet (200K context, strong reasoning)
  - `claude-3-opus.yaml` — Claude 3 Opus (200K context, most powerful)
  - `llama-3.1-70b.yaml` — Llama 3.1 70B (131K context, open-source)
  - `llama-3.2-90b.yaml` — Llama 3.2 90B (131K context, vision capabilities)

- **New Agent Profiles**: Specialized agent personas for specific domains:
  - `data_analyst.yaml` — Statistical analysis, data exploration, visualization
  - `security_auditor.yaml` — Code security auditing, vulnerability detection (OWASP Top 10)
  - `devops_engineer.yaml` — CI/CD, Docker, Kubernetes, infrastructure as code
  - `product_manager.yaml` — Requirements, user stories, roadmaps, stakeholder communication

- **New Tool Categories**:
  - **Git Tools**: `git_status`, `git_diff`, `git_log` — version control operations
  - **API Tools**: `http_request` — REST/GraphQL API testing with full response inspection
  - **Database Tools**: `execute_sql_query` — SQLite/PostgreSQL read-only queries (safety-first)

- **Multi-Provider Support**: Enhanced `_shared.yaml` with universal compatibility rules for:
  - PCSS, OpenRouter, Ollama, LM Studio, vLLM, OpenAI, Gemini
  - Rate limit handling (429), server errors (500), timeout recovery
  - Model-specific format adaptation (<think> tags, XML format)

### Changed
- **Tool Catalog Expansion**: Updated `_shared.yaml` to include Git, API, and Database tools in the canonical tool list
- **Agent Engine**: Modified `agent_engine.py` to auto-load new tool categories (Git, API, Database)
- **Profile Instructions**: All new profiles include incremental writing rules to prevent truncation

### Security
- **Database Safety**: `execute_sql_query` blocks dangerous operations (DROP, TRUNCATE, DELETE, UPDATE) — only SELECT allowed
- **Git Sandbox**: All Git operations restricted to workspace directory via `_safe_path()`

### Technical
- **Import Chain**: Updated `agent_engine.py` imports to include `GitTools`, `APITools`, `DatabaseTools`
- **Tool Initialization**: New tools logged at startup with checkmarks (✓) or info messages (ℹ)

## [0.9.1] - 2026-04-27

### Added
- **Gemini Provider**: Added `https://generativelanguage.googleapis.com/v1beta/openai/` to the default LLM provider list in the UI and settings.
- **Custom Model Profiles**: `settings.json` now supports a `custom_model_profiles` dictionary, allowing users to manually override automated profile assignments.
- **Agent Identity**: Added instructions to `_shared.yaml` ensuring the agent identifies itself as **Omni.ai** when asked.

### Changed
- **Regex-based LLM Profiling**: Replaced hardcoded provider lists in `agent_engine.py` with a heuristic regex system that detects parameter sizes (e.g. `120b`, `8x7b`) to dynamically assign unseen models to appropriate performance tiers (ULTRA, LARGE, BASE, SMALL).
- **Consolidated LLM YAML Profiles**: Refactored `omni_agent/llm_profiles/` by moving redundant behavioral rules into a unified `_shared.yaml`. Individual model profiles now contain only their unique instructions, saving prompt tokens and simplifying maintenance.
- **UI Styling**: The `Create Assistant` button in the Agent Tab now uses a green `success` role for better visibility and UX.

## [0.9.0] - 2026-04-20

### Added
- **Proactive context compression (60% threshold)**: New pre-emptive trim stage in `agent_engine.py` that removes the oldest ~25% of observation blocks when the prompt exceeds 60% of the context-window limit — before TTFT starts to grow exponentially. The existing reactive overflow guard (at 100%) is preserved as a safety net. Both stages log diagnostic messages (`🗜️ Proactive compression at XX%`).
- **`run_terminal` configurable timeout**: `TerminalSchema` gains a `timeout: int` field (default 15 s). The LLM can now specify `timeout: 120` (or higher) for long-running processes such as Playwright browser automation, test suites, and slow build scripts. The process is hard-killed after the timeout; the error message now reports the actual timeout value used.

### Changed
- **Stagnation hard-stop**: The repeated-observation detector in `agent_engine.py` is replaced with a counter (`_stagnation_count`). On each identical observation the agent receives a progressive warning (*"repetition 1/3 — 2 more before termination"*). After **3 consecutive identical observations** the engine returns a rich diagnostic (last tool, observation excerpt) and terminates cleanly instead of looping indefinitely. The counter resets on every new (distinct) observation.
- **Eliminated duplicate log entries**: `main_window.append_log()` no longer writes to `agent_debug.log`. All file logging is now exclusively handled by `agent_engine._log()` (format: `[HH:MM:SS][model_name] message`). This halves the size of the debug log — previously every event was recorded twice (once from the engine, once from the UI callback).

### UI / Frontend
- **Obsidian Atelier theme** (`Cobalt`): complete palette rewrite — deep `#0E0E11` obsidian base, `#C9A84C` warm-gold accent replacing the generic navy-blue aesthetic. All color tokens keyed: `doc_bg`, `border_strong`, `selection_bg`, `button_border`, `scrollbar_*`, `tree_*`, message-bubble backgrounds/borders, `code_bg`/`code_fg`, `splitter`.
- **Warm Daylight theme** (`Dreamweaver`): ivory `#F5F4EF` paper with `#8B6914` amber accent for WCAG-compliant contrast on light backgrounds.
- **Styled message bubbles**: user, AI, agent and system messages each have distinct `background`, `border-left` and label colour derived from the active theme palette.
- **QSS redesign** (`apply_theme`): tabs use underline-only style (2 px solid accent on selected, no box borders); scrollbars slimmed to 6 px, no arrows, gold on hover; buttons use 6 px radius, `font-weight: 500`, correct `:checked` state.
- **Graphite adjustment**: Cobalt `background` softened from pure obsidian `#0A0A0D` to graphite `#1E1E22` for reduced eye strain without losing the dark aesthetic.

## [0.8.2] - 2026-04-18
### Fixed
- **Main window not appearing when PCSS API is slow/unresponsive**: `MainWindow.__init__` called `_refresh_models()` synchronously, which invokes `client.models.list()` — a blocking network request. When the server was slow the GUI thread froze before `show()` ran, so the user saw only a dock icon and no window. Fixed by deferring the model refresh to `QTimer.singleShot(50, …)` after `show()`, and by shortening `list_models()` HTTP timeout to 8 s so it fails fast instead of holding the UI indefinitely. The combobox shows "Loading models..." until the first refresh completes.

## [0.8.1] - 2026-04-18
### Fixed
- **Infinite retry on persistent LLM stream errors**: regression introduced in v0.7.1. The stream-error recovery path used `continue` without incrementing the step counter, so on repeated `APITimeoutError` / `RemoteProtocolError` the agent retried forever (each retry waiting the full 120 s client timeout). Added a `consecutive_stream_errors` circuit breaker: after 3 back-to-back stream failures the agent returns a rich diagnostic (last error type, last action, last observation) instead of looping. Counter resets on any successful stream.

## [0.8.0] - 2026-04-18
### Added
- **Frontend modernization**: `setMinimumSize(1024, 600)` on main window prevents layout collapse; sidebar resizable (180–320 px) and collapsible; outer and content splitters expose stretch factors so the right panel grows and the console can be hidden.
- **Role-based button styles**: stop buttons use `role="danger"`, destructive actions use `role="destructive"` — colours live in `THEMES` dict and respect theme switching.
- **Reasoning panel discoverability**: the "Model Reasoning (CoT)" header is always visible, with an arrow toggle (▶/▼) and a live character-count badge so users notice reasoning is available before any `<think>` content arrives.
- **Debug console themed**: no more green-on-black regardless of theme; `QTextEdit#debugConsole` styles pulled from `console_bg`/`console_fg`.

### Changed
- All emoji-only buttons (`⬛ Stop`, `↻`, `📁`, `✨`, `🧠`) replaced with plain text labels — renders consistently on Windows/Linux/macOS and no longer clips inside fixed-width buttons.
- `ChatInputWidget` height: 80–240 px (was fixed 80 px) — multi-line prompts are usable.
- Agent tab status bar now hosts the "Debug Console" toggle, decluttering the config row.

### Fixed
- `QPushButton` widths no longer truncated: every `setFixedSize` replaced with `setMinimumSize` so longer labels ("Optimize Prompt", "Send to Agent") always fit.
- Inline stylesheets (console, clear-history button, workspace label, stop buttons) centralised into `apply_theme()`; changing theme now updates every widget.

### Documentation
- README: Python requirement corrected to 3.11+; outdated "Tested on macOS" disclaimer replaced; file-tool list synced to actual LangChain FileManagementToolkit names (`file_delete`, `file_search`, `copy_file`, `move_file`).
- CLAUDE.md: project brief rewritten from v0.4.1 to v0.8.0, covering streaming chat, reasoning panel, prompt optimizer, checkpoints, `.agent_context.md` bootstrap, agent safety fixes, and profile discipline.

## [0.7.2] - 2026-04-17
### Changed
- **Profile discipline** — loop-inducing patterns removed from agent profiles:
  - `reviewer.yaml`: per-reference cap of 2 verification attempts before marking UNVERIFIED and moving on; self-enforced loop prevention (no reliance on system warnings).
  - `researcher.yaml`: explicit research budget (max 10 sources, 2–3 discovery rounds); `search_academic` demoted from MANDATORY to preferred-with-fallback.
  - `coder.yaml`: retry rule clarified — at most 2 attempts per sub-problem, second must use materially different args, then switch tool or ask user.
  - `document_writer.yaml`: `search_academic` fallbacks documented.
- **Shared rules** (`llm_profiles/_shared.yaml`): new `common_rules` block with language/encoding, behavioral, search-language, export and anti-loop rules that used to be duplicated across 15 LLM profiles. `llm_profile_loader.py` prepends these automatically; profiles can opt out via `skip_common_rules: true`.
- **Context window declared** in every LLM profile (was only in `bielik_11b`). Matches the tiered profiling in `agent_engine.py` and prevents silent truncation loops on long tasks.

## [0.7.1] - 2026-04-17
### Fixed
- **Crash on LLM stream errors**: wrapped `self.llm.stream()` in a try/except. Network issues, API 500s, malformed chunks now inject a `[SYSTEM]` recovery observation instead of propagating unhandled — scratchpad is preserved, agent gets a chance to retry or emit a clean `Final Answer`.
- **Silent parse failure** (`except: pass`) in the `function call {...}` fallback parser replaced with typed exception handling and a diagnostic log.
- **Worker cancellation race**: `AgentToolAction.event.wait()` now polls with a 0.5 s timeout; `Stop` during tool-approval waits actually cancels instead of hanging the UI.
- **Action loop evasion**: `action_loop_warnings` rewritten from a single int to a per-signature dict keyed by `(action, input-prefix)`. A→B→A→B patterns no longer evade the counter. Hard safety cap of `loop_threshold × 3` total interventions.
- **"No output after loop exit"**: every termination path (thought-loop stop, action-loop stop, hard-cap stop, double-empty stop) now returns a rich message with recent actions and last observation instead of a canned one-liner.

## [0.7.0] - 2026-04-17
### Added
- **Chat mode streaming**: `ChatWorker` now uses `stream=True` and emits `chunk_received` per delta; unified chat renderer (`_render_chat_display`) with scroll-preservation.
- **CoT Reasoning Panel**: collapsible `🧠 Model Reasoning (CoT)` section extracts `<think>...</think>` tags from agent stream and strips them from the main display — visible content in one pane, reasoning in another.
- **Optimize Prompt button**: both Chat and Agent tabs — rewrites the current input via the active model for better clarity and precision.
- **Checkpoint system** (`core/checkpoint_manager.py`): creates a restore point before every agent task. Git commit if the workspace is a git repo, file snapshot in `.agent_checkpoints/` otherwise. "🔖 Checkpoints" button opens a list/diff/restore dialog.
- **`.agent_context.md` bootstrap**: first agent run in a new workspace creates a structured project template (Goal, Tech Stack, Status, Completed, Todo, Notes) populated from the first prompt. Never overwrites an existing file.
- **SQLite indexes** on `messages.conversation_id`, `messages.rating`, `conversations.created_at`.
- **Plan-before-Execute**: ULTRA/LARGE-tier models (397B, DeepSeek V3, 72B+) receive a planning directive in the system prompt so they write a numbered plan in the first `Thought:` before executing — reduces round-trips on complex tasks.
- **Tier-based few-shot**: 10 / 7 / 5 / 3 examples for ULTRA / LARGE / BASE / SMALL (was hardcoded 3 for everyone).

### Changed
- Internal status file renamed from `CLAUDE.md` (which collided with Claude Code's project-instruction convention) to `.agent_status.md`.

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

- **Benchmark Integration**: Integrated `benchmark_pcss.py` and `benchmark_agents_pcss.py` from `test_tmp/` into the main `omni_agent/benchmarks/` module.
  - **Mock & Real Modes**: Agent benchmark now supports testing via fast OpenAI native function calling (mock mode) or full `LangChainAgentEngine` execution in a temporary sandboxed workspace (real mode).
  - **Tool Schema Reflection**: Benchmark tasks use the exact OpenAI function schemas generated recursively from the active `omni_agent.core.tools` library.
- **Reporting System**: Standalone `BENCHMARK_RESULTS.md` table added, and detailed historical runs are archived as Markdown files in `omni_agent/benchmarks/results/`.

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

- Initial release of the omni.ai.
- Basic chat interface with Bielik model.
- Tool integration for file management and document creation.
- Settings management for API keys and workspace paths.
