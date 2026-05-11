# 机器人文字/绘图/焊接轨迹系统开发计划（Claude Code 执行版 v2）

> 本文档是给 Claude Code / 编程 Agent 直接执行的完整任务说明。  
> 目标是让 Agent 按阶段、按 Part 实现，不允许一次性写一个“看似完整但不可维护”的大文件。  
> 本文档中的约束优先级高于 Agent 的任何自行推断。

---

## 0. 项目最终目标

开发一个通用的 **文字 / 绘图 / 焊接轨迹生成系统**。

系统输入可以是：

```text
1. 文字：汉字、A-Z、a-z、0-9、常用符号
2. 字体：TTF / OTF 字体
3. 排版参数：字号、字高 mm、字间距、行距、换行、自动换行、左右/居中对齐、竖排、右到左、对联格式
4. 绘图：内置几何图形、SVG、位图轮廓/骨架
5. 工作空间：机器人示教的左上、左下、右下三个点
6. 模式：写字 / 绘图 / 焊接点位生成
```

系统输出分三类：

```text
1. 写字模式：通过 CRI 实时控制接口执行轨迹
2. 绘图模式：通过 CRI 实时控制接口执行轨迹
3. 焊接模式：只生成 TXT 点位文件，不直接下发运动、不直接控制 IO、不生成 Lua 运动脚本
```

---

## 1. 最高优先级硬约束

### 1.1 绝对禁止事项

Claude Code 必须严格遵守：

```text
1. 焊接模式禁止调用 Robot/move、Robot/moveTo、movJ、movL、movC、movS、movCircle 等机器人 API 运动接口。
2. 焊接模式禁止调用 IOManager/SetIOValue、setDO、setAO、寄存器写入、Modbus 写入等焊机/IO控制接口。
3. 焊接模式第一版只生成 TXT 点位文件，后续由外部系统处理焊接工艺和执行。
4. 写字模式和绘图模式必须走 CRI 实时控制接口，不使用 Robot/move 系列接口。
5. 所有曲线在焊接点位文件中统一离散成足够小间距的点，等价于后续按 movL 点到点执行。
6. 不允许为了铺满工作区而拉伸字体；只能等比例缩放。
7. 不允许把所有路径、断笔、空移、抬笔、落笔混成一条全局三次样条。
8. 不允许直接对欧拉角做三次样条插值。
9. 不允许在字形特征点、尖角、短碎段、闭环关键点直接起弧或灭弧。
10. 不允许把安全高度简单写成 Z+height；必须沿工作平面法向偏移。
11. 不允许把 PIL/OpenCV/轨迹规划/CRI通信/TXT输出全部写在一个文件里。
12. 不允许跳过测试字符和预览输出。
```

### 1.2 本项目使用的机器人接口范围

允许使用：

```text
1. TCP 9001：用于 CRI/StartDataPush、CRI/StopDataPush、CRI/StartControl、CRI/StopControl 等 JSON 控制请求。
2. UDP 9030：用于 CRI 实时控制数据流和状态推送。
3. CRI 状态推送：用于获取机器人实时状态、错误码、末端位姿、运动状态。
4. CRI 控制接口：用于写字/绘图/空跑实时控制。
```

暂时不使用：

```text
1. Robot/move
2. Robot/moveTo
3. Robot/jog
4. Robot/stopMove
5. project/runScript
6. 远程脚本 9002
7. IOManager/SetIOValue
8. RegisterManager/SetRegisterValue
9. ModbusTcp/setVal
10. Lua 脚本生成
```

> 注意：文档里可以保留未来扩展接口，但第一版代码中不得调用这些接口。

---

## 2. 已知 API 约束摘要

根据接口文档，机器人控制器包含 TCP/IP 与 UDP 通信，端口包括 9001 主接口、9002 远程脚本模式、9030 UDP CRI 实时控制接口；JSON 通信使用 UTF-8 编码。第一版仅使用 9001 上的 CRI 控制请求和 9030 UDP CRI 实时数据通道。

### 2.1 CRI 数据推送

2.3.3.23 及以上版本 StartDataPush 请求结构：

```json
{
  "id": 1,
  "ty": "CRI/StartDataPush",
  "db": {
    "ip": "192.168.1.150",
    "port": 18888,
    "duration": 1,
    "highPercision": true,
    "mask": 65535
  }
}
```

StopDataPush：

```json
{
  "id": 1,
  "ty": "CRI/StopDataPush",
  "db": {
    "ip": "192.168.1.150",
    "port": 18888
  }
}
```

### 2.2 CRI 实时控制

StartControl 请求结构：

```json
{
  "id": 1,
  "ty": "CRI/StartControl",
  "db": {
    "filterType": 0,
    "duration": 1,
    "startBuffer": 3
  }
}
```

StopControl：

```json
{
  "id": 1,
  "ty": "CRI/StopControl"
}
```

