# 项目交接文档 — Phase 9 收口状态

> **文档同步**：2026-05-16（焊接页收尾）— 任务 A–F 已完成；`preview_execution.png` 为正式验收图；Phase 9 回归 **7 项**测试全部通过。

## 1. 项目概述

PySide6 机器人焊接文字生成工具。

**当前目标**：
- 用户输入文字、字体、工艺参数、运动参数、三点标定；
- 离线生成 `points.txt` / `job.json` / `<文字>.lua` / preview PNG / `summary.json`；
- 用户仿真确认后，由机器人执行 Lua。

**正式主线**：
- **contour 轮廓字**（单行 + 多行 `\n`）
- **三点 LT / RT / LB 标定**
- **字高 char_height_mm**、**字间距 char_spacing_mm**（横）、**行间距 line_spacing_mm**（竖，多行）
- **左边距 margin_left_mm**、**上边距 margin_top_mm**（无右/下边距；字顶贴顶）
- **空间不足拒绝生成**（不自动缩放）
- **绝对 Z 高度模型 (z_work / z_safe)**，**arcOff 后抬枪**
- **points.txt / Lua 坐标一致**
- **`preview_execution.png` 为正式验收预览图**
- **Lua 导出**
- **contour 多行文字**（`\n` 拆行，行距 `line_spacing_mm` 正式生效）

**技术栈**：Python 3.11 + PySide6 + OpenCV + PIL + NumPy + matplotlib + scikit-image

---

## 2. 当前正式可用功能

### 2.1 contour 轮廓字生成（单行 + 多行）

| 项目 | 状态 |
|------|------|
| 单行文字 contour 模式 | ✅ 正式可用 |
| 多行文字（`\n` / `QPlainTextEdit` / 字面量 `\n` 归一化） | ✅ 正式可用 |
| 中文/英文/数字 | ✅ |
| 字高 `char_height_mm` 真实生效 | ✅ |
| 字间距 `char_spacing_mm`（相邻字外框水平距） | ✅ |
| 行间距 `line_spacing_mm`（多行行间额外竖直距） | ✅ |
| 左/上边距 `margin_left_mm` / `margin_top_mm` | ✅ |
| 字形 padding | ✅ 固定 0（`LINE_BOX_PADDING_PX`） |
| 空间不足拒绝生成，不自动缩放 | ✅ |

**验收数据**：

| 字高目标 | 实测 | 误差 |
|---------|------|------|
| 50mm | 49.9mm | 0.1mm (0.2%) |
| 100mm | 99.9mm | 0.1mm (0.1%) |
| 比值 | 2.00 | ✅ |

| 字距 | 实测 AB 宽度 | 单调递增 |
|------|-------------|---------|
| 0mm | 91.7mm | — |
| 20mm | 111.7mm | ✅ |
| 50mm | 141.7mm | ✅ |

**溢出测试**：100×50mm 工作区下 ABc(char_h=100,spacing=50) → 被正确拒绝；UI 日志（中文）示例：`文字尺寸超出工作区：需要 424.7×101.5 mm，可用 100.0×50.0 mm，缺口 324.7×51.5 mm`（随界面语言 zh/en 切换）。

### 2.1b 排版间距语义（与 UI 一致）

| 概念 | 参数 | 说明 |
|------|------|------|
| 字框内边距 padding | — | **固定 0**，无 UI；`font_rasterizer.LINE_BOX_PADDING_PX` |
| 字间距（横） | `char_spacing_mm` | 同行相邻字外框水平空隙 |
| 行间距（竖） | `line_spacing_mm` | 多行 contour 行间额外空隙；`line_step = 字高 + 行间距` |
| 左边距 | `margin_left_mm` | 相对示教 LT；0 → 首字贴左边界 |
| 上边距 | `margin_top_mm` | 相对示教上边界；0 → 墨迹顶贴顶边界 |
| 右/下边距 | — | **无**；字可写到示教右、下边界 |

**顶对齐修复**（2026-05-16）：`render_char_in_linebox` 使用 `draw_y = padding - bbox[1]`（与 `render_char` 一致）+ `_trim_binary_top`；微软雅黑/黑体/Arial 上边距=0 时首行 `min_y_px≈0`（见 `test_glyph_top_align.py`）。

**边距实现**：`pipeline/layout_inset.py` — Schedule 后 `apply_layout_origin_offset`；溢出可用区 `width - margin_left`、`height - margin_top`。

### 2.2 三点标定语义

正式三点：

