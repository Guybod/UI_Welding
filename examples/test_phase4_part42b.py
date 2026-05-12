"""Phase 4 Part 4.2b 测试 — Refiner 压缩率安全阈值 + 保形守卫"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path import (
    clean_and_resample_strokes, AdaptivePathRefiner, detect_corners,
)
from pipeline.path._shared import calc_path_length_px
from pipeline.raster import render_char, get_default_font_path
from pipeline.vision import ContourExtractor, SkeletonExtractor

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()
FONT_SIZE = 600
PX_PER_MM = 10.0

REFINER = AdaptivePathRefiner()

CFG_CONTOUR = PathConfig(
    mode="contour", sample_spacing_mm=0.5, simplify_epsilon_mm=0.1,
    min_path_length_mm=2.0, dot_strategy="keep", preserve_corners=True,
    corner_angle_deg=60, straight_tol_mm=0.5, curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5, contour_max_vertices=12,
)

CFG_SKEL = PathConfig(
    mode="skeleton", sample_spacing_mm=0.5, simplify_epsilon_mm=0.3,
    min_path_length_mm=1.0, dot_strategy="keep", preserve_corners=True,
    corner_angle_deg=60, straight_tol_mm=0.5, curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5, contour_max_vertices=20,
)

ce = ContourExtractor()

# ============================================================
# Part A: Contour A/B/O/0/8 — retention ratio >= 70%
# ============================================================
print("=" * 70)
print("Part A: Contour retention ratio (>=70%)")
print(f"{'char':>4s}  {'strokes':>7s}  {'inner':>5s}  {'closed':>6s}  "
      f"{'pts_41':>6s}  {'pts_42b':>6s}  {'ratio':>6s}  {'guard':>5s}  {'min_ok':>6s}")
print("-" * 70)

all_ok = True
for ch in ["A", "B", "O", "0", "8"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    n_raw = len(strokes_raw)
    n_inner_raw = sum(1 for s in strokes_raw if s.is_hole)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)

    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
    n_41 = sum(len(s.points_px) for s in strokes_41)

    strokes_42b, s42 = REFINER.refine_strokes(strokes_41, CFG_CONTOUR, px_per_mm=PX_PER_MM)
    n_42b = sum(len(s.points_px) for s in strokes_42b)

    n_42b_strokes = len(strokes_42b)
    n_inner_42b = sum(1 for s in strokes_42b if s.is_hole)
    n_closed_42b = sum(1 for s in strokes_42b if s.closed)

    ratio = n_42b / max(n_41, 1)
    guard = s42["compression_guard_triggered_count"]

    # Assertions
    assert n_42b_strokes == n_raw, f"{ch}: stroke count {n_raw}->{n_42b_strokes}"
    assert n_inner_42b == n_inner_raw, f"{ch}: inner count {n_inner_raw}->{n_inner_42b}"
    assert n_closed_42b == n_closed_raw, f"{ch}: closed lost"
    assert ratio >= 0.70, f"{ch}: retention {ratio:.1%} < 70%"

    # Per-stroke retention check
    for ps in s42["per_stroke"]:
        assert ps["retention"] >= 0.70, \
            f"{ch} {ps['stroke_id'][:6]}: per-stroke retention {ps['retention']:.1%} < 70%"

    # O/0/8: closed contour minimum
    for s in strokes_42b:
        if s.closed:
            assert len(s.points_px) >= 48, \
                f"{ch} {s.id[:6]}: closed points {len(s.points_px)} < 48"

    # Acute angle check for A
    if ch == "A":
        outer = [s for s in strokes_42b if not s.is_hole][0]
        corners = detect_corners(outer.points_px, angle_threshold_deg=60, closed=True)
        assert len(corners) >= 3, f"A outer corners: {len(corners)} < 3"

    min_ok = "OK" if all(ps["retention"] >= 0.70 for ps in s42["per_stroke"]) else "FAIL"
    print(f"{ch:>4s}  {n_raw:>2d}/{n_42b_strokes:<2d}  "
          f"{n_inner_raw}/{n_inner_42b}   {n_closed_raw}/{n_closed_42b}    "
          f"{n_41:>6d}  {n_42b:>6d}  {ratio:>5.1%}  {guard:>5d}  {min_ok:>6s}")

print("Part A: ALL PASSED" if all_ok else "Part A: FAILED")
print()

# ============================================================
# Part B: Skeleton A/B/O/0/8/i/j — retention ratio >= 60%
# ============================================================
print("=" * 70)
print("Part B: Skeleton retention ratio (>=60%)")
print(f"{'char':>4s}  {'strokes':>7s}  {'closed':>6s}  "
      f"{'pts_41':>6s}  {'pts_42b':>6s}  {'ratio':>6s}  {'guard':>5s}")
print("-" * 70)

for ch in ["A", "B", "O", "0", "8", "i", "j"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw, raw_stats = SkeletonExtractor.extract(binary, backend="zhang_suen")
    n_raw = len(strokes_raw)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)

    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=CFG_SKEL)
    n_41 = sum(len(s.points_px) for s in strokes_41)

    strokes_42b, s42 = REFINER.refine_strokes(strokes_41, CFG_SKEL, px_per_mm=PX_PER_MM)
    n_42b = sum(len(s.points_px) for s in strokes_42b)

    ratio = n_42b / max(n_41, 1)
    guard = s42["compression_guard_triggered_count"]

    # Assertions
    assert len(strokes_42b) > 0, f"{ch}: no strokes"
    for s in strokes_42b:
        assert len(s.points_px) >= 2, f"{ch} {s.id[:6]}: empty"
        assert s.source_type == "skeleton", f"{ch} {s.id[:6]}: source={s.source_type}"
    assert ratio >= 0.60, f"{ch}: retention {ratio:.1%} < 60%"

    if ch in ("O", "0"):
        assert any(s.closed for s in strokes_42b), f"{ch}: no closed"

    if ch in ("i", "j"):
        n_comp = raw_stats.get("component_count", 0)
        assert n_comp >= 2 or len(strokes_42b) >= 2, f"{ch}: dot/body lost"

    print(f"{ch:>4s}  {n_raw:>2d}/{len(strokes_42b):<2d}  "
          f"{n_closed_raw}/{sum(1 for s in strokes_42b if s.closed)}    "
          f"{n_41:>6d}  {n_42b:>6d}  {ratio:>5.1%}  {guard:>5d}")

print("Part B: ALL PASSED")
print()

# ============================================================
# Part C: Acute angle preservation
# ============================================================
print("=" * 70)
print("Part C: Acute angle preservation (A/V/W/M/Z/L)")

for ch in ["A", "V", "W", "M", "Z", "L"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
    strokes_42b, s42 = REFINER.refine_strokes(strokes_41, CFG_CONTOUR, px_per_mm=PX_PER_MM)

    assert len(strokes_42b) > 0, f"{ch}: no strokes"
    for s in strokes_42b:
        if not s.closed:
            continue
        corners = detect_corners(s.points_px, angle_threshold_deg=60, closed=True)
        assert len(corners) >= 1, f"{ch}: no corners in closed stroke"

    n_41 = sum(len(s.points_px) for s in strokes_41)
    n_42b = sum(len(s.points_px) for s in strokes_42b)
    ratio = n_42b / max(n_41, 1)
    corners_tot = s42["corners_total"]
    print(f"  {ch}: pts={n_41}→{n_42b} ({ratio:.0%}), corners={corners_tot}")

print("Part C: ALL PASSED")
print()

# ============================================================
# Part D: Synthetic shape tests (general-purpose path engine)
# ============================================================
print("=" * 70)
print("Part D: Synthetic shapes (general path engine)")

# D1: Circle — must retain >=70% and >=48 pts
circle_pts = [PixelPoint(50 + 40 * math.cos(2 * math.pi * i / 200),
                          50 + 40 * math.sin(2 * math.pi * i / 200))
              for i in range(200)]
circle_stroke = Stroke(id="circle", source_type="image",
    points_px=circle_pts, closed=True)

s41_circle, _ = clean_and_resample_strokes([circle_stroke], px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
s42_circle, s42_c = REFINER.refine_strokes(s41_circle, CFG_CONTOUR, px_per_mm=PX_PER_MM)

n_c41 = sum(len(s.points_px) for s in s41_circle)
n_c42 = sum(len(s.points_px) for s in s42_circle)
ratio_c = n_c42 / max(n_c41, 1)
assert ratio_c >= 0.70, f"D1: circle retention {ratio_c:.1%} < 70%"
assert n_c42 >= 48, f"D1: circle points {n_c42} < 48"
print(f"  D1 circle: {n_c41}→{n_c42} ({ratio_c:.0%}), {s42_c['compression_guard_triggered_count']} guards ✓")

# D2: Rectangle — must retain corners (use larger size for reliable detection)
dense_rect = []
corners_def = [(0, 0), (200, 0), (200, 200), (0, 200)]
for k in range(4):
    x1, y1 = corners_def[k]
    x2, y2 = corners_def[(k + 1) % 4]
    for t in range(21):
        frac = t / 20.0
        dense_rect.append(PixelPoint(
            x=x1 + (x2 - x1) * frac,
            y=y1 + (y2 - y1) * frac,
        ))
dense_rect_stroke = Stroke(id="dense_rect", source_type="contour",
    points_px=dense_rect, closed=True)

s41_rect, _ = clean_and_resample_strokes([dense_rect_stroke], px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
s42_rect, s42_r = REFINER.refine_strokes(s41_rect, CFG_CONTOUR, px_per_mm=PX_PER_MM)

n_r41 = sum(len(s.points_px) for s in s41_rect)
n_r42 = sum(len(s.points_px) for s in s42_rect)
ratio_r = n_r42 / max(n_r41, 1)
assert ratio_r >= 0.70, f"D2: rect retention {ratio_r:.1%} < 70%"
corners_r = detect_corners(s42_rect[0].points_px, 60, closed=True)
assert len(corners_r) >= 3, f"D2: rect corners {len(corners_r)} < 3 (at {corners_r})"
print(f"  D2 rectangle: {n_r41}→{n_r42} ({ratio_r:.0%}), corners={len(corners_r)} ✓")

# D3: W-curve (free curve, open)
w_pts = []
for i in range(100):
    t = i / 99.0
    x = t * 200
    y = 50 + 30 * math.sin(t * 4 * math.pi)
    w_pts.append(PixelPoint(x, y))
w_stroke = Stroke(id="w_free", source_type="image", points_px=w_pts, closed=False)
w_s41, _ = clean_and_resample_strokes([w_stroke], px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
w_s42, w_s42_stats = REFINER.refine_strokes(w_s41, CFG_CONTOUR, px_per_mm=PX_PER_MM)

n_w41 = sum(len(s.points_px) for s in w_s41)
n_w42 = sum(len(s.points_px) for s in w_s42)
ratio_w = n_w42 / max(n_w41, 1)
assert ratio_w >= 0.70, f"D3: w-curve retention {ratio_w:.1%} < 70%"
print(f"  D3 W-curve: {n_w41}→{n_w42} ({ratio_w:.0%}) ✓")

# D4: Spline safety — verify output has enough control points
# At 70% retention, a 200-point curve should have >= 140 control points
# This is sufficient for cubic spline interpolation (typically needs 4+ points per curve)
assert n_w42 >= 30, f"D4: w-curve < 30 pts (insufficient for spline)"
print(f"  D4 spline safety: {n_w42} pts (sufficient for spline/CRI) ✓")

print("Part D: ALL PASSED")
print()

# ============================================================
# Part E: Guard detail verification
# ============================================================
print("=" * 70)
print("Part E: Guard details")

binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a_raw = ce.extract(binary_a)
strokes_a_41, _ = clean_and_resample_strokes(strokes_a_raw, px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
_, s42_a = REFINER.refine_strokes(strokes_a_41, CFG_CONTOUR, px_per_mm=PX_PER_MM)

print(f"  Guard triggered: {s42_a['compression_guard_triggered_count']}")
print(f"  min_retention_ratio_contour: {s42_a['min_retention_ratio_contour']}")
print(f"  min_closed_points: {s42_a['min_closed_points']}")
print(f"  Warnings: {len(s42_a['warnings'])}")
for w in s42_a["warnings"]:
    print(f"    - {w}")

for ps in s42_a["per_stroke"]:
    stype = ps['source_type']
    n_b = ps['before']
    n_a = ps['after']
    ret = ps['retention']
    status = "GUARDED" if n_b > 0 and n_a / n_b < 0.75 else "OK"
    print(f"    {ps['stroke_id'][:8]:8s} {stype:8s} closed={ps['closed']} "
          f"{n_b:>4d}→{n_a:<4d} {ret:.1%} [{status}]")

print("Part E: ALL OK")
print()

# ============================================================
# Part F: Debug images
# ============================================================
print("=" * 70)
print("Part F: Debug images")

import numpy as np, cv2
from pipeline.vision.contour_extractor import ContourExtractor as CE

# F1: Contour A after Phase 4.1 + Phase 4.2b
binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a_raw = ce.extract(binary_a)
strokes_a_41, _ = clean_and_resample_strokes(strokes_a_raw, px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
strokes_a_42b, s42_a = REFINER.refine_strokes(strokes_a_41, CFG_CONTOUR, px_per_mm=PX_PER_MM)
CE.save_debug_overlay(binary_a, strokes_a_42b, str(OUT / "phase42b_contour_A.png"))
print(f"  {OUT}/phase42b_contour_A.png")

# F2: Contour O
binary_o = render_char("O", FONT, FONT_SIZE)
strokes_o_raw = ce.extract(binary_o)
strokes_o_41, _ = clean_and_resample_strokes(strokes_o_raw, px_per_mm=PX_PER_MM, config=CFG_CONTOUR)
strokes_o_42b, _ = REFINER.refine_strokes(strokes_o_41, CFG_CONTOUR, px_per_mm=PX_PER_MM)
CE.save_debug_overlay(binary_o, strokes_o_42b, str(OUT / "phase42b_contour_O.png"))
print(f"  {OUT}/phase42b_contour_O.png")

# F3: Skeleton A
skel_a, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_a, backend="zhang_suen")
strokes_sa_raw, _ = SkeletonExtractor.extract(binary_a, backend="zhang_suen")
strokes_sa_41, _ = clean_and_resample_strokes(strokes_sa_raw, px_per_mm=PX_PER_MM, config=CFG_SKEL)
strokes_sa_42b, _ = REFINER.refine_strokes(strokes_sa_41, CFG_SKEL, px_per_mm=PX_PER_MM)
SkeletonExtractor.save_debug_strokes(binary_a, skel_a, strokes_sa_42b,
                                      str(OUT / "phase42b_skeleton_A.png"))
print(f"  {OUT}/phase42b_skeleton_A.png")

# F4: Skeleton i
binary_i = render_char("i", FONT, FONT_SIZE)
skel_i, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_i, backend="zhang_suen")
strokes_si_raw, _ = SkeletonExtractor.extract(binary_i, backend="zhang_suen")
strokes_si_41, _ = clean_and_resample_strokes(strokes_si_raw, px_per_mm=PX_PER_MM, config=CFG_SKEL)
strokes_si_42b, _ = REFINER.refine_strokes(strokes_si_41, CFG_SKEL, px_per_mm=PX_PER_MM)
SkeletonExtractor.save_debug_strokes(binary_i, skel_i, strokes_si_42b,
                                      str(OUT / "phase42b_skeleton_i.png"))
print(f"  {OUT}/phase42b_skeleton_i.png")

print()
print("=" * 70)
print("ALL PHASE 4.2b TESTS PASSED")
print("=" * 70)
