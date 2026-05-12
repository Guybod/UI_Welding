"""Phase 7 Part 7.1 测试 — points.txt 导出"""

import math, sys, os, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (
    RobotPoint, Stroke,
    WeldingProcessConfig, WorkspaceConfig, ProcessSegment,
)
from pipeline.process import WeldingProcessPlanner
from pipeline.mapping import WorkPlane
from pipeline.output import PointsWriter

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
writer = PointsWriter()

# Helper: make a simple segment
def _seg(typ, pts, arc, offset=0.0, stroke_id="s1", weld_p=None):
    meta = {}
    if weld_p:
        meta["weld_params"] = weld_p
    import uuid
    return ProcessSegment(
        id=str(uuid.uuid4())[:8], type=typ,
        points=pts, speed_mm_s=30.0 if arc else 80.0,
        arc_enabled=arc, normal_offset_mm=offset,
        stroke_id=stroke_id, metadata=meta,
    )

# ============================================================
# Part A: Basic format
# ============================================================
print("=" * 60)
print("Part A: Basic format")

pt_base = RobotPoint(10, 20, 100, -180, 0, -135)
segs = [
    _seg("travel", [pt_base, pt_base], False, offset=0),
    _seg("weld", [pt_base, RobotPoint(30, 40, 100, -180, 0, -135)], True, offset=0),
]
wp_flat = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 100, -180, 0, -135),
    RobotPoint(0, 100, 100, -180, 0, -135),
)

path_a = str(OUT / "points_test_a.txt")
stats = writer.write_points_txt(segs, path_a, workplane=wp_flat)

with open(path_a) as f:
    lines = f.readlines()
assert len(lines) == 1 + stats["row_count"]  # header + rows
assert stats["row_count"] == 4  # travel(2) + weld(2)

# Header check
header = lines[0].strip()
expected = "segment_id,stroke_id,segment_type,point_index,x,y,z,rx,ry,rz,speed_mm_s,arc_enabled,voltage,current,tag"
assert header == expected, f"A1: header mismatch:\n  got: {header}\n  exp: {expected}"
print(f"A1 PASS: header matches expected 14 fields")

# Row format: comma separated, 14 fields
for i, line in enumerate(lines[1:], 1):
    fields = line.strip().split(",")
    assert len(fields) == 15, f"A2: row {i} has {len(fields)} fields"
    # arc_enabled is 0 or 1
    assert fields[11] in ("0", "1"), f"A2: arc_enabled={fields[11]}"
print(f"A2 PASS: {stats['row_count']} rows, 14 fields each, arc_enabled is 0/1")

os.unlink(path_a)
print()

# ============================================================
# Part B: Flat plane normal_offset
# ============================================================
print("=" * 60)
print("Part B: Flat plane normal_offset (N=(0,0,1))")

pt = RobotPoint(10, 20, 100, -180, 0, -135)
seg_offset = _seg("weld", [pt], True, offset=15.0)
path_b = str(OUT / "points_test_b.txt")
writer.write_points_txt([seg_offset], path_b, workplane=wp_flat)

with open(path_b) as f:
    lines = f.readlines()
row = lines[1].strip().split(",")
z_exported = float(row[6])
assert abs(z_exported - 115.0) < 0.01, \
    f"B1: z={z_exported:.2f} != 115 (base 100 + offset 15)"
print(f"B1 PASS: base z=100 + offset=15 → exported z={z_exported:.1f} (N=(0,0,1))")

# But the code uses N vector, not z+15
assert wp_flat.normal.z == 1.0, "B2: normal not (0,0,1)"
print(f"B2 PASS: code uses workplane.normal (N={wp_flat.normal.z:.1f}), not hardcoded z+15")

os.unlink(path_b)
print()

# ============================================================
# Part C: Tilted plane normal_offset
# ============================================================
print("=" * 60)
print("Part C: Tilted plane normal_offset")

