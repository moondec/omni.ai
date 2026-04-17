import sys
import os
import glob
import yaml
import platform
import subprocess
from PySide6.QtCore import Qt, QSize, QTimer, QThread, Signal, QObject, QEvent, QDir, QFileInfo
from PySide6.QtGui import QAction, QIcon, QTextCursor, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTextEdit, QTextBrowser, QLineEdit, QPushButton, QLabel, 
    QComboBox, QSplitter, QFrame, QScrollArea, QSizePolicy,
    QApplication, QTabWidget, QFileDialog, QMessageBox, QDialog, QFormLayout,
    QListWidget, QMenu, QTreeView, QPlainTextEdit, QFileSystemModel
)
import datetime
import markdown
import time

from pcss_llm_app.config import ConfigManager
from pcss_llm_app.core.api_client import PcssApiClient
from pcss_llm_app.core.database import DatabaseManager

from pcss_llm_app.core.file_manager import FileManager
from pcss_llm_app.core.agent_engine import LangChainAgentEngine
from pcss_llm_app.core.consilium import ConsiliumOrchestrator
from pcss_llm_app.core.llm_profile_loader import load_llm_profile
from pcss_llm_app.core.workers import ChatWorker, AgentWorker, ConsiliumWorker
from pcss_llm_app.ui.components.chat_input import ChatInputWidget
from pcss_llm_app.ui.syntax_highlighter import PygmentsSyntaxHighlighter
from pcss_llm_app import __version__

# Safe LangChain Message Imports
try:
    from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
except ImportError:
    try:
        from langchain.schema import HumanMessage, AIMessage, BaseMessage
    except ImportError:
        class BaseMessage: content = ""
        class HumanMessage(BaseMessage): pass
        class AIMessage(BaseMessage): pass

