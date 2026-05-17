"""WritingService — 轮廓字离线 pipeline + CRI 轨迹文件生成（后台线程）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Qt, Signal

from core.types import RobotPoint, WeldingProcessConfig, WorkspaceConfig
from pipeline.cri_trajectory_export import (
    TRAJECTORY_FILENAME,
    build_trajectory_from_points_file,
)
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner
from pipeline.user_messages import (
    output_file_log,
    pipeline_done_log,
    pipeline_failed_prefix,
    pipeline_start_log,
    unexpected_error_log,
    workplane_log,
)
from services.welding_service_v2 import _to_robot_point


class _GenerateWorker(QObject):
    finished = Signal(str, str, str)
    failed = Signal(str)
    log_line = Signal(str)
    state_changed = Signal(str)

    def __init__(self, service: "WritingService", kwargs: dict):
        super().__init__()
        self._service = service
        self._kwargs = kwargs

    def run(self):
        try:
            traj, pts, preview = self._service._generate_impl(
                self.log_line.emit, **self._kwargs
            )
            self.finished.emit(traj, pts, preview)
        except Exception as exc:
            self.failed.emit(str(exc))


class WritingService(QObject):
    """绘图/写字轨迹生成 — 复用焊接 pipeline（轮廓字），输出 CRI 轨迹。"""

    state_changed = Signal(str)
    progress = Signal(int, int)
    finished = Signal(str, str, str)
    preview_ready = Signal(str)
    log_message = Signal(str)
    error_occurred = Signal(str)
    generate_busy = Signal()

    STATE_IDLE = "IDLE"
    STATE_GENERATING = "GENERATING"
    STATE_DONE = "DONE"
    STATE_ERROR = "ERROR"

    def __init__(self, parent=None, output_dir: str = "output"):
        super().__init__(parent)
        self._state = self.STATE_IDLE
        self.output_dir = output_dir
        self._thread: Optional[QThread] = None
        self._worker: Optional[_GenerateWorker] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_generating(self) -> bool:
        return self._state == self.STATE_GENERATING

    def start_generate(self, **kwargs):
        """在后台线程生成轨迹；若已在生成中则 emit generate_busy。"""
        if self.is_generating or (self._thread and self._thread.isRunning()):
            self.generate_busy.emit()
            return

        self._set_state(self.STATE_GENERATING)
        thread = QThread(self)
        worker = _GenerateWorker(self, kwargs)
        worker.moveToThread(thread)

        worker.log_line.connect(self.log_message.emit, Qt.ConnectionType.QueuedConnection)
        worker.state_changed.connect(self._set_state, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_worker_finished, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._on_worker_failed, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_finished, Qt.ConnectionType.QueuedConnection)

        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_state(self, state: str):
        self._state = state
        self.state_changed.emit(state)

    def _on_worker_finished(self, traj: str, pts: str, preview: str):
        self._set_state(self.STATE_DONE)
        self.progress.emit(100, 100)
        self.finished.emit(traj, pts, preview)
        if preview:
            self.preview_ready.emit(preview)
        if self._thread and self._thread.isRunning():
            self._thread.quit()

    def _on_worker_failed(self, err: str):
        self._set_state(self.STATE_ERROR)
        self.log_message.emit(err)
        self.error_occurred.emit(err)
        if self._thread and self._thread.isRunning():
            self._thread.quit()

    def _on_thread_finished(self):
        self._thread = None
        self._worker = None

    def _generate_impl(
        self, log_fn: Callable[[str], None], **kwargs
    ) -> tuple[str, str, str]:
        text = kwargs["text"]
        user_lang = kwargs.get("user_lang", "zh")
        self.progress.emit(0, 100)

        out = kwargs.get("output_dir") or self.output_dir
        lt = _to_robot_point(
            kwargs.get("left_top"),
            default=RobotPoint(100, 200, 300, 180, 0, 90),
        )
        rt = _to_robot_point(
            kwargs.get("right_top"),
            default=RobotPoint(300, 200, 300, 180, 0, 90),
        )
        lb = _to_robot_point(
            kwargs.get("left_bottom"),
            default=RobotPoint(100, 400, 300, 180, 0, 90),
        )
        wp = WorkPlane(tl=lt, tr=rt, bl=lb)

        self.progress.emit(10, 100)
        log_fn(
            workplane_log(
                wp.width_mm, wp.height_mm,
                wp.normal.x, wp.normal.y, wp.normal.z,
                lang=user_lang,
            )
        )

        process_cfg = WeldingProcessConfig(
            lead_in_length_mm=0.0,
            lead_out_length_mm=0.0,
            overlap_length_mm=0.0,
            weld_point_spacing_mm=kwargs.get("point_spacing_mm", 0.5),
            travel_speed_mm_s=kwargs.get("write_speed_mm_s", 50.0),
            weld_speed_mm_s=kwargs.get("write_speed_mm_s", 50.0),
            voltage=0.0,
            current=0.0,
        )
        workspace_cfg = WorkspaceConfig(
            z_work_mm=kwargs.get("z_work_mm", 305.0),
            z_safe_mm=kwargs.get("z_safe_mm", 315.0),
            z_super_safe_mm=kwargs.get("z_super_safe_mm", 325.0),
        )

        self.progress.emit(20, 100)
        log_fn(pipeline_start_log(text, "contour", lang=user_lang))

        runner = OfflinePipelineRunner(
            output_dir=out,
            font_path=kwargs.get("font_path"),
            font_size_px=kwargs.get("font_size_px", 600),
            px_per_mm=kwargs.get("px_per_mm", 10.0),
            char_spacing_mm=kwargs.get("char_spacing_mm", 2.0),
            char_height_mm=kwargs.get("char_height_mm", 0.0),
            line_spacing_mm=kwargs.get("line_spacing_mm", 0.0),
            margin_left_mm=kwargs.get("margin_left_mm", 0.0),
            margin_top_mm=kwargs.get("margin_top_mm", 0.0),
            process_config=process_cfg,
            workspace_config=workspace_cfg,
            export_lua=False,
            user_lang=user_lang,
        )
        result = runner.run(text, mode="contour", workplane=wp)
        self.progress.emit(70, 100)

        if not result.ok:
            raise RuntimeError("; ".join(result.errors))

        pts_path = result.files.get("points_txt", "")
        if not pts_path:
            raise RuntimeError("missing points.txt")

        run_dir = str(Path(pts_path).parent)
        traj_path = str(Path(run_dir) / TRAJECTORY_FILENAME)
        traj_stats = build_trajectory_from_points_file(
            pts_path,
            traj_path,
            sample_rate_hz=kwargs.get("sample_rate_hz", 500),
            target_speed_mm_s=kwargs.get("write_speed_mm_s", 50.0),
        )
        for w in traj_stats.get("warnings", []):
            log_fn(f"[warn] {w}")

        png_path = (
            result.files.get("execution_preview_png", "")
            or result.files.get("combined_preview_png", "")
        )

        log_fn(pipeline_done_log(
            result.total_strokes_raw,
            result.total_segments,
            result.total_robot_points,
            result.duration_ms,
            lang=user_lang,
        ))
        log_fn(output_file_log("trajectory_cri.txt", traj_path, lang=user_lang))
        log_fn(output_file_log("points.txt", pts_path, lang=user_lang))
        if png_path:
            log_fn(output_file_log("preview_execution.png", png_path, lang=user_lang))

        self.progress.emit(100, 100)
        return traj_path, pts_path, png_path