```
LT = 左上 (row 0)
RT = 右上 (row 1)
LB = 左下 (row 2)

RB = LT + (RT - LT) + (LB - LT)  — 仅推导，不作为输入
```

映射公式：

```
img_w = width_mm × pixel_per_mm
img_h = height_mm × pixel_per_mm
P = TL + (px / img_w) × (RT - TL) + (py / img_h) × (LB - TL)
```

**规则**：
- 不使用 `right_bottom` 作为输入
- 不允许 `y_flip`
- pixel 方向 = robot 方向
- 正式验收图 `preview_execution.png` 与 points/Lua **同源**（WorkPlane UV 纸面显示，LB 图左下 / RT 图右上）

### 2.3 绝对 Z 高度模型

| 高度 | 用途 | 默认值 |
|------|------|--------|
| `z_work` | weld / lead_in / overlap / lead_out | 305mm |
| `z_safe` | travel / retreat | 315mm |
| `z_super_safe` | 字段已保留，当前流程未输出独立段 | 325mm |

**规则**：
- arcOff 后第一个 movL 必须是 z_safe
- points.txt 与 Lua 坐标一致（无 double offset）
- `z_safe <= z_work` 时输出 warning，不崩溃

**验收数据**：

| 验证项 | 结果 |
|--------|------|
| weld Z=105, retreat Z=115 | ✅ |
| arcOff 后 retreat Z=115 | ✅ |
| ABc 6 笔画全程 | ✅ |
| points.txt ↔ Lua Z 一致性 | ✅ |

### 2.4 Lua 导出

**文件命名**：

| 输入 | 输出 | 说明 |
|------|------|------|
| `A` | `A.lua` | 标准 |
| `Abc123` | `Abc123.lua` | 标准 |
| `你好` | `你好.lua` | 中文保留 |
| `A/B:C*D?` | `A_B_C_D_.lua` | 非法字符→`_` |
| `CON` | `text_CON.lua` | Windows 保留名保护 |
| `""` | `job.lua` | fallback |

**Lua 格式**：

```lua
-- Robot Weld Path Lua Script
-- Text: A
-- Mode: contour
-- Point spacing: 0.5

setWelderParam({job=7,I=200,U=28,L=2})

-- segment: ..., type: travel, points: 2
movL({cp={251.309,562.044,300.000,180.000,0.000,90.000}},{v=90.0,a=300,b=2})
-- segment: ..., type: lead_in, points: 7
arcOn()
movL({cp={251.550,562.482,300.000,180.000,0.000,90.000}},{v=35.0,a=300,b=2})
...
arcOff()
movL({cp={...}},{v=90.0,a=300,b=2})
```

**已验收规则**：

| 规则 | 状态 |
|------|------|
| `movL({cp={...}},{v,a,b})` table 格式 | ✅ |
| `b` / `rb` 互斥，UI 默认 `b=2.0mm`（LuaExportConfig dataclass 默认 0.0，实际以 UI 为准） | ✅ |
| `rb` 为 1~100 整数 | ✅ |
| `wait(ms)` 为整数，默认关闭 | ✅ |
| arcOn/arcOff 按 `segment.arc_enabled` 状态机 | ✅ |
| 文件结束前保证 arcOff | ✅ |
| 文件名按文字命名 | ✅ |
| 微秒级时间戳保证目录唯一 | ✅ |

### 2.5 UI 已完成项

| 功能 | 状态 |
|------|------|
| 左右分栏布局（左侧参数，右侧按钮+日志） | ✅ |
| 焊接页日志 **append**，不覆盖 | ✅ |
| 焊接页日志桥接系统级 `logging.getLogger("codroid")` | ✅ |
| 三点各行：**更新坐标** / **运动到** / **复制** 按钮 | ✅ |
| 运动到：按住运动 (Robot/moveTo type=5) + heartbeat 500ms | ✅ |
| 松开停止 (Robot/moveTo type=-1) | ✅ |
| 复制格式 `[x,y,z,rx,ry,rz]` | ✅ |
| 未连接/非法坐标/并发按压保护 | ✅ |
| 字高 / 字间距(横) / 行间距(竖) / 左·上边距 控件 | ✅ |
| 焊接文字 `QPlainTextEdit` + `normalize_weld_text_input()` | ✅ |
| 绝对 Z 高度 `z_work` / `z_safe` / `super_safe_extra` 控件 | ✅ |
| Lua 运动参数 `a` / `b`/`rb` / `wait` 控件 | ✅ |
| 字体下拉显示中文名称 | ✅ |
| 字体选择保存 font_path + font_family (双 key) | ✅ |
| QSettings 保存/恢复（含 Lua、边距） | ✅ |
| **400ms 防抖自动保存** + `on_leave` + `aboutToQuit` + 主窗口 `closeEvent` | ✅ |
| 全局 QSpinBox/QDoubleSpinBox/QComboBox 滚轮误改防护 | ✅ |
| 预览按钮打开 **`preview_execution.png`** | ✅ |

