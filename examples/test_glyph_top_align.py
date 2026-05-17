"""墨迹顶边对齐：上边距=0 时首行 min_y 应接近 0（多行 Ab3\\nBG2）。"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.mapping.workplane import WorkPlane
from pipeline.offline_runner import OfflinePipelineRunner
from core.types import RobotPoint

FONTS = {
    "msyh": os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "msyh.ttc"),
    "simhei": os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "simhei.ttf"),
    "arial": os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
}

lt = RobotPoint(0, 0, 300, 180, 0, 90)
rt = RobotPoint(400, 0, 300, 180, 0, 90)
lb = RobotPoint(0, 300, 300, 180, 0, 90)
wp = WorkPlane(tl=lt, tr=rt, bl=lb)
text = "Ab3\nBG2"
px_per_mm = 10.0
char_h = 100.0

print(f"text={text!r} char_height={char_h}mm px_per_mm={px_per_mm}")
print("expect: first-line min_y/px_per_mm < 1.0 mm when margin_top=0")

for name, fp in FONTS.items():
    if not os.path.exists(fp):
        print(f"  {name}: skip (no font file)")
        continue
    r = OfflinePipelineRunner(
        output_dir="output",
        font_path=fp,
        char_height_mm=char_h,
        margin_left_mm=0.0,
        margin_top_mm=0.0,
        px_per_mm=px_per_mm,
    )
    res = r.run(text, mode="contour", workplane=wp)
    if not res.ok:
        print(f"  {name}: FAIL {res.errors}")
        continue
    extract = next((s.stats for s in res.stage_stats if s.name == "extract"), {})
    strokes = []
    for st in res.stage_stats:
        if st.name == "schedule" and st.stats:
            pass
    # min y from map stage layout_bbox or re-extract from strokes in result
    map_st = next((s.stats for s in res.stage_stats if s.name == "map"), {})
    bbox = map_st.get("layout_bbox_px") or {}
    min_y = bbox.get("min_y")
    if min_y is None:
        print(f"  {name}: no layout_bbox_px")
        continue
    gap_mm = min_y / px_per_mm
    status = "PASS" if gap_mm < 1.0 else "WARN"
    print(f"  {name}: top gap {gap_mm:.2f} mm (min_y_px={min_y:.1f}) {status}")

print("done")
