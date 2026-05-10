# Codroid 机器人控制终端 — 架构文档

## 项目概述

PySide6 桌面应用，通过 TCP/UDP 与 Codroid 协作机器人控制器通信。
版本 v2.0.0，当前处于 Part 5 (TCP 9001 只读连接) 阶段。

## 目录结构

```
robot_ui/
├── main.py                          # 入口, 组装 LoginPage + MainWindow + ConnectionManager
├── requirements.txt                 # PySide6, PyOpenGL, numpy, psutil, PyYAML
├── config/
│   └── robot_models.yaml            # 机器人型号配置(S20-180-ECO-V2 + default_6axis)
├── app/
│   ├── main_window.py               # 主窗口: TopTabBar + PageStack + Drawer + GlobalCommandBar
│   ├── base_page.py                 # 页面基类 (on_enter/on_leave/on_connection_changed)
│   ├── page_registry.py             # PageSpec + PAGE_REGISTRY (7个功能页)
│   ├── page_router.py               # 懒加载路由器
│   ├── styles/                      # 7套 QSS 主题
│   ├── pages/
│   │   ├── login_page.py            # 登录页: IP/网卡/UDP端口 → connect_requested Signal
│   │   ├── home_page.py             # 首页 (占位)
│   │   ├── welding_page.py          # 焊接页 (占位)
│   │   ├── writing_page.py          # 写字页 (占位)
│   │   ├── upload_page.py           # 上传页 (占位)
│   │   ├── io_monitor.py            # IO 监控 (占位)
│   │   ├── program_editor.py        # 程序编辑器 (占位)
│   │   ├── settings.py             # 设置 (占位)
│   │   ├── http_tools_page.py       # HTTP 工具 (占位)
│   │   └── websocket_tools_page.py  # WebSocket 工具 (占位)
│   └── widgets/
│       ├── top_tab_bar.py           # 顶部标签栏 (滚轮横向滚动)
│       ├── global_command_bar.py    # 底部操作栏 (椭圆开关/三挡位/圆形按钮)
│       ├── robot_control_drawer.py  # 可收缩运动控制抽屉
│       ├── status_bar.py            # 底部状态栏
│       ├── reconnect_dialog.py      # 掉线重连弹窗
│       ├── network_interface_selector.py  # 网卡下拉选择器
│       ├── console_widget.py        # 日志窗口 (预留)
│       ├── joint_slider.py          # 关节滑块 (预留)
│       └── led_indicator.py         # LED 指示灯 (预留)
├── core/
│   ├── connection_config.py         # ConnectionConfig + LocalNetworkInterface
│   ├── robot_state.py               # RobotStateRaw + RobotStateUi + StateConverter + Store
│   ├── robot_model_config.py        # YAML 模型加载器
│   ├── unit_converter.py            # rad↔deg, m↔mm
│   ├── thread_manager.py            # TcpThread (QThread)
│   ├── kinematics.py               # FK/IK (预留, 非实时链路)
│   ├── event_bus.py                # 事件总线 (预留)
│   └── logger.py                    # 彩色终端 + 文件日志, 1MB切分
├── network/
│   ├── tcp_adapter.py               # TcpAdapter: 纯网络层, @Slot 在 TcpThread 执行
│   ├── connection_manager.py        # ConnectionManager: UI线程, 请求/响应/订阅分发
│   ├── http_client.py              # HTTP 9198 (预留)
│   ├── websocket_client.py         # WebSocket 9000 (预留)
│   └── protocol/
│       ├── json_stream.py           # JsonStreamParser: raw_decode, strict UTF-8
│       ├── request.py               # RequestBuilder (线程安全, threading.Lock)
│       ├── response.py              # ResponseDispatcher (当前未使用, TcpAdapter 不再持有)
│       └── errors.py               # ProtocolError / RobotError / NetworkDisconnectedError
├── services/
│   ├── robot_service.py            # RobotService (部分废弃, 改用 cm.send_subscribe)
│   ├── project_http_service.py     # 9198 REST (预留)
│   ├── project_map_service.py      # 9000 WS (预留)
│   ├── http_service.py             # (预留)
│   └── websocket_service.py        # (预留)
├── view3d/                          # OpenGL 3D 渲染 (后续 Part)
└── log/                             # 日志文件 YYYYMMDD.txt
```

## 线程模型

