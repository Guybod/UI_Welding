# 运动节点编排页面分阶段开发计划 v3（9.8 冲刺版）

## 0. 文档目的

本文档用于指导 Claude Code / Codex / 其他 AI Agent 分阶段开发 **运动节点编排页面**。

当前项目已经存在“运动”标签页，因此本计划 **不包含顶部标签页注册工作**。后续节点编辑器应直接集成到现有运动页面中，不要再新增重复的“运动编排”顶层标签页。

该页面目标是实现类似 ComfyUI 的节点连线式机器人运动流程编排界面，用于机器人运动、点位变量、IO、寄存器、逻辑控制和后续自定义节点扩展。

本版基于项目已有 API 文档补充了：

- 机器人运动接口 payload 样例；
- IO / 寄存器节点 payload 样例；
- CRI moving 判断依据；
- 执行日志字段规范；
- 停止/暂停/异常清理规则；
- 手工测试用例清单；
- Claude Code 分阶段执行要求。

---

## 1. 当前前提

### 1.1 已存在内容

当前项目已经存在：

```text
主页
焊接
写字
运动
IO
程序
上传
设置
```

因此本计划不要求：

```text
新增顶部标签
新增页面注册
修改 page_registry.py 中的页面顺序
重做 top_tab_bar.py
```

除非实际源码中“运动”标签页没有对应页面文件，否则不要重复创建新的顶层标签页。

### 1.2 推荐集成方式

在现有运动页面中添加节点编辑器区域。

推荐页面结构：

```text
运动页面 MotionPage
  ├─ 左侧/上方：可保留现有运动控制区域
  ├─ 左侧：节点库面板
  ├─ 中间：GraphView 节点画布
  ├─ 右侧：属性面板
  └─ 底部：执行日志 / 校验日志 / 运行控制栏
```

如果当前运动页只是占位页，可以直接把节点编辑器作为运动页主体。

如果当前运动页已有内容，则优先采用分栏布局，不要破坏已有功能。

---

## 2. 总体原则

1. 每个阶段只完成当前阶段目标。
2. 每个阶段完成后程序必须能启动。
3. 每个阶段完成后必须说明修改了哪些文件、如何测试。
4. 每个阶段完成后必须同步 `plan.md` 或本计划文档中的进度。
5. 不允许一次性重构整个项目。
6. 不允许影响现有登录、主页、焊接、写字、左侧运动抽屉、底部命令栏、TCP/UDP/CRI 通信功能。
7. 所有 move 指令都是非阻塞的，运动完成不能依赖 TCP response，必须依赖 CRI moving 状态判断。
8. 节点页面初期只作为独立“运动编排”功能区域，暂不强行接入焊接和写字流程。
9. 运动页面内的节点编辑器必须与现有左侧运动抽屉共存，不能互相遮挡关键操作区域。
10. GraphModel 与 QGraphicsItem 必须分离，保存文件只保存纯数据模型。

---

## 3. UI 技术路线

### 3.1 技术栈

节点编辑器使用：

- PySide6
- `QGraphicsView`
- `QGraphicsScene`
- `QGraphicsItem`
- `QGraphicsPathItem`
- `QGraphicsProxyWidget`，仅必要时使用

不使用普通 QWidget 硬堆节点画布。

### 3.2 推荐目录结构

```text
app/pages/motion_page.py                  # 如果已有运动页面，则复用该页面
app/widgets/node_editor/
  ├─ __init__.py
  ├─ node_editor_widget.py
  ├─ graph_view.py
  ├─ graph_scene.py
  ├─ node_item.py
  ├─ port_item.py
  ├─ edge_item.py
  ├─ models.py
  ├─ graph_serializer.py
  ├─ graph_validator.py
  ├─ property_panel.py
  ├─ node_library_panel.py
  ├─ execution_log_panel.py
  └─ execution_engine.py

services/
  └─ robot_realtime_state.py

custom_nodes/
  └─ example_node/
      ├─ node.json
      └─ README.md
```

---

## 4. 页面布局设计

### 4.1 三栏 + 底部日志布局

运动页面推荐四区布局：

```text
┌──────────────────────────────────────────────────────────────┐
│ 运动页面标题 / 工具栏 / 运行模式 DryRun Simulation RealRobot │
├───────────────┬───────────────────────────────┬──────────────┤
│ 节点库面板     │ GraphView 节点画布              │ 属性面板       │
│ 180~240 px    │ 可缩放 / 可平移 / 可连线          │ 280~360 px    │
├───────────────┴───────────────────────────────┴──────────────┤
│ 执行日志 / 校验结果 / TCP 指令日志 / CRI moving 状态变化       │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 节点库面板

左侧节点库按分组显示：

```text
运动
点位
IO
寄存器
逻辑
变量
自定义
```

用户点击或拖拽节点类型到画布中创建节点。

### 4.3 属性面板

右侧属性面板显示当前选中节点参数。

无选中节点：

```text
请选择一个节点
```

多选节点：

```text
已选择 N 个节点
```

### 4.4 底部日志面板

底部日志面板用于显示：

```text
图校验结果
节点执行顺序
发送的 TCP 指令
TCP 响应
CRI moving 状态变化
错误信息
执行耗时
```

初版可以是只读文本框，后续可以扩展为表格。

### 4.5 左侧运动抽屉共存规则

当前项目已有左侧运动抽屉。节点编辑器集成到运动页后必须检查遮挡问题。

初版建议：

1. 保留左侧运动抽屉。
2. 节点画布内容区域应预留抽屉宽度影响。
3. 如果抽屉展开会遮挡节点库或画布，优先允许用户手动收起抽屉。
4. 不要在初版强制隐藏抽屉。
5. 如果后续体验不好，再在 MainWindow 中根据当前页面状态自动收起或隐藏抽屉。

---

## 5. 节点分类

节点库按功能分区：

```text
运动节点
  - MoveJ
  - MoveL
  - MoveC
  - MoveCircle
  - Path

点位节点
  - Position / 点位变量

IO 节点
  - SetDO
  - ReadDI
  - SetAO
  - ReadAI

寄存器节点
  - SetRegister
  - ReadRegister

逻辑节点
  - If
  - For
  - While
  - Compare
  - And / Or / Not

变量节点
  - Number
  - Boolean
  - String
  - Pose

自定义节点
  - JSON 模板节点
  - Lua 模板节点，后续
  - Python 插件节点，后续高级模式
