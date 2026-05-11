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
class Path2D:
    """二维路径"""
    id: str
    points: list[Point2D]
    closed: bool = False
    role: str = "stroke"  # stroke / contour_outer / contour_inner / dot / travel
    source: str = ""       # text / drawing / svg / bitmap
    glyph: str = ""        # source character
    metadata: dict = field(default_factory=dict)


@dataclass
class Path3D:
    """三维路径 — Part B 使用"""
    id: str
    poses: list  # list[Pose]
    closed: bool = False
    source_path_id: str = ""
    role: str = "stroke"
    metadata: dict = field(default_factory=dict)


@dataclass
class WeldPointSegment:
    """焊接段 — Part B 使用"""
    id: str
    approach_path: list  # list[Pose]
    arc_start_path: list  # list[Pose]
    lead_in_path: list  # list[Pose]
    main_weld_path: list  # list[Pose]
    overlap_path: list  # list[Pose]
    lead_out_path: list  # list[Pose]
    arc_end_path: list  # list[Pose]
    retreat_path: list  # list[Pose]
    closed: bool = False
    overlap_length_mm: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class PenSegment:
    """写字/绘图工艺段 — Part C 使用"""
    id: str
    approach: list  # list[Pose]
    pen_down: list  # list[Pose]
    draw_path: list  # list[Pose]
    pen_up: list  # list[Pose]
    travel_to_next: list  # list[Pose]


@dataclass
class TrajectorySample:
    """CRI 轨迹采样点 — Part C 使用"""
    t: float  # seconds from start
    pose: object  # Pose
    linear_velocity_mm_s: float
    segment_id: str
    phase: str  # approach / pen_down / draw / pen_up / travel


@dataclass
class TrajectoryResult:
    """CRI 轨迹规划结果 — Part C 使用"""
    samples: list  # list[TrajectorySample]
    sample_rate_hz: int
    duration_s: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class Pose:
    """三维位姿"""
    position: Point3D
    orientation_euler_deg: EulerDeg
