from PySide6.QtWidgets import QStatusBar, QLabel
from app.i18n import I18nManager, tr


class StatusBar(QStatusBar):
    """底部状态栏 — 连接状态 + 位姿数据源（CRI / 订阅）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conn_label = QLabel(tr("status_disconnected"))
        self._pose_label = QLabel("")
        self._pose_label.setStyleSheet("color: #8b9cc8; padding-left: 12px;")
        self.addPermanentWidget(self._conn_label)
        self.addPermanentWidget(self._pose_label)
        I18nManager.instance().language_changed.connect(self._refresh)

    def set_connection_status(self, text: str):
        self._conn_label.setText(text)

    def set_pose_source(self, text: str):
        """位姿来源提示，例如「位姿: CRI」或「位姿: 订阅」；空串则隐藏。"""
        self._pose_label.setText(text)
        self._pose_label.setVisible(bool(text))

    def _refresh(self, lang: str):
        conn = self._conn_label.text()
        if conn in ("未连接", "Disconnected"):
            self._conn_label.setText(tr("status_disconnected"))
        pose = self._pose_label.text()
        if not pose:
            return
        if "CRI" in pose or "cri" in pose.lower():
            self._pose_label.setText(tr("status_pose_line_cri"))
        elif "订阅" in pose or "Sub" in pose:
            self._pose_label.setText(tr("status_pose_line_subscribe"))
