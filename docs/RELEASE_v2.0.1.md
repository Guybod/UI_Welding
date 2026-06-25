# Codroid 焊接上位机 / Codroid Welding UI

## Release v2.0.1

| | |
|---|---|
| **版本 / Version** | v2.0.1 |
| **发布日期 / Release Date** | 2025-06-25 |
| **代号 / Codename** | — |
| **适用平台 / Platform** | Windows 10/11（主要）；源码亦可在 Linux 下运行 / Windows 10/11 (primary); source runnable on Linux |
| **Python** | 3.11+ 推荐 / recommended |
| **基线版本 / Baseline** | v2.0.0 |

---

## 摘要 / Summary

### 中文

本版本为 **v2.0.0 后的维护与体验更新**，重点修复跨平台克隆后源码无法启动的严重问题，并在登录页补齐中英文切换能力。

建议所有用户升级至 v2.0.1。

### English

This release is a **maintenance and UX update** following v2.0.0. It fixes a critical issue where corrupted source files prevented the application from starting after cross-platform checkout, and adds a Chinese/English language toggle on the login screen.

All users are encouraged to upgrade to v2.0.1.

---

## 新增功能 / New Features

### 登录页语言切换 / Login Page Language Toggle

| 中文 | English |
|------|---------|
| 登录界面右上角新增语言切换按钮 | Language toggle button added to the top-right of the login screen |
| 与主界面共用 `ui/language` 设置（`QSettings`） | Shares `ui/language` setting with the main window via `QSettings` |
| 登录页表单、按钮、状态栏及连接失败提示均已国际化 | Login form, buttons, status text, and connection-failure dialogs are fully localized |

**涉及提交 / Commits:** `979f02c`

---

## 缺陷修复 / Bug Fixes

### 源码损坏导致无法启动 / Corrupted Sources Preventing Startup

| 严重级别 / Severity | **Critical** |
|---------------------|--------------|
| 现象 / Symptom | `SyntaxError: source code string cannot contain null bytes` on import |
| 原因 / Cause | Commit `681b14b` accidentally committed EFS-encrypted/binary `.py` payloads instead of plain UTF-8 source |
| 修复 / Fix | Restored 40+ affected files from clean Git history (`1d2fbe6` / `33c822b`) |
| 涉及模块 / Affected areas | `app/`, `pipeline/`, `network/`, `core/`, `services/`, `tools/` |

**涉及提交 / Commits:** `0fc0d6d`

### requirements.txt 换行符 / requirements.txt Line Endings

| 中文 | English |
|------|---------|
| 修复 CR-only（`\r`）换行导致 Windows 下整文件显示为一行 | Fixed CR-only (`\r`) line endings that collapsed the file into one line on Windows |
| 统一为 Unix LF（`\n`） | Normalized to Unix LF (`\n`) |

**涉及提交 / Commits:** `0fc0d6d`

---

## 已知限制 / Known Limitations

| 中文 | English |
|------|---------|
| 轮廓字模式依赖 Windows 系统字体（如 Arial、微软雅黑） | Contour text mode relies on Windows system fonts (e.g. Arial, Microsoft YaHei) |
| 骨架汉字（MakeMeAHanzi）需自备 `third_party/makemeahanzi/graphics.txt` | Hanzi stroke mode requires `third_party/makemeahanzi/graphics.txt` |
| `models/` 目录无 GLB 时，首页 3D 预览无机器人模型（功能可降级运行） | Without GLB files in `models/`, the home-page 3D preview shows no robot mesh (app remains usable) |

---

## 系统要求 / System Requirements

| 项目 / Item | 要求 / Requirement |
|-------------|-------------------|
| 操作系统 / OS | Windows 10/11（推荐）/ recommended |
| Python（源码）/ Python (source) | 3.11+ |
| 网络 / Network | 与机器人控制器同一网段 / Same subnet as robot controller |
| 端口 / Ports | TCP **9001**；UDP **9030**（CRI）；本地 UDP 由登录页分配 / TCP **9001**; UDP **9030** (CRI); local UDP assigned on login |
| 显卡 / GPU | 支持 OpenGL 2.1+（3D 预览）/ OpenGL 2.1+ for 3D preview |

---

## 安装与升级 / Installation & Upgrade

### 从源码运行 / Run from Source

```powershell
git clone https://github.com/Guybod/UI_Welding.git
cd UI_Welding
git checkout v2.0.1   # 或拉取 main 最新 / or pull latest main

python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### 从 v2.0.0 升级 / Upgrade from v2.0.0

```powershell
git pull origin main
pip install -r requirements.txt
```

---

## 完整变更记录 / Full Changelog

```
979f02c feat: add language toggle on login page with i18n strings
0fc0d6d fix: restore corrupted Python sources and normalize requirements line endings
```

---

## 反馈与支持 / Feedback & Support

| 中文 | English |
|------|---------|
| 问题反馈请提交至 GitHub Issues | Please report issues via GitHub Issues |
| 仓库地址：https://github.com/Guybod/UI_Welding | Repository: https://github.com/Guybod/UI_Welding |

---

*Codroid 机器人控制终端 · UI_Welding · v2.0.1*
