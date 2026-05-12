from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Point2D:
    x: float
    y: float


@dataclass
class Point3D:
    x: float
    y: float
    z: float


@dataclass
class EulerDeg:
    rx: float
    ry: float
    rz: float


@dataclass
class Quaternion:
    """四元数 — 预留类型，本轮主流程不使用"""
    w: float
    x: float
    y: float
    z: float


@dataclass
class Path2D:
    """二维路径"""
    id: str
    points: list[Point2D]
    closed: bool = False
    role: str = "stroke"  # stroke / contour_outer / contour_inner / dot / travel
    source: str = ""       # text / drawing / svg / bitmap
    glyph: str | None = None  # source character
    metadata: dict = field(default_factory=dict)


@dataclass
class Path3D:
    """三维路径 — 映射后使用"""
    id: str
    poses: list[Pose]
    closed: bool = False
    source_path_id: str = ""
    role: str = "stroke"
    metadata: dict = field(default_factory=dict)


@dataclass
class WeldPointSegment:
    """焊接段 — 旧版兼容"""
    id: str
    approach_path: list[Pose]
    arc_start_path: list[Pose]
    lead_in_path: list[Pose]
    main_weld_path: list[Pose]
    overlap_path: list[Pose]
    lead_out_path: list[Pose]
    arc_end_path: list[Pose]
    retreat_path: list[Pose]
    closed: bool = False
    overlap_length_mm: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class PenSegment:
    """写字/绘图工艺段 — 旧版兼容"""
    id: str
    approach: list[Pose]
    pen_down: list[Pose]
    draw_path: list[Pose]
    pen_up: list[Pose]
    travel_to_next: list[Pose]


@dataclass
class TrajectorySample:
    """CRI 轨迹采样点 — Future Phase 使用"""
    t: float
    pose: Pose
    linear_velocity_mm_s: float
    segment_id: str
    phase: str


@dataclass
class TrajectoryResult:
    """CRI 轨迹规划结果 — Future Phase 使用"""
    samples: list[TrajectorySample]
    sample_rate_hz: int
    duration_s: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class Pose:
    """三维位姿"""
    position: Point3D
    orientation_euler_deg: EulerDeg
    orientation_q: Quaternion | None = None  # 预留，本轮主流程不使用


@dataclass
class PixelPoint:
    """像素坐标 (渲染画布空间)"""
    x: float
    y: float


@dataclass
class PlanePoint:
    """UV 平面坐标 (mm, 工作平面 2D)"""
    u_mm: float
    v_mm: float


@dataclass
class RobotPoint:
    """机器人笛卡尔坐标 (mm, deg) — TXT 导出主格式"""

    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    def __sub__(self, other: "RobotPoint") -> "RobotPoint":
        """向量减法（仅位置分量，姿态归零）。"""
        return RobotPoint(
            x=self.x - other.x, y=self.y - other.y, z=self.z - other.z,
            rx=0.0, ry=0.0, rz=0.0,
        )

    def __add__(self, other: "RobotPoint") -> "RobotPoint":
        """向量加法（仅位置分量，姿态归零）。"""
        return RobotPoint(
            x=self.x + other.x, y=self.y + other.y, z=self.z + other.z,
            rx=0.0, ry=0.0, rz=0.0,
        )

    def __mul__(self, scalar: float) -> "RobotPoint":
        """标量乘法（仅位置分量，姿态归零）。"""
        return RobotPoint(
            x=self.x * scalar, y=self.y * scalar, z=self.z * scalar,
            rx=0.0, ry=0.0, rz=0.0,
        )

    def __truediv__(self, scalar: float) -> "RobotPoint":
        """标量除法（仅位置分量，姿态归零）。"""
        return RobotPoint(
            x=self.x / scalar, y=self.y / scalar, z=self.z / scalar,
            rx=0.0, ry=0.0, rz=0.0,
        )


@dataclass
class Stroke:
    """统一的路径单元，来自 contour 或 skeleton"""
    id: str
    source_type: str                     # "contour" | "skeleton" | "image"
    points_px: list[PixelPoint]
    points_mm: list[PlanePoint] | None = None
    closed: bool = False
    is_hole: bool = False
    glyph_id: str | None = None
    group_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ProcessSegment:
    """结构化工艺段"""
    id: str
    type: str                           # "travel" | "lead_in" | "weld" | "overlap" | "lead_out" | "retreat"
    points: list[RobotPoint]
    speed_mm_s: float
    arc_enabled: bool
    normal_offset_mm: float             # 沿工作平面法向的偏移量（高度）
    stroke_id: str
    metadata: dict = field(default_factory=dict)