### 2.3 CRI CommandData 结构

CRI 控制数据结构：

```cpp
struct CommandData {
    Int64 timestamp{0};
    Float64 position[6]{0};
    UInt8 type{0};      // 0: 关节, 1: 末端
    UInt8 nc[7]{0};     // 保留字节
};
```

本项目第一版默认使用：

```text
type = 1
position = [x, y, z, rx, ry, rz]
```

单位约定：

```text
内部几何计算：mm、deg、quaternion
CRI 末端控制发送：根据接口文档，末端位置 x/y/z 为 m，rx/ry/rz 为 rad
TXT 点位文件：mm、deg，便于人读和后续脚本处理
```

发送 CRI 前必须做单位转换：

```text
x_mm / 1000 -> x_m
y_mm / 1000 -> y_m
z_mm / 1000 -> z_m
rx_deg -> rx_rad
ry_deg -> ry_rad
rz_deg -> rz_rad
```

---

## 3. 总体架构

必须采用分层架构。

```text
app/
  main.py
  config/
    defaults.py
    schema.py
  core/
    geometry.py
    types.py
    units.py
    errors.py
  layout/
    text_layout.py
    vertical_layout.py
    couplet_layout.py
    drawing_layout.py
  raster/
    font_rasterizer.py
    bitmap_preprocess.py
  vision/
    contour_extractor.py
    skeleton_extractor.py
    graph_paths.py
  path/
    path_cleaner.py
    path_resampler.py
    path_classifier.py
    path_scheduler.py
    overlap_planner.py
  mapping/
    workplane.py
    pose_mapper.py
  process/
    pen_process.py
    weld_point_process.py
  trajectory/
    time_parameterizer.py
    cubic_spline.py
    orientation.py
    trajectory_planner.py
    trajectory_validator.py
  cri/
    tcp_client.py
    udp_status_receiver.py
    udp_command_sender.py
    cri_packet.py
    cri_controller.py
  output/
    txt_point_writer.py
    preview_writer.py
    debug_exporter.py
  tests/
    test_layout.py
    test_paths.py
    test_workplane.py
    test_trajectory.py
    test_txt_output.py
    test_cri_packet.py
  examples/
    configs/
    output/
```

所有模块必须遵守：

```text
1. layout/raster/vision/path 只处理二维排版和路径。
2. mapping 只负责二维到三维工作平面映射。
3. process 只负责添加抬笔/落笔、起弧/灭弧语义、搭接、引入/引出等工艺路径。
4. trajectory 只负责 CRI 实时控制轨迹采样。
5. cri 只负责通信，不做路径算法。
6. output 只负责文件输出和调试预览。
```

---

## 4. 核心数据结构

必须先实现数据结构，再实现算法。

### 4.1 基础几何类型

```python
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
class Quaternion:
    w: float
    x: float
    y: float
    z: float

@dataclass
class EulerDeg:
    rx: float
    ry: float
    rz: float

@dataclass
class Pose:
    position: Point3D
    orientation_q: Quaternion
    orientation_euler_deg: EulerDeg | None = None
```

### 4.2 路径类型

```python
@dataclass
class Path2D:
    id: str
    points: list[Point2D]
    closed: bool
    source: str                  # text / drawing / svg / bitmap
    glyph: str | None = None
    role: str = "stroke"          # stroke / contour_outer / contour_inner / dot / travel
    metadata: dict = field(default_factory=dict)

@dataclass
class Path3D:
    id: str
    poses: list[Pose]
    closed: bool
    source_path_id: str
    role: str
    metadata: dict = field(default_factory=dict)
```

### 4.3 工艺段类型

```python
@dataclass
class PenSegment:
    id: str
    approach: list[Pose]
    pen_down: list[Pose]
    draw_path: list[Pose]
    pen_up: list[Pose]
    travel_to_next: list[Pose]

@dataclass
class WeldPointSegment:
    id: str
    approach_path: list[Pose]
    arc_start_path: list[Pose]
    lead_in_path: list[Pose]
    main_weld_path: list[Pose]
    overlap_path: list[Pose]
    lead_out_path: list[Pose]
    arc_end_path: list[Pose]
    retreat_path: list[Pose]
    closed: bool
    overlap_length_mm: float
    metadata: dict = field(default_factory=dict)
```

### 4.4 轨迹类型

```python
@dataclass
class TrajectorySample:
    t: float
    pose: Pose
    linear_velocity_mm_s: float
    segment_id: str
    phase: str   # approach / pen_down / draw / pen_up / travel

@dataclass
class TrajectoryResult:
    samples: list[TrajectorySample]
    sample_rate_hz: int
    duration_s: float
    warnings: list[str]
```

### 4.5 配置类型

