from PySide6.QtCore import QObject, Signal, QTimer, Slot
from PySide6.QtNetwork import QTcpSocket, QAbstractSocket

from network.protocol.json_stream import JsonStreamParser
from network.protocol.errors import ProtocolError
from core.logger import log


class TcpAdapter(QObject):
    """纯网络层 — 只做 TCP 收发和 JSON 解析。不持有业务 callback/dispatcher。"""

    connected = Signal()
    disconnected = Signal()
    connection_error = Signal(str)
    data_received = Signal(object)       # → ConnectionManager._on_data_received (UI线程)
    shutdown_finished = Signal()         # → thread.quit

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket: QTcpSocket | None = None
        self._stream = JsonStreamParser()
        self._host = ""
        self._port = 9001
        self._timeout_timer: QTimer | None = None

    @property
    def is_connected(self) -> bool:
        return self._socket is not None and self._socket.state() == QAbstractSocket.ConnectedState

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    # ════════════════ @Slot (TcpThread 内执行) ════════════════

    @Slot(str, int)
    def connect_to_host(self, host: str, port: int = 9001):
        self._host = host
        self._port = port
        log.debug(f"TCP → connecting to {host}:{port}")

        if self._socket:
            self._socket.abort()
            self._socket.deleteLater()
            self._socket = None

        self._socket = QTcpSocket(self)  # 在 TcpThread 创建
        self._socket.connected.connect(self.connected)
        self._socket.disconnected.connect(self.disconnected)
        self._socket.errorOccurred.connect(self._on_error)
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.connectToHost(host, port)

        if self._timeout_timer is None:
            self._timeout_timer = QTimer(self)
            self._timeout_timer.setInterval(1000)
            self._timeout_timer.timeout.connect(self._on_timer_tick)
        self._timeout_timer.start()

    @Slot(str)
    def send_message(self, message: str):
        if self._socket and self._socket.state() == QAbstractSocket.ConnectedState:
            # 心跳不写日志
            if "Heartbeat" not in message and "heartbeat" not in message:
                log.debug(f"[send] {self._host}:{self._port} {message[:200]}")
            self._socket.write(message.encode("utf-8"))

    @Slot()
    def shutdown(self):
        """清理所有 socket/timer (TcpThread 内执行), 完成后 emit shutdown_finished"""
        if self._timeout_timer:
            self._timeout_timer.stop()
            self._timeout_timer.deleteLater()
            self._timeout_timer = None
        if self._socket:
            self._socket.abort()
            self._socket.deleteLater()
            self._socket = None
        self.shutdown_finished.emit()

    @Slot()
    def disconnect_from_host(self):
        if self._timeout_timer:
            self._timeout_timer.stop()
        if self._socket:
            self._socket.disconnectFromHost()

    # ════════════════ 内部 (TcpThread) ════════════════

    def _on_timer_tick(self):
        """超时检查回调 — 仅发送信号, 由 UI 线程 ConnectionManager 处理"""
        self.data_received.emit({"_internal": "check_timeouts"})

    def _on_ready_read(self):
        if not self._socket:
            return
        data = bytes(self._socket.readAll())
        try:
            messages = self._stream.feed(data)
        except ProtocolError as e:
            log.error(f"RX decode error: {e}")
            self.connection_error.emit(str(e))
            self._socket.disconnectFromHost()
            return

        for msg in messages:
            # 高频推送不写磁盘: RobotStatus/RobotPosture/ProjectState
            ty = msg.get("ty", "")
            # publish/Error db=[] 是空推送, 不写日志
            is_empty_error = (ty == "publish/Error" and not msg.get("db"))
            is_heartbeat = ("Heartbeat" in ty or "heartbeat" in ty)
            if not is_heartbeat and (("id" in msg) or (ty == "publish/Log") or (ty == "publish/Error" and not is_empty_error)):
                import json as _json
                log.debug(f"[recv] {self._host}:{self._port} {_json.dumps(msg, ensure_ascii=False)}")
            self.data_received.emit(msg)

    def _on_error(self, error: QAbstractSocket.SocketError):
        msg = self._socket.errorString() if self._socket else str(error)
        self.connection_error.emit(msg)
