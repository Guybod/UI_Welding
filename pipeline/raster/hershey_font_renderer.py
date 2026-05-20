"""Hershey 单线 stroke 字体渲染 — glyph → strokes → points（非 TTF / 非 skeletonize）。

Gallery 与正式 skeleton pipeline 必须共用本模块的 ``render_hershey_text_to_strokes``。
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from core.types import PixelPoint, Stroke
from config.stroke_fonts.hershey_presets import resolve_hershey_jhf_name

RENDERER_MODULE = "pipeline.raster.hershey_font_renderer"
RENDERER_VERSION = "1.2.0"

_HERSHEY_IMPORT_ERROR_ZH = "缺少 Hershey-Fonts 依赖，请执行: pip install Hershey-Fonts"
_HERSHEY_IMPORT_ERROR_EN = "Missing Hershey-Fonts; install with: pip install Hershey-Fonts"


class HersheyFontsImportError(ImportError):
    pass


def _load_hershey_fonts():
    try:
        from HersheyFonts import HersheyFonts
    except ImportError as exc:
        raise HersheyFontsImportError(_HERSHEY_IMPORT_ERROR_ZH) from exc
    return HersheyFonts


def _glyph_strokes_local(hf, ch: str) -> list[list[tuple[float, float]]]:
    """单字 stroke 折线；Hershey Y 翻转为屏幕向下为正前的局部坐标。"""
    out: list[list[tuple[float, float]]] = []
    for st in hf.strokes_for_text(ch):
        pts = [(float(x), float(-y)) for x, y in st]
        if len(pts) >= 2:
            out.append(pts)
    return out


def _bbox_points(
    xs: list[float], ys: list[float],
) -> list[float]:
    if not xs:
        return [0.0, 0.0, 0.0, 0.0]
    return [min(xs), min(ys), max(xs), max(ys)]


def _bbox_strokes_local(strokes: list[list[tuple[float, float]]]) -> tuple[float, float, float, float]:
    xs = [x for st in strokes for x, _ in st]
    ys = [y for st in strokes for _, y in st]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_from_stroke_list(strokes: list[Stroke]) -> list[float]:
    xs = [p.x for s in strokes for p in s.points_px]
    ys = [p.y for s in strokes for p in s.points_px]
    return _bbox_points(xs, ys)


def endpoints_coincide_px(
    pts: list[PixelPoint] | list[tuple[float, float]],
    tol: float = 1.5,
) -> bool:
    """首尾点几乎重合才视为闭合（Hershey 唯一 closed 判定依据）。"""
    if len(pts) < 3:
        return False
    if isinstance(pts[0], PixelPoint):
        a, b = pts[0], pts[-1]
        return math.hypot(a.x - b.x, a.y - b.y) <= tol
    a, b = pts[0], pts[-1]
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= tol


def _stroke_closed(pts: list[tuple[float, float]], tol: float = 1.5) -> bool:
    return endpoints_coincide_px(pts, tol=tol)


def enforce_hershey_stroke_semantics(stroke: Stroke) -> bool:
    """将 Stroke.closed 与 metadata 对齐；返回是否发生强制修正。"""
    meta = stroke.metadata or {}
    glyph_closed = bool(meta.get("glyph_stroke_closed", meta.get("closed", stroke.closed)))
    if not glyph_closed and stroke.points_px:
        glyph_closed = endpoints_coincide_px(stroke.points_px)
    changed = stroke.closed != glyph_closed
    stroke.closed = glyph_closed
    meta["glyph_stroke_closed"] = glyph_closed
    meta["closed"] = glyph_closed
    stroke.metadata = meta
    return changed


def _resolve_char(
    hf,
    ch: str,
    *,
    mapped_upper: list[str],
    unsupported: list[str],
) -> tuple[str, list[list[tuple[float, float]]]]:
    if ch == " ":
        return ch, []
    strokes = _glyph_strokes_local(hf, ch)
    if strokes:
        return ch, strokes
    if ch.islower():
        up = ch.upper()
        strokes_up = _glyph_strokes_local(hf, up)
        if strokes_up:
            if ch not in mapped_upper:
                mapped_upper.append(ch)
            return up, strokes_up
    if ch not in unsupported:
        unsupported.append(ch)
    return ch, []


def render_hershey_text_to_strokes(
    text: str,
    *,
    style: str = "futural",
    char_height_mm: float,
    char_spacing_mm: float,
    px_per_mm: float = 10.0,
    line_spacing_mm: float = 0.0,
) -> tuple[list[Stroke], dict[str, Any]]:
    """唯一 Hershey 排版入口：文本 → 已归一化像素 Stroke 列表。

    坐标约定（与 raw preview / WorkPlane 一致）：
    - 排版后 min_x >= 0, min_y >= 0
    - Y 向下为正（pixel 空间）
    """
    del line_spacing_mm
    if char_height_mm <= 0 or px_per_mm <= 0:
        raise ValueError("char_height_mm and px_per_mm must be positive for Hershey layout")

    HersheyFonts = _load_hershey_fonts()
    jhf_name = resolve_hershey_jhf_name(style)
    hf = HersheyFonts()
    hf.load_default_font(jhf_name)

    char_height_px = char_height_mm * px_per_mm
    spacing_px = max(0.0, char_spacing_mm) * px_per_mm
    hf.normalize_rendering(char_height_px)
    scale_factor = char_height_px

    mapped_upper: list[str] = []
    unsupported: list[str] = []
    strokes_out: list[Stroke] = []
    x_cursor_px = 0.0

    char_bboxes_px: dict[str, list[float]] = {}
    char_offsets_px: dict[str, float] = {}
    char_advances_px: dict[str, float] = {}

    def _char_key(idx: int, c: str) -> str:
        return f"{idx}:{c}"
    ch_counts: dict[str, int] = {}
    glyph_count = 0

    for char_idx, ch in enumerate(text):
        ck = _char_key(char_idx, ch)
        char_offsets_px[ck] = x_cursor_px
        if ch == " ":
            adv = char_height_px * 0.35
            char_advances_px[ck] = adv
            char_bboxes_px[ck] = [x_cursor_px, 0.0, x_cursor_px + adv, char_height_px]
            x_cursor_px += adv
            continue

        _used, local = _resolve_char(
            hf, ch, mapped_upper=mapped_upper, unsupported=unsupported,
        )
        if not local:
            char_advances_px[ck] = 0.0
            char_bboxes_px[ck] = [x_cursor_px, 0.0, x_cursor_px, 0.0]
            continue

        glyph_count += 1
        xmin, ymin, xmax, ymax = _bbox_strokes_local(local)
        w_px = max(xmax - xmin, 1.0)
        char_bboxes_px[ck] = [x_cursor_px, ymin, x_cursor_px + w_px, ymax]
        adv_px = w_px + spacing_px
        char_advances_px[ck] = adv_px

        for stroke_idx, st in enumerate(local):
            pts_px = [
                PixelPoint(x=round(x + x_cursor_px - xmin, 3), y=round(y, 3))
                for x, y in st
            ]
            glyph_closed = _stroke_closed(st)
            strokes_out.append(
                Stroke(
                    id=uuid.uuid4().hex[:8],
                    source_type="hershey",
                    points_px=pts_px,
                    closed=glyph_closed,
                    metadata={
                        "extract_algorithm": "hershey",
                        "hershey_style": style,
                        "hershey_jhf_name": jhf_name,
                        "weld_char": ch,
                        "weld_char_index": char_idx,
                        "glyph_stroke_index": stroke_idx,
                        "glyph_stroke_closed": glyph_closed,
                        "closed": glyph_closed,
                    },
                )
            )
        ch_counts[ch] = ch_counts.get(ch, 0) + len(local)
        x_cursor_px += adv_px

    raw_bbox_px = _bbox_from_stroke_list(strokes_out)

    y_shift_px = 0.0
    y_flip_applied = False
    if strokes_out:
        ymin_pre = raw_bbox_px[1]
        if ymin_pre < 0:
            y_shift_px = -ymin_pre
            y_flip_applied = True
            for s in strokes_out:
                s.points_px = [
                    PixelPoint(x=p.x, y=round(p.y + y_shift_px, 3)) for p in s.points_px
                ]
            for ck, box in list(char_bboxes_px.items()):
                char_bboxes_px[ck] = [
                    box[0], box[1] + y_shift_px, box[2], box[3] + y_shift_px,
                ]

    layout_w_px = x_cursor_px
    normalized_bbox_px = _bbox_from_stroke_list(strokes_out)
    if normalized_bbox_px[2] <= normalized_bbox_px[0]:
        text_bbox_px = [0.0, 0.0, layout_w_px, char_height_px]
        layout_h_px = char_height_px
    else:
        text_bbox_px = normalized_bbox_px
        layout_h_px = text_bbox_px[3] - text_bbox_px[1]

    inv = 1.0 / px_per_mm

    def _mm_box(box: list[float]) -> list[float]:
        return [
            round(box[0] * inv, 3),
            round(box[1] * inv, 3),
            round(box[2] * inv, 3),
            round(box[3] * inv, 3),
        ]

    lowercase_policy = "native"
    if mapped_upper or unsupported:
        lowercase_policy = "native_or_map_to_uppercase"

    stats: dict[str, Any] = {
        "extract_algorithm": "hershey",
        "skeleton_source": "hershey",
        "renderer": RENDERER_MODULE,
        "renderer_version": RENDERER_VERSION,
        "ttf_fallback_used": False,
        "hershey_style": style,
        "hershey_jhf_name": jhf_name,
        "stroke_font_dataset": "Hershey-Fonts",
        "lowercase_policy": lowercase_policy,
        "lowercase_mapped_to_upper": mapped_upper,
        "unsupported_chars": unsupported,
        "glyph_count": glyph_count,
        "strokes": len(strokes_out),
        "chars": len(text),
        "per_char": ch_counts,
        "layout_w_px": round(layout_w_px, 1),
        "layout_h_px": round(layout_h_px, 1),
        "linebox_height_px": int(round(layout_h_px)),
        "baseline_px": int(round(layout_h_px)),
        "char_height_px": round(char_height_px, 3),
        "char_spacing_px": round(spacing_px, 3),
        "scale_factor": round(scale_factor, 3),
        "y_shift_px": round(y_shift_px, 3),
        "y_flip_applied": y_flip_applied,
        "raw_bbox_before_normalize_px": [round(v, 3) for v in raw_bbox_px],
        "normalized_bbox_px": [round(v, 3) for v in normalized_bbox_px],
        "text_bbox_px": [round(v, 3) for v in text_bbox_px],
        "text_bbox_mm": _mm_box(text_bbox_px),
        "char_height_mm_requested": char_height_mm,
        "char_spacing_mm_requested": char_spacing_mm,
        "char_bboxes_mm": {k: _mm_box(v) for k, v in char_bboxes_px.items()},
        "char_offsets_mm": {k: round(v * inv, 3) for k, v in char_offsets_px.items()},
        "char_advances_mm": {k: round(v * inv, 3) for k, v in char_advances_px.items()},
        "skeleton_single_line_only": True,
        "multiline_enabled": False,
        "line_count": 1,
    }
    open_n = sum(1 for s in strokes_out if not s.closed)
    closed_n = len(strokes_out) - open_n
    stats["hershey_open_stroke_count"] = open_n
    stats["hershey_closed_stroke_count"] = closed_n
    stats["glyph_stroke_closed_per_stroke"] = [
        {
            "stroke_id": s.id,
            "weld_char": s.metadata.get("weld_char"),
            "glyph_stroke_index": s.metadata.get("glyph_stroke_index"),
            "glyph_stroke_closed": s.metadata.get("glyph_stroke_closed"),
        }
        for s in strokes_out
    ]

    return strokes_out, stats


def render_hershey_text(
    text: str,
    *,
    char_height_mm: float,
    char_spacing_mm: float,
    line_spacing_mm: float = 0.0,
    style: str = "futural",
    px_per_mm: float = 10.0,
) -> tuple[list[Stroke], dict[str, Any]]:
    """兼容别名 — 与 ``render_hershey_text_to_strokes`` 相同。"""
    return render_hershey_text_to_strokes(
        text,
        style=style,
        char_height_mm=char_height_mm,
        char_spacing_mm=char_spacing_mm,
        px_per_mm=px_per_mm,
        line_spacing_mm=line_spacing_mm,
    )


def render_hershey_multiline_to_strokes(
    lines: list[str],
    *,
    style: str = "futural",
    char_height_mm: float,
    char_spacing_mm: float,
    line_spacing_mm: float = 0.0,
    px_per_mm: float = 10.0,
    line_gap_mm: float | None = None,
) -> tuple[list[Stroke], dict[str, Any]]:
    """多行 Hershey：每行调用 ``render_hershey_text_to_strokes``，行步进与 contour 一致。

    行步进 (px) = (字高 + 行间距) * px_per_mm；第 n 行 Y 偏移 = n * 行步进。
    """
    from pipeline.multiline_layout import estimate_layout_size_mm, line_step_mm

    if line_gap_mm is not None:
        line_spacing_mm = line_gap_mm
    step_px = line_step_mm(char_height_mm, line_spacing_mm) * px_per_mm

    all_strokes: list[Stroke] = []
    line_widths_px: list[float] = []
    line_stroke_counts: list[int] = []
    global_char_idx = 0
    last_stats: dict[str, Any] = {}

    for line_idx, line in enumerate(lines):
        y_off = line_idx * step_px
        if line:
            strokes, stats = render_hershey_text_to_strokes(
                line,
                style=style,
                char_height_mm=char_height_mm,
                char_spacing_mm=char_spacing_mm,
                px_per_mm=px_per_mm,
            )
            last_stats = stats
            line_w_px = float(stats.get("layout_w_px", 0))
        else:
            strokes = []
            line_w_px = 0.0

        for s in sorted(
            strokes,
            key=lambda st: int(st.metadata.get("weld_char_index", 0)),
        ):
            s.points_px = [
                PixelPoint(x=p.x, y=round(p.y + y_off, 3)) for p in s.points_px
            ]
            s.metadata = {
                **s.metadata,
                "layout_line_index": line_idx,
                "layout_line_text": line,
                "weld_char_index": global_char_idx,
            }
            global_char_idx += 1
            all_strokes.append(s)

        line_widths_px.append(line_w_px)
        line_stroke_counts.append(len(strokes))

    sheet_bbox = _bbox_from_stroke_list(all_strokes)
    inv = 1.0 / px_per_mm if px_per_mm > 0 else 1.0
    line_widths_mm = [w * inv for w in line_widths_px]
    req_w_mm, req_h_mm = estimate_layout_size_mm(
        line_widths_mm,
        char_height_mm=char_height_mm,
        line_spacing_mm=line_spacing_mm,
    )

    merged = dict(last_stats)
    merged.update({
        "extract_algorithm": "hershey",
        "skeleton_source": "hershey",
        "renderer": RENDERER_MODULE,
        "renderer_version": RENDERER_VERSION,
        "ttf_fallback_used": False,
        "hershey_style": style,
        "multiline_enabled": len(lines) > 1,
        "line_count": len(lines),
        "lines": list(lines),
        "line_spacing_mm_requested": line_spacing_mm,
        "line_step_mm": round(line_step_mm(char_height_mm, line_spacing_mm), 3),
        "line_widths_mm": [round(w, 3) for w in line_widths_mm],
        "line_stroke_counts": line_stroke_counts,
        "layout_w_px": round(max(line_widths_px) if line_widths_px else 0.0, 1),
        "layout_h_px": round(sheet_bbox[3] - sheet_bbox[1] if sheet_bbox else 0.0, 1),
        "required_width_mm": round(req_w_mm, 3),
        "required_height_mm": round(req_h_mm, 3),
        "strokes": len(all_strokes),
        "text_bbox_px": [round(v, 3) for v in sheet_bbox],
        "normalized_bbox_px": [round(v, 3) for v in sheet_bbox],
        "text_bbox_mm": [round(v * inv, 3) for v in sheet_bbox],
        "skeleton_single_line_only": False,
        "glyph_count": global_char_idx,
    })
    open_n = sum(1 for s in all_strokes if not s.closed)
    merged["hershey_open_stroke_count"] = open_n
    merged["hershey_closed_stroke_count"] = len(all_strokes) - open_n
    merged["glyph_stroke_closed_per_stroke"] = [
        {
            "stroke_id": s.id,
            "weld_char": s.metadata.get("weld_char"),
            "glyph_stroke_index": s.metadata.get("glyph_stroke_index"),
            "glyph_stroke_closed": s.metadata.get("glyph_stroke_closed"),
            "layout_line_index": s.metadata.get("layout_line_index"),
        }
        for s in all_strokes
    ]
    return all_strokes, merged


def count_hershey_strokes(
    text: str,
    *,
    style: str = "futural",
    char_height_mm: float = 60.0,
    char_spacing_mm: float = 2.0,
    px_per_mm: float = 10.0,
) -> int:
    strokes, _ = render_hershey_text_to_strokes(
        text,
        style=style,
        char_height_mm=char_height_mm,
        char_spacing_mm=char_spacing_mm,
        px_per_mm=px_per_mm,
    )
    return len(strokes)


def analyze_hershey_digit_4(
    *,
    style: str = "futural",
    char_height_mm: float = 60.0,
    char_spacing_mm: float = 2.0,
    px_per_mm: float = 10.0,
) -> tuple[int, bool, bool]:
    """返回 (stroke_count, is_open, has_triangle) — 基于正式 renderer。"""
    strokes, _ = render_hershey_text_to_strokes(
        "4",
        style=style,
        char_height_mm=char_height_mm,
        char_spacing_mm=char_spacing_mm,
        px_per_mm=px_per_mm,
    )
    polys = strokes_to_polylines(strokes)
    n = len(polys)
    if n == 0:
        return 0, False, False

    has_tri = False
    for st in polys:
        if len(st) == 3:
            peri = sum(
                math.hypot(st[i][0] - st[(i + 1) % 3][0], st[i][1] - st[(i + 1) % 3][1])
                for i in range(3)
            )
            area2 = abs(
                st[0][0] * st[1][1] - st[1][0] * st[0][1]
                + st[1][0] * st[2][1] - st[2][0] * st[1][1]
                + st[2][0] * st[0][1] - st[0][0] * st[2][1]
            )
            if peri > 0 and 4 * math.pi * (area2 * 0.5) / (peri * peri) < 0.72:
                if math.hypot(st[0][0] - st[-1][0], st[0][1] - st[-1][1]) < 2.0:
                    has_tri = True

    closed_loops = sum(
        1
        for st in polys
        if len(st) >= 3 and math.hypot(st[0][0] - st[-1][0], st[0][1] - st[-1][1]) < 1.5
    )
    is_open = n >= 2 and closed_loops == 0 and not has_tri
    if n == 2 and not has_tri:
        is_open = True
    return n, is_open, has_tri


def strokes_to_polylines(strokes: list[Stroke]) -> list[list[tuple[float, float]]]:
    """Gallery / 调试绘图用：Stroke → 折线点列。"""
    return [[(p.x, p.y) for p in s.points_px] for s in strokes if len(s.points_px) >= 2]
