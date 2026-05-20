"""并排对比图 — 上/下或左/右拼接两张等排版预览。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def stack_compare_vertical(
    top_path: str | Path,
    bottom_path: str | Path,
    output_path: str | Path,
    *,
    top_label: str = "MakeMeAHanzi medians",
    bottom_label: str = "Heiti single-line (Source Han Sans derived)",
    gap_px: int = 24,
    label_height: int = 36,
    bg_color: str = "#FFFFFF",
) -> Path:
    top = Image.open(top_path).convert("RGB")
    bottom = Image.open(bottom_path).convert("RGB")
    w = max(top.width, bottom.width)
    h = top.height + bottom.height + gap_px + label_height * 2
    out = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()

    y = 0
    draw.text((8, y + 8), top_label, fill="#333333", font=font)
    y += label_height
    out.paste(top, ((w - top.width) // 2, y))
    y += top.height + gap_px

    draw.text((8, y + 8), bottom_label, fill="#333333", font=font)
    y += label_height
    out.paste(bottom, ((w - bottom.width) // 2, y))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, format="PNG")
    return path
