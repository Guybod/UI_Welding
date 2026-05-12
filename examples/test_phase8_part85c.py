"""Phase 8.5c-b 测试 — UI 三点坐标方向验证"""

import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import RobotPoint, PixelPoint
from pipeline.mapping import WorkPlane

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)

# UI 模拟三点标定
left_top     = RobotPoint(0, 100, 100, -180, 0, -135)
left_bottom  = RobotPoint(0, 0, 100, -180, 0, -135)
right_bottom = RobotPoint(200, 0, 100, -180, 0, -135)

# 推导 right_top（UI 不采集的第四角）
right_top = RobotPoint(
    x=left_top.x + (right_bottom.x - left_bottom.x),
    y=left_top.y + (right_bottom.y - left_bottom.y),
    z=left_top.z,
    rx=left_top.rx, ry=left_top.ry, rz=left_top.rz,
)

print("=" * 60)
print("UI 三点标定数据")
print(f"  left_top     = ({left_top.x}, {left_top.y}, {left_top.z})")
print(f"  left_bottom  = ({left_bottom.x}, {left_bottom.y}, {left_bottom.z})")
print(f"  right_bottom = ({right_bottom.x}, {right_bottom.y}, {right_bottom.z})")
print(f"  right_top*   = ({right_top.x}, {right_top.y}, {right_top.z}) [derived]")
print()

# ============================================================
# Mapping A: current ServiceV2 (TL=LB, TR=RB, BL=LT)
# ============================================================
print("=" * 60)
print("Mapping A: TL=left_bottom, TR=right_bottom, BL=left_top")
print("  (当前 ServiceV2 映射)")

wp_a = WorkPlane(tl=left_bottom, tr=right_bottom, bl=left_top)
n_a = wp_a.normal

print(f"  U = ({wp_a.u_vec.x:.2f}, {wp_a.u_vec.y:.2f}, {wp_a.u_vec.z:.2f})")
print(f"  V = ({wp_a.v_vec.x:.2f}, {wp_a.v_vec.y:.2f}, {wp_a.v_vec.z:.2f})")
print(f"  N = ({n_a.x:.2f}, {n_a.y:.2f}, {n_a.z:.2f})")
print(f"  width={wp_a.width_mm:.1f}, height={wp_a.height_mm:.1f}")

# pixel corners → robot
canvas_w, canvas_h = 600.0, 600.0
corners_px = {
    "top-left     (0,0)":        PixelPoint(0, 0),
    "top-right    (600,0)":      PixelPoint(canvas_w, 0),
    "bottom-left  (0,600)":      PixelPoint(0, canvas_h),
    "bottom-right (600,600)":    PixelPoint(canvas_w, canvas_h),
    "center       (300,300)":    PixelPoint(300, 300),
}
print()
print("  Pixel → Robot 映射 (A):")
for label, px in corners_px.items():
    rp = wp_a.map_point(px, canvas_w, canvas_h)
    print(f"    {label:22s} → ({rp.x:7.1f}, {rp.y:7.1f}, {rp.z:5.1f})")

# Check: pixel (0,0) should ideally map to left_top for no-flip
# Under mapping A, it maps to left_bottom
rp_tl = wp_a.map_point(PixelPoint(0, 0), canvas_w, canvas_h)
assert abs(rp_tl.x - 0) < 0.1 and abs(rp_tl.y - 0) < 0.1, "A: (0,0) not at origin"
print(f"  → pixel(0,0) = robot(0,0,100) = left_bottom (origin)")
print(f"  → image top-left maps to robot bottom-left → VERTICAL FLIP!")

# N=(0,0,1): normal_offset +15 → z=115 (safe height above workpiece)
rp_offset = wp_a.map_point(PixelPoint(100, 100), canvas_w, canvas_h, normal_offset_mm=15)
assert rp_offset.z > 100, f"A: offset z={rp_offset.z}"
print(f"  → N={n_a.z:+.1f}: normal_offset +15 → z={rp_offset.z:.1f} (safe above workpiece) ✓")
print()

# ============================================================
# Mapping B: TL=left_top, TR=right_top, BL=left_bottom
# ============================================================
print("=" * 60)
print("Mapping B: TL=left_top, TR=right_top*, BL=left_bottom")
print("  (无翻转, 但 N=(0,0,-1))")

try:
    wp_b = WorkPlane(tl=left_top, tr=right_top, bl=left_bottom)
    n_b = wp_b.normal
    print(f"  U = ({wp_b.u_vec.x:.2f}, {wp_b.u_vec.y:.2f}, {wp_b.u_vec.z:.2f})")
    print(f"  V = ({wp_b.v_vec.x:.2f}, {wp_b.v_vec.y:.2f}, {wp_b.v_vec.z:.2f})")
    print(f"  N = ({n_b.x:.2f}, {n_b.y:.2f}, {n_b.z:.2f})")
    print()

    print("  Pixel → Robot 映射 (B):")
    for label, px in corners_px.items():
        rp = wp_b.map_point(px, canvas_w, canvas_h)
        print(f"    {label:22s} → ({rp.x:7.1f}, {rp.y:7.1f}, {rp.z:5.1f})")

    # Check: pixel (0,0) maps to left_top → no flip
    rp_tl_b = wp_b.map_point(PixelPoint(0, 0), canvas_w, canvas_h)
    assert abs(rp_tl_b.x - 0) < 0.1 and abs(rp_tl_b.y - 100) < 0.1, \
        f"B: (0,0) at ({rp_tl_b.x:.1f},{rp_tl_b.y:.1f})"
    print(f"  → pixel(0,0) = robot(0,100,100) = left_top ✓ (no flip)")

    # N=(0,0,-1): normal_offset +15 → z=85 (closer to workpiece!)
    rp_offset_b = wp_b.map_point(PixelPoint(100, 100), canvas_w, canvas_h, normal_offset_mm=15)
    print(f"  → N={n_b.z:+.1f}: normal_offset +15 → z={rp_offset_b.z:.1f} (moves toward workpiece!)")
except Exception as e:
    print(f"  ERROR: {e}")
print()

# ============================================================
# Analysis
# ============================================================
print("=" * 60)
print("分析结论")
print()
print("  Mapping A (当前): N=(0,0,1) ✓ 安全高度  BUT 垂直翻转 ✗")
print("  Mapping B (候选): 无翻转 ✓              BUT N=(0,0,-1) ✗ 安全高度")
print()
print("  根本原因: 三点标定缺少第四角 (right_top)")
print("  U=水平, V=垂直, 但 V 方向取决于 BL-TL 的符号")
print()
print("  推荐方案 (不改 WorkPlane 主逻辑):")
print("  1. ServiceV2 保持 Mapping A (TL=LB, TR=RB, BL=LT)")
print("  2. 在 pixel_to_plane 前做 Y 翻转: py' = canvas_h - py")
print("     (或在 WeldingServiceV2 中传入已翻转的 pixel 坐标)")
print()
print("  需要进一步决策: 在哪个层级做 Y 翻转?")
print("    a) WeldingServiceV2 传入 canvas_invert_y=True")
print("    b) WorkPlane 新增 invert_y 参数")
print("    c) PoseMapper 层面翻转")
print()

print("=" * 60)
print("PHASE 8.5c-b DIRECTION VERIFICATION COMPLETE")
print("=" * 60)