```python
@dataclass
class TextLayoutConfig:
    text: str
    font_path: str
    render_font_size_px: int = 600
    target_char_height_mm: float | None = 20.0
    char_spacing_mm: float = 2.0
    line_spacing_mm: float = 5.0
    column_spacing_mm: float = 8.0
    margin_mm: float = 5.0
    writing_mode: str = "horizontal"       # horizontal / vertical / couplet
    primary_flow: str = "left_to_right"    # left_to_right / right_to_left / top_to_bottom
    secondary_flow: str = "top_to_bottom"  # top_to_bottom / right_to_left / left_to_right
    align: str = "center"                  # left / center / right
    vertical_align: str = "center"         # top / center / bottom
    wrap_mode: str = "manual"              # none / manual / auto
    scale_mode: str = "shrink_to_fit"      # fixed_size / shrink_to_fit / fit_workspace
    keep_aspect_ratio: bool = True
    allow_stretch: bool = False
```

```python
@dataclass
class PathConfig:
    mode: str = "skeleton"                 # skeleton / contour
    min_feature_size_mm: float = 2.0
    min_path_length_mm: float = 2.0
    sample_distance_mm: float = 0.5
    max_point_distance_mm: float = 1.0
    simplify_epsilon_mm: float = 0.2
    preserve_corners: bool = True
    corner_angle_deg: float = 60.0
    dot_strategy: str = "short_line"       # keep / filter / short_line / small_circle
```

```python
@dataclass
class WorkspaceConfig:
    left_top: Pose
    left_bottom: Pose
    right_bottom: Pose
    tool_tilt_deg: float = 0.0
    tool_rotate_about_normal_deg: float = 0.0
    pen_up_height_mm: float = 5.0
    weld_up_height_mm: float = 10.0
```

```python
@dataclass
class CriTrajectoryConfig:
    sample_rate_hz: int = 250
    interpolation: str = "cubic_spline"
    target_speed_mm_s: float = 30.0
    max_speed_mm_s: float = 80.0
    max_acc_mm_s2: float = 300.0
    min_waypoint_distance_mm: float = 0.2
    max_step_distance_mm: float = 1.0
    boundary_condition: str = "clamped_zero_velocity"
    orientation_mode: str = "fixed"        # fixed / slerp
    validate_before_execute: bool = True
```

```python
@dataclass
class WeldPointConfig:
    lead_in_length_mm: float = 3.0
    lead_out_length_mm: float = 3.0
    overlap_length_mm: float = 3.0
    min_straight_for_start_mm: float = 8.0
    min_distance_from_corner_mm: float = 3.0
    weld_point_spacing_mm: float = 0.5
    include_process_markers: bool = True
```

---

## 5. 功能范围

### 5.1 第一版必须支持

```text
1. 字符：A-Z、a-z、0-9、空格、-、_、.、/、+、=、:、;、#
2. 模式：骨架字优先，轮廓字预留接口
3. 字体：TTF / OTF
4. 字高：按 mm 设置，必须等比例缩放
5. 字距、行距、列距
6. 手动换行
7. 横排、竖排
8. 左对齐、居中、右对齐
9. 从左到右、从右到左、从上到下
10. 工作空间三点标定：左上、左下、右下
11. 写字/绘图 CRI 实时控制完整流程
12. 焊接 TXT 点位文件输出
13. 封闭路径搭接 overlap_length_mm
14. 开放路径引入 lead_in 和引出 lead_out
15. 小写 i/j 点状特征处理
16. 轨迹预览图和调试导出
```

### 5.2 第二版支持

```text
1. 汉字骨架字
2. 对联模式完整模板
3. 自动换行
4. SVG 导入
5. 位图轮廓绘图
6. 轮廓字内外轮廓排序
7. 闭合轮廓最佳起点自动评分
8. 曲率自适应点距
9. 更高级的速度规划
```

---

## 6. 文本排版要求

### 6.1 排版模式

必须支持：

```text
1. horizontal：横排
2. vertical：竖排
3. couplet：对联格式，第一版可只保留接口和简单实现
```

流向规则：

```text
普通横排：primary_flow=left_to_right, secondary_flow=top_to_bottom
横排右到左：primary_flow=right_to_left, secondary_flow=top_to_bottom
普通竖排：primary_flow=top_to_bottom, secondary_flow=left_to_right
传统竖排/对联：primary_flow=top_to_bottom, secondary_flow=right_to_left
```

### 6.2 缩放策略

必须实现三种：

```text
fixed_size:
  按用户设置的字高 mm 输出；如果超出工作区，返回错误，不自动缩小。

shrink_to_fit:
  优先按用户字高 mm 排版；若超出工作区，整体等比例缩小。

fit_workspace:
  忽略固定字高，以整体内容为单位等比例铺入工作区，不能拉伸。
```

默认：

```text
shrink_to_fit
```

禁止：

```text
scale_x != scale_y
```

### 6.3 PIL 渲染要求

必须使用高分辨率渲染，避免路径锯齿：

```text
render_font_size_px 默认 600
最低不得小于 300
```

