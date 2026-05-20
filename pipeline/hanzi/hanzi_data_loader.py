"""MakeMeAHanzi graphics.txt 加载 — 仅 medians，无 TTF fallback。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass
class HanziGlyph:
    char: str
    medians: list[list[Point]]
    stroke_count: int
    # True: MakeMeAHanzi（Y 向上）；False: chinese-hershey JSON（Y 向下，左上原点）
    y_axis_up: bool = True


@dataclass
class LoadStats:
    total_loaded_chars: int = 0
    path: str = ""


def _parse_medians(raw_medians: object) -> list[list[Point]]:
    if not isinstance(raw_medians, list):
        return []
    strokes: list[list[Point]] = []
    for stroke in raw_medians:
        if not isinstance(stroke, list):
            continue
        pts: list[Point] = []
        for pt in stroke:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                pts.append(Point(float(pt[0]), float(pt[1])))
        if len(pts) >= 2:
            strokes.append(pts)
        elif len(pts) == 1:
            strokes.append(pts + [pts[0]])
    return strokes


def load_hanzi_graphics(path: str | Path) -> dict[str, HanziGlyph]:
    """加载 MakeMeAHanzi graphics.txt（JSONL，每行一字）。"""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            f"未找到 MakeMeAHanzi 数据文件: {p.resolve()}\n"
            "请下载 graphics.txt 并指定 --graphics，参见 third_party/makemeahanzi/README.md"
        )

    glyphs: dict[str, HanziGlyph] = {}
    with p.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"graphics.txt 第 {line_no} 行 JSON 无效: {exc}") from exc

            ch = obj.get("character")
            if not ch or not isinstance(ch, str):
                continue
            medians = _parse_medians(obj.get("medians"))
            if not medians:
                continue
            glyphs[ch] = HanziGlyph(
                char=ch,
                medians=medians,
                stroke_count=len(medians),
            )

    if not glyphs:
        raise ValueError(f"graphics.txt 未解析到任何含 medians 的汉字: {p.resolve()}")

    return glyphs


def collect_required_chars(text: str, *, skip_punctuation: Iterable[str]) -> tuple[list[str], list[str], int]:
    """返回 (保留字符序列表, 唯一汉字列表, 跳过标点数)。"""
    skip = set(skip_punctuation)
    kept: list[str] = []
    unique: set[str] = set()
    skipped = 0
    for ch in text:
        if ch in skip or ch.isspace():
            if ch in skip:
                skipped += 1
            continue
        kept.append(ch)
        unique.add(ch)
    return kept, sorted(unique), skipped


def analyze_coverage(
    glyphs: dict[str, HanziGlyph],
    required_unique: list[str],
) -> tuple[list[str], list[str]]:
    """返回 (命中列表, 缺失列表)。"""
    hit = [c for c in required_unique if c in glyphs]
    missing = [c for c in required_unique if c not in glyphs]
    return hit, missing
