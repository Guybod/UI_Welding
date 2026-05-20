"""文字生成管线分流 — text_source / script_type / render_mode（UI 与 summary 共用）。"""

from __future__ import annotations

from typing import Any

# 稳定 id（itemData / QSettings / summary）
TEXT_SOURCE_TTF_CONTOUR = "ttf_contour"
TEXT_SOURCE_LATIN_STROKE = "latin_stroke"
TEXT_SOURCE_HANZI_STROKE = "hanzi_stroke"
TEXT_SOURCE_IMAGE_CONTOUR = "image_contour"

SCRIPT_LATIN = "latin"
SCRIPT_HANZI = "hanzi"
SCRIPT_MIXED = "mixed"
SCRIPT_IMAGE = "image"

RENDER_CONTOUR = "contour"
RENDER_STROKE = "stroke"
RENDER_IMAGE = "image"

WELDING_TEXT_SOURCE_IDS = (
    TEXT_SOURCE_TTF_CONTOUR,
    TEXT_SOURCE_LATIN_STROKE,
    TEXT_SOURCE_HANZI_STROKE,
)

DRAWING_TEXT_SOURCE_IDS = (
    TEXT_SOURCE_TTF_CONTOUR,
    TEXT_SOURCE_LATIN_STROKE,
    TEXT_SOURCE_IMAGE_CONTOUR,
    TEXT_SOURCE_HANZI_STROKE,
)


def script_type_for_text_source(text_source: str) -> str:
    return {
        TEXT_SOURCE_TTF_CONTOUR: SCRIPT_MIXED,
        TEXT_SOURCE_LATIN_STROKE: SCRIPT_LATIN,
        TEXT_SOURCE_HANZI_STROKE: SCRIPT_HANZI,
        TEXT_SOURCE_IMAGE_CONTOUR: SCRIPT_IMAGE,
    }.get(text_source, SCRIPT_MIXED)


def render_mode_for_text_source(text_source: str) -> str:
    if text_source == TEXT_SOURCE_IMAGE_CONTOUR:
        return RENDER_IMAGE
    if text_source in (TEXT_SOURCE_LATIN_STROKE, TEXT_SOURCE_HANZI_STROKE):
        return RENDER_STROKE
    return RENDER_CONTOUR


def is_text_source_not_implemented(text_source: str, *, target_process: str = "weld") -> bool:
    """保留扩展点；当前焊接/绘图文字源均已实现。"""
    _ = text_source, target_process
    return False


def hanzi_not_implemented_message(*, lang: str = "zh") -> str:
    if lang == "en":
        return (
            "Hanzi stroke welding is not available yet; "
            "stroke data (MakeMeAHanzi / HanziWriter) is not connected."
        )
    return "骨架汉字功能待接入汉字笔画数据，当前不可生成。"


def drawing_latin_stroke_pending_message(*, lang: str = "zh") -> str:
    if lang == "en":
        return (
            "Drawing latin stroke will reuse Hershey single-line fonts; "
            "trajectory generation via drawing/CRI is in progress."
        )
    return "绘画页骨架数字字母将复用 Hershey 单线字，轨迹生成接入中。"


def migrate_welding_text_source(
    *,
    text_source: str | None = None,
    legacy_mode: str | None = None,
) -> str:
    """QSettings 兼容：优先 text_source；否则由旧 mode 迁移。"""
    if text_source and str(text_source).strip():
        ts = str(text_source).strip()
        if ts in WELDING_TEXT_SOURCE_IDS:
            return ts
    mode = (legacy_mode or "").strip().lower()
    if mode == "contour":
        return TEXT_SOURCE_TTF_CONTOUR
    if mode == "skeleton":
        return TEXT_SOURCE_LATIN_STROKE
    return TEXT_SOURCE_LATIN_STROKE


def legacy_mode_from_text_source(text_source: str) -> str:
    """映射到 offline_runner 既有 mode 字符串。"""
    if text_source == TEXT_SOURCE_TTF_CONTOUR:
        return "contour"
    if text_source in (TEXT_SOURCE_LATIN_STROKE, TEXT_SOURCE_HANZI_STROKE):
        return "skeleton"
    return "contour"


def skeleton_source_for_text_source(text_source: str) -> str:
    if text_source == TEXT_SOURCE_HANZI_STROKE:
        return "makemeahanzi"
    if text_source == TEXT_SOURCE_LATIN_STROKE:
        return "hershey"
    return "hershey"


def build_text_pipeline(
    text_source: str,
    *,
    hershey_style: str = "futural",
    stroke_font_source: str = "hershey",
    target_process: str = "weld",
) -> dict[str, Any]:
    """写入 summary.json 的 text_pipeline 块。"""
    base: dict[str, Any] = {
        "text_source": text_source,
        "script_type": script_type_for_text_source(text_source),
        "render_mode": render_mode_for_text_source(text_source),
        "target_process": target_process,
    }
    if text_source == TEXT_SOURCE_LATIN_STROKE:
        base["stroke_font_source"] = stroke_font_source or "hershey"
        base["hershey_style"] = hershey_style or "futural"
    elif text_source == TEXT_SOURCE_HANZI_STROKE:
        base["stroke_font_source"] = "makemeahanzi"
        base["used_field"] = "medians"
        base["ttf_fallback_used"] = False
    return base
