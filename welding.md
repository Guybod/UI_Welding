# welding.md 执行约束修订版

> 本文档基于原始 welding.md 修订。
> 修订日期: 2026-05-12
> 约束来源: 用户执行范围限定、高度命名规范、TXT 格式规范、Part 执行纪律要求。

---

## 0. 执行范围约束（最高优先级）

### 0.1 本轮允许执行的 Phase

| Phase | 内容 | 本轮状态 |
|-------|------|----------|
| Phase 0 | 现状审计 | ✅ 已完成 |
| Phase 1 | 核心数据模型与配置模型 | 🔲 本轮执行 |
| Phase 2 | ContourExtractor 轮廓字引擎 | 🔲 本轮执行 |
| Phase 3 | SkeletonExtractor 骨架字引擎 | 🔲 本轮执行 |
| Phase 4 | Path Refinement 路径整形层 | 🔲 本轮执行 |
| Phase 5 | Workspace UV Mapping 空间映射 | 🔲 本轮执行 |
| Phase 6 | Welding Process 工艺段生成 | 🔲 本轮执行 |
| Phase 7 | Export 导出系统 (Lua脚本 + weld_points.txt + job.json + debug PNG) | 🔲 本轮执行 |
| Phase 8 | Preview 可视化预览 | 🔲 本轮执行 |

### 0.2 Future Phase（保留但不允许本轮实现）

| Phase | 内容 | 本轮状态 |
|-------|------|----------|
| Phase 9 | Trajectory Planner 轨迹规划（绘图用） | ❌ Future Phase |
| Phase 10 | UI 接入（焊接页/绘图页/上传页/后台线程） | ❌ Future Phase |
| Phase 11 | CRI 控制预留 | ❌ Future Phase |

> **规定**：Phase 9/10/11 在本文档中仅保留标题和概要说明，不拆 Part，不执行。当前不允许修改任何 UI 文件，不允许接入 CRI，不允许连接机器人，不允许实现自动上传。

### 0.3 焊接 vs 绘图输出格式（关键区分）

| 模式 | 输出格式 | 用途 | 本轮状态 |
|------|---------|------|----------|
| **焊接** | **Lua 脚本**（movL + setWelderParam + arcOn/Off） | 后续通过 upload_page 上传到机器人项目槽位执行 | 🔲 本轮实现 |
| **焊接** | job.json（结构化任务文件） | 保存完整配置、路径、段、统计，方便复现和调试 | 🔲 本轮实现 |
| **绘图** | points.txt（CSV-like 点位文件） | 给 CRI 实时控制器消费（points.txt → trajectory → UDP） | ❌ Future Phase |
| **通用** | debug PNG / preview PNG | 各阶段调试预览 | 🔲 本轮实现 |

### 0.4 本轮输出范围限定

焊接 pipeline 本轮**仅生成**：
1. **Lua 脚本** — `movL(x, y, z, rx, ry, rz, speed, acc, blend)` + `setWelderParam(...)` + `arcOn()`/`arcOff()` 格式，兼容旧版 wledfont2_UI 的上传方式
2. **点位参考文件** — `weld_points.txt`（空格分隔 `x y z rx ry rz`，供人工检查）
3. **job.json** — 结构化任务文件（含完整配置、路径、段、统计）
4. **debug PNG + preview PNG** — 各阶段调试图和统一预览图

**不允许**：
- 自动上传 Lua 脚本到机器人
- 真实连接机器人
- 真实下发运动或 IO 控制
- 修改 UI 代码（upload_page、welding_page、writing_page 均不动）
- 接入 CRI 实时控制
- 生成绘图用的 TXT 点位文件（那是 Future Phase 的绘图模式输出）

---

## 1. 项目目标

开发一个 **双路径引擎 + 统一后处理** 的文字/图案/焊接轨迹生成系统。

**双路径引擎**：
- **ContourExtractor**（轮廓字引擎）：PIL 渲染 + cv2.findContours，适用于粗字体、艺术字、封闭字形
- **SkeletonExtractor**（骨架字引擎）：PIL 渲染 + skimage.skeletonize + 骨架图遍历，适用于单线字、快速写字、减少热输入

**统一后处理**：两种引擎输出统一的 `Stroke` 数据结构，之后进入同一套 PathRefinement → WorkspaceMapping → WeldingProcess → Export/Preview 流程。

**输出模式**：
- 焊接模式（本轮）→ Lua 脚本 + weld_points.txt（参考） + job.json + debug PNG + preview PNG
- 绘图模式（Future Phase）→ points.txt 点位文件（CSV-like，给 CRI 消费）

---

## 2. 非目标（当前阶段不做）

1. 真实连接机器人执行焊接或绘图
2. 真实下发 Robot/move、Robot/jog、IOManager/SetIOValue 等 API
3. 摆动焊接（只保留 voltage / current 参数，不做摆动参数和波形）
4. 绘图 TXT 点位文件生成（那是 Future Phase 绘图模式输出，不是焊接输出）
5. 汉字完整笔顺级路径规划（第二版）
6. SVG 贝塞尔解析（第二版）
7. 位图复杂轮廓清洗（第二版）
8. UI 接入（焊接页/绘图页/上传页均不动）
9. CRI 实时控制
10. 自动上传项目到机器人
11. Trajectory Planner 轨迹规划（绘图专用，Future Phase）

---

## 3. 关键命名与设计约束

### 3.1 高度字段：法向偏移为主，全局 Z 为辅

所有高度必须优先表达为沿工作平面法向 N 的 offset。主线字段：

| 字段名 | 含义 | 用途 |
|--------|------|------|
| `normal_work_offset_mm` | 沿法向的工作偏移 | 焊接/落笔高度（从工作平面沿法向的偏移量） |
| `normal_safe_offset_mm` | 沿法向的安全偏移 | 安全高度（抬笔/空走，从工作平面沿法向的偏移量） |
| `normal_super_safe_offset_mm` | 沿法向的超安全偏移 | 任务间绝对安全高度 |
| `normal_travel_offset_mm` | 沿法向的空移偏移 | travel 段专用高度 |

