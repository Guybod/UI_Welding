"""图像 → 二值图 → 轮廓 → strokes_px（绘图页 Phase 1 内核）。

无 Qt、无机器人、无 CRI。仅 OpenCV + 现有 Stroke / ContourExtractor 辅助。

产品口径：适合线稿 / Logo / 剪影 / 简单花朵轮廓；随手拍需调参成线稿；
复杂背景与照片级写实暂不承诺。

fit_mode（contain | stretch）在 Phase 2 image_runner 中映射至可写区时实现；
本模块 Phase 1 仅在 stats 中记录 cfg.fit_mode。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from core.types import ImageProcessConfig, Stroke
from pipeline.vision.contour_extractor import ContourExtractor


@dataclass
class ImageProcessResult:
    ok: bool
    error: str = ""
    original_size: tuple[int, int] = (0, 0)  # (width, height)
    original_image: np.ndarray | None = None
    binary_image: np.ndarray | None = None
    contour_preview_image: np.ndarray | None = None
    strokes_px: list[Stroke] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def process_image(image_path: str, cfg: ImageProcessConfig | None = None) -> ImageProcessResult:
    """从图片路径提取像素轮廓 strokes。

    Args:
        image_path: 本地图片路径
        cfg: 预处理参数，None 则用 ImageProcessConfig 默认值

    Returns:
        ImageProcessResult
    """
    cfg = cfg or ImageProcessConfig()
    warnings: list[str] = []
    stats: dict = {"fit_mode": cfg.fit_mode}

    path = Path(image_path)
    if not path.is_file():
        return ImageProcessResult(
            ok=False,
            error=f"image not found: {image_path}",
            stats=stats,
            warnings=warnings,
        )

    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return ImageProcessResult(
            ok=False,
            error=f"cv2.imread failed: {image_path}",
            stats=stats,
            warnings=warnings,
        )

    h, w = bgr.shape[:2]
    stats["original_width_px"] = w
    stats["original_height_px"] = h

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray, pre_stats = _preprocess_gray(gray, cfg)
    stats.update(pre_stats)
    stats["threshold_method"] = cfg.threshold_method
    stats["edge_mode"] = cfg.edge_mode

    binary = _to_binary(gray, cfg)
    if cfg.invert:
        binary = cv2.bitwise_not(binary)
        stats["invert_applied"] = True
    else:
        stats["invert_applied"] = False

    binary, morph_stats = _apply_morphology(binary, cfg)
    stats.update(morph_stats)

    retrieval = cv2.RETR_EXTERNAL if cfg.keep_external_only else cv2.RETR_TREE
    raw_contours, hierarchy = _find_contours(binary, retrieval)

    stats["contours_raw"] = len(raw_contours) if raw_contours else 0

    if not raw_contours:
        return ImageProcessResult(
            ok=False,
            error="no contours found after preprocessing",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            contour_preview_image=_make_contour_preview(bgr, []),
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    filtered_contours, filtered_hierarchy = ContourExtractor._filter_small(
        raw_contours, hierarchy, cfg.min_contour_area,
    )
    stats["contours_after_area_filter"] = len(filtered_contours)

    if not filtered_contours:
        return ImageProcessResult(
            ok=False,
            error="no contours above min_contour_area",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            contour_preview_image=_make_contour_preview(bgr, []),
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    if cfg.keep_external_only:
        labels = ["outer"] * len(filtered_contours)
    else:
        labels = ContourExtractor._classify_inner_outer(filtered_hierarchy)

    indexed = list(enumerate(filtered_contours))
    indexed.sort(key=lambda pair: cv2.contourArea(pair[1]), reverse=True)
    if cfg.max_contours > 0 and len(indexed) > cfg.max_contours:
        dropped = len(indexed) - cfg.max_contours
        indexed = indexed[: cfg.max_contours]
        warnings.append(
            f"trimmed {dropped} contour(s) to max_contours={cfg.max_contours}"
        )

    simplified_contours: list[np.ndarray] = []
    raw_for_closed: list[np.ndarray] = []
    stroke_labels: list[str] = []
    for orig_i, raw_cnt in indexed:
        if len(raw_cnt) < 2:
            continue
        closed = ContourExtractor._detect_closed(raw_cnt)
        eps = max(0.5, float(cfg.simplification_epsilon))
        approx = cv2.approxPolyDP(raw_cnt, eps, closed)
        if len(approx) < 2:
            continue
        simplified_contours.append(approx)
        raw_for_closed.append(raw_cnt)
        stroke_labels.append(labels[orig_i] if orig_i < len(labels) else "outer")

    stats["contours_after_simplify"] = len(simplified_contours)

    if not simplified_contours:
        return ImageProcessResult(
            ok=False,
            error="all contours removed by simplification",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            contour_preview_image=_make_contour_preview(bgr, []),
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    strokes: list[Stroke] = []
    for i, cnt in enumerate(simplified_contours):
        is_hole = stroke_labels[i] == "inner"
        raw_cnt = raw_for_closed[i]
        was_closed = ContourExtractor._detect_closed(raw_cnt)
        stroke = ContourExtractor._extract_contour_path(
            cnt, is_hole=is_hole, force_closed=was_closed,
        )
        stroke.source_type = "image"
        stroke.id = f"img_{i:04d}_{uuid.uuid4().hex[:6]}"
        stroke.metadata["area_px"] = float(cv2.contourArea(raw_cnt))
        strokes.append(stroke)

    strokes = ContourExtractor._unify_direction(strokes, simplified_contours)
    strokes.sort(key=lambda s: min(p.x for p in s.points_px) if s.points_px else 0.0)

    total_points = count_stroke_points(strokes)
    stats["stroke_count"] = len(strokes)
    stats["total_points_px"] = total_points

    if total_points > cfg.max_total_points:
        return ImageProcessResult(
            ok=False,
            error=(
                f"total points {total_points} exceeds max_total_points={cfg.max_total_points}; "
                "increase simplification_epsilon or min_contour_area, or reduce image complexity"
            ),
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            contour_preview_image=_make_contour_preview(bgr, simplified_contours),
            strokes_px=strokes,
            stats=stats,
            warnings=warnings,
        )

    stats["ok"] = True
    return ImageProcessResult(
        ok=True,
        original_size=(w, h),
        original_image=bgr,
        binary_image=binary,
        contour_preview_image=_make_contour_preview(bgr, simplified_contours),
        strokes_px=strokes,
        stats=stats,
        warnings=warnings,
    )


def write_image_debug_previews(result: ImageProcessResult, output_dir: str | Path) -> dict[str, str]:
    """将 ImageProcessResult 写入 debug PNG。

    Returns:
        dict: 输出文件名 → 绝对路径
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    if result.original_image is not None:
        p = out / "preview_image_original.png"
        cv2.imwrite(str(p), result.original_image)
        paths["preview_image_original.png"] = str(p)

    if result.binary_image is not None:
        p = out / "preview_image_binary.png"
        cv2.imwrite(str(p), result.binary_image)
        paths["preview_image_binary.png"] = str(p)

    if result.contour_preview_image is not None:
        p = out / "preview_image_contours.png"
        cv2.imwrite(str(p), result.contour_preview_image)
        paths["preview_image_contours.png"] = str(p)

    return paths