class AgentLogSignal(QObject):
    log_message = Signal(str)

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None, available_models=None):
        super().__init__(parent)
        self.config = config_manager
        self.available_models = available_models or []
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        

        settings_dlg_layout = QFormLayout()
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        # Pre-fill if exists (optional, mostly empty for security)
        if self.config.get_api_key():
             self.api_key_input.setPlaceholderText("Stored in Keyring")
        
        settings_dlg_layout.addRow("PCSS API Key:", self.api_key_input)
        
        # Workspace Path
        self.workspace_input = QLineEdit(self.config.get_workspace_path())
        workspace_layout = QHBoxLayout()
        workspace_layout.addWidget(self.workspace_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_workspace)
        workspace_layout.addWidget(browse_btn)
        settings_dlg_layout.addRow("Workspace:", workspace_layout)

        # Model Selection
        self.model_combo = QComboBox()
        if self.available_models:
            self.model_combo.addItems(self.available_models)
        else:
            self.model_combo.addItems(["bielik_11b", "DeepSeek-V3.1-vLLM"]) # Default fallback
            
        current_model = self.config.get("model", "bielik_11b")
        self.model_combo.setCurrentText(current_model)
        settings_dlg_layout.addRow("Default Model:", self.model_combo)

        # Base URL
        self.base_url_input = QLineEdit(self.config.get_base_url())
        self.base_url_input.setPlaceholderText("https://llm.hpc.pcss.pl/v1")
        settings_dlg_layout.addRow("LLM Server URL:", self.base_url_input)

        # Transcription Model
        self.transcription_model_input = QLineEdit(self.config.get("transcription_model", "whisper-large-v3-turbo:0.8b"))
        self.transcription_model_input.setPlaceholderText("whisper-large-v3-turbo:0.8b")
        settings_dlg_layout.addRow("Transcription Model:", self.transcription_model_input)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        settings_dlg_layout.addRow(save_btn)
        
        self.setLayout(settings_dlg_layout)

    def browse_workspace(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Workspace Directory")
        if dir_path:
            self.workspace_input.setText(dir_path)

    def save_settings(self):
        api_key = self.api_key_input.text().strip()
        if api_key:
            if not self.config.set_api_key(api_key):
                QMessageBox.critical(self, "Error", "Failed to save API Key to Keyring.")
                return # Don't proceed if API key save failed
            
        workspace_path = self.workspace_input.text().strip()
        if workspace_path:
            self.config.set_workspace_path(workspace_path)
            
        selected_model = self.model_combo.currentText()
        if selected_model:
            self.config.set("model", selected_model)

        base_url = self.base_url_input.text().strip()
        if base_url:
            self.config.set_base_url(base_url)
            
        transcription_model = self.transcription_model_input.text().strip()
        if transcription_model:
            self.config.set("transcription_model", transcription_model)
            
        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"PCSS LLM Client v0.6.4")
        self.setGeometry(100, 100, 1200, 800)
        
        # Set App Icon
        logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "logo.png")
        if os.path.exists(logo_path):
             self.setWindowIcon(QIcon(logo_path))

        # Main Layout      
        self.config = ConfigManager()
        self.api = PcssApiClient(self.config)
        self.db = DatabaseManager()
        
        self.current_conversation_id = None
        self.current_agent_conversation_id = None
        self.chat_history = [] 

        self.prompt_history = []
        self.prompt_history_idx = 0 

        # Agent Log Signal
        self.agent_logger = AgentLogSignal()
        self.agent_logger.log_message.connect(self.append_log)

        # Agent State (LangChain)
        self.agent_engine = None
        self.agent_history = []
        self.current_agent_scratchpad = ""
        
        # Worker instances for cancellation
        self.chat_worker = None
        self.agent_worker = None
        
        # Theme state
        self.current_theme = "Cobalt"

        # UI Throttling
        self.log_buffer = []
        self.chat_needs_render = False
        self.ui_update_timer = QTimer(self)
        self.ui_update_timer.timeout.connect(self._throttled_ui_update)
        self.ui_update_timer.start(250) # 4 FPS (Smoother performance during heavy streaming)

        self._init_ui()
        
        # Check API Key
        if not self.config.get_api_key():
            QMessageBox.warning(self, "Setup", "Please configure your API Key in Settings.")
            self.open_settings()
        
        # Try to load models
        self._refresh_models()
        
        # Apply saved theme or default
        saved_theme = self.config.get("theme", "Cobalt")
        self.apply_theme(saved_theme)
    
    # Theme definitions: Cobalt (dark) and Dreamweaver (light)
    THEMES = {
        "Cobalt": {
            "name": "Cobalt",
            "type": "dark",
            "background": "#002240",
            "foreground": "#ffffff",
            "secondary_bg": "#013664",
            "border": "#1e4a6d",
            "accent": "#7aa6da",
            "accent_hover": "#5a8fca",
            "text_muted": "#969896",
            "success": "#b9ca4a",
            "error": "#d54e53",
            "warning": "#e7c547",
            "input_bg": "#001830",
            "button_bg": "#013664",
            "button_hover": "#024a88",
        },
        "Dreamweaver": {
            "name": "Dreamweaver",
            "type": "light",
            "background": "#ffffff",
            "foreground": "#000000",
            "secondary_bg": "#f5f5f5",
            "border": "#cccccc",
            "accent": "#0066cc",
            "accent_hover": "#0052a3",
            "text_muted": "#666666",
            "success": "#228b22",
            "error": "#cc0000",
            "warning": "#ff8c00",
            "input_bg": "#ffffff",
            "button_bg": "#e0e0e0",
            "button_hover": "#d0d0d0",
        }
    }
    
    def _add_to_prompt_history(self, text):
        if not hasattr(self, 'prompt_history'):
            self.prompt_history = []
        if not self.prompt_history or self.prompt_history[-1] != text:
            self.prompt_history.append(text)
        self.prompt_history_idx = len(self.prompt_history)

    def _navigate_prompt_history(self, delta, input_widget):
        if not hasattr(self, 'prompt_history') or not self.prompt_history:
            return
            
        new_idx = self.prompt_history_idx + delta
        if 0 <= new_idx < len(self.prompt_history):
            self.prompt_history_idx = new_idx
            input_widget.setPlainText(self.prompt_history[self.prompt_history_idx])
            cursor = input_widget.textCursor()
            cursor.movePosition(QTextCursor.End)
            input_widget.setTextCursor(cursor)
            input_widget.enter_history_mode()  # Allow continued scrolling
        elif new_idx == len(self.prompt_history):
            self.prompt_history_idx = new_idx
            input_widget.setPlainText("")
            input_widget.exit_history_mode()  # Back to normal editing


    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        # Outermost layout: [File Browser] | [Sidebar + Main Content]
        outer_layout = QHBoxLayout(central_widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # --- Outer horizontal splitter ---
        self.outer_splitter = QSplitter(Qt.Horizontal)

        # === LEFT PANEL: File Browser ===
        self._init_file_browser()
        self.outer_splitter.addWidget(self.file_browser_widget)

        # === RIGHT PANEL: Sidebar + Main Content ===
        right_panel = QWidget()
        main_layout = QHBoxLayout(right_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ---- Sidebar (History) ----
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        
        self.history_list = QListWidget()
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.setToolTip("Right-click to delete individual threads")
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        self.history_list.itemClicked.connect(self.load_history_conversation)
        sidebar_layout.addWidget(QLabel("History"))
        sidebar_layout.addWidget(self.history_list)
        
        self.clear_history_btn = QPushButton("Clear All History")
        self.clear_history_btn.clicked.connect(self.clear_history)
        self.clear_history_btn.setStyleSheet("background-color: #fce4ec; color: #c2185b;")
        sidebar_layout.addWidget(self.clear_history_btn)
        
        # --- Model Selection (Global) ---
        model_group = QWidget()
        model_group_layout = QVBoxLayout(model_group)
        model_group_layout.setContentsMargins(0, 5, 0, 5)
        
        model_header = QHBoxLayout()
        model_header.addWidget(QLabel("Active Model:"))
        
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Refresh list of available models")
        self.refresh_btn.clicked.connect(self._refresh_models)
        model_header.addWidget(self.refresh_btn)
        
        model_group_layout.addLayout(model_header)
        
        self.model_combo = QComboBox()
        self.model_combo.currentTextChanged.connect(self.on_model_changed)
        model_group_layout.addWidget(self.model_combo)
        
        sidebar_layout.addWidget(model_group)
        # --------------------------------
        
        new_chat_btn = QPushButton("New Chat")
        new_chat_btn.clicked.connect(self.start_new_chat)
        sidebar_layout.addWidget(new_chat_btn)
        
        refresh_btn = QPushButton("Refresh History")
        refresh_btn.clicked.connect(self.refresh_history)
        sidebar_layout.addWidget(refresh_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.open_settings)
        sidebar_layout.addWidget(settings_btn)
        
        # Theme Toggle Button
        self.theme_btn = QPushButton("🎨 Dreamweaver")
        self.theme_btn.clicked.connect(self.toggle_theme)
        sidebar_layout.addWidget(self.theme_btn)

        main_layout.addWidget(sidebar)

        # ---- Main Content Area (Splitter for Tabs + Console) ----
        self.main_content_splitter = QSplitter(Qt.Vertical)
        
        # Tab Widget
        self.tabs = QTabWidget()
        
        # Chat Tab
        self.chat_tab = QWidget()
        self._init_chat_tab()
        self.tabs.addTab(self.chat_tab, "💬 Chat")
        
        # Agent Tab
        self.agent_tab = QWidget()
        self._init_agent_tab()
        self.tabs.addTab(self.agent_tab, "🤖 Agent Mode")

        # Editor Tab
        self.editor_tab = QWidget()
        self._init_editor_tab()
        self.tabs.addTab(self.editor_tab, "📝 Editor")
        
        self.main_content_splitter.addWidget(self.tabs)
        
        # Global Console
        self.console_display = QTextEdit()
        self.console_display.setReadOnly(True)
        self.console_display.setPlaceholderText("Debug Console Log...")
        self.console_display.setStyleSheet("background-color: #2b2b2b; color: #00ff00; font-family: monospace;")
        self.console_display.hide()
        self.main_content_splitter.addWidget(self.console_display)
        self.main_content_splitter.setSizes([600, 150])

        main_layout.addWidget(self.main_content_splitter)

        self.outer_splitter.addWidget(right_panel)
        self.outer_splitter.setSizes([220, 980])
        outer_layout.addWidget(self.outer_splitter)
        
        self.refresh_history()

    # ------------------------------------------------------------------
    #  File Browser
    # ------------------------------------------------------------------
    def _init_file_browser(self):
        """Create the file browser panel with a QTreeView."""
        self.file_browser_widget = QWidget()
        fb_layout = QVBoxLayout(self.file_browser_widget)
        fb_layout.setContentsMargins(2, 2, 2, 2)
        fb_layout.setSpacing(2)

        # Header with label and Open Folder button
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("📁 Files"))
        open_folder_btn = QPushButton("Open...")
        open_folder_btn.setFixedHeight(24)
        open_folder_btn.setToolTip("Choose a folder to browse")
        open_folder_btn.clicked.connect(self._choose_browser_root)
        header_layout.addWidget(open_folder_btn)
        fb_layout.addLayout(header_layout)

        # File system model
        self.fs_model = QFileSystemModel()
        self.fs_model.setReadOnly(True)
        workspace = self.config.get_workspace_path() if hasattr(self, 'config') else os.getcwd()
        if not workspace or not os.path.isdir(workspace):
            workspace = os.getcwd()
        root_index = self.fs_model.setRootPath(workspace)

        # Tree view
        self.file_tree = QTreeView()
        self.file_tree.setModel(self.fs_model)
        self.file_tree.setRootIndex(root_index)
        self.file_tree.setAnimated(False)
        self.file_tree.setIndentation(14)
        self.file_tree.setSortingEnabled(True)
        self.file_tree.sortByColumn(0, Qt.AscendingOrder)
        self.file_tree.setDragEnabled(True)
        self.file_tree.setAcceptDrops(False)
        # Hide Size, Type, Date columns – keep only Name
        self.file_tree.hideColumn(1)
        self.file_tree.hideColumn(2)
        self.file_tree.hideColumn(3)
        self.file_tree.header().hide()
        self.file_tree.doubleClicked.connect(self.on_file_double_clicked)
        fb_layout.addWidget(self.file_tree)

    def _choose_browser_root(self):
        """Let user pick a folder and update the file browser root."""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Folder to Browse")
        if dir_path:
            self._update_file_browser_root(dir_path)

    def _update_file_browser_root(self, path: str):
        """Update the file tree root to the given directory path."""
        if os.path.isdir(path):
            new_root = self.fs_model.setRootPath(path)
            self.file_tree.setRootIndex(new_root)

    def on_file_double_clicked(self, index):
        """Open the double-clicked file in the Editor tab, or with system default for binary files."""
        file_path = self.fs_model.filePath(index)
        if not os.path.isfile(file_path):
            return  # Ignore directory double-click (expand/collapse)

        # Text-based files supported by the built-in editor
        TEXT_EXTENSIONS = {
            '.py', '.txt', '.md', '.yaml', '.yml', '.json', '.toml',
            '.cfg', '.ini', '.sh', '.bat', '.csv', '.html', '.htm', '.css',
            '.js', '.ts', '.xml', '.rst', '.env', '.log',
        }
        # Extensions that support a rendered preview
        RENDERABLE_EXTENSIONS = {'.md', '.html', '.htm'}

        _, ext = os.path.splitext(file_path)
        ext_lower = ext.lower()

        if ext_lower not in TEXT_EXTENSIONS:
            # Open binary / non-text files with the system default application
            self._open_file_with_system(file_path)
            return

        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Error Opening File", str(e))
            return

        self._current_editor_file = file_path
        self.editor_file_label.setText(file_path)
        self.editor_edit.setPlainText(content)

        # Show/hide Render Preview checkbox for .md/.html files
        self.render_checkbox.setChecked(False)
        self.render_checkbox.setVisible(ext_lower in RENDERABLE_EXTENSIONS)

        # Ensure we show the text editor (not the preview browser)
        self.editor_edit.setVisible(True)
        self.editor_preview.setVisible(False)

        # Update syntax highlighter for the new file type
        if self._editor_highlighter is not None:
            self._editor_highlighter.set_filename(file_path)
            # Update language indicator in toolbar
            from pygments.lexers import get_lexer_for_filename
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_for_filename(file_path)
                self.editor_lang_label.setText(f"\u2b22 {lexer.name}")
            except (ClassNotFound, Exception):
                self.editor_lang_label.setText("")

        # Switch to Editor tab (index 2)
        self.tabs.setCurrentIndex(2)
        self.append_log(f"Opened file: {file_path}")

    def _open_file_with_system(self, file_path):
        """Open a file with the operating system's default application (cross-platform)."""
        try:
            system = platform.system()
            if system == "Darwin":
                subprocess.Popen(["open", file_path])
            elif system == "Windows":
                os.startfile(file_path)
            else:  # Linux and other Unix-like
                subprocess.Popen(["xdg-open", file_path])
            self.append_log(f"Opened '{os.path.basename(file_path)}' with system default app.")
        except Exception as e:
            QMessageBox.critical(self, "Error Opening File",
                f"Could not open file with system application:\n{e}")

    # ------------------------------------------------------------------
    #  Editor Tab
    # ------------------------------------------------------------------
    def _init_editor_tab(self):
        """Create the text editor tab with syntax highlighting and optional render preview."""
        self._current_editor_file = None
        self._editor_highlighter = None
        layout = QVBoxLayout(self.editor_tab)

        # Toolbar row
        toolbar = QHBoxLayout()
        save_btn = QPushButton("\U0001f4be Save")
        save_btn.setFixedHeight(28)
        save_btn.setToolTip("Save file")
        save_btn.clicked.connect(self.save_current_file)
        toolbar.addWidget(save_btn)

        save_as_btn = QPushButton("Save As...")
        save_as_btn.setFixedHeight(28)
        save_as_btn.clicked.connect(self.save_current_file_as)
        toolbar.addWidget(save_as_btn)

        toolbar.addStretch()

        # Render Preview checkbox (hidden by default, visible only for .md/.html)
        from PySide6.QtWidgets import QCheckBox
        self.render_checkbox = QCheckBox("Render Preview")
        self.render_checkbox.setVisible(False)
        self.render_checkbox.toggled.connect(self._toggle_render_preview)
        toolbar.addWidget(self.render_checkbox)

        # Language indicator label
        self.editor_lang_label = QLabel("")
        self.editor_lang_label.setStyleSheet("color: #a6e22e; font-size: 10px; padding-right: 6px;")
        toolbar.addWidget(self.editor_lang_label)

        layout.addLayout(toolbar)

        # Current file path label
        self.editor_file_label = QLabel("No file open")
        self.editor_file_label.setStyleSheet("color: #75715e; font-size: 10px;")
        layout.addWidget(self.editor_file_label)

        # Text editor — dark background, monospace font
        self.editor_edit = QPlainTextEdit()
        self.editor_edit.setPlaceholderText(
            "Double-click a file in the browser on the left to open it here..."
        )
        self.editor_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.editor_edit.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #1e1e1e;"
            "  color: #f8f8f2;"
            "  selection-background-color: #49483e;"
            "}"
        )
        from PySide6.QtGui import QFont
        mono = QFont("Courier New", 10)
        mono.setStyleHint(QFont.Monospace)
        self.editor_edit.setFont(mono)

        # Attach highlighter (starts with no file → no-op)
        self._editor_highlighter = PygmentsSyntaxHighlighter(
            self.editor_edit.document(), filename=""
        )
        layout.addWidget(self.editor_edit)

        # Render Preview browser (hidden by default, shown when checkbox is toggled)
        self.editor_preview = QTextBrowser()
        self.editor_preview.setReadOnly(True)
        self.editor_preview.setOpenExternalLinks(True)
        self.editor_preview.setVisible(False)
        layout.addWidget(self.editor_preview)

    def _toggle_render_preview(self, checked):
        """Toggle between raw text editor and rendered preview for .md/.html files."""
        if checked and self._current_editor_file:
            _, ext = os.path.splitext(self._current_editor_file)
            raw_text = self.editor_edit.toPlainText()

            if ext.lower() == '.md':
                rendered_html = markdown.markdown(raw_text, extensions=['extra', 'nl2br'])
            elif ext.lower() in ('.html', '.htm'):
                rendered_html = raw_text  # HTML is already renderable
            else:
                rendered_html = f"<pre>{raw_text}</pre>"

            self.editor_preview.setHtml(rendered_html)
            self.editor_edit.setVisible(False)
            self.editor_preview.setVisible(True)
        else:
            self.editor_edit.setVisible(True)
            self.editor_preview.setVisible(False)

    def save_current_file(self):
        """Save editor content to the currently open file."""
        if not self._current_editor_file:
            self.save_current_file_as()
            return
        try:
            with open(self._current_editor_file, 'w', encoding='utf-8') as f:
                f.write(self.editor_edit.toPlainText())
            self.statusBar().showMessage(
                f"Saved: {self._current_editor_file}", 3000
            )
            self.append_log(f"File saved: {self._current_editor_file}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def save_current_file_as(self):
        """Save editor content to a new file chosen by the user."""
        path, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "All Files (*)")
        if path:
            self._current_editor_file = path
            self.editor_file_label.setText(path)
            self.save_current_file()

    def _init_chat_tab(self):
        layout = QVBoxLayout(self.chat_tab)
        
        # Controls
        controls_layout = QHBoxLayout()
        # Model controls moved to Sidebar
        
        save_btn = QPushButton("Save to File")
        save_btn.clicked.connect(self.save_to_file)
        controls_layout.addWidget(save_btn)
        
        load_btn = QPushButton("Load from File")
        load_btn.clicked.connect(self.load_from_file)
        controls_layout.addWidget(load_btn)

        # Chat Console Toggle
        self.toggle_console_chat_btn = QPushButton("Show Debug Console")
        self.toggle_console_chat_btn.setCheckable(True)
        self.toggle_console_chat_btn.toggled.connect(self.toggle_console)
        controls_layout.addWidget(self.toggle_console_chat_btn)
        
        layout.addLayout(controls_layout)
        
        # Chat Display
        self.chat_display = QTextBrowser()
        self.chat_display.setReadOnly(True)
        self.chat_display.setOpenExternalLinks(True)
        layout.addWidget(self.chat_display)
        
        # Input
        input_layout = QHBoxLayout()
        self.message_input = ChatInputWidget()
        self.message_input.workspace_path = getattr(self, 'current_workspace', "")
        self.message_input.send_requested.connect(self.send_message)
        self.message_input.history_up_requested.connect(lambda: self._navigate_prompt_history(-1, self.message_input))
        self.message_input.history_down_requested.connect(lambda: self._navigate_prompt_history(1, self.message_input))
        input_layout.addWidget(self.message_input)
        
        self.chat_send_btn = QPushButton("Send")
        self.chat_send_btn.setFixedSize(80, 80)
        self.chat_send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.chat_send_btn)
        
        self.chat_stop_btn = QPushButton("⬛ Stop")
        self.chat_stop_btn.setFixedSize(80, 80)
        self.chat_stop_btn.clicked.connect(self.stop_chat)
        self.chat_stop_btn.setEnabled(False)
        self.chat_stop_btn.setStyleSheet("QPushButton:enabled { background-color: #d32f2f; color: white; }")
        input_layout.addWidget(self.chat_stop_btn)
        
        layout.addLayout(input_layout)

    def _init_agent_tab(self):
        agent_layout = QVBoxLayout(self.agent_tab) # Renamed to avoid conflict with 'layout'
        
        # Config Area - Row 1: Name and Profile
        config_layout = QHBoxLayout()
        
        self.agent_name_input = QLineEdit()
        self.agent_name_input.setPlaceholderText("Agent Name")
        self.agent_name_input.setFixedWidth(150)
        config_layout.addWidget(self.agent_name_input)
        
        # Profile Selection
        config_layout.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.setMinimumWidth(200)
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        config_layout.addWidget(self.profile_combo)
        
        refresh_profiles_btn = QPushButton("↻")
        refresh_profiles_btn.setFixedSize(40, 32)
        refresh_profiles_btn.setToolTip("Refresh Profiles")
        refresh_profiles_btn.clicked.connect(self._load_agent_profiles)
        config_layout.addWidget(refresh_profiles_btn)
        
        open_folder_btn = QPushButton("📁")
        open_folder_btn.setFixedSize(40, 32)
        open_folder_btn.setToolTip("Open Profiles Folder")
        open_folder_btn.clicked.connect(self._open_profiles_folder)
        config_layout.addWidget(open_folder_btn)
        
        config_layout.addStretch()
        
        create_agent_btn = QPushButton("Create Assistant")
        create_agent_btn.clicked.connect(self.create_assistant)
        config_layout.addWidget(create_agent_btn)
        
        create_thread_btn = QPushButton("New Thread")
        create_thread_btn.clicked.connect(self.create_thread)
        config_layout.addWidget(create_thread_btn)

        agent_layout.addLayout(config_layout)
        
        # --- Consilium Mode Configuration ---
        self.consilium_layout = QHBoxLayout()
        self.consilium_layout.setContentsMargins(0, 5, 0, 5)
        
        from PySide6.QtWidgets import QCheckBox
        self.consilium_checkbox = QCheckBox("Consilium Mode")
        self.consilium_checkbox.toggled.connect(self._toggle_consilium_ui)
        self.consilium_layout.addWidget(self.consilium_checkbox)
        
        self.consilium_controls = QWidget()
        consilium_grid = QHBoxLayout(self.consilium_controls)
        consilium_grid.setContentsMargins(0, 0, 0, 0)
        
        consilium_grid.addWidget(QLabel("Executor:"))
        self.consilium_executor_combo = QComboBox()
        consilium_grid.addWidget(self.consilium_executor_combo)
        
        consilium_grid.addWidget(QLabel("Reviewer:"))
        self.consilium_reviewer_combo = QComboBox()
        consilium_grid.addWidget(self.consilium_reviewer_combo)
        
        consilium_grid.addWidget(QLabel("Skeptic:"))
        self.consilium_skeptic_combo = QComboBox()
        consilium_grid.addWidget(self.consilium_skeptic_combo)
        
        # We will populate these comboboxes in _refresh_models
        
        self.consilium_controls.setVisible(False)
        self.consilium_layout.addWidget(self.consilium_controls)
        self.consilium_layout.addStretch()
        
        agent_layout.addLayout(self.consilium_layout)
        # ------------------------------------
        
        # Load profiles on init
        self.agent_profiles = {}  # {name: {description, instructions}}
        self.current_profile_instructions = ""
        self._load_agent_profiles()

        # Agent Chat Display
        self.agent_display = QTextBrowser()
        self.agent_display.setReadOnly(True)
        self.agent_display.setOpenExternalLinks(False)
        self.agent_display.setOpenLinks(False)
        self.agent_display.anchorClicked.connect(self._handle_link_click)
        agent_layout.addWidget(self.agent_display)

        # Agent Console Toggle
        self.toggle_console_agent_btn = QPushButton("Show Debug Console")
        self.toggle_console_agent_btn.setCheckable(True)
        self.toggle_console_agent_btn.toggled.connect(self.toggle_console)
        config_layout.addWidget(self.toggle_console_agent_btn)
        
        # Status Area
        status_layout = QHBoxLayout()
        self.agent_status_label = QLabel("Status: Idle")
        workspace_path = self.config.get_workspace_path()
        self.workspace_label = QLabel(f"Workspace: {workspace_path}")
        self.workspace_label.setStyleSheet("color: gray; font-size: 10px;")
        
        status_layout.addWidget(self.agent_status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.workspace_label)
        
        agent_layout.addLayout(status_layout)
        
        # Input Area
        input_layout = QHBoxLayout()
        self.agent_input = ChatInputWidget()
        self.agent_input.workspace_path = getattr(self, 'current_workspace', "")
        self.agent_input.send_requested.connect(self.send_to_agent)
        self.agent_input.history_up_requested.connect(lambda: self._navigate_prompt_history(-1, self.agent_input))
        self.agent_input.history_down_requested.connect(lambda: self._navigate_prompt_history(1, self.agent_input))
        input_layout.addWidget(self.agent_input)
        
        self.agent_send_btn = QPushButton("Send to Agent")
        self.agent_send_btn.setFixedSize(120, 80)
        self.agent_send_btn.clicked.connect(self.send_to_agent)
        input_layout.addWidget(self.agent_send_btn)
        
        self.agent_stop_btn = QPushButton("⬛ Stop")
        self.agent_stop_btn.setFixedSize(80, 80)
        self.agent_stop_btn.clicked.connect(self.stop_agent)
        self.agent_stop_btn.setEnabled(False)
        self.agent_stop_btn.setStyleSheet("QPushButton:enabled { background-color: #d32f2f; color: white; }")
        input_layout.addWidget(self.agent_stop_btn)
        
        agent_layout.addLayout(input_layout)

    def _toggle_consilium_ui(self, checked):
        self.consilium_controls.setVisible(checked)
        if checked:
            self.statusBar().showMessage("Consilium Mode activated. Click 'Create Assistant' to re-initialize.", 5000)
        else:
            self.statusBar().showMessage("Solo Mode activated. Click 'Create Assistant' to re-initialize.", 5000)

    def _refresh_models(self):
        """
        Refresh available models from API.
        Fully dynamic - adapts to any changes in API model offerings.
        """
        if self.api.is_configured():
            self.model_combo.blockSignals(True) # Prevent triggering change reset during update
            
            try:
                # 1. Fetch available models from API (single source of truth)
                fetched_models = self.api.list_models()
                
                # 2. Optional: Filter out known problematic models
                KNOWN_BAD_MODELS = []  # Empty for now - add model IDs here if needed
                
                final_models = [m for m in fetched_models if m not in KNOWN_BAD_MODELS]
                
                # Check if we got any models
                if not final_models:
                    raise ValueError("No models available from API")
                
                # 3. Update UI with fetched models
                self.model_combo.clear()
                self.model_combo.addItems(final_models)
                
                # Consilium Combos
                for combo in [self.consilium_executor_combo, self.consilium_reviewer_combo, self.consilium_skeptic_combo]:
                    if hasattr(self, 'consilium_executor_combo'): # Check if initialized
                        combo.clear()
                        combo.addItems(final_models)
                
                # 4. Smart model selection with fallback
                saved_model = self.config.get("model")
                selected_model = None
                
                if saved_model and saved_model in final_models:
                    # Saved model is available - restore it
                    index = self.model_combo.findText(saved_model)
                    if index >= 0:
                        self.model_combo.setCurrentIndex(index)
                        selected_model = saved_model
                        self.append_log(f"✓ Restored model: {saved_model}")
                else:
                    # Saved model not available - use smart fallback
                    if saved_model:
                        self.append_log(f"⚠ Saved model '{saved_model}' no longer available")
                    
                    # Preferred fallback order
                    PREFERRED_MODELS = ["bielik_11b", "DeepSeek-V3.1-vLLM"]
                    
                    for preferred in PREFERRED_MODELS:
                        if preferred in final_models:
                            index = self.model_combo.findText(preferred)
                            if index >= 0:
                                self.model_combo.setCurrentIndex(index)
                                selected_model = preferred
                                self.append_log(f"→ Selected fallback model: {preferred}")
                                break
                    
                    # If no preferred model found, use first available
                    if not selected_model and len(final_models) > 0:
                        self.model_combo.setCurrentIndex(0)
                        selected_model = final_models[0]
                        self.append_log(f"→ Selected first available model: {selected_model}")
                    
                    # Save the new selection
                    if selected_model:
                        self.config.set("model", selected_model)
                
                # Default Consilium selections if available
                def _set_consilium_default(combo, preferred):
                    idx = combo.findText(preferred)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    elif combo.count() > 0:
                        combo.setCurrentIndex(0)
                        
                if hasattr(self, 'consilium_executor_combo'):
                    _set_consilium_default(self.consilium_executor_combo, "Qwen3.5-397B-A17B")
                    _set_consilium_default(self.consilium_reviewer_combo, "DeepSeek-V3.1-vLLM")
                    _set_consilium_default(self.consilium_skeptic_combo, "GLM-4.7")
                
                # 5. Success feedback
                current_model = self.model_combo.currentText()
                self.statusBar().showMessage(
                    f"Models refreshed ({len(final_models)} available) - Using: {current_model}", 
                    3000
                )
                
            except Exception as e:
                # Handle API errors gracefully
                self.append_log(f"❌ Model refresh failed: {str(e)}")
                
                # Emergency fallback - populate with common models
                self.model_combo.clear()
                emergency_models = ["bielik_11b", "DeepSeek-V3.1-vLLM"]
                self.model_combo.addItems(emergency_models)
                self.model_combo.setCurrentIndex(0)
                
                # Show error to user
                err_msg = f"Model refresh failed: {str(e)}"
                self.statusBar().showMessage(err_msg, 10000)
                
            finally:
                self.model_combo.blockSignals(False)

    def on_model_changed(self, text):
        if not text:
            return
            
        # Save selected model to config
        self.config.set("model", text)
        self.append_log(f"Model changed to: {text}")
        
        # Update status bar with current model
        self.statusBar().showMessage(f"Using model: {text}", 5000)
        
        # Reset Chat
        self.start_new_chat()
        
        # Reset Agent
        self.agent_history = []
        self.current_agent_conversation_id = None
        self.agent_display.clear()
        self.agent_display.append(f"<b>System:</b> Model changed to {text}. Please re-initialize Assistant.<br>")
        self.agent_engine = None # Force re-creation with new model
        self.agent_status_label.setText("Model Changed")

    def open_settings(self):
        # Get current models from main combo
        current_models = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]
        
        # Capture current workspace before dialog to detect changes
        old_workspace = self.config.get_workspace_path()
        
        dlg = SettingsDialog(self.config, self, available_models=current_models)
        if dlg.exec():
            # Re-initialize API client
            self.api = PcssApiClient(self.config)
            # Refresh models (this will also restore the saved selection)
            self._refresh_models()
            
            # Check if workspace changed
            new_workspace = self.config.get_workspace_path()
            if old_workspace != new_workspace:
                self.append_log(f"Workspace changed: {old_workspace} -> {new_workspace}. Re-initializing Assistant...")
                self.create_assistant()
                # Update file browser root to new workspace
                if hasattr(self, 'file_tree'):
                    self._update_file_browser_root(new_workspace)
            
            # Log the current selected model for user confirmation
            current_model = self.model_combo.currentText()
            self.append_log(f"Settings saved. Current model: {current_model}")

    def apply_theme(self, theme_name: str):
        """Apply a theme to the application."""
        if theme_name not in self.THEMES:
            theme_name = "Cobalt"
        
        theme = self.THEMES[theme_name]
        
        # Only set and save if the theme actually changed to avoid clobbering config on startup
        if self.current_theme != theme_name:
            self.current_theme = theme_name
            self.config.set("theme", theme_name)
        
        # Update theme toggle button text
        if hasattr(self, 'theme_btn'):
            other_theme = "Dreamweaver" if theme_name == "Cobalt" else "Cobalt"
            self.theme_btn.setText(f"🎨 {other_theme}")
        
        # Build comprehensive stylesheet
        stylesheet = f"""
            QMainWindow, QWidget {{
                background-color: {theme['background']};
                color: {theme['foreground']};
            }}
            QLabel {{
                color: {theme['foreground']};
            }}
            QTextEdit, QTextBrowser, QLineEdit {{
                background-color: {theme['input_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 4px;
                padding: 4px;
            }}
            QListWidget {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {theme['accent']};
                color: {theme['background']};
            }}
            QListWidget::item:hover {{
                background-color: {theme['accent_hover']};
            }}
            QPushButton {{
                background-color: {theme['button_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 4px;
                padding: 6px 12px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {theme['button_hover']};
            }}
            QPushButton:pressed {{
                background-color: {theme['accent']};
            }}
            QPushButton:disabled {{
                background-color: {theme['secondary_bg']};
                color: {theme['text_muted']};
            }}
            QComboBox {{
                background-color: {theme['button_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                selection-background-color: {theme['accent']};
            }}
            QTabWidget::pane {{
                border: 1px solid {theme['border']};
                background-color: {theme['background']};
            }}
            QTabBar::tab {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                padding: 8px 16px;
                border: 1px solid {theme['border']};
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {theme['accent']};
                color: {theme['background']};
            }}
            QMenuBar {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
            }}
            QMenuBar::item:selected {{
                background-color: {theme['accent']};
            }}
            QMenu {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
            }}
            QMenu::item:selected {{
                background-color: {theme['accent']};
            }}
            QScrollBar:vertical {{
                background-color: {theme['secondary_bg']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme['border']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme['accent']};
            }}
            /* Table Formatting */
            table {{
                border-collapse: collapse;
                margin: 10px 0;
                border: 1px solid {theme['border']};
            }}
            th {{
                background-color: {theme['secondary_bg']};
                color: {theme['accent']};
                font-weight: bold;
                padding: 6px;
                border: 1px solid {theme['border']};
            }}
            td {{
                padding: 6px;
                border: 1px solid {theme['border']};
                color: {theme['foreground']};
            }}
        """
        
        self.setStyleSheet(stylesheet)
    
    def toggle_theme(self):
        """Toggle between Cobalt and Dreamweaver themes."""
        new_theme = "Dreamweaver" if self.current_theme == "Cobalt" else "Cobalt"
        self.apply_theme(new_theme)

    def start_new_chat(self):
        self.current_conversation_id = None
        self.chat_history = []
        self.chat_display.clear()
        self.model_combo.setEnabled(True)

    def append_log(self, message: str):
        self.log_buffer.append(message)
        
        # Log to file in the APPLICATION directory (not workspace)
        try:
            app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            log_path = os.path.join(app_dir, "agent_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def send_message(self):
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        self._add_to_prompt_history(text)

        model = self.model_combo.currentText()
        # print(f"DEBUG: Sending message with model: {model}")
        if not self.current_conversation_id:
            title = text[:30] + "..."
            self.current_conversation_id = self.db.create_conversation(title, model, mode="chat")
            self.refresh_history()

        self._append_message("User", text)
        self.message_input.clear()
        
        self.chat_history.append({"role": "user", "content": text})
        self.db.add_message(self.current_conversation_id, "user", text)

        self.chat_worker = ChatWorker(self.api, model, self.chat_history)
        self.chat_worker.finished.connect(self.handle_response)
        self.chat_worker.error.connect(self.handle_error)
        self.chat_worker.cancelled.connect(self.handle_chat_cancelled)
        self.chat_worker.log_message.connect(self.append_log)
        self.chat_worker.start()
        
        # UI state: disable input, enable Stop
        self.message_input.setReadOnly(True)
        self.chat_send_btn.setEnabled(False)
        self.chat_stop_btn.setEnabled(True)

    def handle_response(self, content):
        self._append_message("AI", content)
        self.chat_history.append({"role": "assistant", "content": content})
        self.db.add_message(self.current_conversation_id, "assistant", content)
        self._reset_chat_ui()

    def handle_error(self, err_msg):
        QMessageBox.critical(self, "API Error", err_msg)
        self._reset_chat_ui()

    def handle_chat_cancelled(self):
        """Handle chat worker cancellation."""
        self._append_message("System", "⚠️ Request cancelled by user.")
        self._reset_chat_ui()
    
    def stop_chat(self):
        """Stop the current chat request."""
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.cancel()
            self.append_log("User cancelled chat request. Waiting for background task to complete...")
            self._append_message("System", "⚠️ Cancellation requested, halting background process...")
            self.chat_stop_btn.setEnabled(False)
            # We don't forcibly kill it anymore. The worker will exit smoothly or block on TCP logic.
    
    def _reset_chat_ui(self):
        """Reset chat UI after response/error/cancel."""
        self.message_input.setReadOnly(False)
        self.message_input.restore_cursor_blink()  # Fix Qt cursor blink death
        self.chat_send_btn.setEnabled(True)
        self.chat_stop_btn.setEnabled(False)
        self.message_input.setFocus()
        if getattr(self, 'chat_worker', None):
            self.chat_worker.deleteLater()
            self.chat_worker = None

    def _append_message(self, role, text):
        html = markdown.markdown(text, extensions=['extra', 'nl2br'])
        self.chat_display.append(f"<b>{role}:</b> {html}<br>")
        
        # Auto scroll
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat_display.setTextCursor(cursor)

    # --- Agent Profile Methods ---
    def _load_agent_profiles(self):
        """Load agent profiles from agent_profiles/ directory"""
        profiles_dir = os.path.join(os.path.dirname(__file__), "..", "agent_profiles")
        profiles_dir = os.path.abspath(profiles_dir)
        
        self.agent_profiles = {}
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        
        # Add "No Profile" option
        self.profile_combo.addItem("(No Profile)")
        self.agent_profiles["(No Profile)"] = {"description": "No custom instructions", "instructions": ""}
        
        if os.path.exists(profiles_dir):
            for yaml_file in glob.glob(os.path.join(profiles_dir, "*.yaml")):
                try:
                    with open(yaml_file, 'r', encoding='utf-8') as f:
                        profile = yaml.safe_load(f)
                        if profile and 'name' in profile:
                            name = profile['name']
                            self.agent_profiles[name] = {
                                'description': profile.get('description', ''),
                                'instructions': profile.get('instructions', '')
                            }
                            self.profile_combo.addItem(name)
                except Exception as e:
                    # print(f"Error loading profile {yaml_file}: {e}")
                    pass
        
        self.profile_combo.blockSignals(False)
        
        # Select first real profile if available
        if self.profile_combo.count() > 1:
            self.profile_combo.setCurrentIndex(1)
    
    def _on_profile_changed(self, profile_name):
        """Handle profile selection change"""
        if profile_name in self.agent_profiles:
            profile = self.agent_profiles[profile_name]
            self.current_profile_instructions = profile.get('instructions', '')
            # Update tooltip with description
            self.profile_combo.setToolTip(profile.get('description', ''))
        else:
            self.current_profile_instructions = ""
    
    def _open_profiles_folder(self):
        """Open agent_profiles folder in file manager"""
        profiles_dir = os.path.join(os.path.dirname(__file__), "..", "agent_profiles")
        profiles_dir = os.path.abspath(profiles_dir)
        if os.path.exists(profiles_dir):
            os.system(f'open "{profiles_dir}"')  # macOS
        else:
            QMessageBox.warning(self, "Error", f"Profiles directory not found: {profiles_dir}")

    # --- Agent Mode Methods ---
    def _get_llm_profile_data(self, model_name):
        """Loads specific operational instructions and limits based on the selected LLM.
        
        Returns:
            tuple: (instructions, max_tokens, system_prompt_additions, context_window)
        """
        llm_profiles_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "llm_profiles"))
        if not os.path.exists(llm_profiles_dir):
            return "", 4096, "", 0
        try:
            return load_llm_profile(model_name, llm_profiles_dir)
        except Exception as e:
            self.append_log(f"Warning: Failed to load LLM profile: {e}")
            return "", 4096, "", 0

    def create_assistant(self, preserve_history=False):
        name = self.agent_name_input.text().strip()
        # Get instructions from selected profile
        instructions = self.current_profile_instructions
        
        # Inject Agent Name/Role into instructions if provided
        if name:
            name_header = f"Twoje imię/rola to: {name}.\n"
            instructions = name_header + (instructions or "")
            
        profile_name = self.profile_combo.currentText()
        
        # Create/Init Engine
        api_key = self.config.get_api_key()
        if not api_key:
            QMessageBox.warning(self, "Error", "API Key not set.")
            return

        workspace = self.config.get_workspace_path()
        model = self.model_combo.currentText()
        
        # Determine LLM-specific operational rules and limits
        llm_rules, max_tokens, system_prompt_additions, context_window = self._get_llm_profile_data(model)
        
        try:
            self.agent_status_label.setText("Initializing Agent...")
            # Fetch top-rated examples for this model
            top_examples = self.db.get_top_rated_interactions(model, limit=3)
            
            self.agent_status_label.setText("Agent Ready")
            if not preserve_history:
                self.agent_history = [] # Reset history only when not restoring
            
            is_consilium = hasattr(self, 'consilium_checkbox') and self.consilium_checkbox.isChecked()
            
            if is_consilium:
                # Initialize Consilium Orchestrator
                ex_model = self.consilium_executor_combo.currentText()
                rv_model = self.consilium_reviewer_combo.currentText()
                sk_model = self.consilium_skeptic_combo.currentText()
                
                self.agent_engine = ConsiliumOrchestrator(
                    api_key=api_key,
                    workspace_path=workspace,
                    executor_model=ex_model,
                    reviewer_model=rv_model,
                    skeptic_model=sk_model,
                    log_callback=self.agent_logger.log_message.emit,
                    executor_instructions=instructions,
                    base_url=self.config.get_base_url()
                )
                
                self.agent_display.append(f"<b>System:</b> 🏛️ Consilium '{name}' initialized.<br>")
                self.agent_display.append(f"<b>System:</b> Executor: {ex_model}<br>")
                self.agent_display.append(f"<b>System:</b> Reviewer: {rv_model}<br>")
                self.agent_display.append(f"<b>System:</b> Skeptic: {sk_model}<br>")
                
            else:
                # Initialize Standard Engine
                self.agent_engine = LangChainAgentEngine(
                    api_key, model, workspace, 
                    log_callback=self.agent_logger.log_message.emit,
                    custom_instructions=instructions,
                    llm_instructions=llm_rules,
                    few_shot_examples=top_examples,
                    max_tokens=max_tokens,
                    system_prompt_additions=system_prompt_additions,
                    context_window=context_window,
                    base_url=self.config.get_base_url(),
                    transcription_model=self.config.get("transcription_model", "whisper-large-v3-turbo:0.8b")
                )
                self.agent_display.append(f"<b>System:</b> Agent '{name}' initialized with profile: {profile_name}<br>")
                self.agent_display.append(f"<b>System:</b> Active LLM Model: {model} (Loaded operational rules)<br>")
                
            # Start new persistence session for Agent
            self.current_agent_conversation_id = None # Will be created on first message
            
            self.agent_display.append(f"<b>System:</b> Workspace: {workspace}<br>")
            self.agent_display.append(f"<b>System:</b> Tools: [Files, Documents, OCR, Vision, Web Search]<br>")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            self.agent_status_label.setText("Init Error")

    def create_thread(self):
        # In LangChain mode, "New Thread" just clears memory
        self.agent_history = []
        self.current_agent_conversation_id = None
        self.agent_display.clear()
        self.agent_display.append("<b>System:</b> Memory cleared. New Session.<br>")
        self.agent_status_label.setText("Ready")

    def send_to_agent(self):
        if not self.agent_engine:
            QMessageBox.warning(self, "Agent", "Please Initialize Agent first (Create Assistant button).")
            return

        text = self.agent_input.toPlainText().strip()
        if not text:
            return
            
        self._add_to_prompt_history(text)
            
        html = markdown.markdown(text, extensions=['extra', 'nl2br'])
        self.agent_display.append(f"<b>User:</b> {html}<br>")
        self.agent_input.clear()
        
        # Add to history
        # (LangChain agent handles history internally if passed? My engine run takes history)
        # We pass self.agent_history? 
        # Actually my engine implementation takes list of messages.
        # But AgentExecutor with chat_history handles it.
        # We need to maintain the list of (human, ai) tuples or BaseMessages.
        # Let's assume engine.run expects a list.
        
        # Persistence
        if not self.current_agent_conversation_id:
             model = self.model_combo.currentText()
             profile = self.profile_combo.currentText()
             title = f"Agent: {text[:20]}..."
             self.current_agent_conversation_id = self.db.create_conversation(title, model, mode="agent", agent_profile=profile)
             self.refresh_history()
        
        self.db.add_message(self.current_agent_conversation_id, "user", text)
        
        is_consilium = hasattr(self, 'consilium_checkbox') and self.consilium_checkbox.isChecked()
        
        if is_consilium and isinstance(self.agent_engine, ConsiliumOrchestrator):
            self.agent_worker = ConsiliumWorker(self.agent_engine, text, self.agent_history)
        else:
            self.agent_worker = AgentWorker(self.agent_engine, text, self.agent_history, self.current_agent_scratchpad)
            self.agent_worker.tool_action_requested.connect(self.prompt_tool_action)

        self.agent_status_label.setText("Processing...")
        self.agent_worker.status_update.connect(self.update_agent_status)
        self.agent_worker.chunk_received.connect(self.handle_agent_chunk)
        self.agent_worker.finished.connect(self.handle_agent_response)
        self.agent_worker.error.connect(self.handle_agent_error)
        self.agent_worker.cancelled.connect(self.handle_agent_cancelled)
        
        self.current_agent_stream = ""
        self._render_chat()
        
        # UI state: make input read-only (preserves cursor blink), enable Stop
        self.agent_input.setReadOnly(True)
        self.agent_send_btn.setEnabled(False)
        self.agent_stop_btn.setEnabled(True)
        self.agent_worker.start()

    def _handle_link_click(self, url):
        link = url.toString()
        if link.startswith("rate:"):
            parts = link.split(":")
            if len(parts) == 3:
                action = parts[1]
                msg_id = int(parts[2])
                rating = 1 if action == "up" else -1
                
                # Update DB
                self.db.update_message_rating(msg_id, rating)
                
                # Append to console log
                self.append_log(f"Message {msg_id} rated {action} ({rating}).")
        else:
            import webbrowser
            webbrowser.open(link)

    def _render_chat(self):
        # State tracking
        current_stream_text = getattr(self, 'current_agent_stream', "")
        worker_text = self.agent_worker.text if hasattr(self, 'agent_worker') and self.agent_worker else ""
        
        # Initialize scroll-related variables at top level of function scope
        scrollbar = self.agent_display.verticalScrollBar()
        saved_value = scrollbar.value()
        was_at_bottom = saved_value >= scrollbar.maximum() - 30
        is_streaming = bool(current_stream_text)

        # Optimization: Only re-render if something actually changed (history, user prompt, or stream)
        current_state_key = (len(self.agent_history), worker_text, current_stream_text)
        if hasattr(self, '_last_render_state_key') and self._last_render_state_key == current_state_key:
            return  # Nothing changed, skip expensive rendering

        # Cache historical messages parsing
        if not hasattr(self, '_cached_history_html') or getattr(self, '_cached_history_len', -1) != len(self.agent_history):
            html_parts = []
            for msg in self.agent_history:
                m_html = markdown.markdown(msg.content, extensions=['extra', 'nl2br'])
                role = "User" if isinstance(msg, HumanMessage) else "Agent"
                html_parts.append(f"<b>{role}:</b> {m_html}<br>")
            self._cached_history_html = html_parts
            self._cached_history_len = len(self.agent_history)
            
        html_parts = list(self._cached_history_html)
            
        if hasattr(self, 'agent_worker') and self.agent_worker:
            # Cache user prompt
            if not hasattr(self, '_cached_user_prompt_html') or getattr(self, '_cached_user_prompt_text', "") != worker_text:
                self._cached_user_prompt_html = markdown.markdown(worker_text, extensions=['extra', 'nl2br'])
                self._cached_user_prompt_text = worker_text
            html_parts.append(f"<b>User:</b> {self._cached_user_prompt_html}<br>")
            
        if current_stream_text:
            # Cache currently streaming chunk
            if not hasattr(self, '_cached_stream_html') or getattr(self, '_cached_stream_text', "") != current_stream_text:
                self._cached_stream_html = markdown.markdown(current_stream_text, extensions=['extra', 'nl2br'])
                self._cached_stream_text = current_stream_text
            html_parts.append(f"<b>Agent:</b> {self._cached_stream_html}<br>")
            
        self.agent_display.setUpdatesEnabled(False)
        self.agent_display.setHtml("".join(html_parts))
        
        # Store state to prevent redundant renders
        self._last_render_state_key = current_state_key

        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        self.agent_display.document().adjustSize()
        
        # Re-apply scroll position
        if is_streaming or was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(saved_value)
            
        self.agent_display.setUpdatesEnabled(True)

    def update_agent_status(self, status):
        self.agent_status_label.setText(status)

    def handle_agent_chunk(self, chunk):
        self.current_agent_stream += chunk
        self.chat_needs_render = True

    def _throttled_ui_update(self):
        # Update logs
        if self.log_buffer:
            messages = "\n".join(self.log_buffer)
            self.log_buffer.clear()
            self.console_display.append(messages)
            
            # Auto scroll
            cursor = self.console_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.console_display.setTextCursor(cursor)
            
        # Update chat
        if self.chat_needs_render:
            self.chat_needs_render = False
            self._render_chat()

    def prompt_tool_action(self, action_obj):
        args = action_obj.args
        if action_obj.action == "create_file":
            msg = f"Agent wants to CREATE a file:\n\n{args.get('file_path')}\n\nAllow this action?"
        elif action_obj.action == "edit_file":
            msg = f"Agent wants to EDIT a file:\n\n{args.get('file_path')}\n\nAllow this action?"
        else:
            msg = f"Agent wants to perform action '{action_obj.action}'\n\nAllow this action?"
            
        reply = QMessageBox.question(self, "Tool Action Permission", msg,
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                                     
        if reply == QMessageBox.Yes:
            action_obj.approved = True
        else:
            action_obj.approved = False
            
        action_obj.event.set()

    def handle_agent_response(self, content):
        # Update scratchpad state
        if self.agent_engine:
            self.current_agent_scratchpad = getattr(self.agent_engine, 'active_scratchpad', "")
            if self.current_agent_conversation_id:
                self.db.update_conversation_scratchpad(self.current_agent_conversation_id, self.current_agent_scratchpad)

        # Persist Agent Response to get msg_id first
        msg_id = None
        if self.current_agent_conversation_id:
            try:
                msg_id = self.db.add_message(self.current_agent_conversation_id, "assistant", content)
            except Exception as e:
                self.append_log(f"⚠️ Error saving message to DB: {str(e)}")

        # Update history
        if self.agent_worker:
            input_text = self.agent_worker.text
            self.agent_history.append(HumanMessage(content=input_text))
            
            display_content = content
            if msg_id is not None:
                display_content += f"\n\n<br><a href='rate:up:{msg_id}'>👍</a> <a href='rate:down:{msg_id}'>👎</a>"
            
            self.agent_history.append(AIMessage(content=display_content))
        
        self.current_agent_stream = ""
        self._render_chat()
        
        self._reset_agent_ui()

    def toggle_console(self, checked):
        # Sync buttons
        self.toggle_console_chat_btn.blockSignals(True)
        self.toggle_console_agent_btn.blockSignals(True)
        
        self.toggle_console_chat_btn.setChecked(checked)
        self.toggle_console_agent_btn.setChecked(checked)
        
        text = "Hide Debug Console" if checked else "Show Debug Console"
        self.toggle_console_chat_btn.setText(text)
        self.toggle_console_agent_btn.setText(text)
        
        self.toggle_console_chat_btn.blockSignals(False)
        self.toggle_console_agent_btn.blockSignals(False)

        if checked:
            self.console_display.show()
        else:
            self.console_display.hide()

    def handle_agent_error(self, err):
        # Even on error, save the current scratchpad to allow "continue" attempts
        if self.agent_engine and self.current_agent_conversation_id:
            self.current_agent_scratchpad = getattr(self.agent_engine, 'active_scratchpad', "")
            self.db.update_conversation_scratchpad(self.current_agent_conversation_id, self.current_agent_scratchpad)

        QMessageBox.critical(self, "Agent Error", err)
        self.agent_status_label.setText("Error")
        self._reset_agent_ui()

    def handle_agent_cancelled(self):
        """Handle agent worker cancellation."""
        self.agent_display.append("<b>System:</b> ⚠️ Agent task cancelled by user.<br>")
        self._reset_agent_ui()
    
    def stop_agent(self):
        """Stop the current agent task."""
        if self.agent_worker and self.agent_worker.isRunning():
            self.agent_worker.cancel()
            self.append_log("User cancelled agent task. Waiting for background task to complete...")
            self.agent_display.append("<b>System:</b> ⚠️ Agent cancellation requested, halting background process...<br>")
            self.agent_status_label.setText("Stopping...")
            self.agent_stop_btn.setEnabled(False)
            # Smooth shutdown instead of terminate()
            # Waiting for handle_agent_cancelled signal
    
    def _reset_agent_ui(self):
        """Reset agent UI after response/error/cancel."""
        self.agent_status_label.setText("Ready")
        self.agent_input.setReadOnly(False)
        self.agent_send_btn.setEnabled(True)
        self.agent_stop_btn.setEnabled(False)
        self.agent_input.setFocus()
        self.agent_input.restore_cursor_blink()  # Fix Qt cursor blink death
        if getattr(self, 'agent_worker', None):
            self.agent_worker.deleteLater()
            self.agent_worker = None

    # --- Common Methods ---
    def refresh_history(self):
        self.history_list.clear()
        rows = self.db.get_conversations()
        for r in rows:
            item_text = f"{r[1]} ({r[2]})"
            self.history_list.addItem(item_text)
            self.history_list.item(self.history_list.count()-1).setData(Qt.UserRole, r[0])

    def load_history_conversation(self, item):
        conv_id = item.data(Qt.UserRole)
        
        # Check conversation mode
        conv_info = self.db.get_conversation(conv_id)
        if not conv_info:
            return
            
        mode = conv_info[4] if len(conv_info) > 4 else "chat"
        saved_model = conv_info[3] if len(conv_info) > 3 else ""
        saved_profile = conv_info[5] if len(conv_info) > 5 else ""
        
        messages = self.db.get_messages(conv_id)
        
        # Restore Model selection globally
        if saved_model:
            self.model_combo.setCurrentText(saved_model)

        if mode == "agent":
            # Switch to Agent Tab
            self.tabs.setCurrentIndex(1)
            
            # Restore Profile selection
            if saved_profile:
                self.profile_combo.setCurrentText(saved_profile)
            
            self.current_agent_conversation_id = conv_id
            self.current_agent_scratchpad = conv_info[6] if len(conv_info) > 6 else "" # Load scratchpad (index 6 now)
            self.agent_display.clear()
            self.agent_history = []
            
            # Using robust message types from top-level imports
            try:
                from langchain_core.messages import HumanMessage, AIMessage
            except ImportError:
                try:
                    from langchain.schema import HumanMessage, AIMessage
                except ImportError:
                    # Top-level fallback classes already defined if needed
                    pass
            
            for msg_id, role, content, timestamp, rating in messages:
                if role == "user":
                    self.agent_history.append(HumanMessage(content=content))
                elif role == "assistant":
                    self.agent_history.append(AIMessage(content=content))
            
            # Auto-initialize Agent if engine is missing or model/profile changed
            # This ensures tools and context are ready for "continue" keywords
            should_init = not self.agent_engine or \
                          self.agent_engine.model_name != saved_model or \
                          self.profile_combo.currentText() != saved_profile

            if should_init:
                self.append_log(f"🔄 Auto-initializing Agent for conversation {conv_id}...")
                # Preserve loaded history during re-initialization
                self.create_assistant(preserve_history=True)
                    
            # Force cache invalidation before rendering loaded history
            self._last_render_state_key = None
            self._cached_history_len = -1
            self._render_chat()
            
        else:
            # Switch to standard Chat Tab
            self.tabs.setCurrentIndex(0)
            self.current_conversation_id = conv_id
            self.chat_display.clear()
            self.chat_history = []
            
            for msg_id, role, content, timestamp, rating in messages:
                self._append_message("AI" if role == "assistant" else "User", content)
                self.chat_history.append({"role": role, "content": content})

    def show_history_context_menu(self, position):
        item = self.history_list.itemAt(position)
        if not item:
            return
            
        menu = QMenu()
        delete_action = menu.addAction("Delete Conversation")
        action = menu.exec(self.history_list.mapToGlobal(position))
        
        if action == delete_action:
            conv_id = item.data(Qt.UserRole)
            self.delete_history_item(conv_id)

    def delete_history_item(self, conv_id):
        reply = QMessageBox.question(self, "Confirm Delete", 
                                   "Are you sure you want to delete this conversation?",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.delete_conversation(conv_id)
            if self.current_conversation_id == conv_id:
                self.start_new_chat()
            if self.current_agent_conversation_id == conv_id:
                self.create_thread()
            self.refresh_history()

    def clear_history(self):
        reply = QMessageBox.question(self, "Confirm Clear All", 
                                   "Are you sure you want to delete ALL history? This cannot be undone.",
                                   QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.db.clear_all_conversations()
            self.start_new_chat()
            self.create_thread()
            self.refresh_history()

    def save_to_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Conversation", "", "JSON Files (*.json)")
        if path:
            data = {
                "meta": {
                    "model": self.model_combo.currentText(),
                    "date": str(datetime.datetime.now())
                },
                "messages": self.chat_history
            }
            if FileManager.save_conversation(path, data):
                QMessageBox.information(self, "Saved", "Conversation saved successfully.")

    def load_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Conversation", "", "JSON Files (*.json)")
        if path:
            data = FileManager.load_conversation(path)
            if data:
                self.start_new_chat()
                if "messages" in data:
                    for msg in data["messages"]:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        self._append_message("AI" if role == "assistant" else "User", content)
                        self.chat_history.append({"role": role, "content": content})
