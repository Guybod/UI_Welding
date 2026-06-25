"""Phase 4.1/4.2 路径清洗 — 去重、短线过滤、方向统一、噪声过滤、小圆点生成

纯像素空间操作。所有阈值已为 px 单位（由编排函数完成 mm→px 转换）。
"""

import math
import uuid

from core.types import PixelPoint, Stroke
from pipeline.path._shared import dist_sq, calc_path_length_px


def remove_duplicate_points(
    pts: list[PixelPoint],
    eps: float = 0.5,
) -> list[PixelPoint]:
    """连续去重：移除与前一保留点距离 < eps 的点。

    只做连续去重，不做全局去重，避免破坏自交路径拓扑。
    保证至少返回首尾两点（如果输入 >=2 点且全部被去重）。

    Args:
        pts: 输入点序列
        eps: 距离阈值 (px)，默认 0.5px

    Returns:
        去重后的点列表
    """
    if len(pts) <= 1:
        return list(pts)

    sq_eps = eps * eps
    out = [pts[0]]
    for p in pts[1:]:
        dx = p.x - out[-1].x
        dy = p.y - out[-1].y
        if dx * dx + dy * dy >= sq_eps:
            out.append(p)

    if len(out) == 1 and len(pts) >= 2:
        out.append(pts[-1])

    return out


def remove_short_strokes(
    strokes: list[Stroke],
    min_len_px: float,
    dot_strategy: str = "short_line",
    char_height_px: float = 0.0,
) -> list[Stroke]:
    """过滤过短 stroke。

    Args:
        strokes: 输入 stroke 列表
        min_len_px: 最小路径长度 (px)
        dot_strategy: PathConfig.dot_strategy 原始值
            - "filter": 直接删除短路径
            - "keep": 保留短路径原样
            - "short_line": 将短路径替换为一条短横线
            - "small_circle": TODO Phase 4.2（暂降级为 "short_line"）
        char_height_px: 字符渲染高度 (px)，用于 "short_line" 的横线长度估算

    Returns:
        过滤后的 stroke 列表
    """
    result: list[Stroke] = []

    for s in strokes:
        path_len = calc_path_length_px(s.points_px)
        if path_len >= min_len_px or dot_strategy == "keep":
            result.append(s)
            continue

        # path_len < min_len_px: apply strategy
        if dot_strategy == "filter":
            continue  # drop

        if dot_strategy == "small_circle":
            dot_stroke = _generate_small_circle_stroke(s, char_height_px, path_len)
            result.append(dot_stroke)
            continue

        # "short_line" (default)
        dot_stroke = _generate_short_line_stroke(s, char_height_px, path_len)
        result.append(dot_stroke)

    return result


def normalize_direction(strokes: list[Stroke]) -> list[Stroke]:
    """统一 stroke 方向。

    Open skeleton stroke: 左→右（主方向），上→下（次方向）。
    Closed stroke: 不动，保留 ContourExtractor 的 CCW(外)/CW(内) 约定。
    Contour open stroke: 不动。

    Args:
        strokes: 输入 stroke 列表

    Returns:
        方向统一后的 stroke 列表（原地修改）
    """
    for s in strokes:
        if s.closed:
            continue
        if len(s.points_px) < 2:
            continue

        dx = s.points_px[-1].x - s.points_px[0].x
        dy = s.points_px[-1].y - s.points_px[0].y

        # 主方向按绝对值更大的轴判断
        if abs(dx) >= abs(dy):
            if dx < 0:
                s.points_px.reverse()
        else:
            if dy < 0:
                s.points_px.reverse()

    return strokes


def filter_noise_strokes(
    strokes: list[Stroke],
    min_point_count: int = 2,
    min_length_px: float = 0.0,
) -> list[Stroke]:
    """噪声过滤：移除点数过少或长度过短的 stroke。

    与 remove_short_strokes 的区别：
    - 本函数是纯过滤器，不生成 dot 替代 stroke
    - 用于骨架化产生的极短毛刺清理

    Args:
        strokes: 输入 stroke 列表
        min_point_count: 最小点数阈值
        min_length_px: 最小长度阈值 (px)

    Returns:
        过滤后的 stroke 列表
    """
    return [
        s for s in strokes
        if len(s.points_px) >= min_point_count
        and (min_length_px <= 0 or calc_path_length_px(s.points_px) >= min_length_px)
    ]


def _generate_short_line_stroke(
    original: Stroke,
    char_height_px: float,
    original_len_px: float,
) -> Stroke:
    """为短 dot stroke 生成一条短横线替代 stroke。

    横线长度 = char_height_px * 0.12，最小 3px。
    """
    line_len = char_height_px * 0.12 if char_height_px > 0 else 3.0
    cx = sum(p.x for p in original.points_px) / max(len(original.points_px), 1)
    cy = sum(p.y for p in original.points_px) / max(len(original.points_px), 1)
    half = line_len * 0.5
    return Stroke(
        id=str(uuid.uuid4())[:8],
        source_type=original.source_type,
        points_px=[
            PixelPoint(x=cx - half, y=cy),
            PixelPoint(x=cx + half, y=cy),
        ],
        closed=False,
        is_hole=original.is_hole,
        glyph_id=original.glyph_id,
        group_id=original.group_id,
        metadata={
            **original.metadata,
            "dot_original_id": original.id,
            "dot_original_len_px": original_len_px,
            "dot_strategy": "short_line",
        },
    )


def _generate_small_circle_stroke(
    original: Stroke,
    char_height_px: float,
    original_len_px: float,
) -> Stroke:
    """为短 dot stroke 生成小圆点替代 stroke（8 点近似圆，closed=True）。

    半径 = clamp(char_height_px * 0.04, 1.5, 10.0)
    """
    radius = max(1.5, min(10.0, char_height_px * 0.04)) if char_height_px > 0 else 3.0
    cx = sum(p.x for p in original.points_px) / max(len(original.points_px), 1)
    cy = sum(p.y for p in original.points_px) / max(len(original.points_px), 1)

    n_circle = 8
    circle_pts = []
    for i in range(n_circle):
        angle = 2.0 * math.pi * i / n_circle
        circle_pts.append(PixelPoint(
            x=cx + radius * math.cos(angle),
            y=cy + radius * math.sin(angle),
        ))

    return Stroke(
        id=str(uuid.uuid4())[:8],
        source_type=original.source_type,
        points_px=circle_pts,
        closed=True,
        is_hole=original.is_hole,
        glyph_id=original.glyph_id,
        group_id=original.group_id,
        metadata={
            **original.metadata,
            "dot_original_id": original.id,
            "dot_original_len_px": original_len_px,
            "dot_radius_px": radius,
            "dot_strategy": "small_circle",
        },
    )
