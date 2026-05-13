"""WeldingServiceV2 — 新 pipeline wrapper (Signal 兼容旧 WeldingService 接口)

内部委托 OfflinePipelineRunner.run()，不依赖旧 pipeline 模块。
不生成 Lua，不调用 CRI，不真实连接机器人。
旧 WeldingService 保留不动。
"""

from PySide6.QtCore import QObject, Signal

from core.types import RobotPoint
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner


class WeldingServiceV2(QObject):
    """焊接点位生成服务 V2 — 基于新 pipeline (OfflinePipelineRunner)。

    Signal 接口兼容旧 WeldingService：
      state_changed, finished, preview_ready, log_message, error_occurred
    """

    state_changed = Signal(str)       # IDLE / GENERATING / DONE / ERROR
    progress = Signal(int, int)       # current, total (兼容旧 UI)
    finished = Signal(str, str)       # points_txt_path, job_json_path
    preview_ready = Signal(str)       # combined_preview_png_path
    log_message = Signal(str)         # log line
    error_occurred = Signal(str)      # error message

    STATE_IDLE = "IDLE"
    STATE_GENERATING = "GENERATING"
    STATE_DONE = "DONE"
    STATE_ERROR = "ERROR"

    def __init__(self, parent=None, output_dir: str = "output"):
        super().__init__(parent)
        self._state = self.STATE_IDLE
        self.output_dir = output_dir

    @property
    def state(self) -> str:
        return self._state

    def generate(
        self,
        text: str,
        mode: str = "contour",
        *,
        # 三点标定 (匹配 UI: left_top, left_bottom, right_bottom)
        left_top: RobotPoint | dict | None = None,
        left_bottom: RobotPoint | dict | None = None,
        right_bottom: RobotPoint | dict | None = None,
        # 可选配置
        font_size_px: int = 600,
        px_per_mm: float = 10.0,
        char_spacing_mm: float = 2.0,
        output_dir: str | None = None,
    ):
        """生成焊接点位文件。

        Args:
            text: 输入文字
            mode: "contour" | "skeleton"
            left_top: 左上示教点 (RobotPoint 或 dict)
            left_bottom: 左下示教点
            right_bottom: 右下示教点
            font_size_px: 渲染字号
            px_per_mm: 像素/mm 换算比
            output_dir: 输出目录 (覆盖 __init__ 默认值)
        """
        self._state = self.STATE_GENERATING
        self.state_changed.emit(self._state)
        self.progress.emit(0, 100)

        try:
            out = output_dir or self.output_dir

            # 构造 WorkPlane: 兼容旧 compute_workplane 几何
            # TL=left_bottom (原点), TR=right_bottom (U), BL=left_top (V)
            # N=(0,0,1) → 安全高度正确
            # 注：pixel(0,0)=robot(0,0,100)=left_bottom, 图像原点在 robot 左下角
            # 这是标准 CNC/robot 坐标系约定，非 bug
            lb = _to_robot_point(left_bottom, default=RobotPoint(0, 100, 100, -180, 0, -135))
            rb = _to_robot_point(right_bottom, default=RobotPoint(200, 100, 100, -180, 0, -135))
            lt = _to_robot_point(left_top, default=RobotPoint(0, 0, 100, -180, 0, -135))
            wp = WorkPlane(tl=lb, tr=rb, bl=lt)
            self.progress.emit(10, 100)
            self.log_message.emit(f"WorkPlane: {wp.width_mm:.0f}×{wp.height_mm:.0f} mm, "
                                  f"N=({wp.normal.x:.3f},{wp.normal.y:.3f},{wp.normal.z:.3f})")

            # 运行离线 pipeline
            self.progress.emit(20, 100)
            self.log_message.emit(f"Pipeline: text='{text}' mode={mode}")
            runner = OfflinePipelineRunner(
                output_dir=out,
                font_size_px=font_size_px,
                px_per_mm=px_per_mm,
                char_spacing_mm=char_spacing_mm,
            )
            result = runner.run(text, mode=mode, workplane=wp)
            self.progress.emit(90, 100)

            if not result.ok:
                err_msg = "; ".join(result.errors)
                self.log_message.emit(f"Pipeline FAILED: {err_msg}")
                self._state = self.STATE_ERROR
                self.state_changed.emit(self._state)
                self.error_occurred.emit(err_msg)
                return

            pts_path = result.files.get("points_txt", "")
            job_path = result.files.get("job_json", "")
            png_path = result.files.get("combined_preview_png", "")

            self.log_message.emit(
                f"Done: {result.total_strokes_raw} strokes → "
                f"{result.total_segments} segments, "
                f"{result.total_robot_points} points, "
                f"{result.duration_ms:.0f}ms"
            )
            self.log_message.emit(f"  points.txt: {pts_path}")
            self.log_message.emit(f"  job.json:   {job_path}")
            self.log_message.emit(f"  preview:    {png_path}")

            self._state = self.STATE_DONE
            self.progress.emit(100, 100)
            self.state_changed.emit(self._state)
            self.finished.emit(pts_path, job_path)
            if png_path:
                self.preview_ready.emit(png_path)

        except Exception as exc:
            self._state = self.STATE_ERROR
            self.state_changed.emit(self._state)
            msg = f"ERROR: {exc}"
            self.log_message.emit(msg)
            self.error_occurred.emit(str(exc))


def _to_robot_point(val: RobotPoint | dict | None, default: RobotPoint) -> RobotPoint:
    """将 RobotPoint 或 dict 转为 RobotPoint。None 返回 default。"""
    if val is None:
        return default
    if isinstance(val, RobotPoint):
        return val
    if isinstance(val, dict):
        return RobotPoint(
            x=float(val.get("x", 0)), y=float(val.get("y", 0)),
            z=float(val.get("z", 100)),
            rx=float(val.get("rx", -180)), ry=float(val.get("ry", 0)),
            rz=float(val.get("rz", -135)),
        )
    raise TypeError(f"unsupported type for RobotPoint: {type(val)}")
