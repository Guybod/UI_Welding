"""PIL 高分辨率字体渲染 → 二值 numpy array"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _find_font_file():
    import os
    import sys
    candidates = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        candidates = [
            os.path.join(windir, "Fonts", "arial.ttf"),
            os.path.join(windir, "Fonts", "msyh.ttf"),
            os.path.join(windir, "Fonts", "simhei.ttf"),
        ]
    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ])
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def get_default_font_path() -> str:
    p = _find_font_file()
    if p is None:
        raise FileNotFoundError("No system font found. Specify font_path explicitly.")
    return p


def render_char(char: str, font_path: str, font_size_px: int = 600) -> np.ndarray:
    """渲染单个字符为高分辨率二值图。

    Returns:
        numpy array (dtype=uint8): 0=背景, 255=字形
    """
    if not char or char.isspace():
        return np.zeros((font_size_px, font_size_px), dtype=np.uint8)

    font = ImageFont.truetype(font_path, font_size_px)

    # 测量字符 bounding box
    bbox = font.getbbox(char)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    if w <= 0 or h <= 0:
        return np.zeros((font_size_px, font_size_px // 2), dtype=np.uint8)

    padding = font_size_px // 8
    img_w = w + 2 * padding
    img_h = h + 2 * padding

    img = Image.new("L", (img_w, img_h), 0)
    draw = ImageDraw.Draw(img)
    draw.text((padding - bbox[0], padding - bbox[1]), char, fill=255, font=font)

    arr = np.array(img)
    arr[arr > 127] = 255
    arr[arr <= 127] = 0
    return arr


def render_text(text: str, font_path: str, font_size_px: int = 600) -> list[np.ndarray]:
    """渲染一段文字，返回每个字符的二值图列表。"""
    return [render_char(c, font_path, font_size_px) for c in text]