**兼容保留**（仅用于 `mapping_mode="ortho"` 遗留模式）：
- `z_safe_mm`, `z_work_mm`, `z_super_safe_mm` — 仅在 ortho 映射模式下生效
- 在主线 UV 映射模式下，这些字段**不在主流程中使用**，仅在导出 header 中作为参考注释

**禁止**：在 UV 映射模式下使用 `z + height` 计算安全高度。必须使用 `pos + normal * normal_safe_offset_mm`。

### 3.2 RobotPoint 格式

`RobotPoint` 以 `x/y/z/rx/ry/rz`（mm / deg）作为 TXT 导出主格式。

`Quaternion` 只作为 `core/types.py` 中的**预留类型**。本轮执行中：
- 允许定义 `Quaternion` dataclass 和 `euler_to_quat` / `quat_to_euler` 转换函数
- **不允许**在主流程中使用 quaternion 做姿态表示
- **不允许**实现 slerp 或任何姿态插值
- **不允许**在 pipeline 中将 EulerDeg 替换为 Quaternion

### 3.3 ContourExtractor 首轮验收字符

第一轮验收限定为：**A, B, O, 0, 8**

扩展字符（中文字符如 田、国、焊）放到增强测试阶段，不作为第一轮阻塞项。

---

## 4. 核心数据流

```
[文字输入 + 字体 + 字号]
    │
    ├──(contour 模式)──► ContourExtractor
    │   PIL 渲染 → 二值化 → cv2.findContours
    │   → 内外轮廓分离 → 小轮廓过滤 → 轮廓方向统一
    │   → 输出 list[Stroke]
    │
    └──(skeleton 模式)─► SkeletonExtractor
        PIL 渲染 → 二值化 → skimage.skeletonize
        → 骨架图构建 → 端点/分叉点检测 → 图遍历
        → spur pruning → stroke 拆分
        → 输出 list[Stroke]
            │
            ▼
    Path Refinement（统一整形）
    去重 → 去短线 → RDP 简化 → 重采样 → 平滑
    → 拐角保护 → 路径排序 → travel 优化
            │
            ▼
    Workspace Mapping（UV 映射主线）
    三点 TL/TR/BL → U/V/N 计算
    pixel → UV 平面 → Robot 坐标
    + 法向偏移补偿（normal_work_offset / normal_safe_offset 等）
            │
            ▼
    Welding Process（工艺段生成）
    travel → lead_in → weld → overlap → lead_out → retreat
    速度/arc_enabled 区分
            │
       ┌────┴────┐
       ▼         ▼
    Export     Preview
    Lua脚本   2D/3D PNG
    job.json
```

---

## 5. 核心数据结构

### 5.1 坐标类型

```python
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
```

### 5.2 预留类型（定义但不强制使用）

```python
@dataclass
class Quaternion:
    """四元数 — 预留类型，本轮主流程不使用"""
    w: float
    x: float
    y: float
    z: float
```

### 5.3 Stroke, ProcessSegment, WeldingJob

```python
@dataclass
class Stroke:
    id: str
    source_type: str          # "contour" | "skeleton" | "image"
    points_px: list[PixelPoint]
    points_mm: list[PlanePoint] | None = None
    closed: bool = False
    is_hole: bool = False
    glyph_id: str | None = None
    group_id: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class ProcessSegment:
    id: str
    type: str          # "travel" | "lead_in" | "weld" | "overlap" | "lead_out" | "retreat"
    points: list[RobotPoint]
    speed_mm_s: float
    arc_enabled: bool
    normal_offset_mm: float        # 法向偏移量（当前段的高度）
    stroke_id: str
    metadata: dict = field(default_factory=dict)  # 含 voltage, current 等

@dataclass
class WeldingJob:
    input_config: object           # TextLayoutConfig
    workspace_config: object       # WorkspaceConfig
    process_config: object         # WeldingProcessConfig
    strokes: list[Stroke]
    segments: list[ProcessSegment]
    export_files: dict[str, str]
    preview_data: dict
    metadata: dict = field(default_factory=dict)
```

### 5.4 配置数据类

```python
@dataclass
class TextLayoutConfig:
    text: str
    font_path: str
    render_font_size_px: int = 600
    target_char_height_mm: float | None = 20.0
    char_spacing_mm: float = 2.0
    line_spacing_mm: float = 5.0
    writing_mode: str = "horizontal"
    primary_flow: str = "left_to_right"
    align: str = "center"
    scale_mode: str = "shrink_to_fit"
    keep_aspect_ratio: bool = True

@dataclass
class PathConfig:
    mode: str = "contour"             # "contour" | "skeleton"
    min_path_length_mm: float = 2.0
    sample_spacing_mm: float = 0.5
    simplify_epsilon_mm: float = 0.2
    preserve_corners: bool = True
    corner_angle_deg: float = 60.0
    dot_strategy: str = "short_line"
    contour_max_vertices: int = 12
    straight_tol_mm: float = 0.5
    curve_epsilon_mm: float = 0.65
    curve_resample_step_mm: float = 2.5
    contour_inner_area_frac: float = 0.32

@dataclass
class WorkspaceConfig:
    # 主线：三点标定 UV 映射
    left_top: RobotPoint
    left_bottom: RobotPoint
    right_top: RobotPoint
    right_bottom: RobotPoint | None = None   # 可选第四点
    mapping_mode: str = "uv"                  # "uv" | "perspective" | "ortho"

    # 主线：法向偏移高度
    normal_work_offset_mm: float = 5.0        # 工作高度偏移
    normal_safe_offset_mm: float = 15.0       # 安全高度偏移
    normal_super_safe_offset_mm: float = 25.0 # 超安全高度偏移
    normal_travel_offset_mm: float = 15.0     # travel 空移高度偏移

    # 兼容：旧 ortho 模式的全局 Z
    z_safe_mm: float | None = None
    z_work_mm: float | None = None
    z_super_safe_mm: float | None = None

    # 兼容
    pixel_per_mm: float = 10.0

    # 工具姿态
    tool_tilt_deg: float = 0.0
    tool_rotate_about_normal_deg: float = 0.0

@dataclass
class WeldingProcessConfig:
    lead_in_length_mm: float = 3.0
    lead_out_length_mm: float = 3.0
    overlap_length_mm: float = 5.0
    weld_point_spacing_mm: float = 0.5
    voltage: float = 24.0
    current: float = 150.0
    travel_speed_mm_s: float = 80.0
    weld_speed_mm_s: float = 30.0

@dataclass
class ExportConfig:
    output_dir: str = "output"
    txt_enabled: bool = True
    json_enabled: bool = True
    preview_enabled: bool = True
    preview_dpi: int = 150
    timestamp_prefix: bool = True
```

