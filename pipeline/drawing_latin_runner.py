"""绘画页英数字单线字 (latin_stroke / Hershey) → 绘图工艺 → CRI 轨迹。

不走 weld_process / Lua / 焊接 lead-overlap。
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from core.types import ImageDrawingConfig, PathConfig, ProcessSegment, RobotPoint, Stroke
from pipeline.cri_trajectory_export import (
    TRAJECTORY_FILENAME,
    points_to_trajectory,
    write_trajectory_txt,
)
from pipeline.layout_inset import apply_layout_origin_offset
from pipeline.mapping import PoseMapper
from pipeline.mapping.workplane import WorkPlane
from pipeline.multiline_layout import split_text_lines
from pipeline.process.drawing_process import DrawingProcessPlanner
from pipeline.text_pipeline import TEXT_SOURCE_LATIN_STROKE, build_text_pipeline
from pipeline.weld_skeleton_latin import validate_weld_skeleton_text

STROKES_PREVIEW = "preview_strokes.png"
EXECUTION_PREVIEW = "preview_execution.png"
DRAW_ONLY_PREVIEW = "preview_draw_only.png"


@dataclass
class DrawingTextRunResult:
    ok: bool
    error: str = ""
    output_dir: str = ""
    files: dict[str, str] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def run_latin_stroke_to_cri(
    text: str,
    workplane: WorkPlane,
    *,
    hershey_style: str = "futural",
    char_height_mm: float = 60.0,
    char_spacing_mm: float = 2.0,
    line_spacing_mm: float = 0.0,
    margin_left_mm: float = 0.0,
    margin_top_mm: float = 0.0,
    px_per_mm: float = 10.0,
    drawing_config: ImageDrawingConfig | None = None,
    output_dir: str | Path = "output/drawing_latin_run",
    user_lang: str = "zh",
) -> DrawingTextRunResult:
    """Hershey 字形 → 工作平面映射 → DrawingProcessPlanner → CRI + 预览。"""
    drawing_config = drawing_config or ImageDrawingConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    t0 = time.perf_counter()

    sk_err = validate_weld_skeleton_text(text, lang=user_lang)
    if sk_err:
        return DrawingTextRunResult(ok=False, error=sk_err, output_dir=str(out))

    lines = split_text_lines(text)
    path_cfg = PathConfig(mode="skeleton", skeleton_source="hershey", hershey_style=hershey_style)

    try:
        from pipeline.raster.hershey_font_renderer import (
            RENDERER_MODULE,
            render_hershey_multiline_to_strokes,
            render_hershey_text_to_strokes,
        )
    except ImportError as exc:
        return DrawingTextRunResult(ok=False, error=str(exc), output_dir=str(out))

    try:
        if len(lines) > 1:
            strokes_raw, extract_stats = render_hershey_multiline_to_strokes(
                lines,
                style=hershey_style,
                char_height_mm=char_height_mm,
                char_spacing_mm=char_spacing_mm,
                line_spacing_mm=line_spacing_mm,
                px_per_mm=px_per_mm,
            )
        else:
            single = lines[0] if lines else ""
            strokes_raw, extract_stats = render_hershey_text_to_strokes(
                single,
                style=hershey_style,
                char_height_mm=char_height_mm,
                char_spacing_mm=char_spacing_mm,
                px_per_mm=px_per_mm,
            )
    except Exception as exc:
        return DrawingTextRunResult(ok=False, error=str(exc), output_dir=str(out))

    if extract_stats.get("ttf_fallback_used"):
        return DrawingTextRunResult(
            ok=False,
            error="Hershey latin_stroke does not allow TTF fallback",
            output_dir=str(out),
        )

    if not strokes_raw:
        return DrawingTextRunResult(ok=False, error="no strokes extracted", output_dir=str(out))

    strokes_preview_src = list(strokes_raw)

    from pipeline.path import AdaptivePathRefiner, PathScheduler, clean_and_resample_strokes

    strokes_cl, _ = clean_and_resample_strokes(
        strokes_raw, px_per_mm=px_per_mm, config=path_cfg,
    )
    strokes_rf, _ = AdaptivePathRefiner.refine_strokes(
        strokes_cl, path_cfg, px_per_mm=px_per_mm,
    )
    if extract_stats.get("multiline_enabled"):
        strokes_sc, _ = PathScheduler.schedule_by_line_groups(
            strokes_rf, strategy="nearest", allow_reverse=True,
        )
    else:
        strokes_sc, _ = PathScheduler.schedule_char_order_nearest_endpoint(
            strokes_rf, char_key="weld_char_index", allow_reverse=True,
        )

    if margin_left_mm > 0 or margin_top_mm > 0:
        strokes_sc = apply_layout_origin_offset(
            strokes_sc, margin_left_mm, margin_top_mm, px_per_mm,
        )

    layout_h_px = float(extract_stats.get("layout_h_px", 0))
    layout_w_px = float(extract_stats.get("layout_w_px", 0))
    if strokes_sc:
        all_x = [p.x for s in strokes_sc for p in s.points_px]
        all_y = [p.y for s in strokes_sc for p in s.points_px]
        bbox_w = max(all_x) - min(all_x) if all_x else layout_w_px
        bbox_h = max(all_y) - min(all_y) if all_y else layout_h_px
    else:
        bbox_w, bbox_h = layout_w_px, layout_h_px

    wp_w = getattr(workplane, "width_mm", 0)
    wp_h = getattr(workplane, "height_mm", 0)
    map_w = wp_w * px_per_mm if wp_w > 0 else max(bbox_w, 1.0)
    map_h = wp_h * px_per_mm if wp_h > 0 else max(bbox_h, layout_h_px, 1.0)

    mapped_strokes, map_stats = PoseMapper.map_strokes(
        strokes_sc, workplane, map_w, map_h,
    )
    if not mapped_strokes:
        return DrawingTextRunResult(ok=False, error="mapping produced no strokes", output_dir=str(out))

    try:
        segments, plan_stats = DrawingProcessPlanner.plan(mapped_strokes, drawing_config)
    except ValueError as exc:
        return DrawingTextRunResult(ok=False, error=str(exc), output_dir=str(out))

    if not segments:
        return DrawingTextRunResult(ok=False, error="no draw segments", output_dir=str(out))

    warnings.extend(plan_stats.get("warnings", []))
    robot_points = _segments_to_robot_points(segments)
    samples, traj_warnings = points_to_trajectory(
        robot_points,
        sample_rate_hz=drawing_config.sample_rate_hz,
        target_speed_mm_s=drawing_config.draw_speed_mm_s,
    )
    warnings.extend(traj_warnings)
    if not samples:
        return DrawingTextRunResult(ok=False, error="empty trajectory", output_dir=str(out))

    files: dict[str, str] = {}
    traj_path = out / TRAJECTORY_FILENAME
    write_trajectory_txt(samples, traj_path)
    files[TRAJECTORY_FILENAME] = str(traj_path)

    from pipeline.output.preview_writer import DebugExporter

    raw_path = out / STROKES_PREVIEW
    DebugExporter.write_strokes_preview(
        strokes_preview_src,
        raw_path,
        title="Raw Strokes Preview (Hershey)",
        canvas_w=map_w,
        canvas_h=map_h,
    )
    files[STROKES_PREVIEW] = str(raw_path)

    exec_path = out / EXECUTION_PREVIEW
    exec_stats = DebugExporter.write_drawing_execution_preview(
        segments, exec_path, workplane=workplane, show_travel=True,
    )
    files[EXECUTION_PREVIEW] = str(exec_path)

    draw_path = out / DRAW_ONLY_PREVIEW
    draw_stats = DebugExporter.write_draw_only_preview(
        segments, draw_path, workplane=workplane,
    )
    files[DRAW_ONLY_PREVIEW] = str(draw_path)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    text_pipeline = build_text_pipeline(
        TEXT_SOURCE_LATIN_STROKE,
        hershey_style=hershey_style,
        target_process="drawing",
    )
    skeleton_summary = {
        "skeleton_source": "hershey",
        "renderer": RENDERER_MODULE,
        "hershey_style": hershey_style,
        "ttf_fallback_used": False,
        "stroke_count": len(strokes_raw),
        "glyph_count": extract_stats.get("glyph_count", extract_stats.get("chars", 0)),
        "hershey_open_stroke_count": extract_stats.get("hershey_open_stroke_count", 0),
        "hershey_closed_stroke_count": extract_stats.get("hershey_closed_stroke_count", 0),
    }
    drawing_summary = {
        "z_draw_mm": drawing_config.z_draw_mm,
        "z_safe_mm": drawing_config.z_safe_mm,
        "draw_speed_mm_s": drawing_config.draw_speed_mm_s,
        "travel_speed_mm_s": drawing_config.travel_speed_mm_s,
        "point_spacing_mm": drawing_config.point_spacing_mm,
        "trajectory_file": TRAJECTORY_FILENAME,
        "lead_in_count": 0,
        "lead_out_count": 0,
        "overlap_count": 0,
        "arc_on_count": 0,
        "arc_off_count": 0,
        "weld_process_used": False,
    }
    stats = {
        "extract": extract_stats,
        "map": map_stats,
        "plan": plan_stats,
        "trajectory": {
            "input_robot_points": len(robot_points),
            "output_samples": len(samples),
        },
        "preview_execution": exec_stats,
        "preview_draw_only": draw_stats,
        "duration_ms": round(elapsed_ms, 1),
    }
    summary = {
        "ok": True,
        "text": text,
        "text_pipeline": text_pipeline,
        "drawing": drawing_summary,
        "skeleton": skeleton_summary,
        "files": {k: Path(v).name for k, v in files.items()},
        "stats": stats,
        "warnings": warnings,
    }
    summary_path = out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    files["summary.json"] = str(summary_path)

    return DrawingTextRunResult(
        ok=True,
        output_dir=str(out),
        files=files,
        stats=stats,
        warnings=warnings,
    )


def make_run_output_dir(base_dir: str | Path, text: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "_-." else "_" for c in text)[:30]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return Path(base_dir) / f"{ts}_{safe}_latin_stroke"


def _segments_to_robot_points(segments: list[ProcessSegment]) -> list[RobotPoint]:
    out: list[RobotPoint] = []
    tol = 1e-4
    for seg in segments:
        for p in seg.points:
            if out:
                last = out[-1]
                d = math.hypot(p.x - last.x, p.y - last.y, p.z - last.z)
                if d < tol:
                    continue
            out.append(p)
    return out
