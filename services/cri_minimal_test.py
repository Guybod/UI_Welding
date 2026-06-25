"""CRI 最小诊断轨迹 — 基于当前 TCP，仅 Z 轴 ±delta 往返，不经过文字生成。"""

from __future__ import annotations

from pathlib import Path

TRAJECTORY_FILENAME = "trajectory_cri_minimal.txt"


def write_minimal_z_test_trajectory(
    output_path: str | Path,
    start_pose_mm_deg: list[float],
    *,
    delta_z_mm: float = 10.0,
    duration_s: float = 3.0,
    sample_rate_hz: int = 500,
) -> dict:
    """从当前位姿生成 Z 轴上下往返测试轨迹（mm + deg），首点=当前 TCP。"""
    if len(start_pose_mm_deg) < 6:
        raise ValueError("start_pose 需要 6 个分量 [x,y,z,rx,ry,rz]")

    x0, y0, z0, rx, ry, rz = start_pose_mm_deg[:6]
    n = max(2, int(duration_s * sample_rate_hz))
    half = n // 2
    lines: list[str] = []

    for i in range(n):
        if i < half:
            alpha = i / max(half - 1, 1) if half > 1 else 1.0
            z = z0 + alpha * delta_z_mm
        else:
            back = i - half
            denom = max(n - half - 1, 1)
            alpha = back / denom
            z = z0 + delta_z_mm * (1.0 - alpha)
        lines.append(
            f"{x0:.6f} {y0:.6f} {z:.6f} {rx:.6f} {ry:.6f} {rz:.6f}"
        )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    zs = [float(l.split()[2]) for l in lines]
    return {
        "path": str(path.resolve()),
        "sample_count": n,
        "duration_s": duration_s,
        "sample_rate_hz": sample_rate_hz,
        "delta_z_mm": delta_z_mm,
        "z_range": (min(zs), max(zs)),
        "start_pose": list(start_pose_mm_deg[:6]),
    }


# 兼容旧名
write_minimal_x_test_trajectory = write_minimal_z_test_trajectory