---

## 6. Phase 0：现状审计（已完成）

Phase 0 审计涵盖旧版 wledfont2_UI、旧版 write4.0、当前 pipeline 半成品、当前 UI/服务层。详细结论见原 welding.md 第 3 节。

---

## 7. Phase 1：核心数据模型与配置模型

### Part 1.1 — 补全基础几何类型

**目标**：在 `core/types.py` 中补全本轮所需的基础类型。

**涉及文件**（仅限）：
- `core/types.py`（修改）
- `core/geometry.py`（修改，新增转换函数）
- `core/errors.py`（修改，新增异常类）

**新增内容**：
- `Quaternion(w, x, y, z)` dataclass — **仅作为预留类型**
- `PixelPoint`, `PlanePoint`, `RobotPoint` dataclass
- `Stroke` dataclass
- `ProcessSegment` dataclass（字段使用 `normal_offset_mm` 替代 `height_mm`）
- `WeldingJob` dataclass
- `Pose` 增加 `orientation_q: Quaternion | None = None` — **仅预留，本轮主流程不使用**

**新增函数**（`core/geometry.py`）：
- `euler_deg_to_quat(rx, ry, rz) -> Quaternion` — **预留**
- `quat_to_euler_deg(q: Quaternion) -> tuple` — **预留**
- `dot(a, b) -> float`
- `length(v) -> float`
- `distance(a, b) -> float`
- `normal_from_three_points(tl, tr, bl) -> Point3D` — 已有，确认正确

**新增异常**（`core/errors.py`）：
- `PathExtractionError`
- `ConfigurationError`
- `MappingError`

**验收标准**：
- `Quaternion` dataclass 存在
- `Pose` 有 `orientation_q` 字段但主流程不使用它
- `Stroke`, `ProcessSegment`, `WeldingJob` 可实例化
- `ProcessSegment.normal_offset_mm` 字段存在

**测试方式**：
```bash
python -c "
from core.types import Quaternion, Pose, Stroke, ProcessSegment, WeldingJob, RobotPoint
from core.geometry import euler_deg_to_quat, quat_to_euler_deg
q = euler_deg_to_quat(90, 0, 0)
rx, ry, rz = quat_to_euler_deg(q)
assert abs(rx - 90) < 0.001
s = Stroke(id='s1', source_type='contour', points_px=[PixelPoint(0,0)])
seg = ProcessSegment(id='p1', type='weld', points=[], speed_mm_s=30, arc_enabled=True, normal_offset_mm=5.0, stroke_id='s1')
print('PASS')
"
```

**风险点**：低。

**不允许**：
- 不要修改现有字段名（只新增）
- 不要删除 `orientation_euler_deg` 字段
- 不要在主流程中使用 `Quaternion`

**Part 完成汇报**：
- `git diff --name-only` 文件清单
- 测试命令和输出
- 下一 Part 依赖项

---

### Part 1.2 — 实现配置数据类

**目标**：实现配置 dataclass，使用法向偏移字段。

**涉及文件**（仅限）：
- `core/types.py`（新增配置类）
- `config/welding_defaults.py`（使用新配置类提供默认实例）

**新增内容**：
- `TextLayoutConfig`, `PathConfig`, `WorkspaceConfig`, `WeldingProcessConfig`, `ExportConfig`
- `WorkspaceConfig` 使用 `normal_*_offset_mm` 字段（主线）+ 保留 `z_*_mm`（兼容）
- `config/welding_defaults.py` 提供 `DEFAULT_TEXT_CONFIG`, `DEFAULT_PATH_CONFIG`, `DEFAULT_WORKSPACE_CONFIG`, `DEFAULT_WELDING_CONFIG`, `DEFAULT_EXPORT_CONFIG`

**验收标准**：
- `WorkspaceConfig.normal_work_offset_mm` 等四个法向字段存在
- 配置对象可被 `json.dumps(asdict(config))` 序列化

**测试方式**：
```bash
python -c "
from config.welding_defaults import DEFAULT_WORKSPACE_CONFIG
assert hasattr(DEFAULT_WORKSPACE_CONFIG, 'normal_work_offset_mm')
assert hasattr(DEFAULT_WORKSPACE_CONFIG, 'normal_safe_offset_mm')
print('PASS')
"
```

**风险点**：低。

**不允许**：配置类不要包含 Qt/PySide6 依赖；不要绑定 UI 控件引用。

---

## 8. Phase 2：ContourExtractor 轮廓字引擎

### Part 2.1 — 字体渲染与二值化

**目标**：从当前 `font_renderer.py` 提取独立的字体渲染模块。

**涉及文件**（仅限）：
- `pipeline/raster/__init__.py`（新建）
- `pipeline/raster/font_rasterizer.py`（新建，从 `font_renderer.py` 提取）

