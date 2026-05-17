"""Phase 9.6-c: Layout parameter verification — char height, spacing, overflow, summary layout."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner

# ── 工作区 ──
WP_LARGE = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(600, 0, 100, 180, 0, 90),
    RobotPoint(0, 600, 100, 180, 0, 90),
)
WP_SMALL = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(100, 0, 100, 180, 0, 90),
    RobotPoint(0, 50, 100, 180, 0, 90),
)

LAYOUT_KEYS = (
    "mapping_mode",
    "pixel_per_mm_used",
    "font_size_px_used",
    "char_height_mm_requested",
    "char_height_mm_measured",
    "char_spacing_mm_requested",
    "measured_text_width_mm",
    "measured_text_height_mm",
    "workspace_width_mm",
    "workspace_height_mm",
    "layout_fits_workspace",
    "layout_overflow_width_mm",
    "layout_overflow_height_mm",
    "beta_layout_used",
)


def _weld_bbox_from_points_txt(path: str) -> tuple[float, float, float, float]:
    """返回 xmin, xmax, ymin, ymax；仅统计 weld 段。"""
    xs, ys = [], []
    with open(path, encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 14 and parts[2] == "weld":
                xs.append(float(parts[4]))
                ys.append(float(parts[5]))
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), max(xs), min(ys), max(ys)


def _weld_size_mm(points_path: str) -> tuple[float, float]:
    xmin, xmax, ymin, ymax = _weld_bbox_from_points_txt(points_path)
    return xmax - xmin, ymax - ymin


def _char_centers_x(points_path: str, text: str) -> list[float]:
    """按 weld 点 x 范围粗分字符中心（用于字距中心距）。"""
    buckets: dict[int, list[float]] = {i: [] for i in range(len(text))}
    xmin, xmax, ymin, ymax = _weld_bbox_from_points_txt(points_path)
    if xmax <= xmin:
        return []
    span = (xmax - xmin) / max(len(text), 1)
    with open(points_path, encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 14 and parts[2] == "weld":
                x = float(parts[4])
                idx = min(len(text) - 1, max(0, int((x - xmin) / span)))
                buckets[idx].append(x)
    centers = []
    for i in range(len(text)):
        if buckets[i]:
            centers.append(sum(buckets[i]) / len(buckets[i]))
    return centers


def _height_ok(measured: float, target: float) -> bool:
    tol = max(2.0, target * 0.05)
    return abs(measured - target) <= tol


def _load_layout(summary_path: str) -> dict:
    with open(summary_path, encoding="utf-8") as f:
        data = json.load(f)
    layout = data.get("layout")
    if layout:
        return layout
    for st in data.get("stage_stats", []):
        if st.get("name") == "map" and st.get("stats"):
            return st["stats"]
    return {}


def _assert_layout_keys(layout: dict, ctx: str = "") -> None:
    missing = [k for k in LAYOUT_KEYS if k not in layout]
    assert not missing, f"{ctx} summary layout missing keys: {missing}"


# ============================================================
# Test A: char_height 50 / 100 mm (text="A")
# ============================================================
print("=" * 60)
print("Test A: char_height 50 / 100 mm (text='A')")

heights: dict[int, float] = {}
for target_h in (50, 100):
    runner = OfflinePipelineRunner(
        output_dir="output",
        char_height_mm=float(target_h),
        char_spacing_mm=0.0,
    )
    res = runner.run("A", mode="contour", workplane=WP_LARGE)
    assert res.ok, f"char_height={target_h} failed: {res.errors}"
    pts = os.path.join(res.output_dir, "points.txt")
    assert os.path.isfile(pts), "points.txt missing"
    w_mm, h_mm = _weld_size_mm(pts)
    heights[target_h] = h_mm
    ok = _height_ok(h_mm, target_h)
    status = "PASS" if ok else "FAIL"
    print(f"  char_height={target_h} → measured={h_mm:.1f}mm (width={w_mm:.1f}mm) {status}")
    assert ok, f"height {h_mm:.1f} not within tolerance of {target_h}"

ratio = heights[100] / heights[50] if heights[50] > 0 else 0
print(f"  height ratio 100/50 = {ratio:.2f} (expect ~2.0)")
assert 1.85 <= ratio <= 2.15, f"height ratio out of range: {ratio:.2f}"
print("  PASS: char_height 50/100mm absolute sizing")

# ============================================================
# Test B: char_spacing 0 / 20 / 50 mm (text="AB", char_h=100)
# ============================================================
print("\n" + "=" * 60)
print("Test B: char_spacing 0 / 20 / 50 mm (text='AB', char_height=100)")

widths: dict[int, float] = {}
center_dists: dict[int, float] = {}
for spacing in (0, 20, 50):
    runner = OfflinePipelineRunner(
        output_dir="output",
        char_height_mm=100.0,
        char_spacing_mm=float(spacing),
    )
    res = runner.run("AB", mode="contour", workplane=WP_LARGE)
    assert res.ok, f"spacing={spacing} failed: {res.errors}"
    pts = os.path.join(res.output_dir, "points.txt")
    w_mm, h_mm = _weld_size_mm(pts)
    widths[spacing] = w_mm
    centers = _char_centers_x(pts, "AB")
    if len(centers) >= 2:
        center_dists[spacing] = centers[1] - centers[0]
    print(f"  spacing={spacing}mm: width={w_mm:.1f}mm height={h_mm:.1f}mm", end="")
    if spacing in center_dists:
        print(f" center_dist={center_dists[spacing]:.1f}mm")
    else:
        print()

assert widths[50] > widths[20] > widths[0], f"width NOT monotonic: {widths}"
print(
    f"  PASS: width_50({widths[50]:.0f}) > width_20({widths[20]:.0f}) "
    f"> width_0({widths[0]:.0f})"
)
if len(center_dists) == 3:
    assert center_dists[50] > center_dists[20] > center_dists[0], (
        f"center distance NOT monotonic: {center_dists}"
    )
    print(
        f"  PASS: center_dist_50({center_dists[50]:.0f}) > "
        f"center_dist_20({center_dists[20]:.0f}) > center_dist_0({center_dists[0]:.0f})"
    )

# ============================================================
# Test C: workspace overflow — reject, no auto-scale
# ============================================================
print("\n" + "=" * 60)
print("Test C: workspace overflow (ABc, 100x50mm workspace)")

runner_of = OfflinePipelineRunner(
    output_dir="output",
    char_height_mm=100.0,
    char_spacing_mm=50.0,
    allow_overflow=False,
)
res_of = runner_of.run("ABc", mode="contour", workplane=WP_SMALL)
assert not res_of.ok, "overflow case must fail (ok=True unexpected)"
assert res_of.errors, "overflow case must have errors"

err_text = " ".join(res_of.errors).lower()
assert (
    "exceeds workplane" in err_text
    or "shortage" in err_text
    or "超出工作区" in err_text
    or "缺口" in " ".join(res_of.errors)
), f"error message missing overflow hint: {res_of.errors}"

summary_path = res_of.files.get("summary_json") or os.path.join(
    res_of.output_dir, "summary.json"
)
layout_of = _load_layout(summary_path)
_assert_layout_keys(layout_of, "overflow")

assert layout_of.get("layout_fits_workspace") is False
ow = float(layout_of.get("layout_overflow_width_mm") or 0)
oh = float(layout_of.get("layout_overflow_height_mm") or 0)
assert ow > 0 or oh > 0, f"overflow fields should be >0: width={ow} height={oh}"

req_w = layout_of.get("required_width_mm") or layout_of.get("shortage_width_mm")
avail_w = layout_of.get("available_width_mm") or layout_of.get("workspace_width_mm")
short_w = layout_of.get("shortage_width_mm") or ow

points_path = os.path.join(res_of.output_dir, "points.txt")
if os.path.isfile(points_path):
    w_bad, h_bad = _weld_size_mm(points_path)
    assert w_bad < 200 and h_bad < 150, (
        "unexpected full-size points.txt on overflow reject"
    )

print(
    f"  workspace={layout_of.get('workspace_width_mm')}x"
    f"{layout_of.get('workspace_height_mm')}mm"
)
print(
    f"  required={layout_of.get('required_width_mm')}x"
    f"{layout_of.get('required_height_mm')}mm"
)
print(f"  shortage_w={short_w}mm shortage_h={layout_of.get('shortage_height_mm')}mm")
print("  rejected PASS")

# ============================================================
# Test D: summary.json layout fields (normal run)
# ============================================================
print("\n" + "=" * 60)
print("Test D: summary.json layout fields (normal AB run)")

runner_ok = OfflinePipelineRunner(
    output_dir="output",
    char_height_mm=100.0,
    char_spacing_mm=20.0,
)
res_ok = runner_ok.run("AB", mode="contour", workplane=WP_LARGE)
assert res_ok.ok
summary_path_ok = res_ok.files.get("summary_json") or os.path.join(
    res_ok.output_dir, "summary.json"
)
with open(summary_path_ok, encoding="utf-8") as f:
    summary_doc = json.load(f)

layout_ok = _load_layout(summary_path_ok)
_assert_layout_keys(layout_ok, "normal")

assert layout_ok.get("layout_fits_workspace") is True
assert float(layout_ok.get("layout_overflow_width_mm") or 0) < 0.1
assert float(layout_ok.get("layout_overflow_height_mm") or 0) < 0.1
assert layout_ok.get("beta_layout_used") is False
assert layout_ok.get("mapping_mode") == "linear_mm_per_px"

print("  layout excerpt:")
for key in LAYOUT_KEYS:
    print(f"    {key}: {layout_ok.get(key)}")

# ============================================================
# Test E: Beta / multi-line status (informational)
# ============================================================
print("\n" + "=" * 60)
print("Test E: Multi-line contour formal / skeleton Beta (informational)")
res_ml = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100.0, line_spacing_mm=20.0,
).run("A\nB", mode="contour", workplane=WP_LARGE)
assert res_ml.ok, res_ml.errors
with open(os.path.join(res_ml.output_dir, "summary.json"), encoding="utf-8") as f:
    ly_ml = json.load(f).get("layout", {})
assert ly_ml.get("multiline_enabled") is True
assert ly_ml.get("beta_layout_used") is False
print(f"  contour multi-line OK={res_ml.ok} multiline_enabled=True PASS")
print("  Alignment/Direction/Flow: UI only, not in pipeline")

# ============================================================
# Test F: WeldingPage Beta detection (UI logic, no pipeline)
# ============================================================
print("\n" + "=" * 60)
print("Test F: Beta feature detection (welding_page)")

from app.pages.welding_page import detect_beta_features
from config.welding_defaults import LINE_SPACING_MM as _LS

_base = dict(
    mode="contour",
    text="ABc",
    line_spacing_mm=_LS,
    align="center",
    direction="horizontal",
    flow="ltr",
)
assert detect_beta_features(**_base) == [], f"formal line should have no beta: {detect_beta_features(**_base)}"
print("  formal contour single-line: no Beta flags PASS")

sk = detect_beta_features(**{**_base, "mode": "skeleton"})
assert "骨架字" in sk
print(f"  skeleton mode: {sk} PASS")

ml_c = detect_beta_features(**{**_base, "text": "A\nB"})
assert ml_c == [], f"contour multiline not beta: {ml_c}"
print(f"  contour multiline: {ml_c} PASS")
ml_s = detect_beta_features(**{**_base, "text": "A\nB", "mode": "skeleton"})
assert "多行文字" in ml_s
print(f"  skeleton multiline: {ml_s} PASS")

layout_beta = detect_beta_features(**{**_base, "align": "left", "direction": "vertical", "flow": "rtl"})
assert "对齐模式" in layout_beta and "排版方向" in layout_beta and "流向" in layout_beta
print(f"  non-default align/direction/flow: {layout_beta} PASS")

ls_single = detect_beta_features(**{**_base, "line_spacing_mm": _LS + 1.0})
assert "行距" not in ls_single, f"single-line line_spacing not beta: {ls_single}"
print(f"  single-line non-default line_spacing: not beta PASS")
ls_ml = detect_beta_features(**{**_base, "text": "A\nB", "line_spacing_mm": _LS + 1.0})
assert "行距" not in ls_ml, f"contour multiline line_spacing formal: {ls_ml}"
print(f"  contour multiline line_spacing: not beta PASS")

print("\n" + "=" * 60)
print("ALL PHASE 9.6-c LAYOUT TESTS PASSED")
print("=" * 60)
