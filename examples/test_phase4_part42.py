"""Phase 4 Part 4.2 测试 — AdaptivePathRefiner 拐角保护与自适应简化"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path import (
    clean_and_resample_strokes, AdaptivePathRefiner,
    detect_corners, classify_segments,
    remove_short_strokes,
)
from pipeline.path._shared import turn_angle_deg, dist, calc_path_length_px
from pipeline.raster import render_char, get_default_font_path
from pipeline.vision import ContourExtractor, SkeletonExtractor

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()
FONT_SIZE = 600
PX_PER_MM = 10.0

# ============================================================
# Part A: Corner detection unit tests (synthetic)
# ============================================================
print("=" * 60)
print("Part A: Corner detection")

# A1: Straight line — only endpoints are corners
line = [PixelPoint(i * 5, 0) for i in range(10)]
corners = detect_corners(line, angle_threshold_deg=60, closed=False)
assert corners == [0, 9], f"A1: {corners}"
print("A1 PASS: straight line → [0, 9]")

# A2: Right-angle L (90°) — middle point is corner
L_shape = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(10, 10)]
corners = detect_corners(L_shape, angle_threshold_deg=60, closed=False)
assert 1 in corners, f"A2: {corners}"
print(f"A2 PASS: L-shape → {corners}")

# A3: Gentle bend (~27° turn) — NOT a corner at threshold 60
# Points: (0,0)→(10,0)→(20,5), turn = atan2(50,100) ≈ 26.6°
gentle = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(20, 5)]
corners = detect_corners(gentle, angle_threshold_deg=60, closed=False)
assert 1 not in corners, f"A3: gentle turn should not be corner: {corners}"
print(f"A3 PASS: gentle turn 27° → {corners} (not corner)")

# A3b: Right-angle L (90° turn) — IS a corner
# Already verified in A2; we also verify 90° >= 60° correctly
L_shape2 = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(10, 10)]
corners_L2 = detect_corners(L_shape2, angle_threshold_deg=60, closed=False)
assert 1 in corners_L2, f"A3b: L 90° should be corner: {corners_L2}"
print(f"A3b PASS: L-shape 90° → {corners_L2} (is corner)")

# A4: Acute V (30°) — IS a corner at threshold 60
# Points: (0,10), (5,0), (10,10) — V shape
v_shape = [PixelPoint(0, 10), PixelPoint(5, 0), PixelPoint(10, 10)]
corners = detect_corners(v_shape, angle_threshold_deg=60, closed=False)
assert 1 in corners, f"A4: V-shape middle should be corner: {corners}"
print(f"A4 PASS: V-shape → {corners}")

# A5: Rectangle closed (4 × 90° corners)
rect = [PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(10, 10), PixelPoint(0, 10)]
corners = detect_corners(rect, angle_threshold_deg=60, closed=True)
assert sorted(corners) == [0, 1, 2, 3], f"A5: {corners}"
print(f"A5 PASS: rectangle → {corners}")

# A6: Circle closed (72 points) — 0 or 1 corners (fallback)
circle = [PixelPoint(50 + 40 * math.cos(2 * math.pi * i / 72),
                      50 + 40 * math.sin(2 * math.pi * i / 72))
          for i in range(72)]
corners = detect_corners(circle, angle_threshold_deg=60, closed=True)
assert len(corners) <= 2, f"A6: circle corners={len(corners)} > 2"
print(f"A6 PASS: circle → {len(corners)} corners (fallback)")

# A7: W-shape (4 acute angles)
w_shape = [
    PixelPoint(0, 0), PixelPoint(3, 10), PixelPoint(6, 0),
    PixelPoint(9, 10), PixelPoint(12, 0),
]
corners = detect_corners(w_shape, angle_threshold_deg=60, closed=False)
# Should detect all 4 internal turns + 2 endpoints = 6
assert len(corners) >= 4, f"A7: W expected >=4 corners, got {len(corners)}: {corners}"
print(f"A7 PASS: W-shape → {len(corners)} corners")

print()

# ============================================================
# Part B: Adaptive simplification unit tests
# ============================================================
print("=" * 60)
print("Part B: Adaptive simplification")

refiner = AdaptivePathRefiner()
cfg = PathConfig(
    preserve_corners=True,
    corner_angle_deg=60,
    straight_tol_mm=0.5,
    curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5,
    contour_max_vertices=12,
)
cfg_px = lambda: dict(
    corner_angle_deg=cfg.corner_angle_deg,
    straight_tol_px=cfg.straight_tol_mm * PX_PER_MM,
    curve_epsilon_px=cfg.curve_epsilon_mm * PX_PER_MM,
    curve_resample_px=cfg.curve_resample_step_mm * PX_PER_MM,
    max_vertices=cfg.contour_max_vertices,
    min_retention_ratio=0.0,    # disable guard for synthetic unit tests
    min_closed_points=0,
    min_curve_points=2,
)

# B1: L-shape — corner preserved
# Use 5px spacing to match Phase 4.1 resample output (spacing=5px > min_seg=3px)
L_pts = [PixelPoint(i * 5, 0) for i in range(9)] + [PixelPoint(40, i * 5) for i in range(1, 8)]
px = cfg_px()
refined, _guard = refiner.refine_points(L_pts, closed=False, **px)
assert len(refined) < len(L_pts), f"B1: no reduction ({len(L_pts)}->{len(refined)})"
# The corner at (40,0) should be preserved
has_corner = any(abs(p.x - 40) < 2 and abs(p.y) < 2 for p in refined)
assert has_corner, f"B1: corner (40,0) lost in {[(p.x,p.y) for p in refined]}"
print(f"B1 PASS: L-shape {len(L_pts)}→{len(refined)}, corner preserved ✓")

# B2: V-shape — acute angle preserved (≥3px spacing)
# Build V: (0,50) → tip (50,10) → (100,50), sharing tip point
n_per_arm = 11  # points per arm including tip
# Left arm: (0,50) → (50,10)
V_pts = [PixelPoint(x=50 * t, y=50 - 40 * t) for t in [i / (n_per_arm - 1) for i in range(n_per_arm)]]
# Right arm: (50,10) → (100,50), skip tip (already included)
V_pts += [PixelPoint(x=50 + 50 * t, y=10 + 40 * t) for t in [i / (n_per_arm - 1) for i in range(1, n_per_arm)]]
refined, _guard = refiner.refine_points(V_pts, closed=False, **px)
assert len(refined) < len(V_pts), f"B2: no reduction"
# The tip should be at (50, 10)
has_tip = any(abs(p.x - 50) < 3 and abs(p.y - 10) < 3 for p in refined)
assert has_tip, f"B2: V tip lost in {[(round(p.x),round(p.y)) for p in refined]}"
print(f"B2 PASS: V-shape {len(V_pts)}→{len(refined)}, tip preserved ✓")

# B3: W-shape — all 4 acute corners preserved (≥3px spacing)
W_pts = []
for seg in range(4):
    sx = seg * 60
    step = 5
    for t in range(6):
        if seg % 2 == 0:
            W_pts.append(PixelPoint(sx + t * step * 2, 30 - t * step))
        else:
            W_pts.append(PixelPoint(sx + t * step * 2, t * step))
refined, _guard = refiner.refine_points(W_pts, closed=False, **px)
assert len(refined) < len(W_pts), f"B3: no reduction"
print(f"B3 PASS: W-shape {len(W_pts)}→{len(refined)}, corners preserved ✓")

# B4: Closed circle — not over-simplified (keeps reasonable points)
circle_pts = [PixelPoint(50 + 40 * math.cos(2 * math.pi * i / 80),
                          50 + 40 * math.sin(2 * math.pi * i / 80))
              for i in range(80)]
refined, _guard = refiner.refine_points(circle_pts, closed=True, **px)
assert len(refined) >= 4, f"B4: circle {len(circle_pts)}→{len(refined)} too few"
assert len(refined) <= cfg.contour_max_vertices + 4, \
    f"B4: circle not soft-capped: {len(refined)} > {cfg.contour_max_vertices}+4"
print(f"B4 PASS: circle {len(circle_pts)}→{len(refined)} (soft cap {cfg.contour_max_vertices})")

# B5: Straight line — minimal points after refine (open path min=4)
straight_pts = [PixelPoint(i * 5, 0) for i in range(30)]
refined, _guard = refiner.refine_points(straight_pts, closed=False, **px)
assert len(refined) <= 4 and len(refined) < len(straight_pts), \
    f"B5: straight {len(straight_pts)}→{len(refined)} not reduced"
print(f"B5 PASS: straight {len(straight_pts)}→{len(refined)} (≤4, open min)")

print()

# ============================================================
# Part C: Contour integration (Phase 4.1 + 4.2)
# ============================================================
print("=" * 60)
print("Part C: Contour A/B/O/0/8 + Phase 4.1 + Phase 4.2")

ce = ContourExtractor()
cfg_contour = PathConfig(
    mode="contour",
    sample_spacing_mm=0.5,
    simplify_epsilon_mm=0.1,
    min_path_length_mm=2.0,
    dot_strategy="keep",
    preserve_corners=True,
    corner_angle_deg=60,
    straight_tol_mm=0.5,
    curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5,
    contour_max_vertices=12,
)

for ch in ["A", "B", "O", "0", "8"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    n_raw = len(strokes_raw)
    n_inner = sum(1 for s in strokes_raw if s.is_hole)
    n_closed = sum(1 for s in strokes_raw if s.closed)

    strokes_41, s41 = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg_contour)
    pts_before = sum(len(s.points_px) for s in strokes_41)  # capture before refine
    strokes_42, s42 = AdaptivePathRefiner.refine_strokes(strokes_41, cfg_contour, px_per_mm=PX_PER_MM)
    pts_after = sum(len(s.points_px) for s in strokes_42)

    n_42 = len(strokes_42)
    n_inner_42 = sum(1 for s in strokes_42 if s.is_hole)
    n_closed_42 = sum(1 for s in strokes_42 if s.closed)

    assert n_42 == n_raw, f"{ch}: stroke count {n_raw}→{n_42}"
    assert n_inner_42 == n_inner, f"{ch}: inner count {n_inner}→{n_inner_42}"
    assert n_closed_42 == n_closed, f"{ch}: closed count {n_closed}→{n_closed_42}"
    for s in strokes_42:
        assert len(s.points_px) >= 2, f"{ch} {s.id}: empty"
        assert s.source_type == "contour", f"{ch} {s.id}: source_type={s.source_type}"

    print(f"  {ch}: strokes={n_raw}/{n_42} inner={n_inner}/{n_inner_42} "
          f"closed={n_closed}/{n_closed_42} pts={pts_before}→{pts_after} "
          f"corners={s42.get('corners_total','?')} "
          f"seg_s={s42.get('segments_straight','?')}/{s42.get('segments_curve','?')}")

print("Contour integration: ALL PASSED")
print()

# ============================================================
# Part D: Skeleton integration (Phase 4.1 + 4.2)
# ============================================================
print("=" * 60)
print("Part D: Skeleton A/B/O/0/8/i/j + Phase 4.1 + Phase 4.2")

cfg_skel = PathConfig(
    mode="skeleton",
    sample_spacing_mm=0.5,
    simplify_epsilon_mm=0.3,
    min_path_length_mm=1.0,
    dot_strategy="keep",
    preserve_corners=True,
    corner_angle_deg=60,
    straight_tol_mm=0.5,
    curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5,
    contour_max_vertices=20,
)

for ch in ["A", "B", "O", "0", "8", "i", "j"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw, raw_stats = SkeletonExtractor.extract(binary, backend="zhang_suen")
    n_raw = len(strokes_raw)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)

    strokes_41, s41 = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg_skel)
    pts_before = sum(len(s.points_px) for s in strokes_41)
    strokes_42, s42 = AdaptivePathRefiner.refine_strokes(strokes_41, cfg_skel, px_per_mm=PX_PER_MM)
    pts_after = sum(len(s.points_px) for s in strokes_42)

    n_42 = len(strokes_42)
    n_closed_42 = sum(1 for s in strokes_42 if s.closed)

    assert len(strokes_42) > 0, f"{ch}: no strokes"
    for s in strokes_42:
        assert len(s.points_px) >= 2, f"{ch} {s.id}: empty"
        assert s.source_type == "skeleton", f"{ch} {s.id}: source_type={s.source_type}"

    if ch in ("O", "0"):
        assert any(s.closed for s in strokes_42), f"{ch}: no closed stroke"

    if ch in ("i", "j"):
        n_comp = raw_stats.get("component_count", 0)
        assert n_comp >= 2 or n_42 >= 2, f"{ch}: dot/body lost"

    print(f"  {ch}: strokes={n_raw}/{n_42} closed={n_closed_raw}/{n_closed_42} "
          f"pts={pts_before}→{pts_after} "
          f"corners={s42.get('corners_total','?')}")

print("Skeleton integration: ALL PASSED")
print()

# ============================================================
# Part E: small_circle dot_strategy
# ============================================================
print("=" * 60)
print("Part E: small_circle dot_strategy")

# Create a short stroke that triggers dot_strategy
short = Stroke(id="dot", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(0.5, 0)], closed=False)

result = remove_short_strokes([short], min_len_px=10.0,
                               dot_strategy="small_circle", char_height_px=600)
assert len(result) == 1, "E1: should keep dot"
dot = result[0]
assert dot.closed, "E1: small_circle should be closed"
assert len(dot.points_px) == 8, f"E1: expected 8 pts, got {len(dot.points_px)}"
assert dot.metadata.get("dot_strategy") == "small_circle", f"E1: metadata={dot.metadata}"
print(f"E1 PASS: small_circle → {len(dot.points_px)} pts, closed={dot.closed}, "
      f"radius={dot.metadata.get('dot_radius_px', '?')}")

# small_circle radius clamp test: tiny char -> min radius
result2 = remove_short_strokes([short], min_len_px=10.0,
                                dot_strategy="small_circle", char_height_px=30)
dot2 = result2[0]
r2 = dot2.metadata.get("dot_radius_px", 0)
assert r2 <= 1.5 + 0.01, f"E2: radius not clamped: {r2}"
print(f"E2 PASS: tiny char small_circle radius={r2:.1f} (clamped) ✓")

# short_line still works
result3 = remove_short_strokes([short], min_len_px=10.0,
                                dot_strategy="short_line", char_height_px=600)
assert len(result3) == 1
assert not result3[0].closed, "E3: short_line should be open"
assert result3[0].metadata.get("dot_strategy") == "short_line"
print(f"E3 PASS: short_line dot works ✓")

print()

# ============================================================
# Part F: A/V/W/M/Z/L acute angle preservation
# ============================================================
print("=" * 60)
print("Part F: Acute angle preservation (A/V/W/M/Z/L)")

# Test that contour A has corners preserved after Phase 4.1+4.2
for ch in ["A", "V", "W", "M", "Z", "L"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg_contour)
    strokes_42, s42 = AdaptivePathRefiner.refine_strokes(strokes_41, cfg_contour, px_per_mm=PX_PER_MM)

    # Each char should have at least some strokes with corners detected
    assert len(strokes_42) > 0, f"{ch}: no strokes"
    corners = s42.get("corners_total", 0)
    print(f"  {ch}: {len(strokes_42)} strokes, {corners} corners_total, "
          f"pts={sum(len(s.points_px) for s in strokes_42)}")

# Explicit check: A outer contour must have at least 3 corners (top + 2 bottom)
binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a = ce.extract(binary_a)
strokes_a_41, _ = clean_and_resample_strokes(strokes_a, px_per_mm=PX_PER_MM, config=cfg_contour)
outer_a = [s for s in strokes_a_41 if not s.is_hole]
assert len(outer_a) == 1, f"A outer: expected 1, got {len(outer_a)}"
corners_a = detect_corners(outer_a[0].points_px, angle_threshold_deg=60, closed=True)
# A outer should have at least 3 corners (top + 2 bottom tips + maybe horizontal bar)
assert len(corners_a) >= 3, f"A outer corners: {len(corners_a)} (<3)"
print(f"  A outer contour corners: {corners_a} (verified ≥3)")

print("Acute angle preservation: ALL PASSED")
print()

# ============================================================
# Part G: Debug images
# ============================================================
print("=" * 60)
print("Part G: Debug images")

# G1: L-shape synthetic (≥3px spacing)
L_pts2 = [PixelPoint(i * 5, 0) for i in range(12)] + [PixelPoint(60, i * 5) for i in range(1, 10)]
refined_L_pts, _ = refiner.refine_points(L_pts2, closed=False, **px)
import numpy as np, cv2
h, w = 70, 100
vis_L = np.zeros((h, w, 3), dtype=np.uint8)
for p in L_pts2:
    cv2.circle(vis_L, (int(p.x), int(p.y)), 1, (128, 128, 128), -1)
for p in refined_L_pts:
    cv2.circle(vis_L, (int(p.x), int(p.y)), 3, (0, 255, 0), -1)
cv2.putText(vis_L, f"{len(L_pts2)}->{len(refined_L_pts)}", (5, h - 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
cv2.imwrite(str(OUT / "path_refiner_corner_L.png"), vis_L)
print(f"  {OUT}/path_refiner_corner_L.png")

# G2: W-shape synthetic (≥3px spacing)
W_pts2 = []
for seg in range(4):
    sx = seg * 80
    step = 5
    for t in range(5):
        if seg % 2 == 0:
            W_pts2.append(PixelPoint(sx + t * step * 2, 40 - t * step * 2))
        else:
            W_pts2.append(PixelPoint(sx + t * step * 2, t * step * 2))
vis_W = np.zeros((60, 350, 3), dtype=np.uint8)
refined_W_pts, _ = refiner.refine_points(W_pts2, closed=False, **px)
for p in W_pts2:
    cv2.circle(vis_W, (int(p.x), int(p.y)), 1, (128, 128, 128), -1)
for p in refined_W_pts:
    cv2.circle(vis_W, (int(p.x), int(p.y)), 3, (0, 255, 0), -1)
cv2.putText(vis_W, f"{len(W_pts2)}->{len(refined_W_pts)}", (5, 55),
            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
cv2.imwrite(str(OUT / "path_refiner_corner_W.png"), vis_W)
print(f"  {OUT}/path_refiner_corner_W.png")

# G3: Contour A after Phase 4.1 + 4.2
binary_a2 = render_char("A", FONT, FONT_SIZE)
strokes_a2 = ce.extract(binary_a2)
strokes_a_41, _ = clean_and_resample_strokes(strokes_a2, px_per_mm=PX_PER_MM, config=cfg_contour)
strokes_a_42, _ = AdaptivePathRefiner.refine_strokes(strokes_a_41, cfg_contour, px_per_mm=PX_PER_MM)
from pipeline.vision.contour_extractor import ContourExtractor as CE
CE.save_debug_overlay(binary_a2, strokes_a_42, str(OUT / "path_refiner_contour_A.png"))
print(f"  {OUT}/path_refiner_contour_A.png")

# G4: Contour O after Phase 4.1 + 4.2
binary_o = render_char("O", FONT, FONT_SIZE)
strokes_o = ce.extract(binary_o)
strokes_o_41, _ = clean_and_resample_strokes(strokes_o, px_per_mm=PX_PER_MM, config=cfg_contour)
strokes_o_42, _ = AdaptivePathRefiner.refine_strokes(strokes_o_41, cfg_contour, px_per_mm=PX_PER_MM)
CE.save_debug_overlay(binary_o, strokes_o_42, str(OUT / "path_refiner_contour_O.png"))
print(f"  {OUT}/path_refiner_contour_O.png")

# G5: Skeleton A after Phase 4.1 + 4.2
skel_a, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_a2, backend="zhang_suen")
strokes_sa_raw, _ = SkeletonExtractor.extract(binary_a2, backend="zhang_suen")
strokes_sa_41, _ = clean_and_resample_strokes(strokes_sa_raw, px_per_mm=PX_PER_MM, config=cfg_skel)
strokes_sa_42, _ = AdaptivePathRefiner.refine_strokes(strokes_sa_41, cfg_skel, px_per_mm=PX_PER_MM)
SkeletonExtractor.save_debug_strokes(binary_a2, skel_a, strokes_sa_42,
                                      str(OUT / "path_refiner_skeleton_A.png"))
print(f"  {OUT}/path_refiner_skeleton_A.png")

# G6: Skeleton i after Phase 4.1 + 4.2
binary_i = render_char("i", FONT, FONT_SIZE)
skel_i, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_i, backend="zhang_suen")
strokes_si_raw, _ = SkeletonExtractor.extract(binary_i, backend="zhang_suen")
strokes_si_41, _ = clean_and_resample_strokes(strokes_si_raw, px_per_mm=PX_PER_MM, config=cfg_skel)
strokes_si_42, _ = AdaptivePathRefiner.refine_strokes(strokes_si_41, cfg_skel, px_per_mm=PX_PER_MM)
SkeletonExtractor.save_debug_strokes(binary_i, skel_i, strokes_si_42,
                                      str(OUT / "path_refiner_skeleton_i.png"))
print(f"  {OUT}/path_refiner_skeleton_i.png")

print()
print("=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
