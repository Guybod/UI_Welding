"""骨架 stroke 后处理 — 去重、按字去毛刺、打开伪闭环（仅 skeleton 模式）。"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import replace

from core.types import Stroke


def _stroke_signature(stroke: Stroke) -> tuple:
    pts = stroke.points_px
    if len(pts) < 2:
        return (stroke.closed, len(pts))
    return (
        stroke.closed,
        len(pts),
        round(pts[0].x, 1),
        round(pts[0].y, 1),
        round(pts[-1].x, 1),
        round(pts[-1].y, 1),
    )


def dedupe_skeleton_strokes(strokes: list[Stroke]) -> tuple[list[Stroke], int]:
    """移除点列完全重复的 stroke（骨架图常出现双边）。"""
    seen: set[tuple] = set()
    out: list[Stroke] = []
    removed = 0
    for s in strokes:
        key = _stroke_signature(s)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(s)
    return out, removed


def filter_per_char_spurs(
    strokes: list[Stroke],
    *,
    min_ratio_of_longest: float = 0.18,
    min_points: int = 8,
) -> tuple[list[Stroke], int]:
    """按字保留足够长的 open stroke，去掉短枝。

    max_len 仅基于 open stroke 长度——闭合 stroke 通常绕字一圈，长度远大于
    单笔画，会让阈值过高误删正常短笔画（实测 Arial '4' 闭合 polyline pts=648，
    会让 0.24×648=156 的阈值误删底部 pts=92/150 的正常短笔）。
    """
    by_char: dict[int, list[Stroke]] = defaultdict(list)
    for s in strokes:
        try:
            ci = int(s.metadata.get("weld_char_index", 0))
        except (TypeError, ValueError):
            ci = 0
        by_char[ci].append(s)

    out: list[Stroke] = []
    dropped = 0
    for _ci, group in sorted(by_char.items()):
        if not group:
            continue
        open_lengths = [len(s.points_px) for s in group if not s.closed]
        max_len = max(open_lengths) if open_lengths else 0
        thresh = max(min_points, int(max_len * min_ratio_of_longest))
        for s in group:
            if len(s.points_px) < thresh and not s.closed:
                dropped += 1
                continue
            out.append(s)
    return out, dropped


def _ring_metrics(pts) -> tuple[float, float, list[tuple[float, int, int]]]:
    """返回 (周长, 面积, 边列表) — 边按起点索引升序，含 (length, i, j=(i+1) mod m)。"""
    n = len(pts)
    if n >= 2 and abs(pts[-1].x - pts[0].x) < 1e-6 and abs(pts[-1].y - pts[0].y) < 1e-6:
        ring = list(pts[:-1])
    else:
        ring = list(pts)
    m = len(ring)
    if m < 3:
        return 0.0, 0.0, []
    edges: list[tuple[float, int, int]] = []
    peri = 0.0
    area2 = 0.0
    for i in range(m):
        j = (i + 1) % m
        dx = ring[j].x - ring[i].x
        dy = ring[j].y - ring[i].y
        d = math.hypot(dx, dy)
        peri += d
        edges.append((d, i, j))
        area2 += ring[i].x * ring[j].y - ring[j].x * ring[i].y
    return peri, abs(area2) * 0.5, edges


def open_phantom_loops(
    strokes: list[Stroke],
    *,
    char_height_px: float,
    circularity_max: float = 0.72,
    perimeter_ratio_max: float = 2.0,
    area_ratio_max: float = 0.20,
    min_ring_pts: int = 4,
) -> tuple[list[Stroke], int]:
    """打开骨架化产生的"伪闭环"。

    场景：Arial 数字 '4' 顶部被字体外轮廓封闭，骨架化得到一个三角形闭环；
    用户期望开口 '^' 形（与手写/单线字一致）。

    三重判据（全部满足才打开）：
      - circularity = 4πA/P² < circularity_max
        三角形 ≈ 0.6；椭圆/圆 ≈ 0.78~0.95；
      - perimeter / char_height_px < perimeter_ratio_max
      - area / char_height_px² < area_ratio_max

    保护（实测 binary.shape[0]=143 / 286 时）：
      - '0' circ≈0.81 → KEEP
      - '6' circ≈0.88 → KEEP
      - '8' circ≈0.43 但 area/h²=0.26 (>0.20) → KEEP
      - '9' circ≈0.89 → KEEP
      - 'a'/'g'/'q' circ≈0.78~0.88 → KEEP
      - '4' circ≈0.60, area/h²=0.15, peri/h=1.77 → OPEN

    打开方式：仅把 closed 置为 False，保留原 polyline 顺序。SkeletonExtractor 输出
    的 closed=True polyline 首尾点不重合（首尾间是隐含的"封闭边"），改为 False
    后渲染/规划层不再补这条边，伪三角自动开口。若首尾点恰好重合（图论闭合），
    则去除末尾的重复点，避免预览渲染时仍画出一个零长度的尾迹。
    """
    if char_height_px <= 0:
        return list(strokes), 0
    h = float(char_height_px)
    out: list[Stroke] = []
    opened = 0
    for s in strokes:
        if not s.closed or len(s.points_px) < min_ring_pts:
            out.append(s)
            continue
        peri, area, edges = _ring_metrics(s.points_px)
        if not edges or peri <= 0 or area <= 0:
            out.append(s)
            continue
        circularity = 4.0 * math.pi * area / (peri * peri)
        peri_ratio = peri / h
        area_ratio = area / (h * h)
        if (circularity >= circularity_max
                or peri_ratio >= perimeter_ratio_max
                or area_ratio >= area_ratio_max):
            out.append(s)
            continue

        pts = list(s.points_px)
        if (
            len(pts) >= 2
            and abs(pts[-1].x - pts[0].x) < 1e-6
            and abs(pts[-1].y - pts[0].y) < 1e-6
        ):
            pts = pts[:-1]

        new_meta = dict(s.metadata)
        new_meta["skeleton_loop_opened"] = True
        new_meta["skeleton_loop_perimeter_px"] = round(peri, 2)
        new_meta["skeleton_loop_area_px2"] = round(area, 2)
        new_meta["skeleton_loop_circularity"] = round(circularity, 3)
        out.append(replace(s, points_px=pts, closed=False, metadata=new_meta))
        opened += 1
    return out, opened


def cleanup_skeleton_strokes(
    strokes: list[Stroke],
    *,
    char_height_px: float = 0.0,
) -> tuple[list[Stroke], dict]:
    """dedupe + per-char spur filter + open phantom loops（伪闭环打开）。"""
    s1, deduped = dedupe_skeleton_strokes(strokes)
    s2, spurs = filter_per_char_spurs(s1)
    if char_height_px > 0:
        s3, opened = open_phantom_loops(s2, char_height_px=char_height_px)
    else:
        s3, opened = s2, 0
    return s3, {
        "skeleton_strokes_deduped": deduped,
        "skeleton_strokes_spur_dropped": spurs,
        "skeleton_phantom_loops_opened": opened,
        "skeleton_strokes_after_cleanup": len(s3),
    }
