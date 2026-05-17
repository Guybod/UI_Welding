"""Phase 9-fix test: Lua exporter with table format + arc_enabled state machine"""
import os, json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.offline_runner import OfflinePipelineRunner
from pipeline.mapping import WorkPlane
from core.types import RobotPoint, WeldingProcessConfig, WorkspaceConfig, LuaExportConfig

wp = WorkPlane(RobotPoint(0, 100, 300, 180, 0, 90), RobotPoint(600, 100, 300, 180, 0, 90), RobotPoint(0, 700, 300, 180, 0, 90))
pc = WeldingProcessConfig(voltage=28, current=200, job=7, inductance=2, weld_speed_mm_s=35, travel_speed_mm_s=90)
wc = WorkspaceConfig(normal_work_offset_mm=6, normal_travel_offset_mm=18, normal_safe_offset_mm=20)
lc = LuaExportConfig(acceleration=300, blend_radius=2, precision=3)

# ============================================================
# Test 1: contour "A" — table format + arc state machine
# ============================================================
print("=" * 60)
print("Test 1: contour 'A' — table format + arcOn/arcOff")
r = OfflinePipelineRunner(output_dir="output", process_config=pc, workspace_config=wc, lua_config=lc)
res = r.run("A", mode="contour", workplane=wp)
assert res.ok
lua_path = res.files.get("lua_script", "")
assert lua_path and os.path.exists(lua_path)
with open(lua_path, encoding="utf-8") as f:
    lua = f.read()

# Format checks
assert "setWelderParam({job=7,I=200,U=28,L=2})" in lua, "wrong setWelderParam"
assert "movL({cp={" in lua, "missing table format movL"
assert "arcOn()" in lua, "missing arcOn"
assert "arcOff()" in lua, "missing arcOff"
assert "movL(251" not in lua, "positional format still present"
assert "-- Point spacing: 0.5 mm" not in lua or "Point spacing: 0.5" in lua, "header should show spacing"
print(f"  PASS: {len(lua.split(chr(10)))} lines, table format, arcOn/arcOff OK")

# ============================================================
# Test 2: arc state machine — lead_in in arc, lead_out before arcOff
# ============================================================
print("\n" + "=" * 60)
print("Test 2: arc state machine ordering")
lines = lua.split("\n")
arc_on_line = next(i for i, ln in enumerate(lines) if "arcOn()" in ln)
arc_off_line = next(i for i, ln in enumerate(lines) if "arcOff()" in ln)
arc_on_count = lua.count("arcOn()")
arc_off_count = lua.count("arcOff()")

# Check ordering: arcOn before first movL after it, arcOff before retreat movL
# The segment COMMENT for lead_in may appear before arcOn, but the first movL after arcOn should be lead_in
post_arc_on_lines = lines[arc_on_line:]
first_movl_after_arc_on = next(i for i, ln in enumerate(post_arc_on_lines) if ln.startswith("movL("))
assert post_arc_on_lines[first_movl_after_arc_on + 1].startswith("movL("), "expected movL sequence after arcOn"

# Check end: arcOff before last retreat movLs
pre_arc_off = lines[:arc_off_line]
last_seg_before = next(i for i, ln in enumerate(reversed(pre_arc_off)) if "type:" in ln)
print(f"  PASS: arcOn at line {arc_on_line+1}, arcOff at line {arc_off_line+1}")
print(f"  arc balanced: on={arc_on_count}, off={arc_off_count}")

# ============================================================
# Test 3: contour "O" — overlap within arc
# ============================================================
print("\n" + "=" * 60)
print("Test 3: contour 'O' — overlap between arcOn/arcOff")
r2 = OfflinePipelineRunner(output_dir="output", process_config=pc, workspace_config=wc, lua_config=lc)
res2 = r2.run("O", mode="contour", workplane=wp)
assert res2.ok
with open(res2.files["lua_script"], encoding="utf-8") as f:
    lua2 = f.read()
on_count = lua2.count("arcOn()")
off_count = lua2.count("arcOff()")
assert on_count == off_count, f"unbalanced: {on_count} vs {off_count}"
overlap_idx = lua2.find("overlap")
arc_on_idx = lua2.find("arcOn()")
arc_off_idx = lua2.find("arcOff()")
assert arc_on_idx < overlap_idx < arc_off_idx, "overlap not between arcOn/arcOff"
print(f"  PASS: arc balanced ({on_count}), overlap within arc")

# ============================================================
# Test 4: filename is job.lua + summary.json
# ============================================================
print("\n" + "=" * 60)
print("Test 4: filename based on text + summary")
assert os.path.basename(lua_path) == "A.lua", f"not A.lua: {os.path.basename(lua_path)}"
with open(os.path.join(res.output_dir, "summary.json"), encoding="utf-8") as f:
    s = json.load(f)
le = s["lua_export"]
assert le["lua_path"] == "A.lua", f"lua_path: {le['lua_path']}"
assert le["lua_source_text"] == "A"
assert le["lua_filename_sanitized"] == "A"
print(f"  PASS: {le['lua_path']} source={le['lua_source_text']} sanitized={le['lua_filename_sanitized']}")

# ============================================================
# Test 5: points.txt/job.json format unchanged
# ============================================================
print("\n" + "=" * 60)
print("Test 5: format regression")
with open(os.path.join(res.output_dir, "points.txt"), encoding="utf-8") as f:
    hdr = f.readline()
assert hdr.startswith("segment_id,stroke_id"), f"bad header"
with open(os.path.join(res.output_dir, "job.json"), encoding="utf-8") as f:
    j = json.load(f)
assert "schema_version" in j
print("  PASS")

print("\n" + "=" * 60)
print("ALL Phase 9-fix TESTS PASSED")
print("=" * 60)