文字先由 PIL 渲染为高分辨率二值图，再交给 OpenCV。

---

## 7. 路径提取要求

### 7.1 骨架字

第一版主线是骨架字：

```text
PIL 高分辨率文字图
    -> 二值化
    -> skeletonize / thinning
    -> 8 邻域图结构
    -> 识别端点、交叉点、闭环、小点
    -> 拆分 Path2D[]
```

必须处理：

```text
1. 开放笔画
2. 闭合骨架环
3. 小写 i/j 点
4. 交叉点
5. 短碎段过滤
6. 点距重采样
```

### 7.2 轮廓字

第一版可以只实现基础接口，第二版完善：

```text
cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
```

轮廓字后续必须支持：

```text
1. 外轮廓
2. 内轮廓
3. 先内后外
4. 封闭轮廓起点重排
5. 搭接段
```

---

## 8. 路径清洗与分类

每条 Path2D 必须经过：

```text
1. 删除重复点
2. 删除距离过近点
3. 删除长度小于 min_path_length_mm 的路径
4. 小特征处理
5. 按 sample_distance_mm 重采样
6. 识别 closed/open
7. 识别 dot/stroke/loop
8. 识别尖角和低曲率段
```

### 8.1 小写 i/j 点处理

小写 i/j 的点状特征必须单独处理。

支持策略：

```text
keep：保留原路径
filter：过滤掉
short_line：替换成短横线，默认
small_circle：替换成小圆
```

默认：

```text
short_line
```

短横线长度：

```text
max(2.0mm, 0.12 * target_char_height_mm)
```

---

## 9. 工作空间三点标定

用户示教三个点：

```text
P_LT：左上
P_LB：左下
P_RB：右下
```

计算：

```text
X_vec = P_RB - P_LB
Y_vec = P_LB - P_LT
normal = normalize(cross(X_vec, Y_vec))
```

二维点映射：

```text
P(u, v) = P_LT + (u / canvas_width) * X_vec + (v / canvas_height) * Y_vec
```

安全高度：

```text
P_safe = P + normal * height_mm
```

禁止：

```text
P_safe.z = P.z + height_mm
```

姿态要求：

```text
1. 第一版默认固定姿态。
2. 工具方向由用户示教姿态或工作平面法向生成。
3. 内部姿态用 quaternion 表示。
4. 输出 CRI 前转为 rx/ry/rz。
```

---

## 10. 写字 / 绘图 CRI 实时控制计划

### 10.1 总体流程

```text
输入文字/图形
  -> PIL/SVG/位图生成 Path2D[]
  -> Path2D 清洗、排序、重采样
  -> WorkPlaneMapper 转 Path3D[]
  -> PenProcessPlanner 插入抬笔/落笔/空移
  -> TrajectoryPlanner 生成等周期 PoseSample[]
  -> CRI Controller 开启状态推送
  -> CRI Controller 开启实时控制
  -> UDP CommandSender 按周期发送 CommandData
  -> UDP StatusReceiver 接收状态
  -> 执行结束 StopControl
```

### 10.2 PenProcessPlanner

每条绘制路径生成：

```text
approach_path：抬笔高度移动到起点上方
pen_down_path：下降到绘制高度
draw_path：连续绘制路径
pen_up_path：抬笔离开画布
travel_to_next：抬笔状态下移动到下一段
```

不同 Path2D 之间默认抬笔。

允许后续增加连笔参数：

```text
connect_gap_threshold_mm
```

第一版默认不连笔。

### 10.3 三次样条约束

CRI 轨迹规划器使用三次样条，但必须遵守：

```text
1. 每条连续绘制路径单独规划。
2. 抬笔路径单独规划。
3. 落笔路径单独规划。
4. 空移路径单独规划。
5. 不允许样条跨断笔。
6. 不允许样条跨尖角。
7. 不允许样条跨不同工艺段。
8. 位置可以三次样条，姿态默认 fixed。
9. 不允许对欧拉角做三次样条。
```

### 10.4 轨迹采样

默认参数：

```text
sample_rate_hz = 250
duration_ms = 4
startBuffer = 5
filterType = 0
target_speed_mm_s = 30
max_step_distance_mm = 1.0
```

如果用户配置 1000Hz，则：

```text
duration_ms = 1
sample_rate_hz = 1000
```

但第一版默认 250Hz，更稳。

### 10.5 CRI 通信启动顺序

执行前：

```text
1. 建立 TCP 9001 连接
2. StopDataPush，一律先停旧推送
3. StartDataPush，设置本机 UDP IP、端口、duration、mask、highPercision
4. 等待收到至少一帧状态数据
5. StartControl，设置 filterType、duration、startBuffer
6. 发送 startBuffer + 额外预缓冲点
7. 进入周期发送循环
```

执行后：

```text
1. 发送最后保持点若干帧
2. StopControl
3. StopDataPush
4. 关闭 UDP sender/receiver
5. 关闭 TCP 或保持连接供下次使用
```