```

---

## 6. QGraphicsView 坐标规则

### 6.1 坐标统一原则

节点位置、端口位置、连线端点必须统一使用 `scene` 坐标。

禁止将以下坐标直接保存到 GraphModel：

```text
View 坐标
Widget 坐标
Screen 坐标
Item 局部坐标
```

保存到 JSON 的节点坐标必须是：

```text
scene_x
scene_y
```

### 6.2 常见坐标转换

拖拽创建节点时：

```python
scene_pos = graph_view.mapToScene(event.position().toPoint())
```

端口中心点计算时：

```python
port_scene_pos = port_item.mapToScene(port_item.boundingRect().center())
```

### 6.3 缩放和平移要求

`GraphView` 负责：

```text
鼠标滚轮缩放
中键或右键拖动画布
抗锯齿
深色背景
网格背景
```

缩放后连线不能偏移。

---

## 7. Node / Port / Edge 生命周期规则

### 7.1 PortItem

`PortItem` 应维护自身连接的边：

```python
self.connected_edges: list[EdgeItem]
```

### 7.2 EdgeItem

`EdgeItem` 保存：

```text
source_port
target_port
edge_type
```

连线端点从端口的 scene 坐标实时计算。

### 7.3 NodeItem 移动

`NodeItem` 移动时：

```text
遍历自身所有 PortItem
调用每个 PortItem 的 update_connected_edges()
```

### 7.4 删除规则

删除节点时：

```text
1. 先删除该节点所有端口关联的 EdgeItem
2. 再删除 NodeItem
3. 同步更新 GraphModel
```

删除端口时：

```text
1. 先删除该端口所有关联 EdgeItem
2. 再删除 PortItem
3. 同步更新 GraphModel
```

禁止留下悬空边。

---

## 8. GraphModel 与 UI 图元分离规则

### 8.1 核心原则

`GraphModel` 是唯一可序列化数据源。

`QGraphicsItem` 只是 `GraphModel` 的视图呈现。

禁止把以下对象写入 JSON：

```text
QGraphicsItem
QWidget
QObject
Signal
Slot
lambda
callback
thread
socket
timer
```

### 8.2 保存流程

```text
Scene 当前图元
→ 同步到 GraphModel
→ GraphSerializer 导出 JSON
```

### 8.3 加载流程

```text
读取 JSON
→ GraphSerializer 创建 GraphModel
→ GraphScene 根据 GraphModel 重建 NodeItem / PortItem / EdgeItem
```

---

## 9. 控制流线与数据流线

节点图必须区分两类连线：

```text
控制流线 flow：
  决定节点执行顺序。

数据流线 data：
  传递 pose / number / bool / string / register / io 等数据。
```

示例：

```text
Start.flow_out → MoveJ.flow_in
MoveJ.flow_out → SetDO.flow_in
SetDO.flow_out → End.flow_in

