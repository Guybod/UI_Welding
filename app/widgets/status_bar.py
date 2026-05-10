from PySide6.QtWidgets import QStatusBar, QLabel
from app.i18n import I18nManager, tr


class StatusBar(QStatusBar):
    """底部状态栏 — 显示连接状态, 支持双语"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel(tr("status_disconnected"))
        self.addPermanentWidget(self._label)
        I18nManager.instance().language_changed.connect(self._refresh)

    def set_connection_status(self, text: str):
        self._label.setText(text)

    def _refresh(self, lang: str):
        if self._label.text() in ("未连接", "Disconnected", "已连接", "Connected",
                                   "重连中...", "Reconnecting..."):
            self._label.setText(tr("status_disconnected"))
