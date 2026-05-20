"""焊接骨架字 — 拉丁字母数字字符集校验（Phase W1）。"""

from __future__ import annotations

import re

# 正式支持：A-Z a-z 0-9 空格；可选稳定符号 - _ .
SKELETON_LATIN_PATTERN = re.compile(r"^[A-Za-z0-9 \-_.]*$")
SKELETON_ALLOWED_CHARSET_DESC = "A-Za-z0-9 space - _ ."
SKELETON_CHARSET_UI_ZH = "焊接骨架模式当前仅支持 A-Z、a-z、0-9 和空格。"
SKELETON_CHARSET_UI_EN = (
    "Skeleton weld mode only supports A-Z, a-z, 0-9, and space."
)
def find_illegal_skeleton_chars(text: str) -> list[str]:
    """返回 text 中不在允许集合内的字符（去重保序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for ch in text:
        if ch in ("\n", "\r"):
            continue
        if SKELETON_LATIN_PATTERN.match(ch):
            continue
        if ch not in seen:
            seen.add(ch)
            out.append(ch)
    return out


def has_skeleton_multiline(text: str) -> bool:
    return "\n" in text or "\r" in text


def validate_weld_skeleton_text(text: str, *, lang: str = "zh") -> str | None:
    """不通过时返回用户可读错误信息；通过返回 None。"""
    illegal = find_illegal_skeleton_chars(text)
    if not illegal:
        return None
    chars_display = "".join(illegal[:20])
    if lang == "en":
        return (
            f"{SKELETON_CHARSET_UI_EN} Invalid: {chars_display!r}"
        )
    return f"{SKELETON_CHARSET_UI_ZH} 非法字符: {chars_display!r}"


def skeleton_charset_descriptor() -> str:
    return SKELETON_ALLOWED_CHARSET_DESC
