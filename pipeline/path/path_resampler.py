"""Phase 4.1 路径重采样 — 等距重采样、RDP 简化、步长检查、编排入口

纯像素空间操作。所有阈值已为 px 单位。
mm→px 转换集中在 clean_and_resample_strokes() 中完成。
"""

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path._shared import (
    dist, dist_sq, calc_path_length_px, detect_closed, perpendicular_distance,
)
from pipeline.path.path_cleaner import (
    remove_duplicate_points, remove_short_strokes, normalize_direction,
)


# ---- RDP 简化 ----

def simplify_rdp(
    pts: list[PixelPoint],
    epsilon: float,
    closed: bool = False,
) -> list[PixelPoint]:
    """Ramer-Douglas-Peucker 路径简化。

    Args:
        pts: 输入点序列
        epsilon: 简化容差 (px)
        closed: 是否闭合。闭合时保证首尾重合。

    Returns:
        简化后的点序列。保证首尾端点保留。
    """
    if len(pts) <= 2:
        return list(pts)

    if closed:
        return _rdp_closed(pts, epsilon)
    else:
        return _rdp_open(pts, 0, len(pts) - 1, epsilon)


def _rdp_open(
    pts: list[PixelPoint],
    start: int,
    end: int,
    epsilon: float,
) -> list[PixelPoint]:
    """标准 RDP 开放路径递归。"""
    dmax = 0.0
    index = start
    for i in range(start + 1, end):
        d = perpendicular_distance(pts[i], pts[start], pts[end])
        if d > dmax:
            dmax = d
            index = i

    if dmax > epsilon:
        left = _rdp_open(pts, start, index, epsilon)
        right = _rdp_open(pts, index, end, epsilon)
        return left[:-1] + right
    else:
        return [pts[start], pts[end]]