@dataclass
class WeldingJob:
    """完整的焊接任务"""
    input_config: object                 # TextLayoutConfig
    workspace_config: object             # WorkspaceConfig
    process_config: object               # WeldingProcessConfig
    strokes: list[Stroke]
    segments: list[ProcessSegment]
    export_files: dict[str, str] = field(default_factory=dict)
    preview_data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


# ---- 配置数据类 ----


@dataclass
class TextLayoutConfig:
    """文字排版配置"""
    text: str = ""
    font_path: str = ""
    render_font_size_px: int = 600
    target_char_height_mm: float | None = 20.0
    char_spacing_mm: float = 2.0
    line_spacing_mm: float = 5.0
    writing_mode: str = "horizontal"       # "horizontal" | "vertical"
    primary_flow: str = "left_to_right"    # "left_to_right" | "right_to_left" | "top_to_bottom"
    align: str = "center"                  # "left" | "center" | "right"
    scale_mode: str = "shrink_to_fit"      # "fixed_size" | "shrink_to_fit" | "fit_workspace"
    keep_aspect_ratio: bool = True


@dataclass
class PathConfig:
    """路径提取与整形配置"""
    mode: str = "skeleton"                 # "contour" | "skeleton" | "image"
    min_path_length_mm: float = 2.0
    sample_spacing_mm: float = 0.5
    simplify_epsilon_mm: float = 0.2
    preserve_corners: bool = True
    corner_angle_deg: float = 60.0
    dot_strategy: str = "short_line"       # "keep" | "filter" | "short_line" | "small_circle"
    contour_max_vertices: int = 12
    straight_tol_mm: float = 0.5
    curve_epsilon_mm: float = 0.65
    curve_resample_step_mm: float = 2.5
    contour_inner_area_frac: float = 0.32


@dataclass
class WorkspaceConfig:
    """工作空间标定配置 — 主线 UV 映射 + 法向偏移"""
    # 三点标定
    left_top: RobotPoint | None = None
    left_bottom: RobotPoint | None = None
    right_top: RobotPoint | None = None
    right_bottom: RobotPoint | None = None   # 可选第四点

    # 映射模式
    mapping_mode: str = "uv"                 # 主线 — "uv" | 兼容 — "perspective" | "ortho"

    # 主线：法向偏移高度（沿工作平面法向 N 的 offset）
    normal_work_offset_mm: float = 5.0       # 焊接/落笔高度偏移
    normal_safe_offset_mm: float = 15.0      # 安全高度偏移
    normal_super_safe_offset_mm: float = 25.0  # 任务间超安全高度偏移
    normal_travel_offset_mm: float = 15.0    # travel 空移高度偏移

    # 兼容：仅 ortho legacy 模式使用的全局 Z（新 pipeline 主线不使用）
    z_safe_mm: float | None = None
    z_work_mm: float | None = None
    z_super_safe_mm: float | None = None

    # 兼容：正交映射栅格密度
    pixel_per_mm: float = 10.0

    # 工具姿态
    tool_tilt_deg: float = 0.0
    tool_rotate_about_normal_deg: float = 0.0


@dataclass
class WeldingProcessConfig:
    """焊接工艺配置"""
    lead_in_length_mm: float = 3.0
    lead_out_length_mm: float = 3.0
    overlap_length_mm: float = 5.0
    weld_point_spacing_mm: float = 0.5
    travel_speed_mm_s: float = 80.0
    weld_speed_mm_s: float = 30.0
    voltage: float = 24.0
    current: float = 150.0
    job: int = 0
    inductance: float = 0.0


@dataclass
class ExportConfig:
    """导出配置"""
    output_dir: str = "output"
    lua_enabled: bool = True               # 焊接主线：Lua 脚本输出
    points_ref_enabled: bool = True         # 焊接参考：weld_points.txt
    json_enabled: bool = True               # job.json
    preview_enabled: bool = True            # debug PNG + preview PNG
    preview_dpi: int = 150
    timestamp_prefix: bool = True
