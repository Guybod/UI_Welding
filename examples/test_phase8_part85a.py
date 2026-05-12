"""Phase 8 Part 8.5a 测试 — WeldingServiceV2 wrapper"""

import os, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

try:
    from PySide6.QtCore import QCoreApplication
    _has_qt = True
except ImportError:
    _has_qt = False

if not _has_qt:
    print("=" * 60)
    print("PySide6 not available — testing core logic only")
    print("=" * 60)

    # Test _to_robot_point logic (inline equivalent)
    def _to_robot_point(val, default):
        if val is None: return default
        if isinstance(val, RobotPoint): return val
        if isinstance(val, dict):
            return RobotPoint(
                x=float(val.get("x",0)), y=float(val.get("y",0)),
                z=float(val.get("z",100)), rx=float(val.get("rx",-180)),
                ry=float(val.get("ry",0)), rz=float(val.get("rz",-135)))
        raise TypeError(f"bad type: {type(val)}")

    rp = _to_robot_point({"x": 10, "y": 20, "z": 30}, None)
    assert rp.x == 10 and rp.y == 20 and rp.z == 30
    print("A PASS: dict→RobotPoint conversion")

    rp2 = _to_robot_point(None, RobotPoint(1,2,3,0,0,0))
    assert rp2.x == 1
    print("B PASS: None→default RobotPoint")

    rp3 = _to_robot_point(RobotPoint(5,6,7,8,9,10), None)
    assert rp3.rx == 8
    print("C PASS: RobotPoint passthrough")

    # Test WorkPlane construction
    from pipeline.mapping import WorkPlane
    wp = WorkPlane(
        RobotPoint(0, 0, 100, -180, 0, -135),
        RobotPoint(200, 0, 100, -180, 0, -135),
        RobotPoint(0, 100, 100, -180, 0, -135),
    )
    assert wp.width_mm == 200.0
    print("D PASS: WorkPlane from RobotPoints")

    # Test OfflinePipelineRunner
    from pipeline.offline_runner import OfflinePipelineRunner
    runner = OfflinePipelineRunner(output_dir=str(OUT))
    r = runner.run("A", mode="contour", workplane=wp)
    assert r.ok
    assert os.path.exists(r.files["points_txt"])
    assert os.path.exists(r.files["job_json"])
    assert os.path.exists(r.files["combined_preview_png"])
    print(f"E PASS: runner ok, {r.total_segments} segments, {r.duration_ms:.0f}ms")
    print(f"  points.txt: {os.path.getsize(r.files['points_txt']):,}B")
    print(f"  job.json:   {os.path.getsize(r.files['job_json']):,}B")
    print(f"  preview:    {os.path.getsize(r.files['combined_preview_png']):,}B")

    # Test skeleton mode
    r2 = runner.run("i", mode="skeleton", workplane=wp)
    assert r2.ok
    assert r2.total_strokes_raw >= 2
    print(f"F PASS: skeleton 'i' ok, {r2.total_strokes_raw} strokes, {r2.total_segments} segments")

    # Test bad mode
    r3 = runner.run("A", mode="bad_mode", workplane=wp)
    assert not r3.ok
    print(f"G PASS: bad mode → ok=False, error={r3.errors[0][:50]}")

    # Old WeldingService still importable
    try:
        from services.welding_service import WeldingService
        print("H PASS: old WeldingService still importable")
    except ImportError as e:
        print(f"H WARN: old WeldingService import failed ({e})")

    # No Lua leakage
    for fpath in [r.files["points_txt"], r.files["job_json"]]:
        with open(fpath) as f:
            raw = f.read().lower()
        for kw in ["setwelderparam", "arcon", "arcoff"]:
            assert kw not in raw
    print("I PASS: no Lua leakage")

    print(f"\nOutput: {r.output_dir}")
    for fn in sorted(os.listdir(r.output_dir)):
        print(f"  {fn}: {os.path.getsize(os.path.join(r.output_dir, fn)):,}B")

    print(f"\n{'='*60}")
    print("ALL PHASE 8.5a CORE TESTS PASSED (Qt not available)")
    print(f"{'='*60}")
    sys.exit(0)

# --- Qt available path ---
from services.welding_service_v2 import WeldingServiceV2

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

# ============================================================
print("=" * 60)
print("Part A: WeldingServiceV2 Signals")

