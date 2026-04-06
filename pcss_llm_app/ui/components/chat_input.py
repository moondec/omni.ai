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
        self.setFixedHeight(80)
        self.setAcceptDrops(True)
        self.workspace_path = "" # To be set by main app for relative paths

    def keyPressEvent(self, event):
        # Shift+Enter is default newline, Enter is submit
        if event.key() in [Qt.Key_Return, Qt.Key_Enter] and not (event.modifiers() & Qt.ShiftModifier):
            self.send_requested.emit()
            return

        # Up arrow at the beginning of document navigates history
        if event.key() == Qt.Key_Up:
            cursor = self.textCursor()
            if cursor.blockNumber() == 0:
                self.history_up_requested.emit()
                return

        # Down arrow at the end of document navigates history
        if event.key() == Qt.Key_Down:
            cursor = self.textCursor()
            if cursor.blockNumber() == self.document().blockCount() - 1:
                self.history_down_requested.emit()
                return

        super().keyPressEvent(event)

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
