# Codroid 机械臂 UI 控制系统 — 实施计划

## 执行规则 (最高优先级)

1. Claude Code **每次只能实现一个 Part**。
2. 每个 Part 完成后 **必须停止**，不允许主动进入下一 Part。
3. **不允许自动连接真实机器人**。
4. **不允许自动发送任何运动指令**。
5. 所有实体机器人测试由用户通过 UI 手动点击完成。
6. 只有用户明确回复 **"该 Part 测试通过，继续下一 Part"**，才允许实现下一 Part。
7. 违反以上任何一条即为实现错误。

### Agent 输出格式要求

每个 Part 完成后，Claude Code **必须**输出以下内容，缺一不可：

1. **本 Part 修改了哪些文件** — 完整路径列表
2. **本 Part 没有修改哪些禁止文件** — 明确确认未触碰禁区
3. **如何运行** — 用户需要执行的命令
4. **人工验收步骤** — 用户操作和预期结果
5. **下一 Part 不得自动开始** — 明确声明 "等待用户确认后才能继续下一 Part"

---

## 技术选型

| 项目 | 选择 | 原因 |
|------|------|------|
| UI 框架 | PySide6 | 跨平台(Linux/Windows), Qt3D/OpenGL, 原生网络, QThread |
| 3D 渲染 | PyOpenGL + QOpenGLWidget | 轻量, 与 Qt 无缝集成 |
| 网络 | QTcpSocket / QUdpSocket | PySide6 内置, 异步事件驱动 |
| 协议解析 | JSON (TCP 9001/9002) + CRI Binary struct (UDP 9030) | 9001请求响应+主题推送, 9002远程脚本, 9030实时数据 |
| 多线程 | QThread + Signal/Slot | Qt 线程安全机制 |
| 样式 | QSS (Qt Style Sheet) | 实现网易云风格深色主题 |
| Python 版本 | 3.10+ | 广泛兼容 |

## 项目目录结构

```
robot_ui/
├── main.py                          # 入口
├── requirements.txt                 # 依赖清单
├── config/
│   └── robot_models.yaml            # 机器人型号配置文件(连杆长度/关节数/mesh路径等)
├── app/
│   ├── __init__.py
│   ├── main_window.py               # 主窗口(只持有 TopTabBar + PageStack + GlobalCommandBar + RobotControlDrawer, 不硬编码)
│   ├── page_registry.py             # 页面注册表(PageSpec: key/title/category/factory/requires_connection等)
│   ├── page_router.py               # 页面路由器(懒加载/on_enter/on_leave/连接状态传递)
│   ├── base_page.py                 # 页面基类(BasePage: on_enter/on_leave/on_connection_changed/on_robot_state_changed)
│   ├── styles/
│   │   └── theme.qss                # 深色主题 QSS
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── login_page.py             # 登录连接界面(IP输入/网卡选择/UDP端口/连接按钮)
│   │   ├── home_page.py             # 首页: 状态总览 Dashboard (占位)
│   │   ├── welding_page.py          # 焊接功能页: 送气/送丝/退丝/试运行/焊接参数/路径预览 (占位)
│   │   ├── writing_page.py          # 写字功能页: 字母/数字/图片路径写字 (占位)
│   │   ├── upload_page.py           # 上传功能页: 工程/脚本/变量/点位上传 (占位)
│   │   ├── io_monitor.py            # I/O 监控: DI/DO/AI/AO 状态 (占位)
│   │   ├── program_editor.py        # 程序编辑器 (预留语法高亮, 占位)
│   │   ├── settings.py             # 设置: 网络参数、限位、速度 (占位)
│   │   ├── http_tools_page.py       # HTTP 工具 (占位)
│   │   └── websocket_tools_page.py  # WebSocket 工具 (占位)
│   └── widgets/
│       ├── __init__.py
│       ├── top_tab_bar.py            # 顶部功能页标签栏(横向排列, 支持滚轮滚动, 选中高亮)
│       ├── network_interface_selector.py  # 本机网卡下拉选择器(名称+描述+IPv4, 虚拟网卡标注)
│       ├── status_bar.py            # 底部状态栏(连接状态、帧率)
│       ├── global_command_bar.py    # 底部操作栏(椭圆使能开关+三挡位模式+工程按钮+运动控制, 无清错按钮)
│       ├── robot_control_drawer.py   # 左侧示教器抽屉(3D占位+模式切换+关节点动/笛卡尔点动+速度+moveTo+位姿显示)
│       ├── reconnect_dialog.py      # 掉线重连弹窗
│       ├── network_interface_selector.py  # 本机网卡下拉选择器
│       ├── led_indicator.py         # LED 状态指示灯(未使用)
│       └── console_widget.py        # 日志窗口(未使用)
├── core/
│   ├── __init__.py
│   ├── robot_state.py               # RobotStateStore (UI线程单例, Signal驱动snapshot merge更新) — 当前未接入主链路
│   ├── connection_config.py          # ConnectionConfig + LocalNetworkInterface + pick_available_udp_port
│   ├── robot_model_config.py         # YAML 模型配置加载器
│   ├── unit_converter.py            # rad↔deg, m↔mm
│   ├── thread_manager.py            # TcpThread + UdpThread
│   ├── logger.py                    # 彩色终端(WARNING+) + 文件(DEBUG), 1MB切分, 心跳不写
│   ├── kinematics.py               # 可选运动学模块(预留, 未创建)
│   └── event_bus.py                # 跨线程事件总线(预留, 未创建)
├── network/
│   ├── __init__.py
│   ├── tcp_adapter.py               # 纯网络层: @Slot connect/send/shutdown, Signal: data_received→UI
│   ├── connection_manager.py        # UI线程: pending管理, 响应/推送分发, send_call/send_subscribe, 自动重连
│   ├── udp_cri_adapter.py           # UDP 9030: @Slot bind, 308B校验+解析
│   ├── tcp_script_adapter.py        # TCP 9002 (预留, 未创建)
│   ├── http_client.py              # HTTP 9198 (预留, 未创建)
│   ├── websocket_client.py         # WebSocket 9000 (预留, 未创建)
│   └── protocol/
│       ├── __init__.py
│       ├── json_stream.py             # JsonStreamParser: raw_decode, strict UTF-8
│       ├── request.py                 # RequestBuilder (线程安全, threading.Lock) — 当前未使用
│       ├── response.py                # ResponseDispatcher — 当前未使用
│       ├── errors.py                 # ProtocolError / RobotError / NetworkDisconnectedError
│       ├── cri_parser.py              # CriParser: mask=0xFFFF, highPercision=true, 6轴, 308B
│       └── cri_command.py            # CRI 控制指令 (预留, Part 14)
├── services/
│   ├── __init__.py
│   ├── robot_service.py               # 机器人控制 (当前未使用, subscribe 已改 cm.send_subscribe)
│   ├── cri_service.py                # CRI: bind→StopDataPush→StartDataPush, duration=2ms(500Hz)
│   ├── motion_service.py              # 运动控制 (jog/jogHeartbeat/moveTo/move/pause/resume/stop)
│   ├── project_service.py             # 工程管理 (预留, 未创建)
│   ├── project_http_service.py        # 9198 REST (预留, 未创建)
│   ├── project_map_service.py         # 9000 WS (预留, 未创建)
│   ├── variable_service.py            # 变量 (预留, 未创建)
│   ├── io_service.py                  # IO (预留, 未创建)
│   ├── register_service.py            # 寄存器 (预留, 未创建)
│   ├── script_service.py              # 9002 远程脚本 (预留, 未创建)
│   ├── http_service.py               # HTTP 工具 (预留, 未创建)
│   └── websocket_service.py           # WebSocket 工具 (预留, 未创建)
└── view3d/
    ├── __init__.py
    ├── gl_widget.py                 # QOpenGLWidget 封装
    ├── robot_model.py               # 根据 RobotStatus.type 加载 config/robot_models.yaml, CRI jointPosition 驱动动画
    ├── camera.py                    # 轨道相机(旋转/平移/缩放)
    ├── grid.py                      # 参考网格平面
    └── shaders/
        ├── vertex.glsl              # 顶点着色器
        └── fragment.glsl            # 片段着色器(Phong光照)
```

## 实施步骤

### 阶段一：基础框架 + 只读通信 + 状态显示

> **目标**: 先把软件跑起来，能连接机器人，能读取状态，能显示 CRI 实时数据。
> **这个阶段不做运动控制，不允许机械臂动作。**

---

### Part 0: 环境与空工程初始化

**目标**: 确保 Python 环境和 PySide6 可用，避免 Part 1 一上来就堆大量文件。

**完成文件**:
- [ ] `requirements.txt`
- [ ] `main.py` (最小空窗口)

**功能要求**:
- `main.py` 创建 QApplication + 空 QMainWindow，能启动并显示
- 不创建业务页面
- 不创建网络代码
- 不创建 QSS
- 仅验证 PySide6 可 import

**人工验收**: 运行 `python main.py`，确认空窗口能打开、关闭不报错。

> ✅ **已完成**. 文件: `main.py`(15行), `requirements.txt`(5依赖). 验证: `python main.py` 打开空窗口.

---

### Part 1A: 主窗口骨架 + QSS + 状态栏

**目标**: 四区布局主框架，深色主题，底部状态栏。

**完成文件**:
- [ ] `app/__init__.py`
- [ ] `app/main_window.py` (TopTabBar + PageStack + Drawer + CommandBar 四区占位)
- [ ] `app/styles/theme.qss`
- [ ] `app/widgets/__init__.py`
- [ ] `app/widgets/status_bar.py` (显示"未连接")

**功能要求**:
- 主窗口四区布局到位，各区用占位 QWidget
- QSS 深色主题加载
- 状态栏显示"未连接"
- 不加载页面、不加载注册表、不接网络

**禁止**: `import network`, `import services`, 创建 QTcpSocket/QUdpSocket

**人工验收**: 启动后看到四区轮廓 + 深色背景 + 底部"未连接"。

> ✅ **已完成**. 文件: `app/__init__.py`, `app/main_window.py`(四区骨架+菜单栏 帮助→关于+样式7套), `app/styles/theme*.qss`(7套), `app/widgets/status_bar.py`. 额外: QSettings 持久化样式选择, 连接→登录菜单项.

---

### Part 1B: PageRegistry + PageRouter + 占位页面

**目标**: 页面注册机制和懒加载路由，所有页面为占位。

**完成文件**:
- [ ] `app/base_page.py`
- [ ] `app/page_registry.py`
- [ ] `app/page_router.py`
- [ ] `app/pages/__init__.py`
- [ ] `app/pages/home_page.py` (占位)
- [ ] `app/pages/welding_page.py` (占位)
- [ ] `app/pages/writing_page.py` (占位)
- [ ] `app/pages/upload_page.py` (占位)
- [ ] `app/pages/io_monitor.py` (占位)
- [ ] `app/pages/program_editor.py` (占位)
- [ ] `app/pages/settings.py` (占位)
- [ ] `app/pages/http_tools_page.py` (占位)
- [ ] `app/pages/websocket_tools_page.py` (占位)

**PageRegistry 内容**:
```python
PAGE_REGISTRY = [
    PageSpec("home", "首页", HomePage, category="main"),
    PageSpec("welding", "焊接", WeldingPage, category="process"),
    PageSpec("writing", "写字", WritingPage, category="process"),
    PageSpec("upload", "上传", UploadPage, category="tools"),
    PageSpec("io", "IO", IoMonitorPage, category="robot"),
    PageSpec("program", "程序", ProgramEditorPage, category="robot"),
    PageSpec("http", "HTTP", HttpToolsPage, category="tools"),
    PageSpec("websocket", "WebSocket", WebSocketToolsPage, category="tools"),
    PageSpec("settings", "设置", SettingsPage, category="system"),
]
```

**功能要求**:
- BasePage 有 on_enter/on_leave 空实现
- PageRouter 支持懒加载和缓存
- PageRouter 预留 on_stop_jog_requested Signal（空实现）
- 所有页面为占位：显示标题 + "该功能后续实现"

**禁止**: 不实现具体业务，不接网络

**人工验收**: 运行后不报错，PageRegistry 可导入，PageRouter 能创建页面。

> ✅ **已完成**. 文件: `app/base_page.py`, `app/page_registry.py`(7页, 延迟导入工厂), `app/page_router.py`(懒加载+on_enter/on_leave), `app/pages/*.py`(9个占位页). HTTP/WS 不作为独立页面(PART1C临时需求).

---

### Part 1C: TopTabBar 横向滚动与切页

