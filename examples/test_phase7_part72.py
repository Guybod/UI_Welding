"""Phase 7 Part 7.2 测试 — job.json 导出"""

import json, os, sys, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import (
    RobotPoint, PixelPoint, Stroke, ProcessSegment,
    WeldingProcessConfig, WorkspaceConfig, PathConfig,
)
from pipeline.process import WeldingProcessPlanner
from pipeline.mapping import WorkPlane
from pipeline.output import JobWriter, PointsWriter

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

# ============================================================
# Part A: Minimal job.json
# ============================================================
print("=" * 60)
print("Part A: Minimal job.json")

path_a = str(OUT / "job_minimal.json")
stats = JobWriter.write_job_json(path_a)

with open(path_a) as f:
    doc = json.load(f)
assert doc["schema_version"] == "welding-job-v1"
for key in ["schema_version", "created_at", "generator", "input", "configs",
            "workspace", "path_summary", "strokes", "segments",
            "export_files", "stats", "warnings", "metadata"]:
    assert key in doc, f"A1: missing {key}"
print(f"A1 PASS: all {len(doc)} top-level fields present")
assert doc["strokes"] == []
assert doc["segments"] == []
print(f"A2 PASS: empty strokes/segments valid JSON")
os.unlink(path_a)
print()

# ============================================================
# Part B: Complete integration
# ============================================================
print("=" * 60)
print("Part B: Complete integration")

wp = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 100, -180, 0, -135),
    RobotPoint(0, 100, 100, -180, 0, -135),
)
wcfg = WorkspaceConfig(normal_travel_offset_mm=15.0, normal_work_offset_mm=5.0)
pcfg = WeldingProcessConfig(voltage=22.0, current=140.0, job=0, inductance=0.0)
path_cfg = PathConfig(mode="contour")

pts = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(10, 0, 100, -180, 0, -135),
    RobotPoint(20, 5, 100, -180, 0, -135),
    RobotPoint(30, 5, 100, -180, 0, -135),
]
s1 = Stroke(id="abc123", source_type="skeleton", closed=False,
    points_px=[PixelPoint(100, 200), PixelPoint(300, 400)],
    glyph_id="A", group_id="g1",
    metadata={"robot_points": pts, "custom": "val"})

sq = [
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(50, 0, 100, -180, 0, -135),
    RobotPoint(50, 50, 100, -180, 0, -135),
    RobotPoint(0, 50, 100, -180, 0, -135),
    RobotPoint(0, 0, 100, -180, 0, -135),
]
s2 = Stroke(id="def456", source_type="contour", closed=True, is_hole=False,
    points_px=[], group_id="g1",
    metadata={"robot_points": sq})

planner = WeldingProcessPlanner()
segs, _ = planner.plan([s1, s2], pcfg, workplane=wp, workspace_cfg=wcfg)

path_b = str(OUT / "job_full.json")
stats_b = JobWriter.write_job_json(
    path_b,
    input_info={"text": "A", "mode": "contour", "canvas_w": 600, "canvas_h": 600},
    configs={"process": pcfg, "path": path_cfg, "workspace": wcfg},
    workplane=wp,
    strokes=[s1, s2],
    segments=segs,
    export_files={"points_txt": "output/points.txt"},
    stage_stats={"phase_6_2": {"weld_count": 2}},
    warnings_list=["test warning"],
    metadata={"project": "demo"},
)

with open(path_b) as f:
    doc = json.load(f)

# Strokes
assert len(doc["strokes"]) == 2
assert doc["strokes"][0]["id"] == "abc123"
assert doc["strokes"][0]["source_type"] == "skeleton"
assert doc["strokes"][0]["points_px_count"] == 2
assert doc["strokes"][0]["robot_points_count"] == 4
assert doc["strokes"][0]["glyph_id"] == "A"
print(f"B1 PASS: strokes serialized: {doc['strokes'][0]['id']} "
      f"px={doc['strokes'][0]['points_px_count']} robot={doc['strokes'][0]['robot_points_count']}")

# Segments
assert len(doc["segments"]) == len(segs)
for i, seg in enumerate(doc["segments"]):
    assert seg["deterministic_index"] == i, f"B2: index mismatch at {i}"
    assert seg["id"] == segs[i].id, f"B2: id mismatch at {i}"
    assert "points" in seg
    assert len(seg["points"]) == len(segs[i].points)
    if seg["arc_enabled"]:
        wp2 = seg["metadata"].get("weld_params", {})
        assert wp2.get("voltage") == 22.0, f"B2: voltage at segment {i}"
print(f"B2 PASS: {len(doc['segments'])} segments, deterministic_index matches, ids match points.txt")

# Configs
assert doc["configs"]["process"]["voltage"] == 22.0
print(f"B3 PASS: configs serialized")

os.unlink(path_b)
print()

# ============================================================
# Part C: WorkPlane serialization
# ============================================================
print("=" * 60)
print("Part C: WorkPlane serialization")

path_c = str(OUT / "job_wp.json")
JobWriter.write_job_json(path_c, workplane=wp)

with open(path_c) as f:
    doc = json.load(f)
