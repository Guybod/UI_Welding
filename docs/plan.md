# Codroid UI — 功能规划与交接

> 文档版本：2026-05-21  
> 与 `ARCHITECTURE.md`、`planAPI.md` 并列；描述**已完成 / 进行中 / 待做**及分 part 验收标准。  
> 机器人协议字段以 **[planAPI.md](planAPI.md)** 为准，禁止凭空假设接口。

---

## 目录

1. [项目总览（摘要）](#1-项目总览摘要)
2. [当前进行中：CRI/UDP 预警与订阅位姿兜底](#2-当前进行中criudp-预警与订阅位姿兜底)
3. [历史约束（仍有效）](#3-历史约束仍有效)
4. [文档索引](#4-文档索引)

---

## 1. 项目总览（摘要）

- **技术栈**：Python 3.11 + PySide6；TCP :9001；CRI 数据推送（本地 UDP bind + `CRI/StartDataPush`）；CRI 轨迹控制 UDP :9030。
- **架构说明**：见 [ARCHITECTURE.md](ARCHITECTURE.md)。
- **全局运动**：Jog / moveTo 为按住式 + 500ms 心跳；连接后默认速度 70%。
- **状态缓存**：`services/robot_realtime_state.py`（`RobotRealtimeState` 单例）。

---

## 2. 当前进行中：CRI/UDP 预警与订阅位姿兜底

**状态**：**核心已实现**（2026-05-21；仅位姿获取相关代码；UI 芯片四态/状态栏弹窗未做）

### 2.1 任务目标

当 **CRI 已请求数据推送（`StartDataPush`）但长时间收不到 UDP 帧**，或 **本地 UDP bind 失败** 时：

1. **明确预警**：用户能区分「CRI 正常」「等待首帧」「UDP 无数据、订阅兜底」「绑定失败」；
2. **位姿兜底**：用 TCP 订阅 `publish/RobotPosture` 写入统一状态缓存，供 **3D 预览、关节/TCP 标签、工作空间「从当前位置读取」** 等使用；
3. **安全分级**：**CRI 轨迹执行 / 起点核对 / UDP 探针** 仍要求 **CRI UDP 为权威源**，订阅兜底不得静默进入执行闭环。

### 2.2 现状（已实现 vs 缺失）

| 能力 | 现状 | 位置 |
|------|------|------|
| 订阅 `publish/RobotPosture` | 已订阅 | `app/signal_binder.py` `_bind_subscriptions` |
| CRI 未就绪时 3D 用订阅关节驱动 | 已实现 `drive_model=not cri_ok` | `_on_robot_posture` |
| CRI 未就绪时更新 TCP 文本 | 已实现 | `_on_robot_posture` |
| 首页芯片「CRI / CRI关」 | 二值，语义不足 | `home_page.update_cri_status` |
| `RobotRealtimeState` 写入 | **仅** `update_from_cri_frame`（UDP） | `robot_realtime_state.py` |
| 焊接/绘图「从当前位置读取」 | 仅 `is_valid()`，无 UDP 则日志警告并返回 | `welding_page` / `writing_page` |
| UDP 超时看门狗 | **无** | — |
| `bind_error` UI | **无**（仅日志） | `cri_service.py` |
| `cri_started` 即亮 CRI 芯片 | **假绿**（推送已发、尚无帧） | `signal_binder._on_cri_started` |
| 登出时 `cri_svc.stop()` | **缺失**（仅 `disconnect`） | `signal_binder._bind_login_flow` |

**核心矛盾**：`_cri_pose_active()` = `cri_svc.is_enabled ∧ RobotRealtimeState.is_valid()`，但 `is_valid` 只在收到 UDP 后置真；`cri_started` 又把首页标为 CRI 有效，与真实数据不一致。

### 2.3 调用的 Subagent 与结论摘要

| Subagent | 核心结论 |
|----------|----------|
| **robot-app-architect** | 位姿权威集中在 `RobotRealtimeState` + `CriService` 健康信号；拆分 `has_pose()` 与 `is_cri_primary()`；禁止用单一 `is_valid()` 同时表示「有位姿」和「CRI 正常」。 |
| **pyside6-ui-expert** | 芯片四态：off / pending / udp / subscribe（琥珀 caution）；状态栏 CRI 后缀；`bind_error` 每轮 `start()` 最多一次弹窗；UDP 超时不用 QMessageBox。 |
| **thread-scheduler-expert** | Watchdog `QTimer` 在 **UI 线程、`CriService` 内**；`last_frame_mono` 仅在 `cri_frame_received` 路径更新；stale 时 **`invalidate()`** 以启用 Posture 兜底；登出/断线须 `cri_svc.stop()` + disarm timer。 |

### 2.4 最终采用方案

#### 2.4.1 位姿来源模型（`RobotRealtimeState`）

```python
# 概念枚举（实现时可用 Enum 或 Literal）
PoseSource = NONE | CRI_UDP | TCP_SUBSCRIBE
```

| API（建议） | 语义 |
|-------------|------|
| `has_pose()` | 任一来源有关节/TCP 缓存（**读当前点、填工作空间**） |
| `is_cri_primary()` | CRI 已启用且近期收到 UDP（**执行/探针/起点核对**） |
| `pose_source()` | 当前写入来源，供 UI 与日志 |
| `is_valid()` | **过渡期**可映射为 `has_pose()`，文档标注 deprecated；新代码不用其表示「CRI 正常」 |

**写入优先级**（在 `RobotRealtimeState` 内集中实现）：

1. `update_from_cri_frame(frame)` → `pose_source=CRI_UDP`，刷新 joint/tcp 及 CRI 专有 `is_moving/enabled/estop/status*`；
2. `update_from_robot_posture(db)` → **仅当 `not is_cri_primary()`** 时写入；关节单位 deg→rad，TCP 单位 mm/deg 与现 UI 一致；
3. `invalidate()` → 仅 `cri_stopped`、登出、**UDP stale**（清空 CRI 权威，**不**清空 TCP 已缓存的订阅位姿——由下一次 Posture 推送再写入）。

> **注意**：watchdog 触发 stale 时调用 `invalidate()`，使 `_cri_pose_active` 为 false，Posture 回调可立即 `update_from_robot_posture` 并 `has_pose()==True`。

#### 2.4.2 CRI 传输健康（`CriService`）

新增信号（名称可微调，语义固定）：

| 信号 | 触发条件 |
|------|----------|
| `cri_udp_stale` | `is_enabled` 且 watchdog 判定超时无帧 |
| `bind_error` | 已有；须接到 UI |
| （可选）`cri_first_frame` | 首帧到达，用于取消 pending |

**Watchdog 参数（默认值，实现时可配置常量）**：

| 参数 | 建议值 | 说明 |
|------|--------|------|
| `T_stale` | 250 ms | 约 125 个周期（500Hz，`duration=2ms`） |
| `T_startup_grace` | 800 ms | 覆盖 `cri_started` 后 Stop→200ms→Start、bind、首包 |
| Timer 间隔 | 50–100 ms | UI 线程 `QTimer`，不触碰 socket |

**生命周期**：

- `cri_started` → 清零 `last_frame_mono`，arm timer（带 grace）；
- 首帧 → 更新时间戳，emit 正常帧，UI 切 **udp**；
- 超时 → emit `cri_udp_stale`（debounce，避免每 tick 刷屏）；
- `stop()` / `bind_error` / 非 `connected` → disarm timer；
- **登出**：`cri_svc.stop()` **再** `cm.disconnect()`。

**stale 时是否 `cri.stop()`**：**否**（默认）。仅 `invalidate()` + UI 预警 + 订阅兜底；避免 StopDataPush 抖动。重连或用户登出再统一 `stop()`。

#### 2.4.3 UI 状态机（`signal_binder` + `home_page` + `status_bar`）

集中函数 `_refresh_cri_ui(state)`，根据 `state["cri_ui_mode"]` 更新芯片 + 状态栏后缀（避免 `RobotPosture` 每帧重复写 UI）。

| `cri_ui_mode` | 条件 | 首页芯片 | 芯片样式 |
|---------------|------|----------|----------|
| `off` | 未连接 / `cri_stopped` / `!is_enabled` | CRI关 | inactive |
| `pending` | `cri_started` 后 grace 内无首帧 | CRI关（或「…」） | inactive（**禁止假绿**） |
| `udp` | `is_cri_primary()` | CRI | active（绿） |
| `subscribe` | `is_enabled && !is_cri_primary() && has_pose()` | 订阅位姿 | **caution（琥珀）** |
| `bind_fail` | 收到 `bind_error` | CRI关 | warn（红） |

**状态栏 CRI 后缀**（右侧独立 `QLabel`，仅 mode 变化时更新）：

| mode | i18n key（建议） |
|------|------------------|
| pending | `status_cri_pending` |
| subscribe | `status_cri_fallback` |
| bind_fail | `status_cri_bind_error` |

**弹窗**：仅 `bind_error`，每轮 `start()` 最多一次 `QMessageBox.warning`（latch `cri_bind_dialog_shown`）。  
**禁止**：UDP 超时用 blocking QMessageBox；与 `publish/Error` 机器人故障弹窗合并。

#### 2.4.4 消费者分级

| 场景 | 判定 API | 行为 |
|------|----------|------|
| 3D / 关节 TCP 标签 | `is_cri_primary()` 决定数据源；否则 Posture | 已有逻辑，改为经 RT 统一缓存 |
| 工作空间「从当前位置读取」 | `has_pose()` | 成功；日志注明 `pose_source`；subscribe 时 `tr("weld_log_cri_pose_subscribe")` 类文案 |
| 写字/焊接 CRI 执行、准备起点、minimal_test | `is_cri_primary()` | 失败：现有 `weld_log_cri_no_data` 或更明确的「需要 CRI UDP」 |
| `cri_execution_log` UDP 探针 | `is_cri_primary()` | 保持「CRI状态无效」语义 |
| 节点编辑 MoveJ 取点（若用 RT） | 显示可用 `has_pose()`；执行依赖 CRI 的节点仍 `is_cri_primary()` | 按节点类型文档化 |

#### 2.4.5 数据流（目标）

```text
TCP connected
  → subscribe: RobotStatus, RobotPosture, ProjectState, Error, Log
  → 3s 后 cri_svc.start → StopDataPush → StartDataPush
  → cri_started (pending)

UDP 首帧 ──► update_from_cri_frame ──► pose_source=CRI_UDP ──► UI: CRI 绿

UDP 超时 ──► cri_udp_stale ──► invalidate() ──► pose_source 待 Posture
  publish/RobotPosture ──► update_from_robot_posture ──► pose_source=TCP_SUBSCRIBE
  ──► UI: 订阅位姿 琥珀 + 状态栏「CRI UDP 无数据，使用订阅位姿」

UDP 恢复 ──► 下一帧 CRI ──► 抢回 primary ──► UI: CRI 绿，清除后缀

bind_error ──► UI: 弹窗一次 + bind_fail 芯片 + 停止 watchdog
```

---

### 2.5 分阶段实施计划（待用户确认后编码）

#### Part 1 — 状态模型与 CriService 健康

**目标**：建立 `pose_source`、`has_pose`、`is_cri_primary`、`update_from_robot_posture`；实现 watchdog 与信号。

**涉及文件**：

- `services/robot_realtime_state.py`
- `services/cri_service.py`
- `core/types.py`（可选 `PoseSource` Enum）

**验收**：

1. 单元/手动：模拟 Posture dict 写入后 `has_pose()==True`、`pose_source==TCP_SUBSCRIBE`；
2. 模拟 CRI 帧后 `is_cri_primary()==True`；
3. `start()` 后无帧超过 `T_startup_grace + T_stale` 触发 `cri_udp_stale` 一次；
4. 首帧后不再 stale；
5. `stop()` / disarm 后 timer 不残留。

**风险**：`is_valid` 旧调用方语义变化 → Part 1 仅加 API，Part 3 再改调用方。

---

#### Part 2 — UI 预警与状态机

**目标**：芯片四态、caution 样式、状态栏 CRI 后缀、`bind_error` 弹窗、去除假绿。

**涉及文件**：

- `app/signal_binder.py`
- `app/pages/home_page.py`
- `app/main_window.py`
- `app/widgets/status_bar.py`
- `app/i18n.py`

**i18n 键（建议）**：

```text
home_cri_off, home_cri_udp, home_cri_subscribe
status_cri_pending, status_cri_fallback, status_cri_bind_error
cri_bind_error_title, cri_bind_error_body
weld_log_cri_pose_subscribe   # 读点成功但来源为订阅
```

**验收**：

1. 连接后 pending 阶段芯片为灰「CRI关」，非绿；
2. 有 UDP 后芯片「CRI」绿；
3. 断 UDP（关推送或防火墙）约 250ms+ 后芯片「订阅位姿」琥珀 + 状态栏 fallback 文案；
4. 错误 local_ip 导致 bind 失败：弹窗一次 + 芯片 warn；
5. 语言切换后 CRI 后缀文案正确。

---

#### Part 3 — 业务页与生命周期

**目标**：焊接/绘图读点用 `has_pose()`；执行仍 `is_cri_primary()`；登出 `cri_svc.stop()`；断线 disarm。

**涉及文件**：

- `app/pages/welding_page.py`
- `app/pages/writing_page.py`
- `app/signal_binder.py`（`_bind_login_flow`、`_bind_connection_state`）
- `services/writing_execution_service.py`（确认起点检查用 `is_cri_primary`）
- `services/cri_execution_log.py`（`_UdpPoseProbe` 文案与判定一致）

**验收**：

1. UDP 无数据时：工作空间「读取当前位置」可用（订阅），日志标明订阅来源；
2. 同场景下「执行/准备起点/minimal_test」仍拒绝并提示需 CRI UDP；
3. 登出后再连无重复 timer / 无 `QThread: Destroyed while running`；
4. TCP 断线重连后 CRI 可再次 start，状态正确。

---

#### Part 4 — 文档与日志验收

**目标**：同步 `ARCHITECTURE.md`、本文件状态改为「已完成」；补充 `tools/log_acceptance_harness.py` 可选检查项（若适用）。

**验收**：

1. `docs/plan.md` 本章节标记已完成并注明日期；
2. `ARCHITECTURE.md` §7.4 / §15 与实现一致；
3. 日志可见：`[CRI] udp_stale`、`[CRI] pose_source=TCP_SUBSCRIBE`、`[Login] bind_error` 等。

---

### 2.6 风险点

| 风险 | 缓解 |
|------|------|
| 订阅 TCP 位姿与 CRI 笛卡尔不一致 | 日志/读点提示 `pose_source`；执行路径仍强制 CRI |
| 全局把 `is_valid` 当 CRI 正常 | 分 API；代码审查执行路径 |
| stale 后迟到 UDP 帧 | `update_from_cri_frame` 立即抢回 primary |
| watchdog 与重连叠加重复弹窗 | debounce + disarm on disconnect |
| `RobotStatus.isMoving` 与 CRI `is_moving` 不一致 | stale 后运行态以 `RobotStatus` 为准（可选 Part 3 细化） |

### 2.7 回滚方案

- Part 1–3 均可按 part 回滚对应文件；
- 若需整体回滚：恢复 `RobotRealtimeState` 仅 CRI 写入 + 移除 `CriService` watchdog 信号连接 + 恢复 `update_home_cri(bool)` 二值 API。

### 2.8 禁止修改范围（本特性）

- **不**改 `UdpCriAdapter` 协议解析（308B 帧格式）；
- **不**改 `CRI/StartDataPush` / `StopDataPush` 报文结构；
- **不**在 stale 时自动向机器人循环重发 StartDataPush；
- **不**让 `CriMotionSender` / 写字 UDP 执行在 subscribe 兜底时静默运行；
- **不**在 `signal_binder` 外新增第二套位姿缓存；
- **不**合并启用未使用的 `core/robot_state.RobotStateStore`（除非单独立项）。

---

## 3. 历史约束（仍有效）

以下规则来自原项目 `CLAUDE.md` / 交接习惯，实现任何功能时须遵守：

- 连接成功后默认速度 **70%**；速度变化同时设手动与自动速率；
- Jog / moveTo：**按住式** + 500ms 心跳，松开必须停；
- `StartDataPush` 前必须先 `StopDataPush`；
- UI **不得**直接操作 socket；子线程 **不得**直接改 QWidget；
- 掉线优先自动重连；重连后恢复 CRI 推送与速度；
- 用户/客户手动改过的文件：合并前先 `git diff`，禁止擅自覆盖。

---

## 4. 文档索引

| 文档 | 内容 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 模块边界、线程、页面、pipeline |
| [planAPI.md](planAPI.md) | 机器人 TCP/UDP/订阅 API |
| **本文件 plan.md** | 功能规划、分 part、验收、进行中特性 |
| [NOTICE.md](NOTICE.md) | 第三方许可 |
| [../README.md](../README.md) | 安装与运行 |

---

### 2.9 已实现范围（2026-05-21）

| 项 | 文件 |
|----|------|
| `PoseSource` / `has_pose` / `is_cri_primary` / `update_from_robot_posture` | `services/robot_realtime_state.py` |
| UDP watchdog、`cri_udp_stale`、`disarm_watchdog` | `services/cri_service.py` |
| 订阅写入缓存、stale/bind 处理、登出 `cri.stop` | `app/signal_binder.py` |
| 读当前点 `has_pose` + 订阅日志 | `welding_page.py` / `writing_page.py` |
| 执行仍要求 `is_cri_primary` | `writing_execution_service.py` / `cri_execution_log.py` |

**已补充（2026-05-21）**：状态栏 `位姿: CRI/订阅`；切换/恢复带时间戳日志；连续 10 帧无完整 CRI 才切换；TCP 连接成功即订阅（与状态/日志/报错并列）。  
**未做**：`home_page` 芯片四态、`bind_error` 弹窗。

*下一动作：真机验证 UDP 断流后工作空间「读当前位置」是否可用；可选再补 Part 2 UI 预警。*
