"""Phase 4 路径整形 — 模块内共享工具（非公共 API）

所有函数操作 PixelPoint，不依赖 mm 空间、不引入 RobotPoint/ProcessSegment。
"""

import math

from core.types import PixelPoint


def dist_sq(a: PixelPoint, b: PixelPoint) -> float:
    """两点欧氏距离平方。"""
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy


def dist(a: PixelPoint, b: PixelPoint) -> float:
    """两点欧氏距离。"""
    return math.sqrt(dist_sq(a, b))


def calc_path_length_px(pts: list[PixelPoint]) -> float:
    """计算路径总长（像素）。"""
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for i in range(len(pts) - 1):
        total += dist(pts[i], pts[i + 1])
    return total


def stroke_bbox(pts: list[PixelPoint]) -> tuple[float, float, float, float]:
    """返回 (min_x, min_y, max_x, max_y)。空列表返回 (0, 0, 0, 0)。"""
    if not pts:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def detect_closed(pts: list[PixelPoint], threshold: float = 2.0) -> bool:
    """判定点列表首尾是否闭合（距离 < threshold px）。"""
    if len(pts) < 3:
        return False
    return dist_sq(pts[0], pts[-1]) < (threshold * threshold)


def perpendicular_distance(p: PixelPoint, a: PixelPoint, b: PixelPoint) -> float:
    """点到线段 AB 的垂直距离（px）。"""
    dx = b.x - a.x
    dy = b.y - a.y
    if dx == 0.0 and dy == 0.0:
        return dist(p, a)
    return abs(dx * (a.y - p.y) - dy * (a.x - p.x)) / math.sqrt(dx * dx + dy * dy)


def turn_angle_deg(prev: PixelPoint, curr: PixelPoint, next_: PixelPoint) -> float:
    """三点转向角 (0=直线, 180=折返)。

    使用 atan2(cross, dot) 计算方向变化量的绝对值。
    返回 0~180 度。
    """
    dx1, dy1 = curr.x - prev.x, curr.y - prev.y
    dx2, dy2 = next_.x - curr.x, next_.y - curr.y
    d1 = math.hypot(dx1, dy1)
    d2 = math.hypot(dx2, dy2)
    if d1 < 1e-9 or d2 < 1e-9:
        return 0.0
    cross = dx1 * dy2 - dy1 * dx2
    dot = dx1 * dx2 + dy1 * dy2
    return abs(math.degrees(math.atan2(cross, dot)))
