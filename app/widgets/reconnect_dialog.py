from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, QTimer, Signal


class ReconnectDialog(QDialog):
    """掉线弹窗 — 显示重连状态, 只能由 [停止重连并返回主页面] 关闭"""

    stop_requested = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接已断开")
        self.setMinimumSize(420, 280)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)

        self._config = config

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._title = QLabel("机器人连接已断开，正在尝试重新连接...")
        self._title.setStyleSheet("font-size: 16px; font-weight: bold; color: #e94560;")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._info = QLabel()
        self._info.setStyleSheet("color: #a0a0a0; font-size: 13px;")
        layout.addWidget(self._info)

        self._error = QLabel("")
        self._error.setStyleSheet("color: #ff6666; font-size: 12px;")
        layout.addWidget(self._error)

        layout.addStretch()

        self._btn_stop = QPushButton("停止重连并返回主页面")
        self._btn_stop.setFixedHeight(38)
        self._btn_stop.setCursor(Qt.PointingHandCursor)
        self._btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #e94560; color: white; border: none;
                border-radius: 19px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ff5777; }
        """)
        self._btn_stop.clicked.connect(self._on_stop)
        layout.addWidget(self._btn_stop)

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.accept)

    def update_status(self, attempt: int, next_delay: float, last_error: str = ""):
        robot_ip = self._config.robot_ip if self._config else "?"
        local_ip = self._config.local_ip if self._config else "?"
        udp = self._config.udp_port if self._config else "?"

        self._info.setText(
            f"机器人 IP：{robot_ip}\n"
            f"本机 IP：{local_ip}\n"
            f"UDP 端口：{udp}\n\n"
            f"重连次数：第 {attempt} 次\n"
            f"下一次重连：{next_delay:.0f} 秒后"
        )
        if last_error:
            self._error.setText(f"最近错误：{last_error}")
        else:
            self._error.setText("")

    def mark_reconnected(self, cri_restored: bool = False):
        msg = "已重连，订阅已恢复"
        if cri_restored:
            msg += "，CRI 实时数据推送已恢复"
        self._title.setText(msg)
        self._title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00cc66;")
        self._info.setText("此窗口即将自动关闭...")
        self._btn_stop.hide()
        self._auto_close_timer.start(1500)

    def _on_stop(self):
        self._auto_close_timer.stop()
        self.stop_requested.emit()
        self.reject()

    def closeEvent(self, event):
        event.ignore()