```
┌─ UI Thread (主线程) ─────────────────────────────────────┐
│  QApplication, MainWindow, LoginPage, 所有 QWidget        │
│  ConnectionManager (请求管理/响应分发/订阅回调/重连/弹窗)   │
│  RobotStateStore, PageRouter, 所有 Service                 │
│                                                           │
│  _sig_connect ──→ queued ──→ TcpAdapter.connect_to_host   │
│  _sig_send    ──→ queued ──→ TcpAdapter.send_message      │
│  _sig_shutdown──→ queued ──→ TcpAdapter.shutdown          │
│                                                           │
│  TcpAdapter.connected       ←── queued ──                 │
│  TcpAdapter.disconnected    ←── queued ──                 │
│  TcpAdapter.connection_error←── queued ──                 │
│  TcpAdapter.data_received   ←── queued ──                 │
│  TcpAdapter.shutdown_finished←── queued ──                │
└───────────────────────────────────────────────────────────┘
                         │
┌─ TcpThread ──────────────────────────────────────────────┐
│  TcpAdapter (QObject, moveToThread)                       │
│    QTcpSocket (在此线程创建和操作)                          │
│    JsonStreamParser (纯Python, 在此线程调用)               │
│    QTimer (超时检查, 在此线程创建)                          │
│                                                           │
│  @Slot(str,int) connect_to_host  — 创建 QTcpSocket        │
│  @Slot(str)    send_message      — socket.write           │
│  @Slot()       shutdown          — stop/abort/deleteLater │
│  @Slot()       disconnect_from_host                       │
└───────────────────────────────────────────────────────────┘
```

### 线程安全铁律

1. **跨线程 Signal 全用 `Signal(object)`** — 禁止 `Signal(dict)`/`Signal(list)`。str/bool/int/无参除外
2. **回调不入 TcpThread** — `on_response`/`on_error`/订阅回调全部在 ConnectionManager(UI线程) 保存和调用
3. **socket/timer 清理在 @Slot** — `stop()`/`abort()`/`deleteLater()` 封装在 `TcpAdapter.shutdown()` @Slot
4. **shutdown 必须等完成** — `shutdown()` 完成后 emit `shutdown_finished`，ConnectionManager 才 `thread.wait()`
5. **每次重连清理旧连接** — `_cleanup_thread()` 断开旧 signal 再建新线程

## 数据流

### TCP 连接建立

```
LoginPage.connect_requested.emit(config)
  → main.on_connect → cm.connect_to_robot(config)
    → _do_connect
      → _cleanup_thread (断开旧线程)
      → new TcpThread + TcpAdapter, moveToThread
      → wire signals (sig_xxx → adapter @Slots, adapter.signals → cm handlers)
      → thread.started → _sig_connect.emit(ip, 9001)
      → TcpAdapter.connect_to_host @Slot (TcpThread)
        → QTcpSocket() 创建
        → connectToHost
```

### 命令请求/响应

```
cm.send_call(ty, db, on_response, on_error)
  → UI线程: _seq++, 保存 PendingRequest{ty, on_response, on_error, created_at, timeout}
  → json.dumps({id, ty, db})
  → _sig_send.emit(msg)
  → queued → TcpAdapter.send_message @Slot (TcpThread)
    → socket.write(msg)

... 机器人响应到达 ...

TcpAdapter._on_ready_read (TcpThread)
  → JsonStreamParser.feed → [msg, ...]
  → data_received.emit(msg)
  → queued → ConnectionManager._on_data_received (UI线程)
    → msg 有 id → _dispatch_response
      → _pending.pop(id) → req["on_response"](db) 或 req["on_error"](err)
    → msg 无 id 且 ty=publish/* → _dispatch_publish
      → named handler 或 _subscribe_callbacks[topic] 遍历
```

### 订阅推送

```
cm.send_subscribe(topic, callback)
  → UI线程: _subscribe_callbacks[topic].append(callback)
  → _sig_send.emit({"ty": topic, "tc": 0})
  → queued → TcpAdapter.send_message @Slot (TcpThread)
    → socket.write(...)

... 机器人推送 publish/xxx ...

TcpAdapter._on_ready_read → data_received.emit(msg)
  → queued → ConnectionManager._on_data_received (UI线程)
    → _dispatch_publish
      → RobotStatus → _on_robot_status (named handler)
      → 其他 → _subscribe_callbacks[topic] 遍历回调
```

### 超时检查