Position.pose_out → MoveJ.target_pose
Number.value_out → Wait.duration
Boolean.value_out → If.condition
```

端口类型不匹配时，UI 应拒绝连接。

端口类型建议：

```text
flow
pose
number
bool
string
io
register
path
any
```

---

## 10. 与焊接 / 写字页面的关系

本节点编排页面初期只做“运动编排”功能，不作为焊接和写字功能的强依赖。

### 10.1 写字功能

写字功能目前规划为：

```text
OpenCV 轮廓提取
→ 轨迹点转换
→ 走 CRI 或实时轨迹下发
```

因此写字功能暂时不需要依赖节点编排页面。

### 10.2 焊接功能

焊接功能目前规划为：

```text
OpenCV 轮廓提取
→ 轨迹/焊接工艺转换
→ 生成 Lua 脚本
→ 通过 HTTP 上传到控制器
→ 执行项目
```

因此焊接功能暂时不需要依赖节点编排页面。

### 10.3 后续扩展

后续如有需要，可以把焊接和写字流程封装成节点，例如：

```text
ImageInput
ContourExtract
PathGenerate
LuaGenerate
ProjectUpload
CriWritePath
```

但这不是当前 MVP 目标。

---

## 11. API 基础约定

### 11.1 TCP 主接口

主通信端口：

```text
TCP 9001
```

请求格式：

```json
{
  "id": 1,
  "ty": "请求类型",
  "db": {}
}
```

响应格式：

```json
{
  "id": 1,
  "ty": "请求类型",
  "db": {},
  "err": "错误信息"
}
```

如果响应里包含 `err` 字段，节点执行必须判定失败并进入错误流程。

### 11.2 UDP / CRI

CRI 用于实时状态：

```text
UDP 数据推送
状态数据1 bit7 = 运动中
关节位置单位 rad
TCP 位置单位 m
TCP 姿态单位 rad
```

项目内部 UI / 节点层统一使用：

```text
关节角 deg
TCP 位置 mm
TCP 姿态 deg
```

单位转换必须集中处理，不允许在各个节点里散落转换。

---

## 12. 运动接口 payload 规范

### 12.1 Robot/move 通用格式

`Robot/move` 的 `db` 必须是数组，哪怕只有一条运动指令：

```json
{
  "id": 1,
  "ty": "Robot/move",
  "db": [
    {
      "type": "movJ",
      "speed": 60,
      "acc": 150,
      "blend": 20,
      "targetPoint": {
        "jp": [10, 20, 30, 40, 50, 60],
        "cp": [100, 200, 300, 10, 20, 30],
        "rj": [10, 20, 30, 40, 50, 60],
        "ep": []
      }
    }
  ]
}
```

关键规则：

1. `db` 是运动指令列表。
2. 一次发送多条可以保证指令之间过渡。
3. 多次请求之间的过渡不能保证。
4. `targetPoint.jp` 和 `targetPoint.cp` 至少一个存在。
5. `jp` 优先级高于 `cp`。
6. `movC` 必须使用笛卡尔坐标点，不能使用关节角度点。
7. 如果不需要 `coor` / `tool`，不要传字段。
8. 严禁传入 `"coor": []` 或 `"tool": []`，已知会导致后端崩溃。

### 12.2 MoveJ 节点 payload

MoveJ 优先使用 Position.jp：

```json
{
  "type": "movJ",
  "speed": 60,
  "acc": 150,
  "blend": 0,
  "targetPoint": {
    "jp": [0, 0, 90, 0, 0, 0],
    "ep": []
  }
}
```

如果 Position 只有 cp，初版不自动 IK，GraphValidator 应校验失败。

### 12.3 MoveL 节点 payload

MoveL 使用 Position.cp：

```json
{
  "type": "movL",
  "speed": 100,
  "acc": 200,
  "blend": 0,
  "targetPoint": {
    "cp": [500, 0, 300, 180, 0, 90],
    "ep": []
  }
}
```

### 12.4 MoveC 节点 payload

MoveC 需要目标点和中间点，且必须使用 cp：

```json
{
  "type": "movC",
  "speed": 100,
  "acc": 200,
  "blend": 0,
  "targetPoint": {
    "cp": [600, 0, 300, 180, 0, 90],
    "ep": []
  },
  "middlePoint": {
    "cp": [550, 50, 300, 180, 0, 90]
  }
}
```

### 12.5 MoveCircle 节点 payload

MoveCircle 需要 `middlePoint` 和 `targetPoint`，可选 `circleNum`：

```json
{
  "type": "movCircle",
  "circleNum": 1,
  "speed": 100,
  "acc": 200,
  "blend": 0,
  "targetPoint": {
    "cp": [600, 0, 300, 180, 0, 90],
    "ep": []
  },
  "middlePoint": {
    "cp": [550, 50, 300, 180, 0, 90]
  }
}
```

### 12.6 Path 节点 payload 策略

Path 初版只支持 sequential：

```text
逐点发送 Robot/move
每个运动完成后再发下一个
每个运动完成仍然依赖 CRI moving
```

后续可扩展为一次性组合多个运动指令：

```json
{
  "ty": "Robot/move",
  "db": [
    { "type": "movJ", "...": "..." },
    { "type": "movL", "...": "..." },
    { "type": "movL", "...": "..." }
  ]
}
```

但初版不做 blend 优化。

---

## 13. Jog 与 moveTo 控制规则

### 13.1 Jog

Jog 是按住式：

按下：

```json
{
  "ty": "Robot/jog",
  "db": {
    "mode": 1,
    "speed": 0.1,
    "index": 1,
    "coorType": 0,
    "coorId": 0
  }
}
```

按住期间每 0.5 秒发送：

```json
{
  "ty": "Robot/jogHeartbeat"
}
```

松开：

```json
{
  "ty": "Robot/stopJog"
}
```

### 13.2 moveTo

`Robot/moveTo` 是按住保持型 RunTo 控制，不是点击一次执行到底。

按下预设位按钮：

```json
{
  "ty": "Robot/moveTo",
  "db": {
    "type": 0
  }
}
```

type 映射：

```text
0 = Home / 零点
1 = 安全位置
2 = 蜡烛位
3 = 打包位
4 = 关节规划到指定位置，需要 target
5 = 直线规划到指定位置，需要 target
6 = 程序恢复点
```

按住期间每 0.5 秒发送：

```json
{
  "ty": "Robot/moveToHeartbeat"
}
```

松开按钮必须立即发送：

```json
{
  "ty": "Robot/moveTo",
  "db": {
    "type": -1
  }
}
```

---

## 14. 速度接口规则

连接成功后默认速度设置为 70%。

速度滑条变化后同时设置：

```json
{
  "ty": "Robot/setManualMoveRate",
  "db": 70
}
```

```json
{
  "ty": "Robot/setAutoMoveRate",
  "db": 70
}
```

规则：

```text
手动模式使用 manualMoveRate
自动/远程运行使用 moveRate
远程模式实际使用自动运动倍率
```

节点执行时如果有节点自身 speed/acc，则使用节点参数；如果没有，则使用 Position optional；再没有使用系统默认。

---

## 15. IO 节点 payload 规范

### 15.1 SetDO

```json
{
  "ty": "IOManager/SetIOValue",
  "db": {
    "type": "DO",
    "port": 10,
    "value": 1
  }
}
```

### 15.2 ReadDI / ReadDO / ReadAI / ReadAO

```json
{
  "ty": "IOManager/GetIOValue",
  "db": [
    {
      "type": "DI",
      "port": 0
    }
  ]
}
```

响应：

```json
{
  "ty": "IOManager/GetIOValue",
  "db": [
    {
      "type": "DI",
      "port": 0,
      "value": 0
    }
  ]
}
```

IO 节点可以用 TCP response 判断完成。

---

## 16. 寄存器节点 payload 规范

### 16.1 SetRegister

```json
{
  "ty": "RegisterManager/SetRegisterValue",
  "db": {
    "address": 10000,
    "value": 0
  }
}
```

### 16.2 ReadRegister

```json
{
  "ty": "RegisterManager/GetRegisterValue",
  "db": [10000]
}
```

响应：

```json
{
  "ty": "RegisterManager/GetRegisterValue",
  "db": [
    {
      "address": 10000,
      "value": 0
    }
  ]
}
```

寄存器节点可以用 TCP response 判断完成。

---

## 17. Position 点位节点设计

### 17.1 设计目标

`Position` 节点用于保存机器人点位变量。它本身不执行运动，只输出位置数据，供 `MoveJ / MoveL / MoveC / MoveCircle / Path` 引用。

### 17.2 Position 数据内容

Position 节点同时支持：

```text
jp: 关节角，单位 deg
cp: TCP 位姿，位置单位 mm，姿态单位 deg
ep: 外部轴，初版可以为空 []
optional: 运动可选参数
```

### 17.3 新建 Position 默认行为

新建 Position 节点时，默认读取当前机器人位置：

```text
RobotRealtimeState.current_joints_deg()
RobotRealtimeState.current_tcp_pose_mm_deg()
RobotRealtimeState.current_external_axes()
```

如果阶段 7 的 `RobotRealtimeState` 尚未完成，则 Position 的“更新为当前位置”按钮可以先禁用，只支持手动输入。

不要在阶段 6 临时写一套独立 CRI 缓存，避免后续和 `RobotRealtimeState` 冲突。

### 17.4 Position 属性面板

点击 Position 节点后，右侧属性面板显示：

```text
点位名称
点位类型：
  - 关节位置
  - 笛卡尔位置
  - 同时保存 jp + cp

关节角：
  J1
  J2
  J3
  J4
  J5
  J6

笛卡尔位姿：
  X
  Y
  Z
  A
  B
  C

optional 参数：
  v 速度
  a 加速度
  r 弯曲半径 / blend radius
  tool_id 工具坐标系
  user_coord_id 用户坐标系

按钮：
  更新为当前位置
  手动输入
  应用
  取消
```

### 17.5 Position 数据结构

```json
{
  "id": "node_pos_001",
  "type": "Position",
  "title": "点位1",
  "data": {
    "name": "P1",
    "configured": true,
    "position_type": "both",
    "jp": [0, 0, 90, 0, 0, 0],
    "cp": {
      "x": 500.0,
      "y": 0.0,
      "z": 300.0,
      "a": 180.0,
      "b": 0.0,
      "c": 90.0
    },
    "ep": [],
    "optional": {
      "v": 100,
      "a": 50,
      "r": 0,
      "tool_id": 0,
      "user_coord_id": 0
    },
    "source": "current_robot_pose",
    "updated_at": "2026-05-10 17:30:00"
  }
}
```

### 17.6 optional 参数继承规则

运动参数采用三层优先级：

```text
1. 运动节点自身 optional，优先级最高
2. Position 节点 optional，优先级次之
3. 系统默认运动参数，优先级最低
```

示例：

```text
Position P1:
  v = 100
  a = 50
  r = 0

MoveL:
  v = 200
  r = 5

最终：
  v = 200，来自 MoveL
  a = 50，来自 Position
  r = 5，来自 MoveL
