# Changelog

All notable changes to the Bielik (PCSS LLM Client) project will be documented in this file.

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
