"""Phase 4.2b 路径精炼 — 拐角保护 + 自适应简化 + 保形守卫

AdaptivePathRefiner: 拐角检测 → 直/曲分类 → 差异化简化 → 压缩率守卫。
纯像素空间操作。mm→px 转换集中在 refine_strokes() 编排入口完成。
"""

import math

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path._shared import (
    dist, dist_sq, calc_path_length_px, perpendicular_distance, turn_angle_deg,
)
from pipeline.path.path_resampler import simplify_rdp, resample_uniform


# 拐角检测最小邻域长度 (px)，防止锯齿 zigzag 被误判为拐角
_MIN_SEG_LEN_FOR_CORNER_PX = 3.0

# 闭合轮廓安全下限点数：低于此值强制保留更多点
_MIN_CLOSED_POINTS = 48

# 开放路径安全下限
_MIN_OPEN_POINTS = 4

# 默认压缩保留比例
_DEFAULT_RETENTION_CONTOUR = 0.70   # contour 至少保留 70% 点数
_DEFAULT_RETENTION_SKELETON = 0.60  # skeleton 至少保留 60% 点数


# ---- 拐角检测 ----

def detect_corners(
    pts: list[PixelPoint],
    angle_threshold_deg: float,
    closed: bool = False,
) -> list[int]:
    """检测拐角点索引。

    Args:
        pts: 均匀采样的点序列
        angle_threshold_deg: 转向角阈值 (度)。>= 此值即为拐角。
        closed: 是否闭合路径。闭合时使用环形索引，首尾地位相等。

    Returns:
        拐角点索引列表（已排序）。
        开放路径首尾点必定为 corner。
    """
    n = len(pts)
    if n < 3:
        return list(range(n))

    corners: list[int] = []
    corners_set: set[int] = set()

    # 开放路径：首尾点强制为 corner
    if not closed:
        corners_set.add(0)
        corners_set.add(n - 1)

    # 中间点检测
    for i in range(n):
        if closed and i in (0, n - 1):
            # 闭合路径首尾等同，只检测中间点 + 索引 0 的环形邻域
            pass

        prev_idx = (i - 1) % n
        next_idx = (i + 1) % n
        prev = pts[prev_idx]
        curr = pts[i]
        next_ = pts[next_idx]

        # 最小邻域长度门控：防止锯齿 zigzag 伪拐角
        if dist(curr, prev) < _MIN_SEG_LEN_FOR_CORNER_PX:
            continue
        if dist(next_, curr) < _MIN_SEG_LEN_FOR_CORNER_PX:
            continue

        angle = turn_angle_deg(prev, curr, next_)
        if angle >= angle_threshold_deg:
            corners_set.add(i)

    # 闭合路径至少保留 1 个 corner（取角度最大）
    if closed and not corners_set:
        best_i = max(
            range(n),
            key=lambda i: turn_angle_deg(
                pts[(i - 1) % n], pts[i], pts[(i + 1) % n],
            ),
        )
        corners_set.add(best_i)

    corners = sorted(corners_set)
    return corners


# ---- 直/曲分类 ----

def classify_segments(
    pts: list[PixelPoint],
    corner_indices: list[int],
    straight_tol_px: float,
    closed: bool = False,
) -> list[dict]:
    """将 corner 之间的段分类为直线或曲线。

    用 chordal deviation（段内点到两端 corner 连线的最大垂直距离）
    与 straight_tol_px 比较。

    Args:
        pts: 完整点序列
        corner_indices: 拐角索引列表（已排序）
        straight_tol_px: 弦偏差阈值 (px)
        closed: 闭合路径才连接末 corner → 首 corner；开口路径禁止幻影闭合边

    Returns:
        list[dict]: 每段 {start_idx, end_idx, is_straight, max_deviation_px, points}
    """
    segments: list[dict] = []
    n_corners = len(corner_indices)
    if n_corners < 2:
        return segments

    n_segments = n_corners if closed else n_corners - 1

    for k in range(n_segments):
        i_start = corner_indices[k]
        i_end = corner_indices[(k + 1) % n_corners] if closed else corner_indices[k + 1]

        # 取出 segment 内的点（含两端 corner）
        if i_end > i_start:
            seg_pts = pts[i_start:i_end + 1]
        elif closed:
            seg_pts = pts[i_start:] + pts[:i_end + 1]
        else:
            continue

        if len(seg_pts) <= 2:
            segments.append({
                "start_idx": i_start,
                "end_idx": i_end,
                "is_straight": True,
                "max_deviation_px": 0.0,
                "points": seg_pts,
            })
            continue

        a, b = seg_pts[0], seg_pts[-1]
        max_dev = max(
            perpendicular_distance(p, a, b) for p in seg_pts[1:-1]
        )

        segments.append({
            "start_idx": i_start,
            "end_idx": i_end,
            "is_straight": max_dev <= straight_tol_px,
            "max_deviation_px": max_dev,
            "points": seg_pts,
        })

    return segments