```

---

## 18. RobotRealtimeState 实时状态缓存

### 18.1 设计目标

新增统一实时状态缓存：

```text
services/robot_realtime_state.py
```

`CriService` 接收到 CRI frame 后更新该状态。UI 和执行引擎只读取状态接口，不直接解析 UDP 字节流。

### 18.2 建议接口

```python
class RobotRealtimeState(QObject):
    state_changed = Signal()

    def update_from_cri_frame(self, frame: dict): ...
    def is_valid(self) -> bool: ...
    def is_moving(self) -> bool: ...
    def current_joints_deg(self) -> list[float]: ...
    def current_tcp_pose_mm_deg(self) -> tuple[float, float, float, float, float, float]: ...
    def current_external_axes(self) -> list[float]: ...
```

### 18.3 CRI moving 来源

CRI 状态数据1中：

```text
bit7 = 运动中
```

RobotRealtimeState 应统一解析该字段为：

```python
is_moving() -> bool
```

并记录最近一次状态变化时间。

---

## 19. 机器人运动完成判断

### 19.1 非阻塞原则

所有运动指令接口收到 TCP response 只代表控制器接收成功，不代表运动完成。

运动完成必须依赖 CRI moving。

### 19.2 状态机

运动节点发送指令后：

```text
1. send_command
2. wait_motion_start
3. wait_motion_finish
4. done
```

判断过程：

```text
wait_motion_start:
  等待 moving false → true

wait_motion_finish:
  等待 moving true → false
```

### 19.3 短运动兜底

如果 `wait_motion_start_timeout_ms` 内没有检测到 moving=true：

```text
1. 检查当前位置是否接近目标；
2. 如果接近目标，视为完成；
3. 如果不接近，判定启动失败或超时。
```

### 19.4 默认超时

```text
wait_motion_start_timeout_ms = 1000
wait_motion_finish_timeout_ms = 60000
```

后续可以根据距离和速度估算 finish 超时。

### 19.5 禁止阻塞

禁止：

```python
time.sleep()
while realtime_state.is_moving():
    ...
```

必须使用：

```text
QTimer
状态机
Signal/Slot
```

保证 UI 不阻塞。

---

## 20. Graph 数据模型

### 20.1 JSON 顶层结构

```json
{
  "graph_version": "1.0.0",
  "app_version": "2.0.0",
  "created_at": "2026-05-10 17:30:00",
  "updated_at": "2026-05-10 18:00:00",
  "nodes": [],
  "edges": []
}
```

### 20.2 版本迁移

节点图必须带版本号。

加载旧版本 graph 时：

```text
1. 不允许直接崩溃。
2. 必须尝试 migration。
3. 缺失字段使用默认值。
4. 无法迁移时给出清晰错误提示。
```

### 20.3 节点引用规则

节点之间的引用必须使用稳定 `node_id`。

禁止使用显示名称作为引用依据。

正确：

```json
{
  "target_pose_ref": "node_pos_001"
}
```

不推荐：

```json
{
  "target_pose_ref": "P1"
}
```

---

## 21. GraphValidator 图校验器

### 21.1 设计目标

在 DryRun 或真实执行前，必须先校验节点图。

建议新增：

```text
app/widgets/node_editor/graph_validator.py
```

### 21.2 校验内容

GraphValidator 至少检查：

```text
1. 节点 ID 唯一。
2. Edge 引用的 source/target 节点存在。
3. Edge 引用的端口存在。
4. 端口类型匹配。
5. 必须存在 Start 节点。
6. 必须存在 End 节点。
7. Start 到 End 必须存在 flow 路径。
8. 必填输入端口必须连接。
9. Position 节点如果被运动节点引用，必须 configured=true。
10. MoveJ 必须有合法 jp。
11. MoveL 必须有合法 cp。
12. MoveC / MoveCircle 必须有合法 middlePoint 和 targetPoint 的 cp。
13. 禁止传空数组 coor/tool。
14. 初版禁止循环，后续 For/While 阶段再开放受控循环。
```

### 21.3 输出形式

```python
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
```

校验失败时：

```text
不得执行图
高亮相关节点
在底部日志面板显示错误
```

---

## 22. GraphExecutionEngine 设计

### 22.1 执行引擎接口

```python
class GraphExecutionEngine(QObject):
    node_started = Signal(str)
    node_finished = Signal(str)
    node_failed = Signal(str, str)
    graph_finished = Signal()
    graph_stopped = Signal()
    log_emitted = Signal(dict)

    def run_dry(self, graph: GraphModel): ...
    def run_online(self, graph: GraphModel, mode: str): ...
    def stop(self): ...
    def pause(self): ...
    def resume(self): ...
```

### 22.2 执行模式

支持三种执行模式：

```text
DryRun:
  不发送真实机器人指令，只打印将要执行的动作。

Simulation:
  允许发送到仿真机器人。

RealRobot:
  真实机器人运行，必须二次确认。
```

### 22.3 RealRobot 二次确认

RealRobot 模式点击运行时，必须弹窗显示：

```text
当前图名称
即将执行的运动节点数量
是否已确认机器人工作空间安全
是否已确认急停可用
是否已确认周围无人
是否确认当前处于实机运行
```

用户确认后才能执行。

### 22.4 If / For / While 执行模型

逻辑节点不能只靠普通 DAG 拓扑排序。

必须使用：

```text
执行游标
控制流分支
循环上下文
```

`If` 节点端口：

```text
flow_in
condition: bool
true_flow
false_flow
```

初版先支持：

```text
If
固定次数 For
```

`While` 后置。

---

## 23. 执行停止 / 暂停 / 异常清理规范

### 23.1 Stop 行为

用户点击停止执行时必须：

```text
1. 设置 engine 状态为 stopping/stopped。
2. 停止当前运动等待定时器。
3. 停止所有心跳定时器。
4. 如果当前正在运动，发送 Robot/stopMove。
5. 如果当前是 jog，发送 Robot/stopJog。
6. 如果当前是 moveTo，发送 Robot/moveTo {"type": -1}。
7. 当前节点标记 stopped。
8. 后续节点不再执行。
9. 发出 graph_stopped 信号。
10. 记录停止日志。
```

### 23.2 Pause 行为

初版暂停策略：

```text
暂停只暂停后续节点推进。
如果当前机器人正在运动，优先发送 Robot/pause。
恢复时发送 Robot/resume。
```

如果实际控制器对 pause/resume 的行为不稳定，先在 Simulation/DryRun 中实现 UI 状态，RealRobot 后置。

### 23.3 异常行为

任何节点失败时：

```text
1. 默认停止整个图。
2. 高亮失败节点。
3. 记录错误日志。
4. 保留 GraphExecutionContext。
5. 不自动继续执行后续节点。
```

后续高级模式可支持 `continue_on_error`。

---

## 24. 执行日志格式规范

每条日志使用结构化 dict：

```json
{
  "timestamp": "2026-05-10 18:00:00.123",
  "level": "INFO",
  "event": "node_started",
  "graph_id": "graph_001",
  "node_id": "node_movej_001",
  "node_title": "MoveJ 到 P1",
  "node_type": "MoveJ",
  "message": "开始执行 MoveJ",
  "payload": {},
  "response": {},
  "duration_ms": 0
}
```

### 24.1 level

```text
DEBUG
INFO
WARNING
ERROR
```

### 24.2 event

建议事件类型：

```text
graph_started
graph_finished
graph_stopped
graph_failed

