"""机器人运行模式 — 与全局命令栏 / RobotStatus 一致。"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

ROBOT_MODE_MANUAL = 0
ROBOT_MODE_AUTO = 1
ROBOT_MODE_REMOTE = 2
ROBOT_MODE_UNKNOWN = -1


def normalize_robot_mode(value) -> int:
    """将 RobotStatus.mode 规范为 0/1/2；无效则返回 ROBOT_MODE_UNKNOWN。"""
    try:
        mode = int(value)
    except (TypeError, ValueError):
        return ROBOT_MODE_UNKNOWN
    if mode in (ROBOT_MODE_MANUAL, ROBOT_MODE_AUTO, ROBOT_MODE_REMOTE):
        return mode
    return ROBOT_MODE_UNKNOWN


def query_robot_mode(widget: QWidget | None) -> int:
    """从主窗口命令栏读取当前模式（0 手动 / 1 自动 / 2 远程；-1 未知）。"""
    if widget is None:
        return ROBOT_MODE_UNKNOWN
    win = widget.window()
    bar = getattr(win, "_command_bar", None)
    if bar is None:
        return ROBOT_MODE_UNKNOWN
    sw = getattr(bar, "_mode_switch", None)
    if sw is None:
        return ROBOT_MODE_UNKNOWN
    return int(getattr(sw, "_current", ROBOT_MODE_UNKNOWN))


def is_remote_mode(mode: int) -> bool:
    """是否处于远程模式（与 RobotStatus 订阅 mode 字段一致）。"""
    return mode == ROBOT_MODE_REMOTE
