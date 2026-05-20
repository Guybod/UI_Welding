"""界面日志 — 统一时间戳、写入 QPlainTextEdit，并同步到系统日志文件（log/）。"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit

from core.logger import log as _default_logger

# 已有完整日期时间或 CRI 毫秒前缀则不再重复添加
_UI_TS_PREFIX = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}|\d{2}:\d{2}:\d{2}\.\d{3})\]\s"
)


def format_ui_log_line(msg: str) -> str:
    """为界面日志行添加 ``[YYYY-MM-DD HH:MM:SS]`` 前缀。"""
    text = (msg or "").rstrip("\n")
    if _UI_TS_PREFIX.match(text):
        return text
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"[{ts}] {text}"


def append_ui_log(
    widget: QPlainTextEdit | None,
    msg: str,
    *,
    source: str = "",
    logger: logging.Logger | None = None,
) -> str:
    """追加一行 UI 日志，并写入系统 logger（持久化到 log/ 目录）。"""
    line = format_ui_log_line(msg)
    if widget is not None:
        widget.appendPlainText(line)
    lg = logger or _default_logger
    if source:
        lg.info("[%s] %s", source, msg)
    else:
        lg.info("%s", msg)
    return line