validation_started
validation_failed
validation_passed

node_started
node_finished
node_failed
node_skipped

tcp_send
tcp_response
tcp_error

cri_moving_changed
motion_wait_start
motion_wait_finish
motion_timeout

user_stop
user_pause
user_resume
```

### 24.3 日志面板最低要求

初版日志面板至少显示：

```text
时间
等级
节点名称
事件
消息
```

后续可增加展开查看 payload/response。

---

## 25. 自定义节点机制

### 25.1 初版策略

初版自定义节点只支持安全的 JSON 模板节点。

暂不允许：

```text
执行任意 Python
直接操作 socket
直接操作线程
删除文件
绕过 GraphExecutionEngine
```

### 25.2 目录结构

```text
custom_nodes/
  example_node/
    node.json
    README.md
```

### 25.3 后续扩展

后续可扩展：

```text
Lua 模板节点
Python 插件节点
节点包导入导出
节点模板市场/本地库
```

但必须在开发者模式下启用。

---

## 26. 分阶段开发计划

## 阶段 0：准备与文档同步

### 目标

确认当前项目结构，并把本计划正式纳入项目规划。

### 任务

1. 检查项目根目录是否存在：
   - `plan.md`
   - 本计划文档
   - `CLAUDE.md`
2. 如果 `plan.md` 没有提到“运动节点编排功能”，则补充。
3. 明确当前项目已经有运动标签页，不新增重复顶层标签。
4. 不修改源码。

### 验收标准

```text
1. plan.md 已记录该新功能方向。
2. 本计划文档存在。
3. 没有修改源码。
```

---

## 阶段 1：在现有运动页面加入节点编辑器占位区

### 目标

先只在现有运动页面内加入节点编辑器占位区域，不实现节点编辑器逻辑。

### 任务

1. 读取现有运动页面源码。
2. 不新增重复标签页。
3. 在现有运动页面内加入占位内容：

```text
运动节点编排区域
后续用于节点连线式机器人运动流程编排
```

4. 确认现有左侧运动抽屉不影响页面切换。

### 验收标准

```text
1. 点击现有“运动”标签页后能看到节点编辑器占位区。
2. 不新增重复运动标签。
3. 不影响主页、焊接、写字等页面。
```

---

## 阶段 2：创建 Node Editor 基础目录和空白画布

### 目标

显示空白节点画布，支持缩放和平移。

### 新增目录

```text
app/widgets/node_editor/
```

### 新增文件

```text
app/widgets/node_editor/__init__.py
app/widgets/node_editor/node_editor_widget.py
app/widgets/node_editor/graph_view.py
app/widgets/node_editor/graph_scene.py
```

### 技术要求

`GraphView` 支持：

```text
鼠标滚轮缩放
中键或右键拖动画布
抗锯齿
深色背景
简单网格背景
```

### 验收标准

```text
1. 运动页面显示深色画布。
2. 鼠标滚轮可以缩放。
3. 鼠标拖拽可以平移。
```

---

## 阶段 2.5：确定正式三栏布局

### 目标

避免后续从临时按钮堆叠重构成正式界面。

### 任务

在运动页面中确定：

```text
左侧节点库
中间画布
右侧属性面板
底部日志区域
```

如果空间不足，底部日志可以先做折叠或占位。

### 验收标准

```text
1. 页面有明确的节点库区域。
2. 页面有明确的属性面板区域。
3. 页面有执行日志预留区域。
4. 画布仍可正常缩放和平移。
```

---

## 阶段 3：实现 NodeItem 和 PortItem

### 目标

能在画布上创建和拖动节点。

### 新增文件

```text
app/widgets/node_editor/node_item.py
app/widgets/node_editor/port_item.py
```

### 初始节点

```text
Start
End
Position
MoveJ
MoveL
```

### 验收标准

```text
1. 能添加节点。
2. 节点能拖动。
3. 节点显示输入/输出端口。
4. 节点位置使用 scene 坐标。
```

---

## 阶段 4：实现 EdgeItem 与端口连接

### 目标

实现节点连线。

### 新增文件

```text
app/widgets/node_editor/edge_item.py
```

### 要求

```text
1. 从输出端口拖到输入端口创建连线。
2. 连线使用贝塞尔曲线。
3. 节点移动后连线自动更新。
4. 区分 flow 线和 data 线。
5. 类型不匹配禁止连接。
6. 删除节点时删除关联连线。
```

### 验收标准

```text
1. 能连接合法端口。
2. 非法端口连接被拒绝。
3. 节点移动后连线更新。
4. 删除节点后没有悬空线。
```

---

## 阶段 5：实现 GraphModel 与保存加载 JSON

### 新增文件

```text
app/widgets/node_editor/models.py
app/widgets/node_editor/graph_serializer.py
```

### 要求

```text
1. GraphModel 与 QGraphicsItem 分离。
2. JSON 只保存纯数据。
3. 保存 scene 坐标。
4. 加载后根据 GraphModel 重建 Scene。
```

### 验收标准

```text
1. 节点和连线可以保存 JSON。
2. 可以重新加载。
3. 节点位置、端口、连线恢复。
```

---

## 阶段 5.5：实现 GraphValidator

### 新增文件

```text
app/widgets/node_editor/graph_validator.py
```

### 验收标准

```text
1. 能检查 Start/End。
2. 能检查端口类型。
3. 能检查必填输入。
4. 能检查 Position configured。
5. 校验失败时不允许执行。
```

---

## 阶段 6：实现 Position 节点属性面板

### 新增文件

```text
app/widgets/node_editor/property_panel.py
```

### 验收标准

```text
1. 点击 Position 节点显示属性面板。
2. 可以手动修改 jp/cp/optional。
3. 可以保存到 Graph JSON。
4. 重新加载后数据不丢。
5. 如果 RobotRealtimeState 未完成，“更新为当前位置”按钮可以暂时禁用。
```

---

## 阶段 7：增加 RobotRealtimeState

### 新增文件

```text
services/robot_realtime_state.py
```

### main.py 修改

在 `_on_cri_frame(frame)` 中：

```text
先更新 RobotRealtimeState
再更新 UI 显示
```

### 验收标准

```text
1. CRI 数据到达后 RobotRealtimeState 更新。
2. Position 节点可以读取当前位置。
3. 不影响原有抽屉显示。
```

---

## 阶段 8：实现最小 DryRun 执行引擎

### 新增文件

```text
app/widgets/node_editor/execution_engine.py
```

### 支持节点

```text
Start
End
Position
MoveJ
MoveL
Wait
SetDO
```

### 验收标准

```text
1. Start → MoveJ → MoveL → End 可以 DryRun。
2. 节点执行时高亮。
3. 日志能看到执行顺序。
4. 执行前会调用 GraphValidator。
```

---

## 阶段 9：实现在线执行 MoveJ / MoveL

### 目标

接入真实机器人在线执行，但只做 MoveJ / MoveL。

### 验收标准

```text
1. MoveJ 可以发送。
2. MoveL 可以发送。
3. 运动完成靠 CRI moving。
4. UI 不阻塞。
5. 停止按钮能停止执行。
6. 超时后能失败退出。
```

---

## 阶段 10：增加 IO / 寄存器 / Wait 节点

### 节点

```text
Wait
SetDO
ReadDI
SetRegister
ReadRegister
Compare
```

### 验收标准

```text
1. 可以串联 MoveJ → SetDO → Wait → MoveL。
2. 寄存器节点能读写。
3. Compare 可输出 bool 给后续逻辑节点预留。
```

---

## 阶段 11：增加 If 节点 ✅

### 原则

不能只靠普通 DAG 拓扑排序。

必须引入：

```text
执行游标
分支选择
```

### 实现 (2026-05-11)

重构了 ExecutionEngine 的执行模型，从**预计算线性路径**改为**运行时图遍历**：

| 旧模型 | 新模型 |
|--------|--------|
| `_path: list[str]` + `_cursor: int` | `_current_node_id: str \| None` |
| `_build_path()` 预计算单一路径 | 每步通过 `_flow_target()` 查询 flow 边 |
| `_flow_map` 偏好 false/done 分支 | 移除 `_flow_map`，If/For/While 在运行时动态选择分支 |
| `_advance_later()` 递增 cursor | `_advance_to(next_id)` 设置下一节点 |
| `_index_of()` 在 path 中查找 | 直接赋值 `_current_node_id` |

核心修改：
- **`execution_engine.py`**: 全面重构执行模型，`_build_maps()` 简化为只构建数据源映射
- **`models.py`**: 补充了缺失的 `While` 节点 spec
- If/For/While 的分支跳转不再依赖 pre-computed path
- 循环体返回通过 `_return_stack` + `_current_node_id` 回跳
- 分支合流通过每条分支终端节点的 flow_out 自然汇聚到共同后继

### 验收标准

```text
1. If 根据 bool 走 true 或 false。                                    ✅
2. 未走分支不会执行。                                                  ✅
3. 执行日志能显示分支选择。                                            ✅
4. For/While 循环在新模型下继续正常工作。                               ✅
5. 嵌套 If-in-For 正确执行。                                           ✅
6. 分支合流 (true→MoveJ→End, false→MoveL→End) 正确。                   ✅
7. 分支未连接时报错（如 If 条件为 False 但 false 端口未连线）。          ✅
```

---

## 阶段 12：增加 Path / MoveC / MoveCircle

### Path 初版

只支持：

```text
sequential
```

即逐点执行，每个点完成后再下一个点。

### 验收标准

```text
1. MoveC 可引用两个 Position。
2. MoveCircle 可引用三个 Position。
3. Path 可按顺序执行多个 Position。
4. 每个运动仍然用 CRI moving 判断完成。
```

---

## 阶段 13：增加自定义节点基础机制

### 目标

初版只做 JSON 模板节点。

### 验收标准

```text
1. 可以扫描 custom_nodes。
2. 可以加载 JSON 定义的自定义节点。
3. 可以显示在节点库。
4. 不允许执行危险代码。
```

---

## 阶段 14：完善测试、日志、错误恢复

### 内容

```text
执行日志
错误恢复
停止执行
保存执行记录
节点失败高亮
```

### 验收标准

```text
1. 出错能看到哪个节点失败。
2. 能停止执行。
3. 能查看执行日志。
4. plan.md 和本计划文档记录当前完成状态。
```

---

## 27. 手工测试用例清单

### 27.1 UI 画布测试

```text
1. 打开运动页面，能看到节点编辑器区域。
2. 鼠标滚轮缩放画布。
3. 鼠标拖动画布平移。
4. 添加 Start / End / Position / MoveJ / MoveL 节点。
5. 拖动节点，节点位置正常。
6. 删除节点，关联线同步删除。
```

### 27.2 连线测试

```text
1. Start.flow_out → MoveJ.flow_in 允许。
2. Position.pose_out → MoveJ.target_pose 允许。
3. Position.pose_out → MoveJ.flow_in 拒绝。
4. Start.flow_out → MoveJ.target_pose 拒绝。
5. 节点移动后连线端点跟随。
```

### 27.3 保存加载测试

```text
1. 创建 3 个节点 2 条线。
2. 保存 JSON。
3. 清空画布。
4. 加载 JSON。
5. 节点位置恢复。
6. 连线恢复。
7. Position 数据恢复。
```

### 27.4 GraphValidator 测试

```text
1. 没有 Start，校验失败。
2. 没有 End，校验失败。
3. MoveJ 没有 Position，校验失败。
4. MoveJ 的 Position 没有 jp，校验失败。
5. MoveL 的 Position 没有 cp，校验失败。
6. 非法端口连接，校验失败。
7. Position configured=false，校验失败。
```

### 27.5 DryRun 测试

```text
1. Start → MoveJ → End 可以 DryRun。
2. Start → MoveJ → SetDO → Wait → MoveL → End 可以 DryRun。
3. DryRun 不发送 TCP 指令。
4. DryRun 日志显示节点顺序。
```

### 27.6 在线运动测试

```text
1. Simulation 模式下执行 MoveJ。
2. Simulation 模式下执行 MoveL。
3. TCP response 后不立即判定完成。
4. 等待 CRI moving false→true→false。
5. 短运动时能通过位置接近兜底完成。
6. 超时后节点失败。
7. 点击停止时发送 Robot/stopMove。
```

### 27.7 IO / 寄存器测试

```text
1. SetDO 发送 IOManager/SetIOValue。
2. ReadDI 发送 IOManager/GetIOValue。
3. SetRegister 发送 RegisterManager/SetRegisterValue。
4. ReadRegister 发送 RegisterManager/GetRegisterValue。
5. IO/寄存器节点用 TCP response 判断完成。
```

### 27.8 日志测试

```text
1. 每个节点开始有 node_started 日志。
2. 每个节点完成有 node_finished 日志。
3. TCP 指令有 tcp_send 日志。
4. TCP 响应有 tcp_response 日志。
5. CRI moving 变化有 cri_moving_changed 日志。
6. 错误有 node_failed 日志。
```

---

## 28. Claude Code 执行规则

不要一次性让 Claude Code 完成全部阶段。

推荐指令格式：

```text
请读取 CLAUDE.md、plan.md 和本计划文档。
现在只执行阶段 N。
只完成当前阶段目标，不要提前开发后续阶段。
完成后停下来，说明：
1. 修改了哪些文件；
2. 如何测试；
3. 是否更新了 plan.md；
4. 下一阶段建议是什么。
```

### 第一次建议只执行阶段 0 和阶段 1

```text
请现在只执行阶段 0 和阶段 1：
1. 同步 plan.md；
2. 在现有运动页面中加入节点编辑器占位区；
3. 不新增重复运动标签；
4. 不实现节点画布；
5. 完成后停下来。
```

---

## 29. 开发高风险点与规避规则

### 29.1 UI 和数据模型混合

风险：

```text
QGraphicsItem 和 GraphModel 混在一起，导致保存加载困难。
```

规避：

```text
GraphModel 是唯一数据源。
QGraphicsItem 只是视图。
```

### 29.2 坐标系统混乱

风险：

```text
缩放后连线偏移。
加载后节点位置不对。
拖线落点不准。
```

规避：

```text
所有可保存坐标统一使用 scene 坐标。
```

### 29.3 连线生命周期错误

风险：

```text
节点删除后线还在。
端口删除后 Edge 引用失效。
```

规避：

```text
PortItem 维护 connected_edges。
删除节点前先删除关联 Edge。
```

### 29.4 执行引擎阻塞 UI

风险：

```text
while + sleep 等待运动完成导致界面卡死。
```

规避：

```text
使用 QTimer 状态机，不得阻塞事件循环。
```

### 29.5 CRI moving 判断不稳定

风险：

```text
短运动检测不到 moving=true。
机器人已经到目标但执行引擎一直等。
```

规避：

```text
false→true→false + 短运动兜底 + 超时。
```

### 29.6 自定义节点安全风险

风险：

```text
用户自定义节点执行任意 Python，可能误删文件或直接操作 socket。
```

规避：

```text
初版只允许 JSON 模板节点。
Python 插件节点后置，并放在开发者模式。
```

### 29.7 Robot/move payload 错误

风险：

```text
db 传成对象而不是数组。
movC 误传 jp。
coor/tool 传空数组导致后端崩溃。
```

规避：

```text
Robot/move 的 db 必须是数组。
movC / movCircle 必须使用 cp。
不需要 coor/tool 时不传字段。
GraphValidator 必须检查 payload。
```

---

## 30. 节点数据模型与交互规则 (2026-05-11)

### 30.1 全局变量系统

变量不在画布上存储，而是在 `GraphData.variables` 中统一管理：

```python
@dataclass
class VarDef:
    var_id: str    # 自动生成 UUID 前8位
    name: str      # 变量名
    var_type: str  # "int", "float", "bool", "string", "array"
    value: str     # 当前值 (JSON 兼容字符串)