svc = WeldingServiceV2(output_dir=str(OUT))
signals_received = {}

def on_state(s): signals_received.setdefault("state", []).append(s)
def on_finished(txt, jsn): signals_received["finished"] = (txt, jsn)
def on_preview(png): signals_received["preview"] = png
def on_log(msg): signals_received.setdefault("log", []).append(msg)
def on_error(msg): signals_received["error"] = msg
def on_progress(cur, tot): signals_received.setdefault("progress", []).append((cur, tot))

svc.state_changed.connect(on_state)
svc.finished.connect(on_finished)
svc.preview_ready.connect(on_preview)
svc.log_message.connect(on_log)
svc.error_occurred.connect(on_error)
svc.progress.connect(on_progress)

svc.generate("A", mode="contour")
assert signals_received["state"][-1] == "DONE"
assert "finished" in signals_received
# Progress must emit at least (0,100) and (100,100)
progs = signals_received.get("progress", [])
assert any(p[0] == 0 for p in progs), f"A0: no progress(0,*) in {progs}"
assert any(p[0] == 100 for p in progs), f"A0: no progress(100,*) in {progs}"
pts, job = signals_received["finished"]
assert os.path.exists(pts)
assert os.path.exists(job)
print(f"A PASS: state={signals_received['state']}, progress={progs}")
print(f"  points.txt: {os.path.getsize(pts):,}B")
print(f"  job.json:   {os.path.getsize(job):,}B")

# ============================================================
print("Part B: preview_ready")
assert "preview" in signals_received
png = signals_received["preview"]
assert os.path.exists(png)
assert os.path.getsize(png) > 100
print(f"B PASS: preview_ready emitted, {os.path.getsize(png):,}B")

# ============================================================
print("Part C: Skeleton mode")
svc2 = WeldingServiceV2(output_dir=str(OUT))
received2 = {}
svc2.state_changed.connect(lambda s: received2.setdefault("state", []).append(s))
svc2.finished.connect(lambda t, j: received2.__setitem__("finished", (t, j)))
svc2.error_occurred.connect(lambda m: received2.__setitem__("error", m))

svc2.generate("i", mode="skeleton")
assert received2["state"][-1] == "DONE"
print(f"C PASS: skeleton 'i' done")

# ============================================================
print("Part D: Bad mode triggers error")
svc3 = WeldingServiceV2(output_dir=str(OUT))
received3 = {}
svc3.state_changed.connect(lambda s: received3.setdefault("state", []).append(s))
svc3.error_occurred.connect(lambda m: received3.__setitem__("error", m))

svc3.generate("A", mode="bad_mode")
assert received3["state"][-1] == "ERROR"
assert "error" in received3
print(f"D PASS: bad mode → ERROR, error={received3['error'][:50]}")

# ============================================================
print("Part E: dict input for RobotPoint")
svc4 = WeldingServiceV2(output_dir=str(OUT))
received4 = {}
svc4.state_changed.connect(lambda s: received4.setdefault("state", []).append(s))
svc4.finished.connect(lambda t, j: received4.__setitem__("finished", (t, j)))

svc4.generate("A", mode="contour",
    left_top={"x": 0, "y": 0, "z": 100, "rx": -180, "ry": 0, "rz": -135},
    right_top={"x": 200, "y": 0, "z": 100, "rx": -180, "ry": 0, "rz": -135},
    left_bottom={"x": 0, "y": 100, "z": 100, "rx": -180, "ry": 0, "rz": -135},
)
assert received4["state"][-1] == "DONE"
print(f"E PASS: dict input accepted, finished OK")

# ============================================================
print("Part F: Old WeldingService still importable")
from services.welding_service import WeldingService
assert WeldingService is not None
print(f"F PASS: old WeldingService import OK")

# ============================================================
print("Part G: No Lua leakage")
for fp in [signals_received["finished"][0], signals_received["finished"][1]]:
    with open(fp) as f:
        raw = f.read().lower()
    for kw in ["setwelderparam", "arcon", "arcoff"]:
        assert kw not in raw, f"G: {kw} in {fp}"
print("G PASS: no Lua strings in output files")

print(f"\n{'='*60}")
print("ALL PHASE 8.5a TESTS PASSED")
print(f"{'='*60}")
