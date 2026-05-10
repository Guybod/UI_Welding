import socket

from PySide6.QtWidgets import QComboBox, QPushButton, QHBoxLayout, QWidget
from PySide6.QtCore import Signal

from core.connection_config import LocalNetworkInterface

# 虚拟网卡关键词
VIRTUAL_KEYWORDS = [
    "vmware", "virtual", "docker", "wsl", "hyper-v", "vpn",
    "virtualbox", "loopback", "tunnel", "pseudo",
]


def _is_virtual(name: str, desc: str) -> bool:
    text = (name + " " + desc).lower()
    return any(kw in text for kw in VIRTUAL_KEYWORDS)


def _is_ignored(ipv4: str) -> bool:
    return ipv4 in ("127.0.0.1", "0.0.0.0") or ipv4.startswith("169.254.")


def _enumerate_interfaces() -> list[LocalNetworkInterface]:
    import psutil
    result = []
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        ipv4 = ""
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ipv4 = addr.address
                break
        if not ipv4 or _is_ignored(ipv4):
            continue

        stat = stats.get(name)
        is_up = stat.isup if stat else True
        result.append(LocalNetworkInterface(
            name=name,
            description=name,
            ipv4=ipv4,
            is_up=is_up,
            is_loopback=(ipv4 == "127.0.0.1"),
            is_virtual=_is_virtual(name, name),
        ))
    return result


class NetworkInterfaceSelector(QWidget):
    """本机网卡下拉选择器"""

    interface_selected = Signal(LocalNetworkInterface)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(350)
        layout.addWidget(self._combo, stretch=1)

        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self._refresh_btn)

        self.refresh()

    def refresh(self):
        self._combo.clear()
        interfaces = _enumerate_interfaces()
        if not interfaces:
            self._combo.addItem("(未检测到网卡)", None)
            return

        for iface in interfaces:
            label = f"{iface.name} - {iface.ipv4}"
            if iface.is_virtual:
                label += "  [虚拟网卡]"
            if not iface.is_up:
                label += "  [未启用]"
            self._combo.addItem(label, iface)

    def current_interface(self) -> LocalNetworkInterface | None:
        return self._combo.currentData()
