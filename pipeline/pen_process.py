"""PenProcessPlanner: Path3D[] → PenSegment[] (抬笔/落笔/空移)"""

from core.types import Point3D, Pose, Path3D, PenSegment


def plan_pen_motion(
    paths_3d: list[Path3D],
    safe_height_mm: float = 5.0,
) -> list[PenSegment]:
    """为每条 Path3D 生成写字/绘图工艺段。

    每条路径生成：
        approach:      从安全高度接近起点
        pen_down:      下降到绘制高度
        draw_path:     连续绘制路径
        pen_up:        抬笔离开
        travel_to_next:空移到下一条路径

    Returns:
        PenSegment 列表
    """
    segments = []
    last_end: Pose | None = None

    for i, p3d in enumerate(paths_3d):
        if len(p3d.poses) < 2:
            continue

        seg_id = f"pen_{i:04d}"
        first_pose = p3d.poses[0]
        last_pose = p3d.poses[-1]
        orient = first_pose.orientation_euler_deg

        # 安全高度下的起点和终点
        safe_start = Pose(
            position=Point3D(
                x=first_pose.position.x,
                y=first_pose.position.y,
                z=first_pose.position.z + safe_height_mm,
            ),
            orientation_euler_deg=orient,
        )
        safe_end = Pose(
            position=Point3D(
                x=last_pose.position.x,
                y=last_pose.position.y,
                z=last_pose.position.z + safe_height_mm,
            ),
            orientation_euler_deg=orient,
        )

        # approach: 从上一路径终点（或当前起点上方）→ 当前起点上方
        if last_end is not None:
            approach = [last_end, safe_start]
        else:
            approach = [safe_start]

        # pen_down: 从安全高度 → 绘制起点
        pen_down = [safe_start, first_pose]

        # draw_path: 全部路径点
        draw_path = list(p3d.poses)

        # pen_up: 从绘制终点 → 安全高度
        pen_up = [last_pose, safe_end]

        # travel_to_next: 空移（暂时与 approach 合并，后续路径使用 safe_end 作为 last_end）
        travel = []

        segments.append(PenSegment(
            id=seg_id,
            approach=approach,
            pen_down=pen_down,
            draw_path=draw_path,
            pen_up=pen_up,
            travel_to_next=travel,
        ))

        last_end = safe_end

    return segments