# ---- 差异化简化 ----

def _simplify_straight_segment(seg_pts: list[PixelPoint]) -> list[PixelPoint]:
    """直线段：只保留两端点。"""
    if len(seg_pts) <= 2:
        return list(seg_pts)
    return [seg_pts[0], seg_pts[-1]]


def _simplify_curve_segment(
    seg_pts: list[PixelPoint],
    epsilon: float,
    max_vertices: int,
    closed: bool,
    min_points: int = 4,
) -> list[PixelPoint]:
    """曲线段：RDP 简化 + contour_max_vertices 软限制。

    软限制通过二分搜索 epsilon 实现。
    min_points 作为硬下限：不会压缩到少于 min_points。

    Args:
        seg_pts: 段内点序列
        epsilon: RDP 简化容差 (px)
        max_vertices: 软顶点数上限
        closed: 是否闭合
        min_points: 硬下限点数
    """
    if len(seg_pts) <= 2:
        return list(seg_pts)

    simplified = simplify_rdp(seg_pts, epsilon, closed=closed)

    # 如果已经 <= max_vertices 且 >= min_points，直接返回
    if len(simplified) <= max_vertices and len(simplified) >= min_points:
        return simplified

    # 如果只是低于 min_points，直接返回（RDP 没有过度压缩）
    if len(simplified) < min_points:
        return simplified

    # 点数超过 max_vertices：二分搜索压到上限，但不低于 min_points
    lo, hi = epsilon, epsilon * 20.0
    best = simplified
    for _ in range(15):
        mid = (lo + hi) * 0.5
        candidate = simplify_rdp(seg_pts, mid, closed=closed)
        if len(candidate) <= max_vertices:
            if len(candidate) >= min_points:
                best = candidate
            hi = mid
        else:
            lo = mid
        if len(best) <= max_vertices and len(best) >= min_points:
            if hi - lo < epsilon * 0.1:
                break

    return best


def _resample_refined_to_target(
    refined: list[PixelPoint],
    original: list[PixelPoint],
    closed: bool,
    min_required: int,
    fallback_spacing: float,
) -> list[PixelPoint]:
    """在 refined 结果基础上逐段插值补充点，直到 >= min_required。

    refined 保留了拐角但点数不足。按拐角分段，均匀填充中间点。
    若仍不足，回退到对原输入做均匀重采样。
    """
    n_refined = len(refined)
    if n_refined >= min_required:
        return list(refined)
    if n_refined < 2:
        return list(original)

    # 按各段长度比例分配新增点数
    segments = []
    total_len = 0.0
    for i in range(n_refined):
        j = (i + 1) % n_refined
        seg_len = dist(refined[i], refined[j])
        if closed or j != 0:
            segments.append((i, j, seg_len))
            total_len += seg_len

    if total_len <= 0:
        return list(original)

    # 计算每段需要的额外点数（含两端）
    extra = min_required - n_refined
    result: list[PixelPoint] = [refined[0]]
    for seg_idx, (i, j, seg_len) in enumerate(segments):
        # 按段长比例分配额外点
        if seg_idx < len(segments) - 1 or not closed:
            frac = seg_len / max(total_len, 1e-9)
            seg_extra = max(0, int(round(extra * frac)))
        else:
            # 最后一段拿剩余
            seg_extra = extra - (len(result) - 1 - (seg_idx))

        if seg_extra > 0 and seg_len > 1e-9:
            for k in range(1, seg_extra + 1):
                t = k / (seg_extra + 1)
                result.append(PixelPoint(
                    x=refined[i].x + t * (refined[j].x - refined[i].x),
                    y=refined[i].y + t * (refined[j].y - refined[i].y),
                ))
        result.append(refined[j])

    # 闭合：去掉重复的末点
    if closed and len(result) >= 2:
        if dist_sq(result[0], result[-1]) < 0.01:
            result.pop()

    # 最终安全网
    if len(result) < min_required:
        if len(original) >= min_required:
            return list(original)
        elif total_len > 0:
            safe_sp = total_len / max(min_required, 1) if closed else total_len / max(min_required - 1, 1)
            safe_sp = max(safe_sp, fallback_spacing * 0.1)
            result = resample_uniform(original, safe_sp, closed=closed)
            if len(result) < min_required and len(original) >= min_required:
                result = list(original)

    return result


