"""WritingExecutionService — 准备起点 + CRI UDP 执行（后台线程）。"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal

from network.cri_motion_sender import CriMotionSender
from network.connection_manager import ConnectionManager
from services.cri_service import CriService
from services.robot_realtime_state import RobotRealtimeState


@dataclass
class WritingExecConfig:
    traj_path: str
    robot_ip: str
    write_speed_mm_s: float = 50.0
    move_acc: float = 200.0
    sample_rate_hz: int = 500
    filter_type: int = 1
    start_buffer: int = 5
    cartesian: bool = True
    start_tolerance_mm: float = 2.0
    start_orient_tolerance_deg: float = 3.0
    start_stable_count: int = 6
    start_timeout_s: float = 120.0


class _WritingExecWorker(QObject):
    log = Signal(str)
    error = Signal(str)
    done = Signal(str)

    def __init__(self, task: str, cfg: WritingExecConfig, cm: ConnectionManager, cri: CriService):
        super().__init__()
        self._task = task
        self._cfg = cfg
        self._cm = cm
        self._cri = cri
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        try:
            if self._task == "prepare":
                self._run_prepare()
            elif self._task == "execute":
                self._run_execute()
            else:
                raise ValueError(f"unknown task: {self._task}")
            self.done.emit(self._task)
        except Exception as exc:
            self.error.emit(str(exc))

    def _run_prepare(self):
        start = CriMotionSender.read_first_point(self._cfg.traj_path)
        if not start:
            raise RuntimeError("cannot read trajectory start point")
        self.log.emit(
            f"move to start: [{start[0]:.2f}, {start[1]:.2f}, {start[2]:.2f}]"
        )
        self._send_movL_sync(start)
        self.log.emit("waiting: CRI moving + TCP pose...")
        self._wait_until_at_start(start)
        self.log.emit("arrived at trajectory start")

    def _run_execute(self):
        start = CriMotionSender.read_first_point(self._cfg.traj_path)
        if not start:
            raise RuntimeError("cannot read trajectory start point")
        if not self._check_at_start(start, log_mismatch=True):
            raise RuntimeError(
                "robot not at trajectory start; run 'Move to Start' first"
            )

        self.log.emit("CRI StopControl (pre)")
        self._cri.stop_control()
        time.sleep(0.5)

        duration_ms = max(1, int(1000.0 / self._cfg.sample_rate_hz))
        self.log.emit(
            f"CRI StartControl: {self._cfg.sample_rate_hz} Hz, buffer={self._cfg.start_buffer}"
        )
        self._cri.start_control(
            filter_type=self._cfg.filter_type,
            duration_ms=duration_ms,
            start_buffer=self._cfg.start_buffer,
        )

        sender = CriMotionSender(
            robot_ip=self._cfg.robot_ip,
            frequency_hz=self._cfg.sample_rate_hz,
            cartesian=self._cfg.cartesian,
        )
        try:
            sent = sender.send_file(
                self._cfg.traj_path,
                should_stop=lambda: self._stop,
            )
            self.log.emit(f"UDP sent {sent} samples")
            time.sleep(0.5)
        finally:
            sender.close()
            self._cri.stop_control()
            self.log.emit("CRI StopControl (post)")

    def _pose_distance(self, current: tuple[float, ...], target: List[float]) -> tuple[float, float]:
        pos_d = math.sqrt(
            (current[0] - target[0]) ** 2
            + (current[1] - target[1]) ** 2
            + (current[2] - target[2]) ** 2
        )
        orient_d = math.sqrt(
            (current[3] - target[3]) ** 2
            + (current[4] - target[4]) ** 2
            + (current[5] - target[5]) ** 2
        )
        return pos_d, orient_d

    def _check_at_start(self, target: List[float], *, log_mismatch: bool = False) -> bool:
        state = RobotRealtimeState.instance()
        if not state.is_valid():
            return False
        cur = state.current_tcp_pose_mm_deg()
        pos_d, orient_d = self._pose_distance(cur, target)
        ok = (
            pos_d <= self._cfg.start_tolerance_mm
            and orient_d <= self._cfg.start_orient_tolerance_deg
            and not state.is_moving()
        )
        if log_mismatch and not ok:
            self.log.emit(
                f"not at start: dist={pos_d:.2f}mm orient={orient_d:.2f}° "
                f"moving={state.is_moving()}"
            )
        return ok

    def _wait_until_at_start(self, target: List[float]):
        deadline = time.monotonic() + self._cfg.start_timeout_s
        stable = 0
        seen_moving = False
        interval = 0.2

        while time.monotonic() < deadline:
            if self._stop:
                raise RuntimeError("cancelled")

            state = RobotRealtimeState.instance()
            if not state.is_valid():
                time.sleep(interval)
                continue

            moving = state.is_moving()
            if moving:
                seen_moving = True

            if self._check_at_start(target):
                if not moving:
                    stable += 1
                    if stable >= self._cfg.start_stable_count:
                        cur = state.current_tcp_pose_mm_deg()
                        pos_d, _ = self._pose_distance(cur, target)
                        self.log.emit(
                            f"stable at start: dist={pos_d:.2f}mm, moving=false"
                        )
                        return
                else:
                    stable = 0
            else:
                stable = 0

            time.sleep(interval)

        state = RobotRealtimeState.instance()
        if state.is_valid():
            cur = state.current_tcp_pose_mm_deg()
            pos_d, orient_d = self._pose_distance(cur, target)
            raise TimeoutError(
                f"start point timeout: dist={pos_d:.2f}mm orient={orient_d:.2f}° "
                f"moving={state.is_moving()} seen_moving={seen_moving}"
            )
        raise TimeoutError("start point timeout: no CRI data")

    def _send_movL_sync(self, cp: list[float]):
        done = {"ok": False, "err": None}

        def on_ok(_):
            done["ok"] = True

        def on_err(e):
            done["err"] = e

        db = [{
            "type": "movL",
            "speed": self._cfg.write_speed_mm_s,
            "acc": self._cfg.move_acc,
            "blend": 0,
            "targetPoint": {"cp": cp, "ep": []},
        }]
        self._cm.send_call("Robot/move", db, on_response=on_ok, on_error=on_err, timeout=120.0)

        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            if self._stop:
                raise RuntimeError("cancelled")
            if done["ok"]:
                return
            if done["err"] is not None:
                raise RuntimeError(f"Robot/move failed: {done['err']}")
            time.sleep(0.05)
        raise TimeoutError("Robot/move timeout")


class WritingExecutionService(QObject):
    log_message = Signal(str)
    error_occurred = Signal(str)
    finished = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_WritingExecWorker] = None
        self._busy = False
        self._pending_task: Optional[str] = None

    @property
    def is_busy(self) -> bool:
        return self._busy

    def stop(self):
        if self._worker:
            self._worker.request_stop()

    def run_prepare(
        self,
        cfg: WritingExecConfig,
        cm: ConnectionManager,
        cri: CriService,
    ):
        self._start("prepare", cfg, cm, cri)

    def run_execute(
        self,
        cfg: WritingExecConfig,
        cm: ConnectionManager,
        cri: CriService,
    ):
        self._start("execute", cfg, cm, cri)

    def _start(
        self,
        task: str,
        cfg: WritingExecConfig,
        cm: ConnectionManager,
        cri: CriService,
    ):
        if self._busy:
            self.log_message.emit("execution busy")
            return

        self._busy = True
        self._pending_task = None
        thread = QThread(self)
        worker = _WritingExecWorker(task, cfg, cm, cri)
        worker.moveToThread(thread)

        worker.log.connect(self._on_worker_log, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._on_worker_error, Qt.ConnectionType.QueuedConnection)
        worker.done.connect(self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished, Qt.ConnectionType.QueuedConnection)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_worker_log(self, msg: str):
        self.log_message.emit(msg)

    def _on_worker_error(self, err: str):
        self.error_occurred.emit(err)
        self._pending_task = None
        if self._thread and self._thread.isRunning():
            self._thread.quit()

    def _on_worker_done(self, task: str):
        self._pending_task = task
        if self._thread and self._thread.isRunning():
            self._thread.quit()

    def _on_thread_finished(self):
        task = self._pending_task
        self._pending_task = None
        self._thread = None
        self._worker = None
        self._busy = False
        if task:
            self.finished.emit(task)
