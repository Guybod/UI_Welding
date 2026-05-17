"""PIL 高分辨率字体渲染 → 二值 numpy array

无 Qt/PySide6 依赖。只做渲染，不做排版、不做路径提取。
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 字形 linebox 内边距：固定 0（不提供 UI）；字间距/行间距/示教边距由排版参数控制。
LINE_BOX_PADDING_PX = 0


def _trim_binary_top(binary: np.ndarray) -> tuple[np.ndarray, int]:
    """裁掉二值图顶部全空行，使墨迹顶边落在 y=0。"""
    if binary.size == 0:
        return binary, 0
    rows = np.any(binary > 0, axis=1)
    if not np.any(rows):
        return binary, 0
    top = int(np.argmax(rows))
    if top == 0:
        return binary, 0
    return binary[top:, :].copy(), top


def _ink_bbox_xyxy(binary: np.ndarray) -> tuple[int, int, int, int]:
    """墨迹 tight bbox (x0, y0, x1, y1)；无墨迹则 (0,0,0,0)。"""
    if binary.size == 0:
        return (0, 0, 0, 0)
    ys = np.any(binary > 0, axis=1)
    xs = np.any(binary > 0, axis=0)
    if not np.any(ys) or not np.any(xs):
        return (0, 0, 0, 0)
    y0, y1 = int(np.argmax(ys)), int(len(ys) - np.argmax(ys[::-1]))
    x0, x1 = int(np.argmax(xs)), int(len(xs) - np.argmax(xs[::-1]))
    return (x0, y0, x1, y1)


@dataclass
class LineboxGlyph:
    """统一 linebox 渲染结果 — 所有字符共享相同的 baseline_y 和 linebox_height。

    Attributes:
        image: 二值 numpy array (dtype=uint8, 0=背景, 255=字形)
        linebox_height: 统一行盒高度 px (= ascent + descent + 2*LINE_BOX_PADDING_PX)
        baseline_y: baseline 在 image 中的 y 坐标 px
        ascent: 字体 ascent px (baseline → ascender)
        descent: 字体 descent px (baseline → descender)
        glyph_bbox: 字形在 image 中的 tight bbox (x0, y0, x1, y1)
        char_w_px: 图像宽度 px（含 padding）
    """
    image: np.ndarray
    linebox_height: int
    baseline_y: int
    ascent: int
    descent: int
    glyph_bbox: tuple
    char_w_px: int


# ---- 字体路径查找 ----


def _find_font_file() -> str | None:
    """跨平台字体路径查找"""
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
    """返回系统默认字体路径。未找到时抛出 FileNotFoundError。"""
    p = _find_font_file()
    if p is None:
        raise FileNotFoundError("No system font found. Specify font_path explicitly.")
    return p


# ---- FontRasterizer 类 ----


class FontRasterizer:
    """PIL 高分辨率字体渲染器。

    用法:
        rasterizer = FontRasterizer()
        binary = rasterizer.render_char("A")
        images = rasterizer.render_text("Abc")
    """

    def __init__(self, default_font_path: str | None = None, default_font_size_px: int = 600):
        self._default_font_path = default_font_path
        self.default_font_size_px = default_font_size_px

    # ---- 公开 API ----

    def get_font_path(self) -> str:
        """返回 font_path（优先用户指定，否则系统默认）"""
        if self._default_font_path:
            return self._default_font_path
        return get_default_font_path()

    def render_char(
        self, char: str,
        font_path: str | None = None,
        font_size_px: int | None = None,
    ) -> np.ndarray:
        """渲染单个字符为高分辨率二值图。

        Args:
            char: 单个字符
            font_path: 字体路径，None 则用默认字体
            font_size_px: 渲染字号，None 则用 default_font_size_px

        Returns:
            numpy array (dtype=uint8): 0=背景, 255=字形前景
        """
        fp = font_path or self.get_font_path()
        size = font_size_px or self.default_font_size_px

        if not char or char.isspace():
            return np.zeros((size, size), dtype=np.uint8)

        font = ImageFont.truetype(fp, size)
        bbox = font.getbbox(char)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        if w <= 0 or h <= 0:
            return np.zeros((size, size // 2), dtype=np.uint8)

        padding = LINE_BOX_PADDING_PX
        img_w = w + 2 * padding
        img_h = h + 2 * padding

        img = Image.new("L", (img_w, img_h), 0)
        draw = ImageDraw.Draw(img)
        draw.text((padding - bbox[0], padding - bbox[1]), char, fill=255, font=font)

        return self.binarize(np.array(img))

    def render_char_in_linebox(
        self, char: str,
        font_path: str | None = None,
        font_size_px: int | None = None,
    ) -> LineboxGlyph:
        """渲染单字：墨迹顶边对齐 y=0（tight bbox 绘制 + 裁顶空行）。"""
        fp = font_path or self.get_font_path()
        size = font_size_px or self.default_font_size_px

        font = ImageFont.truetype(fp, size)
        ascent, descent = font.getmetrics()
        padding = LINE_BOX_PADDING_PX

        if not char or char.isspace():
            w = max(size // 4, 1)
            h = max(ascent + descent, 1)
            return LineboxGlyph(
                image=np.zeros((h, w), dtype=np.uint8),
                linebox_height=h,
                baseline_y=padding + ascent,
                ascent=ascent,
                descent=descent,
                glyph_bbox=(0, 0, 0, 0),
                char_w_px=w,
            )

        bbox = font.getbbox(char)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        if w <= 0 or h <= 0:
            blank_w = max(size // 2, 1)
            blank_h = max(ascent + descent, 1)
            return LineboxGlyph(
                image=np.zeros((blank_h, blank_w), dtype=np.uint8),
                linebox_height=blank_h,
                baseline_y=padding + ascent,
                ascent=ascent,
                descent=descent,
                glyph_bbox=(0, 0, 0, 0),
                char_w_px=blank_w,
            )

        img_w = w + 2 * padding
        img_h = h + 2 * padding
        draw_x = padding - bbox[0]
        draw_y = padding - bbox[1]

        img = Image.new("L", (img_w, img_h), 0)
        draw = ImageDraw.Draw(img)
        draw.text((draw_x, draw_y), char, fill=255, font=font)

        binary = self.binarize(np.array(img))
        binary, top_trim = _trim_binary_top(binary)
        baseline_y = max(0, (draw_y + ascent) - top_trim)
        linebox_h = int(binary.shape[0]) if binary.size else 0
        glyph_bbox = _ink_bbox_xyxy(binary)
        img_w_out = int(binary.shape[1]) if binary.size else img_w

        return LineboxGlyph(
            image=binary,
            linebox_height=linebox_h,
            baseline_y=baseline_y,
            ascent=ascent,
            descent=descent,
            glyph_bbox=glyph_bbox,
            char_w_px=img_w_out,
        )

    def render_text_linebox(
        self, text: str,
        font_path: str | None = None,
        font_size_px: int | None = None,
    ) -> list[LineboxGlyph]:
        """渲染一段文字为 LineboxGlyph 列表。

        所有 glyph 共享相同的 linebox_height 和 baseline_y。

        Args:
            text: 文字字符串
            font_path: 字体路径
            font_size_px: 渲染字号

        Returns:
            list[LineboxGlyph]
        """
        return [self.render_char_in_linebox(c, font_path, font_size_px) for c in text]

    def render_text(
        self, text: str,
        font_path: str | None = None,
        font_size_px: int | None = None,
    ) -> list[np.ndarray]:
        """渲染一段文字，返回每个字符的二值图列表。

        Args:
            text: 文字字符串
            font_path: 字体路径
            font_size_px: 渲染字号

        Returns:
            list[np.ndarray]: 每个字符的二值图 (dtype=uint8, 0/255)
        """
        return [self.render_char(c, font_path, font_size_px) for c in text]

    @staticmethod
    def binarize(image: np.ndarray, threshold: int = 127) -> np.ndarray:
        """将灰度图二值化为 0/255 的 uint8 数组。

        Args:
            image: 输入灰度 numpy 数组
            threshold: 二值化阈值 (0-255)

        Returns:
            numpy array (dtype=uint8): 0=背景, 255=前景
        """
        arr = np.asarray(image, dtype=np.uint8)
        arr[arr > threshold] = 255
        arr[arr <= threshold] = 0
        return arr

    # ---- 字号自适应 ----

    @staticmethod
    def get_optimal_font_size(
        text: str,
        font_path: str,
        canvas_w_px: int,
        canvas_h_px: int,
        max_size: int = 4000,
    ) -> int | None:
        """二分查找填满画布的最大字号。

        迁移自 wledfont2_UI / RobotTextGenerator._get_optimal_font_size()。

        Args:
            text: 文字内容
            font_path: 字体路径
            canvas_w_px: 画布宽度 (px)
            canvas_h_px: 画布高度 (px)
            max_size: 最大字号 (避免无限增大)

        Returns:
            最优字号 px, 未找到返回 None
        """
        draw = ImageDraw.Draw(Image.new("L", (10, 10)))
        low, high = 1, max_size
        best_size = None

        while low <= high:
            mid = (low + high) // 2
            try:
                font = ImageFont.truetype(font_path, mid)
            except OSError:
                return best_size

            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]

            if w <= (canvas_w_px - 2) and h <= (canvas_h_px - 2):
                best_size = mid
                low = mid + 1
            else:
                high = mid - 1

        return best_size

    # ---- debug PNG 输出 ----

    @staticmethod
    def save_debug_image(binary: np.ndarray, output_path: str) -> str:
        """保存二值图为 PNG 调试文件。

        Args:
            binary: 二值 numpy 数组 (0/255)
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        img = Image.fromarray(binary, mode="L")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path)
        return output_path


