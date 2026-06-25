# UI_Welding — Codroid Welding Control Terminal

> **中文:** [README.md](README.md)

A **PySide6** desktop application for Codroid collaborative robot welding: connect to the controller, generate text weld trajectories, upload Lua projects, and monitor robot status with global jogging controls.

**Repository:** https://github.com/Guybod/UI_Welding.git

**Current version:** v2.0.1 · [Release notes](docs/RELEASE_v2.0.1.md)

---

## Features

| Module | Description |
|--------|-------------|
| **Login** | Robot IP, local NIC, UDP port; TCP 9001 connection; Chinese/English toggle (top-right) |
| **Home** | Connection/CRI status, joint & TCP overview, GLB 3D preview |
| **Welding** | Contour / Hershey Latin stroke / Hanzi medians → `points.txt`, `job.json`, Lua; 3-point workplane calibration |
| **Upload** | HTTP/WebSocket Lua project upload; slot binding (0–127) |
| **Global** | Enable, manual/auto/remote, simulation, project run/stop, jog drawer, moveTo presets, speed control |
| **Help** | Menu **Help** → welding / upload manuals (Chinese & English) |

Robot protocol: **[docs/planAPI.md](docs/planAPI.md)**.  
Architecture: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** (some sections may lag the simplified UI; refer to source code).

---

## Requirements

- Windows 10/11 (primary development and deployment target)
- Python **3.11+** recommended
- Same subnet as the robot controller (example IP: `192.168.1.136`)
- Ports: TCP **9001**, UDP **9030** (CRI), local UDP for CRI push (assigned on login page)
- GPU: OpenGL 2.1+ (home-page 3D preview)

---

## Install & Run

```powershell
git clone https://github.com/Guybod/UI_Welding.git
cd UI_Welding

python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

python main.py
```

Logs: `log/YYYYMMDD.txt`.

---

## External Data

### Hanzi stroke mode (welding)

Download `graphics.txt` from [MakeMeAHanzi](https://github.com/skishore/makemeahanzi) and place it at:

```text
third_party/makemeahanzi/graphics.txt
```

Large file — **not in Git**. Hanzi stroke generation fails without it. See [third_party/makemeahanzi/README.md](third_party/makemeahanzi/README.md).

### Weld fonts

- **Contour:** system TTF or presets in `config/weld_font_presets.yaml`
- **Latin stroke:** `Hershey-Fonts` (`requirements.txt`, [docs/NOTICE.md](docs/NOTICE.md))
- **Hanzi stroke:** requires `graphics.txt` above

### 3D models (home preview)

Place robot GLB files under `models/` (if not shipped in the repo). Mapping: `config/robot_models.yaml`, `config/model_glb_map.yaml`. Missing models leave the 3D view empty; welding and upload still work.

---

## Typical Workflow

1. **Login** → select NIC and UDP port, connect (switch UI language if needed).
2. **Welding** → calibrate LT/RT/LB → enter text and parameters → **Generate weld points** → inspect Lua and previews under `output/`.
3. **Upload** → pick generated `.lua` (**Latest output**) → project name → upload and bind slot.
4. Run the weld program on the robot via the bound slot or project name.

---

## Output Layout

```text
output/<timestamp>_<summary>_<mode>/
  points.txt, job.json, *.lua
  preview_execution.png
  summary.json
  ...
```

`output/`, `log/`, `dist/`, and `build/` are gitignored — do not commit runtime artifacts.

---

## Project Layout

```text
main.py                 Entry point
app/                    UI, routing, signals, help, QSS themes
network/                TCP/UDP, ConnectionManager
services/               Welding, CRI, project upload SDK
pipeline/               Offline trajectory (no Qt)
core/                   Types, logging, paths, config
config/                 Defaults, robot models, font presets
models/                 Robot GLB (if committed)
view3d/                 Home-page 3D preview
docs/                   API, architecture, release notes
third_party/            Third-party data notes (large files local)
tools/                  Acceptance scripts, mock server, etc.
```

---

## Settings & Persistence

- **QSettings:** `Codroid` / `RobotUI` (login IP, UI language, weld/upload parameters, etc.)
- **Theme & language:** main menu **Settings** → style theme; **Language** zh/en (also on login page top-right)
- **Help menu:** welding and upload page manuals

---

## Development

1. UI must not touch sockets directly — use `ConnectionManager.send_call` for TCP.
2. Weld algorithms: `pipeline/` and `services/welding_service_v2.py`; validate with preview PNG and `summary.json`.
3. Update **docs/planAPI.md** when robot APIs change.
4. Local mock: `tools/mock_robot_server.py` (optional).

---

## License & Third Party

- Hershey fonts: [docs/NOTICE.md](docs/NOTICE.md)
- MakeMeAHanzi / ARPHIC: follow upstream licenses for Hanzi data

---

## Documentation Index

| File | Purpose |
|------|---------|
| [README.md](README.md) | Chinese README |
| [README_EN.md](README_EN.md) | This file (English) |
| [docs/RELEASE_v2.0.1.md](docs/RELEASE_v2.0.1.md) | v2.0.1 release notes |
| [docs/planAPI.md](docs/planAPI.md) | Robot API |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Architecture (reference) |
| [docs/NOTICE.md](docs/NOTICE.md) | Third-party notices |