### 2.6 Preview 正式验收图（任务 D）

| 文件 | 用途 | 数据源 | 正式验收 |
|------|------|--------|----------|
| **`preview_execution.png`** | **正式执行预览 / 客户验收** | `ProcessSegment` 机器人点位 → 投影到纸面 U-V(mm) | ✅ **是** |
| `preview_segments.png` | 兼容旧路径 | 与 execution 同源 | 同 execution |
| `preview_weld_only.png` | 仅焊接段（无 travel/retreat） | 同上，过滤段类型 | 辅助 |
| `preview_strokes.png` | 像素轮廓 debug | `Stroke.points_px` | 否（非机器人坐标） |
| `preview_combined.png` | 三栏：Raw \| Weld \| Execution | 组合 | 辅助 |
| `preview_workplane.png` | U-V debug | 局部坐标 | 否 |

**规则**：
- 显示层 `display_invert_y` **仅影响 PNG**，不改 points/Lua/映射
- `summary.json` → `preview.source = process_segments`，`basis = workplane_uv_paper`
- 溢出失败时写入 **占位** `preview_execution.png`，`preview.generated = false`
- UI「预览」按钮与服务层 `preview_ready` 均优先 **`preview_execution.png`**

### 2.7 ConnectionManager 修复

| 修复项 | 状态 |
|--------|------|
| `on_response=None` 不再 TypeError | ✅ |
| `on_error=None` 同理防御 | ✅ |
| 10074/未开启远程模式 → 业务日志，不触发断连/重连/切页 | ✅ |

---

## 3. Beta / 不建议客户正式使用的功能

| 功能 | 状态 | 说明 |
|------|------|------|
| skeleton 骨架字 | **[Beta]** | 算法不稳定，可能断线、异常骨架 |
| contour 多行文字 | **正式** | `\n` 拆行；行步进 = 字高 + 行距；行内 L→R、行间 T→B |
| skeleton 多行 | **[Beta]** | 仍按整串 glyph 排版，不推荐 |
| 对齐模式 (左/中/右) | **[Beta]** | UI only，未接入 V2 pipeline |
| 排版方向 (横排/竖排) | **[Beta]** | UI only，未接入 V2 pipeline |
| 流向 (左→右/右→左/上→下) | **[Beta]** | UI only，未接入 V2 pipeline |

**UI 行为**（任务 C 已完成）：
- 下拉项标记 `[Beta]`；`itemData` 保存 align/direction/flow，QSettings 按 data 恢复
- 生成时 `detect_beta_features()` 写日志；正式单行 contour 无 Beta 时输出 `weld_production_line`
- 输出日志随 **界面语言 zh/en** 切换（`pipeline/user_messages.py` + `app/i18n.py` `weld_log_*`）
- 正式单行 contour 主线不依赖这些功能

---

## 4. 已知遗留问题

### 4.1 最小化恢复回主页 — ✅ 已修复（任务 A）

**现象（曾出现）**：焊接页 → 最小化 → 恢复 → 误回首页。

**修复（任务 A）**：删除 `app/main_window.py` 中最小化/恢复相关的 `reset_to_home` 自动触发与状态机补丁；`reset_to_home(reason)` 仅允许：
1. `app_init`（`__init__`）
2. `user_click_home`（用户点首页 tab）
3. `logout`（`signal_binder` 返回登录页显式调用）

**禁止**因最小化/恢复、断连、日志刷新等自动回主页。已手动验收：最小化恢复后仍停留在焊接页。

### 4.2 z_super_safe 输出状态需复核

`z_super_safe` 字段已存在于 `WorkspaceConfig`，UI 有控件 (`_spin_z_super_extra` 作为增量)，stats 中已记录 `z_super_safe_mm`。但 **z_work / z_safe 是已验收正式功能**；**z_super_safe 只是字段/UI/stats 保留**。

当前 **未验收** global start/end 超安全点实际输出。后续需要单独 Phase 复核并实现：起点 z_super_safe、结束 z_super_safe、Lua/points 一致性、preview 一致性。

