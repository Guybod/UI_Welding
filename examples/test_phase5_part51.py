"""Phase 5 Part 5.1 测试 — WorkPlane + PoseMapper UV 映射"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (
    PixelPoint, PlanePoint, RobotPoint, Stroke, PathConfig,
)
from core.errors import WorkplaneError
from pipeline.mapping import WorkPlane, PoseMapper
from pipeline.path import clean_and_resample_strokes, AdaptivePathRefiner
from pipeline.raster import render_char, get_default_font_path
from pipeline.vision import ContourExtractor

FONT = get_default_font_path()
FONT_SIZE = 600
CANVAS_W = 600.0
CANVAS_H = 600.0

# ============================================================
# Part A: Flat plane tests
# ============================================================
print("=" * 60)
print("Part A: Flat plane (z same for all 3 points)")

TL = RobotPoint(0, 0, 100, -180, 0, -135)
TR = RobotPoint(200, 0, 100, -180, 0, -135)
BL = RobotPoint(0, 100, 100, -180, 0, -135)

wp = WorkPlane(TL, TR, BL)
ok, msg = wp.validate()
assert ok, f"A0: validate failed: {msg}"
print(f"A0 PASS: validate={ok}")

# A1: pixel(0,0) → robot(0,0,100)
rp = wp.map_point(PixelPoint(0, 0), CANVAS_W, CANVAS_H)
assert abs(rp.x - 0) < 0.01 and abs(rp.y - 0) < 0.01 and abs(rp.z - 100) < 0.01, \
    f"A1: {rp}"
print(f"A1 PASS: pixel(0,0)→robot(0,0,100) ✓")

# A2: pixel(600,0) → proportional to TR
rp = wp.map_point(PixelPoint(CANVAS_W, 0), CANVAS_W, CANVAS_H)
assert abs(rp.x - 200) < 0.1 and abs(rp.y) < 0.1 and abs(rp.z - 100) < 0.1, \
    f"A2: {rp}"
print(f"A2 PASS: pixel({CANVAS_W},0)→robot({rp.x:.1f},{rp.y:.1f},{rp.z:.1f}) ✓")

# A3: pixel(0,600) → robot(0,100,100)
rp = wp.map_point(PixelPoint(0, CANVAS_H), CANVAS_W, CANVAS_H)
assert abs(rp.x) < 0.1 and abs(rp.y - 100) < 0.1 and abs(rp.z - 100) < 0.1, \
    f"A3: {rp}"
print(f"A3 PASS: pixel(0,{CANVAS_H})→robot(0,100,100) ✓")

# A4: pixel(300,300) → robot(100,50,100)
rp = wp.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H)
assert abs(rp.x - 100) < 0.5 and abs(rp.y - 50) < 0.5 and abs(rp.z - 100) < 0.5, \
    f"A4: {rp}"
print(f"A4 PASS: pixel(300,300)→robot({rp.x:.1f},{rp.y:.1f},{rp.z:.1f}) ✓")

# A5: normal ≈ (0,0,1) for flat plane
assert abs(wp.normal.x) < 0.01 and abs(wp.normal.y) < 0.01 and abs(wp.normal.z - 1.0) < 0.01, \
    f"A5: normal=({wp.normal.x:.3f},{wp.normal.y:.3f},{wp.normal.z:.3f})"
print(f"A5 PASS: normal=({wp.normal.x:.2f},{wp.normal.y:.2f},{wp.normal.z:.2f}) ≈ (0,0,1) ✓")

# A6: orientation preserved (rx/ry/rz from TL)
rp = wp.map_point(PixelPoint(100, 50), CANVAS_W, CANVAS_H)
assert rp.rx == TL.rx and rp.ry == TL.ry and rp.rz == TL.rz, \
    f"A6: orientation lost: {rp.rx},{rp.ry},{rp.rz} != {TL.rx},{TL.ry},{TL.rz}"
print(f"A6 PASS: orientation preserved (rx={rp.rx},ry={rp.ry},rz={rp.rz}) ✓")

print()

# ============================================================
# Part B: Flat plane normal offset tests
# ============================================================
print("=" * 60)
print("Part B: Flat plane normal offset")

# B1: normal_offset=10 → z should be 110 (because N≈(0,0,1) for flat plane)
rp0 = wp.map_point(PixelPoint(100, 50), CANVAS_W, CANVAS_H, normal_offset_mm=0)
rp10 = wp.map_point(PixelPoint(100, 50), CANVAS_W, CANVAS_H, normal_offset_mm=10)
dz = rp10.z - rp0.z
assert abs(dz - 10.0) < 0.1, f"B1: dz={dz:.2f} != 10"
print(f"B1 PASS: offset 0→10: dz={dz:.1f} (normal=(0,0,1) → z+=10) ✓")

# B2: dx,dy should not change with normal_offset
assert abs(rp0.x - rp10.x) < 0.01 and abs(rp0.y - rp10.y) < 0.01, \
    f"B2: xy drifted"
print(f"B2 PASS: xy unchanged by normal_offset ✓")

print()

# ============================================================
# Part C: Tilted plane tests
# ============================================================
print("=" * 60)
print("Part C: Tilted plane (z values differ)")

TL2 = RobotPoint(0, 0, 100, -180, 0, -135)
TR2 = RobotPoint(200, 0, 120, -180, 0, -135)
BL2 = RobotPoint(0, 100, 90, -180, 0, -135)

wp2 = WorkPlane(TL2, TR2, BL2)
ok, msg = wp2.validate()
assert ok, f"C0: validate failed: {msg}"
print(f"C0 PASS: tilted plane validated")

# C1: normal is NOT (0,0,1)
n = wp2.normal
assert not (abs(n.x) < 0.01 and abs(n.y) < 0.01 and abs(n.z - 1.0) < 0.01), \
    f"C1: normal is (0,0,1) — plane not tilted"
print(f"C1 PASS: normal=({n.x:.4f},{n.y:.4f},{n.z:.4f}) ≠ (0,0,1) ✓")

# C2: pixel center z reflects tilted plane interpolation
rp_c = wp2.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H)
# TL.z=100, TR.z=120, BL.z=90 → center should have z between 90 and 120
assert 90 - 1 < rp_c.z < 120 + 1, f"C2: center z={rp_c.z:.2f} not in [90,120]"
print(f"C2 PASS: center robot=({rp_c.x:.1f},{rp_c.y:.1f},{rp_c.z:.1f}) in tilted plane ✓")

# C3: normal_offset along N, NOT just z change
rp_c0 = wp2.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H, normal_offset_mm=0)
rp_c10 = wp2.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H, normal_offset_mm=10)
dx, dy, dz = rp_c10.x - rp_c0.x, rp_c10.y - rp_c0.y, rp_c10.z - rp_c0.z
# 10 * N should equal the delta
d_actual = math.sqrt(dx*dx + dy*dy + dz*dz)
assert abs(d_actual - 10.0) < 0.1, f"C3: offset magnitude {d_actual:.3f} != 10"
assert abs(dx - 10 * n.x) < 0.1, f"C3: dx={dx:.3f} != 10*N.x={10*n.x:.3f}"
assert abs(dy - 10 * n.y) < 0.1, f"C3: dy={dy:.3f} != 10*N.y={10*n.y:.3f}"
assert abs(dz - 10 * n.z) < 0.2, f"C3: dz={dz:.3f} != 10*N.z={10*n.z:.3f}"
print(f"C3 PASS: offset delta=({dx:.4f},{dy:.4f},{dz:.4f}) ≈ 10*N ✓")

# C4: orientation preserved
assert rp_c10.rx == TL2.rx and rp_c10.ry == TL2.ry and rp_c10.rz == TL2.rz
print(f"C4 PASS: orientation preserved across offset ✓")

print()

# ============================================================
# Part D: Invalid 3-point tests
# ============================================================
print("=" * 60)
print("Part D: Invalid WorkPlane configurations")

# D1: TL == TR
try:
    WorkPlane(TL, TL, BL)
    assert False, "D1: should have raised"
except WorkplaneError as e:
    print(f"D1 PASS: TL==TR → WorkplaneError: {e}")

# D2: TL == BL
try:
    WorkPlane(TL, TR, TL)
    assert False, "D2: should have raised"
except WorkplaneError as e:
    print(f"D2 PASS: TL==BL → WorkplaneError: {e}")

# D3: Collinear (all on same line)
TL_coll = RobotPoint(0, 0, 100, -180, 0, -135)
TR_coll = RobotPoint(100, 0, 100, -180, 0, -135)
BL_coll = RobotPoint(200, 0, 100, -180, 0, -135)  # same y, same z
try:
    WorkPlane(TL_coll, TR_coll, BL_coll)
    assert False, "D3: collinear should have raised"
except WorkplaneError as e:
    print(f"D3 PASS: collinear → WorkplaneError: {e}")

# D4: U/V angle too small
TL_small = RobotPoint(0, 0, 100, -180, 0, -135)
TR_small = RobotPoint(100, 0, 100, -180, 0, -135)
BL_small = RobotPoint(1, 0.01, 100, -180, 0, -135)  # almost collinear with TR
try:
    WorkPlane(TL_small, TR_small, BL_small)
    assert False, "D4: small angle should have raised"
except WorkplaneError as e:
    print(f"D4 PASS: small U/V angle → WorkplaneError: {e}")

print()

# ============================================================
# Part E: Stroke mapping tests
# ============================================================
print("=" * 60)
print("Part E: Stroke mapping")

# E1: Map a simple synthetic stroke
s_test = Stroke(
    id="test1", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(300, 0), PixelPoint(600, 200)],
    closed=False, is_hole=False, glyph_id="X", group_id="g1",
    metadata={"custom": 42},
)
wp_flat = WorkPlane(TL, TR, BL)
ms = wp_flat.map_stroke(s_test, CANVAS_W, CANVAS_H)

assert ms.source_type == "skeleton", "E1: source_type lost"
assert ms.closed == False, "E1: closed changed"
assert ms.is_hole == False, "E1: is_hole changed"
assert ms.glyph_id == "X", "E1: glyph_id lost"
assert ms.group_id == "g1", "E1: group_id lost"
assert ms.metadata.get("custom") == 42, "E1: metadata lost"
assert ms.points_px == s_test.points_px, "E1: points_px modified"
assert len(ms.points_mm) == len(s_test.points_px), f"E1: points_mm={len(ms.points_mm)} != {len(s_test.points_px)}"
assert len(ms.metadata["robot_points"]) == len(s_test.points_px), \
    f"E1: robot_points={len(ms.metadata['robot_points'])} != {len(s_test.points_px)}"
print(f"E1 PASS: stroke mapped, {len(ms.points_mm)} plane points, {len(ms.metadata['robot_points'])} robot points ✓")

# E2: PoseMapper batch
cfg = PathConfig(mode="contour", sample_spacing_mm=0.5, simplify_epsilon_mm=0.1,
    min_path_length_mm=2.0, dot_strategy="keep", preserve_corners=True,
    corner_angle_deg=60, straight_tol_mm=0.5, curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5, contour_max_vertices=12)

ce = ContourExtractor()
binary_a = render_char("A", FONT, FONT_SIZE)
strokes_raw = ce.extract(binary_a)
strokes_41, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=10.0, config=cfg)
strokes_42b, _ = AdaptivePathRefiner.refine_strokes(strokes_41, cfg, px_per_mm=10.0)

mapper = PoseMapper()
mapped, stats = mapper.map_strokes(strokes_42b, wp_flat, CANVAS_W, CANVAS_H)

assert len(mapped) == len(strokes_42b), f"E2: stroke count {len(strokes_42b)}→{len(mapped)}"
for i, (orig, mp) in enumerate(zip(strokes_42b, mapped)):
    assert mp.source_type == orig.source_type, f"E2[{i}]: source_type"
    assert mp.closed == orig.closed, f"E2[{i}]: closed"
    assert mp.is_hole == orig.is_hole, f"E2[{i}]: is_hole"
    assert mp.points_px == orig.points_px, f"E2[{i}]: points_px"
    assert len(mp.points_mm) == len(orig.points_px), f"E2[{i}]: points_mm count"
    assert len(mp.metadata["robot_points"]) == len(orig.points_px), f"E2[{i}]: robot_points count"

print(f"E2 PASS: {len(mapped)} contour strokes mapped, all invariants preserved ✓")

# E3: Stats check
assert stats["orientation_mode"] == "fixed", f"E3: orientation_mode={stats['orientation_mode']}"
assert "fixed" in stats["warnings"][0], f"E3: orientation warning missing"
print(f"E3 PASS: orientation_mode={stats['orientation_mode']}, "
      f"orientation_source={stats['orientation_source']} ✓")

print()

# ============================================================
# Part F: Tilted plane stroke mapping
# ============================================================
print("=" * 60)
print("Part F: Tilted plane stroke mapping")

s_simple = Stroke(
    id="tilt1", source_type="skeleton",
    points_px=[PixelPoint(0, 0), PixelPoint(600, 600)],
    closed=False, is_hole=False,
)
ms_tilt = wp2.map_stroke(s_simple, CANVAS_W, CANVAS_H)

# First point should be at TL (0,0,100)
rp0 = ms_tilt.metadata["robot_points"][0]
assert abs(rp0.x) < 0.1 and abs(rp0.y) < 0.1 and abs(rp0.z - 100) < 0.1, \
    f"F1: first point {rp0}"
print(f"F1 PASS: first point at TL ✓")

# Last point: verify via round-trip (pixel→plane→robot)
rp_last = ms_tilt.metadata["robot_points"][-1]
pm_last = ms_tilt.points_mm[-1]
# Recompute expected from plane coords
expected_last = wp2.plane_to_robot(pm_last, normal_offset_mm=0)
assert abs(rp_last.x - expected_last.x) < 0.01, f"F2: x mismatch"
assert abs(rp_last.y - expected_last.y) < 0.01, f"F2: y mismatch"
assert abs(rp_last.z - expected_last.z) < 0.01, f"F2: z mismatch"
print(f"F2 PASS: last point matches plane_to_robot (round-trip) ✓")

# F3: tilt offset
rp0_off = wp2.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H, normal_offset_mm=15)
rp0_base = wp2.map_point(PixelPoint(300, 300), CANVAS_W, CANVAS_H, normal_offset_mm=0)
off_vec = RobotPoint(
    x=rp0_off.x - rp0_base.x, y=rp0_off.y - rp0_base.y, z=rp0_off.z - rp0_base.z,
    rx=0, ry=0, rz=0,
)
expected_off = wp2.normal * 15.0
assert abs(off_vec.x - expected_off.x) < 0.1, f"F3: offset vector"
print(f"F3 PASS: offset vector = 15*N ✓")

print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example:")
print(f"  phase: {stats['phase']}")
print(f"  strokes: {stats['input_stroke_count']}→{stats['output_stroke_count']}")
print(f"  points: {stats['input_point_count']}→{stats['mapped_point_count']}")
print(f"  workplane: {stats['workplane_width_mm']}×{stats['workplane_height_mm']} mm")
print(f"  normal: ({stats['normal_vector']['x']:.4f}, {stats['normal_vector']['y']:.4f}, {stats['normal_vector']['z']:.4f})")
print(f"  orientation: {stats['orientation_mode']}, source={stats['orientation_source']}")
print(f"  warnings: {stats['warnings']}")
print()
print("=" * 60)
print("ALL PHASE 5.1 TESTS PASSED")
print("=" * 60)
