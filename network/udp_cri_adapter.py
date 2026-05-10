from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QUdpSocket, QHostAddress

from network.protocol.cri_parser import CriParser
from core.logger import log


class UdpCriAdapter(QObject):
    """UDP 9030 CRI 实时数据接收 — 在 UdpThread 内创建和使用"""

    datagram_received = Signal(object)   # CriFrame dict
    bind_error = Signal(str)
    dropped_count_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket: QUdpSocket | None = None
        self._parser = CriParser()
        self._dropped = 0
        self._local_ip = ""
        self._local_port = 0

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @Slot(str, int)
    def bind_and_listen(self, local_ip: str, local_port: int):
        self._local_ip = local_ip
        self._local_port = local_port

        if self._socket:
            self._socket.abort()
            self._socket.deleteLater()

        self._socket = QUdpSocket(self)
        if not self._socket.bind(QHostAddress(local_ip), local_port):
            self.bind_error.emit(f"UDP bind 失败: {local_ip}:{local_port}")
            return

        self._socket.readyRead.connect(self._on_ready_read)
        log.debug(f"UDP listening on {local_ip}:{local_port}")

    def _on_ready_read(self):
        if not self._socket:
            return
        while self._socket.hasPendingDatagrams():
            data, host, port = self._socket.readDatagram(
                self._socket.pendingDatagramSize()
            )
            if len(data) != CriParser.EXPECTED_SIZE:
                self._dropped += 1
                self.dropped_count_changed.emit(self._dropped)
                continue

            try:
                frame = self._parser.parse(data)
                self.datagram_received.emit(frame)
            except Exception as e:
                self._dropped += 1
                self.dropped_count_changed.emit(self._dropped)
                log.debug(f"CRI parse error: {e}")

    @Slot()
    def shutdown(self):
        if self._socket:
            self._socket.abort()
            self._socket.deleteLater()
            self._socket = None
