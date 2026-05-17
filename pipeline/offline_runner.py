"""Phase 8.2: OfflinePipelineRunner — 端到端离线 Pipeline 封装

单一 runner 类，封装从文字输入到文件输出的全链路调用。
纯 Python，无 Qt/PySide6，无 CRI，无 Lua。

用法:
    from pipeline.offline_runner import OfflinePipelineRunner, RunResult
    from pipeline.mapping import WorkPlane
    from core.types import RobotPoint

    wp = WorkPlane(
        RobotPoint(0, 0, 100, -180, 0, -135),
        RobotPoint(200, 0, 100, -180, 0, -135),
        RobotPoint(0, 100, 100, -180, 0, -135),
    )
    runner = OfflinePipelineRunner(output_dir="output")
    result = runner.run("Abc", mode="contour", workplane=wp)
"""

from __future__ import annotations

import json as _json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.types import PathConfig, WeldingProcessConfig, WorkspaceConfig, LuaExportConfig
from pipeline.raster import FontRasterizer, get_default_font_path
from pipeline.user_messages import (
    no_strokes_extracted,
    skeleton_baseline_drift_warning,
    stage_error,
    workplane_overflow_message,
)


# ── 结果数据类 ──

@dataclass
class StageStats:
    name: str
    status: str = "ok"
    stats: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class RunResult:
    ok: bool
    text: str
    mode: str
    output_dir: str
    files: dict[str, str]
    stage_stats: list[StageStats]
    total_strokes_raw: int = 0
    total_strokes_mapped: int = 0
    total_segments: int = 0
    total_robot_points: int = 0
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── 固定输出文件名 ──
POINTS_FILENAME = "points.txt"
JOB_FILENAME = "job.json"
STROKES_PREVIEW = "preview_strokes.png"
EXECUTION_PREVIEW = "preview_execution.png"
SEGMENTS_PREVIEW = "preview_segments.png"
COMBINED_PREVIEW = "preview_combined.png"
WELD_ONLY_PREVIEW = "preview_weld_only.png"
SUMMARY_FILENAME = "summary.json"


def _weld_bbox_mm_from_segments(segments) -> tuple[float, float]:
    """从 weld/overlap 段计算机器人 XY 包络宽高 (mm)。"""
    xs: list[float] = []
    ys: list[float] = []
    for seg in segments:
        if seg.type not in ("weld", "overlap"):
            continue
        for p in seg.points:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return 0.0, 0.0
    return max(xs) - min(xs), max(ys) - min(ys)


def _layout_summary_from_map_stats(
    map_stats: dict,
    *,
    measured_w_mm: float = 0.0,
    measured_h_mm: float = 0.0,
    beta_layout_used: bool = False,
    extract_stats: dict | None = None,
) -> dict:
    """汇总 layout 诊断字段，写入 summary.json 顶层 layout。"""
    measured_h = measured_h_mm if measured_h_mm > 0 else float(
        map_stats.get("required_height_mm") or 0
    )
    measured_w = measured_w_mm if measured_w_mm > 0 else float(
        map_stats.get("required_width_mm") or 0
    )
    return {
        "mapping_mode": map_stats.get("mapping_mode", "linear_mm_per_px"),
        "pixel_per_mm_used": map_stats.get("pixel_per_mm_used", map_stats.get("pixel_per_mm")),
        "font_size_px_used": map_stats.get("font_size_px_used"),
        "char_height_mm_requested": map_stats.get("char_height_mm_requested"),
        "char_height_mm_measured": round(measured_h, 2),
        "char_spacing_mm_requested": map_stats.get("char_spacing_mm_requested"),
        "measured_text_width_mm": round(measured_w, 2),
        "measured_text_height_mm": round(measured_h, 2),
        "workspace_width_mm": map_stats.get("workspace_width_mm"),
        "workspace_height_mm": map_stats.get("workspace_height_mm"),
        "layout_fits_workspace": map_stats.get("layout_fits_workspace", True),
        "layout_overflow_width_mm": map_stats.get(
            "layout_overflow_width_mm", map_stats.get("shortage_width_mm", 0)
        ),
        "layout_overflow_height_mm": map_stats.get(
            "layout_overflow_height_mm", map_stats.get("shortage_height_mm", 0)
        ),
        "required_width_mm": map_stats.get("required_width_mm"),
        "required_height_mm": map_stats.get("required_height_mm"),
        "available_width_mm": map_stats.get("available_width_mm"),
        "available_height_mm": map_stats.get("available_height_mm"),
        "shortage_width_mm": map_stats.get("shortage_width_mm"),
        "shortage_height_mm": map_stats.get("shortage_height_mm"),
        "beta_layout_used": beta_layout_used,
        "multiline_enabled": bool(
            (extract_stats or map_stats).get("multiline_enabled", False)
        ),
        "line_count": (extract_stats or map_stats).get("line_count", 1),
        "line_spacing_mm_requested": (extract_stats or map_stats).get(
            "line_spacing_mm_requested", map_stats.get("line_spacing_mm_requested")
        ),
        "line_step_mm": (extract_stats or map_stats).get(
            "line_step_mm", map_stats.get("line_step_mm")
        ),
        "line_widths_mm": (extract_stats or map_stats).get(
            "line_widths_mm", map_stats.get("line_widths_mm")
        ),
    }