**新增内容**：
- `FontRasterizer` 类：封装 PIL 渲染、字号自适应、二值化
- `render_char(char, font_path, font_size_px) -> np.ndarray`
- `render_text(text, font_path, font_size_px) -> list[np.ndarray]`
- `get_optimal_font_size(text, font_path, canvas_w, canvas_h) -> int`
- `get_default_font_path() -> str`

**验收标准**：
- 渲染 'A' 和 'B' 到 600px 二值图成功
- 生成 `examples/output/raster_A.png` debug 图

**测试方式**：
```bash
python -c "
from pipeline.raster.font_rasterizer import FontRasterizer
r = FontRasterizer()
img = r.render_char('A', r.get_default_font_path(), 600)
assert img.shape[0] > 0 and img.shape[1] > 0
print('PASS')
"
```

**不允许**：不要在 rasterizer 中做排版或路径提取。

---

### Part 2.2 — 轮廓提取核心

**目标**：实现 `ContourExtractor`，从二值图提取轮廓并输出 `Stroke[]`。

**涉及文件**（仅限）：
- `pipeline/vision/__init__.py`（新建）
- `pipeline/vision/contour_extractor.py`（新建）

**新增内容**：
- `ContourExtractor` 类
  - `extract(binary, config) -> list[Stroke]`
  - `_find_contours(binary)` — cv2.RETR_TREE, CHAIN_APPROX_NONE
  - `_filter_small(contours, min_area)`
  - `_classify_inner_outer(contours, hierarchy, area_frac)` — 内外轮廓分离
  - `_extract_contour_path(cnt, is_inner, source) -> Stroke`
  - `_unify_direction(strokes)` — 外轮廓 CCW / 内轮廓 CW
  - `_order_strokes(strokes)` — 按 boundingRect X 排序

**第一轮验收字符**：**A, B, O, 0, 8**

**验收标准**：
- 'A' 生成开放外轮廓 stroke(s)
- 'B' 生成多段外轮廓 stroke(s) + 内轮廓(孔洞)
- 'O' 生成 1 个外轮廓 + 1 个内轮廓（孔洞）
- '0' 同 O
- '8' 生成 2 个外轮廓或 1 个外轮廓（上下两个环）
- 生成 `examples/output/contour_ABO08.png` 预览图

**测试方式**：
```bash
python -c "
from pipeline.raster.font_rasterizer import FontRasterizer
from pipeline.vision.contour_extractor import ContourExtractor
from config.welding_defaults import DEFAULT_PATH_CONFIG
r = FontRasterizer()
ext = ContourExtractor()
cfg = DEFAULT_PATH_CONFIG; cfg.mode = 'contour'
for ch in ['A','B','O','0','8']:
    img = r.render_char(ch, r.get_default_font_path(), 600)
    strokes = ext.extract(img, cfg)
    outer = [s for s in strokes if not s.is_hole]
    inner = [s for s in strokes if s.is_hole]
    print(f'{ch}: {len(strokes)} strokes, outer={len(outer)}, inner={len(inner)}')
print('PASS')
"
```

**不允许**：
- 不要在 ContourExtractor 中做空间映射
- 不要在 ContourExtractor 中做工艺段插入

---

### Part 2.3 — 轮廓简化与自适应精调

**目标**：迁移旧版 `_adaptive_xy_closed()` 算法链到 ContourExtractor 的像素空间版本。

**涉及文件**（仅限）：
- `pipeline/vision/contour_extractor.py`（修改，增加简化方法）

**新增内容**：
- `_simplify_contour_vertices(cnt, max_v)` — 顶点上限 approxPolyDP
- `_adaptive_simplify_closed(cnt, config)` — 直曲线自适应简化
- `_max_deviation_from_chord(pts)` — 最大弦偏差

**验收标准**：
- 正方形 → 4 角点
- 圆 → 多点保留（无尖角丢失）
- 拐角 'A' 字形在两个尖角处保留点

**不允许**：不要在像素空间做 mm 阈值判断（PathRefinement 会重做）。

---

## 9. Phase 3：SkeletonExtractor 骨架字引擎

### Part 3.1 — 骨架图构建与拓扑分析

**目标**：完善骨架提取，增加骨架图构建、端点/分叉点检测。

**涉及文件**（仅限）：
- `pipeline/vision/skeleton_extractor.py`（重写当前文件）

**新增内容**：
- `SkeletonGraph` 类（nodes / edges）
- `_detect_endpoints(skel)`, `_detect_branchpoints(skel)`
- `_connected_components(skel)`
- `_trace_edge(start, skel, visited)`
- `_spur_pruning(graph, min_len_px)`

**验收标准**：
- 'A' 骨架图端点/分叉点正确
- 生成 `examples/output/skeleton_graph_A.png` 调试图

**测试方式**：
```bash
python -c "
from pipeline.raster.font_rasterizer import FontRasterizer
from pipeline.vision.skeleton_extractor import SkeletonExtractor
from config.welding_defaults import DEFAULT_PATH_CONFIG
r = FontRasterizer()
img = r.render_char('A', r.get_default_font_path(), 600)
ext = SkeletonExtractor()
strokes, stats = ext.extract(img, DEFAULT_PATH_CONFIG)
print(f'A: {len(strokes)} strokes, {stats}')
"
```

**不允许**：不要把骨架像素直接当机器人路径。

---

### Part 3.2 — Stroke 提取与路径排序

**目标**：从 SkeletonGraph 提取 Stroke，支持笔画排序。

**涉及文件**（仅限）：
- `pipeline/vision/skeleton_extractor.py`（修改）

**新增内容**：
- `_extract_strokes_from_graph(graph, config) -> list[Stroke]`
- `_extract_open_strokes(graph)`, `_extract_closed_loops(graph)`
- `_order_strokes(strokes)` — 最近邻贪心 + 双向选择

**验收标准**：
- 'A'-'Z', 'a'-'z', '0'-'9' 每字符 stroke 数量合理
- 闭环 (O/o/0/6/8/9) 正确识别
- 输出调试统计（端点/分叉点/短枝/连通域数量）

