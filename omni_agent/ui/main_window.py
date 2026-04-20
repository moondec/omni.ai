import sys
import os
import re
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
    QListWidget, QMenu, QTreeView, QPlainTextEdit, QFileSystemModel, QCompleter
)
import datetime
import markdown
import time

from omni_agent.config import ConfigManager
from omni_agent import __version__
from omni_agent.core.api_client import OmniApiClient
from omni_agent.core.database import DatabaseManager

from omni_agent.core.file_manager import FileManager
from omni_agent.core.agent_engine import LangChainAgentEngine
from omni_agent.core.consilium import ConsiliumOrchestrator
from omni_agent.core.llm_profile_loader import load_llm_profile
from omni_agent.core.workers import ChatWorker, AgentWorker, ConsiliumWorker
from omni_agent.ui.components.chat_input import ChatInputWidget
from omni_agent.ui.syntax_highlighter import PygmentsSyntaxHighlighter
from omni_agent import __version__

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

class CheckpointsDialog(QDialog):
    """Dialog for browsing and restoring agent checkpoints."""

    def __init__(self, checkpoint_manager, parent=None):
        super().__init__(parent)
        from PySide6.QtGui import QFont
        self._cm = checkpoint_manager
        self.setWindowTitle("Agent Checkpoints")
        self.setMinimumSize(720, 480)

        layout = QVBoxLayout(self)

        mode_label = QLabel(
            f"Mode: {'🔀 git commits' if self._cm.mode() == 'git' else '📁 file snapshots'}"
        )
        mode_label.setStyleSheet("font-size: 10px; color: gray;")
        layout.addWidget(mode_label)

        layout.addWidget(QLabel("Checkpoints (newest first):"))
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.list_widget)

        layout.addWidget(QLabel("Files changed since this checkpoint:"))
        self.diff_display = QTextEdit()
        self.diff_display.setReadOnly(True)
        self.diff_display.setMaximumHeight(160)
        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.Monospace)
        self.diff_display.setFont(mono)
        layout.addWidget(self.diff_display)

        btn_layout = QHBoxLayout()
        self.restore_btn = QPushButton("⏪ Restore to this checkpoint")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._on_restore)
        btn_layout.addWidget(self.restore_btn)
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self._checkpoints = []
        self._refresh()

    def _refresh(self):
        self._checkpoints = self._cm.list()
        self.list_widget.clear()
        if not self._checkpoints:
            self.list_widget.addItem("(No checkpoints yet — checkpoints are created automatically at the start of each agent task)")
            return
        for cp in self._checkpoints:
            ts = cp.get('timestamp', '')[:16]
            label = cp.get('label', '')[:70]
            icon = '🔀' if cp.get('type') == 'git' else '📁'
            self.list_widget.addItem(f"{icon}  {ts}   {label}")

    def _on_select(self, row):
        if row < 0 or row >= len(self._checkpoints):
            self.restore_btn.setEnabled(False)
            self.diff_display.clear()
            return
        self.restore_btn.setEnabled(True)
        cp = self._checkpoints[row]
        cp_id = cp.get('full_id') or cp.get('id', '')
        diff = self._cm.diff_summary(cp_id)
        self.diff_display.setPlainText(diff)

    def _on_restore(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._checkpoints):
            return
        cp = self._checkpoints[row]
        label = cp.get('label', '')[:60]
        ts = cp.get('timestamp', '')[:16]
        reply = QMessageBox.warning(
            self, "Confirm Restore",
            f"Restore workspace to checkpoint from:\n\n"
            f"  {ts}  —  \"{label}\"\n\n"
            "This will overwrite ALL current changes in the workspace.\n"
            "Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        cp_id = cp.get('full_id') or cp.get('id', '')
        ok = self._cm.restore(cp_id)
        if ok:
            QMessageBox.information(self, "Restored", "Workspace restored successfully.")
            self.accept()
        else:
            QMessageBox.critical(self, "Restore Failed",
                                 "Could not restore the checkpoint.\n"
                                 "Check the debug console for details.")


class _ClickOpensPopupFilter(QObject):
    """Event filter that shows combo popup on any mouse click in the line edit.

    Qt's editable QComboBox + QCompleter does NOT automatically show the full
    list on focus/click — the popup only appears after the user starts typing.
    This filter fixes that by calling showPopup() on every MouseButtonPress
    inside the embedded line edit.
    """
    def __init__(self, combo: QComboBox):
        super().__init__(combo)   # combo is parent → auto-deleted with it
        self._combo = combo

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.MouseButtonPress:
            # Small delay via singleShot keeps the normal click handling intact
            # (selection, cursor placement) and avoids double-popup issues.
            QTimer.singleShot(0, self._combo.showPopup)
        return False  # Never swallow the event


def _make_searchable_combo() -> QComboBox:
    """Create an editable QComboBox with click-to-expand + type-to-filter.

    Behaviour:
    - Click anywhere in the field  -> full list appears immediately
    - Start typing                 -> list narrows to entries *containing* the text
    - Case-insensitive, MatchContains
    - NoInsert: typing does NOT add new items
    """
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.lineEdit().setPlaceholderText("Click or type to filter...")

    # Completer — UnfilteredPopupCompletion so clicking an empty field
    # still shows everything (belt-and-suspenders alongside the event filter).
    c = QCompleter([])
    c.setFilterMode(Qt.MatchContains)
    c.setCaseSensitivity(Qt.CaseInsensitive)
    c.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    combo.setCompleter(c)

    # Install the event filter on the embedded line edit so clicking opens popup
    f = _ClickOpensPopupFilter(combo)
    combo.lineEdit().installEventFilter(f)

    return combo


def _attach_completer(combo: QComboBox, items: list) -> None:
    """Replace the combo's completer with a fresh one built from *items*.

    Call this after combo.addItems() so the popup reflects the new data.
    The event filter installed by _make_searchable_combo is preserved on the
    line edit and doesn't need to be re-installed.
    """
    c = QCompleter(items)
    c.setFilterMode(Qt.MatchContains)
    c.setCaseSensitivity(Qt.CaseInsensitive)
    c.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    combo.setCompleter(c)


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

        # Model Selection — editable with click-to-expand and type-to-filter
        self.model_combo = _make_searchable_combo()
        items = self.available_models or ["bielik_11b", "DeepSeek-V3.1-vLLM"]
        self.model_combo.addItems(items)
        _attach_completer(self.model_combo, items)
        current_model = self.config.get("model", "bielik_11b")
        # Try to restore saved model; also try the bare ID (without emoji prefix)
        if not self.model_combo.findText(current_model) >= 0:
            # Maybe displayed with 🆓 prefix — scan for it
            for i in range(self.model_combo.count()):
                if self.model_combo.itemText(i).endswith(current_model):
                    self.model_combo.setCurrentIndex(i)
                    break
        else:
            self.model_combo.setCurrentText(current_model)
        settings_dlg_layout.addRow("Default Model:", self.model_combo)

        # Base URL
        self.base_url_input = QComboBox()
        self.base_url_input.setEditable(True)
        common_urls = [
            "https://llm.hpc.pcss.pl/v1",
            "https://openrouter.ai/api/v1",
            "http://127.0.0.1:1234/v1",
            "http://127.0.0.1:11434/v1",
            "http://127.0.0.1:8000/v1",
            "https://api.openai.com/v1"
        ]
        self.base_url_input.addItems(common_urls)
        self.base_url_input.setCurrentText(self.config.get_base_url())
        self.base_url_input.lineEdit().setPlaceholderText("https://openrouter.ai/api/v1")
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

        base_url = self.base_url_input.currentText().strip()
        if base_url:
            self.config.set_base_url(base_url)
            
        transcription_model = self.transcription_model_input.text().strip()
        if transcription_model:
            self.config.set("transcription_model", transcription_model)
            
        self.accept()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"omni.ai v{__version__}")
        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1024, 600)
        
        # Set App Icon
        logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "resources", "logo.png")
        if os.path.exists(logo_path):
             self.setWindowIcon(QIcon(logo_path))

        # Main Layout      
        self.config = ConfigManager()
        self.api = OmniApiClient(self.config)
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

        # Chat streaming state
        self._chat_messages = []       # List of (display_role, content) for unified rendering
        self.current_chat_stream = ""  # Accumulates streaming chunks from ChatWorker
        self.chat_stream_needs_render = False

        # Reasoning panel state (CoT think-tag accumulator)
        self._accumulated_reasoning = ""

        # Worker instances for cancellation
        self.chat_worker = None
        self.agent_worker = None
        self._optimize_worker = None   # Prompt optimizer worker
        
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

        # Apply saved theme or default — must happen BEFORE the window is shown
        # so initial paint uses the correct colors.
        saved_theme = self.config.get("theme", "Cobalt")
        self.apply_theme(saved_theme)

        # Defer _refresh_models to AFTER show() so the window appears immediately
        # even if the PCSS API is slow/unresponsive. Previously the synchronous
        # models.list() network call inside __init__ could hang the main window
        # for the full client timeout (60s–10min) and the user saw only a dock icon.
        self.model_combo.addItem("Loading models...")
        self.model_combo.setEnabled(False)
        QTimer.singleShot(50, self._refresh_models_after_show)
    
    # Theme definitions: Cobalt (dark) and Dreamweaver (light)
    THEMES = {
        "Cobalt": {
            # ── Graphite Studio — warm graphite, gold accent ─────────────────
            "name": "Cobalt",
            "type": "dark",
            "background":     "#1E1E22",
            "secondary_bg":   "#26262C",
            "input_bg":       "#191920",
            "doc_bg":         "#191920",
            "sidebar_bg":     "#1B1B1F",
            "foreground":     "#E8E8E2",
            "text_muted":     "#7A7A80",
            "border":         "#333338",
            "border_strong":  "#48484F",
            "accent":         "#C9A84C",
            "accent_hover":   "#DEAD6B",
            "accent_dim":     "#7A6230",
            "tab_indicator":  "#C9A84C",
            "input_focus":    "#C9A84C",
            "selection_bg":   "#38341C",
            "success":        "#5CB87A",
            "error":          "#D05A52",
            "warning":        "#C9A84C",
            "button_bg":      "#28282E",
            "button_hover":   "#323238",
            "button_fg":      "#E8E8E2",
            "button_border":  "#3A3A42",
            # Message bubbles
            "msg_user_bg":    "#221F10",
            "msg_user_border":"#C9A84C",
            "msg_user_label": "#C9A84C",
            "msg_ai_bg":      "#1C1C22",
            "msg_ai_border":  "#333338",
            "msg_ai_label":   "#606068",
            "msg_agent_bg":   "#201E10",
            "msg_agent_border":"#C9A84C",
            "msg_agent_label":"#C9A84C",
            "msg_system_bg":  "#1E1E22",
            "msg_system_fg":  "#55555C",
            # Code
            "code_bg":        "#141418",
            "code_border":    "#333338",
            "code_fg":        "#C9A84C",
            "code_pre_fg":    "#B8B8C0",
            # Role buttons
            "danger_bg":      "#38181A",
            "danger_hover":   "#451E20",
            "danger_fg":      "#E06060",
            "danger_border":  "#5E2828",
            "destructive_bg": "#38181A",
            "destructive_fg": "#E06060",
            # Console
            "console_bg":     "#141418",
            "console_fg":     "#50C878",
            # Scrollbar
            "scrollbar_track": "#1E1E22",
            "scrollbar_handle":"#3A3A42",
            "scrollbar_hover": "#C9A84C",
            # Tree / splitter
            "tree_bg":        "#1B1B1F",
            "tree_hover":     "#28282E",
            "tree_selected":  "#35301A",
            "splitter":       "#2A2A30",
        },
        "Dreamweaver": {
            # ── Warm Daylight — ivory paper, amber accent ───────────────────
            "name": "Dreamweaver",
            "type": "light",
            "background":     "#F5F4EF",
            "secondary_bg":   "#ECEAE4",
            "input_bg":       "#FAF9F5",
            "doc_bg":         "#FAF9F5",
            "sidebar_bg":     "#EEEDE7",
            "foreground":     "#1C1C1E",
            "text_muted":     "#8A8A8C",
            "border":         "#D8D5CC",
            "border_strong":  "#B8B5AC",
            "accent":         "#8B6914",
            "accent_hover":   "#6A500E",
            "accent_dim":     "#C9A84C",
            "tab_indicator":  "#8B6914",
            "input_focus":    "#8B6914",
            "selection_bg":   "#EEE0BE",
            "success":        "#2E7D4F",
            "error":          "#B02C2C",
            "warning":        "#8B6914",
            "button_bg":      "#E8E6E0",
            "button_hover":   "#DEDAD2",
            "button_fg":      "#1C1C1E",
            "button_border":  "#CCCAC2",
            # Message bubbles
            "msg_user_bg":    "#FDF8EE",
            "msg_user_border":"#8B6914",
            "msg_user_label": "#8B6914",
            "msg_ai_bg":      "#F5F4EF",
            "msg_ai_border":  "#D8D5CC",
            "msg_ai_label":   "#9A9A9C",
            "msg_agent_bg":   "#FEF8EC",
            "msg_agent_border":"#8B6914",
            "msg_agent_label":"#8B6914",
            "msg_system_bg":  "#ECEAE4",
            "msg_system_fg":  "#9A9A9C",
            # Code
            "code_bg":        "#ECEAE4",
            "code_border":    "#D8D5CC",
            "code_fg":        "#8B6914",
            "code_pre_fg":    "#3A3A3E",
            # Role buttons
            "danger_bg":      "#FFE8E8",
            "danger_hover":   "#FFDCDC",
            "danger_fg":      "#B02C2C",
            "danger_border":  "#E0A0A0",
            "destructive_bg": "#FFE8E8",
            "destructive_fg": "#B02C2C",
            # Console
            "console_bg":     "#EEEDE7",
            "console_fg":     "#2E7D4F",
            # Scrollbar
            "scrollbar_track": "#ECEAE4",
            "scrollbar_handle":"#C0BDB4",
            "scrollbar_hover": "#8B6914",
            # Tree / splitter
            "tree_bg":        "#EEEDE7",
            "tree_hover":     "#E0DED6",
            "tree_selected":  "#E8DFB8",
            "splitter":       "#D8D5CC",
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
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(320)
        sidebar_layout = QVBoxLayout(sidebar)
        
        self.history_list = QListWidget()
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.setToolTip("Right-click to delete individual threads")
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        self.history_list.itemClicked.connect(self.load_history_conversation)
        sidebar_layout.addWidget(QLabel("History"))
        sidebar_layout.addWidget(self.history_list)
        
        self.clear_history_btn = QPushButton("Clear All History")
        self.clear_history_btn.setProperty("role", "destructive")
        self.clear_history_btn.clicked.connect(self.clear_history)
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
        
        self.model_combo = self._make_searchable_combo()
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
        
        # Global Console — styled via apply_theme() (console_bg/console_fg)
        self.console_display = QTextEdit()
        self.console_display.setReadOnly(True)
        self.console_display.setPlaceholderText("Debug Console Log...")
        self.console_display.setObjectName("debugConsole")
        self.console_display.hide()
        self.main_content_splitter.addWidget(self.console_display)
        self.main_content_splitter.setSizes([600, 150])
        self.main_content_splitter.setCollapsible(1, True)
        self.main_content_splitter.setStretchFactor(0, 1)
        self.main_content_splitter.setStretchFactor(1, 0)

        main_layout.addWidget(self.main_content_splitter)

        self.outer_splitter.addWidget(right_panel)
        self.outer_splitter.setSizes([220, 980])
        self.outer_splitter.setCollapsible(0, True)
        self.outer_splitter.setStretchFactor(0, 0)
        self.outer_splitter.setStretchFactor(1, 1)
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

        self.chat_optimize_btn = QPushButton("✨ Optimize Prompt")
        self.chat_optimize_btn.setToolTip("Rewrite prompt using AI for better clarity and precision")
        self.chat_optimize_btn.clicked.connect(lambda: self.optimize_prompt(self.message_input))
        controls_layout.addWidget(self.chat_optimize_btn)

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
        self.chat_send_btn.setMinimumSize(80, 80)
        self.chat_send_btn.clicked.connect(self.send_message)
        input_layout.addWidget(self.chat_send_btn)

        self.chat_stop_btn = QPushButton("Stop")
        self.chat_stop_btn.setMinimumSize(80, 80)
        self.chat_stop_btn.clicked.connect(self.stop_chat)
        self.chat_stop_btn.setEnabled(False)
        self.chat_stop_btn.setProperty("role", "danger")
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
        
        refresh_profiles_btn = QPushButton("Refresh")
        refresh_profiles_btn.setMinimumSize(70, 32)
        refresh_profiles_btn.setToolTip("Refresh agent profiles")
        refresh_profiles_btn.clicked.connect(self._load_agent_profiles)
        config_layout.addWidget(refresh_profiles_btn)

        open_folder_btn = QPushButton("Folder")
        open_folder_btn.setMinimumSize(70, 32)
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

        checkpoints_btn = QPushButton("🔖 Checkpoints")
        checkpoints_btn.setToolTip("Browse and restore workspace checkpoints")
        checkpoints_btn.clicked.connect(self.open_checkpoints_dialog)
        config_layout.addWidget(checkpoints_btn)

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
        self.consilium_executor_combo = self._make_searchable_combo()
        consilium_grid.addWidget(self.consilium_executor_combo)

        consilium_grid.addWidget(QLabel("Reviewer:"))
        self.consilium_reviewer_combo = self._make_searchable_combo()
        consilium_grid.addWidget(self.consilium_reviewer_combo)

        consilium_grid.addWidget(QLabel("Skeptic:"))
        self.consilium_skeptic_combo = self._make_searchable_combo()
        consilium_grid.addWidget(self.consilium_skeptic_combo)

        # Populated in _refresh_models
        
        self.consilium_controls.setVisible(False)
        self.consilium_layout.addWidget(self.consilium_controls)
        self.consilium_layout.addStretch()
        
        agent_layout.addLayout(self.consilium_layout)
        # ------------------------------------
        
        # Load profiles on init
        self.agent_profiles = {}  # {name: {description, instructions}}
        self.current_profile_instructions = ""
        self._load_agent_profiles()

        # Agent Chat Display + Reasoning Panel (vertical splitter)
        self._display_splitter = QSplitter(Qt.Vertical)

        self.agent_display = QTextBrowser()
        self.agent_display.setReadOnly(True)
        self.agent_display.setOpenExternalLinks(False)
        self.agent_display.setOpenLinks(False)
        self.agent_display.anchorClicked.connect(self._handle_link_click)
        self._display_splitter.addWidget(self.agent_display)

        # Reasoning Panel — shows <think> CoT content, hidden until content arrives
        self.reasoning_frame = QFrame()
        self.reasoning_frame.setFrameShape(QFrame.StyledPanel)
        reasoning_outer = QVBoxLayout(self.reasoning_frame)
        reasoning_outer.setContentsMargins(4, 2, 4, 2)
        reasoning_outer.setSpacing(2)

        reasoning_header = QHBoxLayout()
        self.reasoning_toggle_btn = QPushButton("▶ Model Reasoning (CoT)")
        self.reasoning_toggle_btn.setCheckable(True)
        self.reasoning_toggle_btn.setChecked(False)
        self.reasoning_toggle_btn.setToolTip("Show/hide chain-of-thought content (<think> tags)")
        self.reasoning_toggle_btn.setMinimumHeight(24)
        self.reasoning_toggle_btn.toggled.connect(self._toggle_reasoning_body)
        reasoning_header.addWidget(self.reasoning_toggle_btn)

        self.reasoning_badge = QLabel("")
        self.reasoning_badge.setStyleSheet("color: gray; font-size: 10px; padding-left: 8px;")
        reasoning_header.addWidget(self.reasoning_badge)
        reasoning_header.addStretch()
        reasoning_outer.addLayout(reasoning_header)

        self.reasoning_body = QFrame()
        reasoning_body_layout = QVBoxLayout(self.reasoning_body)
        reasoning_body_layout.setContentsMargins(0, 0, 0, 0)
        self.reasoning_display = QTextBrowser()
        self.reasoning_display.setReadOnly(True)
        self.reasoning_display.setMinimumHeight(100)
        reasoning_body_layout.addWidget(self.reasoning_display)
        self.reasoning_body.setVisible(False)
        reasoning_outer.addWidget(self.reasoning_body)

        # Frame is always visible so users discover the feature; body collapses.
        self.reasoning_frame.setVisible(True)
        self._display_splitter.addWidget(self.reasoning_frame)
        self._display_splitter.setCollapsible(1, True)
        self._display_splitter.setStretchFactor(0, 1)
        self._display_splitter.setStretchFactor(1, 0)
        self._display_splitter.setSizes([500, 30])
        agent_layout.addWidget(self._display_splitter)

        # Status / Workspace Area (Agent Console toggle also lives here to keep config row compact)
        status_layout = QHBoxLayout()
        self.agent_status_label = QLabel("Status: Idle")
        workspace_path = self.config.get_workspace_path()
        self.workspace_label = QLabel(f"Workspace: {workspace_path}")
        self.workspace_label.setObjectName("mutedLabel")

        status_layout.addWidget(self.agent_status_label)
        status_layout.addStretch()
        status_layout.addWidget(self.workspace_label)

        self.toggle_console_agent_btn = QPushButton("Debug Console")
        self.toggle_console_agent_btn.setCheckable(True)
        self.toggle_console_agent_btn.setMinimumHeight(24)
        self.toggle_console_agent_btn.toggled.connect(self.toggle_console)
        status_layout.addWidget(self.toggle_console_agent_btn)

        agent_layout.addLayout(status_layout)
        
        # Input Area
        input_layout = QHBoxLayout()
        self.agent_input = ChatInputWidget()
        self.agent_input.workspace_path = getattr(self, 'current_workspace', "")
        self.agent_input.send_requested.connect(self.send_to_agent)
        self.agent_input.history_up_requested.connect(lambda: self._navigate_prompt_history(-1, self.agent_input))
        self.agent_input.history_down_requested.connect(lambda: self._navigate_prompt_history(1, self.agent_input))
        input_layout.addWidget(self.agent_input)
        
        agent_btn_col = QVBoxLayout()
        self.agent_send_btn = QPushButton("Send to Agent")
        self.agent_send_btn.setMinimumSize(160, 38)
        self.agent_send_btn.clicked.connect(self.send_to_agent)
        agent_btn_col.addWidget(self.agent_send_btn)

        self.agent_optimize_btn = QPushButton("✨ Optimize Prompt")
        self.agent_optimize_btn.setMinimumSize(160, 38)
        self.agent_optimize_btn.setToolTip("Rewrite prompt using AI for better clarity and precision")
        self.agent_optimize_btn.clicked.connect(lambda: self.optimize_prompt(self.agent_input))
        agent_btn_col.addWidget(self.agent_optimize_btn)
        input_layout.addLayout(agent_btn_col)

        self.agent_stop_btn = QPushButton("Stop")
        self.agent_stop_btn.setMinimumSize(80, 80)
        self.agent_stop_btn.clicked.connect(self.stop_agent)
        self.agent_stop_btn.setEnabled(False)
        self.agent_stop_btn.setProperty("role", "danger")
        input_layout.addWidget(self.agent_stop_btn)
        
        agent_layout.addLayout(input_layout)

    def _toggle_consilium_ui(self, checked):
        self.consilium_controls.setVisible(checked)
        if checked:
            self.statusBar().showMessage("Consilium Mode activated. Click 'Create Assistant' to re-initialize.", 5000)
        else:
            self.statusBar().showMessage("Solo Mode activated. Click 'Create Assistant' to re-initialize.", 5000)

    @staticmethod
    def _make_searchable_combo() -> QComboBox:
        """Delegate to module-level helper (kept for legacy call-sites)."""
        return _make_searchable_combo()

    @staticmethod
    def _attach_completer(combo: QComboBox, items: list) -> None:
        """Delegate to module-level helper (kept for legacy call-sites)."""
        _attach_completer(combo, items)

    def _refresh_models_after_show(self):
        """Re-enable the combo and trigger the (potentially slow) API model list load.

        Runs via QTimer.singleShot(50, ...) from __init__ so the main window
        becomes visible before any network I/O blocks the GUI thread.
        """
        self.model_combo.setEnabled(True)
        self._refresh_models()

    def _refresh_models(self):
        """
        Refresh available models from API.
        Fully dynamic — adapts to any changes in API model offerings.
        Adds 🆓 prefix to free-tier models, sorts alphabetically.
        """
        if self.api.is_configured():
            self.model_combo.blockSignals(True)  # Prevent triggering change reset during update

            try:
                # 1. Fetch full model metadata (pricing + sorting)
                models_full = self.api.list_models_full()

                # 2. Build display list: free models get 🆓 prefix
                # _model_display_map: display_label -> real model id
                self._model_display_map = {}
                display_labels = []
                for m in models_full:
                    label = ("🆓 " if m["is_free"] else "") + m["id"]
                    self._model_display_map[label] = m["id"]
                    display_labels.append(label)

                # Also keep bare IDs as aliases (for saved config restoring)
                for m in models_full:
                    self._model_display_map[m["id"]] = m["id"]

                # Cache plain IDs for other consumers (consilium combos etc.)
                final_models = [m["id"] for m in models_full]
                self.available_models = final_models

                if not display_labels:
                    raise ValueError("No models available from API")

                # 3. Update main model combo with display labels
                self.model_combo.clear()
                self.model_combo.addItems(display_labels)
                self._attach_completer(self.model_combo, display_labels)

                # 4. Consilium combos — also get 🆓 labels + fresh completers
                for combo in [self.consilium_executor_combo, self.consilium_reviewer_combo, self.consilium_skeptic_combo]:
                    if hasattr(self, "consilium_executor_combo"):
                        combo.clear()
                        combo.addItems(display_labels)
                        self._attach_completer(combo, display_labels)

                # 5. Smart model selection with fallback
                saved_model = self.config.get("model")
                selected_model = None

                def _select_by_real_id(real_id):
                    """Find and select the display label matching real_id."""
                    for i, label in enumerate(display_labels):
                        if self._model_display_map.get(label) == real_id:
                            self.model_combo.setCurrentIndex(i)
                            return True
                    return False

                if saved_model and saved_model in final_models:
                    if _select_by_real_id(saved_model):
                        selected_model = saved_model
                        self.append_log(f"✓ Restored model: {saved_model}")
                else:
                    if saved_model:
                        self.append_log(f"⚠ Saved model '{saved_model}' no longer available")

                    PREFERRED_MODELS = ["bielik_11b", "DeepSeek-V3.1-vLLM"]
                    for preferred in PREFERRED_MODELS:
                        if preferred in final_models:
                            if _select_by_real_id(preferred):
                                selected_model = preferred
                                self.append_log(f"→ Selected fallback model: {preferred}")
                                break

                    if not selected_model and display_labels:
                        self.model_combo.setCurrentIndex(0)
                        selected_model = final_models[0]
                        self.append_log(f"→ Selected first available model: {selected_model}")

                    if selected_model:
                        self.config.set("model", selected_model)

                # 6. Default Consilium selections
                def _set_consilium_default(combo, preferred):
                    idx = combo.findText(preferred)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    elif combo.count() > 0:
                        combo.setCurrentIndex(0)

                if hasattr(self, "consilium_executor_combo"):
                    _set_consilium_default(self.consilium_executor_combo, "Qwen3.5-397B-A17B")
                    _set_consilium_default(self.consilium_reviewer_combo, "DeepSeek-V3.1-vLLM")
                    _set_consilium_default(self.consilium_skeptic_combo, "GLM-4.7")

                # 7. Count free vs paid
                free_count = sum(1 for m in models_full if m["is_free"])
                paid_count = len(models_full) - free_count
                current_model = self._model_display_map.get(self.model_combo.currentText(), self.model_combo.currentText())
                self.statusBar().showMessage(
                    f"Models refreshed: {len(models_full)} total (🆓 {free_count} free, {paid_count} paid) — Using: {current_model}",
                    5000
                )

            except Exception as e:
                self.append_log(f"❌ Model refresh failed: {str(e)}")
                self.model_combo.clear()
                emergency_models = ["bielik_11b", "DeepSeek-V3.1-vLLM"]
                self.model_combo.addItems(emergency_models)
                self.model_combo.setCurrentIndex(0)
                self.statusBar().showMessage(f"Model refresh failed: {str(e)}", 10000)

            finally:
                self.model_combo.blockSignals(False)

    def on_model_changed(self, text):
        if not text:
            return
        # Strip 🆓 display prefix to get the real model ID
        real_id = getattr(self, "_model_display_map", {}).get(text, text)
        # Save real model ID (no emoji) to config
        self.config.set("model", real_id)
        self.append_log(f"Model changed to: {real_id}")

        # Update status bar with current model
        self.statusBar().showMessage(f"Using model: {real_id}", 5000)
        self.agent_display.append(f"<b>System:</b> Model changed to {real_id}. Please re-initialize Assistant.<br>")
        self.agent_engine = None  # Force re-creation with new model
        self.agent_status_label.setText("Model Changed")

    def _current_model(self) -> str:
        """Return the real model ID from the main combo (strips 🆓 display prefix)."""
        text = self.model_combo.currentText()
        return getattr(self, "_model_display_map", {}).get(text, text)

    def open_settings(self):
        # Get current models from main combo
        current_models = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]
        
        # Capture current workspace before dialog to detect changes
        old_workspace = self.config.get_workspace_path()
        
        dlg = SettingsDialog(self.config, self, available_models=current_models)
        if dlg.exec():
            # Re-initialize API client
            self.api = OmniApiClient(self.config)
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
            current_model = self._current_model()
            self.append_log(f"Settings saved. Current model: {current_model}")

    def _doc_stylesheet(self, theme: dict) -> str:
        """CSS applied to QTextBrowser document content (HTML messages, not widget chrome)."""
        return f"""
            body {{
                font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 13px;
                color: {theme['foreground']};
                background-color: {theme['doc_bg']};
                margin: 6px 8px;
                line-height: 1.65;
            }}
            p {{ margin: 0 0 6px 0; }}
            a {{ color: {theme['accent']}; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            code {{
                font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
                font-size: 11.5px;
                background-color: {theme['code_bg']};
                color: {theme['code_fg']};
                padding: 1px 5px;
                border-radius: 3px;
            }}
            pre {{
                font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
                font-size: 11.5px;
                background-color: {theme['code_bg']};
                color: {theme['code_pre_fg']};
                border: 1px solid {theme['code_border']};
                border-radius: 5px;
                padding: 10px 14px;
                margin: 8px 0;
                white-space: pre-wrap;
            }}
            pre code {{ background: transparent; padding: 0; border-radius: 0; color: inherit; }}
            blockquote {{
                border-left: 3px solid {theme['border_strong']};
                padding-left: 12px;
                margin: 6px 0;
                color: {theme['text_muted']};
            }}
            h1 {{ font-size: 17px; font-weight: 700; margin: 14px 0 6px 0; color: {theme['foreground']}; }}
            h2 {{ font-size: 14px; font-weight: 700; margin: 12px 0 5px 0; color: {theme['foreground']}; }}
            h3 {{ font-size: 13px; font-weight: 600; margin: 10px 0 4px 0; color: {theme['foreground']}; }}
            ul, ol {{ padding-left: 20px; margin: 4px 0; }}
            li {{ margin: 2px 0; }}
            table {{ border-collapse: collapse; margin: 8px 0; width: 100%; }}
            th {{ background-color: {theme['secondary_bg']}; color: {theme['accent']};
                  padding: 5px 10px; border: 1px solid {theme['border']}; text-align: left;
                  font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; }}
            td {{ padding: 5px 10px; border: 1px solid {theme['border']}; color: {theme['foreground']}; }}
        """

    def _patch_code_styles(self, html: str, theme: dict) -> str:
        """Inject inline styles into <pre> and <code> elements.

        QTextBrowser's HTML renderer ignores setDefaultStyleSheet for pre/code,
        so document-level CSS is not enough — we must add inline styles directly
        to each element after markdown conversion.
        """
        pre_style = (
            f'background-color:{theme["code_bg"]};'
            f'color:{theme["code_pre_fg"]};'
            f'font-family:"Consolas","Courier New",monospace;'
            f'font-size:12px;'
            f'padding:10px 14px;'
            f'border:1px solid {theme["code_border"]};'
            f'margin:8px 0;'
            f'white-space:pre-wrap;'
            f'display:block;'
        )
        code_style = (
            f'background-color:{theme["code_bg"]};'
            f'color:{theme["code_fg"]};'
            f'font-family:"Consolas","Courier New",monospace;'
            f'font-size:12px;'
            f'padding:1px 5px;'
            f'border-radius:3px;'
        )
        # Inject style into every <pre ...> tag (may already have class attributes)
        html = re.sub(
            r'<pre\b([^>]*)>',
            lambda m: f'<pre{m.group(1)} style="{pre_style}">',
            html,
        )
        # Inject style into every <code ...> tag; code inside pre will
        # inherit pre's styling so the duplicate is harmless
        html = re.sub(
            r'<code\b([^>]*)>',
            lambda m: f'<code{m.group(1)} style="{code_style}">',
            html,
        )
        return html

    def _message_html(self, role: str, text: str) -> str:
        """Return a styled HTML bubble for a chat/agent message."""
        theme = self.THEMES.get(self.current_theme, self.THEMES['Cobalt'])
        fg = theme['foreground']   # explicit text colour — prevents black-on-dark bug
        m_html = markdown.markdown(text, extensions=['extra', 'nl2br'])
        m_html = self._patch_code_styles(m_html, theme)

        if role in ("User",):
            return (
                f'<div style="margin:8px 0 10px 0; padding:9px 14px;'
                f' background-color:{theme["msg_user_bg"]};'
                f' border-left:3px solid {theme["msg_user_border"]};">'
                f'<div style="color:{theme["msg_user_label"]}; font-size:10px;'
                f' font-weight:700; letter-spacing:0.07em; margin-bottom:5px;">YOU</div>'
                f'<div style="color:{fg};">{m_html}</div>'
                f'</div>'
            )
        elif role in ("AI", "Assistant"):
            return (
                f'<div style="margin:8px 0 10px 0; padding:9px 14px;'
                f' background-color:{theme["msg_ai_bg"]};'
                f' border-left:3px solid {theme["msg_ai_border"]};">'
                f'<div style="color:{theme["msg_ai_label"]}; font-size:10px;'
                f' font-weight:700; letter-spacing:0.07em; margin-bottom:5px;">ASSISTANT</div>'
                f'<div style="color:{fg};">{m_html}</div>'
                f'</div>'
            )
        elif role in ("Agent",):
            return (
                f'<div style="margin:8px 0 10px 0; padding:9px 14px;'
                f' background-color:{theme["msg_agent_bg"]};'
                f' border-left:3px solid {theme["msg_agent_border"]};">'
                f'<div style="color:{theme["msg_agent_label"]}; font-size:10px;'
                f' font-weight:700; letter-spacing:0.07em; margin-bottom:5px;">AGENT</div>'
                f'<div style="color:{fg};">{m_html}</div>'
                f'</div>'
            )
        else:
            # System / status message — subtle, small
            return (
                f'<div style="margin:4px 0; padding:5px 12px;'
                f' background-color:{theme["msg_system_bg"]};">'
                f'<span style="color:{theme["msg_system_fg"]}; font-size:11px;'
                f' font-style:italic;">{m_html}</span>'
                f'</div>'
            )

    def _apply_doc_stylesheets(self, theme: dict) -> None:
        """Push the document CSS into every QTextBrowser that shows chat content."""
        css = self._doc_stylesheet(theme)
        for attr in ('chat_display', 'agent_display', 'reasoning_display'):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.document().setDefaultStyleSheet(css)

    def apply_theme(self, theme_name: str):
        """Apply a theme to the application."""
        if theme_name not in self.THEMES:
            theme_name = "Cobalt"

        theme = self.THEMES[theme_name]

        if self.current_theme != theme_name:
            self.current_theme = theme_name
            self.config.set("theme", theme_name)

        if hasattr(self, 'theme_btn'):
            other = "Daylight" if theme_name == "Cobalt" else "Obsidian"
            self.theme_btn.setText(f"◐ {other}")

        # ── Qt Stylesheet ────────────────────────────────────────────────────
        stylesheet = f"""
            /* ── Base ── */
            QMainWindow, QWidget {{
                background-color: {theme['background']};
                color: {theme['foreground']};
                font-size: 13px;
            }}
            QLabel {{ color: {theme['foreground']}; }}

            /* ── Text inputs ── */
            QTextEdit, QTextBrowser, QPlainTextEdit {{
                background-color: {theme['input_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 6px;
                padding: 5px 7px;
                selection-background-color: {theme['selection_bg']};
                selection-color: {theme['foreground']};
            }}
            QTextEdit:focus, QPlainTextEdit:focus {{
                border-color: {theme['input_focus']};
            }}
            QLineEdit {{
                background-color: {theme['input_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 6px;
                padding: 4px 8px;
                selection-background-color: {theme['selection_bg']};
            }}
            QLineEdit:focus {{ border-color: {theme['input_focus']}; }}

            /* ── Buttons ── */
            QPushButton {{
                background-color: {theme['button_bg']};
                color: {theme['button_fg']};
                border: 1px solid {theme['button_border']};
                border-radius: 6px;
                padding: 5px 14px;
                min-height: 26px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {theme['button_hover']};
                border-color: {theme['border_strong']};
            }}
            QPushButton:pressed {{
                background-color: {theme['accent_dim']};
                border-color: {theme['accent']};
            }}
            QPushButton:checked {{
                background-color: {theme['accent_dim']};
                border-color: {theme['accent']};
                color: {theme['accent']};
            }}
            QPushButton:disabled {{
                background-color: {theme['button_bg']};
                color: {theme['text_muted']};
                border-color: {theme['border']};
            }}
            QPushButton[role="danger"]:enabled {{
                background-color: {theme['danger_bg']};
                color: {theme['danger_fg']};
                border: 1px solid {theme['danger_border']};
            }}
            QPushButton[role="danger"]:enabled:hover {{
                background-color: {theme['danger_hover']};
            }}
            QPushButton[role="destructive"] {{
                background-color: {theme['destructive_bg']};
                color: {theme['destructive_fg']};
                border: 1px solid {theme['border']};
            }}

            /* ── List ── */
            QListWidget {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border']};
                border-radius: 6px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {theme['tree_selected']};
                color: {theme['foreground']};
            }}
            QListWidget::item:hover {{
                background-color: {theme['tree_hover']};
            }}

            /* ── ComboBox ── */
            QComboBox {{
                background-color: {theme['button_bg']};
                color: {theme['button_fg']};
                border: 1px solid {theme['button_border']};
                border-radius: 6px;
                padding: 4px 10px;
                min-height: 24px;
            }}
            QComboBox:focus {{ border-color: {theme['input_focus']}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border_strong']};
                selection-background-color: {theme['tree_selected']};
                selection-color: {theme['foreground']};
                padding: 4px;
            }}

            /* ── Tabs — underline style, no boxes ── */
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {theme['border']};
                background-color: {theme['background']};
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {theme['text_muted']};
                padding: 8px 20px;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: 500;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                color: {theme['accent']};
                border-bottom: 2px solid {theme['tab_indicator']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {theme['foreground']};
                background-color: {theme['secondary_bg']};
            }}

            /* ── Scrollbars — slim, minimal ── */
            QScrollBar:vertical {{
                background-color: {theme['scrollbar_track']};
                width: 6px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme['scrollbar_handle']};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme['scrollbar_hover']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background-color: {theme['scrollbar_track']};
                height: 6px;
                margin: 0;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {theme['scrollbar_handle']};
                border-radius: 3px;
                min-width: 24px;
            }}
            QScrollBar::handle:horizontal:hover {{ background-color: {theme['scrollbar_hover']}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

            /* ── Splitter ── */
            QSplitter::handle {{ background-color: {theme['splitter']}; }}
            QSplitter::handle:horizontal {{ width: 1px; }}
            QSplitter::handle:vertical {{ height: 1px; }}

            /* ── Tree view (file browser) ── */
            QTreeView {{
                background-color: {theme['tree_bg']};
                color: {theme['foreground']};
                border: none;
                outline: none;
            }}
            QTreeView::item {{ padding: 3px 4px; border-radius: 3px; }}
            QTreeView::item:selected {{ background-color: {theme['tree_selected']}; }}
            QTreeView::item:hover {{ background-color: {theme['tree_hover']}; }}
            QTreeView::branch {{ background-color: {theme['tree_bg']}; }}

            /* ── CheckBox ── */
            QCheckBox {{ spacing: 7px; color: {theme['foreground']}; }}
            QCheckBox::indicator {{
                width: 15px; height: 15px;
                border: 1px solid {theme['border_strong']};
                border-radius: 3px;
                background-color: {theme['input_bg']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {theme['accent']};
                border-color: {theme['accent']};
            }}

            /* ── Menus ── */
            QMenuBar {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                padding: 0;
                border-bottom: 1px solid {theme['border']};
            }}
            QMenuBar::item {{ padding: 4px 10px; border-radius: 3px; }}
            QMenuBar::item:selected {{ background-color: {theme['secondary_bg']}; color: {theme['accent']}; }}
            QMenu {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border_strong']};
                padding: 4px;
                border-radius: 6px;
            }}
            QMenu::item {{ padding: 5px 20px 5px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {theme['tree_selected']}; }}
            QMenu::separator {{
                height: 1px;
                background-color: {theme['border']};
                margin: 3px 6px;
            }}

            /* ── Tooltips ── */
            QToolTip {{
                background-color: {theme['secondary_bg']};
                color: {theme['foreground']};
                border: 1px solid {theme['border_strong']};
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }}

            /* ── Status bar ── */
            QStatusBar {{
                background-color: {theme['secondary_bg']};
                color: {theme['text_muted']};
                border-top: 1px solid {theme['border']};
                font-size: 11px;
            }}

            /* ── Named elements ── */
            QTextEdit#debugConsole {{
                background-color: {theme['console_bg']};
                color: {theme['console_fg']};
                font-family: "JetBrains Mono", "Fira Code", "Consolas", "Courier New", monospace;
                font-size: 11px;
                border: 1px solid {theme['border']};
                border-radius: 4px;
            }}
            QLabel#mutedLabel {{
                color: {theme['text_muted']};
                font-size: 10px;
            }}
        """

        self.setStyleSheet(stylesheet)
        self._apply_doc_stylesheets(theme)

        # Re-polish role-based buttons so property selectors take effect immediately
        for btn in self.findChildren(QPushButton):
            if btn.property("role"):
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        # Invalidate ALL cached HTML so the next render regenerates message
        # bubbles with the new theme's colours instead of showing stale HTML
        # (inline body bg-color in old HTML overrides the new doc CSS).
        self._last_render_state_key = None
        self._cached_history_html = []
        self._cached_history_len = -1
        self._cached_user_prompt_html = None
        self._cached_user_prompt_text = ""
        self._cached_stream_html = None
        self._cached_stream_text = ""

        # Force immediate re-render of both display areas
        if hasattr(self, 'chat_display'):
            self._render_chat_display()
        if hasattr(self, 'agent_display'):
            self._render_chat()

    def toggle_theme(self):
        """Toggle between Cobalt and Dreamweaver themes."""
        new_theme = "Dreamweaver" if self.current_theme == "Cobalt" else "Cobalt"
        self.apply_theme(new_theme)

    def start_new_chat(self):
        self.current_conversation_id = None
        self.chat_history = []
        self._chat_messages = []
        self.current_chat_stream = ""
        self.chat_display.clear()
        self.model_combo.setEnabled(True)

    def append_log(self, message: str):
        self.log_buffer.append(message)
        # Note: file logging is handled exclusively by agent_engine._log()
        # to avoid duplicate entries in agent_debug.log.

    def send_message(self):
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        self._add_to_prompt_history(text)

        model = self._current_model()
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
        self.chat_worker.chunk_received.connect(self.handle_chat_chunk)
        self.chat_worker.finished.connect(self.handle_response)
        self.chat_worker.error.connect(self.handle_error)
        self.chat_worker.cancelled.connect(self.handle_chat_cancelled)
        self.chat_worker.log_message.connect(self.append_log)
        self.current_chat_stream = ""
        self.chat_worker.start()
        
        # UI state: disable input, enable Stop
        self.message_input.setReadOnly(True)
        self.chat_send_btn.setEnabled(False)
        self.chat_stop_btn.setEnabled(True)

    def handle_chat_chunk(self, chunk):
        self.current_chat_stream += chunk
        self.chat_stream_needs_render = True

    def handle_response(self, content):
        self.current_chat_stream = ""  # Clear stream buffer before appending final message
        self._append_message("AI", content)
        self.chat_history.append({"role": "assistant", "content": content})
        self.db.add_message(self.current_conversation_id, "assistant", content)
        self._reset_chat_ui()

    def handle_error(self, err_msg):
        QMessageBox.critical(self, "API Error", err_msg)
        self._reset_chat_ui()

    def handle_chat_cancelled(self):
        """Handle chat worker cancellation."""
        self.current_chat_stream = ""
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
        if not hasattr(self, '_chat_messages'):
            self._chat_messages = []
        self._chat_messages.append((role, text))
        self._render_chat_display()

    def _render_chat_display(self):
        """Unified chat-mode renderer: rebuilds HTML from _chat_messages + current stream."""
        scrollbar = self.chat_display.verticalScrollBar()
        saved_value = scrollbar.value()
        was_at_bottom = saved_value >= scrollbar.maximum() - 30

        html_parts = []
        for display_role, content in getattr(self, '_chat_messages', []):
            html_parts.append(self._message_html(display_role, content))

        current_stream = getattr(self, 'current_chat_stream', '')
        if current_stream:
            html_parts.append(self._message_html("AI", current_stream))

        theme = self.THEMES.get(self.current_theme, self.THEMES['Cobalt'])
        full_html = (
            f'<html><body style="background-color:{theme["doc_bg"]};">'
            + "".join(html_parts)
            + "</body></html>"
        )

        self.chat_display.setUpdatesEnabled(False)
        self.chat_display.setHtml(full_html)
        self.chat_display.setUpdatesEnabled(True)

        if was_at_bottom or current_stream:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(saved_value)

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
        model = self._current_model()
        
        # Determine LLM-specific operational rules and limits
        llm_rules, max_tokens, system_prompt_additions, context_window = self._get_llm_profile_data(model)
        
        try:
            self.agent_status_label.setText("Initializing Agent...")
            # Tier-based few-shot limit: stronger models benefit from more examples
            try:
                from omni_agent.core.agent_engine import get_model_profile
                _tier = get_model_profile(model).tier
            except Exception:
                _tier = 4
            _few_shot_limit = {1: 10, 2: 7, 3: 5, 4: 3}.get(_tier, 3)
            top_examples = self.db.get_top_rated_interactions(model, limit=_few_shot_limit)
            
            self.agent_status_label.setText("Agent Ready")
            
            # Smart history management: 
            # If manually re-initializing (preserve_history=False) but we HAVE history,
            # we likely want to keep it (hot-swapping models). 
            # To start fresh, user uses "New Thread".
            if not preserve_history and self.agent_history:
                self.append_log("🔄 Re-initializing Agent. History preserved for model/profile switch.")
                preserve_history = True
                
            if not preserve_history:
                self.agent_history = [] # Reset history only when starting truly fresh or initial
            
            is_consilium = hasattr(self, 'consilium_checkbox') and self.consilium_checkbox.isChecked()
            
            if is_consilium:
                # Initialize Consilium Orchestrator
                _dm = getattr(self, "_model_display_map", {})
                ex_model = _dm.get(self.consilium_executor_combo.currentText(), self.consilium_executor_combo.currentText())
                rv_model = _dm.get(self.consilium_reviewer_combo.currentText(), self.consilium_reviewer_combo.currentText())
                sk_model = _dm.get(self.consilium_skeptic_combo.currentText(), self.consilium_skeptic_combo.currentText())
                
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
                
            # Only reset conversation ID if we are NOT preserving history
            if not preserve_history:
                self.current_agent_conversation_id = None
            
            self.agent_display.append(f"<b>System:</b> Workspace: {workspace}<br>")
            self.agent_display.append(f"<b>System:</b> Tools: [Files, Documents, OCR, Vision, Web Search]<br>")
            
            # Force UI refresh to show history if we preserved it
            if preserve_history:
                self._last_render_state_key = None # Invalidate cache
                self._render_chat()
            
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

    def open_checkpoints_dialog(self):
        """Open the checkpoints browser dialog."""
        if not self.agent_engine:
            QMessageBox.information(
                self, "Checkpoints",
                "Initialize the Agent first (Create Assistant) so the workspace path is known."
            )
            return
        from omni_agent.core.checkpoint_manager import CheckpointManager
        cm = self.agent_engine.checkpoint_manager
        dlg = CheckpointsDialog(cm, parent=self)
        dlg.exec()

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
             model = self._current_model()
             profile = self.profile_combo.currentText()
             agent_name = self.agent_name_input.text().strip()
             title = f"Agent: {text[:20]}..."
             self.current_agent_conversation_id = self.db.create_conversation(
                 title, model, mode="agent", agent_profile=profile, agent_name=agent_name
             )
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
        self._accumulated_reasoning = ""
        self._update_reasoning_panel("")
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
                role = "User" if isinstance(msg, HumanMessage) else "Agent"
                html_parts.append(self._message_html(role, msg.content))
            self._cached_history_html = html_parts
            self._cached_history_len = len(self.agent_history)

        html_parts = list(self._cached_history_html)

        if hasattr(self, 'agent_worker') and self.agent_worker:
            if not hasattr(self, '_cached_user_prompt_html') or getattr(self, '_cached_user_prompt_text', "") != worker_text:
                self._cached_user_prompt_html = self._message_html("User", worker_text)
                self._cached_user_prompt_text = worker_text
            html_parts.append(self._cached_user_prompt_html)

        if current_stream_text:
            # Extract <think> reasoning → reasoning panel
            think_matches = re.findall(r'<think>(.*?)</think>', current_stream_text, re.DOTALL)
            if think_matches:
                new_reasoning = "\n\n---\n\n".join(think_matches)
                if new_reasoning != getattr(self, '_accumulated_reasoning', ''):
                    self._accumulated_reasoning = new_reasoning
                    self._update_reasoning_panel(new_reasoning)

            stream_for_display = re.sub(r'<think>.*?</think>\s*', '', current_stream_text, flags=re.DOTALL)
            stream_for_display = re.sub(r'<think>[^<]*$', '', stream_for_display)
            stream_for_display = stream_for_display.strip()

            if stream_for_display:
                if not hasattr(self, '_cached_stream_html') or getattr(self, '_cached_stream_text', "") != stream_for_display:
                    self._cached_stream_html = self._message_html("Agent", stream_for_display)
                    self._cached_stream_text = stream_for_display
                html_parts.append(self._cached_stream_html)

        theme = self.THEMES.get(self.current_theme, self.THEMES['Cobalt'])
        full_html = (
            f'<html><body style="background-color:{theme["doc_bg"]};">'
            + "".join(html_parts)
            + "</body></html>"
        )

        self.agent_display.setUpdatesEnabled(False)
        self.agent_display.setHtml(full_html)
        
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

    def _update_reasoning_panel(self, content: str):
        """Update the CoT reasoning panel with extracted <think> content."""
        if not hasattr(self, 'reasoning_display'):
            return
        if content:
            html = markdown.markdown(content, extensions=['extra', 'nl2br'])
            self.reasoning_display.setHtml(html)
            char_count = len(content)
            self.reasoning_badge.setText(f"  ({char_count:,} chars of reasoning available)")
        else:
            self.reasoning_display.setHtml("")
            self.reasoning_badge.setText("")

    def _toggle_reasoning_body(self, checked: bool):
        self.reasoning_body.setVisible(checked)
        arrow = "▼" if checked else "▶"
        self.reasoning_toggle_btn.setText(f"{arrow} Model Reasoning (CoT)")
        if hasattr(self, '_display_splitter'):
            if checked:
                self._display_splitter.setSizes([400, 200])
            else:
                self._display_splitter.setSizes([550, 30])

    def optimize_prompt(self, input_widget):
        """Rewrite the current prompt for better clarity using the active model."""
        text = input_widget.toPlainText().strip()
        if not text or len(text) < 5:
            return

        # Prevent double-clicks while optimization is in progress
        if self._optimize_worker is not None:
            return

        # If the input is locked (agent is currently working), inform the user
        if input_widget.isReadOnly():
            self.statusBar().showMessage("⚠️ Wait for the agent to finish before optimizing the prompt.", 3000)
            return

        original_text = text
        input_widget.setReadOnly(True)
        input_widget.setPlainText("⏳ Optymalizuję prompt...")

        # Disable both Optimize buttons while the request is in-flight
        _btn_labels = {
            "chat_optimize_btn": "✨ Optimize Prompt",
            "agent_optimize_btn": "✨ Optimize Prompt",
        }
        for attr, _label in _btn_labels.items():
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setEnabled(False)
                btn.setText("⏳ Optymalizuję...")

        messages = [
            {
                "role": "system",
                "content": (
                    "Jesteś niemym systemem do inżynierii promptów. Twój JEDYNY cel to przepisanie prompta na profesjonalną, "
                    "bogatą w kontekst i precyzyjną wersję dla LLM.\n\n"
                    "REGOŁY KRYTYCZNE:\n"
                    "1. ZWRÓĆ WYNIK TYLKO W TAGACH <optimized> ... </optimized>\n"
                    "2. NIE odpowiadaj na pytania i NIE wykonuj zadania.\n"
                    "3. NIE wpisuj żadnych wyjaśnień, powitań ani oryginalnego tekstu poza tagami."
                )
            },
            {"role": "user", "content": f"Przepisz ten prompt:\n\n{text}"}
        ]
        model = self._current_model()
        worker = ChatWorker(self.api, model, messages)
        worker.log_message.connect(self.append_log)

        def _restore_buttons():
            for attr, label in _btn_labels.items():
                btn = getattr(self, attr, None)
                if btn is not None:
                    btn.setEnabled(True)
                    btn.setText(label)

        def on_done(result):
            import re
            optimized = result.strip()
            
            # Wymuś ekstrakcję tylko ze środka tagów by odciąć wstępy ("Oto Twój prompt:", itp)
            match = re.search(r'<optimized>(.*?)</optimized>', optimized, re.DOTALL | re.IGNORECASE)
            if match:
                optimized = match.group(1).strip()
            else:
                # Fallback: usunięcie markdown klocków i prefiksów na wszelki wypadek
                optimized = re.sub(r'^```[\w]*\n', '', optimized)
                optimized = re.sub(r'\n```$', '', optimized)
                optimized = re.sub(r'(?i)^(Oto|Poniżej).*?:\s*\n', '', optimized).strip()

            if not optimized or len(optimized) < 5:
                # API returned empty — restore original instead of clearing the field
                self.append_log("[optimize_prompt] WARNING: empty result from API, restoring original.")
                input_widget.setPlainText(original_text)
                self.statusBar().showMessage("⚠️ Optimization returned empty result. Original prompt restored.", 4000)
            else:
                input_widget.setPlainText(optimized)
                self.statusBar().showMessage("✨ Prompt optimized.", 3000)
            input_widget.setReadOnly(False)
            if hasattr(input_widget, "restore_cursor_blink"):
                input_widget.restore_cursor_blink()
            input_widget.setFocus()
            cursor = input_widget.textCursor()
            cursor.movePosition(QTextCursor.End)
            input_widget.setTextCursor(cursor)
            _restore_buttons()
            self._optimize_worker = None

        def on_error(err):
            self.append_log(f"[optimize_prompt] ERROR: {err}")
            input_widget.setPlainText(original_text)
            input_widget.setReadOnly(False)
            if hasattr(input_widget, "restore_cursor_blink"):
                input_widget.restore_cursor_blink()
            self.statusBar().showMessage(f"❌ Optimization failed: {err[:80]}", 5000)
            _restore_buttons()
            self._optimize_worker = None

        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        self._optimize_worker = worker
        worker.start()

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
            cursor = self.console_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.console_display.setTextCursor(cursor)

        # Update chat streaming (Chat Mode)
        if getattr(self, 'chat_stream_needs_render', False):
            self.chat_stream_needs_render = False
            self._render_chat_display()

        # Update agent streaming (Agent Mode)
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
        saved_agent_name = conv_info[7] if len(conv_info) > 7 else ""
        
        # Restore Model selection globally
        if saved_model:
            self.model_combo.setCurrentText(saved_model)

        if mode == "agent":
            # Switch to Agent Tab
            self.tabs.setCurrentIndex(1)
            
            # Restore Profile selection
            if saved_profile:
                self.profile_combo.setCurrentText(saved_profile)
            
            if saved_agent_name:
                self.agent_name_input.setText(saved_agent_name)
                
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
            
            # CRITICAL: Set ID and scratchpad AFTER potential re-initialization
            # so create_assistant doesn't wipe them.
            self.current_agent_conversation_id = conv_id
            self.current_agent_scratchpad = conv_info[6] if len(conv_info) > 6 else ""
            
            self._render_chat()
            
        else:
            # Switch to standard Chat Tab
            self.tabs.setCurrentIndex(0)
            self.current_conversation_id = conv_id
            self.chat_display.clear()
            self.chat_history = []
            self._chat_messages = []
            self.current_chat_stream = ""

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
                    "model": self._current_model(),
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
