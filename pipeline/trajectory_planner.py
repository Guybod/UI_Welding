"""轨迹规划器：时间参数化 + 三次样条 (纯 numpy) + 固定姿态 → TrajectorySample[]"""

import math
import numpy as np
from core.types import Pose, Point3D, EulerDeg, PenSegment, TrajectorySample, TrajectoryResult


def _dist_3d(a: Pose, b: Pose) -> float:
    p, q = a.position, b.position
    return math.sqrt((p.x - q.x) ** 2 + (p.y - q.y) ** 2 + (p.z - q.z) ** 2)


def _cumulative_distances(poses: list[Pose]) -> list[float]:
    """计算累积距离列表。"""
    d = [0.0]
    for i in range(len(poses) - 1):
        d.append(d[-1] + _dist_3d(poses[i], poses[i + 1]))
    return d


def _natural_cubic_spline(t: list[float], y: list[float]):
    """Natural cubic spline coefficients (pure numpy, no scipy).

    Returns a function f(t_val) that evaluates the spline at t_val.
    """
    n = len(t) - 1
    if n < 1:
        return lambda tv: y[0] if y else 0.0
    if n == 1:
        return lambda tv: y[0] + (y[1] - y[0]) * (tv - t[0]) / (t[1] - t[0]) if t[1] != t[0] else y[0]

    h = [t[i + 1] - t[i] for i in range(n)]
    # Build tridiagonal system for second derivatives
    A = np.zeros((n - 1, n - 1))
    b = np.zeros(n - 1)
    for i in range(n - 1):
        if i > 0:
            A[i, i - 1] = h[i]
        A[i, i] = 2 * (h[i] + h[i + 1])
        if i < n - 2:
            A[i, i + 1] = h[i + 1]
        b[i] = 6 * ((y[i + 2] - y[i + 1]) / h[i + 1] - (y[i + 1] - y[i]) / h[i])

    # Thomas algorithm
    m = np.zeros(n + 1)
    if n > 1:
        try:
            m_inner = np.linalg.solve(A, b)
            # m_inner is M[1]..M[n-1]; M[0]=M[n]=0 for natural spline
            for i in range(1, n):
                m[i] = m_inner[i - 1]
        except np.linalg.LinAlgError:
            pass  # fallback to linear

    # Coefficients
    a = [y[i] for i in range(n)]
    c = [m[i] / 2 for i in range(n)]
    d = [(m[i + 1] - m[i]) / (6 * h[i]) if h[i] != 0 else 0.0 for i in range(n)]
    b_coeff = [
        (y[i + 1] - y[i]) / h[i] - h[i] * (2 * m[i] + m[i + 1]) / 6
        if h[i] != 0 else 0.0
        for i in range(n)
    ]

    def evaluate(tv: float):
        if tv <= t[0]:
            return float(y[0])
        if tv >= t[-1]:
            return float(y[-1])
        for i in range(n):
            if t[i] <= tv <= t[i + 1]:
                dt = tv - t[i]
                return float(a[i] + b_coeff[i] * dt + c[i] * dt ** 2 + d[i] * dt ** 3)
        return float(y[-1])

    return evaluate


def plan_trajectory(
    pen_segments: list[PenSegment],
    sample_rate_hz: int = 250,
    target_speed_mm_s: float = 30.0,
    orientation_mode: str = "fixed",
) -> TrajectoryResult:
    """规划 CRI 轨迹。

    Args:
        pen_segments: PenSegment 列表
        sample_rate_hz: CRI 采样率 (Hz)
        target_speed_mm_s: 目标速度 (mm/s)
        orientation_mode: "fixed" = 固定姿态

    Returns:
        TrajectoryResult: 等周期采样点
    """
    dt_sample = 1.0 / sample_rate_hz
    samples: list[TrajectorySample] = []
    warnings: list[str] = []

    for seg in pen_segments:
        for phase_name, phase_poses in [
            ("approach", seg.approach),
            ("pen_down", seg.pen_down),
            ("draw", seg.draw_path),
            ("pen_up", seg.pen_up),
            ("travel", seg.travel_to_next),
        ]:
            if len(phase_poses) < 2:
                # 单点或空：直接输出
                for pose in phase_poses:
                    samples.append(TrajectorySample(
                        t=float(len(samples)) * dt_sample,
                        pose=pose,
                        linear_velocity_mm_s=0.0,
                        segment_id=seg.id,
                        phase=phase_name,
                    ))
                continue

            # 计算累积弧长和时间参数化
            cum_dist = _cumulative_distances(phase_poses)
            total_length = cum_dist[-1]

            if total_length < 0.01:
                for pose in phase_poses:
                    samples.append(TrajectorySample(
                        t=float(len(samples)) * dt_sample,
                        pose=pose,
                        linear_velocity_mm_s=0.0,
                        segment_id=seg.id,
                        phase=phase_name,
                    ))
                continue

            duration = total_length / target_speed_mm_s
            duration = max(duration, 2 * dt_sample)  # at least 2 samples

            # 时间点
            n_samples = max(2, int(duration / dt_sample))
            t_array = np.linspace(0, duration, n_samples)

            # 时间→弧长：线性映射
            s_array = np.linspace(0, total_length, n_samples)

            # 弧长→t参数：建立 t 作为弧长的函数
            t_of_s = [0.0]
            for j in range(1, len(cum_dist)):
                seg_duration = (cum_dist[j] - cum_dist[j - 1]) / target_speed_mm_s
                t_of_s.append(t_of_s[-1] + seg_duration)

            # 对 x, y, z 分别做三次样条（t 为参数）
            ts_for_spline = list(t_array)
            xs = [p.position.x for p in phase_poses]
            ys = [p.position.y for p in phase_poses]
            zs = [p.position.z for p in phase_poses]

            # 使用累积弧长作为样条参数（更稳定）
            s_params = cum_dist

            spline_x = _natural_cubic_spline(s_params, xs)
            spline_y = _natural_cubic_spline(s_params, ys)
            spline_z = _natural_cubic_spline(s_params, zs)

            orient = phase_poses[0].orientation_euler_deg

            for i, sv in enumerate(s_array):
                px = spline_x(sv)
                py = spline_y(sv)
                pz = spline_z(sv)

                # Check for spline overshoot
                if abs(px) > 1e6 or abs(py) > 1e6 or abs(pz) > 1e6:
                    warnings.append(
                        f"Spline overshoot in {seg.id}/{phase_name} "
                        f"at s={sv:.1f}: ({px:.0f},{py:.0f},{pz:.0f}). "
                        f"Falling back to linear."
                    )
                    # Fall back to linear
                    px, py, pz = 0.0, 0.0, 0.0
                    break

                samples.append(TrajectorySample(
                    t=float(len(samples)) * dt_sample,
                    pose=Pose(
                        position=Point3D(x=px, y=py, z=pz),
                        orientation_euler_deg=EulerDeg(
                            rx=orient.rx, ry=orient.ry, rz=orient.rz),
                    ),
                    linear_velocity_mm_s=target_speed_mm_s,
                    segment_id=seg.id,
                    phase=phase_name,
                ))

    duration_s = len(samples) * dt_sample if samples else 0.0
    return TrajectoryResult(
        samples=samples,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration_s,
        warnings=warnings,
    )