异常停止：

```text
1. 停止发送新点
2. 发送若干帧当前保持点，可配置
3. StopControl
4. 记录错误
```

### 10.6 UDP CommandData 打包

必须实现 `cri_packet.py`：

```python
pack_command_data(
    timestamp: int,
    position: list[float],
    type: int = 1,
    endian: str = "little"
) -> bytes
```

字段：

```text
Int64 timestamp
Float64 position[6]
UInt8 type
UInt8 nc[7]
```

默认使用小端；如实机测试不匹配，再切换。

### 10.7 CRI 状态接收

必须解析：

```text
1. 时间戳
2. 状态数据1
3. 状态数据2
4. 关节位置
5. 末端位置
6. 末端速度，可选
```

状态数据至少要判断：

```text
1. 是否运动中
2. 是否报警
3. 是否急停
4. 是否实时控制模式
5. CRI 错误码
```

第一版只记录和回调，不做复杂安全策略。

---

## 11. 焊接 TXT 点位文件生成计划

### 11.1 焊接模式原则

焊接模式不实时下发，不调用任何机器人运动 API，不控制 IO。  
焊接模式只输出点位文件，供外部系统或人工处理。

焊接模式的目标：

```text
1. 将字母/数字/文字/图形路径转为可焊接点位。
2. 所有曲线离散为足够密的点。
3. 点位间距足够小，使后续逐点 movL 不影响曲线效果。
4. 开放路径生成 lead_in 和 lead_out。
5. 闭合路径生成 overlap 搭接段。
6. 起弧/灭弧点不在字形特征点上。
7. 输出 TXT 文件，包含路径段、点位、语义标记。
```

### 11.2 焊接段结构

每条路径输出 WeldPointSegment：

```text
approach_path：接近点，高于焊接面
arc_start_path：起弧位置路径，不在字形特征点
lead_in_path：引入段
main_weld_path：正式字形路径
overlap_path：闭合路径搭接段，开放路径为空
lead_out_path：引出段
arc_end_path：灭弧位置路径，不在字形特征点
retreat_path：抬枪路径
```

### 11.3 开放路径规则

原始开放路径：

```text
P0 -> P1 -> ... -> Pn
```

生成：

```text
arc_start = P0 - tangent_start * lead_in_length_mm
lead_in = arc_start -> P0
main = P0 -> ... -> Pn
lead_out = Pn -> Pn + tangent_end * lead_out_length_mm
arc_end = lead_out end
```

要求：

```text
1. P0/Pn 是字形特征点，不能作为起弧/灭弧点。
2. 起弧发生在 arc_start。
3. 灭弧发生在 arc_end。
4. lead_in/lead_out 与主路径方向一致。
```

### 11.4 闭合路径规则

原始闭合路径：

```text
P0 -> P1 -> ... -> Pn -> P0
```

生成：

```text
1. 找到低曲率/长直线/非尖角位置 S 作为起点。
2. 从 S 重排闭合路径。
3. main_weld_path 走完整一圈回到 S。
4. overlap_path 继续沿路径方向走 overlap_length_mm。
5. 灭弧点在搭接段之后，不在 S 本身。
```

第一版起点选择简化规则：

```text
1. 优先找最长近似直线段。
2. 如果没有直线段，找曲率最小的连续段。
3. 在该段中部作为 S。
4. 避开尖角、交叉点、小碎段。
```

### 11.5 搭接长度

搭接长度是焊接点位生成的核心参数。

默认：

```text
overlap_length_mm = 3.0
```

可调范围：

```text
0.5mm - 20mm
```

要求：

```text
1. 所有 closed=True 的焊接路径必须生成 overlap_path。
2. overlap_path 实际长度必须 >= overlap_length_mm 的 95%。
3. overlap_path 必须包含在 TXT 文件中，并有 phase=overlap 标记。
4. 不能把 overlap 和 lead_out 混成同一个字段。
```

### 11.6 点位间距

默认：

```text
weld_point_spacing_mm = 0.5
```

要求：

```text
1. 相邻焊接点距离不得大于 max(1.2 * weld_point_spacing_mm, weld_point_spacing_mm + 0.2mm)
2. 曲线也必须离散为小间距点。
3. 不再生成 movC/movS 指令。
4. 后续外部系统可以按点位顺序使用 movL 执行。
```

### 11.7 TXT 文件格式

必须输出一个主 TXT 文件：

```text
output/weld_points_<timestamp>.txt
```

推荐格式：