def _map_stats_from_stages(stage_stats: list[StageStats]) -> dict:
    for st in reversed(stage_stats):
        if st.name == "map" and st.stats:
            return st.stats
    return {}


def _stage_stats_to_json(stages: list[StageStats]) -> list[dict]:
    rows: list[dict] = []
    for s in stages:
        row: dict[str, Any] = {"name": s.name, "status": s.status, "stats": s.stats}
        if s.error:
            row["error"] = s.error
        rows.append(row)
    return rows


class OfflinePipelineRunner:
    """离线 Pipeline 端到端运行器。

    输入: text / mode / workplane / output_dir
    输出: 固定目录结构
    """

    def __init__(
        self,
        output_dir: str = "output",
        font_path: str | None = None,
        font_size_px: int = 600,
        canvas_w_px: float = 600.0,
        canvas_h_px: float = 600.0,
        px_per_mm: float = 10.0,
        allow_overflow: bool = False,
        path_config: PathConfig | None = None,
        process_config: WeldingProcessConfig | None = None,
        workspace_config: WorkspaceConfig | None = None,
        char_spacing_mm: float = 2.0,
        char_height_mm: float = 0.0,
        line_spacing_mm: float = 0.0,
        margin_left_mm: float = 0.0,
        margin_top_mm: float = 0.0,
        lua_config: LuaExportConfig | None = None,
        export_lua: bool = True,
        user_lang: str = "zh",
    ):
        self.output_dir = output_dir
        self.user_lang = user_lang if user_lang in ("zh", "en") else "zh"
        self.font_path = font_path or get_default_font_path()
        self.char_height_mm = char_height_mm
        self.font_size_px = font_size_px
        self.canvas_w_px = canvas_w_px
        self.canvas_h_px = canvas_h_px
        self.px_per_mm = px_per_mm
        self.char_spacing_mm = char_spacing_mm
        self.line_spacing_mm = max(0.0, line_spacing_mm)
        self.margin_left_mm = max(0.0, margin_left_mm)
        self.margin_top_mm = max(0.0, margin_top_mm)
        self.allow_overflow = allow_overflow
        self.lua_config = lua_config or LuaExportConfig()
        self.export_lua = export_lua
        self.path_config = path_config or PathConfig()
        self.process_config = process_config or WeldingProcessConfig()
        self.workspace_config = workspace_config or WorkspaceConfig()

    def run(
        self, text: str, mode: str, workplane: Any,
        *, extra_metadata: dict | None = None,
    ) -> RunResult:
        t_start = datetime.now()
        stage_stats: list[StageStats] = []
        warnings: list[str] = []
        errors: list[str] = []

        # 输出子目录
        # 过滤非法文件名字符（仅保留 alnum + _ - .）
        safe_text = "".join(c if c.isalnum() or c in "_-." else "_" for c in text)[:30]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        run_dir = os.path.join(self.output_dir, f"{ts}_{safe_text}_{mode}")
        os.makedirs(run_dir, exist_ok=True)
        files: dict[str, str] = {}

        # ── Stage 0: 字高 → font_size_px (二分 A 的 bbox 高度) ──
        if self.char_height_mm > 0 and self.px_per_mm > 0:
            target_px = self.char_height_mm * self.px_per_mm
            try:
                from PIL import ImageFont
                low, high, best = 1, 4000, self.font_size_px
                while low <= high:
                    mid = (low + high) // 2
                    font = ImageFont.truetype(self.font_path, mid)
                    bbox = font.getbbox("A")
                    gh = bbox[3] - bbox[1]
                    if gh <= target_px:
                        best = mid
                        low = mid + 1
                    else:
                        high = mid - 1
                self.font_size_px = best
            except Exception:
                pass

        # ── Stage 1-2: render + extract ──
        extract_stats: dict = {}
        multiline_contour = False
        try:
            from pipeline.vision import ContourExtractor
            from pipeline.multiline_layout import (
                layout_contour_multiline,
                layout_legacy_single_string,
                split_text_lines,
            )
            rasterizer = FontRasterizer(
                default_font_path=self.font_path,
                default_font_size_px=self.font_size_px,
            )
            lines = split_text_lines(text)
            line_count = len(lines)
            multiline_contour = mode == "contour" and line_count >= 1

            if multiline_contour:
                strokes_raw, extract_stats = layout_contour_multiline(
                    lines,
                    rasterizer=rasterizer,
                    path_config=self.path_config,
                    char_spacing_mm=self.char_spacing_mm,
                    char_height_mm=self.char_height_mm,
                    line_spacing_mm=self.line_spacing_mm,
                    px_per_mm=self.px_per_mm,
                    contour_extractor_cls=ContourExtractor,
                )
            else:
                strokes_raw, extract_stats = layout_legacy_single_string(
                    text,
                    rasterizer=rasterizer,
                    path_config=self.path_config,
                    char_spacing_mm=self.char_spacing_mm,
                    px_per_mm=self.px_per_mm,
                    mode=mode,
                    contour_extractor_cls=ContourExtractor,
                    skeleton_extractor_mod=None,
                )

            linebox_h = extract_stats.get("linebox_height_px", 0)
            baseline_px = extract_stats.get("baseline_px", 0)
            ascent = extract_stats.get("ascent_px", 0)
            descent = extract_stats.get("descent_px", 0)
            char_baseline_info = extract_stats.get("char_baseline", {})
            layout_w_px = float(extract_stats.get("layout_w_px", 0))
            total_glyph_w_px = layout_w_px
            extract_stats["font_size_px"] = self.font_size_px
            extract_stats["char_height_mm_requested"] = self.char_height_mm
            extract_stats["char_spacing_mm_requested"] = self.char_spacing_mm
            extract_stats["line_spacing_mm_requested"] = self.line_spacing_mm
            extract_stats["margin_left_mm_requested"] = self.margin_left_mm
            extract_stats["margin_top_mm_requested"] = self.margin_top_mm
            extract_stats["strokes"] = len(strokes_raw)
            if "chars" not in extract_stats:
                extract_stats["chars"] = len(text)

            stage_stats.append(StageStats(name="extract", status="ok", stats=extract_stats))
        except Exception as exc:
            errors.append(stage_error("extract", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        if not strokes_raw:
            errors.append(no_strokes_extracted(lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 3: clean ──
        try:
            from pipeline.path import clean_and_resample_strokes
            strokes_cl, s3 = clean_and_resample_strokes(strokes_raw, px_per_mm=self.px_per_mm, config=self.path_config)
            stage_stats.append(StageStats(name="clean", status="ok", stats=s3))
        except Exception as exc:
            errors.append(stage_error("clean", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 4: refine ──
        try:
            from pipeline.path import AdaptivePathRefiner
            strokes_rf, s4 = AdaptivePathRefiner.refine_strokes(strokes_cl, self.path_config, px_per_mm=self.px_per_mm)
            stage_stats.append(StageStats(name="refine", status="ok", stats=s4))
        except Exception as exc:
            errors.append(stage_error("refine", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 5: schedule ──
        try:
            from pipeline.path import PathScheduler
            if multiline_contour and extract_stats.get("line_count", 1) > 0:
                strokes_sc, s5 = PathScheduler.schedule_by_line_groups(
                    strokes_rf, strategy="nearest", allow_reverse=True)
            else:
                strokes_sc, s5 = PathScheduler.schedule(
                    strokes_rf, strategy="nearest", allow_reverse=True)
            stage_stats.append(StageStats(name="schedule", status="ok", stats=s5))
        except Exception as exc:
            errors.append(stage_error("schedule", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── 排版起点：仅左上边距（右/下可贴示教边界）
        if (self.margin_left_mm > 0 or self.margin_top_mm > 0) and self.px_per_mm > 0:
            from pipeline.layout_inset import apply_layout_origin_offset

            strokes_sc = apply_layout_origin_offset(
                strokes_sc,
                self.margin_left_mm,
                self.margin_top_mm,
                self.px_per_mm,
            )

        # ── Stage 6: map ──
        try:
            from pipeline.mapping import PoseMapper
            from pipeline.layout_inset import effective_writable_size_mm

            # 尺寸校验：文字是否超出 WorkPlane
            layout_bbox_px = None
            required_w_mm, required_h_mm = 0.0, 0.0
            shortage_w_mm, shortage_h_mm = 0.0, 0.0
            overflow_detected = False
            if strokes_sc and self.px_per_mm > 0:
                all_x = [p.x for s in strokes_sc for p in s.points_px]
                all_y = [p.y for s in strokes_sc for p in s.points_px]
                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)
                layout_bbox_px = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}
                required_w_mm = (max_x - min_x) / self.px_per_mm
                required_h_mm = (max_y - min_y) / self.px_per_mm
                wp_w = getattr(workplane, "width_mm", 0)
                wp_h = getattr(workplane, "height_mm", 0)
                available_w, available_h = effective_writable_size_mm(
                    wp_w, wp_h, self.margin_left_mm, self.margin_top_mm)
                shortage_w_mm = max(0.0, required_w_mm - available_w)
                shortage_h_mm = max(0.0, required_h_mm - available_h)
                overflow_detected = shortage_w_mm > 0.01 or shortage_h_mm > 0.01

                if overflow_detected:
                    msg = workplane_overflow_message(
                        required_w_mm, required_h_mm,
                        available_w, available_h,
                        shortage_w_mm, shortage_h_mm,
                        lang=self.user_lang,
                    )
                    warnings.append(msg)
                    if not self.allow_overflow:
                        errors.append(msg)
                        err_stats = {
                            "layout_bbox_px": layout_bbox_px,
                            "required_width_mm": round(required_w_mm, 1),
                            "required_height_mm": round(required_h_mm, 1),
                            "available_width_mm": round(available_w, 1),
                            "available_height_mm": round(available_h, 1),
                            "shortage_width_mm": round(shortage_w_mm, 1),
                            "shortage_height_mm": round(shortage_h_mm, 1),
                            "allow_overflow": self.allow_overflow,
                            "overflow_detected": True,
                            "mapping_mode": "linear_mm_per_px",
                            "pixel_per_mm_used": self.px_per_mm,
                            "font_size_px_used": self.font_size_px,
                            "char_height_mm_requested": self.char_height_mm,
                            "char_spacing_mm_requested": self.char_spacing_mm,
                            "line_spacing_mm_requested": self.line_spacing_mm,
                            "margin_left_mm_requested": self.margin_left_mm,
                            "margin_top_mm_requested": self.margin_top_mm,
                            "line_count": extract_stats.get("line_count", 1),
                            "multiline_enabled": extract_stats.get("multiline_enabled", False),
                            "line_step_mm": extract_stats.get("line_step_mm"),
                            "line_widths_mm": extract_stats.get("line_widths_mm"),
                            "workspace_width_mm": round(available_w, 1),
                            "workspace_height_mm": round(available_h, 1),
                            "layout_fits_workspace": False,
                            "layout_overflow_width_mm": round(shortage_w_mm, 1),
                            "layout_overflow_height_mm": round(shortage_h_mm, 1),
                            "beta_layout_used": mode != "contour",
                        }
                        stage_stats.append(StageStats(name="map", status="error", stats=err_stats,
                            error=msg))
                        return _fail(text, mode, run_dir, stage_stats, errors)

            strokes_to_map = strokes_sc
            # map_w/map_h: 基于工作平面物理尺寸 × 像素密度
            # pixel(0,0) → TL 机器人左上，pixel(img_w,img_h) → BR 机器人右下
            wp_w = getattr(workplane, "width_mm", 0)
            wp_h = getattr(workplane, "height_mm", 0)
            if wp_w > 0 and self.px_per_mm > 0:
                map_w = wp_w * self.px_per_mm
            else:
                map_w = total_glyph_w_px if total_glyph_w_px > 0 else self.canvas_w_px
            layout_h_px = float(extract_stats.get("layout_h_px", 0) or linebox_h)
            if wp_h > 0 and self.px_per_mm > 0:
                map_h = wp_h * self.px_per_mm
            else:
                map_h = layout_h_px if layout_h_px > 0 else self.canvas_h_px

            strokes_mp, s6 = PoseMapper.map_strokes(strokes_to_map, workplane, map_w, map_h)

            s6["map_w_px"] = round(map_w, 1)
            s6["map_h_px"] = round(map_h, 1)
            s6["pixel_per_mm"] = self.px_per_mm
            s6["mapping_mode"] = "linear_mm_per_px"
            s6["char_height_mm_requested"] = self.char_height_mm
            s6["char_spacing_mm_requested"] = self.char_spacing_mm
            s6["line_spacing_mm_requested"] = self.line_spacing_mm
            s6["margin_left_mm_requested"] = self.margin_left_mm
            s6["margin_top_mm_requested"] = self.margin_top_mm
            s6["multiline_enabled"] = extract_stats.get("multiline_enabled", False)
            s6["line_count"] = extract_stats.get("line_count", 1)
            s6["line_step_mm"] = extract_stats.get("line_step_mm")
            s6["line_widths_mm"] = extract_stats.get("line_widths_mm")
            s6["beta_layout_used"] = mode != "contour"
            s6["pixel_per_mm_used"] = self.px_per_mm
            s6["font_size_px_used"] = self.font_size_px
            s6["layout_fits_workspace"] = not overflow_detected
            s6["layout_overflow_width_mm"] = round(shortage_w_mm, 1)
            s6["layout_overflow_height_mm"] = round(shortage_h_mm, 1)
            s6["workspace_width_mm"] = round(getattr(workplane, "width_mm", 0), 1)
            s6["workspace_height_mm"] = round(getattr(workplane, "height_mm", 0), 1)

            # 骨架模式 baseline 安全网：用字符 pixel x 范围分组后检查跨字符基线
            if mode == "skeleton" and strokes_mp and linebox_h > 0 and not multiline_contour:
                glyphs = rasterizer.render_text_linebox(text)
                char_x_ranges_px = []
                spacing_px = self.char_spacing_mm * self.px_per_mm
                x_acc = 0.0
                for glyph in glyphs:
                    char_x_ranges_px.append((x_acc, x_acc + glyph.char_w_px))
                    x_acc += glyph.char_w_px + spacing_px

                bl_shifts = _baseline_sanity_check(
                    strokes_mp,
                    layout_w_px=layout_w_px,
                    map_w=map_w,
                    char_x_ranges_px=char_x_ranges_px,
                    char_labels=list(text),
                )
                if bl_shifts:
                    char_shifts = bl_shifts.get("char_shifts", {})
                    per_group = bl_shifts.get("per_group", [])
                    max_shift = max((abs(v) for v in char_shifts.values()), default=0)
                    if per_group:
                        s6["baseline_per_group"] = per_group
                    s6["baseline_grouping_method"] = bl_shifts.get("grouping_method", "N/A")
                    if max_shift > 5.0:
                        s6["baseline_shift_max_mm"] = round(max_shift, 3)
                        s6["baseline_shift_by_char"] = {
                            k: round(v, 3) for k, v in char_shifts.items()}
                        if max_shift > 20.0:
                            warnings.append(
                                skeleton_baseline_drift_warning(
                                    max_shift, lang=self.user_lang))

            s6["map_w_px"] = round(map_w, 1)
            s6["map_h_px"] = round(map_h, 1)

            s6["layout_bbox_px"] = layout_bbox_px
            s6["required_width_mm"] = round(required_w_mm, 1)
            s6["required_height_mm"] = round(required_h_mm, 1)
            s6["shortage_width_mm"] = round(shortage_w_mm, 1)
            s6["shortage_height_mm"] = round(shortage_h_mm, 1)
            s6["allow_overflow"] = self.allow_overflow
            s6["overflow_detected"] = overflow_detected
            stage_stats.append(StageStats(name="map", status="ok", stats=s6))
        except Exception as exc:
            errors.append(stage_error("map", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 7: plan ──
        try:
            from pipeline.process import WeldingProcessPlanner
            segs, s7 = WeldingProcessPlanner.plan(
                strokes_mp, self.process_config,
                workplane=workplane, workspace_cfg=self.workspace_config,
            )
            stage_stats.append(StageStats(name="plan", status="ok", stats=s7))
        except Exception as exc:
            errors.append(stage_error("plan", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 8: export ──
        lua_path = ""
        lua_stats: dict = {}
        try:
            from pipeline.output import PointsWriter, JobWriter, DebugExporter
            pt = str(Path(run_dir) / POINTS_FILENAME)
            jb = str(Path(run_dir) / JOB_FILENAME)
            PointsWriter.write_points_txt(segs, pt)
            JobWriter.write_job_json(jb,
                input_info={"text": text, "mode": mode},
                configs={"process": self.process_config, "path": self.path_config, "workspace": self.workspace_config},
                workplane=workplane, strokes=strokes_mp, segments=segs,
                export_files={"points_txt": pt, "job_json": jb},
                stage_stats={s.name: s.stats for s in stage_stats},
                metadata=extra_metadata,
            )
            preview_results = DebugExporter.write_run_preview(
                strokes_sc, segs, run_dir,
                title_prefix=f"{text} ({mode})",
                cjk_font_path=self.font_path,
                workplane=workplane,
                show_travel_in_execution=True,
            )
            preview_meta = preview_results.get("preview_meta", {})

            # Lua 脚本导出（绘图/写字模式可关闭）
            lua_filename = ""
            if self.export_lua:
                from pipeline.output.lua_exporter import LuaExporter, sanitize_lua_filename
                if self.lua_config.use_text_as_filename:
                    safe_name = sanitize_lua_filename(
                        text, fallback=self.lua_config.fallback_filename.replace(".lua", ""))
                    lua_filename = f"{safe_name}.lua"
                else:
                    lua_filename = self.lua_config.lua_filename
                lua_path = str(Path(run_dir) / lua_filename)
                lua_exporter = LuaExporter(config=self.lua_config)
                lua_stats = lua_exporter.export(segs, lua_path, metadata={
                    "text": text, "mode": mode,
                    "point_spacing": str(self.process_config.weld_point_spacing_mm),
                })
                files["lua_script"] = lua_path

            files["points_txt"] = pt
            files["job_json"] = jb
            files["strokes_preview_png"] = str(Path(run_dir) / STROKES_PREVIEW)
            files["execution_preview_png"] = str(Path(run_dir) / EXECUTION_PREVIEW)
            files["segments_preview_png"] = str(Path(run_dir) / SEGMENTS_PREVIEW)
            files["combined_preview_png"] = str(Path(run_dir) / COMBINED_PREVIEW)
            files["weld_only_preview_png"] = str(Path(run_dir) / WELD_ONLY_PREVIEW)
            wp_path = str(Path(run_dir) / "preview_workplane.png")
            if os.path.exists(wp_path):
                files["workplane_preview_png"] = wp_path
            wp_stats = preview_results.get("workplane_preview", {})
            export_stats = {"preview_meta": preview_meta}
            if wp_stats:
                export_stats["workplane_preview"] = wp_stats
            stage_stats.append(StageStats(name="export", status="ok", stats=export_stats))
        except Exception as exc:
            errors.append(stage_error("export", exc, lang=self.user_lang))
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── 汇总 ──
        total_rp = sum(len(s.points) for s in segs)
        dur = (datetime.now() - t_start).total_seconds() * 1000
        map_stats_ok = _map_stats_from_stages(stage_stats)
        meas_w, meas_h = _weld_bbox_mm_from_segments(segs)
        layout_summary = _layout_summary_from_map_stats(
            map_stats_ok,
            measured_w_mm=meas_w,
            measured_h_mm=meas_h,
            beta_layout_used=(mode != "contour"),
            extract_stats=extract_stats,
        )
        summary = {
            "pipeline_version": "8.7b",
            "text": text,
            "mode": mode,
            "ok": True,
            "duration_ms": round(dur, 1),
            "layout": layout_summary,
            "preview": preview_meta,
            "baseline": {
                "linebox_height_px": linebox_h,
                "baseline_y_px": baseline_px,
                "ascent_px": ascent,
                "descent_px": descent,
                "font_size_px": self.font_size_px,
                "char_baseline": char_baseline_info,
            },
            "lua_export": {
                "lua_path": os.path.basename(lua_path) if lua_path else "",
                "lua_filename": lua_filename,
                "lua_source_text": text,
                "lua_filename_sanitized": (
                    lua_filename.replace(".lua", "") if lua_filename else ""
                ),
                "movl_count": lua_stats.get("total_movl_lines", 0),
                "arc_on_count": lua_stats.get("arc_on_count", 0),
                "arc_off_count": lua_stats.get("arc_off_count", 0),
                "duplicates_skipped": lua_stats.get("duplicates_skipped", 0),
                "warnings": lua_stats.get("warnings", []),
                "wait_insert_enabled": self.lua_config.insert_wait,
                "wait_every_movl_count": self.lua_config.wait_every_movl,
                "wait_duration_ms": self.lua_config.wait_duration_ms,
                "wait_insert_count": lua_stats.get("wait_insert_count", 0),
            },
            "stats": {"strokes_raw": len(strokes_raw), "strokes_mapped": len(strokes_mp),
                      "segments": len(segs), "robot_points": total_rp},
            "output_files": {k: os.path.basename(v) for k, v in files.items()},
            "stage_stats": _stage_stats_to_json(stage_stats),
            "warnings": warnings,
            "errors": errors,
        }
        spath = str(Path(run_dir) / SUMMARY_FILENAME)
        with open(spath, "w", encoding="utf-8") as f:
            _json.dump(summary, f, ensure_ascii=False, indent=2)
        files["summary_json"] = spath

        return RunResult(
            ok=True, text=text, mode=mode, output_dir=run_dir, files=files,
            stage_stats=stage_stats, total_strokes_raw=len(strokes_raw),
            total_strokes_mapped=len(strokes_mp), total_segments=len(segs),
            total_robot_points=total_rp, duration_ms=dur,
            warnings=warnings, errors=errors,
        )




def _baseline_sanity_check(strokes, *, layout_w_px, map_w,
                          char_x_ranges_px=None, char_labels=None) -> dict:
    """骨架模式跨字符基线诊断（仅报告，不修改 stroke）。

    当提供 char_x_ranges_px 时使用精确字符边界分组；
    否则回退到自适应 gap 聚类。

    Returns:
        dict with char_shifts, per_group, median_bottom_mm, max_drift_mm, groups
    """
    if not strokes or map_w <= 0:
        return {}

    # 收集 stroke 的 robot bbox
    stroke_data = []
    for s in strokes:
        rp = s.metadata.get("robot_points")
        if not rp or len(rp) < 2:
            continue
        ys = [p.y for p in rp]
        xs = [p.x for p in rp]
        stroke_data.append({
            "stroke": s, "cx": sum(xs) / len(xs),
            "min_x": min(xs), "max_x": max(xs),
            "min_y": min(ys), "max_y": max(ys),
            "span": max(ys) - min(ys),
        })

    if len(stroke_data) < 2:
        return {}

    all_x_min = min(d["min_x"] for d in stroke_data)
    all_x_max = max(d["max_x"] for d in stroke_data)
    total_w = all_x_max - all_x_min
    if total_w <= 0:
        return {}

    stroke_data.sort(key=lambda d: d["cx"])

    # ---- 字符分组：优先使用精确 char_x_ranges_px ----
    if char_x_ranges_px and map_w > 0 and total_w > 0:
        # 将 pixel x 范围映射到 robot x 范围
        # robot_x = origin_x + (pixel_x / map_w) * total_w  (简化线性映射)
        scale = total_w / layout_w_px if layout_w_px > 0 else total_w / map_w
        robot_origin_x = all_x_min  # 近似：min robot x ≈ origin

        groups: list[list[dict]] = []
        for ci, (px_start, px_end) in enumerate(char_x_ranges_px):
            rx_start = robot_origin_x + px_start * scale
            rx_end = robot_origin_x + px_end * scale
            group = [d for d in stroke_data
                     if d["cx"] >= rx_start and d["cx"] < rx_end]
            if group:
                groups.append(group)

        # 确保所有 stroke 被覆盖：未分配的 stroke 归入最近组
        assigned = set(id(d["stroke"]) for g in groups for d in g)
        unassigned = [d for d in stroke_data if id(d["stroke"]) not in assigned]
        for d in unassigned:
            # 放入最近组
            best_gi = min(range(len(groups)),
                          key=lambda i: abs(d["cx"] - (
                              sum(d2["cx"] for d2 in groups[i]) / max(len(groups[i]), 1))))
            groups[best_gi].append(d)
    else:
        # ---- Fallback: 自适应 gap 聚类 ----
        gaps = [stroke_data[i+1]["min_x"] - stroke_data[i]["max_x"]
                for i in range(len(stroke_data) - 1)]
        if not gaps:
            return {}

        mean_gap = sum(gaps) / len(gaps) if gaps else 5.0
        char_boundary_threshold = max(mean_gap * 2.5, 10.0)

        groups = []
        curr = [stroke_data[0]]
        for i in range(1, len(stroke_data)):
            d = stroke_data[i]
            gap = d["min_x"] - curr[-1]["max_x"]
            if gap > char_boundary_threshold:
                groups.append(curr)
                curr = [d]
            else:
                curr.append(d)
        groups.append(curr)

    if not groups or len(groups) < 2:
        return {"note": f"single char group ({len(groups)}), no cross-char check"}

    # ---- 每组的 baseline 代标 = 最长 span stroke 的 min_y ----
    char_bottoms = []
    for gi, group in enumerate(groups):
        if not group:
            continue
        body = max(group, key=lambda d: d["span"])
        char_bottoms.append(body["min_y"])

    if len(char_bottoms) < 2:
        return {"note": "only one char group with data"}

    median = sorted(char_bottoms)[len(char_bottoms) // 2]
    max_drift = max(abs(b - median) for b in char_bottoms)

    # 每个字符组的详细信息
    per_group = []
    for gi, group in enumerate(groups):
        if not group:
            continue
        label = char_labels[gi] if char_labels and gi < len(char_labels) else f"g{gi}"
        body = max(group, key=lambda d: d["span"])
        bottoms = sorted(d["min_y"] for d in group)
        body_bottom = body["min_y"]
        drift = body_bottom - median
        # 分类: dot (短stroke, span < 3mm), body (最长 span), noise (其余短 stroke)
        for d in group:
            d["classification"] = "body" if d is body else \
                ("dot" if d["span"] < 3.0 else "noise")
        per_group.append({
            "char": label,
            "stroke_count": len(group),
            "body_stroke_idx": group.index(body),
            "body_span_mm": round(body["span"], 2),
            "bottom_y_mm": round(body_bottom, 2),
            "baseline_drift_mm": round(drift, 2),
            "stroke_types": sorted({d["classification"] for d in group}),
        })

    return {
        "char_shifts": {p["char"]: round(p["baseline_drift_mm"], 1) for p in per_group},
        "per_group": per_group,
        "median_bottom_mm": round(median, 1),
        "max_drift_mm": round(max_drift, 1),
        "groups": len(groups),
        "grouping_method": "char_x_ranges" if char_x_ranges_px else "gap_clustering",
    }


def _fail(text, mode, run_dir, stages, errors):
    from pipeline.output.preview_writer import DebugExporter, PREVIEW_META_DEFAULTS

    map_stats = _map_stats_from_stages(stages)
    layout = _layout_summary_from_map_stats(map_stats) if map_stats else {}
    reason = "; ".join(errors) if errors else "pipeline failed"
    preview_meta: dict = {
        **PREVIEW_META_DEFAULTS,
        "generated": False,
        "not_generated_reason": reason,
    }
    files_out: dict[str, str] = {}
    if run_dir and os.path.isdir(run_dir):
        try:
            ph = str(Path(run_dir) / EXECUTION_PREVIEW)
            DebugExporter.write_overflow_preview_placeholder(ph, reason=reason)
            preview_meta["execution_preview_path"] = EXECUTION_PREVIEW
            preview_meta["placeholder"] = True
            files_out["execution_preview_png"] = ph
        except Exception:
            pass
    s = {"pipeline_version": "8.2b", "text": text, "mode": mode, "ok": False,
         "duration_ms": 0, "output_files": {},
         "layout": layout,
         "preview": preview_meta,
         "stage_stats": _stage_stats_to_json(stages),
         "warnings": [], "errors": errors}
    sp = str(Path(run_dir) / SUMMARY_FILENAME)
    with open(sp, "w", encoding="utf-8") as f:
        _json.dump(s, f, ensure_ascii=False, indent=2)
    files_out["summary_json"] = sp
    return RunResult(ok=False, text=text, mode=mode, output_dir=run_dir,
        files=files_out, stage_stats=stages, errors=errors)
