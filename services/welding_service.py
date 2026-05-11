"""焊接输出服务 — 管线编排 + 状态机 + Signal 通知 UI"""

from PySide6.QtCore import QObject, Signal

from core.types import (
    Pose, Point3D, EulerDeg, Path2D, Path3D, WeldPointSegment, TrajectoryResult,
)
from pipeline.font_renderer import get_default_font_path
from pipeline.layout_engine import layout_text
from pipeline.path_processor import process_paths
from pipeline.workplane_mapper import map_to_3d
from pipeline.weld_path_planner import plan_weld_paths
from pipeline.file_output import write_weld_txt, write_weld_json, make_output_paths
from pipeline.preview import preview_weld_segments
from config.welding_defaults import (
    CHAR_HEIGHT_MM, CHAR_SPACING_MM, LINE_SPACING_MM,
    LEAD_IN_MM, LEAD_OUT_MM, OVERLAP_MM, POINT_SPACING_MM,
)


class WeldingService(QObject):
    """焊接点位生成服务 — 编排 pipeline，通过 Signal 通知 UI 进度和结果"""

    # Signals
    state_changed = Signal(str)    # IDLE / GENERATING / DONE / ERROR
    progress = Signal(int, int)    # current, total
    finished = Signal(str, str)    # txt_path, json_path
    preview_ready = Signal(str)    # png_path
    log_message = Signal(str)      # log line

    STATE_IDLE = "IDLE"
    STATE_GENERATING = "GENERATING"
    STATE_DONE = "DONE"
    STATE_ERROR = "ERROR"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = self.STATE_IDLE

    @property
    def state(self) -> str:
        return self._state

    def generate_weld_points(
        self,
        text: str,
        font_path: str = "",
        char_height_mm: float = CHAR_HEIGHT_MM,
        char_spacing_mm: float = CHAR_SPACING_MM,
        line_spacing_mm: float = LINE_SPACING_MM,
        direction: str = "horizontal",
        align: str = "center",
        flow: str = "left_to_right",
        lead_in_mm: float = LEAD_IN_MM,
        lead_out_mm: float = LEAD_OUT_MM,
        overlap_mm: float = OVERLAP_MM,
        point_spacing_mm: float = POINT_SPACING_MM,
        left_top: Pose | None = None,
        left_bottom: Pose | None = None,
        right_bottom: Pose | None = None,
        output_dir: str = "examples/output",
    ):
        """生成焊接点位文件。

        在 UI 线程同步执行（因 pipeline 计算量小，不必另开线程）。
        如需处理大量文字，调用方应自行放到 Worker Thread。
        """
        self._state = self.STATE_GENERATING
        self.state_changed.emit(self._state)

        try:
            font = font_path or get_default_font_path()
            self.log_message.emit(f"字体: {font}")

            # Step 1: Layout
            self.log_message.emit("Step 1/5: 排版文字...")
            paths_2d = layout_text(
                text, font,
                char_height_mm=char_height_mm,
                char_spacing_mm=char_spacing_mm,
                line_spacing_mm=line_spacing_mm,
                direction=direction,
                align=align,
                flow=flow,
            )
            self.log_message.emit(f"  → {len(paths_2d)} 条二维路径")

            # Step 2: Process
            self.log_message.emit("Step 2/5: 清洗路径...")
            paths_2d = process_paths(
                paths_2d,
                sample_spacing_mm=point_spacing_mm,
                char_height_mm=char_height_mm,
            )
            n_closed = sum(1 for p in paths_2d if p.closed)
            self.log_message.emit(
                f"  → {len(paths_2d)} 条 (闭合: {n_closed}, 开放: {len(paths_2d) - n_closed})"
            )

            # Step 3: Map to 3D
            self.log_message.emit("Step 3/5: 映射到3D工作平面...")
            if left_top is None:
                left_top = Pose(Point3D(0, 0, 0), EulerDeg(180, 0, 90))
            if left_bottom is None:
                left_bottom = Pose(Point3D(0, 200, 0), EulerDeg(180, 0, 90))
            if right_bottom is None:
                right_bottom = Pose(Point3D(200, 200, 0), EulerDeg(180, 0, 90))

            # Calculate canvas size from layout
            canvas_w = 200.0
            canvas_h = 100.0
            paths_3d = map_to_3d(
                paths_2d, left_top, left_bottom, right_bottom,
                canvas_width_mm=canvas_w, canvas_height_mm=canvas_h,
            )
            self.log_message.emit(f"  → {len(paths_3d)} 条三维路径")

            # Step 4: Weld plan
            self.log_message.emit("Step 4/5: 生成焊接工艺段...")
            segments = plan_weld_paths(
                paths_3d,
                lead_in_mm=lead_in_mm,
                lead_out_mm=lead_out_mm,
                overlap_mm=overlap_mm,
                point_spacing_mm=point_spacing_mm,
            )
            n_closed_seg = sum(1 for s in segments if s.closed)
            n_overlap = sum(1 for s in segments if len(s.overlap_path) > 0)
            self.log_message.emit(
                f"  → {len(segments)} 段 (闭合: {n_closed_seg}, 搭接: {n_overlap})"
            )

            # Step 5: Write files
            self.log_message.emit("Step 5/5: 写入文件...")
            txt_path, json_path = make_output_paths(text, output_dir)
            meta = {
                "text": text, "font": font,
                "char_height_mm": char_height_mm,
                "lead_in_mm": lead_in_mm, "lead_out_mm": lead_out_mm,
                "overlap_mm": overlap_mm, "point_spacing_mm": point_spacing_mm,
            }
            write_weld_txt(segments, txt_path, meta)
            write_weld_json(segments, json_path, meta)
            self.log_message.emit(f"  → TXT: {txt_path}")
            self.log_message.emit(f"  → JSON: {json_path}")

            # Preview
            self.log_message.emit("生成预览图...")
            preview_path = txt_path.replace(".txt", ".png")
            preview_weld_segments(segments, preview_path,
                                  title=f"Weld Preview: {text}")
            self.log_message.emit(f"  → Preview: {preview_path}")
            self.preview_ready.emit(preview_path)

            self._state = self.STATE_DONE
            self.state_changed.emit(self._state)
            self.finished.emit(txt_path, json_path)

        except Exception as e:
            self._state = self.STATE_ERROR
            self.state_changed.emit(self._state)
            self.log_message.emit(f"ERROR: {e}")
            raise
