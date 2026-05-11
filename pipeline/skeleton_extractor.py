"""骨架提取：二值图 → skeletonize → 8 邻域图 → Path2D[]"""

import numpy as np
from skimage.morphology import skeletonize
from core.types import Point2D, Path2D


def _neighbors(y: int, x: int, skeleton: np.ndarray) -> list[tuple[int, int]]:
    """返回 8 邻域中前景像素坐标列表。"""
    pts = []
    h, w = skeleton.shape
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and skeleton[ny, nx]:
                pts.append((ny, nx))
    return pts


def _count_neighbors(y: int, x: int, skeleton: np.ndarray) -> int:
    return len(_neighbors(y, x, skeleton))


def _trace_path(start: tuple[int, int], skeleton: np.ndarray,
                visited: np.ndarray) -> list[Point2D]:
    """从 start 像素开始沿骨架追踪，直到遇到端点或交叉点。"""
    pts = []
    y, x = start
    while True:
        visited[y, x] = True
        pts.append(Point2D(x=float(x), y=float(y)))

        nbrs = [(ny, nx) for ny, nx in _neighbors(y, x, skeleton)
                if not visited[ny, nx]]

        if len(nbrs) == 0:
            break  # 端点
        if len(nbrs) > 1:
            break  # 交叉点

        y, x = nbrs[0]

    return pts


def extract_paths(bitmap: np.ndarray, char: str = "") -> list[Path2D]:
    """从二值图提取骨架路径。

    Args:
        bitmap: 二值 numpy array (0=背景, 255=前景)
        char: 来源字符（用于生成 path id）

    Returns:
        Path2D 列表，坐标单位为像素
    """
    if bitmap.size == 0 or np.max(bitmap) == 0:
        return []

    binary = bitmap > 0
    skeleton = skeletonize(binary)
    h, w = skeleton.shape
    visited = np.zeros((h, w), dtype=bool)

    paths = []
    path_idx = 0

    # 遍历所有骨架像素
    for y in range(h):
        for x in range(w):
            if not skeleton[y, x] or visited[y, x]:
                continue

            n = _count_neighbors(y, x, skeleton)
            if n == 0:
                visited[y, x] = True
                continue
            elif n >= 2:
                # 交叉点：作为路径分隔，稍后处理
                continue
            # 端点 (n==1) 或孤立段 → 开始追踪
            pts = _trace_path((y, x), skeleton, visited)
            if len(pts) >= 2:
                glyph = char if char else ""
                paths.append(Path2D(
                    id=f"{glyph}_p{path_idx}",
                    points=pts,
                    closed=False,
                    role="stroke",
                    source="text",
                    glyph=glyph,
                ))
                path_idx += 1

    # 处理闭环：剩余的未访问像素属于闭环
    for y in range(h):
        for x in range(w):
            if not skeleton[y, x] or visited[y, x]:
                continue
            pts = _trace_loop((y, x), skeleton, visited)
            if len(pts) >= 3:
                glyph = char if char else ""
                # 闭合路径：把起点追加到末尾
                pts.append(pts[0])
                paths.append(Path2D(
                    id=f"{glyph}_p{path_idx}",
                    points=pts,
                    closed=True,
                    role="stroke",
                    source="text",
                    glyph=glyph,
                ))
                path_idx += 1

    return paths


def _trace_loop(start: tuple[int, int], skeleton: np.ndarray,
                visited: np.ndarray) -> list[Point2D]:
    """追踪闭环路径。"""
    pts = []
    y, x = start
    while True:
        visited[y, x] = True
        pts.append(Point2D(x=float(x), y=float(y)))

        # 优先选未访问的邻居
        nbrs = [(ny, nx) for ny, nx in _neighbors(y, x, skeleton)
                if not visited[ny, nx]]
        if not nbrs:
            # 闭环：检查是否回到了 start 的邻居
            nbrs_all = _neighbors(y, x, skeleton)
            if start in nbrs_all and len(pts) >= 3:
                break
            # 无法继续
            break

        # 选择最"直"的方向（简单做法：取第一个）
        y, x = nbrs[0]

    return pts
