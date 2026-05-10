from PySide6.QtWidgets import QStatusBar, QLabel


class StatusBar(QStatusBar):
    """底部状态栏 — 显示连接状态"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._label = QLabel("未连接")
        self.addPermanentWidget(self._label)

    def set_connection_status(self, text: str):
        self._label.setText(text)
