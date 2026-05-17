"""Phase 1: image_preprocessor 内核冒烟测试（无 UI / 无 CRI）。"""

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
from pipeline.vision.image_preprocessor import (
    count_stroke_points,
    process_image,
    write_image_debug_previews,
)

ASSETS = ROOT / "tests" / "assets"
OUTPUT = ROOT / "output" / "image_preprocessor_debug"


def _save_png(path: Path, img: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return str(path)


def _white_black_circle(path: Path, size: int = 400) -> str:
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 4, (0, 0, 0), 2)
    return _save_png(path, img)


def _black_white_line(path: Path, size: int = 400) -> str:
    img = np.zeros((size, size, 3), dtype=np.uint8)
    cv2.line(img, (40, size // 2), (size - 40, size // 2), (255, 255, 255), 3)
    return _save_png(path, img)


def _noise_and_main(path: Path, size: int = 400) -> str:
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    rng = np.random.default_rng(42)
    for _ in range(80):
        x, y = int(rng.integers(0, size)), int(rng.integers(0, size))
        cv2.circle(img, (x, y), 2, (0, 0, 0), -1)
    cv2.circle(img, (size // 2, size // 2), size // 3, (0, 0, 0), 3)
    return _save_png(path, img)


def _dense_pattern(path: Path, size: int = 200) -> str:
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    for x in range(10, size - 10, 8):
        for y in range(10, size - 10, 8):
            cv2.rectangle(img, (x, y), (x + 4, y + 4), (0, 0, 0), -1)
    return _save_png(path, img)


def test_white_black_circle() -> None:
    img_path = _white_black_circle(ASSETS / "white_black_circle.png")
    for method in ("adaptive", "otsu"):
        cfg = ImageProcessConfig(
            threshold_method=method,
            min_contour_area=50.0,
            simplification_epsilon=2.0,
        )
        result = process_image(img_path, cfg)
        assert result.ok, f"{method}: {result.error}"
        assert len(result.strokes_px) >= 1, method
        assert count_stroke_points(result.strokes_px) > 0, method
        out = OUTPUT / f"test1_{method}"
        paths = write_image_debug_previews(result, out)
        for name in (
            "preview_image_original.png",
            "preview_image_binary.png",
            "preview_image_contours.png",
        ):
            assert Path(paths[name]).is_file(), name
    print("PASS test1 white_black_circle (adaptive + otsu)")


def test_black_white_line_invert() -> None:
    img_path = _black_white_line(ASSETS / "black_white_line.png")
    cfg = ImageProcessConfig(
        threshold_method="otsu",
        invert=True,
        min_contour_area=30.0,
        simplification_epsilon=2.0,
    )
    result = process_image(img_path, cfg)
    assert result.ok, result.error
    assert len(result.strokes_px) >= 1
    assert count_stroke_points(result.strokes_px) > 0
    write_image_debug_previews(result, OUTPUT / "test2_invert")
    print("PASS test2 black_white_line + invert")


def test_noise_filter() -> None:
    img_path = _noise_and_main(ASSETS / "noise_and_circle.png")
    cfg = ImageProcessConfig(
        threshold_method="adaptive",
        min_contour_area=500.0,
        simplification_epsilon=2.0,
    )
    result = process_image(img_path, cfg)
    assert result.ok, result.error
    assert len(result.strokes_px) >= 1
    areas = [s.metadata.get("area_px", 0) for s in result.strokes_px]
    assert all(a >= 500.0 for a in areas), areas
    assert result.stats["contours_after_area_filter"] < result.stats["contours_raw"]
    write_image_debug_previews(result, OUTPUT / "test3_noise")
    print("PASS test3 noise filter (min_contour_area)")


def test_max_total_points() -> None:
    img_path = _dense_pattern(ASSETS / "dense_grid.png")
    cfg = ImageProcessConfig(
        threshold_method="fixed",
        threshold_value=200,
        min_contour_area=1.0,
        max_contours=200,
        simplification_epsilon=0.5,
        max_total_points=50,
    )
    result = process_image(img_path, cfg)
    assert not result.ok
    assert "max_total_points" in result.error
    assert result.binary_image is not None
    write_image_debug_previews(result, OUTPUT / "test4_max_points")
    print("PASS test4 max_total_points (ok=False, no crash)")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    test_white_black_circle()
    test_black_white_line_invert()
    test_noise_filter()
    test_max_total_points()
    print(f"\nAll image_preprocessor tests passed. Debug output: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
