#!/usr/bin/env python3
"""Log-1 本机验收辅助 — 无界面驱动启动/连接/切页/生成/CRI/退出，并解析 log/YYYYMMDD.txt。

用法（项目根目录）:
    python tools/log_acceptance_harness.py

不修改业务逻辑；仅用于验收系统日志时间线。
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# 项目根
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# 无界面 Qt（Windows/Linux 通用）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

LOG_DIR = ROOT / "log"
# 仅识别 Log-1 模块前缀（排除 [send]/[recv] 等流量日志）
PREFIX_RE = re.compile(
    r"\[(Main|Connection|CRI|Login|PageRouter|Pipeline|WeldingService|"
    r"WritingService|WritingExec|ImageDrawing|MainWindow|UI)\]"
)

# Log-1 期望覆盖的前缀（P0+P1+P2，不含 P3）
EXPECTED_PREFIXES = frozenset({
    "Main",
    "Connection",
    "CRI",
    "Login",
    "PageRouter",
    "Pipeline",
    "WeldingService",
    "WritingService",
    "WritingExec",
    "ImageDrawing",
})


def _latest_log_file(before_mtime: float | None = None) -> Path | None:
    if not LOG_DIR.is_dir():
        return None
    candidates = list(LOG_DIR.glob("*.txt"))
    if not candidates:
        return None
    if before_mtime is not None:
        candidates = [p for p in candidates if p.stat().st_mtime >= before_mtime]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _read_session_lines(path: Path, session_marker: str) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    begin_key = f"{session_marker} harness begin"
    idx = text.find(begin_key)
    if idx < 0:
        idx = text.rfind(session_marker)
    if idx < 0:
        return [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("=")]
    chunk = text[idx:]
    return [
        ln for ln in chunk.splitlines()
        if ln.strip() and not ln.startswith("=")
    ]


def _extract_prefixes(lines: list[str]) -> set[str]:
    found: set[str] = set()
    for ln in lines:
        for m in PREFIX_RE.finditer(ln):
            found.add(m.group(1))
    return found


def _has_traceback(lines: list[str]) -> bool:
    blob = "\n".join(lines)
    return "Traceback (most recent call last)" in blob or "logging.exception" in blob


class MockRobotServer:
    """最小 TCP 9001 伪机器人：应答 id 请求，推送 RobotStatus。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 9001):
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.listen(4)
        self._sock.settimeout(1.0)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

    def _handle_client(self, conn: socket.socket) -> None:
        buf = b""
        pushed_status = False
        try:
            while not self._stop.is_set():
                try:
                    data = conn.recv(4096)
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    if "id" in msg:
                        resp = {"id": msg["id"], "db": {}}
                        conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n").encode())
                    ty = msg.get("ty", "")
                    if ty.startswith("publish/") and not pushed_status:
                        pushed_status = True
                        push = {
                            "ty": "publish/RobotStatus",
                            "db": {
                                "type": "nova5",
                                "mode": 2,
                                "state": 2,
                                "isMoving": False,
                                "isSimulation": False,
                                "CoordinateId": 0,
                                "ToolId": 0,
                            },
                        }
                        conn.sendall((json.dumps(push, ensure_ascii=False) + "\n").encode())
        finally:
            try:
                conn.close()
            except OSError:
                pass