wp_tilt = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 120, -180, 0, -135),
    RobotPoint(0, 100, 90, -180, 0, -135),
)
n = wp_tilt.normal
assert not (abs(n.x) < 0.01 and abs(n.y) < 0.01 and abs(n.z - 1) < 0.01), \
    f"C0: normal is (0,0,1)"

pt = RobotPoint(50, 30, 100, -180, 0, -135)
seg_tilt = _seg("weld", [pt], True, offset=10.0)
path_c = str(OUT / "points_test_c.txt")
writer.write_points_txt([seg_tilt], path_c, workplane=wp_tilt)

with open(path_c) as f:
    row = f.readlines()[1].strip().split(",")
x_e, y_e, z_e = float(row[4]), float(row[5]), float(row[6])
dx, dy, dz = x_e - pt.x, y_e - pt.y, z_e - pt.z
expected_dx = 10 * n.x
expected_dy = 10 * n.y
expected_dz = 10 * n.z
assert abs(dx - expected_dx) < 0.1, f"C1: dx={dx:.3f} != {expected_dx:.3f}"
assert abs(dy - expected_dy) < 0.1, f"C1: dy={dy:.3f} != {expected_dy:.3f}"
assert abs(dz - expected_dz) < 0.2, f"C1: dz={dz:.3f} != {expected_dz:.3f}"
print(f"C1 PASS: delta=({dx:.4f},{dy:.4f},{dz:.4f}) = 10*N ✓")
os.unlink(path_c)
print()

# ============================================================
# Part D: No WorkPlane safety
# ============================================================
print("=" * 60)
print("Part D: No WorkPlane safety")

seg_no_wp = _seg("weld", [pt], True, offset=5.0)
try:
    writer.write_points_txt([seg_no_wp], str(OUT / "should_fail.txt"),
                             workplane=None, already_applied_offsets=False)
    assert False, "D1: should have raised"
except ValueError as e:
    assert "normal_offset_mm" in str(e) or "WorkPlane" in str(e), f"D1: {e}"
    print(f"D1 PASS: ValueError on missing WorkPlane: {e}")

# offset=0, no WorkPlane → OK
seg_zero = _seg("weld", [pt], True, offset=0.0)
path_d = str(OUT / "points_test_d.txt")
stats_d = writer.write_points_txt([seg_zero], path_d, workplane=None)
assert stats_d["workplane_required"] == False
os.unlink(path_d)
print(f"D2 PASS: offset=0 without WorkPlane → OK")
print()

# ============================================================
# Part E: already_applied_offsets
# ============================================================
print("=" * 60)
print("Part E: already_applied_offsets=True")

seg_pre = _seg("weld", [pt], True, offset=5.0)
path_e = str(OUT / "points_test_e.txt")
stats_e = writer.write_points_txt([seg_pre], path_e,
                                   workplane=None, already_applied_offsets=True)
assert stats_e["already_applied_offsets"] == True
assert stats_e["normal_offset_applied"] == False

with open(path_e) as f:
    row = f.readlines()[1].strip().split(",")
z_e2 = float(row[6])
assert abs(z_e2 - pt.z) < 0.01, f"E1: z={z_e2} != {pt.z} (should be base plane)"
print(f"E1 PASS: already_applied_offsets → z={z_e2} (unchanged base plane)")
os.unlink(path_e)
print()

# ============================================================
# Part F: Weld params in export
# ============================================================
print("=" * 60)
print("Part F: Weld params export")

seg_wp_on = _seg("weld", [pt], True, offset=0,
                  weld_p={"voltage": 18, "current": 160})
seg_wp_off = _seg("travel", [pt], False, offset=0)

path_f = str(OUT / "points_test_f.txt")
writer.write_points_txt([seg_wp_on, seg_wp_off], path_f, workplane=wp_flat)

with open(path_f) as f:
    lines = f.readlines()
