"""Phase 8 Part 8.1 — 端到端离线 Pipeline 集成测试

全链路: render_char → extract → clean → refine → schedule → map → plan → export
输出: points.txt + job.json + preview PNG
纯离线, 无 Qt/PySide6, 无机器人连接, 无 Lua。
"""

import os, sys, json as _json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PathConfig, WeldingProcessConfig, WorkspaceConfig, RobotPoint
from pipeline.raster import get_default_font_path, render_char
from pipeline.vision import ContourExtractor, SkeletonExtractor
from pipeline.path import clean_and_resample_strokes, AdaptivePathRefiner, PathScheduler
from pipeline.mapping import WorkPlane, PoseMapper
from pipeline.process import WeldingProcessPlanner
from pipeline.output import PointsWriter, JobWriter, DebugExporter

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()
FONT_SIZE = 600
CANVAS_W = 600.0; CANVAS_H = 600.0
PX_PER_MM = 10.0

WP = WorkPlane(
    RobotPoint(0,0,100,-180,0,-135), RobotPoint(200,0,100,-180,0,-135),
    RobotPoint(0,100,100,-180,0,-135),
)

CFG_C = PathConfig(mode="contour", sample_spacing_mm=0.5, simplify_epsilon_mm=0.1,
    min_path_length_mm=2.0, dot_strategy="keep", preserve_corners=True,
    corner_angle_deg=60, straight_tol_mm=0.5, curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5, contour_max_vertices=12)
CFG_S = PathConfig(mode="skeleton", sample_spacing_mm=0.5, simplify_epsilon_mm=0.3,
    min_path_length_mm=1.0, dot_strategy="keep", preserve_corners=True,
    corner_angle_deg=60, straight_tol_mm=0.5, curve_epsilon_mm=0.65,
    curve_resample_step_mm=2.5, contour_max_vertices=20)
PCFG = WeldingProcessConfig(voltage=22.0, current=140.0, job=0, inductance=0.0)
WCFG = WorkspaceConfig(normal_travel_offset_mm=15.0, normal_work_offset_mm=5.0)

ce = ContourExtractor()
mapper = PoseMapper()
scheduler = PathScheduler()
planner = WeldingProcessPlanner()
pw = PointsWriter()
jw = JobWriter()
dx = DebugExporter()

def _clean(prefix):
    for f in os.listdir(str(OUT)):
        if f.startswith(prefix):
            os.unlink(str(OUT / f))

