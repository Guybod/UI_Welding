"""焊接路径规划：开放路径 lead_in/lead_out，闭合路径 overlap"""

import math
from core.types import Point3D, EulerDeg, Pose, Path3D, WeldPointSegment


def _tangent_at(poses: list, idx: int, forward: bool = True) -> tuple[float, float, float]:
    """估算路径在指定索引处的切向方向。"""
    if forward:
        if idx < len(poses) - 1:
            a, b = poses[idx], poses[idx + 1]
        else:
            a, b = poses[idx - 1], poses[idx]
    else:
        if idx > 0:
            a, b = poses[idx - 1], poses[idx]
        else:
            a, b = poses[idx], poses[idx + 1]

    dx = b.position.x - a.position.x
    dy = b.position.y - a.position.y
    dz = b.position.z - a.position.z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        return (0.0, 0.0, 0.0)
    return (dx / length, dy / length, dz / length)


def _extend_along_tangent(pose, tangent: tuple[float, float, float], length: float) -> Pose:
    """从 pose 沿 tangent 延伸 length mm。"""
    return Pose(
        position=Point3D(
            x=pose.position.x + tangent[0] * length,
            y=pose.position.y + tangent[1] * length,
            z=pose.position.z + tangent[2] * length,
        ),
        orientation_euler_deg=pose.orientation_euler_deg,
    )


def _find_best_start(path3d: Path3D, min_straight_mm: float = 8.0) -> int:
    """为闭合路径找到最佳起弧点（最长近似直线段的中部）。"""
    if len(path3d.poses) < 4:
        return 0

    best_idx = 0
    best_len = 0.0

    for i in range(len(path3d.poses) - 1):
        # 简单策略：计算连续两个点的距离，累加找最长直段
        seg_len = 0.0
        for j in range(i, min(len(path3d.poses) - 1, i + 20)):
            a = path3d.poses[j].position
            b = path3d.poses[j + 1].position
            seg_len += math.sqrt(
                (b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2
            )
        if seg_len > best_len and seg_len >= min_straight_mm:
            best_len = seg_len
            best_idx = i + (j - i) // 2  # 取中点

    return best_idx


def _reorder_closed(path3d: Path3D, start_idx: int) -> list:
    """从 start_idx 开始重排闭合路径的 poses。"""
    n = len(path3d.poses)
    poses = path3d.poses[start_idx:] + path3d.poses[1:start_idx + 1]
    return poses


def _resample_positions(poses: list, spacing: float) -> list:
    """对 poses 按位置均匀重采样。"""
    if len(poses) < 2:
        return poses

    out = [poses[0]]
    cumulative = 0.0
    seg_idx = 0
    target = spacing

    while seg_idx < len(poses) - 1 and target < float("inf"):
        a = poses[seg_idx].position
        b = poses[seg_idx + 1].position
        seg_len = math.sqrt(
            (b.x - a.x) ** 2 + (b.y - a.y) ** 2 + (b.z - a.z) ** 2
        )

        while cumulative + seg_len >= target:
            t = (target - cumulative) / seg_len if seg_len > 0 else 0
            interp = Pose(
                position=Point3D(
                    x=a.x + t * (b.x - a.x),
                    y=a.y + t * (b.y - a.y),
                    z=a.z + t * (b.z - a.z),
                ),
                orientation_euler_deg=poses[seg_idx].orientation_euler_deg,
            )
            out.append(interp)
            target += spacing

        cumulative += seg_len
        seg_idx += 1

    out.append(poses[-1])
    return out


def plan_weld_paths(
    paths_3d: list[Path3D],
    lead_in_mm: float = 3.0,
    lead_out_mm: float = 3.0,
    overlap_mm: float = 3.0,
    point_spacing_mm: float = 0.5,
) -> list[WeldPointSegment]:
    """为每个 Path3D 生成焊接工艺段。

    Returns:
        WeldPointSegment 列表
    """
    segments = []

    for i, p3d in enumerate(paths_3d):
        if len(p3d.poses) < 2:
            continue

        seg_id = f"seg_{i:04d}"
        orient = p3d.poses[0].orientation_euler_deg

        if p3d.closed:
            # ── 闭合路径 ──
            start_idx = _find_best_start(p3d)
            ordered = _reorder_closed(p3d, start_idx)

            # 重采样
            main = _resample_positions(ordered, point_spacing_mm)

            # 搭接段：从主路径末尾继续走 overlap_mm
            overlap_pts = []
            if len(main) >= 2:
                # 计算主路径总长度，然后取最后一段搭接
                remain = overlap_mm
                idx = len(main) - 2
                while remain > 0 and idx >= 0:
                    a = main[idx].position
                    b = main[idx + 1].position
                    seg_len = math.sqrt((b.x - a.x) ** 2 + (b.y - a.y) ** 2 +
                                        (b.z - a.z) ** 2)
                    if seg_len <= remain:
                        overlap_pts.insert(0, main[idx + 1])
                        remain -= seg_len
                    else:
                        t = remain / seg_len
                        overlap_pts.insert(0, Pose(
                            position=Point3D(
                                x=a.x + t * (b.x - a.x),
                                y=a.y + t * (b.y - a.y),
                                z=a.z + t * (b.z - a.z),
                            ),
                            orientation_euler_deg=orient,
                        ))
                        remain = 0
                    idx -= 1

            # 接近段和退避段：使用主路径起点沿法向偏移
            entry = main[0] if main else p3d.poses[0]
            exit_pose = main[-1] if main else p3d.poses[-1]

            seg = WeldPointSegment(
                id=seg_id,
                approach_path=[entry],
                arc_start_path=[entry],
                lead_in_path=[],
                main_weld_path=main,
                overlap_path=overlap_pts,
                lead_out_path=[],
                arc_end_path=[exit_pose],
                retreat_path=[exit_pose],
                closed=True,
                overlap_length_mm=overlap_mm,
                metadata=p3d.metadata,
            )
        else:
            # ── 开放路径 ──
            main = _resample_positions(p3d.poses, point_spacing_mm)

            first = main[0]
            last = main[-1]
            tan_start = _tangent_at(p3d.poses, 0, forward=True)
            tan_end = _tangent_at(p3d.poses, len(p3d.poses) - 1, forward=False)

            # 起弧点在引入段起始（不在字形特征点）
            arc_start = _extend_along_tangent(first, tan_start, lead_in_mm)
            lead_in = [arc_start, first]

            # 灭弧点在引出段末端（不在字形特征点）
            arc_end = _extend_along_tangent(last, tan_end, lead_out_mm)
            lead_out = [last, arc_end]

            seg = WeldPointSegment(
                id=seg_id,
                approach_path=[arc_start],
                arc_start_path=[arc_start],
                lead_in_path=lead_in,
                main_weld_path=main,
                overlap_path=[],
                lead_out_path=lead_out,
                arc_end_path=[arc_end],
                retreat_path=[arc_end],
                closed=False,
                overlap_length_mm=0.0,
                metadata=p3d.metadata,
            )

        segments.append(seg)

    return segments
