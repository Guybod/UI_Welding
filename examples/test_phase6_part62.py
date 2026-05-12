"""Phase 6 Part 6.2 测试 — 焊接参数集成"""

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

pts_o = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(10, 0, 100, -180, 0, -135),
    RobotPoint(20, 5, 100, -180, 0, -135),
    RobotPoint(30, 5, 100, -180, 0, -135),
]
s_open = Stroke(id="o1", source_type="skeleton",
    points_px=[], closed=False,
    metadata={"robot_points": pts_o})

sq_pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(50, 0, 100, -180, 0, -135),
    RobotPoint(50, 50, 100, -180, 0, -135),
    RobotPoint(0, 50, 100, -180, 0, -135),
    RobotPoint(0, 0, 100, -180, 0, -135),
]
s_closed = Stroke(id="c1", source_type="contour",
    points_px=[], closed=True,
    metadata={"robot_points": sq_pts})

# ============================================================
# Part A: Default weld params
# ============================================================
print("=" * 60)
print("Part A: Default weld params")

cfg = WeldingProcessConfig()
assert cfg.voltage == 24.0
assert cfg.current == 150.0
assert cfg.job == 0
assert cfg.inductance == 0.0
print(f"A0 PASS: defaults V={cfg.voltage}, I={cfg.current}, job={cfg.job}, L={cfg.inductance}")

segs, stats = planner.plan([s_open], cfg)
assert stats["weld_params_present"] == True
assert stats["weld_voltage"] == 24.0
assert stats["weld_current"] == 150.0
assert stats["weld_job"] == 0
assert stats["weld_inductance"] == 0.0
print(f"A1 PASS: stats weld_params: V={stats['weld_voltage']}, "
      f"I={stats['weld_current']}, job={stats['weld_job']}, L={stats['weld_inductance']}")

print()

# ============================================================
# Part B: Custom weld params
# ============================================================
print("=" * 60)
print("Part B: Custom weld params")

cfg_custom = WeldingProcessConfig(
    voltage=18.0, current=160.0, job=0, inductance=0.0,
)
segs_c, stats_c = planner.plan([s_open], cfg_custom)
assert stats_c["weld_voltage"] == 18.0
assert stats_c["weld_current"] == 160.0
print(f"B1 PASS: custom V={stats_c['weld_voltage']}, I={stats_c['weld_current']}")

# Check metadata on arc segments
wp = None
for seg in segs_c:
    if seg.arc_enabled:
        wp = seg.metadata.get("weld_params")
        assert wp is not None, f"B2: {seg.type} missing weld_params"
        assert wp["voltage"] == 18.0, f"B2: {seg.type} voltage={wp['voltage']}"
        assert wp["current"] == 160.0, f"B2: {seg.type} current={wp['current']}"
        assert wp["job"] == 0
        assert wp["inductance"] == 0.0
    else:
        # travel/retreat: no weld_params or explicitly empty
        wp = seg.metadata.get("weld_params")
        assert wp is None, f"B2: {seg.type} should not have weld_params"

print(f"B2 PASS: arc segments have weld_params, travel/retreat don't")
print()

# ============================================================
# Part C: Closed stroke — overlap has weld_params
# ============================================================
print("=" * 60)
print("Part C: Closed stroke weld_params")

segs_c2, stats_c2 = planner.plan([s_closed], cfg_custom)
overlap_segs = [s for s in segs_c2 if s.type == "overlap"]
assert len(overlap_segs) == 1
ov = overlap_segs[0]
assert ov.metadata.get("weld_params") is not None, "C1: overlap missing weld_params"
assert ov.metadata["weld_params"]["voltage"] == 18.0
print(f"C1 PASS: overlap has weld_params V={ov.metadata['weld_params']['voltage']}")

# Count: closed stroke has lead_in + weld + overlap + lead_out = 4 arc segments
arc_count = sum(1 for s in segs_c2 if s.metadata.get("weld_params"))
assert arc_count == 4, f"C2: expected 4 arc segments, got {arc_count}"
assert stats_c2["weld_param_segments_count"] == 4
print(f"C2 PASS: {arc_count} arc segments have weld_params")
print()

# ============================================================
# Part D: No Lua / setWelderParam / arcOn / arcOff / points.txt
# ============================================================
print("=" * 60)
print("Part D: No Lua/arcOn/setWelderParam/points.txt generation")

import os
# Check no output files generated
output_files = [f for f in os.listdir(".") if f.endswith((".lua", ".txt", ".json"))]
new_outputs = [f for f in output_files if "phase6" in f.lower()]
assert len(new_outputs) == 0, f"D1: unexpected output files: {new_outputs}"
print(f"D1 PASS: no .lua/.txt/.json generated")

# Check ProcessSegment has no setWelderParam/arcOn/arcOff strings
for seg in segs_c2:
    meta_str = str(seg.metadata).lower()
    assert "setwelderparam" not in meta_str, f"D2: setWelderParam in {seg.type}"
    assert "arcon" not in meta_str, f"D2: arcOn in {seg.type}"
    assert "arcoff" not in meta_str, f"D2: arcOff in {seg.type}"
print(f"D2 PASS: no setWelderParam/arcOn/arcOff in any segment metadata")

# All segments are pure data (ProcessSegment), no motion commands
for seg in segs_c2:
    assert hasattr(seg, "points"), f"D3: segment missing points"
    assert isinstance(seg.points, list), f"D3: points not list"
print(f"D3 PASS: all segments are pure ProcessSegment data")
print()

# ============================================================
# Part E: Regression — Phase 6.1 tests still pass (run separately)
# ============================================================
print("=" * 60)
print("Part E: Phase 6.1 regression — run 'python3 examples/test_phase6_part61.py'")
print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example (custom params):")
for k, v in stats_c.items():
    if k != "warnings":
        print(f"  {k}: {v}")
print(f"  warnings: {stats_c['warnings']}")

print()
print("=" * 60)
print("ALL PHASE 6.2 TESTS PASSED")
print("=" * 60)
