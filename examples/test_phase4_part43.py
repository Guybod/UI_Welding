"""Phase 4 Part 4.3 测试 — PathScheduler 路径排序与 Travel 优化"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PixelPoint, Stroke, PathConfig
from pipeline.path import (
    PathScheduler, clean_and_resample_strokes, AdaptivePathRefiner,
)
from pipeline.path._shared import dist, calc_path_length_px
from pipeline.raster import render_char, get_default_font_path
from pipeline.vision import ContourExtractor, SkeletonExtractor

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()
FONT_SIZE = 600
PX = 10.0
SCHED = PathScheduler()

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
# Part A: Synthetic path tests
# ============================================================
print("=" * 60)
print("Part A: Synthetic path tests")

# A1: Three open segments — nearest should reduce travel
s1 = Stroke(id="s1", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0)], closed=False)
s2 = Stroke(id="s2", source_type="skeleton",
    points_px=[PixelPoint(100, 0), PixelPoint(110, 0)], closed=False)
s3 = Stroke(id="s3", source_type="skeleton",
    points_px=[PixelPoint(20, 50), PixelPoint(30, 50)], closed=False)

original_travel = SCHED.calc_total_travel([s1, s2, s3])
# s1→s2: (10,0)→(100,0)=90; s2→s3: (110,0)→(20,50)=~102; total ~192

ordered, stats = SCHED.schedule([s1, s2, s3], strategy="nearest", allow_reverse=False)
opt_travel = SCHED.calc_total_travel(ordered)
assert opt_travel <= original_travel, f"A1: travel {opt_travel} > {original_travel}"
assert len(ordered) == 3, f"A1: lost strokes"
print(f"A1 PASS: travel {original_travel:.0f}->{opt_travel:.0f} px, "
      f"reduction={stats['travel_reduction_percent']}%")

# A2: allow_reverse — reverse makes travel shorter
def _make_rev_strokes():
    return [
        Stroke(id="prev", source_type="skeleton",
            points_px=[PixelPoint(0, 0), PixelPoint(0, 0)], closed=False),
        Stroke(id="rev", source_type="skeleton",
            points_px=[PixelPoint(100, 0), PixelPoint(0, 0)], closed=False),
        Stroke(id="tgt", source_type="skeleton",
            points_px=[PixelPoint(0, 10), PixelPoint(0, 20)], closed=False),
    ]

ordered_norev, s_norev = SCHED.schedule(_make_rev_strokes(), strategy="nearest", allow_reverse=False)
ordered_rev, s_rev_stats = SCHED.schedule(_make_rev_strokes(), strategy="nearest", allow_reverse=True)
assert s_rev_stats["reversed_count"] >= 1, f"A2: no reverse happened"
assert s_rev_stats["optimized_travel_px"] < s_norev["optimized_travel_px"], \
    f"A2: reverse didn't reduce travel"
print(f"A2 PASS: allow_reverse=True reduced travel, reversed={s_rev_stats['reversed_count']}")

# A3: allow_reverse=False — no reverse
ordered_nr, snr = SCHED.schedule(_make_rev_strokes(), strategy="nearest", allow_reverse=False)
assert snr["reversed_count"] == 0, f"A3: reversed when allow_reverse=False"
print(f"A3 PASS: allow_reverse=False → reversed_count={snr['reversed_count']}")

# A4: Closed stroke NOT reversed
closed_s = Stroke(id="cl", source_type="contour",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(10, 10),
               PixelPoint(0, 10), PixelPoint(0, 0)],
    closed=True, is_hole=False)
target2 = Stroke(id="t2", source_type="skeleton",
    points_px=[PixelPoint(100, 100), PixelPoint(110, 100)], closed=False)
ordered_c, sc = SCHED.schedule([closed_s, target2], strategy="nearest", allow_reverse=True)
# closed stroke must NOT be reversed
for s in ordered_c:
    if s.closed:
        assert not s.metadata.get("scheduler_reversed"), \
            f"A4: closed stroke was reversed!"
print(f"A4 PASS: closed stroke not reversed")

# A5: is_hole stroke NOT reversed
hole_s = Stroke(id="hole", source_type="contour",
    points_px=[PixelPoint(5, 5), PixelPoint(5, 8), PixelPoint(8, 8),
               PixelPoint(8, 5), PixelPoint(5, 5)],
    closed=True, is_hole=True)
ordered_h, sh = SCHED.schedule([hole_s, target2], strategy="nearest", allow_reverse=True)
for s in ordered_h:
    if s.is_hole:
        assert not s.metadata.get("scheduler_reversed"), \
            f"A5: is_hole stroke was reversed!"
print(f"A5 PASS: is_hole stroke not reversed")

# A6: calc_total_travel correctness
# Two strokes: (0,0)→(10,0) then (20,0)→(30,0)
# travel = dist((10,0), (20,0)) = 10
t1 = Stroke(id="t1", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0)], closed=False)
t2 = Stroke(id="t2", source_type="skeleton",
    points_px=[PixelPoint(20, 0), PixelPoint(30, 0)], closed=False)
travel = SCHED.calc_total_travel([t1, t2])
assert abs(travel - 10.0) < 0.01, f"A6: travel={travel} != 10"
print(f"A6 PASS: calc_total_travel = {travel:.1f} ✓")

# A7: Deterministic — same input, same order
s_a = Stroke(id="a", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0)], closed=False)
s_b = Stroke(id="b", source_type="skeleton",
    points_px=[PixelPoint(20, 0), PixelPoint(30, 0)], closed=False)
s_c = Stroke(id="c", source_type="skeleton",
    points_px=[PixelPoint(50, 0), PixelPoint(60, 0)], closed=False)
input_list = [s_a, s_b, s_c]
o1, _ = SCHED.schedule([Stroke(**s.__dict__) for s in input_list], strategy="nearest")
o2, _ = SCHED.schedule([Stroke(**s.__dict__) for s in input_list], strategy="nearest")
ids1 = [s.id for s in o1]
ids2 = [s.id for s in o2]
assert ids1 == ids2, f"A7: non-deterministic: {ids1} vs {ids2}"
print(f"A7 PASS: deterministic order {ids1}")

# A8: Points_px NOT modified (except reverse which swaps order)
s_orig = Stroke(id="orig", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(10, 0), PixelPoint(20, 0)], closed=False)
o_orig, _ = SCHED.schedule([s_orig], strategy="nearest", allow_reverse=False)
assert len(o_orig[0].points_px) == 3, f"A8: points modified"
assert o_orig[0].points_px[0].x == 0 and o_orig[0].points_px[-1].x == 20, \
    f"A8: points order changed when not reversed"
print(f"A8 PASS: points_px preserved when not reversed")

print()

# ============================================================
# Part B: Contour integration (Phase 4.1 + 4.2b + 4.3)
# ============================================================
print("=" * 60)
print("Part B: Contour A/B/O/0/8 + 4.1 + 4.2b + Scheduler")
print(f"{'char':>4s}  {'strokes':>7s}  {'inner':>5s}  {'closed':>6s}  "
      f"{'pts':>6s}  {'travel':>8s}  {'reduced':>7s}  {'reversed':>8s}")
print("-" * 60)

for ch in ["A", "B", "O", "0", "8"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw = ce.extract(binary)
    n_raw = len(strokes_raw)
    n_inner_raw = sum(1 for s in strokes_raw if s.is_hole)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)
    pts_raw = sum(len(s.points_px) for s in strokes_raw)

    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX, config=CFG_CONTOUR)
    strokes_42b, _ = AdaptivePathRefiner.refine_strokes(strokes_41, CFG_CONTOUR, px_per_mm=PX)
    pts_42 = sum(len(s.points_px) for s in strokes_42b)

    ordered, s_sched = SCHED.schedule(strokes_42b, strategy="nearest", allow_reverse=True)

    n_ord = len(ordered)
    n_inner_ord = sum(1 for s in ordered if s.is_hole)
    n_closed_ord = sum(1 for s in ordered if s.closed)
    pts_ord = sum(len(s.points_px) for s in ordered)

    assert n_ord == n_raw, f"{ch}: strokes {n_raw}→{n_ord}"
    assert n_inner_ord == n_inner_raw, f"{ch}: inner {n_inner_raw}→{n_inner_ord}"
    assert n_closed_ord == n_closed_raw, f"{ch}: closed lost"
    assert pts_ord == pts_42, f"{ch}: points modified by scheduler ({pts_42}→{pts_ord})"

    print(f"{ch:>4s}  {n_raw:>2d}/{n_ord:<2d}  "
          f"{n_inner_raw}/{n_inner_ord}   {n_closed_raw}/{n_closed_ord}    "
          f"{pts_ord:>6d}  {s_sched['original_travel_px']:>7.0f}  "
          f"{s_sched['travel_reduction_percent']:>6.1f}%  {s_sched['reversed_count']:>8d}")

print("Part B: ALL PASSED")
print()

# ============================================================
# Part C: Skeleton integration
# ============================================================
print("=" * 60)
print("Part C: Skeleton A/B/O/0/8/i/j + 4.1 + 4.2b + Scheduler")
print(f"{'char':>4s}  {'strokes':>7s}  {'closed':>6s}  "
      f"{'pts':>6s}  {'travel':>8s}  {'reduced':>7s}  {'reversed':>8s}")
print("-" * 60)

for ch in ["A", "B", "O", "0", "8", "i", "j"]:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes_raw, raw_stats = SkeletonExtractor.extract(binary, backend="zhang_suen")
    n_raw = len(strokes_raw)
    n_closed_raw = sum(1 for s in strokes_raw if s.closed)

    strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX, config=CFG_SKEL)
    strokes_42b, _ = AdaptivePathRefiner.refine_strokes(strokes_41, CFG_SKEL, px_per_mm=PX)
    pts_42 = sum(len(s.points_px) for s in strokes_42b)

    ordered, s_sched = SCHED.schedule(strokes_42b, strategy="nearest", allow_reverse=True)

    n_ord = len(ordered)
    n_closed_ord = sum(1 for s in ordered if s.closed)
    pts_ord = sum(len(s.points_px) for s in ordered)

    assert n_ord > 0, f"{ch}: no strokes"
    for s in ordered:
        assert s.source_type == "skeleton", f"{ch}: source_type changed"
    assert pts_ord == pts_42, f"{ch}: points modified ({pts_42}→{pts_ord})"

    if ch in ("O", "0"):
        assert any(s.closed for s in ordered), f"{ch}: closed lost"
    if ch in ("i", "j"):
        n_comp = raw_stats.get("component_count", 0)
        assert n_comp >= 2 or n_ord >= 2, f"{ch}: dot/body lost"

    print(f"{ch:>4s}  {n_raw:>2d}/{n_ord:<2d}  "
          f"{n_closed_raw}/{n_closed_ord}    "
          f"{pts_ord:>6d}  {s_sched['original_travel_px']:>7.0f}  "
          f"{s_sched['travel_reduction_percent']:>6.1f}%  {s_sched['reversed_count']:>8d}")

print("Part C: ALL PASSED")
print()

# ============================================================
# Part D: Strategy coverage
# ============================================================
print("=" * 60)
print("Part D: Strategy coverage")

binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a = ce.extract(binary_a)
s41, _ = clean_and_resample_strokes(strokes_a, px_per_mm=PX, config=CFG_CONTOUR)
s42b, _ = AdaptivePathRefiner.refine_strokes(s41, CFG_CONTOUR, px_per_mm=PX)

import copy
# stable
o_stable, ss = SCHED.schedule(copy.deepcopy(s42b), strategy="stable")
assert ss["strategy"] == "stable"
assert ss["input_stroke_count"] == ss["output_stroke_count"]
print(f"  stable: {ss['input_stroke_count']} strokes, travel={ss['optimized_travel_px']:.0f}px")

# nearest
o_near, sn = SCHED.schedule(copy.deepcopy(s42b), strategy="nearest")
assert sn["strategy"] == "nearest"
print(f"  nearest: {sn['input_stroke_count']} strokes, travel={sn['optimized_travel_px']:.0f}px, "
      f"reduction={sn['travel_reduction_percent']}%")

# grouped_nearest (degraded)
o_gn, sg = SCHED.schedule(copy.deepcopy(s42b), strategy="grouped_nearest")
assert sg["strategy"] == "nearest"  # degraded
assert len(sg["warnings"]) >= 1
print(f"  grouped_nearest: degraded to nearest, warning='{sg['warnings'][0][:50]}...'")

print("Part D: ALL PASSED")
print()

# ============================================================
# Part E: Debug images
# ============================================================
print("=" * 60)
print("Part E: Debug images")

import numpy as np, cv2
from pipeline.vision.contour_extractor import ContourExtractor as CE

# E1: Manual — 3 segments before/after scheduling
sched_manual = [
    Stroke(id="m1", source_type="skeleton",
        points_px=[PixelPoint(10, 10), PixelPoint(100, 10)], closed=False),
    Stroke(id="m2", source_type="skeleton",
        points_px=[PixelPoint(300, 80), PixelPoint(200, 80)], closed=False),
    Stroke(id="m3", source_type="skeleton",
        points_px=[PixelPoint(150, 50), PixelPoint(150, 120)], closed=False),
]
ordered_man, _ = SCHED.schedule(sched_manual, strategy="nearest", allow_reverse=True)

vis = np.zeros((150, 400, 3), dtype=np.uint8)
colors = [(0, 255, 0), (255, 0, 0), (0, 0, 255)]
for i, s in enumerate(ordered_man):
    c = colors[i % 3]
    for j in range(len(s.points_px) - 1):
        cv2.line(vis, (int(s.points_px[j].x), int(s.points_px[j].y)),
                 (int(s.points_px[j+1].x), int(s.points_px[j+1].y)), c, 2)
    cv2.putText(vis, f"{i}:{s.id[:4]}", (int(s.points_px[0].x), int(s.points_px[0].y) - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
    cv2.circle(vis, (int(s.points_px[0].x), int(s.points_px[0].y)), 4, (0, 255, 255), -1)
cv2.imwrite(str(OUT / "path_scheduler_manual.png"), vis)
print(f"  {OUT}/path_scheduler_manual.png")

# E2: Contour A scheduled
strokes_a = ce.extract(binary_a)
s41, _ = clean_and_resample_strokes(strokes_a, px_per_mm=PX, config=CFG_CONTOUR)
s42b, _ = AdaptivePathRefiner.refine_strokes(s41, CFG_CONTOUR, px_per_mm=PX)
ordered_a, _ = SCHED.schedule(s42b, strategy="nearest")
CE.save_debug_overlay(binary_a, ordered_a, str(OUT / "path_scheduler_contour_A.png"))
print(f"  {OUT}/path_scheduler_contour_A.png")

# E3: Skeleton A scheduled
skel_a, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_a, backend="zhang_suen")
strokes_sa_raw, _ = SkeletonExtractor.extract(binary_a, backend="zhang_suen")
s_s41, _ = clean_and_resample_strokes(strokes_sa_raw, px_per_mm=PX, config=CFG_SKEL)
s_s42b, _ = AdaptivePathRefiner.refine_strokes(s_s41, CFG_SKEL, px_per_mm=PX)
ordered_sa, _ = SCHED.schedule(s_s42b, strategy="nearest")
SkeletonExtractor.save_debug_strokes(binary_a, skel_a, ordered_sa,
                                      str(OUT / "path_scheduler_skeleton_A.png"))
print(f"  {OUT}/path_scheduler_skeleton_A.png")

# E4: Skeleton i scheduled
binary_i = render_char("i", FONT, FONT_SIZE)
skel_i, _, _, _ = SkeletonExtractor.skeletonize_binary(binary_i, backend="zhang_suen")
strokes_si_raw, _ = SkeletonExtractor.extract(binary_i, backend="zhang_suen")
s_si41, _ = clean_and_resample_strokes(strokes_si_raw, px_per_mm=PX, config=CFG_SKEL)
s_si42b, _ = AdaptivePathRefiner.refine_strokes(s_si41, CFG_SKEL, px_per_mm=PX)
ordered_si, _ = SCHED.schedule(s_si42b, strategy="nearest")
SkeletonExtractor.save_debug_strokes(binary_i, skel_i, ordered_si,
                                      str(OUT / "path_scheduler_skeleton_i.png"))
print(f"  {OUT}/path_scheduler_skeleton_i.png")

print()
print("=" * 60)
print("ALL PHASE 4.3 TESTS PASSED")
print("=" * 60)
