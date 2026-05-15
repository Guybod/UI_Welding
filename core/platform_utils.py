"""跨平台工具 — 打开文件/目录、执行外部命令

统一封装操作系统差异，优先使用 Qt 接口，fallback 到系统命令。
支持 GUI (PySide6) 和 CLI/离线两种模式。
"""

import os
import subprocess
import sys


def open_path(path: str):
    """跨平台打开文件或目录。

    优先使用 QDesktopServices (Qt)，fallback 到系统命令。

    Args:
        path: 文件或目录路径
    """
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"path not found: {path}")

    # 优先 Qt
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        return
    except ImportError:
        pass
    except Exception:
        pass  # Qt 打开失败，fallback

    # Fallback: 系统命令
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", path], timeout=5)
    else:
        subprocess.run(["xdg-open", path], timeout=5)


def run_external(cmd: list[str], timeout: float = 30, cwd: str | None = None):
    """跨平台执行外部命令。

    Args:
        cmd: 命令和参数列表 (e.g. ['python', 'script.py'])
        timeout: 超时秒数
        cwd: 工作目录

    Returns:
        subprocess.CompletedProcess

    Raises:
        subprocess.TimeoutExpired: 超时
        FileNotFoundError: 命令不存在
    """
    try:
        return subprocess.run(cmd, timeout=timeout, cwd=cwd, check=False)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"command not found: {cmd[0]}. "
            f"Ensure it is installed and available in PATH."
        )