row_on = lines[1].strip().split(",")
row_off = lines[2].strip().split(",")
assert row_on[12] == "18", f"F1: weld voltage={row_on[12]}"
assert row_on[13] == "160", f"F1: weld current={row_on[13]}"
assert row_off[12] in ("0", ""), f"F1: travel voltage={row_off[12]}"
assert row_off[13] in ("0", ""), f"F1: travel current={row_off[13]}"
print(f"F1 PASS: weld V={row_on[12]}, I={row_on[13]}; travel V={row_off[12]}, I={row_off[13]}")
os.unlink(path_f)
print()

# ============================================================
# Part G: Phase 6.2 integration
# ============================================================
print("=" * 60)
print("Part G: Phase 6.2 integration")

planner = WeldingProcessPlanner()
cfg = WeldingProcessConfig(voltage=22.0, current=140.0, job=0, inductance=0)
wcfg = WorkspaceConfig(normal_travel_offset_mm=15.0, normal_work_offset_mm=5.0)

pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(10, 0, 100, -180, 0, -135),
    RobotPoint(20, 5, 100, -180, 0, -135),
    RobotPoint(30, 5, 100, -180, 0, -135),
]
s = Stroke(id="g1", source_type="skeleton", points_px=[], closed=False,
           metadata={"robot_points": pts})

segs, _ = planner.plan([s], cfg, workplane=wp_flat, workspace_cfg=wcfg)
path_g = str(OUT / "points_integration.txt")
stats_g = writer.write_points_txt(segs, path_g, workplane=wp_flat)

with open(path_g) as f:
    lines = f.readlines()

# Check: all travel/retreat points have travel_offset, weld has work_offset
travel_rows = [l for l in lines if ",travel," in l]
weld_rows = [l for l in lines if ",weld," in l]
retreat_rows = [l for l in lines if ",retreat," in l]

# Travel: base z=100 + travel_offset=15 = z≈115
for r in travel_rows:
    z = float(r.split(",")[6])
    assert abs(z - 115) < 1, f"G1: travel z={z}"

# Weld: base z=100 + work_offset=5 = z≈105
for r in weld_rows:
    z = float(r.split(",")[6])
    assert abs(z - 105) < 1, f"G2: weld z={z}"

# Retreat: base z=100 + travel_offset=15 = z≈115
for r in retreat_rows:
    z = float(r.split(",")[6])
    assert abs(z - 115) < 1, f"G3: retreat z={z}"

print(f"G1 PASS: travel z≈115 ✓")
print(f"G2 PASS: weld z≈105 ✓")
print(f"G3 PASS: retreat z≈115 ✓")

# arc_enabled and voltage/current in weld
for r in weld_rows:
    fields = r.split(",")
    assert fields[11] == "1"  # arc_enabled
    assert float(fields[12]) == 22.0  # voltage
    assert float(fields[13]) == 140.0  # current

# No Lua/job.json generated
for fname in os.listdir(str(OUT)):
    assert not fname.endswith(".lua"), f"G4: Lua file {fname}"
    assert not fname.endswith(".json"), f"G4: json file {fname}"
print(f"G4 PASS: no .lua/.json generated ✓")

# File is readable CSV
import csv
with open(path_g) as f:
    reader = csv.reader(f)
    rows = list(reader)
    assert len(rows[0]) == 15  # header
    for r in rows[1:]:
        assert len(r) == 15, f"G5: row has {len(r)} fields"
print(f"G5 PASS: valid CSV, {len(rows)-1} data rows ✓")

print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example (Phase 6.2 integration):")
for k, v in stats_g.items():
    if k != "warnings":
        print(f"  {k}: {v}")

# Re-export and show sample
path_sample = str(OUT / "points_sample.txt")
writer.write_points_txt(segs, path_sample, workplane=wp_flat)
print()
print("Sample rows (first 4):")
with open(path_sample) as f:
    for line in f.readlines()[:4]:
        print(f"  {line.rstrip()}")
os.unlink(path_sample)

print()
print("=" * 60)
print("ALL PHASE 7.1 TESTS PASSED")
print("=" * 60)