**不允许**：不要把骨架提取器的排序做为最终排序。

---

## 10. Phase 4：Path Refinement 路径整形层

### Part 4.1 — 基础清洗与重采样

**目标**：统一处理 contour 和 skeleton 产出的 Stroke。

**涉及文件**（仅限）：
- `pipeline/path/__init__.py`（新建）
- `pipeline/path/path_cleaner.py`（新建）
- `pipeline/path/path_resampler.py`（新建）

**新增内容**：
- `remove_duplicate_points(pts, eps)` — 去重
- `remove_short_paths(strokes, min_len)` — 去短线
- `normalize_direction(strokes)` — 方向统一
- `detect_closed(pts, threshold)` — 闭环检测
- `resample_uniform(pts, spacing)` — 等距重采样
- `simplify_rdp(pts, epsilon)` — Douglas-Peucker
- `check_max_step(pts, max_mm) -> list[str]` — 步长检查

**验收标准**：
- 重复点被删除
- 重采样间距误差 < 10%
- 步长超过阈值的报警

**不允许**：不要在清洗中做空间映射或工艺段插入。

---

### Part 4.2 — 拐角保护与自适应简化

**目标**：迁移旧版自适应简化到 mm 空间的 PathRefinement 层。

**涉及文件**（仅限）：
- `pipeline/path/path_refiner.py`（新建）

**新增内容**：
- `AdaptivePathRefiner` 类
  - `refine(points, config) -> list`
  - `_detect_corners(points, angle_thresh)` — 拐角检测
  - `_classify_straight_curve(points, chord_tol)` — 直曲分类
  - `_simplify_straight(points)` / `_simplify_curve(points, epsilon, min_p)`

**验收标准**：
- 正方形 → 4 角点
- 锯齿 → 全部拐角保留
- 弦偏差 < straight_tol_mm

**不允许**：不要引入焊接工艺逻辑。

---

### Part 4.3 — 路径排序与 Travel 优化

**目标**：多段路径执行顺序优化。

**涉及文件**（仅限）：
- `pipeline/path/path_scheduler.py`（新建）

**新增内容**：
- `PathScheduler` 类
  - `optimize(strokes) -> list[Stroke]`
  - `_nearest_neighbor(strokes)` — 最近邻贪心
  - `_consider_reverse(strokes)` — 双向选择
  - `calc_total_travel(strokes) -> float`

**验收标准**：
- 排序后 travel 距离 <= 原始距离
- 同字符笔画不打散

**不允许**：不要在此层做路径简化。

---

## 11. Phase 5：Workspace UV Mapping 空间映射

### Part 5.1 — UV 映射主线

**目标**：实现三点 + 法向量 UV 映射。所有高度使用法向偏移。

**涉及文件**（仅限）：
- `pipeline/mapping/__init__.py`（新建）
- `pipeline/mapping/workplane.py`（新建）
- `pipeline/mapping/pose_mapper.py`（新建）

**新增内容**：

`workplane.py`：
- `WorkPlane` 类
  - `__init__(tl, tr, bl)` — U=normalize(TR-TL), V=normalize(BL-TL), N=normalize(U×V)
  - `pixel_to_plane(px, canvas_w, canvas_h) -> PlanePoint`
  - `plane_to_robot(pm, normal_offset_mm) -> RobotPoint` — 使用法向偏移
  - `get_safe_position(xy, normal_offset_mm) -> RobotPoint` — P + N * normal_offset
  - `validate() -> bool` — 三点不共线检查

`pose_mapper.py`：
- `PoseMapper` 类
  - `map_strokes(strokes, workplane, canvas_w, canvas_h, config) -> list[Stroke]`
  - `set_stroke_heights(stroke, workplane, config)` — 使用 `normal_*_offset_mm` 设置各段高度

**法向偏移使用规则**：
```
travel 高度:    pos + normal * normal_travel_offset_mm
lead_in 过渡:   从 normal_travel_offset_mm 渐变到 normal_work_offset_mm
weld 高度:      pos + normal * normal_work_offset_mm
lead_out 过渡:  从 normal_work_offset_mm 渐变到 normal_travel_offset_mm
retreat 高度:   pos + normal * normal_travel_offset_mm
```

**验收标准**：
- 水平平面上 four corners 映射正确
- 45° 倾斜平面安全高度方向沿法向（非 global Z）
- 输出 U/V/N 向量值和平面尺寸

**测试方式**：
```bash
python -c "
from pipeline.mapping.workplane import WorkPlane
from core.types import RobotPoint
tl = RobotPoint(0, 0, 100, -180, 0, -135)
tr = RobotPoint(200, 0, 100, -180, 0, -135)
bl = RobotPoint(0, 200, 100, -180, 0, -135)
wp = WorkPlane(tl, tr, bl)
assert abs(wp.normal[2] - 1.0) < 0.01  # 法向 ≈ (0,0,1)
# 安全位置应沿法向偏移
safe = wp.get_safe_position(PlanePoint(100, 100), 15.0)
assert abs(safe.z - 115.0) < 0.01  # 100 + 15 = 115（法向为(0,0,1)时等价于 z+height）
print('PASS')
"
```

**不允许**：
- 不要使用 `z + height` 替代法向偏移
- 不要在 mapper 中修改 stroke 拓扑关系

---

### Part 5.2 — 兼容模式保留

**目标**：保留旧 ortho 和 perspective 模式。

**涉及文件**（仅限）：
- `pipeline/mapping/workplane.py`（修改）

**新增内容**：
- `WorkPlane.from_four_corners(tl, tr, bl, br)` — perspective 兼容
- `WorkPlane.from_ortho(tl, pixel_per_mm, w, h)` — ortho 兼容
- 兼容模式下允许使用 `z_safe_mm` / `z_work_mm` 字段

**验收标准**：
- ortho 模式与旧版 pixel_per_mm 输出一致
- 默认 mapping_mode = "uv"

**不允许**：不要让兼容模式成为默认。

