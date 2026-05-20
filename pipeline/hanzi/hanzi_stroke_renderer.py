"""MakeMeAHanzi medians → Stroke 列表（px），支持单行/多行排版。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from core.types import PixelPoint, Stroke
from pipeline.hanzi.hanzi_data_loader import HanziGlyph, Point, load_hanzi_graphics
from pipeline.hanzi.hanzi_text_validate import (
    collect_text_chars,
    find_missing_hanzi_chars,
    validate_hanzi_drawing_text,
)
from pipeline.multiline_layout import estimate_layout_size_mm, line_step_mm, split_text_lines

RENDERER_MODULE = "pipeline.hanzi.hanzi_stroke_renderer"
RENDERER_VERSION = "1.0.0"

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_GRAPHICS = _PROJECT_ROOT / "third_party" / "makemeahanzi" / "graphics.txt"


def resolve_graphics_path(path: str | Path | None = None) -> Path:
    if path:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"MakeMeAHanzi graphics.txt 不存在: {p.resolve()}")
        return p
    if _DEFAULT_GRAPHICS.is_file():
        return _DEFAULT_GRAPHICS
    raise FileNotFoundError(
        f"未找到 graphics.txt，请放置到 {_DEFAULT_GRAPHICS} 或通过参数指定路径"
    )


def _glyph_bbox(glyph: HanziGlyph) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for stroke in glyph.medians:
        for p in stroke:
            xs.append(p.x)
            ys.append(p.y)
    if not xs:
        return 0.0, 0.0, 1.0, 1.0
    return min(xs), min(ys), max(xs), max(ys)


def _medians_to_local_px(
    glyph: HanziGlyph,
    target_px: float,
) -> tuple[list[list[tuple[float, float]]], float]:
    """归一化到 target_px 方框，Y 向下（与后续 Stroke / PIL 一致）。"""
    min_x, min_y, max_x, max_y = _glyph_bbox(glyph)
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)
    scale = target_px / max(w, h)
    pad_x = (target_px - w * scale) * 0.5
    pad_y = (target_px - h * scale) * 0.5
    strokes: list[list[tuple[float, float]]] = []
    for stroke in glyph.medians:
        row: list[tuple[float, float]] = []
        for p in stroke:
            x = (p.x - min_x) * scale + pad_x
            y = (max_y - p.y) * scale + pad_y
            row.append((x, y))
        if len(row) >= 2:
            strokes.append(row)
    width_px = target_px
    return strokes, width_px


def _glyph_to_strokes(
    glyph: HanziGlyph,
    ch: str,
    *,
    char_height_px: float,
    char_scale: float = 0.85,
    char_index: int,
    line_index: int,
    line_text: str,
) -> tuple[list[Stroke], float]:
    target_px = char_height_px * char_scale
    polylines, advance_px = _medians_to_local_px(glyph, target_px)
    out: list[Stroke] = []
    for si, poly in enumerate(polylines):
        pts = [PixelPoint(x=round(x, 3), y=round(y, 3)) for x, y in poly]
        out.append(
            Stroke(
                id=str(uuid.uuid4()),
                source_type="skeleton",
                points_px=pts,
                closed=False,
                metadata={
                    "extract_algorithm": "makemeahanzi",
                    "skeleton_source": "makemeahanzi",
                    "used_field": "medians",
                    "ttf_fallback_used": False,
                    "hanzi_char": ch,
                    "weld_char": ch,
                    "weld_char_index": char_index,
                    "glyph_stroke_index": si,
                    "layout_line_index": line_index,
                    "layout_line_text": line_text,
                },
            )
        )
    return out, advance_px


def render_hanzi_multiline_to_strokes(
    text: str,
    glyphs: dict[str, HanziGlyph],
    *,
    char_height_mm: float,
    char_spacing_mm: float,
    line_spacing_mm: float = 0.0,
    px_per_mm: float = 10.0,
    char_scale: float = 0.85,
) -> tuple[list[Stroke], dict[str, Any]]:
    """多行汉字 medians → Stroke（缺字在调用前应已校验）。"""
    lines = split_text_lines(text)
    char_height_px = char_height_mm * px_per_mm
    spacing_px = char_spacing_mm * px_per_mm
    step_px = line_step_mm(char_height_mm, line_spacing_mm) * px_per_mm

    all_strokes: list[Stroke] = []
    line_widths_px: list[float] = []
    global_char_idx = 0
    glyph_count = 0
    stroke_count = 0

    for line_idx, line in enumerate(lines):
        y_off = line_idx * step_px
        x_cursor = 0.0
        line_w = 0.0

        for ch in line:
            if ch.isspace():
                x_cursor += spacing_px * 0.5
                continue

            glyph = glyphs[ch]
            glyph_count += 1
            char_strokes, advance_px = _glyph_to_strokes(
                glyph,
                ch,
                char_height_px=char_height_px,
                char_scale=char_scale,
                char_index=global_char_idx,
                line_index=line_idx,
                line_text=line,
            )
            global_char_idx += 1
            for s in char_strokes:
                s.points_px = [
                    PixelPoint(x=round(p.x + x_cursor, 3), y=round(p.y + y_off, 3))
                    for p in s.points_px
                ]
                all_strokes.append(s)
            stroke_count += len(char_strokes)
            x_cursor += advance_px + spacing_px
            line_w = max(line_w, x_cursor - spacing_px)

        line_widths_px.append(line_w)

    inv = 1.0 / px_per_mm if px_per_mm > 0 else 1.0
    line_widths_mm = [w * inv for w in line_widths_px]
    req_w_mm, req_h_mm = estimate_layout_size_mm(
        line_widths_mm,
        char_height_mm=char_height_mm,
        line_spacing_mm=line_spacing_mm,
    )

    bbox = _bbox_strokes(all_strokes)
    stats: dict[str, Any] = {
        "extract_algorithm": "makemeahanzi",
        "skeleton_source": "makemeahanzi",
        "stroke_font_source": "makemeahanzi",
        "used_field": "medians",
        "renderer": RENDERER_MODULE,
        "renderer_version": RENDERER_VERSION,
        "ttf_fallback_used": False,
        "glyph_count": glyph_count,
        "strokes": stroke_count,
        "chars": sum(len(line.replace(" ", "")) for line in lines),
        "line_count": len(lines),
        "multiline_enabled": len(lines) > 1,
        "layout_w_px": round(max(line_widths_px) if line_widths_px else 0, 1),
        "layout_h_px": round(bbox[3] - bbox[1] if bbox[3] > bbox[1] else step_px * max(len(lines), 1), 1),
        "char_height_px": round(char_height_px, 3),
        "char_spacing_px": round(spacing_px, 3),
        "char_height_mm_requested": char_height_mm,
        "char_spacing_mm_requested": char_spacing_mm,
        "line_spacing_mm_requested": line_spacing_mm,
        "required_layout_mm": [round(req_w_mm, 3), round(req_h_mm, 3)],
        "missing_chars": [],
    }
    return all_strokes, stats


def _bbox_strokes(strokes: list[Stroke]) -> list[float]:
    xs = [p.x for s in strokes for p in s.points_px]
    ys = [p.y for s in strokes for p in s.points_px]
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]


def render_hanzi_text_to_strokes(
    text: str,
    *,
    graphics_path: str | Path | None = None,
    char_height_mm: float = 60.0,
    char_spacing_mm: float = 2.0,
    line_spacing_mm: float = 0.0,
    px_per_mm: float = 10.0,
    user_lang: str = "zh",
) -> tuple[list[Stroke], dict[str, Any], dict[str, HanziGlyph]]:
    """加载 graphics + 渲染；缺字抛 ValueError。"""
    gpath = resolve_graphics_path(graphics_path)
    glyphs = load_hanzi_graphics(gpath)
    err = validate_hanzi_drawing_text(text, glyphs, lang=user_lang)
    if err:
        raise ValueError(err)
    missing = find_missing_hanzi_chars(text, glyphs)
    strokes, stats = render_hanzi_multiline_to_strokes(
        text,
        glyphs,
        char_height_mm=char_height_mm,
        char_spacing_mm=char_spacing_mm,
        line_spacing_mm=line_spacing_mm,
        px_per_mm=px_per_mm,
    )
    stats["graphics_path"] = str(gpath.resolve())
    stats["total_loaded_chars"] = len(glyphs)
    stats["unique_required_chars"] = len(collect_text_chars(text))
    stats["missing_chars"] = missing
    return strokes, stats, glyphs
