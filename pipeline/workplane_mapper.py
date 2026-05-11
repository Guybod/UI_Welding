"""工作平面映射：三点标定 → Path2D 转 Path3D + 安全高度"""

from core.types import Point2D, Point3D, EulerDeg, Pose, Path2D, Path3D
from core.geometry import cross, normalize, normal_from_three_points
from core.errors import WorkplaneError


def _check_colinear(p1: Point3D, p2: Point3D, p3: Point3D, eps: float = 1e-6):
    """检查三点是否共线。"""
    v1 = Point3D(x=p2.x - p1.x, y=p2.y - p1.y, z=p2.z - p1.z)
    v2 = Point3D(x=p3.x - p1.x, y=p3.y - p1.y, z=p3.z - p1.z)
    c = cross(v1, v2)
    if abs(c.x) < eps and abs(c.y) < eps and abs(c.z) < eps:
        raise WorkplaneError("三点共线，无法确定工作平面")


def compute_workplane(
    left_top: Pose,
    left_bottom: Pose,
    right_bottom: Pose,
) -> tuple[Point3D, Point3D, Point3D]:
    """从三点标定计算工作平面的 X 向量、Y 向量、法向量。

    Returns:
        (x_vec, y_vec, normal): 三个单位向量
    """
    lt = left_top.position
    lb = left_bottom.position
    rb = right_bottom.position

    _check_colinear(lt, lb, rb)

    x_vec = Point3D(x=rb.x - lb.x, y=rb.y - lb.y, z=rb.z - lb.z)
    y_vec = Point3D(x=lt.x - lb.x, y=lt.y - lb.y, z=lt.z - lb.z)
    normal = normalize(cross(x_vec, y_vec))

    return normalize(x_vec), normalize(y_vec), normal


def map_to_3d(
    paths_2d: list[Path2D],
    left_top: Pose,
    left_bottom: Pose,
    right_bottom: Pose,
    canvas_width_mm: float,
    canvas_height_mm: float,
    safe_height_mm: float = 5.0,
    tool_orientation: EulerDeg | None = None,
) -> list[Path3D]:
    """将 2D 路径映射到 3D 工作平面。

    Args:
        paths_2d: 二维路径列表（坐标单位 mm）
        left_top: 左上角示教位姿
        left_bottom: 左下角示教位姿
        right_bottom: 右下角示教位姿
        canvas_width_mm: 2D 画布宽度 (mm)
        canvas_height_mm: 2D 画布高度 (mm)
        safe_height_mm: 安全高度（沿法向偏移）
        tool_orientation: 工具姿态。None 则使用 left_top 的姿态。

    Returns:
        Path3D 列表
    """
    if canvas_width_mm <= 0 or canvas_height_mm <= 0:
        raise ValueError("canvas dimensions must be positive")

    x_vec, y_vec, normal = compute_workplane(left_top, left_bottom, right_bottom)

    # 使用 left_bottom 作为映射原点（因为 LB = LT + Y_vec*something）
    origin = left_bottom.position

    orientation = tool_orientation or left_top.orientation_euler_deg

    result = []
    for p2d in paths_2d:
        poses = []
        for pt in p2d.points:
            # P(u,v) = origin + (u/w)*X_vec + (v/h)*Y_vec
            # 其中 u=pt.x, v=pt.y（2D坐标已按mm布局）
            u_ratio = pt.x / canvas_width_mm
            v_ratio = pt.y / canvas_height_mm

            pos = Point3D(
                x=origin.x + u_ratio * x_vec.x + v_ratio * y_vec.x,
                y=origin.y + u_ratio * x_vec.y + v_ratio * y_vec.y,
                z=origin.z + u_ratio * x_vec.z + v_ratio * y_vec.z,
            )

            # 安全高度位姿：沿法向抬高
            safe_pos = Point3D(
                x=pos.x + normal.x * safe_height_mm,
                y=pos.y + normal.y * safe_height_mm,
                z=pos.z + normal.z * safe_height_mm,
            )

            poses.append(Pose(position=pos, orientation_euler_deg=orientation))

        result.append(Path3D(
            id=p2d.id,
            poses=poses,
            closed=p2d.closed,
            source_path_id=p2d.id,
            role=p2d.role,
            metadata={
                **p2d.metadata,
                "safe_height_mm": safe_height_mm,
                "glyph": p2d.glyph,
                "source": p2d.source,
            },
        ))

    return result