```text
# Robot Text/Shape Weld Point File
# version: 1.0
# units: position=mm, orientation=deg
# text: Abc123
# font: path/to/font.ttf
# mode: skeleton
# workspace: left_top=[...], left_bottom=[...], right_bottom=[...]
# weld_point_spacing_mm: 0.5
# lead_in_length_mm: 3.0
# lead_out_length_mm: 3.0
# overlap_length_mm: 3.0

SEGMENT id=seg_0001 source=A role=stroke closed=false
# phase,index,x,y,z,rx,ry,rz,tag
approach,0,100.000,200.000,310.000,180.000,0.000,90.000,approach
arc_start,0,100.000,200.000,300.000,180.000,0.000,90.000,arc_start
lead_in,0,101.000,200.000,300.000,180.000,0.000,90.000,lead_in
main,0,102.000,200.000,300.000,180.000,0.000,90.000,weld
...
lead_out,0,150.000,200.000,300.000,180.000,0.000,90.000,lead_out
arc_end,0,153.000,200.000,300.000,180.000,0.000,90.000,arc_end
retreat,0,153.000,200.000,310.000,180.000,0.000,90.000,retreat
END_SEGMENT

SEGMENT id=seg_0002 source=O role=loop closed=true
...
overlap,0,...
overlap,1,...
...
END_SEGMENT
```

同时输出 JSON 调试文件：

```text
output/weld_points_<timestamp>.json
```

用于程序再次读取和预览。

### 11.8 焊接预览

必须输出：

```text
output/preview_weld_<timestamp>.png
```

图中必须显示：

```text
1. 原始路径
2. 焊接主路径
3. lead_in
4. lead_out
5. overlap
6. arc_start
7. arc_end
8. segment 编号
9. 路径方向箭头
```

---

## 12. 轨迹规划器设计

### 12.1 输入

```python
TrajectoryRequest:
    segments: list[PenSegment]
    config: CriTrajectoryConfig
```

### 12.2 输出

```python
TrajectoryResult:
    samples: list[TrajectorySample]
```

### 12.3 时间参数化

```text
dt_i = distance(P[i], P[i+1]) / target_speed_mm_s
```

并强制：

```text
dt_i >= 1 / sample_rate_hz
```

### 12.4 三次样条

使用三次样条时：

```text
1. x(t), y(t), z(t) 分别插值。
2. 每个连续 phase 单独插值。
3. phase 边界速度默认为 0 或按切线估计，第一版用 clamped_zero_velocity。
4. 尖角处分段。
5. 如果样条过冲超过阈值，退化为线性重采样。
```

### 12.5 姿态

第一版：

```text
orientation_mode = fixed
```

内部：

```text
quaternion
```

发送前：

```text
quaternion -> rx/ry/rz -> rad
```

---

## 13. 测试字符和验收样例

必须使用以下测试集。

### 13.1 基础大写

```text
ABCDEF
GHIJKL
MNOPQR
STUVWXYZ
```

覆盖：

```text
A: 尖角
B: 多闭环/曲线
D/O/P/R: 闭合路径
S: 曲线
W/M/N/V/X/Y/Z: 尖角和折线
```

### 13.2 小写

```text
abcdefg
hijklmn
opqrstuvwxyz
```

覆盖：

```text
i/j: 点状特征
g/j/p/q/y: 下伸部
a/b/d/e/g/o/p/q: 闭合骨架/闭环
f/t/r: 小特征
```

### 13.3 数字

```text
0123456789
```

覆盖：

```text
0/6/8/9: 闭合路径 + overlap
2/3/5: 曲线
1/4/7: 开放路径
```

### 13.4 混排

```text
Abc123
Weld-09
OpenAI_2026
```

### 13.5 排版

```text
1. 横排左对齐
2. 横排居中
3. 横排右对齐
4. 右到左
5. 竖排
6. 手动换行
7. shrink_to_fit
8. fit_workspace
```

---

## 14. 分阶段开发计划

# Phase 0：工程骨架和基础数据结构

## Part 0.1 创建工程结构

任务：

```text
1. 创建 app/ 目录结构。
2. 创建 config/core/layout/raster/vision/path/mapping/process/trajectory/cri/output/tests/examples。
3. 添加 requirements.txt。
4. 添加 README.md。
5. 添加 main.py 命令行入口。
```

依赖建议：

```text
pillow
opencv-python
numpy
scipy
matplotlib
scikit-image
pytest
```

验收：

```text
python -m pytest
python app/main.py --help
```

禁止：

```text
不得在 main.py 中实现业务算法。
```

## Part 0.2 实现核心数据结构

任务：

```text
1. 实现 core/types.py。
2. 实现 core/geometry.py。
3. 实现 core/units.py。
4. 实现 config/schema.py。
```

验收：

```text
pytest tests/test_types.py
```

---

# Phase 1：文本排版和高分辨率渲染

## Part 1.1 PIL 字体渲染

任务：

```text
1. 实现 FontRasterizer。
2. 支持 TTF/OTF。
3. 支持高分辨率渲染。
4. 输出二值图和 debug png。
```

验收：

```text
生成 examples/output/raster_Abc123.png
```

## Part 1.2 排版引擎

任务：

