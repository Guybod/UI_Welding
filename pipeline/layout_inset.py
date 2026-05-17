"""工作平面排版起点 inset — 仅左上边距（字从左→右、从上→下，无右/下边距）。"""

from __future__ import annotations

from core.types import PixelPoint, Stroke


def effective_writable_size_mm(
    width_mm: float,
    height_mm: float,
    margin_left_mm: float,
    margin_top_mm: float,
) -> tuple[float, float]:
    """可写区域：示教宽/高各减去左上边距（右侧与下侧可贴到示教边界）。"""
    ml = max(0.0, float(margin_left_mm))
    mt = max(0.0, float(margin_top_mm))
    return max(0.0, width_mm - ml), max(0.0, height_mm - mt)


def translate_strokes_px(
    strokes: list[Stroke],
    dx: float,
    dy: float,
) -> list[Stroke]:
    if not strokes or (dx == 0.0 and dy == 0.0):
        return strokes
    for stroke in strokes:
        stroke.points_px = [
            PixelPoint(x=p.x + dx, y=p.y + dy) for p in stroke.points_px
        ]
    return strokes


def apply_layout_origin_offset(
    strokes: list[Stroke],
    margin_left_mm: float,
    margin_top_mm: float,
    px_per_mm: float,
) -> list[Stroke]:
    """将排版原点 (0,0) 平移到距示教 LT 为 (margin_left, margin_top) 的位置。"""
    if not strokes or px_per_mm <= 0.0:
        return strokes
    dx = max(0.0, margin_left_mm) * px_per_mm
    dy = max(0.0, margin_top_mm) * px_per_mm
    return translate_strokes_px(strokes, dx, dy)
