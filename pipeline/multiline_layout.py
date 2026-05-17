"""Contour 多行排版 — 按行渲染、自上而下、行内从左到右。"""

from __future__ import annotations

import uuid
from typing import Any

from core.types import PixelPoint, Stroke


def split_text_lines(text: str) -> list[str]:
    """按换行拆行，保留空行；统一 \\r\\n / \\r / \\n。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.split("\n")


def line_step_mm(char_height_mm: float, line_spacing_mm: float) -> float:
    """行步进 (mm) = 字高 + 行距（行间额外间距）。"""
    return max(0.0, char_height_mm) + max(0.0, line_spacing_mm)


def estimate_layout_size_mm(
    line_widths_mm: list[float],
    *,
    char_height_mm: float,
    line_spacing_mm: float,
) -> tuple[float, float]:
    """理论包络：宽=max(行宽)，高=行数×字高+(行数-1)×行距。"""
    n = len(line_widths_mm)
    if n == 0:
        return 0.0, 0.0
    w = max(line_widths_mm) if line_widths_mm else 0.0
    step = line_step_mm(char_height_mm, line_spacing_mm)
    h = n * max(0.0, char_height_mm) + max(0, n - 1) * max(0.0, line_spacing_mm)
    return w, h


def layout_contour_multiline(
    lines: list[str],
    *,
    rasterizer,
    path_config,
    char_spacing_mm: float,
    char_height_mm: float,
    line_spacing_mm: float,
    px_per_mm: float,
    contour_extractor_cls,
) -> tuple[list[Stroke], dict[str, Any]]:
    """多行 contour：每行独立 linebox 渲染，Y = line_index × line_step_px。"""
    spacing_px = char_spacing_mm * px_per_mm
    step_px = line_step_mm(char_height_mm, line_spacing_mm) * px_per_mm

    strokes_raw: list[Stroke] = []
    ch_counts: dict[str, int] = {}
    char_baseline_info: dict[str, dict] = {}
    line_widths_px: list[float] = []
    line_stroke_counts: list[int] = []

    linebox_h = 0
    baseline_px = 0
    ascent = 0
    descent = 0

    for line_idx, line in enumerate(lines):
        y_off = line_idx * step_px
        line_w_px = 0.0
        line_strokes_before = len(strokes_raw)

        if line:
            glyphs = rasterizer.render_text_linebox(line)
            if glyphs and linebox_h == 0:
                linebox_h = glyphs[0].linebox_height
                baseline_px = glyphs[0].baseline_y
                ascent = glyphs[0].ascent
                descent = glyphs[0].descent

            x_cursor_px = 0.0
            for ch, glyph in zip(line, glyphs):
                binary = glyph.image
                ext = contour_extractor_cls()
                strokes = ext.extract(binary, config=path_config)
                if x_cursor_px > 0 or y_off > 0:
                    for s in strokes:
                        s.points_px = [
                            PixelPoint(x=p.x + x_cursor_px, y=p.y + y_off)
                            for p in s.points_px
                        ]
                elif y_off > 0:
                    for s in strokes:
                        s.points_px = [
                            PixelPoint(x=p.x, y=p.y + y_off) for p in s.points_px
                        ]

                char_w_px = float(binary.shape[1]) if binary.size else float(glyph.width_px)
                for s in strokes:
                    s.metadata = {
                        **s.metadata,
                        "layout_line_index": line_idx,
                        "layout_line_text": line,
                    }
                    if not s.id:
                        s.id = str(uuid.uuid4())
                strokes_raw.extend(strokes)
                ch_counts[ch] = ch_counts.get(ch, 0) + len(strokes)
                char_baseline_info[f"L{line_idx}:{ch}"] = {
                    "linebox_height": glyph.linebox_height,
                    "baseline_y_px": glyph.baseline_y,
                    "ascent_px": glyph.ascent,
                    "descent_px": glyph.descent,
                    "glyph_bbox": list(glyph.glyph_bbox),
                }
                x_cursor_px += char_w_px + spacing_px
            line_w_px = max(0.0, x_cursor_px - spacing_px) if x_cursor_px > 0 else 0.0
        else:
            if linebox_h == 0:
                ref = rasterizer.render_text_linebox("A")
                if ref:
                    linebox_h = ref[0].linebox_height
                    baseline_px = ref[0].baseline_y
                    ascent = ref[0].ascent
                    descent = ref[0].descent

        line_widths_px.append(line_w_px)
        line_stroke_counts.append(len(strokes_raw) - line_strokes_before)

    layout_w_px = max(line_widths_px) if line_widths_px else 0.0
    if strokes_raw:
        all_y = [p.y for s in strokes_raw for p in s.points_px]
        layout_h_px = (max(all_y) - min(all_y)) if all_y else 0.0
    else:
        layout_h_px = max(
            0.0,
            len(lines) * step_px - (line_spacing_mm * px_per_mm if len(lines) > 1 else 0),
        )

    line_widths_mm = [w / px_per_mm for w in line_widths_px] if px_per_mm > 0 else []
    req_w_mm, req_h_mm = estimate_layout_size_mm(
        line_widths_mm,
        char_height_mm=char_height_mm,
        line_spacing_mm=line_spacing_mm,
    )

    stats: dict[str, Any] = {
        "multiline_enabled": len(lines) > 1,
        "line_count": len(lines),
        "lines": lines,
        "line_spacing_mm_requested": line_spacing_mm,
        "line_step_mm": round(line_step_mm(char_height_mm, line_spacing_mm), 3),
        "line_widths_mm": [round(w, 3) for w in line_widths_mm],
        "line_stroke_counts": line_stroke_counts,
        "layout_w_px": round(layout_w_px, 1),
        "layout_h_px": round(layout_h_px, 1),
        "required_width_mm": round(req_w_mm, 3),
        "required_height_mm": round(req_h_mm, 3),
        "linebox_height_px": linebox_h,
        "baseline_px": baseline_px,
        "ascent_px": ascent,
        "descent_px": descent,
        "per_char": ch_counts,
        "char_baseline": char_baseline_info,
    }
    return strokes_raw, stats


def layout_legacy_single_string(
    text: str,
    *,
    rasterizer,
    path_config,
    char_spacing_mm: float,
    px_per_mm: float,
    mode: str,
    contour_extractor_cls,
    skeleton_extractor_mod,
) -> tuple[list[Stroke], dict[str, Any]]:
    """旧版整串排版（skeleton 或多行 skeleton Beta 仍走此路径）。"""
    from pipeline.vision import SkeletonExtractor

    glyphs = rasterizer.render_text_linebox(text)
    linebox_h = glyphs[0].linebox_height if glyphs else 0
    baseline_px = glyphs[0].baseline_y if glyphs else 0
    ascent = glyphs[0].ascent if glyphs else 0
    descent = glyphs[0].descent if glyphs else 0
    char_baseline_info: dict[str, dict] = {}
    strokes_raw: list[Stroke] = []
    ch_counts: dict[str, int] = {}
    x_cursor_px = 0.0
    total_glyph_w_px = 0.0

    for ch, glyph in zip(text, glyphs):
        binary = glyph.image
        if mode == "contour":
            strokes = contour_extractor_cls().extract(binary, config=path_config)
        else:
            strokes, _ = SkeletonExtractor.extract(
                binary, config=path_config, backend="auto")
        if x_cursor_px > 0:
            for s in strokes:
                s.points_px = [PixelPoint(x=p.x + x_cursor_px, y=p.y) for p in s.points_px]
        char_w_px = binary.shape[1] if binary.size else max(glyph.width_px, 1)
        spacing_px = char_spacing_mm * px_per_mm
        total_glyph_w_px += char_w_px
        x_cursor_px += char_w_px + spacing_px
        strokes_raw.extend(strokes)
        ch_counts[ch] = len(strokes)
        char_baseline_info[ch] = {
            "linebox_height": glyph.linebox_height,
            "baseline_y_px": glyph.baseline_y,
            "ascent_px": glyph.ascent,
            "descent_px": glyph.descent,
            "glyph_bbox": list(glyph.glyph_bbox),
        }

    lines = split_text_lines(text)
    line_widths_mm = [x_cursor_px / px_per_mm] if px_per_mm > 0 else [0.0]
    req_w, req_h = estimate_layout_size_mm(
        line_widths_mm,
        char_height_mm=0,
        line_spacing_mm=0,
    )
    if px_per_mm > 0 and strokes_raw:
        all_x = [p.x for s in strokes_raw for p in s.points_px]
        all_y = [p.y for s in strokes_raw for p in s.points_px]
        req_w = (max(all_x) - min(all_x)) / px_per_mm
        req_h = (max(all_y) - min(all_y)) / px_per_mm

    return strokes_raw, {
        "multiline_enabled": len(lines) > 1,
        "line_count": len(lines),
        "lines": lines,
        "chars": len(text),
        "strokes": len(strokes_raw),
        "per_char": ch_counts,
        "linebox_height_px": linebox_h,
        "baseline_px": baseline_px,
        "ascent_px": ascent,
        "descent_px": descent,
        "layout_w_px": round(x_cursor_px, 1),
        "char_baseline": char_baseline_info,
        "line_spacing_mm_requested": 0.0,
        "line_step_mm": 0.0,
        "line_widths_mm": line_widths_mm,
        "required_width_mm": round(req_w, 3),
        "required_height_mm": round(req_h, 3),
        "legacy_string_layout": True,
    }
