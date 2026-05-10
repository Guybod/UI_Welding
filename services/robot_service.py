from PySide6.QtCore import QObject

from network.connection_manager import ConnectionManager
from network.tcp_adapter import TcpAdapter


class RobotService(QObject):
    """机器人基础服务 — Part 5: 只读订阅"""

    def __init__(self, connection_manager: ConnectionManager, parent=None):
        super().__init__(parent)
        self._cm = connection_manager

    def subscribe_status(self, callback):
        ad = self._cm.adapter
        if ad:
            ad.subscribe("publish/RobotStatus", callback)

    def subscribe_error(self, callback):
        ad = self._cm.adapter
        if ad:
            ad.subscribe("publish/Error", callback)

    def subscribe_log(self, callback):
        ad = self._cm.adapter
        if ad:
            ad.subscribe("publish/Log", callback)
