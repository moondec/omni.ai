from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QTextCursor
import os

class ChatInputWidget(QTextEdit):
    send_requested = Signal()
    history_up_requested = Signal()
    history_down_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setMinimumHeight(80)
        self.setMaximumHeight(240)
        self.setAcceptDrops(True)
        self.setCursorWidth(2)  # Make cursor clearly visible and blinking
        self.workspace_path = "" # To be set by main app for relative paths
        self._browsing_history = False  # True when navigating through prompt history

    def keyPressEvent(self, event):
        # Shift+Enter is default newline, Enter is submit
        if event.key() in [Qt.Key_Return, Qt.Key_Enter] and not (event.modifiers() & Qt.ShiftModifier):
            self.send_requested.emit()
            return

        # Up arrow navigates history when:
        # - input is empty, OR
        # - we are already browsing history (loaded a previous entry)
        if event.key() == Qt.Key_Up:
            if not self.toPlainText().strip() or self._browsing_history:
                self.history_up_requested.emit()
                return

        # Down arrow navigates history when:
        # - input is empty, OR
        # - we are already browsing history
        if event.key() == Qt.Key_Down:
            if not self.toPlainText().strip() or self._browsing_history:
                self.history_down_requested.emit()
                return

        # Any other key press exits history browsing mode
        self._browsing_history = False

        super().keyPressEvent(event)

    def enter_history_mode(self):
        """Called by MainWindow when a history entry is loaded into the widget."""
        self._browsing_history = True

    def exit_history_mode(self):
        """Called when the user exits history (e.g. Down past the newest entry)."""
        self._browsing_history = False

    def restore_cursor_blink(self):
        """Force-restart the cursor blink timer.

        Qt's QTextEdit loses its cursor blink animation after setEnabled(False/True)
        or setReadOnly(True/False) cycles. This workaround toggles cursorWidth to
        restart the internal blink timer.
        """
        self.setCursorWidth(0)
        self.setCursorWidth(2)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            cursor = self.textCursor()
            paths = []
            
            for url in urls:
                local_path = os.path.abspath(url.toLocalFile())
                if self.workspace_path and local_path.startswith(self.workspace_path):
                    rel_path = os.path.relpath(local_path, self.workspace_path)
                    paths.append(rel_path)
                else:
                    paths.append(local_path)
            
            cursor.insertText(" ".join(paths))
            self.setFocus()
        else:
            super().dropEvent(event)
