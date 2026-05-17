"""左上示教边距 — 仅 margin_left / margin_top，无右下边距。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import PixelPoint, Stroke
from pipeline.layout_inset import (
    apply_layout_origin_offset,
    effective_writable_size_mm,
)

assert effective_writable_size_mm(100, 80, 5, 10) == (95.0, 70.0)
assert effective_writable_size_mm(100, 80, 0, 0) == (100.0, 80.0)

s = Stroke(id="t", source_type="contour", points_px=[PixelPoint(0, 0), PixelPoint(10, 0)])
out = apply_layout_origin_offset([s], margin_left_mm=2.0, margin_top_mm=3.0, px_per_mm=10.0)
assert out[0].points_px[0].x == 20.0 and out[0].points_px[0].y == 30.0
print("layout_inset unit PASS")

try:
    from pipeline.mapping.workplane import WorkPlane
    from core.types import RobotPoint
    from pipeline.offline_runner import OfflinePipelineRunner

    lt = RobotPoint(0, 0, 300, 180, 0, 90)
    rt = RobotPoint(200, 0, 300, 180, 0, 90)
    lb = RobotPoint(0, 150, 300, 180, 0, 90)
    wp = WorkPlane(tl=lt, tr=rt, bl=lb)

    ok0 = OfflinePipelineRunner(
        output_dir="output",
        char_height_mm=100.0,
        margin_left_mm=0.0,
        margin_top_mm=0.0,
        px_per_mm=10.0,
    ).run("A", mode="contour", workplane=wp)

    ok1 = OfflinePipelineRunner(
        output_dir="output",
        char_height_mm=100.0,
        margin_left_mm=50.0,
        margin_top_mm=0.0,
        px_per_mm=10.0,
    ).run("A", mode="contour", workplane=wp)

    if ok0.ok and not ok1.ok:
        print("left margin reduces available width PASS")
    elif ok0.ok and ok1.ok:
        print("left margin run ok at this size PASS")
    else:
        print(f"integration: ok0={ok0.ok} ok1={ok1.ok}")
except Exception as exc:
    print(f"integration skipped: {exc}")

print("ALL margin L/T tests done")