**目标**: 顶部横向标签栏，集成 PageRouter。

**完成文件**:
- [ ] `app/widgets/top_tab_bar.py`

**功能要求**:
- 从 PageRegistry 读取所有页面生成标签
- 横向排列，标签过多时支持鼠标滚轮横向滚动
- 当前选中标签高亮
- 点击标签通过 PageRouter 切换 PageStack
- 切换时调用 on_leave/on_enter

**禁止**: 不实现具体业务，不接网络

**人工验收**: 点击标签能切换页面，滚轮能滚动标签栏。

---

### Part 1D: GlobalCommandBar 占位按钮

**目标**: 创建底部全局操作栏，所有按钮禁用状态。

**完成文件**:
- [ ] `app/widgets/global_command_bar.py`

**按钮清单** (全部 disabled):
- 上使能 / 下使能
- 清错
- 停止运动 / 停止点动
- 模式切换: 手动 / 自动 / 远程
- 仿真 / 实机
- 启动 / 停止 / 暂停 / 恢复

**功能要求**:
- 按钮固定底部，始终可见
- 所有按钮初始 disabled
- 只创建占位 Signal，不绑定任何 Service
- 不 `import services/network`，不生成 ty/db

**人工验收**: 底部操作栏可见，所有按钮灰色不可点击。

> ✅ **已完成**. 后续重设计(Part 8): 椭圆使能开关(未使能⇄已使能) + 停止运动 + 暂停/恢复运动(toggle) + 启动/暂停/停止工程 + 仿真/实机椭圆开关(右) + 手动/自动/远程三挡位椭圆开关. 清错按钮移到ErrorDialog弹窗. 停止点动删除. 所有按钮通过 _ToggleSwitch.set_checked_silent() 防止 RobotStatus 同步时反馈循环.

---

### Part 1E: RobotControlDrawer 占位展开/收回

**目标**: 可收缩机器人控制抽屉，占位 UI 框架。

**完成文件**:
- [ ] `app/widgets/robot_control_drawer.py`

**功能要求**:
- 默认收起，只露出触发按钮
- 点击展开/收回（简单动画）
- 展开后置顶，覆盖在 PageStack 上方，不阻塞 TopTabBar 和 GlobalCommandBar
- 预留 on_stop_jog_requested Signal（空实现）

**控制内容** (Part 1E 仅占位，按钮禁用):
- 关节点动 J1~J6 +/- (占位)
- 笛卡尔点动 X/Y/Z/Rx/Ry/Rz +/- (占位)
- 坐标系选择 (占位)
- Jog 速度 (占位)
- 当前关节角 / TCP 位姿显示 (显示 "--")
- 停止点动按钮 (占位)

**禁止**: 不接网络，不实现 Jog 逻辑，不 import services

**人工验收**: 点击按钮展开/收回抽屉，占位内容正确，不报错。

> ✅ **已完成**. 用户随后重写为示教器布局(Part 7-8期间): 左侧48px窄条+"运动"按钮, 展开348px: 型号+坐标系信息+3D占位(150px)+模式切换(关节/坐标系)+连续点动/寸动/步长+速度滑块+关节点动J1-J6六行+/笛卡尔点动XYZ RxRyRz六行+moveTo四按钮(Home/安全/蜡烛/打包)+位姿显示. 无停止点动按钮(松开自动停). QFrame+ObjectName QSS作用域, geometry动画200ms, 信号防重复连接, 延迟隐藏content.

---

### Part 1: 顶部标签式多页面主框架 (汇总)

> **注意**: Part 1 已拆分为 Part 0 → Part 1A → 1B → 1C → 1D → 1E。此节仅为 UI 布局和区域职责的汇总参考，**不是可执行 Part**。完成 1E 后直接进入 Part 2，不允许重复实现 Part 1。

#### 整体布局

```
┌──────────────────────────────────────────────────┐
│ TopTabBar: 首页 | 焊接 | 写字 | 上传 | IO | ...   │
├──────────────────────────────────────────────────┤
│                                                  │
│              当前功能页 PageStack                  │
│                                                  │
│   ┌──────────────────────┐                       │
│   │ RobotControlDrawer   │ ← 点击展开/收回        │
│   │ (悬浮, 不占布局宽度)  │                       │
│   └──────────────────────┘                       │
│                                                  │
├──────────────────────────────────────────────────┤
│ GlobalCommandBar: 上电 下电 清错 停止 模式切换...  │
└──────────────────────────────────────────────────┘
```

#### UI 区域职责矩阵

| 区域 | 放什么 | 不放什么 |
|------|--------|----------|
| **顶部标签页** TopTabBar | 首页、焊接、写字、上传、IO、程序、设置、HTTP、WebSocket | 不放 Jog 细节按钮 |
| **中间页面** PageStack | 当前功能模块内容 | 不放全局急停/停止这种常驻按钮 |
| **可收缩抽屉** RobotControlDrawer | 机器人 Jog、关节/TCP 位姿、坐标系、Jog速度 | 不放送气、送丝、退丝、试运行 |
| **底部操作栏** GlobalCommandBar | 上使能、下使能、启动、停止、暂停、恢复、模式切换、清错、stopMove/stopJog | 不放焊接工艺按钮 |
| **焊接页** WeldingPage | 试运行、送气、送丝、退丝、焊接参数、路径生成 | 不放通用模式切换 |

> **法则**: 每个区域只能放规定的东西。交叉污染（如把送丝放进 GlobalCommandBar）视为实现错误。

---

### Part 2: 配置文件与机器人模型配置

**目标**: 建立机器人型号配置机制，但不做 3D 实时动画。

**完成文件**:
- [ ] `config/robot_models.yaml`
- [ ] `core/robot_model_config.py`

**功能要求**:
- 增加 `robot_models.yaml`
- 支持通过机器人型号 `type` 加载模型配置
- 找不到型号时 fallback 到 `default_6axis`
- 不允许 Claude Code 自行查 DH 参数
- DH 不作为第一版实时显示主链路
- 模型配置只负责显示信息：关节数量、关节顺序、模型类型、mesh 路径、显示比例等

**禁止事项**:
- 禁止查网上 UR DH 参数
- 禁止写 FK 作为实时显示主链路
- 禁止让模型配置影响通信协议

**人工验收**: 用户确认程序能读取 `robot_models.yaml`、能加载 `default_6axis`、没有机器人连接时 UI 不报错。

---

### Part 3: RobotStateRaw / RobotStateUi 单位转换

**目标**: 建立状态数据模型和单位转换规则。

**完成文件**:
- [ ] `core/robot_state.py`
- [ ] `core/unit_converter.py`

**功能要求**:
- 建立两层状态: `RobotStateRaw`(保存 CRI 原始值 rad/m)、`RobotStateUi`(保存 UI 显示值 deg/mm)
- 单位转换: joint_deg = rad × 180/π, tcp_mm = m × 1000, tcp_deg = rad × 180/π

**禁止事项**:
- 禁止 UI 直接读取 RobotStateRaw
- 禁止 TCP JSON 命令直接使用 CRI 原始 rad/m 数据
- 禁止混用 rad 和 deg

**人工验收**: 用户确认给定模拟 CRI 数据能正确转换成 UI 的 mm + deg，UI 页面能显示转换后的值。

---

### Part 4: TCP JSON 协议层 (仅协议，不接 socket)

**目标**: 实现 JSON 裸流解析和请求响应分发，不接真实 socket。

**完成文件**:
- [ ] `network/protocol/json_stream.py`
- [ ] `network/protocol/request.py`
- [ ] `network/protocol/response.py`
- [ ] `network/protocol/errors.py`