def _rdp_closed(pts: list[PixelPoint], epsilon: float) -> list[PixelPoint]:
    """RDP 闭合路径：找到距离首尾连线最远的点拆分递归。"""
    if len(pts) <= 3:
        return list(pts)

    dmax = 0.0
    index = 0
    for i in range(1, len(pts) - 1):
        d = perpendicular_distance(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax = d
            index = i

    if dmax > epsilon:
        left = _rdp_open(pts, 0, index, epsilon)
        right = _rdp_open(pts, index, len(pts) - 1, epsilon)
        result = left[:-1] + right
    else:
        result = [pts[0], pts[-1]]

    # Ensure closure
    if len(result) >= 2:
        if dist_sq(result[0], result[-1]) >= epsilon * epsilon * 0.25:
            result.append(result[0])

    return result


# ---- 等距重采样 ----

def resample_uniform(
    pts: list[PixelPoint],
    spacing: float,
    closed: bool = False,
) -> list[PixelPoint]:
    """沿路径等距重采样，线性插值。

    Args:
        pts: 输入点序列
        spacing: 目标采样间距 (px)
        closed: 是否闭合。闭合时末点→首点的闭合段参与采样。

    Returns:
        重采样后的点序列。开放路径保留首尾端点，闭合路径首点即末点。
    """
    if len(pts) < 2:
        return list(pts)

    n = len(pts)

    # 累积段长
    seg_lens: list[float] = []
    for i in range(n - 1):
        seg_lens.append(dist(pts[i], pts[i + 1]))

    if closed:
        seg_lens.append(dist(pts[-1], pts[0]))

    total = sum(seg_lens)
    if total < spacing:
        return list(pts)

    out = [pts[0]]
    target = spacing
    seg_idx = 0
    seg_start = 0.0
    limit = total if closed else total - 1e-9

    while target < limit:
        while seg_idx < len(seg_lens) and seg_start + seg_lens[seg_idx] < target:
            seg_start += seg_lens[seg_idx]
            seg_idx += 1

        if seg_idx >= len(seg_lens):
            break

        if seg_lens[seg_idx] < 1e-9:
            target += spacing
            continue

        t = (target - seg_start) / seg_lens[seg_idx]

        if closed and seg_idx == len(seg_lens) - 1:
            a, b = pts[-1], pts[0]
        else:
            a, b = pts[seg_idx], pts[seg_idx + 1]

        out.append(PixelPoint(
            x=a.x + t * (b.x - a.x),
            y=a.y + t * (b.y - a.y),
        ))
        target += spacing

    if not closed:
        last = pts[-1]
        if len(out) == 0 or out[-1].x != last.x or out[-1].y != last.y:
            out.append(last)

    return out


# ---- 步长检查 ----

def check_max_step(
    strokes: list[Stroke],
    max_step: float,
) -> list[dict]:
    """检查每条 stroke 中是否有超出最大步长的段。

    非破坏性，不修改 stroke。

    Args:
        strokes: stroke 列表
        max_step: 最大允许步长 (px)

    Returns:
        list[dict]: 每个超限段一条记录
          {stroke_id, segment_index, step_length_px, max_allowed_px, severity}
    """
    warnings: list[dict] = []
    for s in strokes:
        pts = s.points_px
        for i in range(len(pts) - 1):
            step = dist(pts[i], pts[i + 1])
            if step > max_step:
                severity = "error" if step > max_step * 2.0 else "warning"
                warnings.append({
                    "stroke_id": s.id,
                    "segment_index": i,
                    "step_length_px": round(step, 3),
                    "max_allowed_px": round(max_step, 3),
                    "severity": severity,
                })
    return warnings


# ---- 编排入口 ----

def clean_and_resample_strokes(
    strokes: list[Stroke],
    px_per_mm: float,
    config: PathConfig,
    char_height_px: float = 0.0,
) -> tuple[list[Stroke], dict]:
    """Phase 4.1 编排入口：mm→px 转换 + 清洗 + 重采样 + 步长检查。

    调用顺序：
      1. mm→px 集中转换
      2. for each stroke: 连续去重 → 闭合重检测 → RDP → 均匀重采样 → 二次去重
      3. 短路径过滤（含 dot_strategy）
      4. 方向统一
      5. 步长检查（非破坏性）

    Args:
        strokes: 输入 stroke 列表 (contour 或 skeleton 输出)
        px_per_mm: 像素/mm 换算比。由调用方根据渲染尺寸计算。
        config: PathConfig（所有 mm 阈值在此转换为 px）
        char_height_px: 字符渲染高度 (px)，用于 dot 横线长度估算。
            0 表示自动从 strokes bbox 估算。

    Returns:
        (cleaned_strokes, stats)
        stats 含: input_count, output_count, dropped_count, dot_count,
                  max_step_warnings, px_per_mm, spacing_px, epsilon_px 等
    """
    if px_per_mm <= 0:
        px_per_mm = 10.0  # safe default

    # ---- 1. mm → px 集中转换 ----
    min_len_px = config.min_path_length_mm * px_per_mm
    spacing_px = config.sample_spacing_mm * px_per_mm
    epsilon_px = config.simplify_epsilon_mm * px_per_mm

    if char_height_px <= 0 and strokes:
        all_ys: list[float] = []
        for s in strokes:
            for p in s.points_px:
                all_ys.append(p.y)
        if all_ys:
            char_height_px = max(all_ys) - min(all_ys)

    input_count = len(strokes)
    dot_count = 0
    dropped_count = 0

    # ---- 2. per-stroke pipeline ----
    result: list[Stroke] = []
    for s in strokes:
        pts = s.points_px
        is_hershey = (s.metadata or {}).get("extract_algorithm") == "hershey"

        # 2a. 连续去重（Zhang-Suen 锯齿第一步清理）
        pts = remove_duplicate_points(pts, eps=0.5)
        if len(pts) < 2:
            dropped_count += 1
            continue

        # Hershey 已是稀疏矢量折线，勿按骨架图做 RDP/密采样（否则预览与样张严重偏离）
        if is_hershey:
            s.points_px = pts
            result.append(s)
            continue

        # 2b. 闭合状态重检测
        if not s.closed:
            s.closed = detect_closed(pts, threshold=max(spacing_px * 2.0, 2.0))

        # 2c. RDP 简化（在重采样之前，减少点数）
        pts = simplify_rdp(pts, epsilon_px, closed=s.closed)
        if len(pts) < 2:
            dropped_count += 1
            continue

        # 2d. 等距重采样
        pts = resample_uniform(pts, spacing_px, closed=s.closed)
        if len(pts) < 2:
            dropped_count += 1
            continue

        # 2e. 二次去重（清理重采样可能产生的极小步长）
        pts = remove_duplicate_points(pts, eps=spacing_px * 0.1)

        s.points_px = pts
        result.append(s)

    # ---- 3. 短路径过滤 ----
    result = remove_short_strokes(
        result, min_len_px,
        dot_strategy=config.dot_strategy,
        char_height_px=char_height_px,
    )
    dot_count = sum(
        1 for s in result
        if s.metadata.get("dot_original_id") is not None
    )

    # ---- 4. 方向统一 ----
    result = normalize_direction(result)

    # ---- 5. 步长检查（非破坏性）----
    max_step_px = spacing_px * 3.0
    step_warnings = check_max_step(result, max_step_px)

    stats = {
        "phase": "4.1",
        "input_count": input_count,
        "output_count": len(result),
        "dropped_count": dropped_count,
        "dot_count": dot_count,
        "px_per_mm": px_per_mm,
        "spacing_px": round(spacing_px, 4),
        "epsilon_px": round(epsilon_px, 4),
        "min_len_px": round(min_len_px, 4),
        "max_step_px": round(max_step_px, 4),
        "max_step_warnings": len(step_warnings),
        "max_step_details": step_warnings,
        "used_default_px_per_mm": px_per_mm == 10.0 and len(strokes) > 0,
    }

    return result, stats
