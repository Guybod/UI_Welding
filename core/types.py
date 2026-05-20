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
    margin_left_mm: float = 0.0
    margin_top_mm: float = 0.0
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
    # 骨架字（由 weld_font_presets 按字体写入）
    skeleton_raster_close_px: int = 0
    skeleton_raster_dilate_px: int = 0
    skeleton_spur_min_px: float = 3.0
    skeleton_merge_gap_px: float = 0.0
    skeleton_branch_cluster_radius_px: int = 5
    # 骨架字数据源：hershey=正式单线 stroke；ttf_skeleton_beta=旧 TTF 细化
    skeleton_source: str = "hershey"
    hershey_style: str = "futural"


@dataclass
class ImageProcessConfig:
    """图像 → 轮廓预处理配置（绘图页图片模式）。

    产品范围（口径）：
    - 适合：线稿、Logo、剪影、简单花朵轮廓。
    - 随手拍：需调阈值/边缘参数成线稿后再生成；复杂背景与照片级写实暂不承诺。

    UI（MVP）：
    - 生成前须有线稿预览，但为按钮触发的轻预览，不做参数联动实时预览。
    - 映射至可写区：默认 fit_mode=contain（等比留白）；可选 stretch 拉伸铺满。
    """
    threshold_method: str = "adaptive"   # fixed | adaptive | otsu
    threshold_value: int = 127
    blur_kernel: int = 3                 # 高斯模糊核；0/1 关闭
    gaussian_sigma: float = 0.0          # 0=自动
    median_blur_kernel: int = 0            # 中值滤波；0 关闭
    contrast: float = 1.0                # 对比度系数
    brightness: int = 0                    # 亮度偏移
    sharpen_amount: float = 0.0          # 锐化强度；0 关闭 (Unsharp Mask)
    sharpen_sigma: float = 1.0
    adaptive_block_size: int = 11          # adaptive 块大小（奇数）
    adaptive_c: int = 2
    edge_mode: str = "none"              # none | canny
    canny_low: int = 50
    canny_high: int = 150
    morph_kernel_size: int = 2           # 闭运算核；<2 不执行闭运算
    morph_open_size: int = 2             # 开运算核；<2 不执行开运算
    morph_mode: str = "close_open"       # none|close|open|open_close|close_open
    invert: bool = False
    min_contour_area: float = 100.0
    max_contours: int = 50
    simplification_epsilon: float = 1.5  # approxPolyDP 像素 epsilon
    contour_strategy: str = "external"   # external | all | centerline_beta
    fill_before_contour: bool = True     # 区域 mask 后再提轮廓，减少双层边
    fill_holes: bool = True              # 对前景 mask 填洞（Logo/剪影）
    keep_external_only: bool = True      # 与 contour_strategy 联动；external 时强制 True
    remove_border_contour: bool = False  # 过滤贴边超大轮廓（保守，默认关）
    fit_mode: str = "contain"            # contain | stretch
    max_total_points: int = 20000
    # 流程步骤开关（UI 分组复选框，默认全开）
    step_preprocess: bool = True
    step_binarize: bool = True
    step_morphology: bool = True
    step_region_mask: bool = True
    step_contour_extract: bool = True
    step_contour_dedup: bool = True
    step_contour_filter: bool = True
    step_mapping: bool = True

    def __post_init__(self) -> None:
        if self.fit_mode not in ("contain", "stretch"):
            raise ValueError(
                f"fit_mode must be 'contain' or 'stretch', got {self.fit_mode!r}"
            )
        if self.threshold_method not in ("fixed", "adaptive", "otsu"):
            raise ValueError(
                f"threshold_method must be fixed/adaptive/otsu, got {self.threshold_method!r}"
            )
        if self.edge_mode not in ("none", "canny"):
            raise ValueError(
                f"edge_mode must be 'none' or 'canny', got {self.edge_mode!r}"
            )
        if self.contour_strategy not in ("external", "all", "centerline_beta"):
            raise ValueError(
                "contour_strategy must be external, all, or centerline_beta, "
                f"got {self.contour_strategy!r}"
            )
        if self.morph_mode not in ("none", "close", "open", "open_close", "close_open"):
            raise ValueError(
                "morph_mode must be none, close, open, open_close, or close_open, "
                f"got {self.morph_mode!r}"
            )


