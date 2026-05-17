"""图像 → 二值图 → 轮廓 → strokes_px（绘图页 Phase 1 内核）。

无 Qt、无机器人、无 CRI。仅 OpenCV + 现有 Stroke / ContourExtractor 辅助。

contour_strategy（Phase 3-b / 3-b-fix）：
- external：region-first 实心 mask → 最外轮廓 + 去重，预览与轨迹同源
- all：二值边缘图 RETR_TREE，保留内部线条
- centerline_beta：占位，回退 external
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np

from core.types import ImageProcessConfig, Stroke
from pipeline.vision.contour_extractor import ContourExtractor

_CONTOUR_STRATEGIES = frozenset({"external", "all", "centerline_beta"})


@dataclass
class ImageProcessResult:
    ok: bool
    error: str = ""
    original_size: tuple[int, int] = (0, 0)  # (width, height)
    original_image: np.ndarray | None = None
    binary_image: np.ndarray | None = None
    mask_image: np.ndarray | None = None
    contour_preview_image: np.ndarray | None = None
    contour_external_preview_image: np.ndarray | None = None
    strokes_px: list[Stroke] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def resolve_contour_settings(cfg: ImageProcessConfig) -> tuple[str, bool, int]:
    """统一 contour_strategy 与 keep_external_only / OpenCV retrieval 模式。"""
    strategy = (cfg.contour_strategy or "external").lower()
    if strategy not in _CONTOUR_STRATEGIES:
        strategy = "external"
    if strategy == "external":
        return strategy, True, cv2.RETR_EXTERNAL
    if strategy == "all":
        return strategy, False, cv2.RETR_TREE
    return "external", True, cv2.RETR_EXTERNAL


def contour_strategy_log_messages(cfg: ImageProcessConfig) -> list[str]:
    """预览/生成时写入日志的轮廓策略提示。"""
    strategy = (cfg.contour_strategy or "external").lower()
    msgs: list[str] = []
    if strategy == "all":
        msgs.append(
            "[Drawing] 当前为全部轮廓模式，低精度图片可能出现双层边；"
            "如外轮廓重复，请切换“外轮廓优先”。"
        )
    elif strategy == "external":
        msgs.append(
            "[Drawing] 图片模式：当前使用外轮廓优先策略，适合剪影/Logo，内部线条将被忽略。"
        )
    elif strategy == "centerline_beta":
        msgs.append(
            "[Drawing] 中心线 [Beta] 暂未正式实现，已按外轮廓优先处理。"
        )
    if cfg.fill_before_contour:
        msgs.append("[Drawing] 已启用填充后提轮廓，用于合并破碎边缘。")
    return msgs


def process_image(image_path: str, cfg: ImageProcessConfig | None = None) -> ImageProcessResult:
    """从图片路径提取像素轮廓 strokes。"""
    cfg = cfg or ImageProcessConfig()
    warnings: list[str] = []
    stats: dict = {"fit_mode": cfg.fit_mode}

    strategy_raw = (cfg.contour_strategy or "external").lower()
    if strategy_raw == "centerline_beta":
        warnings.append("centerline_beta 暂未正式实现，已按外轮廓优先处理。")
    strategy, keep_external, retrieval = resolve_contour_settings(cfg)
    stats["selected_strategy"] = strategy

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

    stats.update(_pipeline_step_flags(cfg))

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    if cfg.step_preprocess:
        gray, pre_stats = _preprocess_gray(gray, cfg)
        stats.update(pre_stats)
    else:
        stats["preprocess_skipped"] = True

    stats["threshold_method"] = cfg.threshold_method
    stats["edge_mode"] = cfg.edge_mode

    if not cfg.step_binarize:
        return ImageProcessResult(
            ok=False,
            error="二值化步骤已关闭，无法继续提取轮廓",
            original_size=(w, h),
            original_image=bgr,
            stats=stats,
            warnings=warnings,
        )

    binary = _to_binary(gray, cfg)
    if cfg.invert:
        binary = cv2.bitwise_not(binary)
        stats["invert_applied"] = True
    else:
        stats["invert_applied"] = False

    stats["binary_foreground_ratio"] = round(
        float(np.count_nonzero(binary)) / max(1, binary.size), 6,
    )

    if not cfg.step_contour_extract:
        return ImageProcessResult(
            ok=False,
            error="轮廓提取步骤已关闭",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            stats=stats,
            warnings=warnings,
        )

    if strategy == "all":
        if cfg.step_morphology:
            binary, morph_stats = _apply_morphology(binary, cfg)
            stats.update(morph_stats)
        else:
            stats.update({"morph_close": 0, "morph_open": 0, "morphology_skipped": True})
        if cfg.step_region_mask:
            mask = _build_region_mask(binary, cfg, external_mode=False)
        else:
            mask = (binary > 0).astype(np.uint8) * 255
            stats["region_mask_skipped"] = True
        external_source = "binary"
        raw_contours, hierarchy, ext_meta = _extract_all_contours(binary, mask, cfg)
    else:
        if cfg.step_region_mask:
            mask, morph_stats = _build_solid_external_mask(
                binary, cfg, apply_morph=cfg.step_morphology,
            )
            stats.update(morph_stats)
        else:
            stats.update({"morph_close": 0, "morph_open": 0, "morph_mode": cfg.morph_mode})
            mask = (binary > 0).astype(np.uint8) * 255
            stats["region_mask_skipped"] = True
        external_source = "mask"
        raw_contours, hierarchy, ext_meta = _extract_external_contours(
            mask, cfg, dedup=cfg.step_contour_dedup,
        )

    stats.update(ext_meta)
    stats["external_source"] = external_source
    stats["mask_foreground_ratio"] = round(
        float(np.count_nonzero(mask)) / max(1, mask.size), 6,
    )
    stats["contour_strategy"] = strategy
    stats["contour_strategy_requested"] = strategy_raw
    stats["fill_before_contour"] = bool(cfg.fill_before_contour)
    stats["fill_holes"] = bool(cfg.fill_holes)
    stats["keep_external_only"] = keep_external
    stats["remove_border_contour"] = bool(cfg.remove_border_contour)
    stats["contour_retrieval_mode"] = (
        "RETR_EXTERNAL" if strategy == "external" else "RETR_TREE"
    )

    if cfg.remove_border_contour and raw_contours:
        before = len(raw_contours)
        raw_contours = _filter_border_contours(raw_contours, w, h)
        dropped = before - len(raw_contours)
        if dropped:
            warnings.append(f"removed {dropped} border-touching contour(s)")
            hierarchy = None

    empty_preview = _make_contour_preview(bgr, [])

    if not raw_contours:
        return ImageProcessResult(
            ok=False,
            error="no contours found after preprocessing",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            mask_image=mask,
            contour_preview_image=empty_preview,
            contour_external_preview_image=empty_preview,
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    if cfg.step_contour_filter:
        filtered_contours, filtered_hierarchy = ContourExtractor._filter_small(
            raw_contours, hierarchy, cfg.min_contour_area,
        )
    else:
        filtered_contours = list(raw_contours)
        filtered_hierarchy = hierarchy
        stats["contour_filter_skipped"] = True
    stats["contours_after_area_filter"] = len(filtered_contours)

    if not filtered_contours:
        return ImageProcessResult(
            ok=False,
            error="no contours above min_contour_area",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            mask_image=mask,
            contour_preview_image=empty_preview,
            contour_external_preview_image=empty_preview,
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    if keep_external:
        labels = ["outer"] * len(filtered_contours)
    else:
        labels = ContourExtractor._classify_inner_outer(filtered_hierarchy)

    indexed = list(enumerate(filtered_contours))
    indexed.sort(key=lambda pair: cv2.contourArea(pair[1]), reverse=True)
    if cfg.step_contour_filter and cfg.max_contours > 0 and len(indexed) > cfg.max_contours:
        dropped = len(indexed) - cfg.max_contours
        indexed = indexed[: cfg.max_contours]
        warnings.append(
            f"trimmed {dropped} contour(s) to max_contours={cfg.max_contours}"
        )

    simplify_cfg = cfg
    if not cfg.step_contour_filter:
        simplify_cfg = replace(cfg, simplification_epsilon=0.5)

    simplified_contours, raw_for_closed, stroke_labels = _simplify_contours(
        indexed, labels, simplify_cfg,
    )

    stats["contours_after_simplify"] = len(simplified_contours)
    stats["contour_count_kept"] = len(simplified_contours)
    stats["points_count_after_simplify"] = sum(len(c) for c in simplified_contours)

    if not simplified_contours:
        return ImageProcessResult(
            ok=False,
            error="all contours removed by simplification",
            original_size=(w, h),
            original_image=bgr,
            binary_image=binary,
            mask_image=mask,
            contour_preview_image=empty_preview,
            contour_external_preview_image=empty_preview,
            strokes_px=[],
            stats=stats,
            warnings=warnings,
        )

    strokes = _contours_to_strokes(
        simplified_contours, raw_for_closed, stroke_labels, strategy,
    )
    strokes = ContourExtractor._unify_direction(strokes, simplified_contours)
    strokes.sort(key=lambda s: min(p.x for p in s.points_px) if s.points_px else 0.0)

    total_points = count_stroke_points(strokes)
    stats["stroke_count"] = len(strokes)
    stats["final_stroke_count"] = len(strokes)
    stats["total_points_px"] = total_points
    stats["warnings"] = list(warnings)

    if strategy == "external" and len(strokes) > 1:
        warnings.append(
            f"external mode kept {len(strokes)} separate outer contour(s) "
            "(multiple disconnected subjects)"
        )
        stats["warnings"] = list(warnings)

    # 预览与轨迹必须同源：同一份 simplified_contours
    unified_preview = _make_contour_preview(bgr, simplified_contours)

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
            mask_image=mask,
            contour_preview_image=unified_preview,
            contour_external_preview_image=unified_preview,
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
        mask_image=mask,
        contour_preview_image=unified_preview,
        contour_external_preview_image=unified_preview,
        strokes_px=strokes,
        stats=stats,
        warnings=warnings,
    )


def write_image_debug_previews(result: ImageProcessResult, output_dir: str | Path) -> dict[str, str]:
    """将 ImageProcessResult 写入 debug PNG。"""
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

    if result.mask_image is not None:
        p = out / "preview_image_mask.png"
        cv2.imwrite(str(p), result.mask_image)
        paths["preview_image_mask.png"] = str(p)

    if result.contour_preview_image is not None:
        p = out / "preview_image_contours.png"
        cv2.imwrite(str(p), result.contour_preview_image)
        paths["preview_image_contours.png"] = str(p)

    if result.contour_external_preview_image is not None:
        p = out / "preview_image_contours_external.png"
        cv2.imwrite(str(p), result.contour_external_preview_image)
        paths["preview_image_contours_external.png"] = str(p)

    return paths


def _pipeline_step_flags(cfg: ImageProcessConfig) -> dict:
    return {
        "step_preprocess": bool(cfg.step_preprocess),
        "step_binarize": bool(cfg.step_binarize),
        "step_morphology": bool(cfg.step_morphology),
        "step_region_mask": bool(cfg.step_region_mask),
        "step_contour_extract": bool(cfg.step_contour_extract),
        "step_contour_dedup": bool(cfg.step_contour_dedup),
        "step_contour_filter": bool(cfg.step_contour_filter),
        "step_mapping": bool(cfg.step_mapping),
    }


def _extract_external_contours(
    solid_mask: np.ndarray,
    cfg: ImageProcessConfig,
    *,
    dedup: bool = True,
) -> tuple[list, np.ndarray | None, dict]:
    """region-first：仅对实心 mask 提最外轮廓，并去重防双边。"""
    raw, hierarchy = _find_contours(
        solid_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE,
    )
    meta: dict = {
        "contour_count_raw": len(raw) if raw else 0,
        "contours_raw": len(raw) if raw else 0,
        "contour_count_external": len(raw) if raw else 0,
    }
    if dedup:
        deduped = _deduplicate_external_contours(raw)
    else:
        deduped = list(raw)
        meta["contour_dedup_skipped"] = True
    meta["contour_count_after_dedup"] = len(deduped)
    if len(raw) != len(deduped):
        meta["contour_dedup_removed"] = len(raw) - len(deduped)
    return deduped, None, meta


def _extract_all_contours(
    binary: np.ndarray,
    mask: np.ndarray,
    cfg: ImageProcessConfig,
) -> tuple[list, np.ndarray | None, dict]:
    """all 模式：在二值边缘图上 RETR_TREE。"""
    raw, hierarchy = _find_contours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE,
    )
    ext_only, _ = _find_contours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return raw, hierarchy, {
        "contour_count_raw": len(raw) if raw else 0,
        "contours_raw": len(raw) if raw else 0,
        "contour_count_external": len(ext_only) if ext_only else 0,
        "contour_count_after_dedup": len(raw) if raw else 0,
    }


def _build_solid_external_mask(
    binary: np.ndarray,
    cfg: ImageProcessConfig,
    *,
    apply_morph: bool = True,
) -> tuple[np.ndarray, dict]:
    """external 专用：将可能的双环/边缘带合并为实心前景区域。"""
    mask = (binary > 0).astype(np.uint8) * 255
    morph_stats: dict = {"morph_close": 0, "morph_open": 0, "morph_mode": cfg.morph_mode}
    solid = mask
    if apply_morph and cfg.step_morphology:
        solid, morph_stats = _apply_morphology(solid, cfg)

    if cfg.fill_holes or cfg.fill_before_contour:
        solid = _fill_holes(solid)

    min_area = max(float(cfg.min_contour_area), 16.0)
    solid = _keep_large_components(solid, min_area)
    return solid, morph_stats


def _build_region_mask(
    binary: np.ndarray,
    cfg: ImageProcessConfig,
    *,
    external_mode: bool,
) -> np.ndarray:
    """all 模式下的区域 mask（对照用，不用于提轮廓）。"""
    mask = (binary > 0).astype(np.uint8) * 255
    if not cfg.fill_before_contour:
        return mask
    if cfg.step_morphology:
        mask, _ = _apply_morphology(mask, cfg)
    if cfg.fill_holes:
        mask = _fill_holes(mask)
    return mask


def _keep_large_components(mask: np.ndarray, min_area: float) -> np.ndarray:
    """保留面积足够的连通域，去掉噪点。"""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return mask
    out = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            out[labels == i] = 255
    return out


def _deduplicate_external_contours(contours: list) -> list:
    """external 防双边：去掉被大轮廓包裹且高度相似的重复轮廓。"""
    if len(contours) <= 1:
        return list(contours)

    ordered = sorted(contours, key=cv2.contourArea, reverse=True)
    kept: list = []

    for cnt in ordered:
        if len(cnt) < 3:
            continue
        dup = False
        for master in kept:
            if _is_duplicate_external_pair(cnt, master):
                dup = True
                break
        if not dup:
            kept.append(cnt)
    return kept


def _is_duplicate_external_pair(inner: np.ndarray, outer: np.ndarray) -> bool:
    """判定 inner 是否为 outer 的双层边重复（应丢弃 inner）。"""
    ai = abs(cv2.contourArea(inner))
    ao = abs(cv2.contourArea(outer))
    if ao < ai:
        inner, outer = outer, inner
        ai, ao = ao, ai
    if ao <= 1:
        return False

    mi = cv2.moments(inner)
    if mi["m00"] <= 0:
        return False
    cx = mi["m10"] / mi["m00"]
    cy = mi["m01"] / mi["m00"]
    if cv2.pointPolygonTest(outer, (float(cx), float(cy)), False) < 0:
        return False

    if ai / ao >= 0.88:
        return True

    xi, yi, wi, hi = cv2.boundingRect(inner)
    xo, yo, wo, ho = cv2.boundingRect(outer)
    inter_x1 = max(xi, xo)
    inter_y1 = max(yi, yo)
    inter_x2 = min(xi + wi, xo + wo)
    inter_y2 = min(yi + hi, yo + ho)
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return False
    inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    union = wi * hi + wo * ho - inter_area
    iou = inter_area / max(1.0, union)
    if iou >= 0.82:
        return True

    peri_i = max(cv2.arcLength(inner, True), 1.0)
    dists = []
    step = max(1, len(inner) // 40)
    for pt in inner[::step]:
        px, py = float(pt[0][0]), float(pt[0][1])
        d = cv2.pointPolygonTest(outer, (px, py), True)
        dists.append(abs(d))
    if dists and max(dists) < 6.0 and ai / ao >= 0.55:
        return True

    return False


def _simplify_contours(
    indexed: list[tuple[int, np.ndarray]],
    labels: list[str],
    cfg: ImageProcessConfig,
) -> tuple[list[np.ndarray], list[np.ndarray], list[str]]:
    simplified: list[np.ndarray] = []
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
        simplified.append(approx)
        raw_for_closed.append(raw_cnt)
        stroke_labels.append(labels[orig_i] if orig_i < len(labels) else "outer")
    return simplified, raw_for_closed, stroke_labels


def _contours_to_strokes(
    simplified_contours: list[np.ndarray],
    raw_for_closed: list[np.ndarray],
    stroke_labels: list[str],
    strategy: str,
) -> list[Stroke]:
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
        stroke.metadata["contour_strategy"] = strategy
        strokes.append(stroke)
    return strokes


def _fill_holes(binary: np.ndarray) -> np.ndarray:
    h, w = binary.shape[:2]
    flood = binary.copy()
    pad = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(flood, pad, (0, 0), 255)
    flood_inv = cv2.bitwise_not(flood)
    return cv2.bitwise_or(binary, flood_inv)


def _filter_border_contours(
    contours: list,
    width: int,
    height: int,
    margin: int = 2,
) -> list:
    img_area = float(width * height)
    kept: list = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = cv2.contourArea(cnt)
        touches = (
            x <= margin
            or y <= margin
            or x + bw >= width - margin
            or y + bh >= height - margin
        )
        if touches and area >= 0.85 * img_area:
            continue
        kept.append(cnt)
    return kept


def _preprocess_gray(gray: np.ndarray, cfg: ImageProcessConfig) -> tuple[np.ndarray, dict]:
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


_MORPH_MODES = ("none", "close", "open", "open_close", "close_open")


def _morph_op_sequence(mode: str) -> list[str]:
    if mode == "close":
        return ["close"]
    if mode == "open":
        return ["open"]
    if mode == "open_close":
        return ["open", "close"]
    if mode == "close_open":
        return ["close", "open"]
    return []


def _morph_kernel(size: int) -> np.ndarray | None:
    k = int(size)
    if k < 2:
        return None
    k = k | 1
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def _apply_morphology(binary: np.ndarray, cfg: ImageProcessConfig) -> tuple[np.ndarray, dict]:
    stats: dict = {
        "morph_mode": cfg.morph_mode,
        "morph_close": 0,
        "morph_open": 0,
    }
    out = binary
    if not cfg.step_morphology or cfg.morph_mode == "none":
        stats["morphology_skipped"] = True
        return out, stats

    for op in _morph_op_sequence(cfg.morph_mode):
        if op == "close":
            kernel = _morph_kernel(cfg.morph_kernel_size)
            if kernel is None:
                continue
            out = cv2.morphologyEx(out, cv2.MORPH_CLOSE, kernel)
            stats["morph_close"] = int(cfg.morph_kernel_size)
        elif op == "open":
            kernel = _morph_kernel(cfg.morph_open_size)
            if kernel is None:
                continue
            out = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel)
            stats["morph_open"] = int(cfg.morph_open_size)
    return out, stats


def _find_contours(
    binary: np.ndarray,
    mode: int,
    approx: int = cv2.CHAIN_APPROX_NONE,
) -> tuple[list, np.ndarray | None]:
    if binary.dtype != np.uint8:
        binary = binary.astype(np.uint8)
    contours, hierarchy = cv2.findContours(
        binary, mode, approx,
    )
    if hierarchy is not None:
        hierarchy = hierarchy[0]
    return contours, hierarchy


def _make_contour_preview(
    bgr: np.ndarray,
    contours: list[np.ndarray],
) -> np.ndarray:
    h, w = bgr.shape[:2]
    preview = np.full((h, w, 3), 255, dtype=np.uint8)
    if contours:
        cv2.drawContours(
            preview, contours, -1, (0, 0, 255), 1, lineType=cv2.LINE_AA,
        )
    return preview


def count_stroke_points(strokes: list[Stroke]) -> int:
    return sum(len(s.points_px) for s in strokes)
