from PySide6.QtWidgets import QTextEdit


class ConsoleWidget(QTextEdit):
    """日志/终端输出窗口 — 只读"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumHeight(150)
        self.setStyleSheet(
            "background-color: #0d1b36; color: #a0a0a0;"
            "border: 1px solid #0f3460; font-size: 11px;"
        )

    def append_log(self, text: str):
        self.append(text)
        # keep scroll at bottom
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