def _preprocess_gray(gray: np.ndarray, cfg: ImageProcessConfig) -> tuple[np.ndarray, dict]:
    """对比度/亮度 → 中值 → 高斯 → 锐化。"""
    stats: dict = {}
    out = gray.astype(np.float32)

    if abs(cfg.contrast - 1.0) > 1e-6 or cfg.brightness != 0:
        out = out * float(cfg.contrast) + float(cfg.brightness)
        out = np.clip(out, 0, 255)
        stats["contrast"] = round(cfg.contrast, 3)
        stats["brightness"] = cfg.brightness

    out = out.astype(np.uint8)

    if cfg.median_blur_kernel > 1:
        k = int(cfg.median_blur_kernel) | 1
        out = cv2.medianBlur(out, k)
        stats["median_blur_kernel"] = k
    else:
        stats["median_blur_kernel"] = 0

    if cfg.blur_kernel > 1:
        k = int(cfg.blur_kernel) | 1
        sigma = float(cfg.gaussian_sigma) if cfg.gaussian_sigma > 0 else 0.0
        out = cv2.GaussianBlur(out, (k, k), sigmaX=sigma, sigmaY=sigma)
        stats["blur_kernel"] = k
        stats["gaussian_sigma"] = round(sigma, 2) if sigma > 0 else "auto"
    else:
        stats["blur_kernel"] = 0

    if cfg.sharpen_amount > 0.01:
        sig = max(0.5, float(cfg.sharpen_sigma))
        blurred = cv2.GaussianBlur(out, (0, 0), sigmaX=sig, sigmaY=sig)
        amount = float(cfg.sharpen_amount)
        out = cv2.addWeighted(out, 1.0 + amount, blurred, -amount, 0)
        stats["sharpen_amount"] = round(amount, 3)
        stats["sharpen_sigma"] = round(sig, 2)

    return out, stats


