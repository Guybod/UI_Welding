# Codroid 机器人控制终端

PySide6 上位机：连接 Codroid 机器人，完成 **焊接文字**、**绘图轨迹（CRI）**、**运动节点编排**、工程上传、IO/寄存器监控与全局示教点动。

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **登录** | 机器人 IP、本机网卡、UDP 端口；TCP 9001 连接，失败停留登录页 |
| **首页** | 连接/CRI 状态、关节与 TCP 概览、GLB 模型预览 |
| **运动** | 节点图编排：MoveJ/L/C、Path、IO、寄存器、If/For/While、宏与插件 |
| **焊接** | 轮廓字 / Hershey 骨架拉丁 / **汉字 medians** → `points.txt`、`job.json`、Lua；三点 LT/RT/LB 标定 |
| **绘图** | TTF 轮廓、Hershey 拉丁、**汉字 medians（MakeMeAHanzi）**、图片轮廓 → CRI 轨迹执行 |
| **IO / 寄存器** | 轮询读写（远程模式） |
| **上传** | HTTP/WS 上传 Lua 工程、槽位绑定（集成原 HTTP/WS 工具能力） |
| **全局** | 使能、手/自/远程、仿真、工程启停、Jog、moveTo 预设、速度默认 70% |

机器人 JSON/TCP/UDP 协议见 **[docs/planAPI.md](docs/planAPI.md)**。  
系统设计与模块边界见 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**。

---

## 环境要求

- Windows 10/11（当前主要开发与部署环境）
- Python **3.11** 推荐
- 与机器人控制器同一网段（默认 IP 示例：`192.168.1.136`）
- 端口：TCP **9001**（主接口）、UDP **9030**（CRI 轨迹控制）、本地 UDP 端口（登录页分配，CRI 数据推送入站）

---

## 安装与运行

```powershell
cd D:\code\UI

# 创建虚拟环境（推荐）
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 启动
python main.py
```

日志目录：`logs/YYYYMMDD.txt`（通信与异常详情）。

---

## 外部数据准备

### 汉字骨架（焊接 / 绘图 `hanzi_stroke`）

