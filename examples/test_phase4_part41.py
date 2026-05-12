"""Phase 4 Part 4.1 测试 — PathRefinement 基础清洗与重采样"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path import (
    remove_duplicate_points, remove_short_strokes, normalize_direction,
    resample_uniform, simplify_rdp, check_max_step, clean_and_resample_strokes,
    filter_noise_strokes,
)
from pipeline.path._shared import detect_closed
from pipeline.raster import get_default_font_path, render_char
from pipeline.vision import ContourExtractor, SkeletonExtractor

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()
FONT_SIZE = 600
PX_PER_MM = 10.0  # 600px for ~60mm char height

# ============================================================
# Part A: Synthetic path tests
# ============================================================
print("=" * 60)
print("Part A: Synthetic path tests")
print("=" * 60)

# T1: empty path
assert len(resample_uniform([], 0.5)) == 0, "T1 fail: empty"
print("T1 PASS: empty path")

# T2: single point
pts_single = [PixelPoint(10, 10)]
assert len(remove_duplicate_points(pts_single)) == 1, "T2 fail: single pt dedup"
assert len(resample_uniform(pts_single, 0.5)) == 1, "T2 fail: single pt resample"
print("T2 PASS: single point")

# T3: two-point path resample — endpoints preserved
pts2 = [PixelPoint(0, 0), PixelPoint(10, 0)]
resampled = resample_uniform(pts2, 2.0, closed=False)
assert len(resampled) >= 2, f"T3 fail: len={len(resampled)}"
assert resampled[0].x == 0.0 and resampled[-1].x == 10.0, "T3 fail: endpoints"
print(f"T3 PASS: 2-pt resampled to {len(resampled)} pts, endpoints preserved")

# T4: consecutive duplicates removed
pts_dup = [PixelPoint(0, 0), PixelPoint(0, 0), PixelPoint(1, 0),
           PixelPoint(1, 0), PixelPoint(2, 0)]
pts_clean = remove_duplicate_points(pts_dup, eps=0.5)
assert len(pts_clean) == 3, f"T4 fail: {len(pts_clean)} != 3"
print(f"T4 PASS: {len(pts_dup)} -> {len(pts_clean)} (consecutive dedup)")

# T5: non-consecutive duplicates (self-intersect) — NOT removed
pts_self = [PixelPoint(0, 0), PixelPoint(5, 5), PixelPoint(0, 0)]
pts_self_clean = remove_duplicate_points(pts_self, eps=0.5)
assert len(pts_self_clean) == 3, f"T5 fail: self-intersect removed"
print("T5 PASS: self-intersection preserved")

# T6: closed detection
tri_open = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(0, 10)]
tri_closed = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(0, 10), PixelPoint(0, 0)]
assert not detect_closed(tri_open, threshold=2.0), "T6 fail: open tri"
assert detect_closed(tri_closed, threshold=2.0), "T6 fail: closed tri"
print("T6 PASS: closed detection")

# T7: closed path uniform resample
square = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(10, 10), PixelPoint(0, 10)]
r_closed = resample_uniform(square, 2.0, closed=True)
assert len(r_closed) >= 4, f"T7 fail: len={len(r_closed)}"
# check spacing
for i in range(len(r_closed) - 1):
    dx = r_closed[i + 1].x - r_closed[i].x
    dy = r_closed[i + 1].y - r_closed[i].y
    step = math.hypot(dx, dy)
    assert step < 2.0 * 1.5, f"T7 fail: step={step:.2f} > 3.0"
print(f"T7 PASS: closed square resampled to {len(r_closed)} pts, spacing ~2.0")

# T8: zigzag RDP (simulate Zhang-Suen diagonal)
zigzag = [
    PixelPoint(0, 0), PixelPoint(1, 0), PixelPoint(1, 1),
    PixelPoint(2, 1), PixelPoint(2, 2), PixelPoint(3, 2),
    PixelPoint(3, 3), PixelPoint(4, 3), PixelPoint(4, 4), PixelPoint(5, 4),
]
simplified = simplify_rdp(zigzag, epsilon=2.0, closed=False)
assert len(simplified) < len(zigzag), f"T8 fail: no reduction ({len(simplified)} >= {len(zigzag)})"
assert simplified[0].x == 0 and simplified[-1].x == 5, "T8 fail: endpoints"
print(f"T8 PASS: zigzag {len(zigzag)} -> {len(simplified)} (RDP, epsilon=2.0)")

# T9: direction normalization (open skeleton)
right = Stroke(id="r", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0)], closed=False)
left = Stroke(id="l", source_type="skeleton",
    points_px=[PixelPoint(10, 0), PixelPoint(0, 0)], closed=False)
[norm_r, norm_l] = normalize_direction([right, left])
assert norm_r.points_px[0].x == 0, "T9 fail: rightward unchanged"
assert norm_l.points_px[0].x == 0, f"T9 fail: leftward not flipped (first.x={norm_l.points_px[0].x})"
print("T9 PASS: direction normalized (left-to-right)")

# T10: closed stroke direction preserved
closed_s = Stroke(id="c", source_type="contour",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(0, 10), PixelPoint(0, 0)],
    closed=True, is_hole=False)
[closed_norm] = normalize_direction([closed_s])
assert closed_norm.points_px[0].x == 0 and closed_norm.points_px[1].x == 10, "T10 fail: closed altered"
print("T10 PASS: closed stroke direction preserved")

# T11: check_max_step
fine = [PixelPoint(0, 0), PixelPoint(1, 0), PixelPoint(2, 0)]
s_fine = Stroke(id="f", source_type="skeleton", points_px=fine)
w1 = check_max_step([s_fine], max_step=0.5)
assert len(w1) == 2, f"T11 fail: expected 2 warnings, got {len(w1)}"
w2 = check_max_step([s_fine], max_step=2.0)
assert len(w2) == 0, f"T11 fail: expected 0 warnings, got {len(w2)}"
print(f"T11 PASS: check_max_step ({len(w1)} warnings @0.5, {len(w2)} @2.0)")

# T12: remove_short_strokes with dot_strategy
short = Stroke(id="short", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(0.5, 0)])
r_filter = remove_short_strokes([short], min_len_px=1.0, dot_strategy="filter")
assert len(r_filter) == 0, "T12 fail: filter"
r_keep = remove_short_strokes([short], min_len_px=1.0, dot_strategy="keep")
assert len(r_keep) == 1, "T12 fail: keep"
r_line = remove_short_strokes([short], min_len_px=1.0, dot_strategy="short_line", char_height_px=100)
assert len(r_line) == 1, "T12 fail: short_line"
assert r_line[0].source_type == "skeleton", "T12 fail: source_type lost"
assert len(r_line[0].points_px) == 2, "T12 fail: dot has 2 pts"
print("T12 PASS: remove_short_strokes strategies")

# T13: clean_and_resample_strokes integration
cfg = PathConfig(sample_spacing_mm=0.5, simplify_epsilon_mm=0.2, min_path_length_mm=2.0)
result, stats = clean_and_resample_strokes(
    [short, right], px_per_mm=10.0, config=cfg,
)
assert stats["output_count"] >= 1, f"T13 fail: no output"
print(f"T13 PASS: clean_and_resample integration ({stats['output_count']} strokes)")
print()

# ============================================================
# Part B: Contour integration tests
# ============================================================
print("=" * 60)
print("Part B: Contour integration (A/B/O/0/8)")
print("=" * 60)

CONTOUR_CHARS = ["A", "B", "O", "0", "8"]
ce = ContourExtractor()

for ch in CONTOUR_CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    n_raw = len(strokes_raw)
    n_inner_raw = sum(1 for s in strokes_raw if s.is_hole)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)
    raw_pts = sum(len(s.points_px) for s in strokes_raw)

    cfg = PathConfig(
        mode="contour",
        sample_spacing_mm=0.5,
        simplify_epsilon_mm=0.1,
        min_path_length_mm=2.0,
        dot_strategy="keep",
    )
    strokes_clean, stats = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg)

    n_clean = len(strokes_clean)
    n_inner_clean = sum(1 for s in strokes_clean if s.is_hole)
    n_closed_clean = sum(1 for s in strokes_clean if s.closed)
    clean_pts = sum(len(s.points_px) for s in strokes_clean)

    # Asserts
    assert n_clean == n_raw, f"{ch}: stroke count changed ({n_raw}->{n_clean})"
    assert n_inner_clean == n_inner_raw, f"{ch}: inner count changed ({n_inner_raw}->{n_inner_clean})"
    assert n_closed_clean == n_closed_raw, f"{ch}: closed count changed ({n_closed_raw}->{n_closed_clean})"
    for s in strokes_clean:
        assert len(s.points_px) > 0, f"{ch} {s.id}: empty points"
        assert s.source_type == "contour", f"{ch} {s.id}: source_type={s.source_type}"

    print(f"  {ch}: strokes={n_raw}/{n_clean} inner={n_inner_raw}/{n_inner_clean} "
          f"closed={n_closed_raw}/{n_closed_clean} pts={raw_pts}->{clean_pts}")

print("Contour integration: ALL PASSED")
print()

# ============================================================
# Part C: Skeleton integration tests
# ============================================================
print("=" * 60)
print("Part C: Skeleton integration (A/B/O/0/8/i/j)")
print("=" * 60)

SKEL_CHARS = ["A", "B", "O", "0", "8", "i", "j"]

for ch in SKEL_CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw, raw_stats = SkeletonExtractor.extract(binary, backend="zhang_suen")
    n_raw = len(strokes_raw)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)
    raw_pts = sum(len(s.points_px) for s in strokes_raw)

    cfg = PathConfig(
        mode="skeleton",
        sample_spacing_mm=0.5,
        simplify_epsilon_mm=0.3,
        min_path_length_mm=1.0,
        dot_strategy="keep",
    )
    strokes_clean, stats = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg)

    n_clean = len(strokes_clean)
    n_closed_clean = sum(1 for s in strokes_clean if s.closed)
    clean_pts = sum(len(s.points_px) for s in strokes_clean)

    # Asserts
    assert len(strokes_clean) > 0, f"{ch}: no strokes after cleaning"
    for s in strokes_clean:
        assert len(s.points_px) > 0, f"{ch} {s.id}: empty points"
        assert s.source_type == "skeleton", f"{ch} {s.id}: source_type={s.source_type}"

    # O/0 should still have closed strokes
    if ch in ("O", "0"):
        assert any(s.closed for s in strokes_clean), f"{ch}: no closed stroke after cleaning"

    # i/j component check
    if ch in ("i", "j"):
        n_comp = raw_stats.get("component_count", 0)
        n_strokes = len(strokes_clean)
        assert n_comp >= 2 or n_strokes >= 2, f"{ch}: dot/body lost (comp={n_comp}, strokes={n_strokes})"

    print(f"  {ch}: strokes={n_raw}/{n_clean} closed={n_closed_raw}/{n_closed_clean} "
          f"pts={raw_pts}->{clean_pts} ({stats['max_step_warnings']} step warns)")

print("Skeleton integration: ALL PASSED")
print()

# ============================================================
# Part D: Debug images
# ============================================================
print("=" * 60)
print("Part D: Debug images")
print("=" * 60)

# D1: Contour A
binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a_raw = ce.extract(binary_a)
cfg = PathConfig(sample_spacing_mm=0.5, simplify_epsilon_mm=0.1,
                 min_path_length_mm=2.0, dot_strategy="keep")
strokes_a_clean, _ = clean_and_resample_strokes(strokes_a_raw, px_per_mm=PX_PER_MM, config=cfg)
from pipeline.vision.contour_extractor import ContourExtractor as CE
CE.save_debug_overlay(binary_a, strokes_a_clean, str(OUT / "path_refine_contour_A.png"))
print(f"  {OUT}/path_refine_contour_A.png")

# D2: Skeleton A
skel_a, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_a, backend="zhang_suen")
strokes_skel_raw, _ = SkeletonExtractor.extract(binary_a, backend="zhang_suen")
cfg_skel = PathConfig(sample_spacing_mm=0.5, simplify_epsilon_mm=0.3,
                       min_path_length_mm=1.0, dot_strategy="keep")
strokes_skel_clean, _ = clean_and_resample_strokes(strokes_skel_raw, px_per_mm=PX_PER_MM, config=cfg_skel)
SkeletonExtractor.save_debug_strokes(binary_a, skel_a, strokes_skel_clean,
                                      str(OUT / "path_refine_skeleton_A.png"))
print(f"  {OUT}/path_refine_skeleton_A.png")

# D3: Skeleton i
binary_i = render_char("i", FONT, FONT_SIZE)
skel_i, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_i, backend="zhang_suen")
strokes_i_raw, _ = SkeletonExtractor.extract(binary_i, backend="zhang_suen")
strokes_i_clean, _ = clean_and_resample_strokes(strokes_i_raw, px_per_mm=PX_PER_MM, config=cfg_skel)
SkeletonExtractor.save_debug_strokes(binary_i, skel_i, strokes_i_clean,
                                      str(OUT / "path_refine_skeleton_i.png"))
print(f"  {OUT}/path_refine_skeleton_i.png")

print()
print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