@dataclass
class ImageDrawingConfig:
    """图片模式绘图工艺（笔 Z / 速度 / 可写区边距）。"""
    z_draw_mm: float = 305.0
    z_safe_mm: float = 315.0
    point_spacing_mm: float = 0.5
    travel_speed_mm_s: float = 80.0
    draw_speed_mm_s: float = 50.0
    margin_mm: float = 0.0
    max_total_points: int = 20000
    sample_rate_hz: int = 500
    max_robot_points: int = 50000

    def __post_init__(self) -> None:
        if self.z_safe_mm <= self.z_draw_mm:
            raise ValueError(
                f"z_safe_mm ({self.z_safe_mm}) must be greater than z_draw_mm ({self.z_draw_mm})"
            )


@dataclass
class ImageRunResult:
    """run_image_to_cri 输出摘要。"""
    ok: bool
    error: str = ""
    output_dir: str = ""
    files: dict[str, str] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


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

    # ── 主线：绝对 Z 高度（Phase 9.3-c 起为主模型）──
    z_work_mm: float = 305.0        # 焊接段绝对 Z（lead_in/weld/overlap/lead_out）
    z_safe_mm: float = 315.0        # 安全高度绝对 Z（travel/retreat）
    z_super_safe_mm: float = 325.0  # 超安全高度（预留）

    # ── @deprecated: 法向偏移量，新代码不应使用 ──
    normal_work_offset_mm: float = 5.0
    normal_safe_offset_mm: float = 15.0
    normal_super_safe_offset_mm: float = 25.0
    normal_travel_offset_mm: float = 15.0

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
    # 骨架字 W1-a：分叉处连续焊（仅 skeleton + 启用时）
    skeleton_continuous_junctions: bool = True
    skeleton_junction_merge_mm: float = 2.0
    skeleton_component_bridge_mm: float = 25.0


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


@dataclass
class LuaExportConfig:
    """Lua 焊接脚本导出格式配置"""
    acceleration: float = 300.0          # mm/s^2, movL a= 参数
    blend_mode: str = "absolute"         # "absolute" → b=, "relative" → rb=
    blend_radius: float = 0.0           # mm, b= 值 (absolute 模式)
    blend_ratio: int = 50               # 1-100, rb= 值 (relative 模式)
    lua_filename: str = "job.lua"       # 固定文件名 (use_text_as_filename=False 时使用)
    use_text_as_filename: bool = True   # True 时用 sanitize_lua_filename(text) 命名
    fallback_filename: str = "job.lua"  # text 为空时的 fallback
    precision: int = 3                   # x/y/z/rx/ry/rz 小数位数
    speed_precision: int = 1             # v= 速度小数位数
    skip_duplicate_points: bool = True   # 跳过连续相同位姿
    duplicate_tolerance_mm: float = 0.001
    include_travel: bool = True          # 输出 travel/retreat movL
    include_comments: bool = True        # 输出 -- segment 注释
    # wait() injection
    insert_wait: bool = False            # True → 每 N 条 movL 后插入 wait
    wait_every_movl: int = 30            # 每 N 条 movL 后插入一次 wait
    wait_duration_ms: int = 1            # wait 时间 (毫秒)

    def __post_init__(self):
        if self.blend_mode not in ("absolute", "relative"):
            raise ValueError(f"blend_mode must be 'absolute' or 'relative', got {self.blend_mode!r}")
        self.blend_ratio = max(1, min(100, int(self.blend_ratio)))
        self.wait_duration_ms = max(1, int(self.wait_duration_ms))
