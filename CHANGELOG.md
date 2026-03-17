# Changelog

All notable changes to the Bielik (PCSS LLM Client) project will be documented in this file.

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

## [0.1.0] - 2026-03-16

### Added

- Initial release of the PCSS LLM Client.
- Basic chat interface with Bielik model.
- Tool integration for file management and document creation.
- Settings management for API keys and workspace paths.
