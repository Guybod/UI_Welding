"""图片模式离线 runner — 预处理 → 工作平面映射 → 绘图工艺 → CRI 轨迹。"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, replace
from pathlib import Path

from core.types import (
    ImageDrawingConfig,
    ImageProcessConfig,
    ImageRunResult,
    PixelPoint,
    PlanePoint,
    ProcessSegment,
    RobotPoint,
    Stroke,
)
from pipeline.cri_trajectory_export import (
    TRAJECTORY_FILENAME,
    points_to_trajectory,
    write_trajectory_txt,
)
from pipeline.mapping.workplane import WorkPlane
from pipeline.process.drawing_process import DrawingProcessPlanner
from pipeline.vision.image_preprocessor import (
    ImageProcessResult,
    process_image,
    write_image_debug_previews,
)


@dataclass
class _FitTransform:
    mode: str
    image_width_px: float
    image_height_px: float
    margin_mm: float
    usable_width_mm: float
    usable_height_mm: float
    bbox_min_x: float
    bbox_min_y: float
    bbox_max_x: float
    bbox_max_y: float
    image_scale: float | None = None
    scale_x: float | None = None
    scale_y: float | None = None
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0

    def px_to_plane_mm(self, px: float, py: float) -> tuple[float, float]:
        if self.mode == "stretch":
            assert self.scale_x is not None and self.scale_y is not None
            u = self.offset_x_mm + px * self.scale_x
            v = self.offset_y_mm + py * self.scale_y
            return u, v
        assert self.image_scale is not None
        u = self.offset_x_mm + px * self.image_scale
        v = self.offset_y_mm + py * self.image_scale
        return u, v


def run_image_to_cri(
    image_path: str,
    workplane: WorkPlane,
    image_config: ImageProcessConfig | None = None,
    drawing_config: ImageDrawingConfig | None = None,
    output_dir: str | Path = "output/image_run",
) -> ImageRunResult:
    """图片 → strokes → 工作区映射 → 绘图轨迹 → CRI 文件与预览。"""
    image_config = image_config or ImageProcessConfig()
    drawing_config = drawing_config or ImageDrawingConfig()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    t0 = time.perf_counter()

    prep = process_image(image_path, image_config)
    if not prep.ok:
        return ImageRunResult(
            ok=False,
            error=prep.error or "image preprocessing failed",
            output_dir=str(out),
            warnings=list(prep.warnings),
        )
    warnings.extend(prep.warnings)

    img_w, img_h = prep.original_size
    fit = _compute_fit_transform(
        prep.strokes_px,
        img_w,
        img_h,
        workplane,
        drawing_config.margin_mm,
        image_config.fit_mode,
    )

    mapped_strokes = _map_strokes_to_workplane(prep.strokes_px, workplane, fit)
    if not mapped_strokes:
        return ImageRunResult(
            ok=False,
            error="no strokes after workplane mapping",
            output_dir=str(out),
            warnings=warnings,
        )

    px_points = sum(len(s.points_px) for s in mapped_strokes)
    if px_points > image_config.max_total_points:
        return ImageRunResult(
            ok=False,
            error=(
                f"stroke pixel points {px_points} exceeds "
                f"max_total_points={image_config.max_total_points}"
            ),
            output_dir=str(out),
            warnings=warnings,
            stats={"fit": _fit_to_dict(fit), "preprocess": prep.stats},
        )

    try:
        segments, plan_stats = DrawingProcessPlanner.plan(mapped_strokes, drawing_config)
    except ValueError as exc:
        return ImageRunResult(
            ok=False,
            error=str(exc),
            output_dir=str(out),
            warnings=warnings,
        )

    if not segments:
        return ImageRunResult(
            ok=False,
            error="no process segments generated",
            output_dir=str(out),
            warnings=warnings,
        )

    warnings.extend(plan_stats.get("warnings", []))
    total_robot_points = plan_stats.get("total_robot_points", 0)
    duration_s = _estimate_duration_s(segments)

    if total_robot_points > drawing_config.max_total_points:
        return ImageRunResult(
            ok=False,
            error=(
                f"total robot points {total_robot_points} exceeds "
                f"max_total_points={drawing_config.max_total_points}"
            ),
            output_dir=str(out),
            warnings=warnings,
            stats={
                "fit": _fit_to_dict(fit),
                "plan": plan_stats,
                "estimated_duration_s": round(duration_s, 3),
            },
        )

    if total_robot_points > drawing_config.max_robot_points:
        warnings.append(
            f"total robot points {total_robot_points} exceeds soft limit "
            f"max_robot_points={drawing_config.max_robot_points}"
        )

    files: dict[str, str] = {}

    debug_paths = write_image_debug_previews(prep, out)
    files.update(debug_paths)

    traj_path = out / TRAJECTORY_FILENAME
    robot_points = _segments_to_robot_points(segments)
    samples, traj_warnings = points_to_trajectory(
        robot_points,
        sample_rate_hz=drawing_config.sample_rate_hz,
        target_speed_mm_s=drawing_config.draw_speed_mm_s,
    )
    warnings.extend(traj_warnings)
    write_trajectory_txt(samples, traj_path)
    files[TRAJECTORY_FILENAME] = str(traj_path)

    from pipeline.output.preview_writer import DebugExporter

    exec_preview = out / "preview_execution.png"
    preview_stats = DebugExporter.write_drawing_execution_preview(
        segments, exec_preview, workplane=workplane, show_travel=True,
    )
    files["preview_execution.png"] = str(exec_preview)

    mapped_bbox = _mapped_bbox_uv(mapped_strokes)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    stats = {
        "image_path": str(image_path),
        "fit": _fit_to_dict(fit),
        "preprocess": prep.stats,
        "mapping": {
            "stroke_count": len(mapped_strokes),
            "workplane_width_mm": round(workplane.width_mm, 4),
            "workplane_height_mm": round(workplane.height_mm, 4),
            "mapped_bbox_uv": mapped_bbox,
        },
        "plan": plan_stats,
        "trajectory": {
            "input_robot_points": len(robot_points),
            "output_samples": len(samples),
            "sample_rate_hz": drawing_config.sample_rate_hz,
        },
        "total_robot_points": total_robot_points,
        "estimated_duration_s": round(duration_s, 3),
        "duration_ms": round(elapsed_ms, 1),
        "preview_execution": preview_stats,
    }

    summary_path = out / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "ok": True,
                "files": files,
                "stats": stats,
                "warnings": warnings,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    files["summary.json"] = str(summary_path)

    return ImageRunResult(
        ok=True,
        output_dir=str(out),
        files=files,
        stats=stats,
        warnings=warnings,
    )


def _compute_fit_transform(
    strokes: list[Stroke],
    img_w: int,
    img_h: int,
    workplane: WorkPlane,
    margin_mm: float,
    fit_mode: str,
) -> _FitTransform:
    min_x, min_y, max_x, max_y = _stroke_bbox(strokes, img_w, img_h)
    content_w = max(max_x - min_x, 1.0)
    content_h = max(max_y - min_y, 1.0)
    usable_w = max(workplane.width_mm - 2.0 * margin_mm, 1e-6)
    usable_h = max(workplane.height_mm - 2.0 * margin_mm, 1e-6)
    mode = (fit_mode or "contain").lower()

    if mode == "stretch":
        scale_x = usable_w / max(float(img_w), 1.0)
        scale_y = usable_h / max(float(img_h), 1.0)
        return _FitTransform(
            mode="stretch",
            image_width_px=float(img_w),
            image_height_px=float(img_h),
            margin_mm=margin_mm,
            usable_width_mm=usable_w,
            usable_height_mm=usable_h,
            bbox_min_x=min_x,
            bbox_min_y=min_y,
            bbox_max_x=max_x,
            bbox_max_y=max_y,
            scale_x=scale_x,
            scale_y=scale_y,
            offset_x_mm=margin_mm,
            offset_y_mm=margin_mm,
        )

    scale = min(usable_w / content_w, usable_h / content_h)
    offset_x = margin_mm + (usable_w - content_w * scale) / 2.0 - min_x * scale
    offset_y = margin_mm + (usable_h - content_h * scale) / 2.0 - min_y * scale
    return _FitTransform(
        mode="contain",
        image_width_px=float(img_w),
        image_height_px=float(img_h),
        margin_mm=margin_mm,
        usable_width_mm=usable_w,
        usable_height_mm=usable_h,
        bbox_min_x=min_x,
        bbox_min_y=min_y,
        bbox_max_x=max_x,
        bbox_max_y=max_y,
        image_scale=scale,
        offset_x_mm=offset_x,
        offset_y_mm=offset_y,
    )


def _stroke_bbox(
    strokes: list[Stroke],
    img_w: int,
    img_h: int,
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for s in strokes:
        for p in s.points_px:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return 0.0, 0.0, float(img_w), float(img_h)
    return min(xs), min(ys), max(xs), max(ys)


def _map_strokes_to_workplane(
    strokes: list[Stroke],
    workplane: WorkPlane,
    fit: _FitTransform,
) -> list[Stroke]:
    mapped: list[Stroke] = []
    orient = workplane.orientation_source
    for stroke in strokes:
        plane_points: list[PlanePoint] = []
        robot_points: list[RobotPoint] = []
        for px in stroke.points_px:
            u_mm, v_mm = fit.px_to_plane_mm(px.x, px.y)
            pm = PlanePoint(u_mm=u_mm, v_mm=v_mm)
            rp = workplane.plane_to_robot(pm, normal_offset_mm=0.0, orientation_source=orient)
            plane_points.append(pm)
            robot_points.append(rp)
        mapped.append(
            replace(
                stroke,
                points_mm=plane_points,
                metadata={**stroke.metadata, "robot_points": robot_points},
            )
        )
    return mapped


def _fit_to_dict(fit: _FitTransform) -> dict:
    d = {
        "mode": fit.mode,
        "margin_mm": fit.margin_mm,
        "usable_width_mm": round(fit.usable_width_mm, 6),
        "usable_height_mm": round(fit.usable_height_mm, 6),
        "offset_x_mm": round(fit.offset_x_mm, 6),
        "offset_y_mm": round(fit.offset_y_mm, 6),
        "bbox_min_x": fit.bbox_min_x,
        "bbox_min_y": fit.bbox_min_y,
        "bbox_max_x": fit.bbox_max_x,
        "bbox_max_y": fit.bbox_max_y,
        "image_width_px": fit.image_width_px,
        "image_height_px": fit.image_height_px,
    }
    if fit.mode == "contain":
        d["image_scale"] = round(fit.image_scale or 0.0, 8)
        d["scale_x"] = round(fit.image_scale or 0.0, 8)
        d["scale_y"] = round(fit.image_scale or 0.0, 8)
    else:
        d["scale_x"] = round(fit.scale_x or 0.0, 8)
        d["scale_y"] = round(fit.scale_y or 0.0, 8)
    return d


def _segments_to_robot_points(segments: list[ProcessSegment]) -> list[RobotPoint]:
    out: list[RobotPoint] = []
    tol = 1e-4
    for seg in segments:
        for p in seg.points:
            if out:
                last = out[-1]
                d = math.sqrt(
                    (p.x - last.x) ** 2
                    + (p.y - last.y) ** 2
                    + (p.z - last.z) ** 2
                )
                if d < tol:
                    continue
            out.append(p)
    return out


def _mapped_bbox_uv(strokes: list[Stroke]) -> dict:
    us: list[float] = []
    vs: list[float] = []
    for s in strokes:
        if not s.points_mm:
            continue
        for pm in s.points_mm:
            us.append(pm.u_mm)
            vs.append(pm.v_mm)
    if not us:
        return {}
    return {
        "min_u_mm": round(min(us), 4),
        "max_u_mm": round(max(us), 4),
        "min_v_mm": round(min(vs), 4),
        "max_v_mm": round(max(vs), 4),
        "width_mm": round(max(us) - min(us), 4),
        "height_mm": round(max(vs) - min(vs), 4),
    }


def _estimate_duration_s(segments: list[ProcessSegment]) -> float:
    total = 0.0
    for seg in segments:
        spd = max(seg.speed_mm_s, 1e-6)
        for i in range(len(seg.points) - 1):
            a, b = seg.points[i], seg.points[i + 1]
            total += math.sqrt(
                (b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2
            ) / spd
    return total
