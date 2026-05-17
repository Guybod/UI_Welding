"""字体渲染模块 — PIL 高分辨率文字渲染 → 二值 numpy array"""

from pipeline.raster.font_rasterizer import (
    FontRasterizer,
    LineboxGlyph,
    get_default_font_path,
    render_char,
    render_text,
    render_char_in_linebox,
    render_text_linebox,
)