---

## 12. Phase 6：Welding Process 工艺段生成

### Part 6.1 — 工艺段结构生成

**目标**：从 Stroke 生成 ProcessSegment 序列，高度使用法向偏移。

**涉及文件**（仅限）：
- `pipeline/process/__init__.py`（新建）
- `pipeline/process/weld_process.py`（新建）

**新增内容**：
- `WeldingProcessPlanner` 类
  - `plan(strokes, workplane, config) -> list[ProcessSegment]`
  - `_plan_open(stroke, workplane, config)` — 开放路径
  - `_plan_closed(stroke, workplane, config)` — 闭合路径 + overlap
  - `_build_travel(from_pt, to_pt, workplane, config)` — travel 段（normal_travel_offset）
  - `_build_lead_in(stroke, workplane, config)` — lead_in 段
  - `_build_weld(stroke, workplane, config)` — weld 段（normal_work_offset）
  - `_build_overlap(stroke, workplane, config)` — overlap 段（闭合）
  - `_build_lead_out(stroke, workplane, config)` — lead_out 段
  - `_build_retreat(stroke, workplane, config)` — retreat 段
  - `_find_best_start(closed_points, config)` — 找低曲率段中部

**工艺段序列**：
```
[travel]  → 空移到 stroke 起点上方 (normal_travel_offset_mm, arc_enabled=False)
[lead_in]  → 从安全高度下降到工作高度并起弧 (normal_work_offset_mm, arc_enabled=True)
[weld]     → 正式焊接路径 (normal_work_offset_mm, arc_enabled=True)
[overlap]  → 闭合路径搭接段 (normal_work_offset_mm, arc_enabled=True)，开放路径为空
[lead_out] → 引出段 (normal_work_offset_mm, arc_enabled=True)
[retreat]  → 退枪到安全高度 (normal_travel_offset_mm, arc_enabled=False)
```

**验收标准**：
| 路径类型 | travel | lead_in | weld | overlap | lead_out | retreat |
|----------|--------|---------|------|---------|----------|---------|
| 'A'(开放) | 有 | 有 | 有 | 无 | 有 | 有 |
| 'O'(闭合) | 有 | 有 | 有 | 有(>=overlap_mm*0.95) | 有 | 有 |
| '0/8'(闭合) | 有 | 有 | 有 | 有 | 有 | 有 |
| 'B'(开放+内孔) | 有 | 有 | 有 | 无/有(依路径) | 有 | 有 |

- lead_in/lead_out 起弧灭弧点不在字形特征点
- 所有段高度通过 workplane.normal 计算（非法向不得使用 z+height）
- travel 段 arc_enabled=False

**不允许**：
- 不要硬编码 Z 高度偏移
- 不要在开放路径生成 overlap

---

### Part 6.2 — 焊接参数集成

**目标**：ProcessSegment.metadata 中包含 voltage、current。

**涉及文件**（仅限）：
- `pipeline/process/weld_process.py`（修改）
- `config/welding_defaults.py`（修改）

**验收标准**：
- 每个 weld 段的 metadata 含 voltage 和 current
- TXT 导出 header 含电压电流

**不允许**：不要实现摆动焊接参数（wtype/wfreq/wamp）。

---

## 13. Phase 7：Export 导出系统

### Part 7.1 — Lua 脚本导出（焊接主线）

**目标**：输出焊接用 Lua 脚本，格式兼容旧版 wledfont2_UI，movL + setWelderParam + arcOn/Off。

**涉及文件**（仅限）：
- `pipeline/output/__init__.py`（新建）
- `pipeline/output/lua_writer.py`（新建）

**新增内容**：
- `LuaWriter` 类
  - `write(segments, output_path, config, weld_params) -> str` — 写入 Lua 脚本
  - `_write_set_welder_param(f, voltage, current)` — setWelderParam({job=0, I=..., U=..., L=0})
  - `_format_movl(point, speed, acc, blend=0) -> str` — 格式化单条 movL
  - `_write_arcon(f)` / `_write_arcoff(f)` — arcOn() / arcOff()
  - `_write_comment(f, text)` — Lua 注释行
  - `_maybe_insert_breakpoint(f, line_count, interval=30)` — 每 N 行插入 print("")

**Lua 脚本结构**（按旧版格式）：
```lua
-- Robot Weld Path Lua Script v1.0
-- text: Abc123
-- font: /path/to/font.ttf
-- mode: contour
-- voltage: 24.0V  current: 150.0A
-- normal_work_offset_mm: 5.0
-- normal_safe_offset_mm: 15.0
-- lead_in_mm: 3.0  lead_out_mm: 3.0  overlap_mm: 5.0

setWelderParam({job=0, I=150.0, U=24.0, L=0})

-- stroke_A  seg_0001  approach
movL(100.000, 200.000, 182.500, -180.000, 0.000, -135.000, v=80.0, a=300, b=0)
-- stroke_A  seg_0001  lead_in (arc on)
movL(100.000, 200.000, 172.500, -180.000, 0.000, -135.000, v=30.0, a=300, b=0)
arcOn()

-- stroke_A  seg_0001  weld
movL(101.000, 200.000, 172.500, -180.000, 0.000, -135.000, v=30.0, a=300, b=0)
movL(102.000, 200.500, 172.500, -180.000, 0.000, -135.000, v=30.0, a=300, b=0)
...
print("")

-- stroke_A  seg_0001  overlap
movL(150.000, 200.000, 172.500, -180.000, 0.000, -135.000, v=30.0, a=300, b=0)

-- stroke_A  seg_0001  lead_out (arc off)
arcOff()
movL(153.000, 200.000, 182.500, -180.000, 0.000, -135.000, v=30.0, a=300, b=0)
print("")

-- ... 后续 stroke ...
```

