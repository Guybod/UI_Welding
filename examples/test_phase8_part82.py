"""Phase 8 Part 8.2 测试 — OfflinePipelineRunner"""

import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint, PathConfig, WeldingProcessConfig, WorkspaceConfig
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner, RunResult

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

wp = WorkPlane(
    RobotPoint(0, 0, 100, -180, 0, -135),
    RobotPoint(200, 0, 100, -180, 0, -135),
    RobotPoint(0, 100, 100, -180, 0, -135),
)

# ============================================================
print("=" * 60)
print("Test 1: Contour 'A'")
runner = OfflinePipelineRunner(output_dir=str(OUT))
r = runner.run("A", mode="contour", workplane=wp)
assert r.ok, f"Test 1 failed: {r.errors}"
assert r.total_segments >= 5
assert r.total_strokes_raw >= 1
for key in ["points_txt", "job_json", "strokes_preview_png",
            "segments_preview_png", "combined_preview_png", "summary_json"]:
    assert key in r.files, f"missing {key}"
    assert os.path.exists(r.files[key]), f"missing file {key}"
    assert os.path.getsize(r.files[key]) > 100, f"empty {key}"
print(f"Test 1 PASS: ok={r.ok}, dir={os.path.basename(r.output_dir)}, "
      f"segs={r.total_segments}, dur={r.duration_ms:.0f}ms")

# ============================================================
print("Test 2: Skeleton 'i'")
r2 = runner.run("i", mode="skeleton", workplane=wp)
assert r2.ok
assert r2.total_strokes_raw >= 2  # dot + body
assert r2.total_segments >= 3
for key in r2.files:
    assert os.path.exists(r2.files[key])
print(f"Test 2 PASS: ok={r2.ok}, strokes_raw={r2.total_strokes_raw}, "
      f"segs={r2.total_segments}")

# ============================================================
print("Test 3: summary.json content")
sp = r.files["summary_json"]
with open(sp) as f:
    s = json.load(f)
assert s["ok"] == True
assert s["text"] == "A"
assert s["mode"] == "contour"
assert s["duration_ms"] > 0
assert "output_files" in s
assert "stage_stats" in s
assert len(s["stage_stats"]) >= 7
assert s["stats"]["segments"] == r.total_segments
# Directory naming: <timestamp>_<safe_text>_<mode>
dirname = os.path.basename(r.output_dir)
assert dirname.endswith("_contour"), f"bad dir suffix: {dirname}"
assert "_A_" in dirname or dirname.startswith("202"), f"bad dir format: {dirname}"
print(f"Test 3 PASS: summary.json valid, {len(s['stage_stats'])} stages, "
      f"version={s['pipeline_version']}, dir={dirname}")

# ============================================================
print("Test 4: No Lua leakage")
for r in [r, r2]:
    for key in ["points_txt", "job_json", "summary_json"]:
        with open(r.files[key]) as f:
            raw = f.read().lower()
        for kw in ["setwelderparam", "arcon", "arcoff"]:
            assert kw not in raw, f"{kw} in {r.files[key]}"
print("Test 4 PASS: no Lua strings in text output files")

# ============================================================
print("Test 5: Output directory listing")
files_in_dir = os.listdir(r.output_dir)
expected = ["points.txt", "job.json", "preview_strokes.png",
            "preview_segments.png", "preview_combined.png", "summary.json"]
for fn in expected:
    assert fn in files_in_dir, f"missing {fn}"
print(f"Test 5 PASS: all 6 expected files present in {os.path.basename(r.output_dir)}")

# ============================================================
print("Test 6: Bad mode handled")
r_bad = runner.run("A", mode="bad_mode", workplane=wp)
assert not r_bad.ok
assert any("unknown mode" in e for e in r_bad.errors)
print(f"Test 6 PASS: bad mode → ok=False, error: {r_bad.errors[0][:50]}")

# ============================================================
print(f"\nOutput directory: {r.output_dir}")
print("Files:")
for fn in sorted(files_in_dir):
    fp = os.path.join(r.output_dir, fn)
    print(f"  {fn}: {os.path.getsize(fp):,} bytes")

print(f"\n{'='*60}")
print("ALL PHASE 8.2 TESTS PASSED")
print(f"{'='*60}")
