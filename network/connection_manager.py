import json
import time
from PySide6.QtCore import QObject, Signal, QTimer

from core.connection_config import ConnectionConfig
from core.logger import log
from core.thread_manager import TcpThread
from network.tcp_adapter import TcpAdapter
from network.protocol.errors import NetworkDisconnectedError

BACKOFF_SEQUENCE = [1, 2, 4, 8]


class ConnectionManager(QObject):
    """TCP 9001 连接生命周期管理 + 自动重连 + 请求/响应 + 订阅分发。全在 UI 线程。"""

    _sig_connect = Signal(str, int)
    _sig_send = Signal(str)
    _sig_shutdown = Signal()

    connection_state_changed = Signal(str)
    connection_failed = Signal(str)
    robot_type_ready = Signal(str)
    status_bar_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: ConnectionConfig | None = None
        self._thread: TcpThread | None = None
        self._adapter: TcpAdapter | None = None

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        self._reconnect_attempt = 0
        self._dialog = None
        self._cri_push_enabled = False
        self._was_connected = False
        self._first_connect = True

        # ── 请求/响应管理 (UI 线程) ──
        self._seq = 0
        self._pending: dict[int | str, dict] = {}
        self._silent_log_ids: set[int] = set()

        # ── 订阅回调 (UI 线程) ──
        self._subscribe_callbacks: dict[str, list] = {}
        self._logged_publish_recv: set[str] = set()

    @property
    def adapter(self) -> TcpAdapter | None:
        return self._adapter

    @property
    def is_connected(self) -> bool:
        return self._adapter is not None and self._adapter.is_connected

    @property
    def cri_push_enabled(self) -> bool:
        return self._cri_push_enabled

    def set_cri_push_enabled(self, v: bool):
        self._cri_push_enabled = v

    # ════════════════ 连接 ════════════════

    def connect_to_robot(self, config: ConnectionConfig):
        self._config = config
        self._reconnect_attempt = 0
        log.info("[Connection] connect_to_robot %s:9001", config.robot_ip)
        self._do_connect()

    def _do_connect(self):
        self._cleanup_thread()

        self._thread = TcpThread()
        self._adapter = TcpAdapter()
        self._adapter.moveToThread(self._thread)

        self._sig_connect.connect(self._adapter.connect_to_host)
        self._sig_send.connect(self._adapter.send_message)
        self._sig_shutdown.connect(self._adapter.shutdown)

        self._adapter.set_traffic_log_filter(self._traffic_log_filter)
        self._adapter.data_received.connect(self._on_data_received)
        self._adapter.connected.connect(self._on_connected)
        self._adapter.disconnected.connect(self._on_disconnected)
        self._adapter.connection_error.connect(self._on_socket_error)
        # 不在此连接 shutdown_finished → thread.quit，quit 由 disconnect() 直接调用。
        # 如果走 Signal/Slot 跨线程连接，shutdown_finished 在 TcpThread emit 后
        # 会以 queued 方式投递到 UI 线程，但此时 UI 线程正阻塞在 wait() 中，
        # 永远无法处理 quit 事件，形成死锁。

        self._thread.started.connect(
            lambda: self._sig_connect.emit(self._config.robot_ip, 9001)
        )
        self._thread.start()
        self.connection_state_changed.emit("connecting")

        if self._first_connect:
            if hasattr(self, '_connect_timeout') and self._connect_timeout is not None:
                self._connect_timeout.stop()
                self._connect_timeout.deleteLater()
            self._connect_timeout = QTimer(self)
            self._connect_timeout.setSingleShot(True)
            self._connect_timeout.timeout.connect(self._on_first_connect_timeout)
            self._connect_timeout.start(3000)

    def _cleanup_thread(self):
        if self._adapter:
            for sig in [self._sig_connect, self._sig_send, self._sig_shutdown]:
                try:
                    sig.disconnect(self._adapter)
                except (TypeError, RuntimeError):
                    pass
            self._adapter.deleteLater()
        if self._thread:
            if self._thread.isRunning():
                self._sig_shutdown.emit()
                self._thread.quit()
                self._thread.wait(3000)
        self._adapter = None
        self._thread = None

    def _on_first_connect_timeout(self):
        if self._first_connect:
            log.warning(
                "[Connection] first_connect_timeout %s:9001",
                self._config.robot_ip,
            )
            self.connection_failed.emit(f"连接 {self._config.robot_ip}:9001 超时 (3秒)")
            self.disconnect()
            self._first_connect = False

    # ════════════════ 断线 ════════════════

    def disconnect(self):
        log.info("[Connection] disconnect")
        if hasattr(self, '_connect_timeout'):
            self._connect_timeout.stop()
        self._reconnect_timer.stop()
        self._subscribe_callbacks.clear()
        self._logged_publish_recv.clear()
        self._drain_pending(NetworkDisconnectedError("连接断开"))
        if self._adapter:
            # 断开业务信号（不参与 shutdown 流程）
            for sig_name in ["data_received", "connected", "disconnected",
                             "connection_error"]:
                try:
                    sig = getattr(self._adapter, sig_name)
                    sig.disconnect()
                except (TypeError, RuntimeError):
                    pass
            self._sig_shutdown.emit()
            self._adapter.deleteLater()
        if self._thread:
            self._thread.quit()                  # 直接调用，线程安全（避免跨线程信号死锁）
            finished = self._thread.wait(3000)
            if not finished:
                log.warning("[Connection] TcpThread did not exit within 3s, terminating")
                self._thread.terminate()
                self._thread.wait(1000)
        self._adapter = None
        self._thread = None

    def stop_reconnect(self):
        log.info("[Connection] stop_reconnect")
        self._reconnect_timer.stop()
        self.disconnect()
        self._reconnect_attempt = 0
        self._was_connected = False
        if self._dialog:
            self._dialog.accept()
            self._dialog = None

    # ════════════════ 重连 ════════════════

    def _on_disconnected(self):
        if self._first_connect:
            return
        if not self._was_connected:
            return
        self._start_reconnect()

    def _on_socket_error(self, msg: str):
        if self._first_connect:
            log.warning("[Connection] socket_error (first_connect): %s", msg)
            self.connection_failed.emit(msg)
            self.disconnect()
            self._first_connect = False
            return
        if self._was_connected:
            self._start_reconnect()

    def _start_reconnect(self):
        if not self._config:
            return
        self.connection_state_changed.emit("reconnecting")
        self._show_dialog()
        delay = BACKOFF_SEQUENCE[min(self._reconnect_attempt, len(BACKOFF_SEQUENCE) - 1)] \
            if self._reconnect_attempt < len(BACKOFF_SEQUENCE) else 10
        attempt = self._reconnect_attempt + 1
        log.info("[Connection] reconnect start attempt=%d delay=%ss", attempt, delay)
        self._reconnect_timer.start(int(delay * 1000))
        self._reconnect_attempt += 1
        if self._dialog:
            self._dialog.update_status(self._reconnect_attempt, delay, "")

    def _try_reconnect(self):
        if not self._config:
            return
        self._do_connect()

    # ════════════════ 连接成功 ════════════════

    def _on_connected(self):
        if hasattr(self, '_connect_timeout'):
            self._connect_timeout.stop()
        was_reconnect = self._dialog is not None
        self._first_connect = False
        self._was_connected = True
        self._reconnect_attempt = 0
        log.info("[Connection] connected")
        if was_reconnect:
            log.info("[Connection] reconnect success")
        self.connection_state_changed.emit("connected")
        if self._dialog:
            self._dialog.mark_reconnected(self._cri_push_enabled)
            self._dialog = None

    # ════════════════ 数据接收与分发 (UI 线程) ════════════════

    def _on_data_received(self, msg: dict):
        if not isinstance(msg, dict):
            return

        # 内部信号: 超时检查
        if msg.get("_internal") == "check_timeouts":
            self._check_timeouts()
            return

        ty = msg.get("ty", "")

        # 推送: publish/*（控制器推送常带 "id": null，不能走命令响应分支）
        if ty.startswith("publish/"):
            self._dispatch_publish(msg)
            return

        # 命令响应: 有效 id
        if msg.get("id") is not None:
            self._dispatch_response(msg)

    def _traffic_log_filter(self, msg: dict, direction: str) -> bool:
        """返回 True 表示写入系统日志（log/ 文件）。"""
        if direction not in ("send", "recv"):
            return True
        rid = msg.get("id")
        if rid is None:
            return True
        try:
            rid = int(rid)
        except (TypeError, ValueError):
            return True
        return rid not in self._silent_log_ids

    def _dispatch_response(self, msg: dict):
        req_id = msg.get("id")
        if req_id is not None:
            try:
                self._silent_log_ids.discard(int(req_id))
            except (TypeError, ValueError):
                pass
        req = self._pending.pop(req_id, None)
        if req is None:
            return
        err = msg.get("err")
        if err:
            cb = req.get("on_error")
            if callable(cb):
                cb(Exception(f"RobotError: {err}"))
        else:
            cb = req.get("on_response")
            if callable(cb):
                cb(msg.get("db", {}))

    def _dispatch_publish(self, msg: dict):
        ty = msg.get("ty", "")
        err = msg.get("err")
        if err:
            log.warning("[Connection] publish rejected topic=%s err=%s", ty, err)
            return
        db = msg.get("db") or {}

        if ty not in self._logged_publish_recv:
            self._logged_publish_recv.add(ty)
            db_keys = list(db.keys()) if isinstance(db, dict) else []
            log.info(
                "[Connection] publish recv topic=%s db_keys=%s",
                ty, db_keys[:12],
            )

        if ty == "publish/RobotStatus":
            self._on_robot_status(db)
        elif ty == "publish/Error":
            pass  # 由 subscribe callback 处理, 不做弹窗
        elif ty == "publish/Log":
            pass

        for cb in self._subscribe_callbacks.get(ty, []):
            try:
                cb(db)
            except Exception as e:
                log.warning(
                    "[Connection] publish callback failed topic=%s err=%r",
                    ty, e,
                )
                pass

    def _on_robot_status(self, db: dict):
        robot_type = db.get("type", "")
        if robot_type:
            self.robot_type_ready.emit(robot_type)
        state = db.get("state", -1)
        mode = db.get("mode", -1)
        self.status_bar_message.emit(
            f"已连接 | 型号: {robot_type} | 模式: {mode} | 状态: {state}"
        )

    # ════════════════ 请求/响应 (UI 线程) ════════════════

    def send_call(
        self,
        ty: str,
        db,
        on_response,
        on_error,
        timeout: float = 5.0,
        *,
        log_traffic: bool = True,
    ):
        if not self._adapter:
            on_error(Exception("未连接"))
            return

        self._seq += 1
        req_id = self._seq
        if not log_traffic:
            self._silent_log_ids.add(req_id)
        self._pending[req_id] = {
            "ty": ty,
            "on_response": on_response,
            "on_error": on_error,
            "created_at": time.monotonic(),
            "timeout": timeout,
            "log_traffic": log_traffic,
        }
        msg = json.dumps({"id": req_id, "ty": ty, "db": db}, ensure_ascii=False)
        self._sig_send.emit(msg)

    def send_subscribe(self, topic: str, callback, interval_ms: int = 0):
        if callback is not None:
            if topic not in self._subscribe_callbacks:
                self._subscribe_callbacks[topic] = []
            self._subscribe_callbacks[topic].append(callback)
        msg = json.dumps({"ty": topic, "tc": interval_ms}, ensure_ascii=False)
        log.info("[Connection] subscribe send topic=%s tc=%s", topic, interval_ms)
        self._sig_send.emit(msg)

    def send_raw(self, obj: dict):
        self._sig_send.emit(json.dumps(obj, ensure_ascii=False))

    def _drain_pending(self, error: Exception):
        pending_count = len(self._pending)
        if pending_count:
            log.warning(
                "[Connection] drain_pending reason=%s pending=%d",
                error, pending_count,
            )
        for req in list(self._pending.values()):
            try:
                req["on_error"](error)
            except Exception as e:
                log.warning(
                    "[Connection] drain_pending on_error callback failed: %r", e,
                )
                pass
        self._pending.clear()
        self._silent_log_ids.clear()

    def _check_timeouts(self):
        now = time.monotonic()
        timed_out = [
            rid for rid, req in self._pending.items()
            if now - req["created_at"] > req["timeout"]
        ]
        for rid in timed_out:
            self._silent_log_ids.discard(rid)
            req = self._pending.pop(rid, None)
            if req:
                log.warning(
                    "[Connection] request timeout id=%s ty=%s",
                    rid, req["ty"],
                )
                try:
                    req["on_error"](TimeoutError(f"Request timeout: id={rid}, ty={req['ty']}"))
                except Exception as e:
                    log.warning(
                        "[Connection] timeout on_error callback failed id=%s: %r",
                        rid, e,
                    )
                    pass

    # ════════════════ 弹窗 ════════════════

    def _show_dialog(self):
        if self._dialog:
            return
        from app.widgets.reconnect_dialog import ReconnectDialog
        self._dialog = ReconnectDialog(self._config)
        self._dialog.stop_requested.connect(self.stop_reconnect)
        self._dialog.show()