**功能要求**:
- JsonStreamParser 支持无分隔 JSON 拼接
- 禁止 readLine() 思路
- TCP JSON 严格 UTF-8 解码；解码失败清空缓冲并抛出 ProtocolError
- RequestBuilder 生成 `{id, ty, db}`
- ResponseDispatcher 区分: 有 id → PendingRequest；无 id 且 ty 是 publish/* → 订阅推送

**禁止事项**:
- 禁止创建 QTcpSocket
- 禁止连接实体机器人
- 禁止写运动接口

**人工验收**: 用户通过本地单元测试确认: 多个 JSON 拼接能切开、半包 JSON 能等待下一次数据、publish/* 能被分发、id 响应能匹配 PendingRequest。

---

### Part 4.5: 登录连接界面

**目标**: 软件启动后先进入登录/连接界面，用户填写 IP、选择网卡、确认 UDP 端口后点击连接，才进入主界面。不直接自动连接。

**完成文件**:
- [ ] `app/pages/login_page.py`
- [ ] `app/widgets/network_interface_selector.py`
- [ ] `core/connection_config.py`

#### 界面布局

```
┌─────────────────────────────────────────┐
│         Codroid 机器人控制终端           │
│                                         │
│  机器人 IP:  [192.168.1.136          ]  │
│  本机网卡:   [以太网 - Intel(R)... ▼ ]  │
│             [刷新网卡]                  │
│  UDP 端口:   [38421          ]         │
│                                         │
│       [连接机器人]    [离线模式]         │
│                                         │
│  状态: 未连接                           │
└─────────────────────────────────────────┘
```

#### 数据结构 (`core/connection_config.py`)

```python
@dataclass
class LocalNetworkInterface:
    name: str           # 网卡名称, 如 "以太网"
    description: str    # 描述, 如 "Intel(R) Ethernet Controller..."
    ipv4: str           # IPv4 地址
    is_up: bool         # 是否启用
    is_loopback: bool   # 是否环回
    is_virtual: bool    # 是否虚拟网卡(VMware/Docker/WSL等)

@dataclass
class ConnectionConfig:
    robot_ip: str = "192.168.1.136"
    local_ip: str = ""
    local_interface: LocalNetworkInterface | None = None
    udp_port: int = 0   # 0 = 未分配, 由 pick_available_udp_port() 生成
```

#### 本机网卡下拉菜单 (`app/widgets/network_interface_selector.py`)

**显示格式**:
```
以太网 - Intel(R) Ethernet Controller - 192.168.1.50
WLAN - Realtek WiFi Adapter - 192.168.1.88
以太网 2 - VMware Virtual Ethernet Adapter - 192.168.56.1  [虚拟网卡]
DockerNAT - 172.17.0.1  [虚拟网卡]
```

**过滤规则**:
- `127.0.0.1`、`0.0.0.0`、`169.254.x.x` 默认隐藏或置灰
- 虚拟网卡（VMware/Docker/WSL/VPN）显示但标注 `[虚拟网卡]`，不强行过滤（客户现场可能通过桥接网络调试）
- `is_up == False` 的网卡置灰或标注 `[未启用]`

**枚举方法**: 使用 `socket.getaddrinfo` 或 `psutil.net_if_addrs()` 获取本机网卡列表。

#### UDP 端口规则 (`app/pages/login_page.py`)

```python
def pick_available_udp_port(min_port=10000, max_port=65535, retry=10) -> int:
    """预检查端口可用性，失败自动重试"""
    for _ in range(retry):
        port = random.randint(min_port, max_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()
    raise RuntimeError("无法自动分配可用 UDP 端口，请手动指定")
```

注意: 此函数只是"预检查"，真正使用时 `QUdpSocket.bind()` 仍可能失败，Part 6 内还需要做 bind 失败处理。

**端口规则**:
- 启动时自动随机生成 10000~65535 范围内的端口
- 用户可手动修改
- 绑定失败时自动重试（最多 10 次），仍失败提示用户手动选择

#### 功能要求

- 软件启动后先显示登录界面，不直接进入主界面
- 用户填写机器人 IP、选择本机网卡、确认 UDP 端口
- 点击"连接机器人"**只做输入校验 + 生成 ConnectionConfig + 发出 `connect_requested(config)` Signal**，然后切换到主界面
- 真正的 TCP 9001 连接由 Part 5 ConnectionManager 接收 Signal 后执行
- 点击"离线模式"跳过连接直接进入主界面（所有机器人功能禁用）
- 主界面**不重复提供**机器人 IP / 本机 IP / UDP 端口输入
- 如需修改连接参数 → 用户返回登录界面重新选择

**禁止事项**:
- 禁止在登录界面创建 QTcpSocket
- 禁止在登录界面发送任何机器人请求
- 禁止自动连接
- 禁止自动进入主界面（必须用户点击按钮）

**人工验收**: 
- 启动软件显示登录界面
- 下拉菜单正确显示本机网卡列表（虚拟网卡标注）
- UDP 端口自动生成在 10000~65535 范围
- 点击"连接机器人" → 切换主界面（不验证实际连接成功，Part 5 才做）
- 点击"离线模式" → 切换主界面

---

### Part 5: TCP 9001 连接与只读订阅

**目标**: 使用 Part 4.5 生成的 ConnectionConfig 连接 TCP 9001，订阅状态主题，只读不运动。

**完成文件**:
- [ ] `network/tcp_adapter.py`
- [ ] `network/connection_manager.py`
- [ ] `app/widgets/reconnect_dialog.py` (掉线弹窗)
- [ ] `services/robot_service.py` (只读部分)
- [ ] `app/pages/home_page.py`

**功能要求**:
- ConnectionManager 接收 `connect_requested(config: ConnectionConfig)` Signal
- 使用 `config.robot_ip` 连接 TCP 9001（默认端口 9001）
- **主界面不再提供机器人 IP / 本机 IP / UDP 端口输入**
- 如需修改连接参数 → 用户返回登录界面重新选择
- 连接成功后订阅: `publish/RobotStatus`、`publish/Error`、`publish/Log`
- 从 `RobotStatus.db.type` 读取机器人型号 → 加载 `robot_models.yaml`
- 状态栏显示连接状态、机器人型号、模式、状态
- 不做运动控制

#### 自动重连退避策略

1. 第 1 次重连: 1 秒后
2. 第 2 次重连: 2 秒后
3. 第 3 次重连: 4 秒后
4. 第 4 次重连: 8 秒后
5. 第 5 次及以后: 每 10 秒重试一次
6. 最大重连次数默认不限，直到用户点击 [停止重连并返回主页面] 或程序关闭

#### TCP 9001 掉线弹窗规则

1. 掉线后**必须立即弹窗**提示用户
2. 掉线后**优先自动重连**，不要求用户点击按钮触发
3. 弹窗持续显示:
```
           机器人连接已断开，正在尝试重新连接...

           机器人 IP：192.168.1.136
           本机 IP：192.168.1.50
           UDP 端口：38421

           重连次数：第 3 次
           下一次重连：4 秒后
           最近错误：Connection timeout

                          [停止重连并返回主页面]
```
4. 弹窗只保留一个按钮: **[停止重连并返回主页面]**
   - 停止当前自动重连流程
   - 关闭弹窗
   - 保持主界面打开
   - 所有机器人功能保持禁用
   - 用户可在主界面选择返回登录页重新配置连接参数
5. 自动重连成功后 (分情况显示):
   - 如果本次会话用户已手动启用过 CRI: 弹窗显示"已重连，订阅已恢复，CRI 实时数据推送已恢复"
   - 如果本次会话用户未启用过 CRI: 弹窗显示"已重连，订阅已恢复"
   - 1~2 秒后自动关闭弹窗
   - 状态栏同步显示对应文案
6. 自动重连失败时:
   - 弹窗继续显示失败原因和下一次重连倒计时
   - 不自动关闭弹窗

**自动重连成功后允许恢复**:
- TCP 9001 连接
- active subscriptions（按原 topic + interval_ms 重新发送）
- 用户本次会话中已经手动启用过的 CRI StartDataPush（先 StopDataPush 再 StartDataPush）

**自动重连成功后禁止恢复**:
- Jog / move / moveTo / move_path
- CRI StartControl
- 上使能
- 工程运行
- 焊接送丝 / 送气 / 退丝
- 任何运动类心跳

**禁止事项**:
- 禁止程序启动后自动连接；首次连接必须等待 Part 4.5 的 `connect_requested(config)` Signal
- 允许已连接成功后的 TCP 掉线自动重连，但只允许恢复 TCP、订阅和用户本次会话已手动启用过的 CRI StartDataPush，禁止恢复任何运动状态
- 禁止在主界面重复提供 IP/端口输入
- 禁止自动 switchOn / jog / move / moveTo
- 禁止启用 CRI StartControl

**人工验收**: 用户在登录页填写参数点击连接 → 进入主界面后确认状态栏显示连接成功、RobotStatus 正常、错误日志显示。

**拔网线断线测试** (必须验证):
- 弹窗立即出现
- 重连次数和下一次重连倒计时持续更新
- 所有机器人控制按钮禁用
- 不发送 switchOn / jog / move / StartControl
- 插回网线后自动重连成功，订阅恢复，弹窗 1~2 秒后自动关闭

---

### Part 6: CRI StartDataPush + UDP 308 字节解析

**目标**: 启动固定 CRI 数据推送，解析实时关节和 TCP 位姿。

**完成文件**:
- [ ] `network/udp_cri_adapter.py`
- [ ] `network/protocol/cri_parser.py`
- [ ] `services/cri_service.py`
- [ ] `core/robot_state.py` (完善)
- [ ] `app/pages/home_page.py` (完善)

> 注意: `cri_command.py` 留到 Part 14，Part 6 只做数据接收解析。

**固定协议约束** (必须写死):
- mask = 0xFFFF, highPercision = true, axis_count = 6, external_axis_count = 0
- 期望帧长 308 bytes
- 发送给控制器的完整 JSON:
```json
{
  "id": "<auto_id>",
  "ty": "CRI/StartDataPush",
  "db": {
    "ip": "<local_ip>",
    "port": <local_udp_port>,
    "duration": 20,
    "mask": 65535,
    "highPercision": true
  }
}
```
- 代码内部常量统一使用 `HIGH_PERCISION`（故意沿用控制器拼写，不用 PRECISION）

**启动 CRI 实时数据必须按顺序执行**:
1. 使用 `ConnectionConfig.local_ip` / `ConnectionConfig.udp_port` 创建并绑定 QUdpSocket
2. 绑定成功后，发送 `CRI/StopDataPush`（清理旧推送，失败不阻塞）
3. StopDataPush 成功、失败或超时后，发送 `CRI/StartDataPush`
4. StartDataPush 响应成功后，UI 显示"实时数据已启动"
5. **如果 UDP bind 失败，禁止发送 StartDataPush**

**功能要求**:
- UI 点击"启动实时数据"后按上述顺序执行
- 收到 UDP datagram 后先检查长度: `len(data) == 308` 才解析，不匹配整帧丢弃
- 解析后写入 RobotStateRaw → 转换成 RobotStateUi
- Dashboard 显示: 6 轴关节角 deg、TCP xyz mm、TCP 姿态 deg、isMoving、UDP 接收频率、丢帧计数

**禁止事项**:
- 禁止 UI 提供 mask / highPercision / 外部轴数量修改入口
- 禁止 Service public API 暴露 mask / highPercision / axis_count / external_axis_count
- 禁止启动 CRI/StartControl
- 禁止在 UDP bind 成功前发送 StartDataPush

**人工验收**: 用户点击连接 9001、启动 CRI 数据推送。确认 UDP 能收到 308 字节数据、UI 关节角/TCP 位姿单位正确、移动机械臂时 UI 数据刷新、坏帧不会导致崩溃。

---

### Part 7: 只读 Dashboard 完整化 + UI 状态同步

**目标**: 把状态显示做完整，并将订阅数据同步到 GlobalCommandBar 控件状态。

**完成文件**:
- [ ] `app/pages/home_page.py` (完善)
- [ ] `app/widgets/led_indicator.py`
- [ ] `app/widgets/status_bar.py`
- [ ] `app/widgets/console_widget.py`

**功能要求**:
- 显示: 连接状态、机器人型号、模式 mode、状态 state、是否使能、是否仿真、isMoving、6 轴关节角 deg、TCP xyz mm、TCP 姿态 deg、错误日志、UDP 接收频率

#### UI 状态同步 (订阅 → GlobalCommandBar)

从 `publish/RobotStatus` 同步:
| 字段 | 目标控件 | 方法 |
|------|----------|------|
| `db.state` (0=未使能) | 使能开关 | `_command_bar.set_enable_state(state != 0)` |
| `db.mode` (0=手动/1=自动/2=远程) | 三挡位模式开关 | `_command_bar.set_mode(mode)` |
| `db.isSimulation` | 仿真/实机开关 | `_command_bar.set_simulation(isSimulation)` |

从 `publish/ProjectState` 同步:
| 字段 | 目标控件 | 方法 |
|------|----------|------|
| `db.state` (2=运行/3=暂停) | 工程按钮组 | `_command_bar.set_project_paused(state==3)` |

从 CRI `statusData1` / `publish/RobotStatus` 同步:
| 字段 | 目标控件 | 方法 |
|------|----------|------|
| `isMoving` | 运动按钮状态 | 运动中时"暂停运动"可用、"恢复运动"隐藏 |
| `state == 3` (点动中) / `state == 4` (RunTo) | 运动按钮组 | `_command_bar.set_motion_paused(False)` |

从 `publish/Error` 同步:
| 条件 | 行为 |
|------|------|
| 收到非空错误推送 | 弹出 `ErrorDialog`，只有点击"清除错误"(`System/clearError`) 才能关闭 |

**禁止事项**:
- 禁止运动按钮
- 禁止自动使能
- 禁止自动清错
- 禁止在无网络时模拟状态

**人工验收**: 用户确认连接后状态稳定、CRI 数据正常刷新、断开/重连 UI 不崩、错误日志能显示。

---

### 阶段二：手动控制 + IO + 3D + 扩展功能

> **目标**: 在已有只读状态稳定的基础上，逐步增加由用户手动触发的控制功能。

---

### Part 8: 机器人基础控制按钮

**目标**: 增加非运动类控制按钮。

**完成文件**:
- [ ] `services/robot_service.py`
- [ ] `app/pages/home_page.py` (完善)

**功能按钮**: 清错(`System/clearError`)、上使能(`Robot/switchOn`)、下使能(`Robot/switchOff`)、进入手动(`Robot/toManual`)、进入自动(`Robot/toAuto`)、进入远程(`Robot/toRemote`)、仿真(`Robot/toSimulation`)、实机(`Robot/toActual`)

**功能要求**:
- 所有按钮必须由用户点击
- 不能启动后自动执行
- 每个按钮调用后只根据响应显示"命令已接收"
- 实际状态变化以 RobotStatus / CRI 状态为准

**禁止事项**: 禁止按钮触发运动、禁止自动切模式、禁止自动使能

**人工验收**: 用户手动点击每个按钮，确认响应正常、状态显示随 RobotStatus 更新、异常时 UI 能显示错误。

---

### Part 9: Jog 手动点动控制

**目标**: 实现手动 Jog，必须按住运动、松开停止。

**完成文件**:
- [ ] `services/motion_service.py`
- [ ] `app/widgets/robot_control_drawer.py` (实现 Jog UI)
- [ ] `app/widgets/joint_slider.py`

**功能要求**:
- `jog_start()` 发送 `Robot/jog`
- HeartbeatManager 在 TcpThread 内发送 `Robot/jogHeartbeat`
- 松开按钮发送 `Robot/stopJog`
- 页面切换、窗口失焦、断线、抽屉收回时触发 stopJog
- Jog 速度 UI 默认低速
- 响应只表示命令接收，实际运动状态看 CRI isMoving

**禁止事项**:
- 禁止点击一次后持续运动
- 禁止 UI 线程创建 heartbeat QTimer
- 禁止 Service 自己创建 socket
- 禁止未连接 CRI 状态时启用 Jog

**人工验收**: 用户手动测试张开抽屉按住 J1+ 确认机器人低速运动、松开确认停止、切页面/断线/窗口失焦/抽屉收回时停止。

---

### Part 10: movJ / movL / movC / move_path

**目标**: 实现由用户手动点击触发的运动指令。

**完成文件**:
- [ ] `services/motion_service.py` (完善)
- [ ] `app/pages/home_page.py` 或新增运动指令弹窗 (UI 入口)

**功能要求**:
- `mov_j()` / `mov_l()` / `mov_c()` / `mov_circle()` / `move_path()`
- `Robot/move` 的 db 必须是数组 `[{...}, {...}]`
- `move_path()` 一次传入多个路径段保证过渡
- 不需要 coor/tool 时直接省略字段，禁止传 `[]`
- UI 输入和 TCP JSON 命令单位统一为 mm + deg

**禁止事项**:
- 禁止自动生成大范围目标点
- 禁止直接把 CRI raw rad/m 发给 Robot/move
- 禁止把 move 响应当作运动完成

**人工验收**: 用户通过 UI 手动输入小范围目标，确认 Robot/move JSON 结构正确、db 是数组、单位 mm + deg、动作完成由 CRI isMoving 变化判断。

---

### Part 11: IO / 寄存器 / 变量页面

**目标**: 实现 IO、寄存器、变量读写。

**完成文件**:
- [ ] `services/io_service.py`
- [ ] `services/register_service.py`
- [ ] `services/variable_service.py`
- [ ] `app/pages/io_monitor.py`
- [ ] `app/pages/settings.py`

**功能要求**: DI/DO/AI/AO 读取、DO/AO 写入、寄存器读取/写入、全局变量读取/保存/删除、工程变量运行时读取。所有写操作由用户点击触发。

**禁止事项**: 禁止自动写 DO、禁止自动写寄存器、禁止自动改变量

**人工验收**: 用户手动点击读取和写入，确认 IO 状态正确、DO 输出正确、异常响应能显示。

---

### Part 12: 3D 简化模型显示

**目标**: 用 CRI jointPosition 驱动 3D 关节动画。

**完成文件**:
- [ ] `view3d/gl_widget.py`
- [ ] `view3d/robot_model.py`
- [ ] `view3d/camera.py`
- [ ] `view3d/grid.py`

**功能要求**:
- 根据 `RobotStatus.type` 加载模型配置
- 找不到型号使用 `default_6axis`
- 第一版只做简化连杆模型
- 关节动画由 CRI jointPosition 驱动
- UI 显示单位 deg，3D 内部可用 rad 做旋转
- 不依赖 DH 正解作为实时状态主链路
- 末端实际 xyz/rx/ry/rz 直接显示 CRI 转换后的 UI 值

**禁止事项**:
- 禁止 Claude Code 自行查 DH 参数
- 禁止第一版加载复杂 STL 后导致卡顿
- 禁止用 FK 结果覆盖 CRI 末端位姿

**人工验收**: 用户移动实体机械臂，确认 3D 模型关节动画跟随、数值显示和 CRI 一致、UI 不明显卡顿。

---

### Part 13: 9002 远程脚本

**目标**: 实现远程脚本模式。

**完成文件**:
- [ ] `network/tcp_script_adapter.py`
- [ ] `services/script_service.py`
- [ ] `app/pages/program_editor.py`

**功能要求**: 连接 9002、发送脚本、接收变量返回、支持 interrupt/resume/stop。所有执行由用户点击触发。

**禁止事项**: 禁止启动后自动执行脚本、禁止自动发送运动脚本

**人工验收**: 用户手动执行简单脚本，确认返回正常。

---

### Part 14: CRI StartControl 实时控制

**目标**: 最后再实现 CRI 实时控制指令发送。

**完成文件**:
- [ ] `services/cri_service.py` (完善)
- [ ] `network/protocol/cri_command.py` (完善)
- [ ] `network/udp_cri_adapter.py` (完善)

**功能要求**:
- StartDataPush 已经稳定后才做
- StartControl 必须由用户点击确认
- 控制指令 struct 固定 70 字节
- 不启动后自动发送
- 不重连后自动恢复
- 停止控制必须明确

**禁止事项**: 禁止在前面 Part 提前实现、禁止自动启用 StartControl、禁止断线重连后自动恢复实时控制

**人工验收**: 用户手动确认后测试。

---

### Part 15: 完善与打包

**目标**: 完善稳定性和可发布性。

**完成文件**:
- [ ] 日志系统
- [ ] 配置持久化
- [ ] 异常捕获
- [ ] 窗口关闭清理
- [ ] `README.md`
- [ ] `requirements.txt` (完善)

**功能要求**: 关闭窗口时停止 Jog 心跳、停止 CRI 数据推送、断开 TCP/UDP、保存 IP/端口/UI 设置、记录错误日志。

**人工验收**: 用户确认多次启动/关闭无异常、断线/重连不崩、配置能保存、日志可查看。
## 核心依赖

```
PySide6>=6.5          # UI框架
PyOpenGL>=3.1         # OpenGL绑定
numpy>=1.24           # 矩阵运算
psutil>=5.9           # 枚举本机网卡名称/描述/IPv4
PyYAML>=6.0           # 读取 config/robot_models.yaml
```

## AI 实现约束

> 以下约束对所有实施阶段强制执行，违反任何一条即为实现错误。

| # | 约束 | 说明 |
|---|------|------|
| 1 | 每次只实现一个 Part | 必须按 Part 0 → Part 1A → ... → Part 15 顺序推进。阶段只是分组，不是一次实现单位。禁止一次性实现整个阶段 |
| 2 | Part 1 只做骨架和占位 | 允许页面切换、状态栏、TopTabBar、抽屉展开/收回等基础 UI。禁止网络、Service绑定、真实机器人指令。后续 Part 逐步放开 |
| 3 | 顺序推进，禁止提前 | 禁止提前实现后续 Part 的功能。例如 Part 1 不能写 MotionService 或网络连接 |
| 4 | Socket 线程亲和性 | QTcpSocket/QUdpSocket 只能在所属 QThread 内创建和访问 |
| 5 | UI 层隔离 | UI 禁止 `import network/`，只能 `import services/` |
| 6 | Service 不持有 socket | Service 只持有 adapter 引用，不创建 socket |
| 7 | 运动响应 ≠ 完成 | 运动接口响应只表示命令已接收，完成靠 CRI `isMoving` 判断 |
| 8 | `Robot/move` 拆分为专用方法 | `motion_service` 暴露 `mov_j()/mov_l()/mov_c()/mov_circle()/move_path()`。`move_path` 一次传入多个路径段，内部拼成 `db: [{...}, {...}]` 保证轨迹过渡 |
| 9 | coor/tool 省略而非空数组 | 不需要坐标系时直接省略字段，禁止传 `[]` |
| 10 | 每阶段最小测试 | 完成一个阶段必须运行验证，确认通过才能进入下一阶段 |
| 11 | 重连后状态重建 | 重连成功后必须: 重新订阅全部 topic, 恢复 CRI 数据推送, 失败所有 pending。禁止自动恢复 CRI 实时控制 |
| 12 | RobotState 不跨线程直接写 | RobotStateStore 仅 UI 线程拥有。TcpThread/UdpThread 通过 Signal 发 snapshot dict, UI 线程 merge 更新。禁止多线程加锁直接改 |
| 13 | Heartbeat QTimer 归 TcpThread | MotionService 只发 start/stop 请求, HeartbeatManager + QTimer 在 TcpThread 内。Service 不直接创建 QTimer |
| 14 | QSS 第一版克制 | 只做基础深色主题: 主背景/TopTabBar/按钮(含hover+pressed+checked)/输入框/表格/状态灯。禁止复杂动画、渐变、毛玻璃、过度阴影 |
| 15 | 跨线程 Signal 全用 object | 所有携带 dict/list/callback 的跨线程 Signal 必须声明为 `Signal(object)`，禁止 `Signal(dict)`/`Signal(list)`。str/bool/int/无参除外 |
| 16 | 回调不入 TcpThread | 订阅回调、on_response/on_error 回调全部保存在 ConnectionManager(UI线程)。TcpThread 只做网络收发和 JSON 解析，不持有不调用任何 UI 回调 |
| 17 | socket/timer 清理在 @Slot | 所有 `stop()`/`abort()`/`deleteLater()` 封装在 TcpAdapter.shutdown() @Slot 中。UI 线程通过 `_sig_shutdown.emit()` 触发，禁止直接操作 adapter 内部对象 |
| 15 | DH 非第一版必需 | 禁止 AI 从网查 DH 参数。kinematics.py 为可选模块，不作为实时显示主链路 |
| 16 | CRI 主数据源, RobotPosture 兜底 | 关节角度/TCP位姿/isMoving 优先读 CRI。publish/RobotPosture 仅在 CRI 未启动/断开时使用 |
| 17 | 单位转换必须经 StateConverter | CRI rad/m → StateConverter → UI deg/mm。MotionService 拼 TCP JSON 用 deg/mm，禁止把 rad/m 填入 TCP 命令 |
| 18 | CRI 推送配置固定 | mask=0xFFFF, highPercision=true, 6轴, 无外部轴, 308字节。禁止 UI 可配置, 禁止 Service public API 暴露这些参数。注意 JSON 字段名 highPercision 不能拼错 |

---

## 真机手动联调约束

> 本项目不要求 AI 自动执行真机测试。**禁止 Claude Code 编写会自动触发实体机械臂运动的测试脚本。** 所有真机测试由用户通过 UI 手动点击完成。

| # | 约束 | 说明 |
|---|------|------|
| 1 | AI 不连真机 | Claude Code 不得自动连接真实机器人并发送运动指令 |
| 2 | 无自动运动测试脚本 | 不编写自动执行 `Robot/jog`/`Robot/move`/`Robot/moveTo`/`CRI/StartControl` 的测试脚本 |
| 3 | 默认不连 | UI 首次启动默认不连接机器人，需用户点击"连接" |
| 4 | 只订阅不使能 | UI 连接后默认只订阅状态，不自动使能，不自动运动 |
| 5 | 显式运动触发 | 所有运动按钮默认需用户明确点击 |
| 6 | 按住运动松开停止 | Jog 必须采用"按住触发点动，松开调用 stopJog"交互 |
| 7 | Jog 安全停止 | Jog 按钮释放 / 鼠标移出按钮区域 / 窗口失焦 / 页面切换 / 断线时，必须调用 `Robot/stopJog` |
| 8 | 二次确认 | `Robot/move`、`moveTo`、`CRI/StartControl` 按钮需弹窗二次确认 |
| 9 | 默认低速 | 首次启动速度倍率限制为低速(5%~10%)，由用户手动调高 |
| 10 | 显式紧急按钮 | UI 需提供明显可见的 `停止点动`、`停止运动`、`下使能`、`清除错误` 按钮 |
| 11 | 重连不恢复运动 | 断线重连后只恢复状态订阅，不自动恢复 Jog / moveTo / move / CRI 实时控制 |
| 12 | 无位姿不运动 | 未收到有效 `RobotStateUi` 位姿前禁用所有运动按钮。位姿可来自 CRI 主数据源，也可来自 `publish/RobotPosture` fallback，两者任一有效即算有数据 |

---

## 通讯架构设计

机器人控制器开放多个端口，分为核心通道和扩展通道：

**核心通道 (阶段一实现)**:
```
┌─────────────────────────────────────────────────────────┐
│  UI 客户端                                               │
├──────────┬──────────────────┬───────────────────────────┤
│ TCP 9001 │ TCP 9002         │ UDP 9030                  │
│ JSON     │ JSON             │ Binary (CRI)              │
│ 请求/响应│ 远程脚本执行      │ 实时数据推送+控制指令下发  │
│ +主题推送│                  │                           │
└──────────┴──────────────────┴───────────────────────────┘
```

**扩展通道 (阶段二后续 Part 实现)**:
| 通道 | 端口 | 协议 | 用途 |
|------|------|------|------|
| HTTP REST | 9198 | HTTP/JSON | 工程上传、变量管理、点位操作 |
| WebSocket | 9000 | WS/JSON | 工程映射、实时状态推送 |

### 通道 A: TCP 9001 — 控制指令通道

**协议**: TCP, JSON, UTF-8
**方向**: 双向（请求→响应, 订阅→推送）

**请求格式**:
```json
{ "id": <int|str>, "ty": "<接口类型>", "db": <请求参数> }
```

**响应格式**:
```json
{ "id": <int|str>, "ty": "<接口类型>", "db": <返回数据>, "err": {"code": N, "msg": "..."} }
```

**推送格式**（订阅后主动推送，无id匹配）:
```json
{ "ty": "publish/<Topic>", "db": <推送数据>, "tc": <订阅周期ms> }
```

**接口分类**:
| 前缀 | 功能域 | 示例 |
|------|--------|------|
| `project/` | 工程控制 | runScript, pause, stop, run, runStep |
| `globalVar/` | 全局变量 | getVars, saveVars, removeVars |
| `Robot/` | 机器人控制 | jog, moveTo, move, switchOn, switchOff |
| `Robot/` | 计算 | apostocpos(正解), cpostoapos(逆解) |
| `IOManager/` | IO读写 | GetIOValue, SetIOValue |
| `RegisterManager/` | 寄存器 | GetRegisterValue, SetRegisterValue |
| `ModbusTcp/` | Modbus主站 | setDevice, setTable, getConfig |
| `EC2RS485/` | 末端485 | init, read, write |
| `System/` | 系统 | clearError |
| `MFC/` | 法兰灯带 | SetLed |
| `CRI/` | 实时控制 | StartDataPush, StartControl(通过TCP下发配置) |

**关键设计点**:
- 请求通过 `id` 字段匹配响应，需要维护 `_pending: dict[id, PendingRequest]` 映射
- 推送消息的 `ty` 以 `publish/` 开头，无 `id` 字段，需独立路由到订阅回调
- 点动(jog)和moveTo需要在 500ms 内发心跳维持，否则自动停止
- 焊接送丝/退丝/送气同样需要 500ms 心跳

### 通道 B: TCP 9002 — 远程脚本通道

**协议**: TCP, JSON, UTF-8
**方向**: 双向（脚本执行→结果返回）

**请求格式**:
```json
{
  "command": "resume|stop|interrupt",  // 控制命令(存在时script无效)
  "script": "<lua代码>",               // 脚本代码
  "vars": ["var1", "var2"],            // 执行后返回的变量(可选)
  "...": "自定义透传字段"
}
```

**响应格式**:
```json
{
  "code": 0,           // 0=成功
  "msg": "OK",
  "vars": {"P1": 1, "v2": "hello"},
  "...": "透传返回"
}
```

**运行机制**:
- 脚本加入队列(FIFO, 最大64条), 队列满返回错误
- 可通过 `command: "interrupt"` 打断死循环
- 通过 9001 的 `project/pause|resume|stop` 也可控制

### 通道 C: UDP 9030 — CRI 实时通道

**协议**: UDP, Binary
**方向**: 机器人→客户端(数据推送), 客户端→机器人(控制指令)

#### C.1 实时数据推送（机器人 → 客户端）

通过 TCP 9001 的 `CRI/StartDataPush` 配置目标 IP/端口，机器人开始向该地址推送二进制数据包。

**本项目固定配置**:

| 参数 | 固定值 | 说明 |
|------|--------|------|
| mask | 0xFFFF (65535) | 全部数据位开启 |
| highPercision | true | Float64 (8字节) |
| axis_count | 6 | 6轴机器人 |
| external_axis_count | 0 | 无外部轴 |
| UDP 单帧长度 | **308 bytes** | 固定期望值, 不匹配直接丢弃 |

> 注意: JSON 字段名是 `highPercision`，代码内部常量也统一用 `HIGH_PERCISION`（故意沿用控制器拼写）。禁止混用 PRECISION/PERCISION。

**mask 位定义** (仅供参考，本项目不做配置):

| 位 | 字段 | 类型 | 本项目 |
|----|------|------|--------|
| 0 | 时间戳 | Int64 | ✓ |
| 1 | 状态数据1 | UInt16 | ✓ |
| 2 | 状态数据2 | UInt16 | ✓ |
| 3-7 | 保留 | — | mask包含但不读 |
| 8 | 关节位置 | Float64×6 | ✓ |
| 9 | 关节速度 | Float64×6 | ✓ |
| 10 | 末端位置 | Float64×6 | ✓ |
| 11 | 末端速度 | Float64×6 | ✓ |
| 12 | 末端线速度 | Float64 | ✓ |
| 13 | 关节力矩 | Float64×6 | ✓ |
| 14 | 关节外力 | Float64×6 | ✓ |
| 15 | 外部轴位置 | — | mask包含, external_axis_count=0 不读取 |

**CriParser 固定配置**:
```python
class CriParserFixedConfig:
    MASK = 0xFFFF
    HIGH_PERCISION = True          # Float64
    AXIS_COUNT = 6
    EXTERNAL_AXIS_COUNT = 0
    EXPECTED_PACKET_SIZE = 308     # int: bytes
```

**start_data_push 固定请求** (cri_service):
```python
def start_data_push(self, local_ip: str, local_port: int):
    """仅接受本机 IP 和 UDP 监听端口, mask/highPercision/轴数在内部写死"""
    self._tcp.call(
        ty="CRI/StartDataPush",
        db={
            "ip": local_ip,
            "port": local_port,
            "duration": 20,
            "mask": 65535,           # 0xFFFF
            "highPercision": True,   # 注意拼写
        }
    )
```

#### C.2 实时控制指令（客户端 → 机器人）

通过 TCP 9001 的 `CRI/StartControl` 配置滤波/间隔/缓冲后，客户端向 9030 端口发送二进制控制指令。

**指令结构** (每帧固定 70 字节):
```
┌──────────┬──────────────────────────┬───────┬──────────┐
│ Int64    │ Float64[6]               │ UInt8 │ UInt8[7] │
│ timestamp│ position (关节/末端)      │ type  │ reserved │
│ (未使用) │                          │ 0关节 │          │
│ 8B       │ 48B                      │ 1末端 │ 7B       │
└──────────┴──────────────────────────┴───────┴──────────┘
```

### 消息流设计

```
                     ┌─────────────┐
                     │  RobotState │ (dataclass, 线程安全)
                     └──────┬──────┘
                            │ update
              ┌─────────────┼─────────────┐
              │             │             │
         ┌────┴────┐  ┌────┴────┐  ┌─────┴────┐
         │TCP 9001 │  │TCP 9002 │  │ UDP 9030 │
         │Adapter  │  │Adapter  │  │ Adapter  │
         └────┬────┘  └────┬────┘  └─────┬────┘
              │             │             │
    ┌─────────┼───────┐     │     ┌──────┼──────┐
    │         │       │     │     │      │      │
┌───┴──┐ ┌───┴──┐ ┌──┴──┐  │ ┌───┴──┐ ┌─┴──┐ ┌─┴──────┐
│Request│ │Resp. │ │Push │  │ │CRI   │ │CRI │ │CRI     │
│Builder│ │Disp. │ │Disp.│  │ │Parser│ │Cmd │ │DataBuf │
└───────┘ └──────┘ └─────┘  │ └──────┘ └────┘ └────────┘
                            │
                    ┌───────┴──────┐
                    │  Heartbeat   │
                    │  Manager     │
                    │ (QTimer 500ms)│
                    └──────────────┘
```

**数据流向** (所有跨线程通信均通过 Signal/Slot):
1. **上行(请求→响应)**: UI ViewModel → Signal → TcpThread RequestBuilder → TCP 9001 → 机器人 → TCP 9001 → JsonStreamParser → ResponseDispatcher → id匹配PendingRequest → 回调 → Signal → UI ViewModel
2. **推送(订阅)**: 机器人 → TCP 9001 → JsonStreamParser → ResponseDispatcher(无id+ty=publish/) → 订阅回调 → Signal → UI
3. **CRI数据(主实时源)**: 机器人 → UDP 9030 → UdpThread CriParser → 环形缓冲批量 → Signal(rad/m) → UI RobotStateStore.apply_cri_snapshot() → StateConverter → RobotStateUi(deg/mm) → 3D视图+仪表盘
4. **publish/RobotPosture(fallback)**: 仅在 CRI 未启动/断开时兜底, API 原始单位 deg/mm
5. **CRI控制**: UI → Signal → UdpThread CriCommandBuilder → UDP 9030 → 机器人
6. **心跳**: HeartbeatManager(TcpThread内QTimer, 500ms) → TCP 9001 → 机器人

### 线程模型

**Qt 铁律**: QTcpSocket / QUdpSocket 必须在创建它的线程中使用（线程亲和性），不能跨线程操作。

```
┌─ UI Thread (Main) ──────────────────────────────────────────┐
│  所有页面 (dashboard, jog_control, io_monitor, ...)          │
│  RobotStateViewModel (只读, Signal驱动刷新)                  │
│  QTimer → 60fps 3D视图刷新                                  │
│  UI 不持有任何 socket 引用                                   │
└──────────────────────────────────────────────────────────────┘
        │ Signal/Slot (Qt 自动跨线程)        │ Signal/Slot
        ▼                                    ▼
┌─ TcpThread ───────────────────┐  ┌─ UdpThread ──────────────┐
│  tcp_adapter (QTcpSocket 9001) │  │  udp_cri_adapter         │
│  tcp_script_adapter (9002)     │  │  (QUdpSocket 9030)       │
│  JsonStreamParser              │  │  cri_parser              │
│  ResponseDispatcher            │  │  CRI 数据环形缓冲区       │
│  HeartbeatManager (QTimer)     │  │                          │
│  请求/响应 PendingRequest 管理 │  │                          │
└────────────────────────────────┘  └──────────────────────────┘
```

| 线程 | 职责 | 创建对象 |
|------|------|----------|
| **UI Thread** | 页面渲染、用户交互、3D视图、状态展示 | QWidget, ViewModel, QTimer(UI刷新) |
| **TcpThread** | TCP 9001/9002 连接管理、JSON收发、请求匹配、订阅推送、心跳 | QTcpSocket, JsonStreamParser, HeartbeatManager |
| **UdpThread** | CRI 9030 数据接收、二进制解析、控制指令下发 | QUdpSocket, CriParser |

**跨线程数据流** (仅通过 Signal/Slot):
```
TcpThread → Signal(data=dict) → UI Thread: RobotState 更新
TcpThread → Signal(topic, data) → UI Thread: 订阅推送回调
UdpThread → Signal(posture, joint) → UI Thread: 3D视图动画
UdpThread → Signal(joint, speed, torque) → UI Thread: 仪表盘刷新

UI Thread → Signal(ty, db) → TcpThread: 用户操作触发请求
UI Thread → Signal(cmd) → UdpThread: CRI 控制指令
```

- 心跳 QTimer 在 TcpThread 内创建，驱动 jogHeartbeat / moveToHeartbeat / welderHeartbeat（500ms）
- UdpThread 的 CRI 数据使用环形缓冲区，避免高频 UDP 数据触发过多 Signal（合并 16ms 内的数据批量 emit）

### TCP JSON 流解析 (JsonStreamParser)

机器人 TCP 返回的 JSON 对象之间**没有换行符**，直接拼接：
```
{"id":1,"ty":"Robot/jog","db":null}{"ty":"publish/RobotPosture","db":{...}}{"id":2,...}
```
不能用 `readLine()`，必须用大括号计数或 `json.JSONDecoder.raw_decode()` 从字节流中逐个切出完整 JSON 对象。

```python
class JsonStreamParser:
    """从无分隔符TCP流中切分出完整JSON对象
    TCP 是流式协议, 一个坏字节可能导致后续 JSON 结构被悄悄改坏,
    因此 UTF-8 解码失败必须清缓冲, 不能 errors="ignore"。
    """
    _buffer: str = ""
    
    def feed(self, data: bytes) -> list[dict]:
        try:
            self._buffer += data.decode("utf-8")
        except UnicodeDecodeError:
            # TCP JSON 流出现非法字节, 流已不可信
            # 清空缓冲, 上层记录错误日志并考虑断开重连
            self._buffer = ""
            raise ProtocolError("TCP JSON UTF-8 decode failed, buffer cleared")
        
        results = []
        decoder = json.JSONDecoder()
        while self._buffer:
            self._buffer = self._buffer.lstrip()
            if not self._buffer:
                break
            try:
                obj, end = decoder.raw_decode(self._buffer)
                results.append(obj)
                self._buffer = self._buffer[end:]
            except json.JSONDecodeError:
                break  # 不完整 JSON, 等待下一波数据
        return results
```

**CRI UDP 解析** — UDP 每个 datagram 是独立包，坏帧**整帧丢弃**，不做字节级修复:

```python
# CriParser 固定配置
class CriParser:
    MASK = 0xFFFF
    # 注意: 常量名故意沿用控制器拼写 PERCISION, 不是 PRECISION
    HIGH_PERCISION = True       # Float64
    AXIS_COUNT = 6
    EXTERNAL_AXIS_COUNT = 0
    EXPECTED_SIZE = 308

# UdpCriAdapter 收到数据后先校验长度再解析
def _on_datagram(self, data: bytes):
    if len(data) != self.EXPECTED_SIZE:
        logger.debug(f"CRI bad packet size: {len(data)}, expected {self.EXPECTED_SIZE}")
        self._dropped_count += 1
        return  # 整帧丢弃
    try:
        frame = CriParser.parse(data)  # 固定配置, 不传参
        self._cri_frame_ready.emit(frame)
    except (struct.error, ValueError, IndexError) as e:
        logger.debug(f"CRI parse error: {e}")
        self._dropped_count += 1
```

### 请求/响应匹配 + 推送路由

**命令语义**: 所有命令接口都是**非阻塞**的。发送移动指令后，机器人立即返回仅表示"指令已接收"，运动是否完成需要从 CRI 数据流中监测 `isMoving` 标志位判断。因此响应匹配不承载"操作完成"语义，只承载"指令送达+有无语法错误"。

不使用 `concurrent.futures.Future`（与 Qt 事件循环不兼容），改用 QTimer 超时 + 回调的 `PendingRequest`:

```python
@dataclass
class PendingRequest:
    ty: str
    on_response: callable          # 成功回调 (msg: dict) -> None
    on_error: callable             # 错误回调 (err: RobotError) -> None
    timeout_timer: QTimer          # 超时后触发 on_error(TimeoutError)

class TcpAdapter(QObject):
    _stream: JsonStreamParser
    _pending: dict[int|str, PendingRequest]        # id → PendingRequest
    _subscriptions: dict[str, list[callable]]      # publish/<Topic> → callbacks
    _seq: int = 0
    
    def call(self, ty: str, db: dict, on_response, on_error, timeout=5.0):
        """异步发送请求。UI层只调这个，不阻塞事件循环。"""
        ...
    
    def subscribe(self, topic: str, callback: callable):
        """订阅某个主题的推送"""
        ...
    
    def _on_data(self, raw: bytes):
        for msg in self._stream.feed(raw):
            # 推送消息: 无id字段, ty以publish/开头
            if 'id' not in msg and msg.get('ty', '').startswith('publish/'):
                self._dispatch_push(msg)
                continue  # 不能return, feed()一次可能返回多个JSON对象
            # 命令响应: 有id字段, 匹配 pending
            req = self._pending.pop(msg['id'], None)
            if req is None:
                continue  # 找不到匹配的请求, 跳过本条继续处理后续消息
            req.timeout_timer.stop()
            if 'err' in msg and msg['err']:
                req.on_error(RobotError(msg['err']))
            else:
                req.on_response(msg.get('db', {}))
```

**UI 层调用示例** (通过 Service，不直接 import network/):
```python
class JogControlPage(QWidget):
    def __init__(self, motion_service: MotionService):
        self._motion = motion_service
    
    def on_jog_positive(self, axis: int):
        # Service 封装了 ty/db 拼接和心跳管理
        self._motion.jog_start(
            mode=JogMode.LINEAR,
            axis=axis,
            direction=Direction.POSITIVE,
            speed=0.5,
            coordinate_type=CoordinateType.USER,
            coordinate_id=1,
            on_started=lambda: self._status.setText("点动中"),
            on_error=lambda e: self._status.setText(f"错误: {e}")
        )
    
    def on_jog_stop(self):
        self._motion.jog_stop(
            on_stopped=lambda: self._status.setText("已停止")
        )
```

**运动完成判断** (不靠命令响应，靠 CRI 数据):

所有运动类指令（jog / moveTo / move）的响应只表示指令被机器人接收。运动实际结束需要监测 UdpThread 推送的 CRI 状态数据中的 `isMoving` 标志位：

```python
# RobotState 中由 CRI 数据流持续更新
class RobotState:
    is_moving: bool     # CRI 状态数据1 bit7: 运动中
    state: int          # 0未使能/1使能中/2空闲/3点动中/4RunTo/5拖动中
    mode: int           # 0手动/1自动/2远程
```

当 `is_moving` 从 True 翻转为 False 时，运动结束，emit `motion_finished` 信号。

### 连接状态机

```
DISCONNECTED ──connect()──→ CONNECTING ──connected──→ CONNECTED
     ↑                          │                         │
     │                          │                         │
     └────disconnect()────← DISCONNECTED ←──error/disconnected
        (自动重连: 1s/2s/4s/8s/之后每10s, 直到用户停止重连或程序关闭)
```

### 错误处理策略

| 场景 | 通道 | 处理 |
|------|------|------|
| 请求超时 | TCP 9001 | PendingRequest.timeout_timer 触发 → on_error(TimeoutError), 默认5s |
| TCP JSON UTF-8 解码失败 | TCP 9001/9002 | 清空缓冲区, 抛出 ProtocolError, 上层断开重连（不可 errors="ignore"） |
| TCP JSON 解析失败 | TCP 9001/9002 | 保留 buffer 中不完整 JSON, 等待后续数据拼接（正常粘包场景） |
| CRI UDP 长度不匹配 | UDP 9030 | 固定配置下期望 308 bytes；不匹配则整帧丢弃，记录 debug 日志，不做字节级修复 |
| CRI UDP 解析错误 | UDP 9030 | 308 bytes 但内容解析失败 → 整帧丢弃，记录日志，等下一帧 |
| CRI 配置被尝试修改 | Service/UI | 禁止。mask/highPercision/axis_count/external_axis_count 不暴露给 UI 和 public API |
| 连接断开 | TCP 9001 | emit disconnected 信号，弹出 ReconnectDialog，按 1s→2s→4s→8s→之后每10s 自动重连，直到用户点击 [停止重连并返回主页面] 或程序关闭 |
| 协议错误 | TCP 9001 | err字段非空 → 调用 on_error(RobotError(code, msg)) |
| 心跳丢失 | TCP 9001 | 机器人自动停止点动/moveTo/焊接, 无需客户端额外处理 |
| 命令队列满 | TCP 9002 | 返回 code≠0, 提示重试 |

### 重连后的状态重建

每次 TCP 9001 连接成功（包括首次连接和断线重连），**必须**按以下顺序执行状态重建。

**前提**: 只有用户本次会话中已经**手动启动过** CRI StartDataPush，才允许自动恢复。程序首次启动 / 冷启动 / 从配置文件加载后，**不允许自动恢复** CRI StartDataPush。

**执行顺序**:

```
1. 清空所有 PendingRequest
   → 断线前未完成的请求全部回调 NetworkDisconnectedError
   → 禁止继续等待旧请求响应

2. 重新发送所有 active subscriptions
   → publish/RobotStatus
   → publish/RobotPosture
   → publish/Error
   → publish/Log
   → 以及用户手动启用过的其他订阅
   → 订阅必须重新发送，禁止认为旧订阅仍然有效

3. 如果本次会话中用户已手动启用过 CRI StartDataPush → 重建 CRI 数据推送
   a. 先发送 CRI/StopDataPush（清理旧推送状态, 不做硬性成功前置条件）
   b. StopDataPush 成功、失败或超时后，都继续发送 CRI/StartDataPush
   c. StartDataPush 必须使用当前 ConnectionConfig.local_ip 和 ConnectionConfig.udp_port
   d. mask/highPercision/axis_count/external_axis_count 仍然固定，不允许 UI 修改

4. 如果本次会话中用户没有手动启用过 CRI StartDataPush
   → 连接成功后禁止自动启动 CRI 数据推送

5. 禁止自动恢复任何运动类状态
   → 禁止自动恢复 Jog
   → 禁止自动恢复 move / moveTo / move_path
   → 禁止自动恢复 CRI StartControl
   → 禁止自动上使能
   → 禁止自动运行工程
   → 禁止自动送气/送丝/退丝/焊接

6. UI 状态栏文案:
   - 首次连接成功: connected → "已连接，订阅已建立"
   - 断线重连成功: reconnected → "已重连，订阅已恢复"

7. TCP 9001 掉线弹窗与自动重连:
   - 掉线后必须立即弹窗提示用户
   - 掉线后优先自动重连，不要求用户点击"重新连接"
   - 弹窗持续显示重连状态、重连次数、下一次重连倒计时、最近错误信息
   - 弹窗只保留一个按钮: [停止重连并返回主页面]
   - 点击该按钮后停止自动重连，关闭弹窗，保持主界面打开，所有机器人功能保持禁用
   - 自动重连成功后弹窗显示"已重连"，1~2 秒后自动关闭
   - 自动重连失败时弹窗不关闭，继续显示下一次重连倒计时
   - 自动重连成功后禁止恢复任何运动类状态
   - 退避策略: 1s → 2s → 4s → 8s → 每10s，最大重连次数不限
```

**实现方式**: ConnectionManager 在 `connected` 信号触发后调用 `_rebuild_state()`：

```python
@dataclass
class SubscriptionSpec:
    topic: str          # e.g. "publish/RobotStatus"
    interval_ms: int    # tc 参数
    callback_key: str   # 回调标识

class ConnectionManager(QObject):
    _active_subs: dict[str, SubscriptionSpec]  # topic → SubscriptionSpec (持久)
    # 重连时按原 topic + interval_ms 重新发送订阅请求, 不能只保存 callback
    _cri_push_enabled: bool = False  # 本次会话中用户是否手动启用过 CRI 推送
    _cri_control_enabled: bool = False  # CRI 控制状态(无论如何不自动恢复)
    _connection_config: ConnectionConfig  # 当前连接的 IP/端口配置
    
    def _on_connected(self):
        # 1. 清空 pending
        for req in self._tcp_adapter.drain_pending():
            req.on_error(NetworkDisconnectedError("连接断开"))
        
        # 2. 重新订阅所有主题 (按原 topic + interval_ms)
        for spec in self._active_subs.values():
            self._tcp_adapter.subscribe(spec.topic, spec.interval_ms, self._get_callback(spec.callback_key))
        
        # 3. CRI 数据推送: 先 Stop 再 Start
        if self._cri_push_enabled:
            self._cri_service.stop_data_push(
                on_done=lambda: self._cri_service.start_data_push(
                    local_ip=self._connection_config.local_ip,
                    local_port=self._connection_config.udp_port
                )
            )
        
        # 4. CRI 实时控制: 不恢复, 通知用户
        if self._cri_control_enabled:
            self._cri_control_enabled = False
            logger.warning("CRI 实时控制已断开，需用户手动重新启用")
            self._status_changed.emit("CRI 实时控制需手动重新确认")
```

---

## 数据模型与单位规范

### 数据源优先级

实时状态数据有两个来源，优先级不同：

```
CRI UDP 9030 (主)          publish/RobotPosture (fallback)
      │                             │
      │ 关节角度、TCP位姿、          │ 关节点位、TCP位姿、
      │ 速度、力矩、isMoving         │ 附加轴位置
      │                             │
      ▼                             ▼
  RobotStateRaw              RobotStateRaw
  (rad / m)                  (deg / mm, API原始单位)
      │                             │
      └──────────┬──────────────────┘
                 │
                 ▼
         RobotStateUi
         (deg / mm)
```

| 数据源 | 通道 | 优先级 | 用途 |
|--------|------|--------|------|
| CRI `jointPosition` / `endPosition` / `statusData1` | UDP 9030 | **主** | 3D动画、关节显示、TCP显示、isMoving判断 |
| `publish/RobotPosture` | TCP 9001 | **fallback** | CRI 未启动或断开时兜底 |
| `publish/RobotStatus` | TCP 9001 | **必须** | 机器人型号 type、模式 mode、状态 state、仿真标志、工具号、负载号 |
| `publish/Error` | TCP 9001 | **必须** | 报警和错误显示 |
| `publish/Log` | TCP 9001 | 可选 | 系统日志 |

### 单位转换规则

CRI UDP 9030 原始数据单位与 UI / TCP JSON 命令单位不一致，必须在状态转换层统一处理。

| 数据 | CRI 原始单位 | UI 显示单位 | TCP JSON 命令单位 |
|------|-------------|-------------|-------------------|
| 关节角度 | **rad** | **deg** | **deg** |
| TCP 位置 x/y/z | **m** | **mm** | **mm** |
| TCP 姿态 rx/ry/rz | **rad** | **deg** | **deg** |
| 关节速度 | rad/s | deg/s (显示用) | — |
| TCP 速度 | m/s | mm/s (显示用) | — |
| 关节力矩 | Nm | Nm (显示用) | — |

**转换公式**:
```
joint_deg   = joint_rad × 180 / π
tcp_x_mm    = tcp_x_m × 1000
tcp_y_mm    = tcp_y_m × 1000
tcp_z_mm    = tcp_z_m × 1000
tcp_rx_deg  = tcp_rx_rad × 180 / π
tcp_ry_deg  = tcp_ry_rad × 180 / π
tcp_rz_deg  = tcp_rz_rad × 180 / π
```

**重要**: `MotionService` 发送 TCP JSON 运动指令 (`Robot/move`、`Robot/moveTo`、`Robot/apostocpos`、`Robot/cpostoapos`) 时，参数单位是 mm + deg。禁止把 CRI 的 rad/m 原始值直接填入 TCP JSON。CRI 实时控制 (`CRI/StartControl`) 若后续启用，按 CRI 协议要求使用对应单位，不与 TCP JSON 命令单位混用。

### RobotState 分层设计

禁止跨线程直接修改状态对象。采用 Raw → Ui 分层，Signal 传递 snapshot dict。

```python
@dataclass
class RobotStateRaw:
    """协议解析层写入，保存原始单位。仅 TcpThread/UdpThread 写入。"""
    # CRI 数据 (rad / m)
    joint_position: list[float] = field(default_factory=list)   # rad
    joint_velocity: list[float] = field(default_factory=list)   # rad/s
    joint_torque: list[float] = field(default_factory=list)     # Nm
    tcp_x: float = 0.0  # m
    tcp_y: float = 0.0  # m
    tcp_z: float = 0.0  # m
    tcp_rx: float = 0.0 # rad
    tcp_ry: float = 0.0 # rad
    tcp_rz: float = 0.0 # rad
    # 状态标志 (CRI statusData1/2)
    is_moving: bool = False
    is_enabled: bool = False
    is_emergency_stop: bool = False
    # RobotStatus 信息
    robot_type: str = ""
    mode: int = 0
    state: int = 0
    is_simulation: bool = False
    tool_id: int = 0
    coordinate_id: int = 0

@dataclass
class RobotStateUi:
    """UI 显示层，仅 UI 线程读取。单位 deg / mm。"""
    joint_deg: list[float] = field(default_factory=list)       # deg
    tcp_x_mm: float = 0.0   # mm
    tcp_y_mm: float = 0.0   # mm
    tcp_z_mm: float = 0.0   # mm
    tcp_rx_deg: float = 0.0 # deg
    tcp_ry_deg: float = 0.0 # deg
    tcp_rz_deg: float = 0.0 # deg
    is_moving: bool = False
    is_enabled: bool = False
    is_emergency_stop: bool = False
    robot_type: str = ""
    mode: int = 0
    state: int = 0
    is_simulation: bool = False

class StateConverter:
    """RobotStateRaw → RobotStateUi 单位转换，在 UI 线程执行"""
    @staticmethod
    def convert(raw: RobotStateRaw) -> RobotStateUi:
        rad_to_deg = lambda v: v * 57.29577951308232
        return RobotStateUi(
            joint_deg=[rad_to_deg(j) for j in raw.joint_position],
            tcp_x_mm=raw.tcp_x * 1000,
            tcp_y_mm=raw.tcp_y * 1000,
            tcp_z_mm=raw.tcp_z * 1000,
            tcp_rx_deg=rad_to_deg(raw.tcp_rx),
            tcp_ry_deg=rad_to_deg(raw.tcp_ry),
            tcp_rz_deg=rad_to_deg(raw.tcp_rz),
            is_moving=raw.is_moving,
            is_enabled=raw.is_enabled,
            is_emergency_stop=raw.is_emergency_stop,
            robot_type=raw.robot_type,
            mode=raw.mode,
            state=raw.state,
            is_simulation=raw.is_simulation,
        )

class RobotStateStore(QObject):
    """UI 线程单例。Signal 接收 snapshot dict → merge → 通知 UI"""
    raw: RobotStateRaw = field(default_factory=RobotStateRaw)
    ui: RobotStateUi = field(default_factory=RobotStateUi)
    
    changed = Signal()  # UI 刷新信号
    
    @Slot(dict)
    def apply_cri_snapshot(self, cri_data: dict):
        """UdpThread → Signal → UI Thread. 更新 raw 并转换到 ui"""
        self.raw.joint_position = cri_data.get("joint_position", [])
        self.raw.tcp_x = cri_data.get("tcp_x", 0.0)
        # ... merge 其他字段
        self.ui = StateConverter.convert(self.raw)
        self.changed.emit()
```

**数据流**:
```
UdpThread CriParser → Signal(cri_snapshot_dict) → UI Thread
                                                      │
                                          RobotStateStore.apply_cri_snapshot()
                                                      │
                                          RobotStateRaw (rad/m) 更新
                                                      │
                                          StateConverter.convert()
                                                      │
                                          RobotStateUi (deg/mm) 更新
                                                      │
                                          Signal(changed) → UI 页面刷新
```

### 模型配置自动加载

`config/robot_models.yaml` 示例:

```yaml
robots:
  S20-180-ECO-V2:
    display_name: "S20-180-ECO-V2"
    joint_count: 6
    model_type: "simple_chain"
    mesh_dir: "assets/models/S20-180-ECO-V2"
    joint_order: [J1, J2, J3, J4, J5, J6]
    raw_joint_unit: "rad"
    raw_tcp_position_unit: "m"
    raw_tcp_orientation_unit: "rad"
    ui_joint_unit: "deg"
    ui_tcp_position_unit: "mm"
    ui_tcp_orientation_unit: "deg"
    link_visual:
      base_height_mm: 180
      link_lengths_mm: [182, 425, 330, 164, 164, 180.5]
      joint_radius_mm: 35

  default_6axis:
    display_name: "Generic 6-Axis Robot"
    joint_count: 6
    model_type: "simple_chain"
    joint_order: [J1, J2, J3, J4, J5, J6]
    raw_joint_unit: "rad"
    raw_tcp_position_unit: "m"
    raw_tcp_orientation_unit: "rad"
    ui_joint_unit: "deg"
    ui_tcp_position_unit: "mm"
    ui_tcp_orientation_unit: "deg"
```

**加载流程**:
1. 连接机器人 → 订阅 `publish/RobotStatus` → 收到 `db.type`
2. 根据 `type` 查找 `robot_models.yaml` 中对应配置
3. 找不到 → 使用 `default_6axis`
4. `view3d/robot_model.py` 读取配置中的 `link_visual` 构建 3D 模型
5. 关节动画由 CRI `jointPosition` (单位 rad, 但模型内部自行处理) 驱动

---

## 关键技术难点

| 难点 | 解决方案 |
|------|----------|
| **TCP JSON 裸连无分隔符** | JsonStreamParser: raw_decode / 大括号计数, 缓冲区累积+切分 |
| **同一连接混推请求与推送** | 按是否含id字段路由: 有id→PendingRequest匹配, 无id→publish/订阅回调 |
| **CRI 固定协议解析** | mask=0xFFFF, highPercision=true, 6轴, 无外部轴, 308字节固定帧长。长度不匹配直接丢弃 |
| **三通道协同** | TCP 9001/9002 共享 ConnectionManager, UDP 9030 独立管理 |
| **RobotState 跨线程安全** | RobotStateStore 仅 UI 线程拥有; TcpThread/UdpThread 通过 Signal 发 snapshot dict; UI 线程 merge; 禁止加锁后跨线程直接写 |
| **CRI与TCP JSON单位不一致** | RobotStateRaw(rad/m) → StateConverter → RobotStateUi(deg/mm); MotionService 使用 mm/deg 拼 TCP JSON 指令 |
| **CRI数据源优先, RobotPosture兜底** | CRI 作为主实时源; publish/RobotPosture 仅在 CRI 未启动/断开时回退 |
| **多型号模型加载** | robot_models.yaml 按 RobotStatus.type 加载; 未知型号回退 default_6axis; 不靠 DH 参数推导尺寸 |
| **3D 性能** | VBO/VAO 渲染, CRI数据变化时才更新, 非连续重绘 |
| **跨平台差异** | PySide6 统一抽象, 避免平台特定 API |

## 实现时临时增加需求

> 以下需求在实施过程中由用户临时提出，不在原始计划中，但已实现。后续 Part 必须兼容。

| 日期 | 来源 Part | 需求 | 说明 |
|------|-----------|------|------|
| 2026-05-10 | Part 1A | 菜单栏 + 关于对话框 | 帮助 → 关于，版本号 v2.0.0 |
| 2026-05-10 | Part 1A | 样式切换菜单 | 7 种预设: 科技蓝/暗夜黑/工业灰/活力橙/清新绿/明亮/跟随系统。使用 `QMainWindow.setStyleSheet()` 全量替换，对后续所有页面生效。`跟随系统` 清除 stylesheet |
| 2026-05-10 | Part 1C | HTTP/WS 不独立成页 | HTTP 和 WebSocket 是上传功能的通讯手段，不是独立页面。已从 PAGE_REGISTRY 移除，对应的 http_client / websocket_client 在 network/ 中后续实现。上传页移到程序后 |
| 2026-05-10 | Part 1D | GlobalCommandBar 按钮重设计 | 上使能→椭圆形开关(未使能⇄已使能)；清错→移到弹窗(Part 5 订阅 Error 后弹出，只能由清错按钮关闭)；停止点动→删除(Jog松开自动stopJog)；暂停/恢复运动→toggle；手动/自动/远程→三挡位椭圆开关；仿真/实机→右侧椭圆开关；启动/暂停/停止→带图标圆形按钮(▶⏸⏹)，暂停且检测到工程暂停时变成恢复 |
| 2026-05-10 | Part 5 | 去离线模式 | 删除登录页"离线模式"按钮，只能通过真实TCP连接进入主界面 |
| 2026-05-10 | Part 5 | 连接失败弹窗 | QTcpSocket.errorOccurred 驱动，不盲等超时。IP不对/端口不通/机器人不在线时弹窗提示真实错误原因，停留在登录页 |
| 2026-05-10 | Part 5 | 点击连接不立即跳转 | 登录页点连接后停留在登录页显示"连接中..."，只有 `connection_state_changed("connected")` 才切换到主界面 |
| 2026-05-10 | Part 5 | 状态信息分布 | RobotStatus订阅数据分散到: 型号→抽屉, 模式→状态栏+底部栏, 使能→底部栏开关, 仿真→底部栏开关。HomePage简化为占位 |
| 2026-05-10 | Part 5 | 连接超时 3s | 首次连接设 3s QTimer 超时。超时未连上→弹窗"连接超时"→回登录页。socket 级 errorOccurred 优先触发（不等满3秒）。连上后取消计时器 |
| 2026-05-10 | Part 5 | 线程清理 | TcpThread 关闭用 `quit()`+`wait(3000)` 等线程退出，解决 "QThread: Destroyed while thread is still running" 错误 |
| 2026-05-10 | Part 5 | 登录页 UI 控件 | 加了 `set_status(text)` 和 `set_enabled(bool)` 方法供 main.py 在连接过程调用 |
| 2026-05-10 | Part 5 | 返回登录页未恢复按钮 | `on_return_to_login` 加 `login.set_enabled(True)` + `login.set_status("准备连接")`，否则按钮一直禁用 |
| 2026-05-10 | Part 5 | 补 RobotPosture 订阅 | 连接后增加 `publish/RobotPosture`(tc=200) → 抽屉关节角+TCP位姿, CRI 未启动前的 fallback |
| 2026-05-10 | Part 5 | 补 ProjectState 订阅 | 连接后增加 `publish/ProjectState`(tc=500) → `command_bar.set_project_paused()` |
| 2026-05-10 | Part 5 | 订阅间隔 100ms | 5 个订阅请求用 `QTimer.singleShot(i*100)` 间隔发送, 避免一口气发出被机器人丢弃 |
| 2026-05-10 | Part 5 | 日志系统 | `core/logger.py`: 追加模式, 文件名 `YYYYMMDD.txt`。每次启动写 `====...====` 分割线。超过 1MB 自动切 `_1.txt`。终端只显示 WARNING+, 收发全量写文件。recv 记录原始 JSON 原文 |
| 2026-05-10 | Part 5 | 连接后切模式再订阅 | 连接成功 → `Robot/toAuto` → 100ms → `Robot/toRemote` → 订阅。机器人要求远程模式才能接收订阅, 否则返回 err 10074 |
| 2026-05-10 | Part 5 | 订阅 tc 全部为 0 | 硬性要求: 所有 `publish/*` 订阅请求的 `tc` 字段必须为 0 |
| 2026-05-10 | Part 5 | 去 QTimer 跨线程 | `PendingRequest` 不再持有单个 QTimer, 改用 `time.monotonic()` + TcpAdapter 内 1s 周期 QTimer 统一检查超时, 避免跨线程 stop timer |
| 2026-05-10 | Part 10 | 运动节点编排功能 | Part 10 原方向为表单式运动指令页(movJ/L/C/Circle/path)，现改为节点连线式编排器（类 ComfyUI）。详细 14 阶段计划见 `plan2.md`。运动页面复用现有"运动"标签页，不新增重复顶层标签。初期只做运动编排，不强依赖焊接/写字 |

---

## 实施进度

| Part | 状态 | 关键产出 |
|------|------|----------|
| Part 0 | ✅ | `main.py`(空窗口), `requirements.txt` |
| Part 1A | ✅ | `app/main_window.py`(四区骨架), 菜单栏(帮助→关于v2.0.0 + 样式7套QSS), `app/widgets/status_bar.py`, QSettings持久化 |
| Part 1B | ✅ | `app/base_page.py`, `app/page_registry.py`(7页延迟导入), `app/page_router.py`(懒加载), 9个占位页 |
| Part 1C | ✅ | `app/widgets/top_tab_bar.py`(滚轮横向滚动+PageRouter集成), MainWindow集成TopTabBar |
| Part 1D | ✅ | `app/widgets/global_command_bar.py`(椭圆使能开关+三挡位模式+工程按钮), ErrorDialog弹窗 |
| Part 1E | ✅ | `app/widgets/robot_control_drawer.py`(悬浮抽屉+J1-J6/XYZ±/坐标系/位姿显示), MainWindow集成 |
| Part 2 | ✅ | `config/robot_models.yaml`(S20-180-ECO-V2+default_6axis), `core/robot_model_config.py`(YAML加载器) |
| Part 3 | ✅ | `core/robot_state.py`(Raw/Ui/Store), `core/unit_converter.py`(rad↔deg, m↔mm) |
| Part 4 | ✅ | `network/protocol/json_stream.py`(raw_decode strict UTF-8), `request.py`(threading.Lock), `response.py`, `errors.py` |
| Part 4.5 | ✅ | `app/pages/login_page.py`(IP/网卡/UDP端口→connect_requested Signal), `core/connection_config.py`, `app/widgets/network_interface_selector.py` |
| Part 5 | ✅ | `network/tcp_adapter.py`(纯网络层@Slot, data_received+shutdown_finished), `network/connection_manager.py`(UI线程请求/响应/订阅分发, 自动重连1s→2s→4s→8s→10s, 掉线弹窗), `app/widgets/reconnect_dialog.py`, 连接后toAuto→toRemote→5订阅 |
| Part 6 | ✅ | `network/udp_cri_adapter.py`, `network/protocol/cri_parser.py`(308B固定解析), `services/cri_service.py`(bind→Stop→Start), `core/thread_manager.py`新增UdpThread |
| Part 7 | ✅ | 连接→command_bar+drawer按钮启用; isMoving→运动暂停/恢复; ErrorDialog弹窗(只能清错关闭); 空Error(db=[])不弹窗不写日志; HomePage保持占位(状态全在底部栏和抽屉显示) |
| Part 8 | ✅ | 使能开关→switchOn/Off; 模式三挡→toManual/Auto/Remote; 仿真开关→toSimulation/Actual; 运动控制→stopMove/pause/resume; 工程按钮→runByIndex(1)/stop/pause/resume; Jog: jog_pressed(mode,idx,sign)→jog+jogHeartbeat(500ms), jog_released→stopJog停心跳; moveTo: moveto_pressed(0-3)→Robot/moveTo+moveToHeartbeat(500ms), moveto_released→停心跳; 速度滑块松开→setManualMoveRate→100ms→setAutoMoveRate; 连接后自动发速度70%; 反馈循环防护(set_checked_silent); 心跳send/recv不写日志; stop_move同时停jog和moveTo心跳 |
| Part 9 | ✅ | Jog/moveTo 改为 pressed/released 双信号模式, 抽屉 API 重构(jog_pressed/jog_released/moveto_pressed/moveto_released), _on_moveto_start_error 错误处理 |
| Part 10 | ⏳ | 运动页已有 `app/pages/motion_page.py`(当前为表单式占位，按钮未绑定API)。新方向: 改为节点连线式编排器，详见 `plan2.md`。阶段 0 已完成(plan.md 同步)。阶段 1 待开始 |
| Part 10-Node | ⏳ | 运动节点编排 14 阶段计划(plan2.md): 阶段0文档同步✅ → 阶段1占位区✅ → 阶段2画布✅ → 阶段2.5三栏布局✅ → 阶段3节点拖拽✅ → 阶段4连线✅ → 阶段5保存加载✅ → 阶段5.5校验✅ → 阶段6属性面板✅ → 阶段7实时状态✅ → 阶段8 DryRun✅ → 阶段9在线运动✅(暂停) → 数据模型修复✅(2026-05-11) → 阶段10 IO/寄存器✅(2026-05-11) → 阶段11 If节点✅(2026-05-11, 执行模型重构: 线性路径→图遍历) → 阶段12 Path/MoveC/MoveCircle✅(2026-05-11) → 阶段13自定义节点 → 阶段14完善 |
| 数据模型修复 | ✅ | 全局变量(VarDef.var_id), flow主线唯一连接, 拖节点插入主线, Wait→duration_ms, Position显示名, 变量端口统一value, GetVar加载重建(plan2.md §30) |
| Part 11-15 | ⏳ | 见计划 |
| CRI 配置 | ✅ | duration=2ms(500Hz), mask=0xFFFF, highPercision=true, 6轴, 308B |

### Part 8 按钮绑定全表

| 按钮 | 位置 | API |
|------|------|-----|
| 使能开关 ON/OFF | GlobalCommandBar | `Robot/switchOn`/`switchOff` |
| 手动/自动/远程 | GlobalCommandBar | `Robot/toManual`/`toAuto`/`toRemote` |
| 仿真/实机 | GlobalCommandBar | `Robot/toSimulation`/`toActual` |
| 停止运动 | GlobalCommandBar | `Robot/stopMove` |
| 暂停/恢复运动 | GlobalCommandBar | `Robot/pause`/`Robot/resume` |
| Home/安全/蜡烛/打包 | GlobalCommandBar | `Robot/moveTo type=0/1/2/3`(无target)+moveToHeartbeat(500ms) |
| 启动/暂停/停止工程 | GlobalCommandBar | `project/runByIndex(1)`/`pause`/`stop` |
| 点动 +/- (pressed) | RobotControlDrawer | `Robot/jog`+jogHeartbeat(500ms) |
| 点动 (released) | RobotControlDrawer | `Robot/stopJog`+停jogHeartbeat |
| moveTo (pressed) | RobotControlDrawer | `Robot/moveTo {"type":N}`+moveToHeartbeat(500ms) |
| moveTo (released) | RobotControlDrawer | 停moveToHeartbeat |
| 停止运动 | GlobalCommandBar | 同时停jog和moveTo心跳 |
| 速度滑块 | RobotControlDrawer | 松开发→`setManualMoveRate`→100ms→`setAutoMoveRate` |
| 清错 | ErrorDialog弹窗 | `System/clearError` |

### 心跳管理

| 心跳 | 周期 | 启动 | 停止 |
|------|------|------|------|
| jogHeartbeat | 500ms | jog_pressed | jog_released / stop_move |
| moveToHeartbeat | 500ms | moveto_pressed 响应成功 | moveto_released / stop_move |

### 反馈循环防护

`_ToggleSwitch.set_checked_silent()` 用 `blockSignals(True/False)` 防止 `RobotStatus` 同步状态时触发 `toggled` 反复下发命令。 |
| Part 9-15 | ⏳ | 见计划 |

### RobotControlDrawer 信号 API

| 信号 | 参数 | 触发时机 | main.py 连接 |
|------|------|----------|-------------|
| `jog_pressed` | (mode, index, sign) | 点动按钮按下 | `_on_jog_pressed` → jog + jogHeartbeat.start |
| `jog_released` | — | 点动按钮松开 | `_on_jog_stop` → stopJog + jogHeartbeat.stop |
| `moveto_pressed` | (move_type: 0-3) | moveTo 按钮按下 | `_on_moveto_pressed` → moveTo + moveToHeartbeat.start |
| `moveto_released` | — | moveTo 按钮松开 | `_on_moveto_released` → moveToHeartbeat.stop |
| `speed_rate_changed` | (rate: 1-100) | 速度滑块松开 | `_on_speed_changed` → setManualMoveRate→100ms→setAutoMoveRate |

### 左侧示教器抽屉数据绑定

| 数据源 | 订阅/通道 | 频率 | → 抽屉方法 | 显示 |
|--------|----------|------|-----------|------|
| `RobotStatus.db.type` | publish(首次) | 一次 | `set_robot_model(text)` | 型号标签 |
| `RobotStatus.db.CoordinateId` | publish | 变更推送 | `set_world_coordinate(f"坐标系{id}")` | 顶部坐标系行 |
| `RobotStatus.db.ToolId` | publish | 变更推送 | `set_tool_coordinate(f"工具{id}")` | 顶部坐标系行 |
| `RobotPosture.db.joint` | publish, tc=0 | 变更推送 | `update_joint_display([deg])` | 关节点动页 6 值标签 |
| `RobotPosture.db.end.{x,y,z,a,b,c}` | publish, tc=0 | 变更推送 | `update_tcp_display(x,y,z,a,b,c)` | 坐标系点动页 6 值标签 |
| CRI `jointPosition` (rad) | UDP 308B | 1ms | `update_joint_display(rad→deg)` | 同上 (主数据源, 精度更高) |
| CRI `endPosition` (m+rad) | UDP 308B | 1ms | `update_tcp_display(m→mm, rad→deg)` | 同上 |

**数据优先级**: CRI UDP > publish/RobotPosture。两者都更新同一个 UI, CRI 数据覆盖 RobotPosture 数据。

### 当前架构关键文件

| 文件 | 线程 | 职责 |
|------|------|------|
| `main.py` | UI | LoginPage+MainWindow+ConnectionManager+CriService+全部按钮绑定+心跳管理 |
| `app/widgets/robot_control_drawer.py` | UI | 左侧示教器: jog_pressed(mode,index,sign)/jog_released, moveto_pressed(0-3)/moveto_released, speed_rate_changed |
| `app/widgets/global_command_bar.py` | UI | 底部操作栏+moveTo按钮, _ToggleSwitch防反馈, ErrorDialog |
| `network/tcp_adapter.py` | TcpThread | @Slot: connect/send/shutdown, Signal: data_received→UI |
| `network/connection_manager.py` | UI | pending, 响应/推送分发, 自动重连, send_call/send_subscribe |
| `network/udp_cri_adapter.py` | UdpThread | @Slot: bind, 308B校验+解析, Signal: datagram_received→UI |
| `services/cri_service.py` | UI | bind→StopDataPush→StartDataPush 序列 |

---

## QWidget 组件设计规范 (Part 1E 复盘)

> 从 RobotControlDrawer 改版中总结。以后所有 QWidget 组件按此标准。

### 布局

| 原则 | 做法 |
|------|------|
| 不用外部独立按钮 | 用 QHBoxLayout: 左侧窄栏(sidebar) + 右侧内容(content) |
| QSS 作用域 | 每个区域用 QFrame + `setObjectName("xxx")`, QSS 用 `#xxx {}` 选择器 |
| 展开/收起 | `geometry` QPropertyAnimation, 200ms OutCubic |
| 内容延迟隐藏 | 收起动画 `_anim.finished` 信号连接 `_hide_content_after_collapse` |

### 信号连接

| 原则 | 做法 |
|------|------|
| 动画 finished 防重复 | 用 `_xxx_connected` bool 旗标 + `_disconnect_anim_finished()` 先断开再连接 |
| 信号/槽异常保护 | `try/except (TypeError, RuntimeError)` 包裹 disconnect |

### 显示更新

| 原则 | 做法 |
|------|------|
| 浮点数转换 | `try/except (TypeError, ValueError)` 兜底, 失败显示 `"--"` |

### MainWindow 定位子组件

| 原则 | 做法 |
|------|------|
| 坐标映射 | `child.mapTo(self, QPoint(0,0))` 得到子组件在 MainWindow 的坐标 |
| 延迟定位 | `QTimer.singleShot(0/30/100, ...)` 三次, 处理布局初始化和 resize 后的落位延迟 |
| 置顶 | 每次定位后 `child.raise_()` 确保不被 PageStack 遮挡 |
| 子组件 API | 组件提供 `is_expanded()`, `expanded_width()`, `collapsed_width()` 给 MainWindow 布局用 |

### 代码组织

| 原则 | 做法 |
|------|------|
| UI 构建分离 | `_build_sidebar() → QFrame`, `_build_content() → QFrame`, 各返回独立 QFrame |
| 工具方法 | `_add_separator(layout)`, `_add_section_title(layout, text)` 减少重复 |

---

## 待补充/待确认的问题

1. ~~**自定义协议的具体帧格式**~~ → 已确认: JSON over TCP(9001/9002), Binary over UDP(9030)
2. ~~**UR6 的 DH 参数**~~ → 已确认第一版不需要。模型尺寸从 robot_models.yaml 配置加载，不通过 DH 推导
3. **是否需要示教器功能** — 路径记录+回放
4. **是否需要实时曲线图** — 关节数据随时间变化的波形图(pyqtgraph)
5. **机器人具体型号** — S20-180-ECO-V2(从RobotStatus推送中获取), 需确认关节数
6. **是否需要适配真实UR控制柜** — 当前为Codroid机器人API, 如需UR需适配Dashboard/RTDE协议