### 4.3 高级排版（对齐/方向/流向）— 仍 UI only

**contour 多行**已于任务 E 正式化（见 §7）。以下仍为 **[Beta] UI only**，未进 pipeline：
- 对齐 (左/中/右)、排版方向 (横/竖)、流向 (LTR/RTL/TTB)

### 4.4 送气/送丝/退丝 — ✅ 已接 TCP

| 按钮 | `Welder/command` | 说明 |
|------|------------------|------|
| 送丝 | 1 | 按住启动 + 500ms `commandHeart` 心跳 |
| 退丝 | 2 | 同上 |
| 送气 | 3 | 同上 |
| 松开 / 离页 | 0 | 立即停止 |

接口：`welder/sendparams`，db 为 `[{path, value}]` 数组（planAPI §23）。实现：`app/pages/welding_page.py`。

---

## 5. 关键文件说明

### UI 层

| 文件 | 职责 |
|------|------|
| `app/pages/welding_page.py` | 焊接页 UI、参数收集、日志、三点标定、运动到/复制、生成入口 |
| `app/main_window.py` | 主窗口、页面导航、最小化恢复问题重点文件 |
| `app/i18n.py` | 中文/英文显示文本 |
| `app/utils/wheel_guard.py` | 全局滚轮防护 (QSpinBox/QDoubleSpinBox/QComboBox) |
| `app/base_page.py` | BasePage 基类 (on_enter/on_leave 钩子) |
| `app/page_router.py` | 页面路由；`persist_all_page_settings()` 供主窗口关闭时保存 |
| `app/widgets/robot_control_drawer.py` | 左侧运动抽屉 (Jog/moveTo/速度) |
| `app/widgets/global_command_bar.py` | 底部全局命令栏 (Home/Safe/Candle/Pack) |

### Service 层

| 文件 | 职责 |
|------|------|
| `services/welding_service_v2.py` | 焊接生成服务入口，将 UI 参数传入 OfflinePipelineRunner，构造 WeldingProcessConfig/WorkspaceConfig/LuaExportConfig |
| `services/welding_service.py` | 旧 V1 焊接服务（已废弃，保留不删） |

### Pipeline 层

| 文件 | 职责 |
|------|------|
| `pipeline/offline_runner.py` | **正式 contour 生成主链路**：字高→font_size 二分、多行/单串排版、左·上边距、overflow、各 Stage |
| `pipeline/multiline_layout.py` | contour 多行：拆行、行步进、按行渲染与调度统计 |
| `pipeline/layout_inset.py` | 仅左/上边距平移、可写区有效尺寸 |
| `pipeline/raster/font_rasterizer.py` | PIL 渲染、LineboxGlyph、`LINE_BOX_PADDING_PX=0`、墨迹顶对齐 |
| `pipeline/vision/contour_extractor.py` | 轮廓提取 (从二值图提取轮廓路径) |
| `pipeline/vision/skeleton_extractor.py` | 骨架提取 (Zhang-Suen/skimage) |
| `pipeline/mapping/workplane.py` | WorkPlane 三点定义、pixel_to_plane 映射 |
| `pipeline/mapping/pose_mapper.py` | PoseMapper 批量映射 |
| `pipeline/process/weld_process.py` | 生成 travel/lead_in/weld/overlap/lead_out/retreat ProcessSegment；z_work/z_safe 分配；arc_enabled 标记；0.5mm 重采样 |
| `pipeline/output/lua_exporter.py` | Lua 导出：setWelderParam、movL、arcOn/arcOff 状态机、wait 插入、文件名 sanitize |
| `pipeline/output/points_writer.py` | points.txt CSV 导出 |
| `pipeline/output/job_writer.py` | job.json 导出 |
| `pipeline/output/preview_writer.py` | preview PNG 导出、CJK 字体支持 |
| `pipeline/path/path_cleaner.py` | 路径清洗 (去重/短线过滤/dot 生成) |
| `pipeline/path/path_refiner.py` | 路径细化 (自适应保形) |
| `pipeline/path/path_resampler.py` | 路径重采样 (RDP 简化/等距) |
| `pipeline/path/path_scheduler.py` | 路径调度 (最近邻排序) |

### Types

| 文件 | 职责 |
|------|------|
| `core/types.py` | RobotPoint、PixelPoint、Stroke、ProcessSegment、WeldingProcessConfig、WorkspaceConfig、LuaExportConfig、PathConfig 等全部 dataclass |