```

规则：
- 创建变量时生成唯一 `var_id`
- GetVar/SetVar 节点通过 `var_id` 引用变量，非 `var_name`
- 修改 GetVar 属性面板的值 → 同步更新 `GraphData.variables[var_id].value` + 所有引用同 `var_id` 的 GetVar 节点
- 再次拖入同一变量不会创建新变量定义，复用已有 `var_id`
- 保存 JSON 必须保存 `variables` 数组
- 加载 JSON 必须先加载 variables，再 nodes，再 edges
- 如果加载时 `var_id` 对应的变量不存在，节点显示灰色，GraphValidator 报错

### 30.2 flow 主线连接规则

| 端口类型 | 方向 | 最多连接数 |
|----------|------|------------|
| flow | input | 1 |
| flow | output | 1 |
| data | input | 1 |
| data | output | 无限 |

- `_add_edge` 创建边时检查：flow 输出已有连接→拒绝；flow/数据输入已有连接→拒绝
- GraphValidator 检查 flow 输出唯一性，重复时报错
- If/For/While 逻辑节点以后单独处理

### 30.3 拖节点插入主线

- 拖拽带有 flow_in + flow_out 的节点到现有 flow Edge 上 → 自动插入
- 删除旧边，创建 source→新节点、新节点→target 两条新边
- Start/End/Position/Int/Float/Bool/String/Array 不允许插入
- If/For/While 暂不做自动插入

### 30.4 Wait 单位

- Wait 字段统一用 `duration_ms`，单位毫秒
- UI 显示 `ms`
- 旧 JSON 的 `duration`(秒)/`duration_sec`(秒) 自动 ×1000 迁移为 `duration_ms`
- 所有涉及时间的字段统一后缀 `_ms`

### 30.5 Position 显示名

- Position 节点创建时使用用户输入的名称作为 `title`
- 属性面板修改 `name` → 同步更新 NodeItem.title
- 保存 JSON 后重新加载，名称不变

### 30.6 变量端口统一

- 所有变量引用节点（GetVar/SetVar）输出端口统一为 `value`
- GraphValidator 和 Serializer 使用 `value`
- 加载旧 JSON 时 `out`/`value_out` 自动迁移为 `value`

### 30.7 动态节点加载

- GetVar/SetVar 的端口定义存储在 `node_data._ports` 中
- 加载 JSON 时检测 `_ports` 字段，使用 `override_spec` 重建动态端口
- 如果 `_ports` 不存在或 var_id 无效，节点显示为缺失

## 30.9 全部节点执行逻辑 (2026-05-11)

### 数据节点 (递归求值)

所有数据节点通过 `_eval_data(node_id)` 递归求值，结果缓存避免重复计算。

| 类别 | 节点 | 计算逻辑 |
|------|------|----------|
| 常量 | Int, Float, Bool, String | 返回 data["value"] |
| 变量 | GetVar | 返回 VarDef.value |
| 数学 | Add/Sub/Mul/Div/Pow/Mod | a op b |
| | Square/Sqrt/Abs/Neg | unary math |
| | Sin/Cos/Tan | 三角函数(输入度) |
| | Deg2Rad/Rad2Deg | 单位换算 |
| 比较 | Gt/Lt/Ge/Le/Eq | a op b → bool |
| 逻辑 | And/Or/Not/Xor | 布尔运算 |
| 字符串 | StrConcat/Split/Find/Replace/Len | 字符串操作 |
| | Num2Str/Bool2Str | 类型转换 |
| 数组 | ArrayGet | arr[index] |
| | ArrayLen | len(arr) |
| 点位 | BreakPosition | pose→jp+cp, 右键拆分 |
| | MakePosition | jp+cp→pose |
| For | For | 输出当前 _for_index |

### 控制流节点

| 节点 | 行为 |
|------|------|
| **If** | condition=True→走true分支, False→走false分支 |
| **For** | start/end/step, 循环执行body, 结束走done. 输出index供ArrayGet |
| **While** | condition=True→循环body, False→走done |

### 循环体返回

For/While 的 body 执行完后，通过 `_return_stack` 自动跳回循环节点继续迭代。body 分支内的节点不需要手动连回 For。

### 交互增强

- **端口标签**：所有端口显示名称(boddy/done/condition/start/end/step等)，非类型名
- **Flow 端口**：三角▶形状，非圆形
- **拖线创建常量**：从输入端口拖到空白→自动创建 Int/Bool/String 常量并连线
- **右键拆分点位**：BreakPosition/MakePosition 的 jp/cp 端口右键→拆分/合并为 J1~J6 或 XYZABC
- **属性即时应用**：所有属性面板改值即生效，无"应用"按钮

## 30.10 当前优先级建议

真正开发时优先做到：

```text
阶段 0
阶段 1
阶段 2
阶段 2.5
阶段 3
阶段 4
阶段 5
阶段 5.5
阶段 6
阶段 7
```

完成阶段 7 后，项目将具备：

```text
现有运动页面内的节点编辑器入口
节点画布
正式三栏布局
节点拖拽
节点连线
保存加载
GraphValidator
Position 点位节点
CRI 实时状态缓存
```

此时再进入真实执行引擎阶段，会更安全、更容易调试。

---

## 31. 评分目标

本计划的目标是达到 9.8 分工程计划标准：

```text
1. 能指导 AI 分阶段实现。
2. 每阶段可独立测试。
3. 明确 UI 架构。
4. 明确 Graph 数据模型。
5. 明确机器人 API payload。
6. 明确 CRI moving 完成判断。
7. 明确停止/异常清理。
8. 明确高风险开发坑。
9. 明确手工测试用例。
```

## 32. 已实现功能详情 (阶段 0-6)

### 32.1 节点清单 (54 种)

| 分类 | 颜色 | 节点 | 端口 |
|------|------|------|------|
| **基础** | `#607D8B` | Start | flow(output) |
| | | End | flow(input) |
| **运动** | `#1976D2` | MoveJ, MoveL, MoveC, MoveCircle, MovePath | flow(in/out) + pose 输入(连 Position) |
| **点位** | `#F57C00` | Position | flow(in/out) + pose(output), 存 jp+cp+optional |
| **运算** | `#00897B` | Add, Sub, Mul, Div, Pow, Mod | a(number in) + b(number in) → result(number out) |
| | | Square, Sqrt, Abs, Neg | a(number in) → result(number out) |
| | | Sin, Cos, Tan | a(number in) → result(number out) |
| | | Deg2Rad, Rad2Deg | 单位换算 |
| | | MatMulL, MatMulR | a(pose in) + b(pose in) → result(pose out) |
| | | Int2Float, Float2Int | 类型转换 |
| **逻辑** | `#7B1FA2` | If, For, While | 控制流分支/循环 |
| | | And, Or, Not, Xor | bool 逻辑运算 |
| | | Gt, Lt, Eq, Ge, Le | 数值/任意值比较 |
| **字符串** | `#00ACC1` | StrConcat | a(string) + b(string) → result(string) |
| | | StrSplit | str + sep → result(any) |
| | | StrFind, StrReplace, StrLen | 查找/替换/长度 |
| | | Num2Str, Bool2Str | 类型转字符串 |
| **IO** | `#FBC02D` | SetDO, ReadDI, SetAO, ReadAI | IO 读写 |
| **寄存器** | `#C2185B` | SetRegister, ReadRegister | 寄存器读写 |
| **变量** | `#388E3C` | Int, Float, Bool, String, Array | 纯数据输出(无 flow) |

