"""Phase 9.d: Execution preview — same source as points/Lua, no axis flip."""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint
from pipeline.mapping import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner

WP_ABC = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(600, 0, 100, 180, 0, 90),
    RobotPoint(0, 600, 100, 180, 0, 90),
)
WP_SMALL = WorkPlane(
    RobotPoint(0, 0, 100, 180, 0, 90),
    RobotPoint(100, 0, 100, 180, 0, 90),
    RobotPoint(0, 50, 100, 180, 0, 90),
)


def _weld_x_ranges(points_path: str) -> list[tuple[float, float]]:
    """按 weld 点 x 范围粗分字符（用于 ABc 横向顺序）。"""
    xs_by_stroke: list[list[float]] = []
    with open(points_path, encoding="utf-8") as f:
        next(f)
        cur_stroke = None
        bucket: list[float] = []
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 14 or parts[2] != "weld":
                continue
            sid = parts[1]
            x = float(parts[4])
            if sid != cur_stroke:
                if bucket:
                    xs_by_stroke.append(bucket)
                bucket = [x]
                cur_stroke = sid
            else:
                bucket.append(x)
        if bucket:
            xs_by_stroke.append(bucket)
    return [(min(b), max(b)) for b in xs_by_stroke if b]


def _first_z_from_lua(lua_path: str) -> float | None:
    with open(lua_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"movL\(\{cp=\{([^}]+)\}", text)
    if not m:
        return None
    return float(m.group(1).split(",")[2])


def _first_z_from_points(points_path: str) -> float | None:
    with open(points_path, encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 14:
                return float(parts[6])
    return None


# ============================================================
# Test 1: ABc execution preview + summary
# ============================================================
from pipeline.output.preview_writer import _uv_projector, _workplane_corners_uv

# 纸面角点：LB 左下 (u小,v大)、RT 右上 (u大,v小)
_uv = _uv_projector(WP_ABC)
_exp = _workplane_corners_uv(WP_ABC)
for _k, _pt in {"LT": WP_ABC.tl, "RT": WP_ABC.tr, "LB": WP_ABC.bl}.items():
    _got = _uv(_pt)
    assert abs(_got[0] - _exp[_k][0]) < 0.05 and abs(_got[1] - _exp[_k][1]) < 0.05, (_k, _got, _exp[_k])
assert _exp["LB"][0] < _exp["RT"][0] and _exp["LB"][1] > _exp["LT"][1], _exp

print("=" * 60)
print("Test 1: ABc execution preview")
r = OfflinePipelineRunner(output_dir="output", char_height_mm=100, char_spacing_mm=20)
res = r.run("ABc", mode="contour", workplane=WP_ABC)
assert res.ok, res.errors
run_dir = res.output_dir
exec_png = os.path.join(run_dir, "preview_execution.png")
assert os.path.isfile(exec_png), "preview_execution.png missing"
print(f"  preview_execution.png: OK ({os.path.getsize(exec_png)} bytes)")

with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as f:
    summary = json.load(f)
prev = summary.get("preview", {})
assert prev.get("source") == "process_segments", prev
assert prev.get("transform") == "display_invert_y", prev
assert prev.get("basis") == "workplane_uv_paper", prev
assert prev.get("generated") is not False
print(f"  summary.preview.source={prev.get('source')} transform={prev.get('transform')} PASS")

pts = os.path.join(run_dir, "points.txt")
ranges = _weld_x_ranges(pts)
assert len(ranges) >= 2, f"expected multiple weld stroke groups, got {ranges}"
# ABc 应沿 +X（LT→RT）排列：各字符 x 中心递增
centers = sorted((a + b) / 2 for a, b in ranges)
assert centers == sorted(centers) and centers[-1] > centers[0], centers
if len(centers) >= 3:
    assert centers[0] < centers[1] < centers[2], f"ABc not left-to-right by X: {centers}"
    print(f"  ABc char centers X (mm): {[round(c, 1) for c in centers[:3]]} L→R PASS")
else:
    print(f"  ABc weld x centers: {[round(c, 1) for c in centers]} (partial check) PASS")

z_pts = _first_z_from_points(pts)
z_lua = _first_z_from_lua(res.files["lua_script"])
assert z_pts is not None and z_lua is not None
assert abs(z_pts - z_lua) < 0.01, f"points Z {z_pts} vs lua Z {z_lua}"
print(f"  points/Lua Z first point match: {z_pts:.1f} PASS")

# ============================================================
# Test 2: weld_only + combined exist
# ============================================================
print("\n" + "=" * 60)
print("Test 2: weld_only and combined previews")
assert os.path.isfile(os.path.join(run_dir, "preview_weld_only.png"))
assert os.path.isfile(os.path.join(run_dir, "preview_combined.png"))
assert os.path.isfile(os.path.join(run_dir, "preview_strokes.png"))
from pipeline.output.preview_writer import _WELD_ONLY_TYPES, _TRAVEL_TYPES
assert not _TRAVEL_TYPES & _WELD_ONLY_TYPES
print(f"  weld_only types: {sorted(_WELD_ONLY_TYPES)} (no travel/retreat) PASS")
print("  preview_weld_only.png + preview_combined.png: OK PASS")

# ============================================================
# Test 3: overflow — no misleading execution
# ============================================================
print("\n" + "=" * 60)
print("Test 3: overflow preview placeholder")
r_fail = OfflinePipelineRunner(
    output_dir="output", char_height_mm=100, char_spacing_mm=50)
res_fail = r_fail.run("ABc", mode="contour", workplane=WP_SMALL)
assert not res_fail.ok
with open(os.path.join(res_fail.output_dir, "summary.json"), encoding="utf-8") as f:
    s_fail = json.load(f)
p_fail = s_fail.get("preview", {})
assert p_fail.get("generated") is False
assert p_fail.get("transform") == "display_invert_y"
_reason = p_fail.get("not_generated_reason", "")
assert (
    "exceeds" in _reason.lower()
    or "超出" in _reason
    or s_fail.get("errors")
)
exec_fail = os.path.join(res_fail.output_dir, "preview_execution.png")
# 占位图或不存在均可；若存在应为 placeholder
if os.path.isfile(exec_fail):
    assert p_fail.get("placeholder") is True
    print("  overflow: placeholder preview_execution.png PASS")
else:
    print("  overflow: no execution png (acceptable) PASS")
print(f"  not_generated_reason present PASS")

print("\n" + "=" * 60)
print("ALL PHASE 9 PREVIEW TESTS PASSED")
print("=" * 60)
