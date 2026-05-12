"""Phase 3 Part 3.2 测试 — SkeletonExtractor Stroke 提取"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.raster import get_default_font_path, render_char
from pipeline.vision import SkeletonExtractor

OUT = Path(__file__).resolve().parent / "output"
OUT.mkdir(parents=True, exist_ok=True)
FONT = get_default_font_path()

CHARS = ["A", "B", "O", "0", "8", "i", "j"]
FONT_SIZE = 600

print(f"{'char':>4s}  {'strokes':>7s}  {'closed':>6s}  {'open':>4s}  "
      f"{'comp':>4s}  {'ep':>4s}  {'bp':>4s}  {'edge':>4s}  {'backend':>10s}  {'warn':>5s}")
print("-" * 90)

for ch in CHARS:
    binary = render_char(ch, FONT, FONT_SIZE)

    # backend="zhang_suen"
    strokes, stats = SkeletonExtractor.extract(binary, backend="zhang_suen")

    skeleton, _, _, _ = SkeletonExtractor.skeletonize_binary(binary, backend="zhang_suen")
    debug_path = str(OUT / f"skeleton_strokes_{ch}.png")
    SkeletonExtractor.save_debug_strokes(binary, skeleton, strokes, debug_path)

    be = stats.get("skeleton_backend_used", "?")
    warn = "Y" if stats.get("skeleton_warning", "") else ""
    print(
        f"{ch:>4s}  {stats['stroke_count']:>7d}  {stats['closed_count']:>6d}  "
        f"{stats['open_count']:>4d}  {stats['component_count']:>4d}  "
        f"{stats['endpoint_count']:>4d}  {stats['branchpoint_count']:>4d}  "
        f"{stats['edge_count']:>4d}  {be:>10s}  {warn:>5s}"
    )

    # validate
    assert len(strokes) > 0, f"{ch}: no strokes"
    for s in strokes:
        assert len(s.points_px) > 0, f"{ch} stroke {s.id}: empty points"
        assert s.source_type == "skeleton", f"{ch} stroke {s.id}: wrong source_type={s.source_type}"

# check specific expectations
binary_o = render_char("O", FONT, FONT_SIZE)
strokes_o, _ = SkeletonExtractor.extract(binary_o, backend="zhang_suen")
assert any(s.closed for s in strokes_o), "O: no closed stroke"

binary_0 = render_char("0", FONT, FONT_SIZE)
strokes_0, _ = SkeletonExtractor.extract(binary_0, backend="zhang_suen")
assert any(s.closed for s in strokes_0), "0: no closed stroke"

for ch in ["i", "j"]:
    binary_ch = render_char(ch, FONT, FONT_SIZE)
    strokes_ch, stats_ch = SkeletonExtractor.extract(binary_ch, backend="zhang_suen")
    assert stats_ch["component_count"] >= 2 or len(strokes_ch) >= 2, \
        f"{ch}: expected >=2 components or strokes, got comp={stats_ch['component_count']} strokes={len(strokes_ch)}"
    print(f"\n{ch} detail: comp={stats_ch['component_count']}, strokes={len(strokes_ch)}, "
          f"closed={stats_ch['closed_count']}, ep={stats_ch['endpoint_count']}")

# backend="auto" test on A (fallback to zhang_suen since no skimage)
print("\n--- backend=auto on A ---")
binary_a = render_char("A", FONT, FONT_SIZE)
strokes_a_auto, stats_a_auto = SkeletonExtractor.extract(binary_a, backend="auto")
assert len(strokes_a_auto) > 0, "A auto: no strokes"
be_auto = stats_a_auto.get("skeleton_backend_used", "?")
print(f"A auto: strokes={len(strokes_a_auto)}, backend={be_auto}")

print("\n=== All tests passed ===")
for ch in CHARS:
    print(f"  examples/output/skeleton_strokes_{ch}.png")
