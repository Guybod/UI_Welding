"""焊接/写字 — 文字二值图 → Stroke（轮廓与骨架严格分流）。

- contour：仅 ContourExtractor（外轮廓，闭合描边）
- skeleton：仅 SkeletonExtractor（细化中心线，单道焊/写字）

禁止在本模块外交叉调用两种提取器；排版层应只使用 extract_glyph_strokes()。
图片模式（任意位图）走 pipeline.vision.image_preprocessor，不在此模块。
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from core.types import PathConfig, Stroke

WeldTextMode = Literal["contour", "skeleton"]
_VALID_MODES = frozenset({"contour", "skeleton"})


class UnknownTextExtractModeError(ValueError):
    pass


def normalize_weld_text_mode(mode: str) -> WeldTextMode:
    """规范化焊接文字模式；非法值直接报错，避免静默走错算法。"""
    m = (mode or "contour").strip().lower()
    if m not in _VALID_MODES:
        raise UnknownTextExtractModeError(
            f"unknown text extract mode {mode!r}; use 'contour' or 'skeleton'"
        )
    return m  # type: ignore[return-value]


def extract_glyph_strokes(
    binary: np.ndarray,
    mode: str,
    config: PathConfig | None = None,
) -> tuple[list[Stroke], dict]:
    """单字/单块二值图 → Stroke 列表。

    Returns:
        strokes, extract_meta（骨架含 skeleton_* 字段，轮廓含 contour 标记）
    """
    mode_n = normalize_weld_text_mode(mode)
    if mode_n == "contour":
        from pipeline.vision.contour_extractor import ContourExtractor

        strokes = ContourExtractor().extract(binary, config=config)
        return strokes, {"extract_algorithm": "contour"}

    from pipeline.vision.skeleton_extractor import SkeletonExtractor

    strokes, sk_stats = SkeletonExtractor.extract(
        binary, config=config, backend="auto"
    )
    from pipeline.skeleton_stroke_cleanup import cleanup_skeleton_strokes

    char_h = float(binary.shape[0]) if binary is not None and binary.size else 0.0
    strokes, cleanup_stats = cleanup_skeleton_strokes(strokes, char_height_px=char_h)
    meta = {"extract_algorithm": "skeleton", **dict(sk_stats), **cleanup_stats}
    return strokes, meta