**Lua 格式规则**：
- `movL(x, y, z, rx, ry, rz, v=<speed>, a=<acc>, b=<blend>)`
- `v` 参数使用 ProcessSegment.speed_mm_s
- `a` (加速度) 默认 300 mm/s²
- `b` (blend 过渡) 默认 0
- travel 段不调用 arcOn/arcOff
- lead_in 起始处调用 arcOn()
- lead_out 末尾处调用 arcOff()
- travel 和 retreat 段 speed 使用 travel_speed_mm_s
- 每 stroke 结束 insert print("")
- 每 30 行 movL 插入 print("") 断点（兼容旧版）

**输入**：`list[ProcessSegment]` + ExportConfig + 焊接参数(voltage/current)

**输出**：Lua 文件路径 + `weld_points.txt` 参考文件（空格分隔 x y z rx ry rz）

**验收标准**：
- Lua 脚本可在机器人控制器 Lua 解释器中执行
- setWelderParam 在文件开头只调用一次
- arcOn/arcOff 成对出现（每 stroke 一次）
- travel 段不含 arcOn/arcOff
- 每 30 行有 print("") 断点

**不允许**：
- 不要改变 movL 参数顺序（x, y, z, rx, ry, rz 必须是前 6 个位置参数）
- 不要在 weld 段中错误调用 arcOff
- 不要在 Lua 中嵌入 IO 寄存器写入（那是机器人端的内部逻辑）

---

### Part 7.2 — job.json 任务文件导出

---

### Part 7.2 — job.json + weld_points.txt 参考文件导出

**目标**：输出结构化 JSON + 人可读点位参考文件。

**涉及文件**（仅限）：
- `pipeline/output/json_writer.py`（新建）

**新增内容**：
- `JsonJobWriter` 类
  - `write(job: WeldingJob, output_path) -> str` — 写入 JSON
- `PointsRefWriter` 类
  - `write(segments, output_path) -> str` — 写入空格分隔的点位参考文件（x y z rx ry rz 每行）

**JSON 结构**：
```json
{
  "version": "1.0",
  "timestamp": "...",
  "input": {"text": "Abc123", "font": "...", "mode": "contour"},
  "config": {
    "text_layout": {...},
    "path": {...},
    "workspace": {
      "tl": {"x": 100, "y": 200, "z": 167.5, "rx": -180, "ry": 0, "rz": -135},
      "bl": {...}, "tr": {...},
      "normal": {"x": 0, "y": 0, "z": 1},
      "normal_work_offset_mm": 5.0,
      "normal_safe_offset_mm": 15.0
    },
    "welding": {"lead_in_mm": 3.0, "lead_out_mm": 3.0, "overlap_mm": 5.0, "voltage": 24.0, "current": 150.0}
  },
  "strokes": [{"id": "stroke_A", "source_type": "contour", "point_count": 42, "closed": false, "is_hole": false}],
  "segments": [
    {
      "id": "seg_0001",
      "type": "weld",
      "arc_enabled": true,
      "stroke_id": "stroke_A",
      "points": [{"x": 101.0, "y": 200.0, "z": 172.5, "rx": -180, "ry": 0, "rz": -135}],
      "metadata": {"voltage": 24.0, "current": 150.0}
    }
  ],
  "stats": {"total_points": 500, "total_segments": 10, "total_length_mm": 320.5}
}
```

**不允许**：JSON 中不要包含二进制数据或文件引用。

---

### Part 7.3 — Debug PNG 导出

**目标**：导出各阶段调试图像。

**涉及文件**（仅限）：
- `pipeline/output/preview_writer.py`（新建）

**新增内容**：
- `DebugExporter` 类
  - `export_original_binary(binary, path)` — 原始二值图
  - `export_contour_overlay(binary, strokes, path)` — 轮廓叠加
  - `export_skeleton_overlay(binary, graph, strokes, path)` — 骨架叠加（含端点/分叉点）
  - `export_stroke_order(strokes, path)` — stroke 顺序
  - `export_process_segments(segments, workplane, path)` — 工艺段彩色

**验收标准**：
- 生成 `examples/output/original_A.png`, `contour_A.png`, `segments_A.png`
- travel 虚线 / weld 实线 / overlap 红色

**不允许**：不要在导出函数中做路径计算。

---

## 14. Phase 8：Preview 可视化预览

### Part 8.1 — 统一预览管线

**目标**：整合所有预览到统一的 PreviewManager。

**涉及文件**（仅限）：
- `pipeline/preview.py`（重写当前文件）

**新增内容**：
- `PreviewManager` 类
  - `preview_all(job, output_dir) -> dict[str, str]`
  - `preview_extraction(binary, strokes)` — 路径提取预览
  - `preview_refinement(before, after)` — 整形前后对比
  - `preview_workspace(strokes, workplane)` — 工作平面 3D 投影
  - `preview_segments(segments, workplane)` — 工艺段预览
  - `preview_robot_path(segments, workplane)` — 机器人路径投影

**验收标准**：
- 所有预览图正常生成
- 3D 工作平面投影正确显示倾斜平面

**不允许**：不要在 PreviewManager 中修改数据。

---

## 15. Future Phase A：Trajectory Planner 轨迹规划（绘图用）

> **状态**：Future Phase，本轮不允许执行。
>
> 概要：将旧 write4.0 ConstantVelocitySpline 重构为通用 TrajectoryPlanner，为 WritingPage 的 CRI 控制做准备。
>
> 绘图模式输出：**points.txt**（CSV-like 固定字段格式，给 CRI 控制器消费）
> ```
> segment_id,stroke_id,segment_type,point_index,x,y,z,rx,ry,rz,speed_mm_s,arc_enabled,voltage,current,tag
> ```
> 涉及文件：`pipeline/trajectory/` 目录（新建）、`cubic_spline.py`、`time_parameterizer.py`、`trajectory_planner.py`

---

## 16. Future Phase B：UI 接入