```text
1. 实现 TextLayoutEngine。
2. 支持横排、竖排、手动换行。
3. 支持左/中/右对齐。
4. 支持字距、行距、列距。
5. 支持 left_to_right/right_to_left/top_to_bottom。
```

验收：

```text
生成横排、竖排、右到左的 debug png。
```

## Part 1.3 等比例缩放

任务：

```text
1. fixed_size。
2. shrink_to_fit。
3. fit_workspace。
4. 禁止拉伸。
```

验收：

```text
相同字体在不同工作区中比例不变。
```

---

# Phase 2：OpenCV 路径提取

## Part 2.1 骨架提取

任务：

```text
1. 二值图 skeletonize。
2. 构建 8 邻域图。
3. 识别端点、交叉点、闭环。
4. 拆分 Path2D[]。
```

验收：

```text
A-Z、a-z、0-9 均能输出 Path2D。
```

## Part 2.2 路径清洗和重采样

任务：

```text
1. 删除重复点。
2. 删除过短路径。
3. 小点特征处理。
4. 按 mm 点距重采样。
5. 标记 closed/open/dot/stroke。
```

验收：

```text
i/j 点能按 short_line 策略替换。
0/O/o 能识别 closed。
```

## Part 2.3 路径预览

任务：

```text
1. 输出路径编号。
2. 输出方向箭头。
3. 输出端点/交叉点/闭环标记。
```

验收：

```text
examples/output/preview_paths_Abc123.png
```

---

# Phase 3：工作平面映射

## Part 3.1 三点标定

任务：

```text
1. 实现 WorkPlane。
2. 输入 left_top/left_bottom/right_bottom。
3. 计算 X_vec/Y_vec/normal。
4. 检查三点不共线。
```

验收：

```text
二维矩形四角能映射到正确三维点。
```

## Part 3.2 Path2D -> Path3D

任务：

```text
1. 将 Path2D 映射为 Path3D。
2. 安全高度沿 normal 偏移。
3. 姿态固定。
```

验收：

```text
同一文字在倾斜平面也能正确生成 3D 点。
```

---

# Phase 4：写字/绘图 CRI 轨迹规划

## Part 4.1 PenProcessPlanner

任务：

```text
1. 每条 Path3D 生成 PenSegment。
2. 添加 approach、pen_down、draw、pen_up、travel_to_next。
3. 不同路径之间默认抬笔。
```

验收：

```text
预览图能看到空移线和绘制线分离。
```

## Part 4.2 三次样条轨迹规划器

任务：

```text
1. TimeParameterizer。
2. CubicSplineInterpolator。
3. FixedOrientationInterpolator。
4. TrajectoryValidator。
5. 每个 phase 单独规划。
```

验收：

```text
输出 TrajectoryResult，采样周期稳定。
相邻点距离不超过 max_step_distance_mm。
```

## Part 4.3 CRI 数据包

任务：

```text
1. 实现 CommandData 打包。
2. 末端控制 type=1。
3. mm/deg 转 m/rad。
4. 支持 little/big endian 配置。
```

验收：

```text
pytest tests/test_cri_packet.py
```

## Part 4.4 CRI 通信控制器

任务：

```text
1. TCP 9001 JSON 请求。
2. StopDataPush -> StartDataPush。
3. UDP StatusReceiver。
4. StartControl。
5. UDP CommandSender 周期发送。
6. StopControl。
7. StopDataPush。
```

验收：

```text
提供 dry-run 模式，不连接实机也能打印完整流程。
提供 real-run 模式，用户手动启用。
```

禁止：

```text
不得调用 Robot/move、Robot/moveTo、IO、Register、Modbus。
```

---

# Phase 5：焊接 TXT 点位文件

## Part 5.1 WeldPointProcessPlanner

任务：

```text
1. 开放路径生成 lead_in/lead_out。
2. 闭合路径选择起点并重排。
3. 闭合路径生成 overlap_path。
4. 生成 approach/retreat。
```

验收：

```text
O/o/0/6/8/9 必须有 overlap。
A/1/4/7 必须有 lead_in 和 lead_out。
```

## Part 5.2 TXT 点位输出

任务：

```text
1. 实现 TxtPointWriter。
2. 输出 phase,index,x,y,z,rx,ry,rz,tag。
3. 输出 metadata header。
4. 输出 JSON 调试文件。
```

验收：

```text
examples/output/weld_points_Abc123.txt
examples/output/weld_points_Abc123.json
```

禁止：

```text
不得生成 Lua。
不得调用机器人 API。
不得控制 IO。
```

## Part 5.3 焊接点位预览

任务：

```text
1. 显示 main/lead_in/lead_out/overlap。
2. 显示 arc_start/arc_end。
3. 显示方向箭头。
4. 显示 segment 编号。
```

验收：

```text
preview_weld_Abc123.png 中能清楚看到 overlap。
```

---

# Phase 6：绘图模式

