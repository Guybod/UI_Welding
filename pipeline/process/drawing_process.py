"""绘图工艺段生成 — 笔 Z 语义（无 arcOn / 无焊接 lead/overlap）。"""

from __future__ import annotations

import uuid

from core.types import ImageDrawingConfig, ProcessSegment, RobotPoint, Stroke
from pipeline.process.weld_process import _resample_robot_points, _with_z


class DrawingProcessPlanner:
    """Stroke → travel / draw / retreat ProcessSegment。"""

    @staticmethod
    def plan(
        strokes: list[Stroke],
        cfg: ImageDrawingConfig,
    ) -> tuple[list[ProcessSegment], dict]:
        warnings: list[str] = []
        segments: list[ProcessSegment] = []
        counts = {"travel": 0, "draw": 0, "retreat": 0}
        total_points = 0

        for stroke in strokes:
            robot_pts = _get_robot_points(stroke)
            if len(robot_pts) < 2:
                warnings.append(f"stroke {stroke.id[:8]}: <2 points, skipped")
                continue

            draw_pts = _resample_robot_points(
                robot_pts, cfg.point_spacing_mm, closed=stroke.closed,
            )
            if len(draw_pts) < 2:
                warnings.append(f"stroke {stroke.id[:8]}: resample <2 points, skipped")
                continue

            start = draw_pts[0]
            end = draw_pts[-1]

            segments.append(_make_draw_segment(
                "travel", stroke.id, _with_z([start, start], cfg.z_safe_mm),
                cfg.travel_speed_mm_s,
            ))
            segments.append(_make_draw_segment(
                "draw", stroke.id, _with_z(list(draw_pts), cfg.z_draw_mm),
                cfg.draw_speed_mm_s,
            ))
            segments.append(_make_draw_segment(
                "retreat", stroke.id, _with_z([end, end], cfg.z_safe_mm),
                cfg.travel_speed_mm_s,
            ))

            counts["travel"] += 1
            counts["draw"] += 1
            counts["retreat"] += 1
            total_points += 2 + len(draw_pts) + 2

        stats = {
            "phase": "image_draw",
            "input_stroke_count": len(strokes),
            "generated_segment_count": len(segments),
            "travel_count": counts["travel"],
            "draw_count": counts["draw"],
            "retreat_count": counts["retreat"],
            "total_robot_points": total_points,
            "z_draw_mm": cfg.z_draw_mm,
            "z_safe_mm": cfg.z_safe_mm,
            "warnings": warnings,
        }
        return segments, stats


def _get_robot_points(stroke: Stroke) -> list[RobotPoint]:
    rp = stroke.metadata.get("robot_points")
    if not rp:
        raise ValueError(
            f"Stroke {stroke.id} missing metadata['robot_points']; map to workplane first"
        )
    return list(rp)


def _make_draw_segment(
    seg_type: str,
    stroke_id: str,
    points: list[RobotPoint],
    speed_mm_s: float,
) -> ProcessSegment:
    return ProcessSegment(
        id=str(uuid.uuid4())[:8],
        type=seg_type,
        points=points,
        speed_mm_s=speed_mm_s,
        arc_enabled=False,
        normal_offset_mm=0.0,
        stroke_id=stroke_id,
        metadata={"drawing": True},
    )
