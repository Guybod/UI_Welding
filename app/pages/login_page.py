from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
)
from PySide6.QtCore import Signal, Qt

from core.connection_config import ConnectionConfig
from core.connection_config import pick_available_udp_port
from app.widgets.network_interface_selector import NetworkInterfaceSelector


class LoginPage(QWidget):
    """登录连接界面 — 填写 IP/网卡/UDP端口, 点击连接进入主界面"""

    connect_requested = Signal(ConnectionConfig)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        # 标题
        title = QLabel("Codroid 机器人控制终端")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #e94560;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        version = QLabel("v2.0.0")
        version.setStyleSheet("font-size: 12px; color: #888888;")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        layout.addSpacing(20)

        form_width = 420
        form_layout = QVBoxLayout()
        form_layout.setAlignment(Qt.AlignCenter)

        # 机器人 IP
        ip_row = QHBoxLayout()
        ip_row.addWidget(QLabel("机器人 IP:"))
        self._robot_ip = QLineEdit("192.168.1.136")
        self._robot_ip.setFixedWidth(250)
        ip_row.addWidget(self._robot_ip)
        ip_row.addStretch()
        form_layout.addLayout(ip_row)

        # 本机网卡
        nic_row = QHBoxLayout()
        nic_row.addWidget(QLabel("本机网卡:"))
        self._nic_selector = NetworkInterfaceSelector()
        nic_row.addWidget(self._nic_selector)
        form_layout.addLayout(nic_row)

        # UDP 端口
        port_row = QHBoxLayout()
        port_row.addWidget(QLabel("UDP 端口:"))
        self._udp_port = QLineEdit()
        self._udp_port.setFixedWidth(100)
        try:
            auto_port = pick_available_udp_port()
            self._udp_port.setText(str(auto_port))
        except RuntimeError:
            self._udp_port.setPlaceholderText("请手动输入")
        port_row.addWidget(self._udp_port)
        port_row.addStretch()
        form_layout.addLayout(port_row)

        # 居中表单
        form_wrapper = QHBoxLayout()
        form_wrapper.addStretch()
        form_wrapper.addLayout(form_layout)
        form_wrapper.addStretch()
        layout.addLayout(form_wrapper)

        layout.addSpacing(20)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)
        btn_row.setSpacing(16)

        self._btn_connect = QPushButton("连接机器人")
        self._btn_connect.setFixedHeight(40)
        self._btn_connect.setMinimumWidth(140)
        self._btn_connect.setCursor(Qt.PointingHandCursor)
        self._btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #e94560; color: white; border: none;
                border-radius: 20px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ff5777; }
        """)
        self._btn_connect.clicked.connect(self._on_connect)
        btn_row.addWidget(self._btn_connect)


        layout.addLayout(btn_row)

        layout.addSpacing(10)

        # 状态
        self._status = QLabel("准备连接")
        self._status.setStyleSheet("color: #888888; font-size: 12px;")
        self._status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._status)

    def _on_connect(self):
        robot_ip = self._robot_ip.text().strip()
        nic = self._nic_selector.current_interface()
        if not robot_ip:
            QMessageBox.warning(self, "输入错误", "请输入机器人 IP 地址")
            return
        if nic is None or not nic.ipv4:
            QMessageBox.warning(self, "输入错误", "请选择本机网卡")
            return

        try:
            port = int(self._udp_port.text().strip())
            if port < 10000 or port > 65535:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "输入错误", "UDP 端口需在 10000~65535 范围")
            return

        config = ConnectionConfig(
            robot_ip=robot_ip,
            local_ip=nic.ipv4,
            local_interface=nic,
            udp_port=port,
        )
        self._status.setText("正在连接...")
        self._btn_connect.setEnabled(False)
        self.connect_requested.emit(config)

    def set_status(self, text: str):
        self._status.setText(text)

    def set_enabled(self, enabled: bool):
        self._btn_connect.setEnabled(enabled)