### Network/Motion

| 文件 | 职责 |
|------|------|
| `network/connection_manager.py` | TCP 连接、send_call、响应分发、callback 防御 |
| `services/cri_service.py` | CRI/UDP 数据推送 |
| `app/signal_binder.py` | 全局 moveTo (Home/Safe/Candle/Pack) 信号绑定 |

---

## 6. 当前正式生成链路

```
WeldingPage._on_generate()
  → _collect_params()
  → WeldingServiceV2.generate(text, mode, left_top, right_top, left_bottom,
       char_height_mm, char_spacing_mm, line_spacing_mm,
       margin_left_mm, margin_top_mm,
       voltage, current, job, inductance, weld_speed, travel_speed,
       z_work_mm, z_safe_mm, z_super_safe_mm,
       lua_accel, lua_blend_mode, lua_blend_radius, lua_blend_ratio,
       wait_enabled, wait_count, wait_duration_ms, font_path, user_lang)

  → OfflinePipelineRunner.run(text, mode, workplane)
    Stage 0: 字高 → font_size_px 二分搜索 (char_height_mm × px_per_mm)
    Stage 1-2: contour 多行 layout_contour_multiline 或 legacy 单串
               render_text_linebox (tight bbox + 顶空行裁剪) + contour_extract
    Stage 3-5: clean + refine + schedule (多行: schedule_by_line_groups)
    5.5: apply_layout_origin_offset(margin_left, margin_top)
    Stage 6: PoseMapper.map (linear_mm_per_px, 溢出检测扣左/上边距)
    Stage 7: WeldingProcessPlanner.plan (ProcessSegment + z_work/z_safe)
    Stage 8: points_writer + job_writer + lua_exporter + preview_writer

  输出:
    output/<ts>_<text>_<mode>/
      points.txt
      job.json
      <文字>.lua
      preview_strokes.png
      preview_execution.png    ← 正式验收图
      preview_segments.png     ← 与 execution 同源（兼容）
      preview_weld_only.png
      preview_combined.png
      preview_workplane.png
      summary.json
```

**正式 contour 主线不依赖**：skeleton、对齐、排版方向、流向（Beta UI only）。

---

## 7. Phase 9 任务完成记录（A–F）

| 任务 | 内容 | 状态 | 主要改动 |
|------|------|------|----------|
| **A** | 最小化恢复不再回主页 | ✅ 完成 | `app/main_window.py`、`app/signal_binder.py` — 限制 `reset_to_home` 触发场景 |
| **B** | Phase 9.6-c 自动化与 layout 诊断 | ✅ 完成 | `examples/test_phase9_6_layout_params.py`；`offline_runner` summary `layout` 字段 |
| **C** | Beta UI 标记与生成日志 | ✅ 完成 | `welding_page.py`、`i18n.py` — `[Beta]`、`detect_beta_features`、双语日志 |
| **D** | 预览图整理 + 正式验收图 | ✅ 完成 | `preview_writer.py` — `preview_execution.png` 纸面 UV 对齐 |
| **E** | contour 多行正式化 | ✅ 完成 | `multiline_layout.py`、`line_spacing_mm`、按行调度、`test_phase9_multiline_layout.py` |
| **F** | 焊接页收尾 | ✅ 完成 | 左·上边距、`layout_inset.py`；QSettings 防抖+退出保存；Lua 读写加固；墨迹顶对齐；预览按钮→execution |

### 多行 layout（任务 E）

- **拆行**：`\r\n` / `\n` / `\r` 统一为 `\n`，**保留空行**。
- **行步进**：`line_step_mm = char_height_mm + line_spacing_mm`；第 `i` 行顶部像素 Y = `i × line_step_mm × px_per_mm`。
- **行内**：每行独立 `render_text_linebox(line)`，x 从 0，字距 `char_spacing_mm`。
- **调度**：`PathScheduler.schedule_by_line_groups` — 行内 nearest，行间按输入顺序。
- **溢出**：`required_h = n×字高 + (n-1)×行距`（与实测 bbox 一并检查）；拒绝且不缩放。
- **单行**：`line_count=1` 时行距不影响高度。

---

## 8. 当前测试文件与回归

