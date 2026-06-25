"""汉字 medians 骨架预览渲染 — PIL，无 TTF。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from pipeline.hanzi.hanzi_data_loader import HanziGlyph, Point


PreviewMode = Literal["plain", "grid", "order_debug"]


@dataclass
class HanziPreviewConfig:
    cell_size_px: int = 120
    char_scale: float = 0.85
    char_spacing_px: int = 20
    line_spacing_px: int = 50
    margin_px: int = 80
    punct_gap_px: int = 10
    line_width: float = 1.2
    bg_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    grid_color: str = "#DDDDDD"
    missing_color: str = "#CC0000"
    start_dot_radius: int = 3
    show_stroke_numbers: bool = False


@dataclass
class LineLayout:
    """一行排版：字符或标点间隙。"""
    items: list[tuple[str, str | None]]  # ("char", "东") | ("gap", None)


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


def _normalize_strokes(
    glyph: HanziGlyph,
    target_size: float,
) -> list[list[tuple[float, float]]]:
    """归一化到 target_size 方框，保持纵横比，输出 PIL 坐标（Y 向下）。

    MakeMeAHanzi：Y 向上，需翻转。chinese-hershey JSON：已为左上原点 Y 向下。
    """
    min_x, min_y, max_x, max_y = _glyph_bbox(glyph)
    w = max(max_x - min_x, 1e-6)
    h = max(max_y - min_y, 1e-6)
    scale = target_size / max(w, h)
    pad_x = (target_size - w * scale) * 0.5
    pad_y = (target_size - h * scale) * 0.5
    out: list[list[tuple[float, float]]] = []
    for stroke in glyph.medians:
        row: list[tuple[float, float]] = []
        for p in stroke:
            x = (p.x - min_x) * scale + pad_x
            if glyph.y_axis_up:
                y = (max_y - p.y) * scale + pad_y
            else:
                y = (p.y - min_y) * scale + pad_y
            row.append((x, y))
        out.append(row)
    return out


def build_lines_from_text(
    lines_raw: list[str],
    *,
    skip_punctuation: set[str],
    punct_gap: bool = True,
) -> tuple[list[LineLayout], int]:
    layouts: list[LineLayout] = []
    skipped = 0
    for raw in lines_raw:
        items: list[tuple[str, str | None]] = []
        for ch in raw:
            if ch.isspace():
                continue
            if ch in skip_punctuation:
                skipped += 1
                if punct_gap:
                    items.append(("gap", None))
                continue
            items.append(("char", ch))
        layouts.append(LineLayout(items=items))
    return layouts, skipped


def _line_pixel_width(layout: LineLayout, cfg: HanziPreviewConfig) -> int:
    w = 0
    for kind, _ in layout.items:
        if kind == "char":
            w += cfg.cell_size_px
        else:
            w += cfg.punct_gap_px
        if layout.items:
            w += cfg.char_spacing_px
    if layout.items:
        w -= cfg.char_spacing_px
    return max(w, 0)


def _canvas_size(layouts: list[LineLayout], cfg: HanziPreviewConfig) -> tuple[int, int]:
    max_w = max((_line_pixel_width(ln, cfg) for ln in layouts), default=0)
    rows = len(layouts)
    height = (
        cfg.margin_px * 2
        + rows * cfg.cell_size_px
        + max(0, rows - 1) * cfg.line_spacing_px
    )
    width = cfg.margin_px * 2 + max_w
    return width, height


def render_hanzi_preview(
    layouts: list[LineLayout],
    glyphs: dict[str, HanziGlyph],
    output_path: str | Path,
    *,
    mode: PreviewMode = "plain",
    cfg: HanziPreviewConfig | None = None,
    missing_chars: set[str] | None = None,
) -> Path:
    cfg = cfg or HanziPreviewConfig()
    missing_chars = missing_chars or set()
    target_char = cfg.cell_size_px * cfg.char_scale

    w, h = _canvas_size(layouts, cfg)
    img = Image.new("RGB", (max(w, 1), max(h, 1)), cfg.bg_color)
    draw = ImageDraw.Draw(img)

    try:
        num_font = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        num_font = ImageFont.load_default()

    for row_i, layout in enumerate(layouts):
        x_cursor = cfg.margin_px
        y0 = cfg.margin_px + row_i * (cfg.cell_size_px + cfg.line_spacing_px)

        for kind, ch in layout.items:
            if kind == "gap":
                x_cursor += cfg.punct_gap_px + cfg.char_spacing_px
                continue

            assert ch is not None
            cell_x = x_cursor
            cell_y = y0

            if mode in ("grid", "order_debug"):
                draw.rectangle(
                    [cell_x, cell_y, cell_x + cfg.cell_size_px, cell_y + cfg.cell_size_px],
                    outline=cfg.grid_color,
                    width=1,
                )

            glyph = glyphs.get(ch)
            if glyph is None or ch in missing_chars:
                draw.line(
                    [
                        cell_x + 8, cell_y + 8,
                        cell_x + cfg.cell_size_px - 8, cell_y + cfg.cell_size_px - 8,
                    ],
                    fill=cfg.missing_color,
                    width=1,
                )
                draw.line(
                    [
                        cell_x + cfg.cell_size_px - 8, cell_y + 8,
                        cell_x + 8, cell_y + cfg.cell_size_px - 8,
                    ],
                    fill=cfg.missing_color,
                    width=1,
                )
                x_cursor += cfg.cell_size_px + cfg.char_spacing_px
                continue

            strokes = _normalize_strokes(glyph, target_char)
            offset_x = cell_x + (cfg.cell_size_px - target_char) * 0.5
            offset_y = cell_y + (cfg.cell_size_px - target_char) * 0.5

            for si, stroke in enumerate(strokes):
                pts = [(offset_x + x, offset_y + y) for x, y in stroke]
                if len(pts) >= 2:
                    draw.line(pts, fill=cfg.stroke_color, width=int(max(1, cfg.line_width)))

                if mode == "order_debug" and pts:
                    sx, sy = pts[0]
                    r = cfg.start_dot_radius
                    draw.ellipse(
                        [sx - r, sy - r, sx + r, sy + r],
                        fill="#E74C3C",
                        outline=cfg.stroke_color,
                    )
                    if cfg.show_stroke_numbers:
                        draw.text((sx + 4, sy - 4), str(si + 1), fill="#E74C3C", font=num_font)

            x_cursor += cfg.cell_size_px + cfg.char_spacing_px

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG")
    return out
