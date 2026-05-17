"""Phase 9.3-c-b: Height model verification"""
import os, json, re
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.offline_runner import OfflinePipelineRunner
from pipeline.mapping import WorkPlane
from core.types import RobotPoint, WorkspaceConfig

wp = WorkPlane(RobotPoint(0, 0, 100, 180, 0, 90), RobotPoint(200, 0, 100, 180, 0, 90), RobotPoint(0, 100, 100, 180, 0, 90))
wc = WorkspaceConfig(z_work_mm=105, z_safe_mm=115, z_super_safe_mm=125)


def pts_rows(path):
    with open(path, encoding="utf-8") as f:
        next(f)
        return [dict(zip(["seg_id","stroke_id","seg_type","idx","x","y","z","rx","ry","rz","speed","arc","voltage","current","tag"],
            l.strip().split(","))) for l in f if l.strip()]


# ============================================================
# Test 1: Z consistency
# ============================================================
print("=" * 60)
print("Test 1: points.txt vs Lua Z consistency")
r = OfflinePipelineRunner(output_dir="output", workspace_config=wc)
res = r.run("A", mode="contour", workplane=wp)
assert res.ok, f"failed: {res.errors}"

rows = pts_rows(os.path.join(res.output_dir, "points.txt"))
weld_z = [float(r["z"]) for r in rows if r["seg_type"] == "weld"]
travel_z = [float(r["z"]) for r in rows if r["seg_type"] == "travel"]
retreat_z = [float(r["z"]) for r in rows if r["seg_type"] == "retreat"]

print(f"  pts weld Z: {min(weld_z):.1f}-{max(weld_z):.1f}")
print(f"  pts travel Z: {min(travel_z):.1f}-{max(travel_z):.1f}")
print(f"  pts retreat Z: {min(retreat_z):.1f}-{max(retreat_z):.1f}")
assert abs(min(weld_z) - 105) < 0.5, f"weld Z wrong"
assert abs(min(travel_z) - 115) < 0.5, f"travel Z wrong"
assert abs(min(retreat_z) - 115) < 0.5, f"retreat Z wrong"

# Check Lua Z
with open(res.files["lua_script"], encoding="utf-8") as f:
    lua = f.read()
lua_zs = []
for m in re.finditer(r'movL\(\{cp=\{([^}]+)\}', lua):
    z = float(m.group(1).split(",")[2])
    lua_zs.append(z)

# Lua: travel movLs at Z=115, weld at Z=105
z115_count = sum(1 for z in lua_zs if abs(z - 115) < 0.5)
z105_count = sum(1 for z in lua_zs if abs(z - 105) < 0.5)
print(f"  Lua Z~105 (weld): {z105_count}, Z~115 (travel/retreat): {z115_count}")
assert z105_count > 0, "No Lua weld Z=105"
assert z115_count > 0, "No Lua travel/retreat Z=115"
print("  PASS: no double offset between pts and Lua")

# ============================================================
# Test 2: arcOff → retreat lift
# ============================================================
print("\n" + "=" * 60)
print("Test 2: arcOff() followed by retreat lift")
lines = lua.split("\n")
for i, line in enumerate(lines):
    if "arcOff()" in line:
        for j in range(i + 1, min(i + 10, len(lines))):
            if lines[j].startswith("movL("):
                m = re.search(r'movL\(\{cp=\{([^}]+)\}', lines[j])
                z = float(m.group(1).split(",")[2]) if m else 0
                assert abs(z - 115) < 0.5, f"arcOff+1 Z={z}"
                print(f"  arcOff at L{i+1} → next movL Z={z:.1f} OK")
                break
        break
print("  PASS")

# ============================================================
# Test 3: ABc multi-stroke
# ============================================================
print("\n" + "=" * 60)
print("Test 3: ABc multi-stroke lift")
r3 = OfflinePipelineRunner(output_dir="output", workspace_config=wc)
res3 = r3.run("ABc", mode="contour", workplane=wp)
with open(res3.files["lua_script"], encoding="utf-8") as f:
    lua3 = f.read()
lines3 = lua3.split("\n")
ao_lines = [i for i, l in enumerate(lines3) if "arcOff()" in l]
print(f"  Strokes: {len(ao_lines)}")
for k, ao in enumerate(ao_lines):
    for j in range(ao + 1, min(ao + 5, len(lines3))):
        if lines3[j].startswith("movL("):
            m = re.search(r'movL\(\{cp=\{([^}]+)\}', lines3[j])
            z = float(m.group(1).split(",")[2]) if m else 0
            assert abs(z - 115) < 0.5, f"Stroke {k+1} arcOff+1 Z={z}"
    print(f"  Stroke {k+1}/{len(ao_lines)}: arcOff → retreat OK")
print("  PASS")

# ============================================================
# Test 4: z_super_safe
# ============================================================
print("\n" + "=" * 60)
print("Test 4: z_super_safe")
with open(os.path.join(res.output_dir, "summary.json"), encoding="utf-8") as f:
    s = json.load(f)
for st in s.get("stage_stats", []):
    if st["name"] == "plan":
        p = st["stats"]
        print(f"  height_model: {p.get('height_model')}")
        print(f"  z_work_mm: {p.get('z_work_mm')}")
        print(f"  z_safe_mm: {p.get('z_safe_mm')}")
        print(f"  z_super_safe_mm: {p.get('z_super_safe_mm')}")
print("  NOTE: z_super_safe stored in config, not yet output as a separate segment")
print("  PASS (documented limitation)")

# ============================================================
# Test 5: Safety warning
# ============================================================
print("\n" + "=" * 60)
print("Test 5: z_safe <= z_work warning")
wc_bad = WorkspaceConfig(z_work_mm=900, z_safe_mm=895)
r5 = OfflinePipelineRunner(output_dir="output", workspace_config=wc_bad)
res5 = r5.run("A", mode="contour", workplane=wp)
with open(os.path.join(res5.output_dir, "summary.json"), encoding="utf-8") as f:
    s5 = json.load(f)
plan_warnings = []
for st in s5.get("stage_stats", []):
    if st["name"] == "plan":
        plan_warnings = st.get("stats", {}).get("warnings", [])
has_warn = any("z_safe" in w.lower() or "drag" in w.lower() for w in plan_warnings)
print(f"  Plan warnings: {plan_warnings}")
assert has_warn, "Missing safety warning!"
assert res5.ok, "Should not crash"
print("  PASS")

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