| 测试文件 | 覆盖范围 |
|---------|---------|
| `examples/test_phase9_lua_exporter.py` | Lua table 格式、arc 状态机、文件名、回归 |
| `examples/test_phase9_3c_verify.py` | 绝对 Z、points/Lua 一致、arcOff 抬枪、多笔画、z_super_safe 文档 |
| `examples/test_phase9_6_layout_params.py` | 字高 50/100mm、字距单调、溢出拒绝、summary layout、Beta 检测 |
| `examples/test_phase9_preview.py` | **preview_execution.png**、纸面 UV、溢出占位、与 points/Lua 同源 |
| `examples/test_phase9_multiline_layout.py` | contour 多行、行距单调、溢出、行序、Beta 检测 |
| `examples/test_layout_inset_margin.py` | 左/上边距平移、可写区尺寸 |
| `examples/test_glyph_top_align.py` | 雅黑/黑体/Arial 上边距=0 时顶隙≈0 |

**回归命令（2026-05-16 全部 PASS）**：

```bash
.venv\Scripts\python.exe examples\test_phase9_lua_exporter.py
.venv\Scripts\python.exe examples\test_phase9_3c_verify.py
.venv\Scripts\python.exe examples\test_phase9_6_layout_params.py
.venv\Scripts\python.exe examples\test_phase9_preview.py
.venv\Scripts\python.exe examples\test_phase9_multiline_layout.py
.venv\Scripts\python.exe examples\test_layout_inset_margin.py
.venv\Scripts\python.exe examples\test_glyph_top_align.py
```

---

## 9. 后续建议（非紧急）

### z_super_safe 实际输出

`z_super_safe` 字段/UI/stats 已保留，**未**输出独立起止超安全 movL 段；需单独 Phase 若客户要求。

### 可选后续

- Beta 排版参数（对齐/方向/流向）真正接入 pipeline
- `font_size_px` / `px_per_mm` 暴露为 UI 可配（当前生成硬编码 600 / 10.0）

---

## 10. 禁止后续破坏的已验收规则

| # | 规则 |
|---|------|
| 1 | 不恢复 `y_flip` |
| 2 | 不把 `right_bottom` 当输入三点 |
| 3 | 不改变 LT / RT / LB 语义 |
| 4 | 不改变 Lua `movL({cp={...}},{...})` table 格式 |
| 5 | 不改变 `b` / `rb` 互斥 |
| 6 | 不改变 `wait(ms)` 整数语义 |
| 7 | 不破坏 z_work/z_safe 绝对高度模型 |
| 8 | 不破坏 arcOff 后抬枪 |
| 9 | 不破坏 points.txt 与 Lua 坐标一致性 |
| 10 | 不破坏 Robot/moveTo 按住运动、松开 type=-1 |
| 11 | 不让最小化/恢复触发页面导航 |
| 12 | 不把 Beta 功能包装成正式功能 |
| 13 | 不恢复 linebox 归一化 bug (map_w 含 spacing 导致压缩) |
| 14 | 不删除旧 V1 `services/welding_service.py` |
| 15 | 正式验收预览以 `preview_execution.png` 为准；`display_invert_y` 仅 PNG 显示层 |

---

## 11. 最终状态结论

**Phase 9 正式主线 + 焊接页已收口**（任务 A–F 完成，回归 **7 项**测试通过）：

| 模块 | 状态 |
|------|------|
| Lua 导出 (movL/arcOn/arcOff/wait/b/rb/a) | ✅ |
| 绝对 Z (z_work/z_safe) + arcOff 后抬枪 | ✅ |
| 字高 / 字间距 / 行间距 + 溢出拒绝 | ✅ |
| 左·上边距 + 墨迹顶对齐 | ✅ |
| points.txt ↔ Lua 坐标一致 | ✅ |
| **preview_execution.png 正式验收图** + UI 预览同图 | ✅ |
| **contour 多行 + line_spacing_mm** | ✅ |
| 三点 LT/RT/LB + 纸面 UV 预览 | ✅ |
| QSettings 防抖/退出保存 + Lua 参数持久化 | ✅ |
| 最小化恢复不回主页（任务 A） | ✅ |
| Beta UI 标记 + 双语日志（任务 C） | ✅ |
| ConnectionManager callback 防御 | ✅ |
| z_super_safe 独立路径输出 | ⚠️ 未实现（仅字段/stats） |
| Beta 排版接入 pipeline | ⚠️ UI only |
| 送气/送丝/退丝 TCP（按住/松开） | ✅ |

---

**建议**：新功能前先跑 §8 **七条**回归；客户验收预览以 **`preview_execution.png`** 为准。快速接手读 **`cursor.md`**。

**项目根目录**：`D:\code\UI`
**Python venv**：`.venv` (Python 3.11)
**入口**：`python main.py`