### 32.2 交互特性

| 功能 | 说明 |
|------|------|
| **双击添加节点** | 节点库双击 → 画布中心创建 |
| **拖拽添加节点** | 节点库拖拽到画布 → 落点位置创建 |
| **双击删除连线** | 双击贝塞尔曲线即删除 |
| **悬停高亮** | 连线悬停变粗 + 手型光标 |
| **双击重命名** | 双击节点标题栏可改名 |
| **Delete/Backspace** | 删除选中节点(含关联连线) |
| **16px 端口吸附** | 拖线松手时自动吸附附近合法端口 |

### 32.3 Position 属性面板

选中 Position 节点后右侧面板显示：

```
┌─────────────────────────────┐
│ 名称: [P1___________]       │
├─────────────────────────────┤
│ 关节角 jp (deg)             │
│   J1: [0.00]  J2: [0.00]   │
│   J3: [90.00] J4: [0.00]   │
│   J5: [0.00]  J6: [0.00]   │
├─────────────────────────────┤
│ 笛卡尔位姿 cp (mm / deg)    │
│   X: [500.0]  Y: [0.0]     │
│   Z: [300.0]                │
│   A: [180.00] B: [0.00]    │
│   C: [90.00]                │
├─────────────────────────────┤
│ 默认运动参数 optional       │
│   速度: [200] mm/s          │
│   加速度: [500] mm/s²       │
│   过渡半径(绝对): [0.0] mm  │
│   过渡半径(相对): [0.0] %   │
├─────────────────────────────┤
│ [更新为当前位置] (阶段7启用) │
│ [应用]                      │
└─────────────────────────────┘
```