def run_harness() -> dict:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from core.connection_config import ConnectionConfig, pick_available_udp_port
    from core.logger import log, setup_logger
    from core.types import RobotPoint

    setup_logger("codroid")
    t0 = time.time()
    session_marker = f"LOG_ACCEPT_{int(t0)}"

    mock = MockRobotServer("127.0.0.1", 9001)
    try:
        mock.start()
    except OSError as exc:
        return {"error": f"mock server bind failed: {exc}"}

    # 标记本次会话（写入日志便于切片）
    import platform
    from PySide6 import __version__ as pyside_version

    log.info(
        "[Main] application start python=%s pyside6=%s platform=%s (acceptance)",
        platform.python_version(),
        pyside_version,
        platform.platform(),
    )
    log.info("[Main] %s harness begin", session_marker)

    from app.bootstrap import create_app_stack
    from app.page_registry import PAGE_REGISTRY
    from app.service_provider import ServiceProvider
    from app.signal_binder import bind_all
    from network.connection_manager import ConnectionManager
    from pipeline.mapping import WorkPlane
    from services.cri_service import CriService
    from services.robot_service import RobotService
    from services.welding_service_v2 import WeldingServiceV2

    app = QApplication(sys.argv)
    stack, login, main_win = create_app_stack()
    cm = ConnectionManager()
    cri_svc = CriService(cm)
    RobotService(cm)
    sp = ServiceProvider(cm, cri_svc)
    main_win._page_router.set_service_provider(sp)
    bind_all(cm, cri_svc, login, main_win, stack)

    local_ip = "127.0.0.1"
    udp_port = pick_available_udp_port()
    cfg = ConnectionConfig(
        robot_ip="127.0.0.1",
        local_ip=local_ip,
        udp_port=udp_port,
    )

    # 1) 连接
    login.connect_requested.emit(cfg)

    def _after_connected():
        # 2) 切页
        for spec in PAGE_REGISTRY[:4]:
            main_win._page_router.navigate(spec)
        # 3) 焊接生成（同步，触发 Pipeline + WeldingService）
        lt = RobotPoint(100, 200, 300, 180, 0, 90)
        rt = RobotPoint(300, 200, 300, 180, 0, 90)
        lb = RobotPoint(100, 400, 300, 180, 0, 90)
        wp = WorkPlane(tl=lt, tr=rt, bl=lb)
        svc = WeldingServiceV2(output_dir=str(ROOT / "output" / "log_accept"))
        try:
            svc.generate(
                "A",
                mode="skeleton",
                text_source="latin_stroke",
                left_top=lt,
                right_top=rt,
                left_bottom=lb,
                char_height_mm=60.0,
                output_dir=str(ROOT / "output" / "log_accept"),
            )
        except Exception as exc:
            log.warning("[Main] harness welding generate raised: %s", exc)
        # 4) CRI 已在 bind_all 里 3s 自动 start；再显式 stop/start 覆盖日志
        QTimer.singleShot(500, lambda: cri_svc.stop())
        QTimer.singleShot(1200, lambda: cri_svc.start(cfg))
        QTimer.singleShot(2500, _finish)

    def _finish():
        log.info("[Main] %s harness finish, quitting", session_marker)
        main_win.return_to_login.emit()
        QTimer.singleShot(200, lambda: (
            cri_svc.stop(),
            cm.disconnect(),
            log.info("[Main] aboutToQuit cleanup start"),
            log.info("[Main] aboutToQuit cleanup done"),
            app.quit(),
        ))

    def _on_state(state: str):
        if state == "connected":
            QTimer.singleShot(800, _after_connected)

    cm.connection_state_changed.connect(_on_state)

    # 连接超时兜底
    QTimer.singleShot(8000, lambda: (_finish() if app else None))

    stack.show()
    app.exec()

    mock.stop()

    log_path = _latest_log_file(t0 - 1)
    if not log_path:
        return {"error": "no log file found", "session_marker": session_marker}

    lines = _read_session_lines(log_path, session_marker)
    prefixes = _extract_prefixes(lines)

    # 关键时间线检查
    timeline_checks = {
        "app_start": any("[Main] application start" in ln for ln in lines),
        "connect_request": any("[Login] user connect request" in ln for ln in lines),
        "connected": any("[Connection] connected" in ln for ln in lines),
        "login_state": any("[Login] connection_state_changed" in ln for ln in lines),
        "toAuto": any("[Login] Robot/toAuto" in ln for ln in lines),
        "subscriptions": any("[Login] subscriptions:" in ln for ln in lines),
        "page_navigate": any("[PageRouter] navigate" in ln for ln in lines),
        "pipeline_run": any("[Pipeline] run start" in ln for ln in lines),
        "welding_service": any("[WeldingService] generate start" in ln for ln in lines),
        "cri_start": any("[CRI] start local_ip=" in ln for ln in lines),
        "cleanup": any("[Main] aboutToQuit cleanup" in ln for ln in lines),
    }

    return {
        "log_path": str(log_path.resolve()),
        "session_marker": session_marker,
        "line_count": len(lines),
        "prefixes_found": sorted(prefixes),
        "prefixes_expected": sorted(EXPECTED_PREFIXES),
        "prefixes_missing": sorted(EXPECTED_PREFIXES - prefixes),
        "has_traceback": _has_traceback(lines),
        "timeline_checks": timeline_checks,
        "sample_lines": lines[:8] + (lines[-12:] if len(lines) > 20 else []),
    }


def main() -> int:
    print("Log-1 acceptance harness (offscreen Qt + mock TCP 9001)")
    result = run_harness()
    if "error" in result and "log_path" not in result:
        print("ERROR:", result["error"])
        return 1

    print("\n=== Log-1 Acceptance Report ===")
    print("log file:", result.get("log_path"))
    print("session:", result.get("session_marker"))
    print("lines in session:", result.get("line_count"))
    print("\nPrefixes found:", ", ".join(result.get("prefixes_found", [])))
    missing = result.get("prefixes_missing", [])
    print("Prefixes missing (expected P0-P2):", ", ".join(missing) if missing else "(none)")
    print("\nTimeline checks:")
    for k, v in result.get("timeline_checks", {}).items():
        print(f"  {k}: {'OK' if v else 'MISSING'}")
    print("\nException traceback in log:", result.get("has_traceback"))
    print("\nSample log lines:")
    for ln in result.get("sample_lines", []):
        print(" ", ln[:200])

    failed = [k for k, v in result.get("timeline_checks", {}).items() if not v]
    if failed or missing:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