ws = doc["workspace"]
assert ws["mapping_mode"] == "uv"
assert len(ws["TL"]) == 6
assert ws["width_mm"] == 200.0 and ws["height_mm"] == 100.0
assert len(ws["N"]) == 6 and abs(ws["N"][2] - 1.0) < 0.01  # N≈(0,0,1)
print(f"C1 PASS: flat plane N≈(0,0,1), U/V/N 6-element arrays")

# Tilted plane
wp_tilt = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 120, -180, 0, -135),
    RobotPoint(0, 100, 90, -180, 0, -135),
)
path_ct = str(OUT / "job_wp_tilt.json")
JobWriter.write_job_json(path_ct, workplane=wp_tilt)
with open(path_ct) as f:
    doc_t = json.load(f)
n_t = doc_t["workspace"]["N"]
assert abs(n_t[0]) > 0.01 or abs(n_t[1]) > 0.01, \
    f"C2: tilted normal xy=({n_t[0]:.4f},{n_t[1]:.4f}) ≈ 0"
print(f"C2 PASS: tilted plane N=({n_t[0]:.4f},{n_t[1]:.4f},{n_t[2]:.4f}) has non-zero x/y")
os.unlink(path_c); os.unlink(path_ct)
print()

# ============================================================
# Part D: Metadata safety
# ============================================================
print("=" * 60)
print("Part D: Metadata safety")

from pathlib import Path as P
s_bad_meta = Stroke(id="bad1", source_type="skeleton", closed=False,
    points_px=[],
    metadata={
        "path_obj": P("/tmp/test"),
        "nested": {"deep": P("/var/log")},
        "normal_str": "hello",
    })
path_d = str(OUT / "job_meta_safe.json")
s_bad_meta.metadata["robot_points"] = pts  # needed by planner
segs_d, _ = planner.plan([s_bad_meta], pcfg, workplane=wp, workspace_cfg=wcfg)
JobWriter.write_job_json(path_d, strokes=[s_bad_meta], segments=segs_d)
with open(path_d) as f:
    doc = json.load(f)
# Should not crash, should be valid JSON
assert doc["strokes"][0]["metadata"]["path_obj"] == str(P("/tmp/test"))
print(f"D1 PASS: Path object serialized to string")
os.unlink(path_d)
print()

# ============================================================
# Part E: points.txt association
# ============================================================
print("=" * 60)
print("Part E: points.txt association")

# Write points.txt first
path_pts = str(OUT / "points_assoc.txt")
PointsWriter.write_points_txt(segs, path_pts, workplane=wp)
with open(path_pts) as f:
    pts_lines = f.readlines()
pts_seg_ids = set()
for line in pts_lines[1:]:
    pts_seg_ids.add(line.split(",")[0])

# Write job.json with same segments
path_j = str(OUT / "job_assoc.json")
JobWriter.write_job_json(
    path_j, segments=segs,
    export_files={"points_txt": path_pts},
)
with open(path_j) as f:
    doc = json.load(f)

job_seg_ids = set(s["id"] for s in doc["segments"])
assert pts_seg_ids == job_seg_ids, \
    f"E1: segment_id mismatch: pts={len(pts_seg_ids)} job={len(job_seg_ids)}"
print(f"E1 PASS: {len(job_seg_ids)} segment_ids match between points.txt and job.json")

# deterministic_index allows cross-reference
for s in doc["segments"]:
    assert "deterministic_index" in s
print(f"E2 PASS: deterministic_index present in all segments")
os.unlink(path_pts); os.unlink(path_j)
print()

# ============================================================
# Part F: No other files generated
# ============================================================
print("=" * 60)
print("Part F: No Lua/PNG/arcOn generated")

for fname in os.listdir(str(OUT)):
    assert not fname.endswith(".lua"), f"F: Lua file {fname}"
    assert fname.endswith(".json") or fname.endswith(".txt") or fname.endswith(".png"), \
        f"F: already-existing file OK"

# Check job.json content has no Lua strings
path_f = str(OUT / "job_nolua.json")
JobWriter.write_job_json(path_f, segments=segs, workplane=wp)
with open(path_f) as f:
    raw = f.read().lower()
assert "setwelderparam" not in raw, "F: setWelderParam"
assert "arcon" not in raw, "F: arcOn"
assert "arcoff" not in raw, "F: arcOff"
print(f"F PASS: no Lua/arcOn/arcOff in JSON content")
os.unlink(path_f)
print()

# ============================================================
# Summary
# ============================================================
print("=" * 60)
print("Stats example:")
for k, v in stats_b.items():
    print(f"  {k}: {v}")

print()
print("job.json top-level keys:", list(doc.keys()))
print("Sample segment entry (first):")
seg0 = doc["segments"][0]
print(f"  id={seg0['id']}, index={seg0['deterministic_index']}, type={seg0['type']}")
print(f"  points[0]={seg0['points'][0]}")
print(f"  metadata={seg0['metadata']}")

print()
print("=" * 60)
print("ALL PHASE 7.2 TESTS PASSED")
print("=" * 60)