数据与节点一起保存到 JSON，加载后完整恢复。

### 32.4 运动参数优先级

```
Move 节点自身 speed/acc/blend  (最高)
 └→ Position.optional          (次之)
     └→ 系统默认               (最低)
```

### 32.5 图校验规则

| 规则 | 级别 |
|------|------|
| 必须有 Start 节点 | ❌ Error |
| 必须有 End 节点 | ❌ Error |
| 节点 ID 唯一 | ❌ Error |
| 边引用源/目标存在 | ❌ Error |
| 端口类型匹配 (flow→flow, pose→pose...) | ❌ Error |
| Start→End flow 路径连通 | ❌ Error |
| 运动节点 pose 输入必须连 Position | ❌ Error |
| 非 Start/End 的 flow 输入未连接 | ⚠ Warning |

### 32.6 中英文双语

- 菜单栏 `设置 → 语言 → 中文/English` 切换
- QSettings 持久化语言选择，启动时自动加载
- 覆盖：菜单栏、标签页、状态栏、节点编辑器全部文本
- 登录页不翻译
- 翻译引擎：`app/i18n.py`，I18nManager + Signal 驱动 UI 刷新

### 32.7 工程名与保存

- 顶栏：`工程: [名称] [校验] [保存] [加载]`
- 保存：直接写入 `projects/<名称>.json`，无弹窗
- 加载：文件对话框，默认打开 `projects/` 目录
- Ctrl+S / Ctrl+O 快捷键
- JSON 含 graph_version + updated_at + nodes[].data
