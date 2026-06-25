"""从 pipeline 导出的 points.txt 生成 CRI 等周期轨迹文件。"""

from __future__ import annotations

import csv
import math
from pathlib import Path

from core.types import EulerDeg, PenSegment, Point3D, Pose, RobotPoint, TrajectorySample
from pipeline.trajectory_planner import plan_trajectory

TRAJECTORY_FILENAME = "trajectory_cri.txt"


def read_points_from_csv(points_path: str | Path) -> list[RobotPoint]:
    """解析 PointsWriter 生成的 points.txt（含表头）。"""
    path = Path(points_path)
    if not path.is_file():
        raise FileNotFoundError(f"points file not found: {path}")

    rows: list[RobotPoint] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append(
                    RobotPoint(
                        x=float(row["x"]),
                        y=float(row["y"]),
                        z=float(row["z"]),
                        rx=float(row["rx"]),
                        ry=float(row["ry"]),
                        rz=float(row["rz"]),
                    )
                )
            except (KeyError, ValueError) as exc:
                raise ValueError(f"invalid points row: {row}") from exc
    return rows


def _dedupe_points(points: list[RobotPoint], tol: float = 1e-4) -> list[RobotPoint]:
    if not points:
        return []
    out = [points[0]]
    for p in points[1:]:
        last = out[-1]
        d = math.sqrt(
            (p.x - last.x) ** 2
            + (p.y - last.y) ** 2
            + (p.z - last.z) ** 2
        )
        if d > tol:
            out.append(p)
    return out


def _robot_point_to_pose(pt: RobotPoint) -> Pose:
    return Pose(
        position=Point3D(x=pt.x, y=pt.y, z=pt.z),
        orientation_euler_deg=EulerDeg(rx=pt.rx, ry=pt.ry, rz=pt.rz),
    )


def points_to_trajectory(
    points: list[RobotPoint],
    *,
    sample_rate_hz: int = 500,
    target_speed_mm_s: float = 50.0,
) -> tuple[list[TrajectorySample], list[str]]:
    """将稀疏工艺点密化为 CRI 采样序列。"""
    deduped = _dedupe_points(points)
    if len(deduped) < 2:
        if len(deduped) == 1:
            p = _robot_point_to_pose(deduped[0])
            return [
                TrajectorySample(
                    t=0.0,
                    pose=p,
                    linear_velocity_mm_s=0.0,
                    segment_id="draw",
                    phase="draw",
                )
            ], []
        return [], ["no points for trajectory"]

    poses = [_robot_point_to_pose(p) for p in deduped]
    pen_seg = PenSegment(
        id="draw_all",
        approach=[],
        pen_down=[],
        draw_path=poses,
        pen_up=[],
        travel_to_next=[],
    )
    result = plan_trajectory(
        [pen_seg],
        sample_rate_hz=sample_rate_hz,
        target_speed_mm_s=target_speed_mm_s,
    )
    return result.samples, list(result.warnings)


def write_trajectory_txt(samples: list[TrajectorySample], output_path: str | Path) -> int:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for s in samples:
        p = s.pose.position
        o = s.pose.orientation_euler_deg
        lines.append(
            f"{p.x:.6f} {p.y:.6f} {p.z:.6f} "
            f"{o.rx:.6f} {o.ry:.6f} {o.rz:.6f}"
        )
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines)


def build_trajectory_from_points_file(
    points_path: str | Path,
    output_path: str | Path,
    *,
    sample_rate_hz: int = 500,
    target_speed_mm_s: float = 50.0,
) -> dict:
    pts = read_points_from_csv(points_path)
    samples, warnings = points_to_trajectory(
        pts, sample_rate_hz=sample_rate_hz, target_speed_mm_s=target_speed_mm_s
    )
    count = write_trajectory_txt(samples, output_path)
    return {
        "input_points": len(pts),
        "output_samples": count,
        "warnings": warnings,
    }
