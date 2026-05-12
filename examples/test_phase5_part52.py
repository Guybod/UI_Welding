"""Phase 5 Part 5.2 测试 — Workspace Mapping 兼容模式"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (
    PixelPoint, PlanePoint, RobotPoint, Stroke,
)
from core.errors import WorkplaneError
from pipeline.mapping import WorkPlane, PoseMapper

# ============================================================
# Part A: from_ortho tests
# ============================================================
print("=" * 60)
print("Part A: from_ortho")

origin = RobotPoint(0, 0, 100, -180, 0, -135)
wp = WorkPlane.from_ortho(origin, pixel_per_mm=10, canvas_w=1000, canvas_h=500)

assert wp.mapping_mode == "ortho", f"A0: mode={wp.mapping_mode}"
assert abs(wp.width_mm - 100) < 0.01, f"A0: width={wp.width_mm}"
assert abs(wp.height_mm - 50) < 0.01, f"A0: height={wp.height_mm}"
print(f"A0 PASS: ortho mode, {wp.width_mm}×{wp.height_mm} mm")

# A1: pixel(0,0) → robot(0,0,100)
rp = wp.map_point(PixelPoint(0, 0), 1000, 500)
assert abs(rp.x) < 0.01 and abs(rp.y) < 0.01 and abs(rp.z - 100) < 0.01, f"A1: {rp}"
print(f"A1 PASS: pixel(0,0)→robot(0,0,100) ✓")

# A2: pixel(1000,0) → robot(100,0,100)
rp = wp.map_point(PixelPoint(1000, 0), 1000, 500)
assert abs(rp.x - 100) < 0.1 and abs(rp.y) < 0.1, f"A2: {rp}"
print(f"A2 PASS: pixel(1000,0)→robot(100,0,100) ✓")

# A3: pixel(0,500) → robot(0,50,100)
rp = wp.map_point(PixelPoint(0, 500), 1000, 500)
assert abs(rp.y - 50) < 0.1, f"A3: {rp}"
print(f"A3 PASS: pixel(0,500)→robot(0,50,100) ✓")

# A4: normal_offset along N=(0,0,1)
rp0 = wp.map_point(PixelPoint(500, 250), 1000, 500, normal_offset_mm=0)
rp10 = wp.map_point(PixelPoint(500, 250), 1000, 500, normal_offset_mm=10)
assert abs(rp10.z - rp0.z - 10) < 0.01, f"A4: dz={rp10.z-rp0.z}"
print(f"A4 PASS: normal_offset along N=(0,0,1) ✓")

# A5: orientation preserved
assert rp10.rx == origin.rx and rp10.ry == origin.ry and rp10.rz == origin.rz
print(f"A5 PASS: orientation preserved ✓")

# A6: from_ortho with custom orientation_source
orient_custom = RobotPoint(0, 0, 0, 90, 45, 0)
wp_custom = WorkPlane.from_ortho(origin, 10, 1000, 500, orientation_source=orient_custom)
rp_c = wp_custom.map_point(PixelPoint(0, 0), 1000, 500)
assert rp_c.rx == 90 and rp_c.ry == 45, f"A6: orient={rp_c.rx},{rp_c.ry}"
print(f"A6 PASS: custom orientation_source ✓")

print()

# ============================================================
# Part B: from_four_corners coplanar test
# ============================================================
print("=" * 60)
print("Part B: from_four_corners (coplanar)")

TL = RobotPoint(0, 0, 100, -180, 0, -135)
TR = RobotPoint(200, 0, 100, -180, 0, -135)
BL = RobotPoint(0, 100, 100, -180, 0, -135)
BR = RobotPoint(200, 100, 100, -180, 0, -135)  # perfectly coplanar

wp4 = WorkPlane.from_four_corners(TL, TR, BL, BR)
assert wp4.mapping_mode == "four_corners", f"B0: mode={wp4.mapping_mode}"
err = wp4.compat_metadata["br_plane_error_mm"]
assert abs(err) < 0.01, f"B1: br_plane_error={err:.4f} != 0"
print(f"B1 PASS: coplanar BR, error={err:.6f} mm ✓")

# Verify it works like a normal WorkPlane
rp = wp4.map_point(PixelPoint(300, 300), 600, 600)
assert abs(rp.x - 100) < 0.5 and abs(rp.y - 50) < 0.5, f"B2: {rp}"
print(f"B2 PASS: four_corners maps correctly ✓")

# "br_warning" should NOT be present
assert "br_warning" not in wp4.compat_metadata, f"B3: unexpected br_warning"
print(f"B3 PASS: no false br_warning ✓")

print()

# ============================================================
# Part C: from_four_corners BR deviation test
# ============================================================
print("=" * 60)
print("Part C: from_four_corners (BR deviates)")

BR_bad = RobotPoint(200, 100, 105, -180, 0, -135)  # z=105 instead of 100: 5mm off

wp_bad = WorkPlane.from_four_corners(TL, TR, BL, BR_bad, br_tolerance_mm=5.0)
err = wp_bad.compat_metadata["br_plane_error_mm"]
assert abs(err - 5.0) < 0.1, f"C1: br_plane_error={err:.4f} != 5.0"
print(f"C1 PASS: BR error={err:.2f} mm (expected 5.0) ✓")

# At exactly 5.0mm tolerance, should NOT warn (not >)
assert "br_warning" not in wp_bad.compat_metadata, \
    f"C2: warning at exact tolerance"
print(f"C2 PASS: no warning at exact tolerance ✓")

# Test with tolerance=3.0: 5.0 > 3.0 → should warn
wp_warn = WorkPlane.from_four_corners(TL, TR, BL, BR_bad, br_tolerance_mm=3.0)
assert "br_warning" in wp_warn.compat_metadata, \
    f"C3: missing br_warning for 5mm > 3mm tolerance"
print(f"C3 PASS: br_warning='{wp_warn.compat_metadata['br_warning'][:60]}...' ✓")

print()

# ============================================================
# Part D: Phase 5.1 regression
# ============================================================
print("=" * 60)
print("Part D: Phase 5.1 regression")

# Flat plane (uv mode)
TL_f = RobotPoint(0, 0, 100, -180, 0, -135)
TR_f = RobotPoint(200, 0, 100, -180, 0, -135)
BL_f = RobotPoint(0, 100, 100, -180, 0, -135)
wp_uv = WorkPlane(TL_f, TR_f, BL_f)
assert wp_uv.mapping_mode == "uv", f"D0: mode={wp_uv.mapping_mode}"

rp = wp_uv.map_point(PixelPoint(0, 0), 600, 600)
assert abs(rp.x) < 0.01 and abs(rp.y) < 0.01 and abs(rp.z - 100) < 0.01, f"D1: {rp}"
print(f"D1 PASS: uv flat plane ✓")

# Tilted plane
TL_t = RobotPoint(0, 0, 100, -180, 0, -135)
TR_t = RobotPoint(200, 0, 120, -180, 0, -135)
BL_t = RobotPoint(0, 100, 90, -180, 0, -135)
wp_tilt = WorkPlane(TL_t, TR_t, BL_t)
n = wp_tilt.normal
assert not (abs(n.x) < 0.01 and abs(n.y) < 0.01), f"D2: normal is (0,0,1)"
print(f"D2 PASS: tilted plane normal ≠ (0,0,1) ✓")

# Illegal points
try:
    WorkPlane(TL_f, TL_f, BL_f)
    assert False, "D3"
except WorkplaneError:
    print(f"D3 PASS: TL==TR raises WorkplaneError ✓")

print()

# ============================================================
# Part E: Stroke mapping with compat modes
# ============================================================
print("=" * 60)
print("Part E: Stroke mapping with compat modes")

s = Stroke(
    id="compat1", source_type="contour",
    points_px=[PixelPoint(0, 0), PixelPoint(500, 250), PixelPoint(1000, 500)],
    closed=False, is_hole=True, glyph_id="X", group_id="g1",
    metadata={"key": "val"},
)

# ortho mode
ms_ortho = wp.map_stroke(s, 1000, 500)
assert ms_ortho.source_type == "contour", "E1: source_type"
assert ms_ortho.is_hole == True, "E1: is_hole"
assert ms_ortho.glyph_id == "X", "E1: glyph_id"
assert ms_ortho.metadata["key"] == "val", "E1: metadata"
assert ms_ortho.points_px == s.points_px, "E1: points_px modified"
assert len(ms_ortho.metadata["robot_points"]) == 3, f"E1: robot_points={len(ms_ortho.metadata['robot_points'])}"
print(f"E1 PASS: ortho stroke mapped ✓")

# four_corners mode
ms_4c = wp4.map_stroke(s, 600, 600)
assert len(ms_4c.metadata["robot_points"]) == 3, f"E2: robot_points"
print(f"E2 PASS: four_corners stroke mapped ✓")

# PoseMapper with ortho
mapper = PoseMapper()
mapped, stats = mapper.map_strokes([s], wp, 1000, 500)
assert stats["mapping_mode"] == "ortho", f"E3: mode={stats['mapping_mode']}"
assert stats["compatibility_mode_used"] == True, f"E3: compat flag"
print(f"E3 PASS: PoseMapper mode={stats['mapping_mode']}, compat={stats['compatibility_mode_used']} ✓")

# PoseMapper with four_corners + BR warning
_, stats_w = mapper.map_strokes([s], wp_warn, 600, 600)
assert stats_w["mapping_mode"] == "four_corners"
assert "br_warning" in stats_w["compat_metadata"]
print(f"E4 PASS: BR warning in stats ✓")

print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example (ortho):")
for k, v in stats.items():
    if k != "compat_metadata":
        print(f"  {k}: {v}")
print(f"  compat_metadata: {stats['compat_metadata']}")
print()
print("Stats example (four_corners with BR deviation):")
print(f"  mapping_mode: {stats_w['mapping_mode']}")
print(f"  compatibility_mode_used: {stats_w['compatibility_mode_used']}")
print(f"  compat_metadata: {stats_w['compat_metadata']}")
print(f"  warnings: {stats_w['warnings']}")
print()
print("=" * 60)
print("ALL PHASE 5.2 TESTS PASSED")
print("=" * 60)
