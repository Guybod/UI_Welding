"""汉字骨架文本校验 — 缺字即失败，禁止 TTF fallback。"""

from __future__ import annotations


def collect_text_chars(text: str) -> list[str]:
    """去重保序，忽略换行与空白。"""
    seen: set[str] = set()
    out: list[str] = []
    for ch in text:
        if ch in "\n\r" or ch.isspace():
            continue
        if ch not in seen:
            seen.add(ch)
            out.append(ch)
    return out


def find_missing_hanzi_chars(text: str, glyphs: dict) -> list[str]:
    missing: list[str] = []
    for ch in collect_text_chars(text):
        if ch not in glyphs:
            missing.append(ch)
    return missing


def validate_hanzi_drawing_text(
    text: str,
    glyphs: dict,
    *,
    lang: str = "zh",
) -> str | None:
    """不通过返回错误信息；通过返回 None。"""
    if not text or not text.strip():
        if lang == "en":
            return "Text is empty."
        return "文本为空。"
    missing = find_missing_hanzi_chars(text, glyphs)
    if not missing:
        return None
    display = "".join(missing[:30])
    extra = len(missing) - 30
    suffix = f" …等{extra}字" if extra > 0 else ""
    if lang == "en":
        return (
            f"Missing MakeMeAHanzi glyphs ({len(missing)}): {display!r}{suffix}. "
            "No TTF fallback."
        )
    return (
        f"MakeMeAHanzi 缺字 ({len(missing)} 个): {display!r}{suffix}。"
        "不允许回退到字体渲染。"
    )
