"""图片模式参数预设 — 供 UI 一键填充 ImageProcessConfig。"""

from __future__ import annotations

from dataclasses import replace

from core.types import ImageProcessConfig

PRESET_LINEART = "lineart"
PRESET_SILHOUETTE = "silhouette"
PRESET_PHOTO_EDGE_BETA = "photo_edge_beta"
PRESET_PHOTO_COMPLEX_BETA = "photo_complex_beta"

PRESET_LABELS: dict[str, tuple[str, bool]] = {
    PRESET_LINEART: ("线稿/白纸黑线", False),
    PRESET_SILHOUETTE: ("剪影/Logo", False),
    PRESET_PHOTO_EDGE_BETA: ("照片边缘 [Beta]", True),
    PRESET_PHOTO_COMPLEX_BETA: ("复杂照片 [Beta]", True),
}

_PRESETS: dict[str, ImageProcessConfig] = {
    PRESET_LINEART: ImageProcessConfig(
        threshold_method="adaptive",
        blur_kernel=3,
        morph_kernel_size=2,
        morph_open_size=2,
        min_contour_area=50.0,
        simplification_epsilon=1.5,
        invert=False,
        max_contours=50,
    ),
    PRESET_SILHOUETTE: ImageProcessConfig(
        threshold_method="otsu",
        blur_kernel=5,
        morph_kernel_size=3,
        min_contour_area=300.0,
        simplification_epsilon=2.0,
        max_contours=20,
        invert=False,
    ),
    PRESET_PHOTO_EDGE_BETA: ImageProcessConfig(
        threshold_method="adaptive",
        blur_kernel=5,
        sharpen_amount=0.35,
        morph_kernel_size=2,
        morph_open_size=0,
        min_contour_area=100.0,
        simplification_epsilon=2.5,
        max_contours=100,
        edge_mode="canny",
        canny_low=40,
        canny_high=120,
        invert=False,
    ),
    PRESET_PHOTO_COMPLEX_BETA: ImageProcessConfig(
        threshold_method="adaptive",
        blur_kernel=7,
        morph_kernel_size=3,
        min_contour_area=200.0,
        simplification_epsilon=3.0,
        max_contours=80,
        invert=False,
    ),
}

_BETA_HINTS: dict[str, str] = {
    PRESET_PHOTO_EDGE_BETA: "照片边缘为 Beta：需配合预览调参，不保证效果。",
    PRESET_PHOTO_COMPLEX_BETA: "复杂照片不保证效果，请尽量使用线稿/剪影类素材。",
}


def list_preset_ids() -> list[str]:
    return [
        PRESET_LINEART,
        PRESET_SILHOUETTE,
        PRESET_PHOTO_EDGE_BETA,
        PRESET_PHOTO_COMPLEX_BETA,
    ]


def get_preset_config(preset_id: str) -> ImageProcessConfig:
    """返回预设副本；未知 id 时回退 lineart。"""
    base = _PRESETS.get(preset_id, _PRESETS[PRESET_LINEART])
    return replace(base)


def preset_beta_hint(preset_id: str) -> str:
    return _BETA_HINTS.get(preset_id, "")
