"""WritingExecutionService — 准备起点 + CRI UDP 执行（后台线程）。"""

from __future__ import annotations

import math
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal

from network.cri_motion_sender import CriMotionSender
from network.connection_manager import ConnectionManager
from services.cri_execution_log import (
    CriExecutionTrace,
    _UdpPoseProbe,
    format_ts_ms,
    log_cri_protocol_reference,
    log_cri_start_control,
    log_cri_stop_control,
    log_execution_footer,
    log_tcp_vs_trajectory_start,
    log_trajectory_summary,
    log_trajectory_z_diagnosis,
    log_udp_send_begin,
    log_udp_send_summary,
    log_udp_target_and_packets,
)
from services.cri_minimal_test import TRAJECTORY_FILENAME, write_minimal_z_test_trajectory
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
    z_draw_mm: float = 305.0
    z_safe_mm: float = 315.0
    cri_data_push_ip: str = ""
    cri_data_push_port: int = 0
    skip_start_check: bool = False


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
            elif self._task == "minimal_test":
                self._run_minimal_test()
            else:
                raise ValueError(f"unknown task: {self._task}")
            self.done.emit(self._task)
        except Exception as exc:
            self.error.emit(str(exc))

    def _emit(self, msg: str) -> None:
        self.log.emit(msg)

    def _run_prepare(self):
        start = CriMotionSender.read_first_point(self._cfg.traj_path)
        if not start:
            raise RuntimeError("cannot read trajectory start point")
        self._emit(
            f"{format_ts_ms()} 移至起点: "
            f"[{start[0]:.2f}, {start[1]:.2f}, {start[2]:.2f}]"
        )
        self._send_movL_sync(start)
        self._emit(f"{format_ts_ms()} 等待 CRI 运动结束并核对 TCP 位姿...")
        self._wait_until_at_start(start)
        self._emit(f"{format_ts_ms()} 已到达轨迹起点")

    def _run_minimal_test(self):
        """最小 Z±10mm 诊断：读当前 TCP → 生成轨迹 → 移至起点 → CRI 执行。"""
        rt = RobotRealtimeState.instance()
        if not rt.is_valid():
            raise RuntimeError("无 CRI 实时数据，无法读取当前 TCP 位姿")
        start_pose = list(rt.current_tcp_pose_mm_deg())
        out_dir = Path("output/cri_minimal_test")
        traj_path = out_dir / TRAJECTORY_FILENAME
        meta = write_minimal_z_test_trajectory(
            traj_path,
            start_pose,
            delta_z_mm=10.0,
            duration_s=3.0,
            sample_rate_hz=int(self._cfg.sample_rate_hz),
        )
        self._emit(f"{format_ts_ms()} —— CRI 最小测试轨迹已生成（当前 TCP 为起点）——")
        self._emit(
            f"{format_ts_ms()} 路径={meta['path']} 点数={meta['sample_count']} "
            f"TCP起点 Z={start_pose[2]:.1f}mm Z范围={meta['z_range']} "
            f"(±{meta['delta_z_mm']:.0f}mm 往返)"
        )
        saved_traj = self._cfg.traj_path
        self._cfg.traj_path = meta["path"]
        try:
            self._emit(f"{format_ts_ms()} 最小测试：先移至轨迹起点…")
            self._run_prepare()
            self._run_execute()
        finally:
            self._cfg.traj_path = saved_traj

    def _run_execute(self):
        trace = CriExecutionTrace()
        freq = float(self._cfg.sample_rate_hz)

        start = CriMotionSender.read_first_point(self._cfg.traj_path)
        if not start:
            raise RuntimeError("cannot read trajectory start point")
        if not self._cfg.skip_start_check:
            if not self._check_at_start(start, log_mismatch=True):
                raise RuntimeError(
                    "robot not at trajectory start; run 'Move to Start' first"
                )

        self._emit(f"{format_ts_ms()} —— 开始 CRI 轨迹执行 ——")
        log_cri_protocol_reference(self._emit)
        traj_stats = log_trajectory_summary(self._emit, self._cfg.traj_path, freq)
        log_trajectory_z_diagnosis(
            self._emit,
            self._cfg.traj_path,
            z_draw_mm=self._cfg.z_draw_mm,
            z_safe_mm=self._cfg.z_safe_mm,
        )
        if start:
            log_tcp_vs_trajectory_start(self._emit, start)
        sample_count = int(traj_stats["sample_count"])
        expected_dur = float(traj_stats["expected_duration_s"])

        log_cri_stop_control(
            self._emit, self._cm, trace, phase="pre",
            should_stop=lambda: self._stop,
        )
        time.sleep(0.5)

        duration_ms = max(1, min(16, int(1000.0 / freq)))
        log_cri_start_control(
            self._emit,
            self._cm,
            trace,
            filter_type=self._cfg.filter_type,
            duration_ms=duration_ms,
            start_buffer=self._cfg.start_buffer,
            frequency_hz=freq,
            should_stop=lambda: self._stop,
        )

        bind_ip = self._cfg.cri_data_push_ip or ""
        sender = CriMotionSender(
            robot_ip=self._cfg.robot_ip,
            frequency_hz=freq,
            cartesian=self._cfg.cartesian,
            bind_local_ip=bind_ip,
        )
        log_udp_target_and_packets(
            self._emit,
            sender,
            self._cfg.traj_path,
            cri_data_push_ip=self._cfg.cri_data_push_ip,
            cri_data_push_port=self._cfg.cri_data_push_port,
        )

        pose_probe = _UdpPoseProbe(start)
        sent = 0
        interrupted = False
        socket_err = False
        log_udp_send_begin(
            self._emit,
            sample_count=sample_count,
            frequency_hz=freq,
            expected_duration_s=expected_dur,
        )
        udp_begin = time.perf_counter()
        try:
            try:
                sent = sender.send_file(
                    self._cfg.traj_path,
                    should_stop=lambda: self._stop,
                    on_elapsed=lambda el, _s, _t: pose_probe.tick(self._emit, el),
                )
                if self._stop and sent < sample_count:
                    interrupted = True
            except (socket.error, OSError) as exc:
                socket_err = True
                trace.socket_error = True
                self._emit(f"{format_ts_ms()} UDP socket 错误: {exc}")
                raise
        finally:
            udp_end = time.perf_counter()
            actual_dur = max(udp_end - udp_begin, 1e-9)
            sender.close()
            log_udp_send_summary(
                self._emit,
                sent_count=sent,
                actual_duration_s=actual_dur,
                socket_error=socket_err,
                interrupted=interrupted,
            )
            if pose_probe.max_dist_from_start < 0.1:
                self._emit(
                    f"{format_ts_ms()} 诊断: UDP 全程距起点 max={pose_probe.max_dist_from_start:.3f}mm "
                    f"— 机器人可能未消费控制包"
                )
            else:
                self._emit(
                    f"{format_ts_ms()} 诊断: UDP 期间观测到位移 max={pose_probe.max_dist_from_start:.3f}mm"
                )
            time.sleep(0.5)
            log_cri_stop_control(
                self._emit, self._cm, trace, phase="post",
                should_stop=lambda: self._stop,
            )
            log_execution_footer(self._emit, trace)

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
            self._emit(
                f"{format_ts_ms()} 未在起点: 距离={pos_d:.2f}mm 姿态差={orient_d:.2f}° "
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
                        self._emit(
                            f"{format_ts_ms()} 起点稳定: 距离={pos_d:.2f}mm, moving=false"
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

    def run_minimal_test(
        self,
        cfg: WritingExecConfig,
        cm: ConnectionManager,
        cri: CriService,
    ):
        """CRI 最小 X±10mm 诊断（不依赖文字轨迹）。"""
        self._start("minimal_test", cfg, cm, cri)

    def _start(
        self,
        task: str,
        cfg: WritingExecConfig,
        cm: ConnectionManager,
        cri: CriService,
    ):
        if self._busy:
            self.log_message.emit(f"{format_ts_ms()} 执行任务繁忙，请稍候")
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
