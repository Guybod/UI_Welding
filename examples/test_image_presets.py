"""图片预设与调参逻辑冒烟测试（无 Qt UI）。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import ImageProcessConfig
from pipeline.vision.image_preprocessor import process_image, write_image_debug_previews
from pipeline.vision.image_presets import (
    PRESET_LINEART,
    PRESET_PHOTO_EDGE_BETA,
    PRESET_SILHOUETTE,
    get_preset_config,
    preset_beta_hint,
)


def _circle_png(path: Path) -> str:
    img = np.full((400, 400, 3), 255, dtype=np.uint8)
    cv2.circle(img, (200, 200), 100, (0, 0, 0), 2)
    cv2.imwrite(str(path), img)
    return str(path)


def _black_line_png(path: Path) -> str:
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.line(img, (30, 150), (270, 150), (255, 255, 255), 3)
    cv2.imwrite(str(path), img)
    return str(path)


def test_presets_distinct() -> None:
    a = get_preset_config(PRESET_LINEART)
    b = get_preset_config(PRESET_SILHOUETTE)
    assert a.threshold_method != b.threshold_method or a.min_contour_area != b.min_contour_area
    assert preset_beta_hint(PRESET_PHOTO_EDGE_BETA)
    print("PASS presets distinct + beta hints")


def test_lineart_preview() -> None:
    with tempfile.TemporaryDirectory() as td:
        img = _circle_png(Path(td) / "c.png")
        cfg = get_preset_config(PRESET_LINEART)
        r = process_image(img, cfg)
        assert r.ok, r.error
        paths = write_image_debug_previews(r, Path(td) / "out")
        for name in (
            "preview_image_original.png",
            "preview_image_binary.png",
            "preview_image_contours.png",
        ):
            assert Path(paths[name]).is_file(), name
    print("PASS lineart preview files")


def test_min_area_changes_contours() -> None:
    with tempfile.TemporaryDirectory() as td:
        img = _circle_png(Path(td) / "noise.png")
        low = get_preset_config(PRESET_LINEART)
        low.min_contour_area = 10.0
        high = get_preset_config(PRESET_LINEART)
        high.min_contour_area = 5000.0
        r_low = process_image(img, low)
        r_high = process_image(img, high)
        assert r_low.ok
        assert len(r_low.strokes_px) >= len(r_high.strokes_px)
    print("PASS min_contour_area effect")


def test_sharpen_and_canny() -> None:
    with tempfile.TemporaryDirectory() as td:
        img = _circle_png(Path(td) / "c.png")
        cfg = ImageProcessConfig(
            sharpen_amount=0.5,
            edge_mode="canny",
            canny_low=30,
            canny_high=100,
            min_contour_area=20.0,
        )
        r = process_image(img, cfg)
        assert r.ok, r.error
        assert r.stats.get("sharpen_amount", 0) > 0
        assert r.stats.get("edge_mode") == "canny"
    print("PASS sharpen + canny")


def test_invert_black_background() -> None:
    with tempfile.TemporaryDirectory() as td:
        img = _black_line_png(Path(td) / "line.png")
        cfg = ImageProcessConfig(threshold_method="otsu", invert=False, min_contour_area=20.0)
        r0 = process_image(img, cfg)
        cfg_inv = ImageProcessConfig(threshold_method="otsu", invert=True, min_contour_area=20.0)
        r1 = process_image(img, cfg_inv)
        assert r1.ok, r1.error
        assert len(r1.strokes_px) >= 1
    print("PASS invert on black background")


def main() -> int:
    test_presets_distinct()
    test_lineart_preview()
    test_min_area_changes_contours()
    test_sharpen_and_canny()
    test_invert_black_background()
    print("\nAll image preset / tuning tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