## Part 6.1 内置几何图形

任务：

```text
1. 直线。
2. 矩形。
3. 圆。
4. 椭圆。
5. 多边形。
6. 五角星。
```

验收：

```text
所有图形可走 CRI 轨迹规划，也可生成焊接 TXT 点位。
```

## Part 6.2 SVG 预留接口

任务：

```text
1. 定义 SvgImporter 接口。
2. 暂时可抛 NotImplementedError。
3. 不影响第一版运行。
```

---

# Phase 7：命令行和集成

## Part 7.1 CLI 命令

必须支持：

```bash
python app/main.py render-text --text "Abc123" --font ./font.ttf --out examples/output
python app/main.py extract-path --image examples/output/raster_Abc123.png --mode skeleton
python app/main.py preview --text "Abc123" --font ./font.ttf
python app/main.py weld-points --text "Abc123" --font ./font.ttf --out examples/output
python app/main.py cri-dry-run --text "Abc123" --font ./font.ttf
python app/main.py cri-run --text "Abc123" --font ./font.ttf --robot-ip 192.168.1.136 --local-ip 192.168.1.150 --udp-port 18888
```

`cri-run` 必须要求显式参数，不能默认连接实机。

## Part 7.2 配置文件

支持 YAML/JSON 配置：

```text
examples/configs/default_text.yaml
examples/configs/default_cri.yaml
examples/configs/default_weld_points.yaml
```

---

# Phase 8：测试、验收、Agent 回报格式

## Part 8.1 单元测试

必须覆盖：

```text
1. 单位转换
2. 三点平面映射
3. 文本排版缩放不拉伸
4. 骨架路径提取
5. 闭合路径 overlap
6. 开放路径 lead_in/lead_out
7. CRI CommandData 打包
8. TXT 输出格式
```

## Part 8.2 集成测试

必须生成以下文件：

```text
examples/output/raster_Abc123.png
examples/output/preview_paths_Abc123.png
examples/output/preview_pen_Abc123.png
examples/output/preview_weld_Abc123.png
examples/output/weld_points_Abc123.txt
examples/output/weld_points_Abc123.json
examples/output/cri_dry_run_Abc123.json
```

## Part 8.3 Claude Code 每完成一个 Part 必须汇报

每个 Part 完成后，Claude Code 必须输出：

```text
1. 本 Part 修改/新增了哪些文件。
2. 新增了哪些类和函数。
3. 怎么运行本 Part 的测试。
4. 生成了哪些预览/输出文件。
5. 本 Part 没做什么。
6. 下一 Part 依赖什么。
7. 是否违反了禁止事项。
```

---

## 15. 第一版完成定义

第一版完成时，必须满足：

```text
1. 可输入 Abc123 / 0123456789 / A-Z / a-z。
2. 可选择字体。
3. 可设置字高 mm、字距、行距。
4. 可横排、竖排、手动换行、左中右对齐。
5. 可通过三点标定映射到三维工作面。
6. 可生成骨架路径。
7. 可生成写字/绘图 CRI dry-run 轨迹。
8. 可真实启用 CRI run，但必须由用户显式命令触发。
9. 可生成焊接 TXT 点位文件。
10. 闭合路径必须有 overlap。
11. 开放路径必须有 lead_in/lead_out。
12. i/j 点状特征必须可处理。
13. 有清晰预览图。
14. 没有调用 Robot/move、Robot/moveTo、IO、Register、Modbus、Lua。
```

---

## 16. 重点实现顺序

Claude Code 必须按顺序做：

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 5 -> Phase 4 -> Phase 7 -> Phase 8
```

说明：

```text
1. 先做焊接 TXT 点位输出，再做真实 CRI 控制。
2. CRI 真实控制风险更高，必须在路径、预览、TXT 输出稳定后再做。
3. Phase 4 可以先完成 dry-run，再做 real-run。
```

---

## 17. 给 Claude Code 的最终执行指令

请严格按本文档开发，不要自由发挥接口边界。

第一轮只执行：

```text
Phase 0 + Phase 1 + Phase 2 的最小可运行版本
```

完成后输出：

```text
1. 项目结构
2. 运行命令
3. 预览图片路径
4. 测试结果
5. 下一步建议执行的 Part
```

不要一次性完成全部 Phase。每个 Part 完成后必须等待用户测试结果，再进入下一 Part。

---

## 18. 本计划评分目标

本版本目标是：

```text
作为 Claude Code 任务文档：9.8/10
作为第一版工程规格：9.5/10
作为长期完整技术规格：9.0/10
```

剩余非第一版内容：

```text
1. 完整汉字笔顺级路径规划
2. 完整 SVG 贝塞尔解析
3. 位图复杂轮廓清洗
4. 完整关节空间连续性检查
5. 焊接工艺执行系统
6. Lua 脚本执行系统
```

这些不是第一版目标，不要让 Claude Code 提前实现。