从 [MakeMeAHanzi](https://github.com/skishore/makemeahanzi) 获取 `graphics.txt`，放置为：

```text
third_party/makemeahanzi/graphics.txt
```

体积约数十 MB，**默认不提交 Git**。缺字时焊接/绘图生成会报错，不使用 TTF 替代。

说明见 [third_party/makemeahanzi/README.md](third_party/makemeahanzi/README.md)。

### 焊接字体

- 轮廓模式：系统 TTF（微软雅黑、Arial 等）或 `config/weld_font_presets.py` 预设路径。  
- 骨架拉丁：`Hershey-Fonts` 包（pip 已声明），见 [docs/NOTICE.md](docs/NOTICE.md)。  
- 骨架汉字：同上 `graphics.txt`（MakeMeAHanzi medians），非 TTF。

### 3D 模型（首页预览）

**`models/` 随仓库一并提交**（约 5.5MB，多机型 GLB）。克隆后无需再下载，首页与左侧抽屉即可显示机械臂 3D；连接机器人后随关节角转动。

- 路径：根目录 `models/*.glb`（如 `20kg-6axis-model-v2.glb`）  
- 映射：`config/robot_models.yaml`、`config/model_glb_map.yaml`  
- 加载：`view3d/model_resolver.py` 按 `RobotStatus.type` 选型  

若误删 `models/`，3D 区域仅为深色空白，**不影响**焊接/绘图/CRI；补回 GLB 即可恢复。

---

## 使用要点

### 连接

1. 选择本机网卡与 UDP 端口（可自动分配 10000–65535）。  
2. 连接成功后自动：`toAuto` → `toRemote` → 订阅状态 → 默认速度 **70%**。  
3. 掉线自动重连（1s→2s→4s→8s），弹窗仅「返回主页面」。

### 点动与 RunTo（按住式）

- **Jog**：按下 `Robot/jog` + 500ms `jogHeartbeat`；松开 `stopJog`。  
- **moveTo 预设**（零点/安全/蜡烛/打包）：按下 `Robot/moveTo` + `moveToHeartbeat`；松开 `type=-1`。  
- 切页、断线、停止运动会强制停心跳。

### 焊接生成

1. 标定左上 / 右上 / 左下三点（LT/RT/LB）。  
2. 输入文字（支持多行 `\n`）、字高、字间距、行间距、左/上边距。  
3. 生成后查看 **`preview_execution.png`** 与 Lua。  
4. 空间不足会拒绝生成（不自动缩放）。

### 绘图与 CRI

1. 选择文字源（轮廓 / Hershey / 汉字 / 图片）。  
2. 生成轨迹 → `output/<时间戳>_.../trajectory_cri.txt` 等。  
3. **准备起点**（TCP movL）→ **CRI 执行**（StartControl + UDP 9030）。  
4. 可用「CRI 最小 Z 测试」验证 UDP 通断（不经过文字 pipeline）。

### 工程上传

在 **上传** 页配置 Lua 路径、工程名、上传/绑定模式；依赖已连接机器人，底层为 `RobotProjectSDK`（HTTP 9198 + WebSocket 9000）。

---

## 输出目录

每次焊接/绘图生成通常在：

```text
output/<微秒时间戳>_<文本摘要>_<模式>/
  points.txt / job.json / *.lua
  preview_execution.png    # 焊接正式验收图
  preview_strokes.png
  trajectory_cri.txt       # 绘图 CRI
  summary.json
```

`output/` 为运行产物，可按需清理或加入 `.gitignore`。

---

## 项目结构（简表）

```text
main.py              入口
app/                 界面、路由、信号绑定
network/             TCP/UDP、ConnectionManager
services/            焊接/绘图/执行/上传/CRI
pipeline/            离线轨迹算法（无 Qt）
core/                类型、日志、配置
config/              默认参数与机型
models/              机器人 GLB 模型文件
view3d/              首页 3D 加载与渲染
styles/              QSS 主题
docs/planAPI.md      机器人 API 文档
docs/ARCHITECTURE.md 架构与维护说明（本文档姊妹篇）
```

---

## 配置与持久化

- **QSettings**：组织 `Codroid`，应用 `RobotUI`（登录 IP、焊接/绘图/上传/IO 等参数）。  
- **主题与语言**：主菜单「设置」→ 7 套 QSS + 中/英（非独立设置页）。  
- **节点工程**：运动页保存的 JSON 图（用户指定路径）。

---

## 开发与维护

1. 先读 **docs/ARCHITECTURE.md** 的线程规则与数据流，再改通信或运动控制。  
2. 改机器人接口时同步 **docs/planAPI.md**（若协议变更）。  
3. UI 不得直接操作 socket；新功能经 `ConnectionManager.send_call`。  
4. 焊接/绘图算法改 `pipeline/`，用 `summary.json` 与预览 PNG 验收。  
5. 本地 mock：`tools/mock_robot_server.py`（按需）。

### 已知限制

- 顶栏 **程序** 页为占位。  
- 焊接/绘图汉字均需本地 `third_party/makemeahanzi/graphics.txt`。  
- 焊接 UI 中的对齐/方向/流向为 Beta，未接入 pipeline。

---

## 许可证与第三方

- Hershey 字体：见 [docs/NOTICE.md](docs/NOTICE.md)。  
- MakeMeAHanzi / ARPHIC：汉字数据请遵循上游许可。  
- 本应用其余代码以项目方约定为准。

---

## 文档索引

| 文件 | 用途 |
|------|------|
| [README.md](README.md) | 本文件：安装与使用 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构、模块、扩展与禁忌 |
| [docs/planAPI.md](docs/planAPI.md) | 机器人通信 API |
| [docs/NOTICE.md](docs/NOTICE.md) | Hershey 等第三方许可说明 |
