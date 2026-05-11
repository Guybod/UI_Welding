"""路径清洗与分类：去重、重采样、过滤、小点处理"""

import math
from core.types import Point2D, Path2D


def _dist(a: Point2D, b: Point2D) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def process_paths(
    paths: list[Path2D],
    sample_spacing_mm: float = 0.5,
    min_path_length_mm: float = 2.0,
    dot_strategy: str = "short_line",
    char_height_mm: float = 20.0,
) -> list[Path2D]:
    """清洗并分类路径。

    Returns:
        处理后的 Path2D 列表
    """
    result = []

    for path in paths:
        # 1. 去重
        path.points = _deduplicate(path.points)

        # 2. 计算路径长度
        total_len = _path_length(path.points)

        # 3. 小点处理
        if total_len < min_path_length_mm and path.closed is False:
            if dot_strategy == "filter":
                continue
            elif dot_strategy == "short_line":
                path = _make_short_line(path, char_height_mm)
            elif dot_strategy == "keep":
                pass

        # 4. 重采样
        path.points = _resample(path.points, sample_spacing_mm)

        # 5. 再次去重（重采样可能引入）
        path.points = _deduplicate(path.points)

        if len(path.points) >= 2:
            result.append(path)

    # 6. 识别闭合路径
    for path in result:
        if not path.closed and len(path.points) >= 3:
            d = _dist(path.points[0], path.points[-1])
            if d < sample_spacing_mm * 3:
                path.closed = True

    return result


def _deduplicate(pts: list[Point2D]) -> list[Point2D]:
    if len(pts) <= 1:
        return pts
    out = [pts[0]]
    for p in pts[1:]:
        if _dist(out[-1], p) > 0.001:
            out.append(p)
    return out


def _path_length(pts: list[Point2D]) -> float:
    if len(pts) < 2:
        return 0.0
    return sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def _resample(pts: list[Point2D], spacing: float) -> list[Point2D]:
    """均匀重采样，点距 ≈ spacing mm。"""
    if len(pts) < 2:
        return pts[:]

    # 计算累积弧长
    seg_lens = [_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(seg_lens)
    if total < spacing:
        return pts[:]

    out = [pts[0]]
    target = spacing
    seg_idx = 0
    seg_start = 0.0

    while target < total:
        # 前进到目标弧长所在的段
        while seg_idx < len(seg_lens) and seg_start + seg_lens[seg_idx] < target:
            seg_start += seg_lens[seg_idx]
            seg_idx += 1

        if seg_idx >= len(seg_lens):
            break

        t = (target - seg_start) / seg_lens[seg_idx]
        a, b = pts[seg_idx], pts[seg_idx + 1]
        out.append(Point2D(
            x=a.x + t * (b.x - a.x),
            y=a.y + t * (b.y - a.y),
        ))
        target += spacing

    out.append(pts[-1])
    return out


def _make_short_line(path: Path2D, char_height_mm: float) -> Path2D:
    """将小点替换为短横线。"""
    line_len = max(2.0, 0.12 * char_height_mm)
    cx = path.points[0].x
    cy = path.points[0].y

    return Path2D(
        id=path.id,
        points=[
            Point2D(x=cx - line_len / 2, y=cy),
            Point2D(x=cx + line_len / 2, y=cy),
        ],
        closed=False,
        role="dot",
        source=path.source,
        glyph=path.glyph,
        metadata=path.metadata,
    )