def _to_binary(gray: np.ndarray, cfg: ImageProcessConfig) -> np.ndarray:
    mode = (cfg.edge_mode or "none").lower()
    if mode == "canny":
        lo = int(cfg.canny_low)
        hi = int(cfg.canny_high)
        if hi < lo:
            hi = min(255, lo + 1)
        return cv2.Canny(gray, lo, hi)
    return _threshold(gray, cfg)


def _threshold(gray: np.ndarray, cfg: ImageProcessConfig) -> np.ndarray:
    method = (cfg.threshold_method or "adaptive").lower()
    if method == "fixed":
        _, binary = cv2.threshold(
            gray, cfg.threshold_value, 255, cv2.THRESH_BINARY_INV,
        )
    elif method == "otsu":
        _, binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
    else:
        block = max(3, int(cfg.adaptive_block_size) | 1)
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block,
            int(cfg.adaptive_c),
        )
    return binary


def _apply_morphology(binary: np.ndarray, cfg: ImageProcessConfig) -> tuple[np.ndarray, dict]:
    stats: dict = {}
    out = binary
    if cfg.morph_kernel_size >= 2:
        k = int(cfg.morph_kernel_size)
        kernel = np.ones((k, k), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel)
        stats["morph_close"] = k
    else:
        stats["morph_close"] = 0
    if cfg.morph_open_size >= 2:
        k = int(cfg.morph_open_size)
        kernel = np.ones((k, k), np.uint8)
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel)
        stats["morph_open"] = k
    else:
        stats["morph_open"] = 0
    return out, stats


def _find_contours(
    binary: np.ndarray,
    mode: int,
) -> tuple[list, np.ndarray | None]:
    if binary.dtype != np.uint8:
        binary = binary.astype(np.uint8)
    contours, hierarchy = cv2.findContours(
        binary, mode, cv2.CHAIN_APPROX_NONE,
    )
    if hierarchy is not None:
        hierarchy = hierarchy[0]
    return contours, hierarchy


def _make_contour_preview(
    bgr: np.ndarray,
    contours: list[np.ndarray],
) -> np.ndarray:
    """白底 + 红色轮廓线（不叠加原图）。"""
    h, w = bgr.shape[:2]
    preview = np.full((h, w, 3), 255, dtype=np.uint8)
    if contours:
        cv2.drawContours(
            preview, contours, -1, (0, 0, 255), 1, lineType=cv2.LINE_AA,
        )
    return preview


def count_stroke_points(strokes: list[Stroke]) -> int:
    return sum(len(s.points_px) for s in strokes)