```
TcpAdapter QTimer(1000ms) → data_received.emit({"_internal": "check_timeouts"})
  → queued → ConnectionManager._on_data_received
    → _check_timeouts: time.monotonic() 对比, 超时 → req["on_error"](TimeoutError)
```

### 断线清理

```
cm.disconnect()
  → _drain_pending(NetworkDisconnectedError)  // 失败所有 pending
  → _sig_shutdown.emit()
  → queued → TcpAdapter.shutdown @Slot (TcpThread)
    → timer.stop/deleteLater
    → socket.abort/deleteLater
    → shutdown_finished.emit()
  → queued → thread.quit()
  → cm 等待 thread.wait(3000)
```

## 连接后自动化流程

```
TCP connected
  → cm.send_call("Robot/toAuto", {}, ...)
  → on_response → 100ms → cm.send_call("Robot/toRemote", {}, ...)
  → on_response → 订阅5个主题 (100ms间隔):
      publish/RobotStatus  (tc=0) → 状态栏+底部栏+型号加载
      publish/RobotPosture  (tc=0) → 抽屉关节角+TCP位姿 (CRI前fallback)
      publish/ProjectState  (tc=0) → 工程按钮组状态
      publish/Error         (tc=0) → 状态栏showMessage (去重, 不弹窗)
      publish/Log           (tc=0) → 日志收集
```

## UI 布局

```
┌──────────────────────────────────────────────────┐
│ TopTabBar: 首页|焊接|写字|IO|程序|上传|设置        │
├──────────────────────────────────────────────────┤
│              PageStack (QStackedWidget)           │
│   ┌──────────────────────┐                       │
│   │ RobotControlDrawer   │ ← 可收缩悬浮抽屉       │
│   └──────────────────────┘                       │
├──────────────────────────────────────────────────┤
│ GlobalCommandBar: [使能开关] [停止] [暂停/恢复]    │
│   [启动] [暂停工程] [停止工程]  [仿真开关] [手动|自动|远程] │
└──────────────────────────────────────────────────┘
```

### UI 区域职责矩阵

| 区域 | 放什么 | 不放什么 |
|------|--------|----------|
| TopTabBar | 功能页标签 | Jog 按钮 |
| PageStack | 当前功能模块 | 全局急停 |
| RobotControlDrawer | Jog/关节/TCP/坐标系/Jog速度 | 送气/送丝/退丝/试运行 |
| GlobalCommandBar | 使能/清错/停止/模式切换/工程控制 | 焊接工艺按钮 |
| WeldingPage | 试运行/送气/送丝/退丝/焊接参数 | 通用模式切换 |

## 单位规范

| 数据 | CRI(UDP) | publish/TCP | UI 显示 | TCP JSON 命令 |
|------|----------|-------------|---------|---------------|
| 关节角 | rad | deg | deg | deg |
| TCP xyz | m | mm | mm | mm |
| TCP rpy | rad | deg | deg | deg |

CRI 是主实时源, publish/RobotPosture 是 fallback。

## 日志

- 终端: WARNING 级别 (只显错误/警告)
- 文件: log/YYYYMMDD.txt, DEBUG 全量, `[send]`/`[recv]` 前缀, recv 原始 JSON
- 启动分割线 `==== 2026-05-10 13:14:05 ====`
- 超过 1MB 自动切 `_1.txt`, `_2.txt`

## CRI UDP 固定配置 (Part 6 实现)

| 参数 | 固定值 |
|------|--------|
| mask | 0xFFFF |
| highPercision | true (注意拼写) |
| axis_count | 6 |
| external_axis_count | 0 |
| 帧长 | 308 bytes |

## 关键设计决策记录

1. **不用 concurrent.futures.Future** — 改为 UI 线程保存 dict + time.monotonic() 超时检查
2. **TcpAdapter 是纯网络层** — 不持有 RequestBuilder/ResponseDispatcher, 不调用业务 callback
3. **RequestBuilder/ResponseDispatcher 保留但未使用** — 连接管理器直接在 UI 线程管理 pending
4. **登录页无离线模式** — 只允许 TCP 连接进入主界面
5. **连接后自动 toAuto→toRemote→订阅** — 设计师要求的两步切换
6. **订阅 tc=0** — 避免高频推送
7. **订阅请求间隔 100ms** — QTimer.singleShot(i*100) 逐个发送
8. **样式切换用 QSettings 持久化** — 7套主题 + 跟随系统
