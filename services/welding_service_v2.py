"""WeldingServiceV2 — 新 pipeline wrapper (Signal 兼容旧 WeldingService 接口)

内部委托 OfflinePipelineRunner.run()，不依赖旧 pipeline 模块。
不生成 Lua，不调用 CRI，不真实连接机器人。
焊接页唯一使用的生成服务（原 V1 已移除）。
"""

from PySide6.QtCore import QObject, Signal

from config.weld_font_presets import WeldFontPresetError
from core.types import RobotPoint
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner
from pipeline.user_messages import (
    output_file_log,
    pipeline_done_log,
    pipeline_failed_prefix,
    pipeline_start_log,
    unexpected_error_log,
    weld_font_not_allowed,
    workplane_log,
)


class WeldingServiceV2(QObject):
    """焊接点位生成服务 V2 — 基于新 pipeline (OfflinePipelineRunner)。

    Signal 接口兼容旧 WeldingService：
      state_changed, finished, preview_ready, log_message, error_occurred
    """

    state_changed = Signal(str)       # IDLE / GENERATING / DONE / ERROR
    progress = Signal(int, int)       # current, total (兼容旧 UI)
    finished = Signal(str, str)       # points_txt_path, job_json_path
    preview_ready = Signal(str)       # preview_execution.png path
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
        mode: str = "skeleton",
        *,
        text_source: str | None = None,
        # 四点标定 (UI 三点 + 推导 right_top)
        left_top: RobotPoint | dict | None = None,
        right_top: RobotPoint | dict | None = None,
        left_bottom: RobotPoint | dict | None = None,
        right_bottom: RobotPoint | dict | None = None,
        # 可选配置
        font_path: str | None = None,
        font_preset_id: str | None = None,
        skeleton_source: str = "hershey",
        hershey_style: str = "futural",
        font_size_px: int = 600,
        px_per_mm: float = 10.0,
        char_spacing_mm: float = 2.0,
        char_height_mm: float = 0.0,
        line_spacing_mm: float = 0.0,
        margin_left_mm: float = 0.0,
        margin_top_mm: float = 0.0,
        lead_in_mm: float = 3.0,
        lead_out_mm: float = 3.0,
        overlap_mm: float = 5.0,
        weld_point_spacing_mm: float = 0.5,
        output_dir: str | None = None,
        # 工艺参数
        voltage: float = 24.0,
        current: float = 150.0,
        job: int = 0,
        inductance: float = 0.0,
        weld_speed: float = 30.0,
        travel_speed: float = 80.0,
        # 工作空间偏移
        z_work_mm: float = 305.0,
        z_safe_mm: float = 315.0,
        z_super_safe_mm: float = 325.0,
        # Lua 运动参数
        lua_accel: float = 300.0,
        lua_blend_mode: str = "absolute",
        lua_blend_radius: float = 2.0,
        lua_blend_ratio: int = 50,
        # wait() injection
        wait_enabled: bool = False,
        wait_count: int = 30,
        wait_duration_ms: int = 1,
        user_lang: str = "zh",
    ):
        """生成焊接点位文件。

        Args:
            text: 输入文字
            mode: "contour" | "skeleton"（兼容；优先 text_source）
            text_source: ttf_contour | latin_stroke | hanzi_stroke
            left_top: 左上示教点 (RobotPoint 或 dict)
            left_bottom: 左下示教点
            right_bottom: 右下示教点
            font_size_px: 渲染字号
            px_per_mm: 像素/mm 换算比
            output_dir: 输出目录 (覆盖 __init__ 默认值)
            user_lang: 界面语言 "zh" | "en"，用于输出日志文案
        """
        self._state = self.STATE_GENERATING
        self.state_changed.emit(self._state)
        self.progress.emit(0, 100)

        try:
            out = output_dir or self.output_dir

            # 构造 WorkPlane: TL=左上, TR=右上, BL=左下
            lt = _to_robot_point(left_top, default=RobotPoint(100, 200, 300, 180, 0, 90))
            rt = _to_robot_point(right_top, default=RobotPoint(300, 200, 300, 180, 0, 90))
            lb = _to_robot_point(left_bottom, default=RobotPoint(100, 400, 300, 180, 0, 90))
            wp = WorkPlane(tl=lt, tr=rt, bl=lb)
            self.progress.emit(10, 100)
            self.log_message.emit(workplane_log(
                wp.width_mm, wp.height_mm,
                wp.normal.x, wp.normal.y, wp.normal.z,
                lang=user_lang,
            ))

            from pipeline.text_pipeline import (
                TEXT_SOURCE_TTF_CONTOUR,
                legacy_mode_from_text_source,
                migrate_welding_text_source,
                skeleton_source_for_text_source,
            )

            resolved_source = migrate_welding_text_source(
                text_source=text_source,
                legacy_mode=mode,
            )

            mode = legacy_mode_from_text_source(resolved_source)
            sk_for_run = skeleton_source_for_text_source(resolved_source)

            self.progress.emit(20, 100)
            self.log_message.emit(pipeline_start_log(text, mode, lang=user_lang))
            from core.types import WeldingProcessConfig, WorkspaceConfig, LuaExportConfig
            use_ttf_restrict = resolved_source == TEXT_SOURCE_TTF_CONTOUR
            runner = OfflinePipelineRunner(
                output_dir=out,
                font_path=font_path,
                font_preset_id=font_preset_id,
                restrict_weld_fonts=use_ttf_restrict,
                skeleton_source=sk_for_run,
                hershey_style=hershey_style,
                font_size_px=font_size_px,
                lua_config=LuaExportConfig(
                    acceleration=lua_accel,
                    blend_mode=lua_blend_mode,
                    blend_radius=lua_blend_radius,
                    blend_ratio=lua_blend_ratio,
                    insert_wait=wait_enabled,
                    wait_every_movl=wait_count,
                    wait_duration_ms=wait_duration_ms,
                ),
                px_per_mm=px_per_mm,
                char_spacing_mm=char_spacing_mm,
                char_height_mm=char_height_mm,
                line_spacing_mm=line_spacing_mm,
                margin_left_mm=margin_left_mm,
                margin_top_mm=margin_top_mm,
                process_config=WeldingProcessConfig(
                    lead_in_length_mm=lead_in_mm,
                    lead_out_length_mm=lead_out_mm,
                    overlap_length_mm=overlap_mm,
                    weld_point_spacing_mm=weld_point_spacing_mm,
                    voltage=voltage, current=current, job=job,
                    inductance=inductance,
                    weld_speed_mm_s=weld_speed, travel_speed_mm_s=travel_speed,
                ),
                workspace_config=WorkspaceConfig(
                    z_work_mm=z_work_mm,
                    z_safe_mm=z_safe_mm,
                    z_super_safe_mm=z_super_safe_mm,
                ),
                user_lang=user_lang,
            )
            result = runner.run(
                text,
                mode=mode,
                workplane=wp,
                text_source=resolved_source,
                target_process="weld",
            )
            self.progress.emit(90, 100)

            if not result.ok:
                err_msg = "; ".join(result.errors)
                self.log_message.emit(
                    f"{pipeline_failed_prefix(lang=user_lang)}{err_msg}"
                )
                self._state = self.STATE_ERROR
                self.state_changed.emit(self._state)
                self.error_occurred.emit(err_msg)
                return

            pts_path = result.files.get("points_txt", "")
            job_path = result.files.get("job_json", "")
            png_path = (
                result.files.get("execution_preview_png", "")
                or result.files.get("combined_preview_png", "")
                or result.files.get("weld_only_preview_png", "")
            )

            self.log_message.emit(pipeline_done_log(
                result.total_strokes_raw,
                result.total_segments,
                result.total_robot_points,
                result.duration_ms,
                lang=user_lang,
            ))
            self.log_message.emit(output_file_log("points.txt", pts_path, lang=user_lang))
            self.log_message.emit(output_file_log("job.json", job_path, lang=user_lang))
            self.log_message.emit(
                output_file_log("preview_execution.png", png_path, lang=user_lang)
            )
            lua_path = result.files.get("lua_script", "")
            if lua_path:
                self.log_message.emit(output_file_log("lua", lua_path, lang=user_lang))

            self._state = self.STATE_DONE
            self.progress.emit(100, 100)
            self.state_changed.emit(self._state)
            self.finished.emit(pts_path, job_path)
            if png_path:
                self.preview_ready.emit(png_path)

        except WeldFontPresetError as exc:
            self._state = self.STATE_ERROR
            self.state_changed.emit(self._state)
            path = font_path or ""
            msg = weld_font_not_allowed(path, lang=user_lang) if path else str(exc)
            self.log_message.emit(f"{pipeline_failed_prefix(lang=user_lang)}{msg}")
            self.error_occurred.emit(msg)
        except Exception as exc:
            self._state = self.STATE_ERROR
            self.state_changed.emit(self._state)
            msg = unexpected_error_log(exc, lang=user_lang)
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