def run(text, mode, label):
    cfg = CFG_C if mode == "contour" else CFG_S
    print(f"\n{'='*60}\nE2E: '{text}' mode={mode}\n{'='*60}")

    # Step 1-2: render + extract
    strokes_raw = []
    for ch in text:
        binary = render_char(ch, FONT, FONT_SIZE)
        if mode == "contour":
            strokes = ce.extract(binary)
        else:
            strokes, sk = SkeletonExtractor.extract(binary, backend="zhang_suen")
        for s in strokes:
            assert len(s.points_px) >= 2
        strokes_raw.extend(strokes)
    print(f"  Step 1-2: {len(strokes_raw)} raw strokes")

    # Step 3: clean
    strokes_cl, _ = clean_and_resample_strokes(strokes_raw, px_per_mm=PX_PER_MM, config=cfg)
    print(f"  Step 3 clean: {len(strokes_cl)} strokes")

    # Step 4: refine
    strokes_rf, rf_s = AdaptivePathRefiner.refine_strokes(strokes_cl, cfg, px_per_mm=PX_PER_MM)
    print(f"  Step 4 refine: {len(strokes_rf)} strokes, corners={rf_s['corners_total']}, "
          f"guard={rf_s['compression_guard_triggered_count']}")

    # Step 5: schedule
    strokes_sc, sc_s = scheduler.schedule(strokes_rf, strategy="nearest", allow_reverse=True)
    print(f"  Step 5 schedule: {len(strokes_sc)} strokes, reversed={sc_s['reversed_count']}, "
          f"travel_reduction={sc_s['travel_reduction_percent']}%")

    # Step 6: map
    strokes_mp, mp_s = mapper.map_strokes(strokes_sc, WP, CANVAS_W, CANVAS_H)
    for s in strokes_mp:
        assert s.metadata.get("robot_points"), f"missing robot_points in {s.id}"
    print(f"  Step 6 map: {len(strokes_mp)} strokes, mode={mp_s['mapping_mode']}")

    # Step 7: plan
    segs, pl_s = planner.plan(strokes_mp, PCFG, workplane=WP, workspace_cfg=WCFG)
    types = [s.type for s in segs]
    print(f"  Step 7 plan: {len(segs)} segments {types}")

    # Step 8: export
    prefix = f"e2e_{label}"
    _clean(prefix)
    pt = str(OUT / f"{prefix}_points.txt")
    jb = str(OUT / f"{prefix}_job.json")
    pn = str(OUT / f"{prefix}_combined.png")

    pts_s = pw.write_points_txt(segs, pt, workplane=WP)
    jb_s = jw.write_job_json(jb, input_info={"text":text,"mode":mode},
        configs={"process":PCFG,"path":cfg,"workspace":WCFG},
        workplane=WP, strokes=strokes_mp, segments=segs,
        export_files={"points_txt":pt}, stage_stats={"plan":pl_s})
    pn_s = dx.write_combined_preview(strokes_mp, segs, pn,
        title=f"E2E: '{text}' ({mode})")
    print(f"  Step 8: pts={pts_s['row_count']} rows, "
          f"job={jb_s['file_size_bytes']}B, png={pn_s['file_size_bytes']}B")

    # Verify
    with open(pt) as f:
        assert f.readline().startswith("segment_id")
    with open(jb) as f:
        j = _json.load(f)
        assert j["schema_version"] == "welding-job-v1"
        assert len(j["segments"]) == len(segs)
    for fpath in [pt, jb, pn]:
        assert os.path.getsize(fpath) > 100

    return {"strokes_raw":len(strokes_raw), "strokes_mp":len(strokes_mp),
            "segments":len(segs), "files":(pt,jb,pn)}

# ================================================================
print("="*60); print("Part A: Contour 'O'")
ra = run("O", "contour", "A_O")
assert ra["strokes_raw"] >= 1 and ra["segments"] >= 5
with open(ra["files"][1]) as f:
    assert "overlap" in [s["type"] for s in _json.load(f)["segments"]]
print("A PASS")

print("\n"+"="*60); print("Part B: Skeleton 'A'")
rb = run("A", "skeleton", "B_A")
assert rb["strokes_raw"] >= 2 and rb["segments"] >= 6
print("B PASS")

print("\n"+"="*60); print("Part C: Contour 'AB'")
rc = run("AB", "contour", "C_AB")
assert rc["strokes_raw"] >= 3 and rc["segments"] >= 6
print("C PASS")

print("\n"+"="*60); print("Part D: Skeleton 'i'")
rd = run("i", "skeleton", "D_i")
assert rd["strokes_raw"] >= 2 and rd["segments"] >= 3
print("D PASS")

print("\n"+"="*60); print("Part E: No Lua leakage")
for r in [ra,rb,rc,rd]:
    for fp in r["files"][:2]:
        with open(fp) as f:
            raw = f.read().lower()
        for kw in ["setwelderparam","arcon","arcoff",".lua"]:
            assert kw not in raw, f"E: {kw} in {fp}"
print("E PASS")

print("\n"+"="*60); print("Part F: segment_id cross-ref")
for r in [ra,rb,rc,rd]:
    pt_f, jb_f = r["files"][0], r["files"][1]
    with open(pt_f) as f:
        pt_ids = set(l.split(",")[0] for l in f.readlines()[1:] if l.strip())
    with open(jb_f) as f:
        jb_ids = set(s["id"] for s in _json.load(f)["segments"])
    assert pt_ids == jb_ids, f"F: id mismatch: {len(pt_ids)} vs {len(jb_ids)}"
print("F PASS: all segment_ids match between points.txt and job.json")

print("\n"+"="*60); print("GENERATED FILES:")
for r, name in [(ra,"A_O"),(rb,"B_A"),(rc,"C_AB"),(rd,"D_i")]:
    print(f"  {name}: ", end="")
    for fp in r["files"]:
        print(f"{Path(fp).name}({os.path.getsize(fp):,}B) ", end="")
    print()

print(f"\n{'='*60}\nALL PHASE 8.1 END-TO-END TESTS PASSED\n{'='*60}")
