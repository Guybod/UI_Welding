from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit
from PySide6.QtCore import Qt


class ExecutionLogPanel(QWidget):
    """执行日志面板 — 占位, 后续显示校验结果/执行顺序/TCP指令/CRI状态"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("executionLogPanel")
        self.setMaximumHeight(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("执行日志")
        title.setStyleSheet("font-weight: bold; padding: 4px 8px;")
        layout.addWidget(title)

        self._log = QPlainTextEdit()
        self._log.setObjectName("executionLog")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        layout.addWidget(self._log)
