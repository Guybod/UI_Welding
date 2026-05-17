"""Phase 2: image_runner 冒烟测试（无 UI / 无 CRI 执行）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.types import ImageDrawingConfig, ImageProcessConfig, RobotPoint
from pipeline.image_runner import run_image_to_cri
from pipeline.mapping.workplane import WorkPlane
from pipeline.process.drawing_process import DrawingProcessPlanner

OUTPUT = ROOT / "output" / "image_runner_test"
ASSETS = ROOT / "tests" / "assets"


def _workplane(w: float = 200.0, h: float = 200.0) -> WorkPlane:
    lt = RobotPoint(100, 200, 300, 180, 0, 90)
    tr = RobotPoint(100 + w, 200, 300, 180, 0, 90)
    lb = RobotPoint(100, 200 + h, 300, 180, 0, 90)
    return WorkPlane(tl=lt, tr=tr, bl=lb)


def _save(path: Path, img: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)
    return str(path)


def _white_circle(path: Path, size: int = 400) -> str:
    img = np.full((size, size, 3), 255, dtype=np.uint8)
    cv2.circle(img, (size // 2, size // 2), size // 4, (0, 0, 0), 2)
    return _save(path, img)


def _rect_outline(path: Path, w: int = 400, h: int = 200) -> str:
    img = np.full((h, w, 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (40, 30), (w - 40, h - 30), (0, 0, 0), 2)
    return _save(path, img)


def test_contain_circle() -> None:
    img = _white_circle(ASSETS / "runner_circle.png")
    out = OUTPUT / "test1_contain_circle"
    result = run_image_to_cri(
        img,
        _workplane(),
        ImageProcessConfig(min_contour_area=50.0, simplification_epsilon=2.0, fit_mode="contain"),
        ImageDrawingConfig(point_spacing_mm=1.0),
        out,
    )
    assert result.ok, result.error
    assert Path(result.files["trajectory_cri.txt"]).is_file()
    assert Path(result.files["preview_execution.png"]).is_file()
    assert Path(result.files["summary.json"]).is_file()
    assert result.stats["total_robot_points"] > 0
    traj_lines = Path(result.files["trajectory_cri.txt"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(traj_lines) > 0
    print("PASS test1 contain circle + outputs")


def test_contain_uniform_scale() -> None:
    img = _rect_outline(ASSETS / "runner_rect.png", 400, 200)
    result = run_image_to_cri(
        img,
        _workplane(200, 200),
        ImageProcessConfig(
            threshold_method="otsu",
            min_contour_area=80.0,
            simplification_epsilon=2.0,
            fit_mode="contain",
        ),
        ImageDrawingConfig(margin_mm=5.0, point_spacing_mm=2.0),
        OUTPUT / "test2_contain_uniform",
    )
    assert result.ok, result.error
    fit = result.stats["fit"]
    assert fit["mode"] == "contain"
    assert abs(fit["scale_x"] - fit["scale_y"]) < 1e-9
    assert abs(fit["scale_x"] - fit["image_scale"]) < 1e-9
    print("PASS test2 contain uniform scale")


def test_stretch_fill() -> None:
    img = _rect_outline(ASSETS / "runner_rect_stretch.png", 400, 200)
    wp = _workplane(200, 200)
    result = run_image_to_cri(
        img,
        wp,
        ImageProcessConfig(min_contour_area=80.0, fit_mode="stretch"),
        ImageDrawingConfig(margin_mm=0.0, point_spacing_mm=2.0),
        OUTPUT / "test3_stretch",
    )
    assert result.ok, result.error
    fit = result.stats["fit"]
    assert fit["mode"] == "stretch"
    assert abs(fit["scale_x"] - fit["scale_y"]) > 1e-6
    assert abs(fit["scale_x"] - 0.5) < 0.01
    assert abs(fit["scale_y"] - 1.0) < 0.01
    bbox = result.stats["mapping"]["mapped_bbox_uv"]
    assert bbox["max_u_mm"] <= wp.width_mm + 1.0
    assert bbox["max_v_mm"] <= wp.height_mm + 1.0
    print("PASS test3 stretch scales")


def test_z_semantics() -> None:
    from pipeline.image_runner import _compute_fit_transform, _map_strokes_to_workplane
    from pipeline.vision.image_preprocessor import process_image

    img = _white_circle(ASSETS / "runner_z.png", 300)
    img_cfg = ImageProcessConfig(min_contour_area=40.0, simplification_epsilon=2.0)
    draw_cfg = ImageDrawingConfig(z_draw_mm=305.0, z_safe_mm=315.0, point_spacing_mm=1.5)
    wp = _workplane()
    prep = process_image(img, img_cfg)
    assert prep.ok
    fit = _compute_fit_transform(prep.strokes_px, *prep.original_size, wp, draw_cfg.margin_mm, "contain")
    mapped = _map_strokes_to_workplane(prep.strokes_px, wp, fit)
    segments, _ = DrawingProcessPlanner.plan(mapped, draw_cfg)
    assert segments
    for seg in segments:
        zs = {round(p.z, 3) for p in seg.points}
        if seg.type == "travel":
            assert zs == {draw_cfg.z_safe_mm}
        elif seg.type == "draw":
            assert zs == {draw_cfg.z_draw_mm}
        elif seg.type == "retreat":
            assert zs == {draw_cfg.z_safe_mm}
    print("PASS test4 Z semantics")


def test_welding_regression() -> None:
    scripts = [
        "test_phase9_lua_exporter.py",
        "test_phase9_3c_verify.py",
        "test_phase9_6_layout_params.py",
        "test_phase9_preview.py",
    ]
    import subprocess

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    for name in scripts:
        r = subprocess.run(
            [str(py), str(ROOT / "examples" / name)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"{name} failed:\n{r.stdout}\n{r.stderr}"
    print("PASS test5 welding regression (4 scripts)")


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    test_contain_circle()
    test_contain_uniform_scale()
    test_stretch_fill()
    test_z_semantics()
    test_welding_regression()
    print(f"\nAll image_runner tests passed. Output: {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
