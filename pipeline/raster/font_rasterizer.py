"""PIL 高分辨率字体渲染 → 二值 numpy array

无 Qt/PySide6 依赖。只做渲染，不做排版、不做路径提取。
"""

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


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

        padding = size // 8
        img_w = w + 2 * padding
        img_h = h + 2 * padding

        img = Image.new("L", (img_w, img_h), 0)
        draw = ImageDraw.Draw(img)
        draw.text((padding - bbox[0], padding - bbox[1]), char, fill=255, font=font)

        return self.binarize(np.array(img))

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
