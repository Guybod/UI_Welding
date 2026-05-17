"""Phase 9.e: Contour multiline layout — line_spacing, overflow, order, Beta flags."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner
from pipeline.multiline_layout import line_step_mm
from pipeline.output.preview_writer import _uv_projector

WP_LARGE = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(600, 0, 100, 180, 0, 90),
    RobotPoint(0, 600, 100, 180, 0, 90),
)
WP_SMALL = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(200, 0, 100, 180, 0, 90),
    RobotPoint(0, 150, 100, 180, 0, 90),
)


def _load_layout(summary_path: str) -> dict:
    with open(summary_path, encoding="utf-8") as f:
        return json.load(f).get("layout", {})


def _weld_uv_v_values(points_path: str, workplane: WorkPlane) -> list[float]:
    to_uv = _uv_projector(workplane)
    vs: list[float] = []
    with open(points_path, encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 14 and parts[2] == "weld":
                rp = RobotPoint(
                    float(parts[4]), float(parts[5]), float(parts[6]),
                    float(parts[7]), float(parts[8]), float(parts[9]),
                )
                vs.append(to_uv(rp)[1])
    return vs


def _first_last_line_v(points_path: str, wp: WorkPlane) -> tuple[float, float]:
    """按 points 文件顺序：前 1/3 weld 点 V 中位 vs 后 1/3。"""
    vs = _weld_uv_v_values(points_path, wp)
    if len(vs) < 4:
        return vs[0] if vs else 0.0, vs[-1] if vs else 0.0
    n = len(vs)
    k = max(1, n // 3)
    first = sorted(vs[:k])[k // 2]
    last = sorted(vs[-k:])[k // 2]
    return first, last


# ============================================================
# Test 1: basic multiline generation
# ============================================================
print("=" * 60)
print("Test 1: multiline basic AB\\nCD")
runner = OfflinePipelineRunner(
    output_dir="output",
    char_height_mm=100.0,
    char_spacing_mm=20.0,
    line_spacing_mm=30.0,
)
res = runner.run("AB\nCD", mode="contour", workplane=WP_LARGE)
assert res.ok, res.errors
layout = _load_layout(os.path.join(res.output_dir, "summary.json"))
assert layout.get("multiline_enabled") is True, layout
assert layout.get("line_count") == 2, layout
assert layout.get("beta_layout_used") is False, layout
assert os.path.isfile(os.path.join(res.output_dir, "preview_execution.png"))
assert os.path.isfile(res.files.get("points_txt", ""))
assert os.path.isfile(res.files.get("lua_script", ""))
exp_h = 2 * 100.0 + 30.0
meas_h = float(layout.get("measured_text_height_mm", 0))
assert 200 <= meas_h <= 280, f"height {meas_h} not near {exp_h}"
print(f"  measured_text_height_mm={meas_h:.1f} (expect ~{exp_h}) PASS")
print(f"  line_count={layout.get('line_count')} multiline_enabled PASS")

# ============================================================
# Test 2: line_spacing monotonic
# ============================================================
print("\n" + "=" * 60)
print("Test 2: line_spacing 0 / 20 / 50 (text=A\\nB)")
heights: dict[float, float] = {}
for ls in (0.0, 20.0, 50.0):
    r = OfflinePipelineRunner(
        output_dir="output", char_height_mm=100.0, line_spacing_mm=ls,
    ).run("A\nB", mode="contour", workplane=WP_LARGE)
    assert r.ok, r.errors
    ly = _load_layout(os.path.join(r.output_dir, "summary.json"))
    heights[ls] = float(ly.get("measured_text_height_mm", 0))
    print(f"  line_spacing={ls:.0f}mm → height={heights[ls]:.1f}mm")
assert heights[50] > heights[20] > heights[0], heights
print("  PASS: height_50 > height_20 > height_0")

# ============================================================
# Test 3: char_spacing on multiline
# ============================================================
print("\n" + "=" * 60)
print("Test 3: char_spacing on multiline AB\\nCD")
widths: dict[float, float] = {}
for cs in (0.0, 20.0, 50.0):
    r = OfflinePipelineRunner(
        output_dir="output", char_height_mm=100.0, char_spacing_mm=cs,
        line_spacing_mm=20.0,
    ).run("AB\nCD", mode="contour", workplane=WP_LARGE)
    assert r.ok, r.errors
    ly = _load_layout(os.path.join(r.output_dir, "summary.json"))
    widths[cs] = float(ly.get("measured_text_width_mm", 0))
    print(f"  char_spacing={cs:.0f}mm → width={widths[cs]:.1f}mm")
assert widths[50] > widths[20] > widths[0], widths
print("  PASS: width monotonic")

# ============================================================
# Test 4: overflow
# ============================================================
print("\n" + "=" * 60)
print("Test 4: multiline overflow")
r_fail = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100.0, line_spacing_mm=50.0,
).run("AB\nCD", mode="contour", workplane=WP_SMALL)
assert not r_fail.ok, "expected overflow failure"
ly_fail = _load_layout(os.path.join(r_fail.output_dir, "summary.json"))
assert ly_fail.get("layout_fits_workspace") is False
oh = float(ly_fail.get("layout_overflow_height_mm", 0))
assert oh > 0, ly_fail
req_h = 2 * 100 + 50
print(f"  required_height≈{req_h}mm overflow_h={oh:.1f}mm PASS")

# ============================================================
# Test 5: row order (first line lower V than second)
# ============================================================
print("\n" + "=" * 60)
print("Test 5: stroke order / line Y separation")
r_ord = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100.0, line_spacing_mm=30.0,
).run("AB\nCD", mode="contour", workplane=WP_LARGE)
pts = r_ord.files.get("points_txt", "")
v_first, v_last = _first_last_line_v(pts, WP_LARGE)
assert v_first < v_last, f"first line V ({v_first}) should be < second ({v_last})"
with open(os.path.join(r_ord.output_dir, "summary.json"), encoding="utf-8") as f:
    stages = json.load(f).get("stage_stats", [])
sched = next(s for s in stages if s.get("name") == "schedule")
assert sched.get("stats", {}).get("strategy") == "by_line_groups", sched
print(f"  V_first={v_first:.1f} < V_last={v_last:.1f}, schedule=by_line_groups PASS")

# ============================================================
# Test 6: Beta detection
# ============================================================
print("\n" + "=" * 60)
print("Test 6: detect_beta_features")
from app.pages.welding_page import detect_beta_features, normalize_weld_text_input
from config.welding_defaults import LINE_SPACING_MM

base = dict(
    text="A", mode="contour", line_spacing_mm=LINE_SPACING_MM,
    align="center", direction="horizontal", flow="ltr",
)
assert detect_beta_features(**{**base, "text": "A\nB"}) == [], (
    detect_beta_features(**{**base, "text": "A\nB"})
)
sk = detect_beta_features(**{**base, "text": "A\nB", "mode": "skeleton"})
assert "多行文字" in sk, sk
print("  contour A\\nB: no multiline beta PASS")
print(f"  skeleton A\\nB: {sk} PASS")

# ============================================================
# Test 7: single line unaffected by line_spacing
# ============================================================
print("\n" + "=" * 60)
print("Test 7: single line line_spacing no effect")
h0 = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100.0, line_spacing_mm=0.0,
).run("AB", mode="contour", workplane=WP_LARGE)
h50 = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100.0, line_spacing_mm=50.0,
).run("AB", mode="contour", workplane=WP_LARGE)
assert h0.ok and h50.ok
ly0 = _load_layout(os.path.join(h0.output_dir, "summary.json"))
ly50 = _load_layout(os.path.join(h50.output_dir, "summary.json"))
assert ly0.get("line_count") == 1
assert abs(float(ly0["measured_text_height_mm"]) - float(ly50["measured_text_height_mm"])) < 5.0
print("  single-line height ~same with line_spacing 0 vs 50 PASS")

print("\n" + "=" * 60)
print("Test 8: normalize_weld_text_input (literal \\\\n)")
assert normalize_weld_text_input("AB\\nCD") == "AB\nCD"
assert normalize_weld_text_input("A\nB") == "A\nB"
assert normalize_weld_text_input("AB\r\nCD") == "AB\nCD"
print("  literal \\\\n → real newline PASS")

print("\n" + "=" * 60)
print("ALL MULTILINE LAYOUT TESTS PASSED")
print("=" * 60)
