"""视觉提取：文字轮廓/骨架（分流见 text_stroke_extract）、图片轮廓（image_preprocessor）。"""

from pipeline.vision.contour_extractor import ContourExtractor
from pipeline.vision.image_preprocessor import (
    ImageProcessResult,
    process_image,
    write_image_debug_previews,
)
from pipeline.vision.skeleton_extractor import SkeletonExtractor, SkeletonGraph

# 文字焊接/写字提线统一入口（轮廓与骨架不可混用）
from pipeline.text_stroke_extract import (  # noqa: E402
    UnknownTextExtractModeError,
    extract_glyph_strokes,
    normalize_weld_text_mode,
)
