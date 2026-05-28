# UI_Welding — Codroid 焊接上位机

基于 **PySide6** 的 Codroid 协作机器人焊接控制终端：连接机器人、生成文字焊接轨迹、上传 Lua 工程到控制器，并提供首页状态监控与全局点动。

**仓库地址：** https://github.com/Guybod/UI_Welding.git

---

## 功能概览

| 模块 | 说明 |
|------|------|
| **登录** | 机器人 IP、本机网卡、UDP 端口；TCP 9001 连接 |
| **首页** | 连接/CRI 状态、关节与 TCP 概览、GLB 3D 预览 |
| **焊接** | 轮廓字 / Hershey 骨架拉丁 / 汉字 medians → `points.txt`、`job.json`、Lua；三点工作空间标定 |
| **上传** | HTTP/WebSocket 上传 Lua 工程、槽位绑定（0–127） |
| **全局** | 使能、手/自/远程、仿真、工程启停、左侧点动抽屉、moveTo 预设、速度调节 |
| **帮助** | 菜单「帮助」→ 焊接 / 上传界面帮助手册（中/英） |

机器人通信协议见 **[docs/planAPI.md](docs/planAPI.md)**。  
架构说明见 **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**（部分内容可能随精简版界面过期，以代码为准）。

---

## 环境要求

- Windows 10/11（主要开发与部署环境）
- Python **3.11+** 推荐
- 与机器人控制器同一网段（示例 IP：`192.168.1.136`）
- 端口：TCP **9001**、UDP **9030**（CRI）、本地 UDP（CRI 推送入站，登录页分配）

---

## 安装与运行

```powershell
git clone https://github.com/Guybod/UI_Welding.git
cd UI_Welding

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

python main.py
```

日志目录：`log/YYYYMMDD.txt`（若存在 `logs/` 则为历史路径，以实际配置为准）。

---

## 外部数据准备

### 汉字骨架（焊接「骨架汉字」模式）

从 [MakeMeAHanzi](https://github.com/skishore/makemeahanzi) 获取 `graphics.txt`，放置为：

```text
third_party/makemeahanzi/graphics.txt
```

体积较大，**不纳入 Git**。缺失时汉字骨架生成会报错。说明见 [third_party/makemeahanzi/README.md](third_party/makemeahanzi/README.md)。

### 焊接字体

- **轮廓字**：系统 TTF 或 `config/weld_font_presets.yaml` 预设  
- **骨架拉丁**：`Hershey-Fonts`（见 `requirements.txt`、[docs/NOTICE.md](docs/NOTICE.md)）  
- **骨架汉字**：依赖上述 `graphics.txt`

### 3D 模型（首页预览）

`models/` 目录含多机型 GLB（若仓库已包含）。映射见 `config/robot_models.yaml`、`config/model_glb_map.yaml`。缺模型时 3D 区域为空，不影响焊接与上传。

---

## 典型工作流

1. **登录** → 选择网卡与 UDP 端口，连接机器人。  
2. **焊接** → 标定左上/右上/左下三点 → 输入文字与参数 →「生成焊接点」→ 查看 `output/` 下 Lua 与预览图。  
3. **上传** → 选择生成的 `.lua`（可用「最新输出」）→ 填写工程名 → 上传并绑定槽位。  
4. 在机器人端通过对应槽位或工程名运行焊接程序。

---

## 输出目录

```text
output/<时间戳>_<摘要>_<模式>/
  points.txt, job.json, *.lua
  preview_execution.png
  summary.json
  ...
```

`output/`、`log/` 已在 `.gitignore` 中排除，勿提交运行产物。

---

## 项目结构

```text
main.py                 入口
app/                    界面、路由、信号、帮助手册
network/                TCP/UDP、ConnectionManager
services/               焊接、CRI、工程上传 SDK
pipeline/               离线轨迹算法（无 Qt）
core/                   类型、日志、配置
config/                 默认参数、机型、字体预设
models/                 机器人 GLB（若已提交）
view3d/                 首页 3D 预览
styles/                 QSS 主题
docs/                   API 与架构文档
third_party/            第三方数据说明（大文件本地自备）
tools/                  验收脚本、mock 等
```

---

## 配置与持久化

- **QSettings**：`Codroid` / `RobotUI`（登录 IP、焊接/上传参数等）  
- **主题与语言**：菜单「设置」→ 样式主题；「语言」中/英  
- **菜单「帮助」**：焊接页、上传页操作说明

---

## 开发与维护

1. UI 不直接操作 socket；经 `ConnectionManager.send_call` 发 TCP。  
2. 焊接算法改 `pipeline/` 与 `services/welding_service_v2.py`，用预览 PNG 与 `summary.json` 验收。  
3. 改机器人接口时同步 **docs/planAPI.md**。  
4. 本地 mock：`tools/mock_robot_server.py`（按需）。

---

## 许可证与第三方

- Hershey 字体：见 [docs/NOTICE.md](docs/NOTICE.md)  
- MakeMeAHanzi / ARPHIC：汉字数据遵循上游许可  

---

## 文档索引

| 文件 | 用途 |
|------|------|
| [README.md](README.md) | 本文件 |
| [docs/planAPI.md](docs/planAPI.md) | 机器人 API |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构（参考） |
| [docs/NOTICE.md](docs/NOTICE.md) | 第三方许可 |