# ---- AdaptivePathRefiner ----

class AdaptivePathRefiner:
    """拐角保护 + 自适应简化精炼器。

    用法:
        refiner = AdaptivePathRefiner()
        refined_strokes, stats = refiner.refine_strokes(strokes, config, px_per_mm=10.0)
    """

    @staticmethod
    def refine_points(
        pts: list[PixelPoint],
        closed: bool,
        corner_angle_deg: float,
        straight_tol_px: float,
        curve_epsilon_px: float,
        curve_resample_px: float,
        max_vertices: int,
        min_retention_ratio: float = 0.70,
        min_closed_points: int = _MIN_CLOSED_POINTS,
        min_curve_points: int = 16,
    ) -> tuple[list[PixelPoint], bool]:
        """纯像素点序列自适应简化 + 保形压缩率守卫。

        Args:
            pts: 输入点序列（应为均匀采样后的点）
            closed: 是否闭合
            corner_angle_deg: 拐角检测角度阈值
            straight_tol_px: 直线判定弦偏差阈值 (px)
            curve_epsilon_px: 曲线段 RDP epsilon (px)
            curve_resample_px: 曲线段重采样间距 (px)
            max_vertices: 曲线段软顶点数上限（不覆盖 min_retention_ratio）
            min_retention_ratio: 最少保留点数比例 (0~1)
            min_closed_points: 闭合路径最少点数
            min_curve_points: 曲线段最少点数

        Returns:
            (points, guard_triggered)
            — guard_triggered=True 表示需要回退/重采样才满足保形要求
        """
        n = len(pts)
        if n <= 2:
            return list(pts), False

        # 计算最小保留点数
        min_by_ratio = max(1, int(math.ceil(n * min_retention_ratio)))
        min_by_type = (min_closed_points if closed else _MIN_OPEN_POINTS)
        min_required = max(min_by_ratio, min_by_type)

        # ---- 执行自适应简化 ----
        raw = AdaptivePathRefiner._do_refine(
            pts, closed, corner_angle_deg, straight_tol_px,
            curve_epsilon_px, curve_resample_px, max_vertices,
            min_curve_points,
        )

        guard_triggered = len(raw) < min_required

        if guard_triggered:
            # 回退策略：在 _do_refine 结果（保留拐角）的基础上，
            # 逐段插值补充中间点，直到满足 min_required
            result = _resample_refined_to_target(
                raw, pts, closed, min_required, curve_resample_px,
            )
        else:
            result = raw

        return result, guard_triggered

    @staticmethod
    def _do_refine(
        pts: list[PixelPoint],
        closed: bool,
        corner_angle_deg: float,
        straight_tol_px: float,
        curve_epsilon_px: float,
        curve_resample_px: float,
        max_vertices: int,
        min_curve_points: int,
    ) -> list[PixelPoint]:
        """内部：执行自适应简化（不包含压缩率守卫）。"""
        n = len(pts)
        if n <= max_vertices and closed:
            return list(pts)

        corners = detect_corners(pts, corner_angle_deg, closed=closed)

        if len(corners) <= 2 and closed:
            simplified = simplify_rdp(pts, curve_epsilon_px, closed=True)
            if len(simplified) > max_vertices:
                simplified = _simplify_curve_segment(
                    pts, curve_epsilon_px, max_vertices, closed=True,
                    min_points=min_curve_points,
                )
            if len(simplified) > 3:
                simplified = resample_uniform(simplified, curve_resample_px, closed=True)
            return simplified

        if len(corners) <= 2 and not closed:
            simplified = _simplify_curve_segment(
                pts, curve_epsilon_px, max_vertices, closed=False,
                min_points=min_curve_points,
            )
            if len(simplified) > 3:
                simplified = resample_uniform(simplified, curve_resample_px, closed=False)
            return simplified

        segments = classify_segments(pts, corners, straight_tol_px, closed=closed)

        result: list[PixelPoint] = []
        for seg in segments:
            seg_pts = seg["points"]
            if seg["is_straight"]:
                simplified = _simplify_straight_segment(seg_pts)
            else:
                simplified = _simplify_curve_segment(
                    seg_pts, curve_epsilon_px, max_vertices, closed=False,
                    min_points=min_curve_points,
                )
            if not result:
                result.extend(simplified)
            else:
                result.extend(simplified[1:])

        if closed and len(result) >= 3:
            if dist_sq(result[0], result[-1]) > straight_tol_px * straight_tol_px * 0.25:
                result.append(result[0])

        return result

    @staticmethod
    def _pick_retention_ratio(source_type: str) -> float:
        """根据 source_type 选择保留率。"""
        ratios = {
            "contour": _DEFAULT_RETENTION_CONTOUR,
            "skeleton": _DEFAULT_RETENTION_SKELETON,
            "image": _DEFAULT_RETENTION_CONTOUR,
        }
        return ratios.get(source_type, _DEFAULT_RETENTION_CONTOUR)

    @staticmethod
    def refine_stroke(
        stroke: Stroke,
        corner_angle_deg: float,
        straight_tol_px: float,
        curve_epsilon_px: float,
        curve_resample_px: float,
        max_vertices: int,
        min_retention_ratio: float | None = None,
        min_closed_points: int = _MIN_CLOSED_POINTS,
        min_curve_points: int = 16,
    ) -> tuple[Stroke, bool]:
        """单条 stroke 自适应简化。原地修改 points_px。

        Returns:
            (stroke, guard_triggered)
        """
        ratio = min_retention_ratio if min_retention_ratio is not None else \
            AdaptivePathRefiner._pick_retention_ratio(stroke.source_type)

        stroke.points_px, guard = AdaptivePathRefiner.refine_points(
            stroke.points_px,
            closed=stroke.closed,
            corner_angle_deg=corner_angle_deg,
            straight_tol_px=straight_tol_px,
            curve_epsilon_px=curve_epsilon_px,
            curve_resample_px=curve_resample_px,
            max_vertices=max_vertices,
            min_retention_ratio=ratio,
            min_closed_points=min_closed_points,
            min_curve_points=min_curve_points,
        )
        return stroke, guard

    @staticmethod
    def refine_strokes(
        strokes: list[Stroke],
        config: PathConfig,
        px_per_mm: float = 10.0,
        min_retention_ratio_contour: float = _DEFAULT_RETENTION_CONTOUR,
        min_retention_ratio_skeleton: float = _DEFAULT_RETENTION_SKELETON,
        min_retention_ratio_image: float = _DEFAULT_RETENTION_CONTOUR,
        min_closed_points: int = _MIN_CLOSED_POINTS,
        min_curve_points: int = 16,
    ) -> tuple[list[Stroke], dict]:
        """Phase 4.2 编排入口：mm→px 集中转换 + 逐 stroke 精炼 + 保形守卫。

        Args:
            strokes: Phase 4.1 清洗/重采样后的 stroke 列表
            config: PathConfig
            px_per_mm: 像素/mm 换算比
            min_retention_ratio_contour: contour 类型最少保留点数比例 (default 0.70)
            min_retention_ratio_skeleton: skeleton 类型最少保留点数比例 (default 0.60)
            min_retention_ratio_image: image 类型最少保留点数比例 (default 0.70)
            min_closed_points: 闭合路径最少点数 (default 48)
            min_curve_points: 曲线段最少点数 (default 16)

        Returns:
            (refined_strokes, stats)
        """
        if px_per_mm <= 0:
            px_per_mm = 10.0

        # mm → px 集中转换
        straight_tol_px = config.straight_tol_mm * px_per_mm
        curve_epsilon_px = config.curve_epsilon_mm * px_per_mm
        curve_resample_px = config.curve_resample_step_mm * px_per_mm
        corner_angle_deg = config.corner_angle_deg
        max_vertices = config.contour_max_vertices

        # 各 source_type 的保留率
        ratio_map = {
            "contour": min_retention_ratio_contour,
            "skeleton": min_retention_ratio_skeleton,
            "image": min_retention_ratio_image,
        }

        input_count = len(strokes)
        vertices_before = sum(len(s.points_px) for s in strokes)
        corners_total = 0
        seg_straight = 0
        seg_curve = 0
        guard_triggered = 0
        guard_details: list[dict] = []
        per_stroke_before_after: list[dict] = []
        warnings: list[str] = []

        refined: list[Stroke] = []
        for s in strokes:
            orig_pts = s.points_px
            n_before = len(orig_pts)

            # Hershey 矢量折线保持 renderer 几何，不走拐角分段（避免开口路径幻影闭合边）
            if (s.metadata or {}).get("extract_algorithm") == "hershey":
                refined.append(s)
                per_stroke_before_after.append({
                    "stroke_id": s.id,
                    "source_type": s.source_type,
                    "closed": s.closed,
                    "before": n_before,
                    "after": n_before,
                    "retention": 1.0,
                    "hershey_preserve": True,
                })
                continue

            # 统计
            corners = detect_corners(orig_pts, corner_angle_deg, closed=s.closed)
            corners_total += len(corners)
            if len(corners) >= 2:
                segs = classify_segments(orig_pts, corners, straight_tol_px, closed=s.closed)
                seg_straight += sum(1 for seg in segs if seg["is_straight"])
                seg_curve += sum(1 for seg in segs if not seg["is_straight"])

            # 确定保留率
            ratio = ratio_map.get(s.source_type, _DEFAULT_RETENTION_CONTOUR)
            min_by_ratio = max(1, int(math.ceil(n_before * ratio)))
            min_by_type = min_closed_points if s.closed else _MIN_OPEN_POINTS
            min_req = max(min_by_ratio, min_by_type)

            # 精炼
            pts, guard_triggered_stroke = AdaptivePathRefiner.refine_points(
                orig_pts,
                closed=s.closed,
                corner_angle_deg=corner_angle_deg,
                straight_tol_px=straight_tol_px,
                curve_epsilon_px=curve_epsilon_px,
                curve_resample_px=curve_resample_px,
                max_vertices=max_vertices,
                min_retention_ratio=ratio,
                min_closed_points=min_closed_points,
                min_curve_points=min_curve_points,
            )

            n_after = len(pts)
            retention = n_after / max(n_before, 1)

            if guard_triggered_stroke:
                guard_triggered += 1
                guard_details.append({
                    "stroke_id": s.id,
                    "source_type": s.source_type,
                    "closed": s.closed,
                    "before": n_before,
                    "after": n_after,
                    "min_required": min_req,
                    "retention": round(retention, 4),
                })
                if n_after < min_req:
                    warnings.append(
                        f"compression guard FAILED: {s.id[:6]} ({s.source_type}) "
                        f"{n_before}->{n_after} < {min_req} required"
                    )
                else:
                    warnings.append(
                        f"compression guard: {s.id[:6]} ({s.source_type}) "
                        f"{n_before}->{n_after} (guard resampled, target {min_req})"
                    )

            per_stroke_before_after.append({
                "stroke_id": s.id,
                "source_type": s.source_type,
                "closed": s.closed,
                "before": n_before,
                "after": n_after,
                "retention": round(retention, 4),
            })

            if len(pts) >= 2:
                s.points_px = pts
                refined.append(s)

            if len(pts) >= max_vertices and s.closed:
                pass  # max_vertices is soft only, tracked via retention ratio

        vertices_after = sum(len(s.points_px) for s in refined)

        stats = {
            "phase": "4.2b",
            "input_stroke_count": input_count,
            "output_stroke_count": len(refined),
            "vertices_before": vertices_before,
            "vertices_after": vertices_after,
            "reduction_ratio": round(vertices_after / max(vertices_before, 1), 4),
            "corners_total": corners_total,
            "segments_straight": seg_straight,
            "segments_curve": seg_curve,
            "compression_guard_triggered_count": guard_triggered,
            "compression_guard_details": guard_details,
            "min_retention_ratio_contour": min_retention_ratio_contour,
            "min_retention_ratio_skeleton": min_retention_ratio_skeleton,
            "min_closed_points": min_closed_points,
            "per_stroke": per_stroke_before_after,
            "straight_tol_px": round(straight_tol_px, 4),
            "curve_epsilon_px": round(curve_epsilon_px, 4),
            "curve_resample_px": round(curve_resample_px, 4),
            "corner_angle_deg": corner_angle_deg,
            "max_vertices": max_vertices,
            "warnings": warnings,
        }

        return refined, stats
