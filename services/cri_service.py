import time

from PySide6.QtCore import QObject, Signal, QTimer

from core.logger import log
from core.thread_manager import UdpThread
from network.udp_cri_adapter import UdpCriAdapter
from network.connection_manager import ConnectionManager

# 与 StartDataPush duration=4ms 对齐；连续 N 次无完整帧则切换订阅（直至下次连接）
_CRI_FRAME_TICK_MS = 4
_CRI_MISS_FRAMES_THRESHOLD = 125
_CRI_START_DATA_PUSH_TIMEOUT_S = 3.0
_CRI_STARTUP_GRACE_S = 0.8


def _is_complete_cri_frame(frame: dict) -> bool:
    joint = frame.get("joint_position") or []
    return len(joint) >= 6


class CriService(QObject):
    """CRI 实时数据服务 — 管理 UdpThread, 通过 TCP 9001 发送 StartDataPush/StopDataPush"""

    cri_started = Signal()
    cri_stopped = Signal()
    cri_frame_received = Signal(object)
    cri_udp_stale = Signal()  # 连续多帧无完整 CRI 报文
    bind_error = Signal(str)

    _sig_bind = Signal(str, int)
    _sig_shutdown_udp = Signal()

    def __init__(self, connection_manager: ConnectionManager, parent=None):
        super().__init__(parent)
        self._cm = connection_manager
        self._udp_thread: UdpThread | None = None
        self._udp_adapter: UdpCriAdapter | None = None
        self._config = None
        self._enabled = False
        self._miss_streak = 0
        self._stale_notified = False
        self._grace_until_mono = 0.0
        self._got_frame_since_tick = False
        self._frame_tick = QTimer(self)
        self._frame_tick.setInterval(_CRI_FRAME_TICK_MS)
        self._frame_tick.timeout.connect(self._on_frame_tick)

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def disarm_watchdog(self) -> None:
        self._frame_tick.stop()
        self._miss_streak = 0
        self._stale_notified = False
        self._grace_until_mono = 0.0
        self._got_frame_since_tick = False

    def _arm_watchdog(self) -> None:
        self._miss_streak = 0
        self._stale_notified = False
        self._got_frame_since_tick = False
        self._grace_until_mono = time.monotonic() + _CRI_STARTUP_GRACE_S
        self._frame_tick.start()

    def _emit_stale_if_needed(self, detail: str) -> None:
        if self._miss_streak < _CRI_MISS_FRAMES_THRESHOLD or self._stale_notified:
            return
        self._stale_notified = True
        log.warning(
            "[CRI] %d consecutive incomplete/missing frames (threshold=%d), %s",
            self._miss_streak,
            _CRI_MISS_FRAMES_THRESHOLD,
            detail,
        )
        self.cri_udp_stale.emit()

    def _record_miss(self, detail: str) -> None:
        if not self._enabled or time.monotonic() < self._grace_until_mono:
            return
        self._miss_streak += 1
        self._emit_stale_if_needed(detail)

    def _on_frame_tick(self) -> None:
        if not self._enabled:
            return
        if self._got_frame_since_tick:
            self._got_frame_since_tick = False
            return
        self._record_miss("no complete frame in tick")

    def _on_frame_incomplete(self, reason: str) -> None:
        self._record_miss(f"incomplete: {reason}")

    def _on_datagram_received(self, frame: dict) -> None:
        if not _is_complete_cri_frame(frame):
            self._record_miss("incomplete:joints")
            return
        self._miss_streak = 0
        self._got_frame_since_tick = True

        # 已切换订阅兜底：同一次连接内不再恢复 CRI 位姿（直至下次连接）
        if self._stale_notified:
            return

        self.cri_frame_received.emit(frame)

    def start(self, config):
        self.disarm_watchdog()
        self._config = config
        log.info(
            "[CRI] start local_ip=%s udp_port=%s enabled=%s",
            config.local_ip, config.udp_port, self._enabled,
        )

        if self._udp_thread:
            if self._udp_adapter:
                try:
                    self._sig_bind.disconnect(self._udp_adapter.bind_and_listen)
                    self._sig_shutdown_udp.disconnect(self._udp_adapter.shutdown)
                    self._udp_adapter.bind_error.disconnect(self._on_bind_error)
                    self._udp_adapter.frame_incomplete.disconnect(self._on_frame_incomplete)
                    self._udp_adapter.datagram_received.disconnect(self._on_datagram_received)
                except (TypeError, RuntimeError):
                    pass
                self._udp_adapter.deleteLater()
                self._udp_adapter = None
            self._udp_thread.quit()
            self._udp_thread.wait(3000)
            self._udp_thread = None

        self._udp_thread = UdpThread()
        self._udp_adapter = UdpCriAdapter()
        self._udp_adapter.moveToThread(self._udp_thread)

        self._sig_bind.connect(self._udp_adapter.bind_and_listen)
        self._sig_shutdown_udp.connect(self._udp_adapter.shutdown)
        self._udp_adapter.bind_error.connect(self._on_bind_error)
        self._udp_adapter.frame_incomplete.connect(self._on_frame_incomplete)
        self._udp_adapter.datagram_received.connect(self._on_datagram_received)

        self._udp_thread.started.connect(
            lambda: self._sig_bind.emit(config.local_ip, config.udp_port)
        )
        self._udp_thread.start()

        def _on_start_push_ok(_db):
            self._enabled = True
            self._cm.set_cri_push_enabled(True)
            log.info("[CRI] StartDataPush ok enabled=True")
            self.cri_started.emit()
            self._arm_watchdog()

        def _on_start_push_fail(exc: Exception):
            log.warning("[CRI] StartDataPush failed or timeout: %s", exc)
            self._miss_streak = _CRI_MISS_FRAMES_THRESHOLD
            self._stale_notified = True
            self.cri_udp_stale.emit()

        def _request_start_push():
            self._cm.send_call(
                "CRI/StartDataPush",
                {
                    "ip": config.local_ip,
                    "port": config.udp_port,
                    "duration": 4,
                    "mask": 65535,
                    "highPercision": True,
                },
                on_response=_on_start_push_ok,
                on_error=_on_start_push_fail,
                timeout=_CRI_START_DATA_PUSH_TIMEOUT_S,
                log_traffic=True,
            )

        def _after_stop(_db):
            QTimer.singleShot(200, _request_start_push)

        self._cm.send_call(
            "CRI/StopDataPush",
            {},
            on_response=_after_stop,
            on_error=lambda _e: QTimer.singleShot(200, _request_start_push),
            timeout=2.0,
            log_traffic=False,
        )

    def _on_bind_error(self, msg: str):
        log.warning("[CRI] bind_error: %s", msg)
        self.disarm_watchdog()
        self._miss_streak = _CRI_MISS_FRAMES_THRESHOLD
        self._emit_stale_if_needed(f"bind_error: {msg}")
        self.bind_error.emit(msg)

    def start_control(
        self,
        filter_type: int = 1,
        duration_ms: int = 2,
        start_buffer: int = 5,
    ) -> dict:
        msg = {
            "id": 0,
            "ty": "CRI/StartControl",
            "db": {
                "filterType": filter_type,
                "duration": duration_ms,
                "startBuffer": start_buffer,
            },
        }
        self._cm.send_raw(msg)
        return msg

    def stop_control(self) -> dict:
        msg = {"id": 0, "ty": "CRI/StopControl"}
        self._cm.send_raw(msg)
        return msg

    def start_control_dry_run(
        self, filter_type: int = 0, duration: int = 1, start_buffer: int = 3
    ) -> dict:
        msg = {
            "id": 0, "ty": "CRI/StartControl",
            "db": {
                "filterType": filter_type,
                "duration": duration,
                "startBuffer": start_buffer,
            },
        }
        log.debug("[CRI] DryRun StartControl: %s", msg)
        return msg

    def stop_control_dry_run(self) -> dict:
        msg = {"id": 0, "ty": "CRI/StopControl"}
        log.debug("[CRI] DryRun StopControl: %s", msg)
        return msg

    def stop(self):
        self.disarm_watchdog()
        log.info("[CRI] stop enabled=%s", self._enabled)
        self._cm.send_raw({"id": 0, "ty": "CRI/StopDataPush"})
        self._enabled = False
        self._cm.set_cri_push_enabled(False)

        if self._udp_thread and self._udp_thread.isRunning():
            self._sig_shutdown_udp.emit()
            self._udp_thread.quit()
            self._udp_thread.wait(3000)

        if self._udp_adapter:
            for sig in [self._sig_bind, self._sig_shutdown_udp]:
                try:
                    sig.disconnect(self._udp_adapter)
                except (TypeError, RuntimeError):
                    pass
            for sig_name in ["bind_error", "datagram_received", "frame_incomplete"]:
                try:
                    sig = getattr(self._udp_adapter, sig_name)
                    sig.disconnect()
                except (TypeError, RuntimeError):
                    pass
            self._udp_adapter.deleteLater()

        self._udp_thread = None
        self._udp_adapter = None
        log.info("[CRI] stopped enabled=False")
        self.cri_stopped.emit()
