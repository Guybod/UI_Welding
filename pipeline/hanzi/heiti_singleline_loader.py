"""LingDong chinese-hershey-font STRK-Heiti.json 加载（思源黑体衍生单线，非 TTF 渲染）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pipeline.hanzi.hanzi_data_loader import HanziGlyph, Point


@dataclass
class HeitiLoadStats:
    path: str = ""
    total_loaded_chars: int = 0
    broken_stroke_entries: int = 0


def _unicode_key_to_char(key: str) -> str | None:
    key = key.strip()
    if key.startswith("U+"):
        try:
            return chr(int(key[2:], 16))
        except ValueError:
            return None
    if len(key) == 1:
        return key
    return None


def _parse_stroke_polylines(raw: object, *, scale: float = 1000.0) -> list[list[Point]]:
    """JSON 折线：坐标 0~1，原点左上。"""
    if not isinstance(raw, list):
        return []
    strokes: list[list[Point]] = []
    for poly in raw:
        if not isinstance(poly, list):
            continue
        pts: list[Point] = []
        for pt in poly:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                pts.append(Point(float(pt[0]) * scale, float(pt[1]) * scale))
        if len(pts) >= 2:
            strokes.append(pts)
        elif len(pts) == 1:
            strokes.append([pts[0], pts[0]])
    return strokes


def load_heiti_stroke_json(path: str | Path) -> tuple[dict[str, HanziGlyph], HeitiLoadStats]:
    """加载 STRK-Heiti.json（或兼容的 chinese-hershey stroke 文件）。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"未找到黑体单线 JSON: {p.resolve()}\n"
            "请从 https://github.com/LingDong-/chinese-hershey-font 下载 "
            "dist/json/STRK-Heiti.json 并放到 third_party/chinese-hershey-font/\n"
            "或使用 --heiti-json 指定路径"
        )

    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"黑体单线 JSON 根节点应为 object: {p}")

    glyphs: dict[str, HanziGlyph] = {}
    broken = 0
    for key, polylines in data.items():
        ch = _unicode_key_to_char(key)
        if not ch:
            continue
        medians = _parse_stroke_polylines(polylines)
        if not medians:
            broken += 1
            continue
        glyphs[ch] = HanziGlyph(
            char=ch,
            medians=medians,
            stroke_count=len(medians),
            y_axis_up=False,
        )

    if not glyphs:
        raise ValueError(f"未从 {p} 解析到任何有效字形")

    stats = HeitiLoadStats(
        path=str(p.resolve()),
        total_loaded_chars=len(glyphs),
        broken_stroke_entries=broken,
    )
    return glyphs, stats


def analyze_glyph_quality(glyphs: dict[str, HanziGlyph], chars: list[str]) -> dict:
    """缺字、断线、单点笔、笔画数统计。"""
    missing: list[str] = []
    single_point_strokes = 0
    short_strokes = 0
    stroke_counts: list[int] = []

    for ch in chars:
        g = glyphs.get(ch)
        if g is None:
            missing.append(ch)
            continue
        stroke_counts.append(g.stroke_count)
        for st in g.medians:
            if len(st) < 2:
                short_strokes += 1
            if len(st) == 2 and st[0].x == st[1].x and st[0].y == st[1].y:
                single_point_strokes += 1

    return {
        "missing_chars": missing,
        "missing_count": len(missing),
        "single_point_strokes": single_point_strokes,
        "short_strokes": short_strokes,
        "stroke_count_min": min(stroke_counts) if stroke_counts else 0,
        "stroke_count_max": max(stroke_counts) if stroke_counts else 0,
        "stroke_count_avg": (
            sum(stroke_counts) / len(stroke_counts) if stroke_counts else 0.0
        ),
    }
