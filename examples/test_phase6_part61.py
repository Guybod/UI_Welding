"""Phase 6 Part 6.1 测试 — WeldingProcessPlanner 工艺段生成"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (
    RobotPoint, Stroke,
    WeldingProcessConfig, WorkspaceConfig,
)
from pipeline.process import WeldingProcessPlanner
from pipeline.mapping import WorkPlane

planner = WeldingProcessPlanner()

# ============================================================
# Part A: Open stroke
# ============================================================
print("=" * 60)
print("Part A: Open stroke")

pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(10, 0, 100, -180, 0, -135),
    RobotPoint(20, 5, 100, -180, 0, -135),
    RobotPoint(30, 5, 100, -180, 0, -135),
]
s_open = Stroke(id="open1", source_type="skeleton",
    points_px=[], closed=False,
    metadata={"robot_points": pts})

cfg = WeldingProcessConfig(
    lead_in_length_mm=3.0, lead_out_length_mm=3.0,
    overlap_length_mm=5.0, weld_point_spacing_mm=0.5,
    travel_speed_mm_s=80.0, weld_speed_mm_s=30.0,
)

segments, stats = planner.plan([s_open], cfg)
types = [s.type for s in segments]
assert "travel" in types, f"A1: no travel in {types}"
assert "lead_in" in types, f"A1: no lead_in"
assert "weld" in types, f"A1: no weld"
assert "lead_out" in types, f"A1: no lead_out"
assert "retreat" in types, f"A1: no retreat"
assert "overlap" not in types, f"A1: open stroke has overlap!"
print(f"A1 PASS: open stroke types={types}")

for seg in segments:
    if seg.type in ("lead_in", "weld", "lead_out"):
        assert seg.arc_enabled, f"A2: {seg.type} arc_enabled=False"
    if seg.type in ("travel", "retreat"):
        assert not seg.arc_enabled, f"A2: {seg.type} arc_enabled=True"
print(f"A2 PASS: arc_enabled correct")

for seg in segments:
    assert seg.stroke_id == "open1", f"A3: wrong stroke_id={seg.stroke_id}"
print(f"A3 PASS: stroke_id correct")

assert stats["overlap_count"] == 0, f"A4: overlap_count={stats['overlap_count']}"
assert stats["weld_count"] == 1
print(f"A4 PASS: counts: weld={stats['weld_count']}, overlap={stats['overlap_count']}")
print()

# ============================================================
# Part B: Closed stroke
# ============================================================
print("=" * 60)
print("Part B: Closed stroke")

sq_pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(50, 0, 100, -180, 0, -135),
    RobotPoint(50, 50, 100, -180, 0, -135),
    RobotPoint(0, 50, 100, -180, 0, -135),
    RobotPoint(0, 0, 100, -180, 0, -135),
]
s_closed = Stroke(id="closed1", source_type="contour",
    points_px=[], closed=True, is_hole=False,
    metadata={"robot_points": sq_pts})

segments_c, stats_c = planner.plan([s_closed], cfg)
types_c = [s.type for s in segments_c]
assert "overlap" in types_c, f"B1: closed stroke missing overlap in {types_c}"
assert stats_c["overlap_count"] == 1
print(f"B1 PASS: closed types={types_c}")

ov_seg = [s for s in segments_c if s.type == "overlap"][0]
assert len(ov_seg.points) >= 2, f"B2: overlap has {len(ov_seg.points)} points"
assert ov_seg.arc_enabled, f"B2: overlap arc_enabled=False"
print(f"B2 PASS: overlap {len(ov_seg.points)} pts, arc_enabled=True")
print()

# ============================================================
# Part C: Missing robot_points
# ============================================================
print("=" * 60)
print("Part C: Missing robot_points")

s_bad = Stroke(id="bad1", source_type="skeleton",
    points_px=[], closed=False, metadata={})

try:
    planner.plan([s_bad], cfg)
    assert False, "C1: should have raised"
except ValueError as e:
    assert "robot_points" in str(e), f"C1: wrong error: {e}"
    print(f"C1 PASS: ValueError: {e}")

s_empty = Stroke(id="empty1", source_type="skeleton",
    points_px=[], closed=False,
    metadata={"robot_points": []})
try:
    planner.plan([s_empty], cfg)
    assert False, "C2: should have raised"
except ValueError as e:
    print(f"C2 PASS: empty robot_points -> ValueError")
print()

# ============================================================
# Part D: Multi-stroke
# ============================================================
print("=" * 60)
print("Part D: Multi-stroke")

s1 = Stroke(id="ms1", source_type="contour",
    points_px=[], closed=True,
    metadata={"robot_points": sq_pts})
s2 = Stroke(id="ms2", source_type="skeleton",
    points_px=[], closed=False,
    metadata={"robot_points": pts})

segments_m, stats_m = planner.plan([s1, s2], cfg)
assert stats_m["generated_segment_count"] >= 8, \
    f"D1: only {stats_m['generated_segment_count']} segments"
assert stats_m["overlap_count"] == 1
assert stats_m["weld_count"] == 2
stroke_ids = set(seg.stroke_id for seg in segments_m)
assert stroke_ids == {"ms1", "ms2"}, f"D2: stroke_ids={stroke_ids}"
print(f"D1 PASS: {stats_m['generated_segment_count']} segments from 2 strokes")
print(f"D2 PASS: stroke_ids correct")

for sid in ["ms1", "ms2"]:
    seg_order = [s.type for s in segments_m if s.stroke_id == sid]
    ti = seg_order.index("travel") if "travel" in seg_order else -1
    wi = seg_order.index("weld") if "weld" in seg_order else -1
    ri = seg_order.index("retreat") if "retreat" in seg_order else -1
    assert ti < wi < ri, f"D3: wrong segment order for {sid}: {seg_order}"
print(f"D3 PASS: segment order travel<weld<retreat")
print()

# ============================================================
# Part E: WorkPlane offset metadata
# ============================================================
print("=" * 60)
print("Part E: WorkPlane offset metadata")

TL = RobotPoint(0, 0, 100, -180, 0, -135)
TR = RobotPoint(200, 0, 100, -180, 0, -135)
BL = RobotPoint(0, 100, 100, -180, 0, -135)
wp = WorkPlane(TL, TR, BL)
wcfg = WorkspaceConfig(normal_travel_offset_mm=15.0, normal_work_offset_mm=5.0)

segments_wp, stats_wp = planner.plan(
    [s_open], cfg, workplane=wp, workspace_cfg=wcfg,
)

# All ProcessSegment.points stay at base plane (z=100).
# normal_offset_mm stores the intended process height; Phase 7 Export applies the offset.
travel_seg = [s for s in segments_wp if s.type == "travel"][0]
weld_seg = [s for s in segments_wp if s.type == "weld"][0]
assert abs(travel_seg.points[0].z - 100) < 0.1, \
    f"E1: travel z={travel_seg.points[0].z:.1f}"
assert abs(weld_seg.points[0].z - 100) < 0.1, \
    f"E1: weld z={weld_seg.points[0].z:.1f}"
assert travel_seg.normal_offset_mm == 15.0, \
    f"E1: travel offset={travel_seg.normal_offset_mm}"
assert weld_seg.normal_offset_mm == 5.0, \
    f"E1: weld offset={weld_seg.normal_offset_mm}"
print(f"E1 PASS: base plane z=100, travel_offset={travel_seg.normal_offset_mm}, "
      f"weld_offset={weld_seg.normal_offset_mm} (Phase 7 applies offset)")

assert stats_wp["workplane_available"] == True
assert stats_wp["travel_offset_mm"] == 15.0
assert stats_wp["work_offset_mm"] == 5.0
print(f"E2 PASS: workplane available, offsets correct")

# Without workplane/workspace_cfg: deferred warning, but still works
_, stats_nowp = planner.plan([s_open], cfg)
assert not stats_nowp["workplane_available"]
assert any("deferred" in w for w in stats_nowp["warnings"]), \
    f"E3: no deferred warning in {stats_nowp['warnings']}"
print(f"E3 PASS: deferred warning: {stats_nowp['warnings'][0][:70]}...")
print()

# ============================================================
# Part F: Edge cases
# ============================================================
print("=" * 60)
print("Part F: Edge cases")

# F1: short closed path (overlap clamp)
short_pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(2, 0, 100, -180, 0, -135),
    RobotPoint(2, 2, 100, -180, 0, -135),
    RobotPoint(0, 2, 100, -180, 0, -135),
    RobotPoint(0, 0, 100, -180, 0, -135),
]
s_short = Stroke(id="short1", source_type="contour",
    points_px=[], closed=True,
    metadata={"robot_points": short_pts})
_, stats_short = planner.plan([s_short], cfg)
has_clamp = any("clamped" in w for w in stats_short["warnings"])
print(f"F1 PASS: short path overlap {'clamped' if has_clamp else 'ok'}")

# F2: 2-point open stroke (minimal)
pts2 = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(10, 0, 100, -180, 0, -135),
]
s_2pt = Stroke(id="twopt", source_type="skeleton",
    points_px=[], closed=False,
    metadata={"robot_points": pts2})
segs_2pt, _ = planner.plan([s_2pt], cfg)
assert len(segs_2pt) >= 3, f"F2: only {len(segs_2pt)} segments"
print(f"F2 PASS: 2-pt stroke -> {len(segs_2pt)} segments")

# F3: zero-length lead_in/out
cfg_zero = WeldingProcessConfig(
    lead_in_length_mm=0, lead_out_length_mm=0,
    overlap_length_mm=0, weld_point_spacing_mm=0.5,
)
segs_zero, _ = planner.plan([s_open], cfg_zero)
assert "weld" in [s.type for s in segs_zero], "F3: no weld"
print(f"F3 PASS: zero lead_in/out produces weld segment")
print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example (open stroke, with workplane):")
for k, v in stats_wp.items():
    if k != "warnings":
        print(f"  {k}: {v}")
print(f"  warnings: {stats_wp['warnings']}")

print()
print("Stats example (closed stroke):")
for k, v in stats_c.items():
    if k != "warnings":
        print(f"  {k}: {v}")
print(f"  warnings: {stats_c['warnings']}")

print()
print("=" * 60)
print("ALL PHASE 6.1 TESTS PASSED")
print("=" * 60)
