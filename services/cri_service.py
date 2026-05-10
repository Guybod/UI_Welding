from PySide6.QtCore import QObject, Signal, QTimer

from core.thread_manager import UdpThread
from network.udp_cri_adapter import UdpCriAdapter
from network.connection_manager import ConnectionManager


class CriService(QObject):
    """CRI 实时数据服务 — 管理 UdpThread, 通过 TCP 9001 发送 StartDataPush/StopDataPush"""

    cri_started = Signal()
    cri_stopped = Signal()
    cri_frame_received = Signal(object)
    bind_error = Signal(str)

    # → UdpCriAdapter @Slot
    _sig_bind = Signal(str, int)

    def __init__(self, connection_manager: ConnectionManager, parent=None):
        super().__init__(parent)
        self._cm = connection_manager
        self._udp_thread: UdpThread | None = None
        self._udp_adapter: UdpCriAdapter | None = None
        self._config = None
        self._enabled = False

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def start(self, config):
        self._config = config

        if self._udp_thread:
            self._udp_thread.quit()
            self._udp_thread.wait(3000)
            self._udp_thread = None

        self._udp_thread = UdpThread()
        self._udp_adapter = UdpCriAdapter()
        self._udp_adapter.moveToThread(self._udp_thread)

        self._sig_bind.connect(self._udp_adapter.bind_and_listen)
        self._udp_adapter.bind_error.connect(self.bind_error.emit)
        self._udp_adapter.datagram_received.connect(self.cri_frame_received.emit)

        self._udp_thread.started.connect(
            lambda: self._sig_bind.emit(config.local_ip, config.udp_port)
        )
        self._udp_thread.start()

        # StopDataPush → StartDataPush (通过 TCP)
        def _do_start():
            self._cm.send_raw({
                "id": 0, "ty": "CRI/StartDataPush",
                "db": {
                    "ip": config.local_ip, "port": config.udp_port,
                    "duration": 2, "mask": 65535, "highPercision": True,
                }
            })
            self._enabled = True
            self._cm.set_cri_push_enabled(True)
            self.cri_started.emit()

        self._cm.send_raw({"id": 0, "ty": "CRI/StopDataPush"})
        QTimer.singleShot(200, _do_start)

    def stop(self):
        self._cm.send_raw({"id": 0, "ty": "CRI/StopDataPush"})
        self._enabled = False
        self._cm.set_cri_push_enabled(False)
        if self._udp_thread:
            self._udp_thread.quit()
            self._udp_thread.wait(3000)
            self._udp_thread = None
        self._udp_adapter = None
        self.cri_stopped.emit()