# ---- 模块级便捷函数（兼容旧 font_renderer.py 的调用方式） ----


def render_char(
    char: str,
    font_path: str | None = None,
    font_size_px: int = 600,
) -> np.ndarray:
    """便捷函数：渲染单个字符"""
    r = FontRasterizer(default_font_path=font_path, default_font_size_px=font_size_px)
    return r.render_char(char)


def render_text(
    text: str,
    font_path: str | None = None,
    font_size_px: int = 600,
) -> list[np.ndarray]:
    """便捷函数：渲染一段文字"""
    r = FontRasterizer(default_font_path=font_path, default_font_size_px=font_size_px)
    return r.render_text(text)


def render_char_in_linebox(
    char: str,
    font_path: str | None = None,
    font_size_px: int = 600,
) -> LineboxGlyph:
    """便捷函数：渲染单个字符到 linebox"""
    r = FontRasterizer(default_font_path=font_path, default_font_size_px=font_size_px)
    return r.render_char_in_linebox(char)


def render_text_linebox(
    text: str,
    font_path: str | None = None,
    font_size_px: int = 600,
) -> list[LineboxGlyph]:
    """便捷函数：渲染一段文字到 linebox"""
    r = FontRasterizer(default_font_path=font_path, default_font_size_px=font_size_px)
    return r.render_text_linebox(text)