> **状态**：Future Phase，本轮不允许执行。
>
> 概要：焊接页增加电压/电流/模式选择；绘画页实现 CRI 轨迹生成界面（dry-run）；上传页实现项目管理上传。
> 涉及文件：`welding_page.py`、`writing_page.py`、`upload_page.py`、`signal_binder.py`、`welding_service.py`（后台线程化）
>
> **重要**：upload_page 是独立功能模块，不允许绑定到本轮 welding pipeline 中。

---

## 17. Future Phase C：CRI 控制预留

> **状态**：Future Phase，本轮不允许执行。
>
> 概要：设计 CRIController / CriTrajectoryPlayer / CriStateCache 接口，明确 points.txt → CommandData 的转换规则。
> 不实现真实下发。

---

## 18. 本轮 Part 执行纪律（每个 Part 必须遵守）

1. **只改本 Part 明确涉及的文件**——不允许顺手修其他模块
2. **不跨 Phase 修改**——当前 Phase 未完成前，不允许动下一 Phase 的文件
3. **不顺手重构 UI**——不允许修改 `app/` 目录下任何文件
4. **不顺手接入 CRI**——不允许修改 `services/cri_service.py`、`network/protocol/cri_packer.py`
5. **不顺手改网络层**——不允许修改 `network/connection_manager.py` 或 TCP/UDP 相关文件
6. **每个 Part 完成后必须输出**：
   - `git diff --name-only` 文件变更清单
   - 测试命令
   - 测试结果（复制终端输出）
   - 下一 Part 建议
   - 是否违反了任何禁止事项

---

## 19. 风险总表

| 风险编号 | 风险描述 | 严重程度 | 影响 Phase | 缓解措施 |
|----------|----------|----------|------------|----------|
| R1 | 安全高度仍可能被写成 z+height | 严重 | Phase 5,6 | Phase 5 强制使用 normal_offset，Phase 6 审查 |
| R2 | ContourExtractor hierarchy 解析错误 | 中 | Phase 2 | 用 A/B/O/0/8 做回归测试 |
| R3 | SkeletonExtractor 交叉点在复杂字符中丢失连接 | 中 | Phase 3 | 首批只支持字母数字 |
| R4 | 三点共线导致法向计算不稳定 | 低 | Phase 5 | 共线性检测 + 用户提示 |
| R5 | matplotlib 在 headless 环境 crash | 低 | Phase 7,8 | 使用 Agg backend |
| R6 | 旧 pipeline 与新技术栈共存期间的模块冲突 | 低 | 全 Phase | 新 pipeline 放独立子目录 |

---

## 20. 测试总表

| Phase | 测试内容 | 方法 | 预期 |
|-------|----------|------|------|
| 1.1 | 类型实例化 | import + 构造 | 所有类型可用 |
| 1.2 | 配置序列化 | `json.dumps(asdict(config))` | 成功 |
| 2.1 | 字体渲染 | 渲染 'A' 600px | 二值图非空 |
| 2.2 | 轮廓提取 | A/B/O/0/8 → strokes | 内外轮廓数量正确 |
| 2.3 | 轮廓简化 | 正方→4角点 | 简化正确 |
| 3.1 | 骨架图构建 | 'A' → graph | 端点/分叉点正确 |
| 3.2 | stroke 提取 | A-Z → strokes | 数量合理 |
| 4.1 | 清洗重采样 | 冗余数据 → 清洗后 | 去重/间距正确 |
| 4.2 | 自适应简化 | 正方/锯齿/圆 | 角点保留 |
| 4.3 | 路径排序 | 随机路径 → 优化后 | travel 减少 |
| 5.1 | UV 映射 | 三点 → 平面映射 | 坐标/法向正确 |
| 5.1 | 安全高度方向 | 45° 倾斜平面 | 沿法向 |
| 6.1 | 工艺段 | O→闭合/V→开放 | 段类型顺序正确 |
| 7.1 | points.txt | 输出 → csv.reader 解析 | 14 字段固定 |
| 7.2 | job.json | 输出 → json.load | 可解析可复现 |
| 7.3 | debug PNG | 输出 → 查看 | 图像正确 |
| 8.1 | preview | 一键生成 | 无崩溃 |

---

## 21. 推荐执行顺序

```
Phase 1.1 → 1.2
    ↓
Phase 2.1 → 2.2 → 2.3
    ↓
Phase 3.1 → 3.2
    ↓
Phase 4.1 → 4.2 → 4.3
    ↓
Phase 5.1 → 5.2
    ↓
Phase 6.1 → 6.2
    ↓
Phase 7.1 → 7.2 → 7.3
    ↓
Phase 8.1
```

每 1-2 个 Part 完成后必须验证，通过后再进入下一步。

---

## 22. 绝对禁止事项

1. 不要修改代码（除非进入执行阶段且获得用户确认）
2. 不要真实连接机器人
3. 不要真实下发运动（Robot/move、Robot/jog、Robot/moveTo 等）
4. 不要使用普通 IO 接口（IOManager/SetIOValue、setDO、setAO 等）
5. 不要把焊接/写字/绘图和旧运动拖拽可视化模块混在一起
6. 不要把 skeletonize 输出直接当机器人路径
7. 不要只做骨架字（必须同时支持轮廓字）
8. 不要让路径提取器承担工艺段、空间映射、导出职责
9. 不要把 TXT 导出格式写得随意（必须 CSV-like 固定字段）
10. 不要修改 UI 文件（本轮不允许动 app/ 目录）
11. 不要对欧拉角做样条插值
12. 不要在安全高度计算中使用简单的 z+height（必须用法向偏移）
13. 不要允许 scale_x != scale_y
14. 不要把 Quaternion 强制用于主流程
15. 不要在 pipeline 模块中引入 Qt/PySide6 依赖
16. 不要实现 Phase 9/10/11（Future Phase）
17. 不要实现自动上传
18. 不要跨 Phase 顺手重构

---

*修订日期: 2026-05-12*
*原版: welding.md (v2)*
*修订范围: 执行范围限定、高度命名规范、TXT 格式固定化、Part 执行纪律*
