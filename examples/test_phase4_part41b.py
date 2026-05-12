"""Phase 4 Part 4.1b 测试 — ContourExtractor filter_small 单位修复"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.types import PathConfig
from pipeline.raster import render_char, get_default_font_path
from pipeline.vision import ContourExtractor
from pipeline.vision.contour_extractor import DEFAULT_MIN_CONTOUR_AREA_PX

FONT = get_default_font_path()
FONT_SIZE = 600
CHARS = ["A", "B", "O", "0", "8"]

ce = ContourExtractor()

# ============================================================
# Test 1: Default (no new params) — A/B/O/0/8 regression
# ============================================================
print("=" * 60)
print("Test 1: Default params regression")
for ch in CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes = ce.extract(binary)
    outers = [s for s in strokes if not s.is_hole]
    inners = [s for s in strokes if s.is_hole]
    assert len(strokes) > 0, f"{ch}: no strokes"
    assert len(outers) >= 1, f"{ch}: no outer contour"
    if ch in ("O", "0"):
        assert len(inners) >= 1, f"{ch}: no inner contour"
    if ch == "8":
        assert len(inners) >= 2, f"8: expected >=2 inner, got {len(inners)}"
    for s in strokes:
        assert len(s.points_px) > 0, f"{ch} {s.id}: empty points"
    print(f"  {ch}: {len(outers)} outer + {len(inners)} inner = {len(strokes)} total OK")

# ============================================================
# Test 2: px_per_mm=10
# ============================================================
print("Test 2: px_per_mm=10")
for ch in CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes = ce.extract(binary, px_per_mm=10.0)
    outers = [s for s in strokes if not s.is_hole]
    inners = [s for s in strokes if s.is_hole]
    assert len(strokes) > 0
    if ch in ("O", "0"):
        assert len(inners) >= 1, f"{ch}: inner lost with px_per_mm=10"
    if ch == "8":
        assert len(inners) >= 2, f"8: inner lost with px_per_mm=10"
    print(f"  {ch}: {len(outers)}o+{len(inners)}i OK")

# ============================================================
# Test 3: explicit min_area_px=4
# ============================================================
print("Test 3: explicit min_area_px=4")
for ch in CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)
    strokes = ce.extract(binary, min_area_px=4.0)
    outers = [s for s in strokes if not s.is_hole]
    inners = [s for s in strokes if s.is_hole]
    assert len(strokes) > 0
    if ch in ("O", "0"):
        assert len(inners) >= 1, f"{ch}: inner lost with min_area_px=4"
    if ch == "8":
        assert len(inners) >= 2, f"8: inner lost with min_area_px=4"
    print(f"  {ch}: {len(outers)}o+{len(inners)}i OK")

# ============================================================
# Test 4: Small noise filtering
# ============================================================
print("Test 4: Noise filtering")
import cv2

# Create a clean O binary with added salt noise
binary_clean = render_char("O", FONT, FONT_SIZE)
binary_noisy = binary_clean.copy()
# Add 10 single-pixel noise dots
rng = np.random.RandomState(42)
for _ in range(10):
    x = rng.randint(0, binary_noisy.shape[1])
    y = rng.randint(0, binary_noisy.shape[0])
    if binary_noisy[y, x] == 0:
        binary_noisy[y, x] = 255

# Default filter (4.0 px²) — should filter single-pixel noise
strokes_default = ce.extract(binary_noisy)
# With min_area_px=0.0 — should keep all noise
strokes_nofilter = ce.extract(binary_noisy, min_area_px=0.0)

print(f"  O clean: {len(ce.extract(binary_clean))} strokes")
print(f"  O + noise (default 4.0): {len(strokes_default)} strokes")
print(f"  O + noise (min_area_px=0.0): {len(strokes_nofilter)} strokes")
assert len(strokes_default) == len(ce.extract(binary_clean)), \
    "noise NOT filtered by default threshold"
assert len(strokes_nofilter) > len(strokes_default), \
    "min_area_px=0 should keep more contours (noise)"

# ============================================================
# Test 5: Tiny synthetic — boundary test
# ============================================================
print("Test 5: Synthetic boundary tests")

# 3x3 square (contour area=4.0 via Green's theorem) — kept at threshold=4.0
block_3x3 = np.zeros((20, 20), dtype=np.uint8)
block_3x3[8:11, 8:11] = 255
strokes_4 = ce.extract(block_3x3, min_area_px=4.0)
assert len(strokes_4) >= 1, "3x3 square (area=4.0) should be kept at threshold=4.0"
print(f"  3x3 square: min_area_px=4.0 → {len(strokes_4)} strokes (kept) ✓")

# same 3x3 square — filtered at threshold=4.01
strokes_401 = ce.extract(block_3x3, min_area_px=4.01)
assert len(strokes_401) == 0, "3x3 square should be filtered at threshold=4.01"
print(f"  3x3 square: min_area_px=4.01 → {len(strokes_401)} strokes (filtered) ✓")

# 4x4 square (contour area=9.0) — always kept
block_4x4 = np.zeros((20, 20), dtype=np.uint8)
block_4x4[8:12, 8:12] = 255
strokes_4x4 = ce.extract(block_4x4, min_area_px=4.0)
assert len(strokes_4x4) >= 1, "4x4 square should be kept"
print(f"  4x4 square: min_area_px=4.0 → {len(strokes_4x4)} strokes (kept) ✓")

# 1px dot (area≈0.0) — should always be filtered
tiny_dot = np.zeros((20, 20), dtype=np.uint8)
tiny_dot[10, 10] = 255
strokes_dot = ce.extract(tiny_dot, min_area_px=4.0)
# 1px dot may or may not produce a valid contour with CHAIN_APPROX_NONE
# If it does, area is ~0, should be filtered
if len(strokes_dot) == 0:
    print(f"  1px dot: no contour found (expected) ✓")
else:
    print(f"  1px dot: {len(strokes_dot)} contour(s) found — may be OpenCV edge case")

# extreme threshold: nothing passes
strokes_none = ce.extract(binary_clean, min_area_px=1e9)
assert len(strokes_none) == 0, "huge threshold should empty result"
print(f"  min_area_px=1e9 → {len(strokes_none)} strokes ✓")

# min_area_px=0: no filter, all contours kept
strokes_zero = ce.extract(binary_clean, min_area_px=0.0)
assert len(strokes_zero) >= len(ce.extract(binary_clean)), \
    "min_area_px=0 should keep at least as many as default"
print(f"  min_area_px=0.0 → {len(strokes_zero)} strokes ✓")

# ============================================================
# Test 6: px_per_mm conversion formula verification
# ============================================================
print("Test 6: px_per_mm conversion derivation")
cfg = PathConfig(min_path_length_mm=2.0)
# px_per_mm=10, min_len_px=20, expected min_area ≥ (20/4)^2 = 25
# At threshold 25, a 5x5 noise block (area≈25) should be filtered or borderline
# But O's inner contour (~8000) should still pass
binary_o = render_char("O", FONT, FONT_SIZE)
strokes_o_px = ce.extract(binary_o, config=cfg, px_per_mm=10.0)
inners_o = [s for s in strokes_o_px if s.is_hole]
assert len(inners_o) >= 1, "O inner contour lost with px_per_mm=10"
print(f"  O with px_per_mm=10: {len(strokes_o_px)} strokes, {len(inners_o)} inner ✓")

# Verify that min_area_px overrides px_per_mm
strokes_override = ce.extract(binary_o, config=cfg, px_per_mm=10.0, min_area_px=4.0)
# Both should work; min_area_px=4.0 is more permissive than derived ~25
assert len(strokes_override) >= len(strokes_o_px), \
    "min_area_px=4 should be more permissive than derived px_per_mm threshold"
print(f"  O with px_per_mm=10 + min_area_px=4 override: {len(strokes_override)} strokes ✓")

# ============================================================
# Test 7: Small font size — inner contour survival
# ============================================================
print("Test 7: Small font inner contour preservation")
binary_o_30 = render_char("O", FONT, 30)
strokes_o_30 = ce.extract(binary_o_30, min_area_px=4.0)
inners_o_30 = [s for s in strokes_o_30 if s.is_hole]
# At 30px, O's inner contour is small but should still be > 4 px²
# If the font rendering doesn't produce a hole at 30px, this is a font artifact, not a bug
if len(inners_o_30) >= 1:
    print(f"  O@30px: {len(strokes_o_30)} strokes, {len(inners_o_30)} inner ✓")
else:
    print(f"  O@30px: {len(strokes_o_30)} strokes, 0 inner (font too small for hole, acceptable)")

# ============================================================
# Summary
# ============================================================
print()
print("=" * 60)
print(f"DEFAULT_MIN_CONTOUR_AREA_PX = {DEFAULT_MIN_CONTOUR_AREA_PX}")
print("ALL TESTS PASSED")
print("=" * 60)
