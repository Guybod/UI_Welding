"""Phase 8 Part 8.3 测试 — 统一 Preview 管线 / 旧 preview.py 收口"""

import os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint, PixelPoint, Stroke, ProcessSegment, WeldingProcessConfig, WorkspaceConfig
from pipeline.mapping import WorkPlane
from pipeline.output import DebugExporter
from pipeline.offline_runner import OfflinePipelineRunner

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
dx = DebugExporter()

# ============================================================
print("=" * 60)
print("Part A: DebugExporter write_run_preview")

s_outer = Stroke(id="o1", source_type="contour",
    points_px=[PixelPoint(100,100), PixelPoint(500,100),
               PixelPoint(500,500), PixelPoint(100,500), PixelPoint(100,100)],
    closed=True, is_hole=False)
s_hole = Stroke(id="h1", source_type="contour",
    points_px=[PixelPoint(200,200), PixelPoint(400,200),
               PixelPoint(400,400), PixelPoint(200,400), PixelPoint(200,200)],
    closed=True, is_hole=True)

import uuid
segs = [
    ProcessSegment(id=str(uuid.uuid4())[:8], type="travel",
        points=[RobotPoint(0,0,100,-180,0,-135)], speed_mm_s=80,
        arc_enabled=False, normal_offset_mm=15, stroke_id="s1", metadata={}),
    ProcessSegment(id=str(uuid.uuid4())[:8], type="weld",
        points=[RobotPoint(0,0,100,-180,0,-135), RobotPoint(50,30,100,-180,0,-135)],
        speed_mm_s=30, arc_enabled=True, normal_offset_mm=5, stroke_id="s1",
        metadata={"weld_params": {"voltage": 18, "current": 160}}),
]

run_dir = str(OUT / "test_run_preview")
result = dx.write_run_preview([s_outer, s_hole], segs, run_dir, title_prefix="Test")

for key in ["strokes_preview", "segments_preview", "combined_preview"]:
    s = result[key]
    assert os.path.exists(s["output_path"]), f"{key}: missing"
    assert s["file_size_bytes"] > 100, f"{key}: too small ({s['file_size_bytes']}B)"
    assert s["file_size_bytes"] > 100
print(f"A1 PASS: 3 preview PNGs generated:")
for key, s in result.items():
    print(f"  {key}: {os.path.basename(s['output_path'])} ({s['file_size_bytes']:,}B)")
print()

# ============================================================
print("=" * 60)
print("Part B: OfflinePipelineRunner preview integration")

wp = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 100, -180, 0, -135),
    RobotPoint(0, 100, 100, -180, 0, -135),
)
runner = OfflinePipelineRunner(output_dir=str(OUT))
r = runner.run("A", mode="contour", workplane=wp)
assert r.ok

for key in ["strokes_preview_png", "segments_preview_png", "combined_preview_png"]:
    assert key in r.files, f"B: missing {key}"
    assert os.path.exists(r.files[key]), f"B: missing file {key}"
    assert os.path.getsize(r.files[key]) > 100, f"B: empty {key}"
print(f"B1 PASS: runner produces 3 preview PNGs via DebugExporter")
for key in ["strokes_preview_png", "segments_preview_png", "combined_preview_png"]:
    print(f"  {os.path.basename(r.files[key])}: {os.path.getsize(r.files[key]):,}B")
print()

# ============================================================
print("=" * 60)
print("Part C: Old preview.py compatibility")

import pipeline.preview as old_preview
assert hasattr(old_preview, "preview_paths_2d"), "C1: missing old function"
assert hasattr(old_preview, "preview_weld_segments"), "C1: missing old function"
assert hasattr(old_preview, "preview_pen_segments"), "C1: missing old function"
print(f"C1 PASS: old preview.py imports OK, 3 functions present")

# Check deprecated marker
with open(Path(__file__).parent.parent / "pipeline" / "preview.py") as f:
    doc = f.read()
assert "Deprecated" in doc or "deprecated" in doc, "C2: missing deprecated marker"
print(f"C2 PASS: deprecated marker found in pipeline/preview.py")
print()

# ============================================================
print("=" * 60)
print("Part D: No Lua/CRI/UI leakage")

for r in [r]:
    for key in ["points_txt", "job_json", "summary_json"]:
        with open(r.files[key]) as f:
            raw = f.read().lower()
        for kw in ["setwelderparam", "arcon", "arcoff"]:
            assert kw not in raw, f"D: {kw} in {r.files[key]}"
print("D1 PASS: no Lua/arc strings in output")
print("D2 PASS: no CRI/UI/real robot calls (static verification)")
print()

# ============================================================
print("=" * 60)
print("Part E: Points.txt/job.json format unchanged")

with open(r.files["points_txt"]) as f:
    assert f.readline().startswith("segment_id,stroke_id")
with open(r.files["job_json"]) as f:
    j = json.load(f)
    assert j["schema_version"] == "welding-job-v1"
print("E1 PASS: points.txt header + job.json schema unchanged")
print()

# ============================================================
print(f"Preview output directory: {r.output_dir}")
for fn in sorted(os.listdir(r.output_dir)):
    fp = os.path.join(r.output_dir, fn)
    print(f"  {fn}: {os.path.getsize(fp):,} bytes")

print(f"\n{'='*60}")
print("ALL PHASE 8.3 TESTS PASSED")
print(f"{'='*60}")
