from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPlainTextEdit

from app.i18n import I18nManager, tr
from app.ui_log import append_ui_log


class ExecutionLogPanel(QWidget):
    """执行日志面板 — 显示校验结果/执行顺序/TCP指令/CRI状态, 支持双语"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("executionLogPanel")
        self.setMaximumHeight(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(tr("node_log_title"))
        self._title.setStyleSheet("font-weight: bold; padding: 4px 8px;")
        layout.addWidget(self._title)

        self._log = QPlainTextEdit()
        self._log.setObjectName("executionLog")
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        layout.addWidget(self._log)

        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def clear(self) -> None:
        self._log.clear()

    def append_line(self, msg: str, *, source: str = "Node") -> str:
        return append_ui_log(self._log, msg, source=source)

    def _on_language_changed(self, lang: str):
        self._title.setText(tr("node_log_title"))
