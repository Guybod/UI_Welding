"""Phase 6.1 焊接工艺段生成 — Stroke → ProcessSegment 序列

WeldingProcessPlanner: 结构化工艺段生成。
从 Stroke.metadata["robot_points"] 读取 RobotPoint，生成 travel/lead_in/weld/
overlap(closed)/lead_out/retreat 段。
只生成内存中的 ProcessSegment；不生成 Lua/arcOn/setWelderParam/points.txt。
"""

import math
import uuid

from core.types import (
    RobotPoint, Stroke, ProcessSegment,
    WeldingProcessConfig, WorkspaceConfig,
)

# WorkPlane 可选依赖（用于安全高度计算）
try:
    from pipeline.mapping.workplane import WorkPlane as _WorkPlane
except ImportError:
    _WorkPlane = None  # type: ignore


class WeldingProcessPlanner:
    """焊接工艺段生成器。

    用法:
        planner = WeldingProcessPlanner()
        segments, stats = planner.plan(strokes, process_cfg,
                                        workplane=wp, workspace_cfg=wcfg)
    """

    @staticmethod
    def plan(
        strokes: list[Stroke],
        process_cfg: WeldingProcessConfig,
        workplane: object | None = None,
        workspace_cfg: WorkspaceConfig | None = None,
    ) -> tuple[list[ProcessSegment], dict]:
        """主入口：Stroke 列表 → ProcessSegment 序列。

        Args:
            strokes: 已完成 Phase 5 映射的 Stroke（含 metadata["robot_points"]）
            process_cfg: 焊接工艺配置
            workplane: WorkPlane 实例（可选，用于安全高度计算）
            workspace_cfg: WorkspaceConfig（可选，提供 normal_*_offset_mm）

        Returns:
            (segments, stats)
        """
        warnings_list: list[str] = []

        z_work = _get_z(workspace_cfg, "work")
        z_safe = _get_z(workspace_cfg, "safe")
        z_super_safe = _get_z(workspace_cfg, "super_safe")

        if z_safe <= z_work:
            warnings_list.append(
                f"安全高度 z_safe ({z_safe:.1f}) 不高于工作高度 z_work ({z_work:.1f})，"
                f"存在拖枪风险")

        weld_params = {
            "voltage": process_cfg.voltage,
            "current": process_cfg.current,
            "job": process_cfg.job,
            "inductance": process_cfg.inductance,
        }

        all_segments: list[ProcessSegment] = []
        stats_counts = {
            "travel": 0, "lead_in": 0, "weld": 0,
            "overlap": 0, "lead_out": 0, "retreat": 0,
        }
        total_points = 0
        weld_param_segments = 0
        weld_pts_before = 0
        weld_pts_after = 0
        resample_warnings = 0

        for s in strokes:
            robot_pts = _get_robot_points(s)
            pts_before = len(robot_pts)

            # 对 weld 主路径做等距重采样
            robot_pts = _resample_robot_points(
                robot_pts, process_cfg.weld_point_spacing_mm, closed=s.closed)
            pts_after = len(robot_pts)
            weld_pts_before += pts_before
            weld_pts_after += pts_after

            # 检查重采样后步长
            step_s = _compute_step_stats(robot_pts)
            if step_s["max"] > 0.75:
                resample_warnings += 1
                warnings_list.append(
                    f"stroke {s.id[:6]}: max weld step {step_s['max']}mm "
                    f"> 0.75mm (mean={step_s['mean']}mm, p95={step_s['p95']}mm)")

            segs = WeldingProcessPlanner._plan_stroke(
                s, robot_pts, process_cfg,
                workplane, z_work, z_safe, weld_params, warnings_list,
            )
            all_segments.extend(segs)
            for seg in segs:
                stats_counts[seg.type] = stats_counts.get(seg.type, 0) + 1
                total_points += len(seg.points)
                if seg.metadata.get("weld_params"):
                    weld_param_segments += 1

        stats = {
            "phase": "6.2",
            "input_stroke_count": len(strokes),
            "generated_segment_count": len(all_segments),
            "travel_count": stats_counts["travel"],
            "lead_in_count": stats_counts["lead_in"],
            "weld_count": stats_counts["weld"],
            "overlap_count": stats_counts["overlap"],
            "lead_out_count": stats_counts["lead_out"],
            "retreat_count": stats_counts["retreat"],
            "total_robot_points": total_points,
            "workplane_available": workplane is not None,
            "height_model": "absolute_z",
            "z_work_mm": z_work,
            "z_safe_mm": z_safe,
            "z_super_safe_mm": z_super_safe,
            "weld_params_present": True,
            "weld_job": process_cfg.job,
            "weld_current": process_cfg.current,
            "weld_voltage": process_cfg.voltage,
            "weld_inductance": process_cfg.inductance,
            "weld_param_segments_count": weld_param_segments,
            "weld_point_spacing_mm": process_cfg.weld_point_spacing_mm,
            "weld_points_before_resample": weld_pts_before,
            "weld_points_after_resample": weld_pts_after,
            "resample_warning_count": resample_warnings,
            "warnings": warnings_list,
        }

        # 汇总所有 weld/overlap 段的最终步长统计（逐段统计后合并）
        all_step_stats = []
        for seg in all_segments:
            if seg.type in ("weld", "overlap"):
                ss = _compute_step_stats(seg.points)
                if ss["count"] > 0:
                    all_step_stats.append(ss)
        if all_step_stats:
            stats["weld_step_min_mm"] = min(s["min"] for s in all_step_stats)
            stats["weld_step_mean_mm"] = round(
                sum(s["mean"] * s["count"] for s in all_step_stats) /
                max(sum(s["count"] for s in all_step_stats), 1), 3)
            stats["weld_step_median_mm"] = round(
                sorted(s["median"] for s in all_step_stats)
                [len(all_step_stats) // 2], 3)
            stats["weld_step_max_mm"] = max(s["max"] for s in all_step_stats)
            stats["weld_step_p95_mm"] = max(s["p95"] for s in all_step_stats)

        return all_segments, stats

    # ---- 内部 ----

    @staticmethod
    @staticmethod
    def _plan_stroke(
        stroke: Stroke,
        robot_pts: list[RobotPoint],
        cfg: WeldingProcessConfig,
        workplane: object | None,
        z_work: float,
        z_safe: float,
        weld_params: dict,
        warnings_list: list[str],
    ) -> list[ProcessSegment]:
        if stroke.closed:
            return WeldingProcessPlanner._plan_closed(
                stroke, robot_pts, cfg, workplane, z_work, z_safe, weld_params, warnings_list)
        else:
            return WeldingProcessPlanner._plan_open(
                stroke, robot_pts, cfg, workplane, z_work, z_safe, weld_params, warnings_list)

    @staticmethod
    def _plan_open(
        stroke: Stroke, pts: list[RobotPoint], cfg: WeldingProcessConfig,
        workplane: object | None, z_work: float, z_safe: float,
        weld_params: dict, warnings_list: list[str],
    ) -> list[ProcessSegment]:
        segments: list[ProcessSegment] = []
        if len(pts) < 2:
            warnings_list.append(f"stroke {stroke.id[:6]}: <2 robot_points, skipped")
            return segments
        segments.append(_make_segment(
            "travel", stroke.id, _with_z([pts[0], pts[0]], z_safe),
            cfg.travel_speed_mm_s, False))
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, _with_z(li_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")
        segments.append(_make_segment(
            "weld", stroke.id, _with_z(list(pts), z_work),
            cfg.weld_speed_mm_s, True, 0.0, weld_params))
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, _with_z(lo_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")
        segments.append(_make_segment(
            "retreat", stroke.id, _with_z([pts[-1], pts[-1]], z_safe),
            cfg.travel_speed_mm_s, False))
        return segments

    @staticmethod
    def _plan_closed(
        stroke: Stroke, pts: list[RobotPoint], cfg: WeldingProcessConfig,
        workplane: object | None, z_work: float, z_safe: float,
        weld_params: dict, warnings_list: list[str],
    ) -> list[ProcessSegment]:
        segments: list[ProcessSegment] = []
        if len(pts) < 3:
            warnings_list.append(f"stroke {stroke.id[:6]}: <3 robot_points, skipped")
            return segments
        segments.append(_make_segment(
            "travel", stroke.id, _with_z([pts[0], pts[0]], z_safe),
            cfg.travel_speed_mm_s, False))
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, _with_z(li_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")
        segments.append(_make_segment(
            "weld", stroke.id, _with_z(list(pts), z_work),
            cfg.weld_speed_mm_s, True, 0.0, weld_params))
        path_len = _path_length(pts)
        effective_overlap = min(cfg.overlap_length_mm, path_len * 0.5)
        if effective_overlap < cfg.overlap_length_mm:
            warnings_list.append(
                f"stroke {stroke.id[:6]}: overlap clamped "
                f"({cfg.overlap_length_mm}→{effective_overlap:.1f} mm, path_len={path_len:.1f} mm)")
        if effective_overlap > 0.01:
            ol_pts = _copy_path_head(pts, effective_overlap)
            if len(ol_pts) >= 2:
                segments.append(_make_segment(
                    "overlap", stroke.id, _with_z(ol_pts, z_work),
                    cfg.weld_speed_mm_s, True, 0.0, weld_params))
            else:
                warnings_list.append(f"stroke {stroke.id[:6]}: overlap too short, skipped")
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, _with_z(lo_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")
        segments.append(_make_segment(
            "retreat", stroke.id, _with_z([pts[0], pts[0]], z_safe),
            cfg.travel_speed_mm_s, False))
        return segments


# ---- 辅助函数 ----

def _with_z(pts: list[RobotPoint], z: float) -> list[RobotPoint]:
    """返回新列表，所有点 Z 替换为 z，X/Y/rx/ry/rz 不变。"""
    return [RobotPoint(x=p.x, y=p.y, z=z, rx=p.rx, ry=p.ry, rz=p.rz) for p in pts]

def _get_robot_points(stroke: Stroke) -> list[RobotPoint]:
    rp = stroke.metadata.get("robot_points")
    if not rp:
        raise ValueError(
            f"Stroke {stroke.id} missing metadata['robot_points']; "
            f"run Phase 5 PoseMapper first"
        )
    if not isinstance(rp, list) or len(rp) == 0:
        raise ValueError(f"Stroke {stroke.id}: robot_points is empty")
    return rp


def _make_segment(
    seg_type: str,
    stroke_id: str,
    points: list[RobotPoint],
    speed: float,
    arc_enabled: bool,
    normal_offset: float = 0.0,
    weld_params: dict | None = None,
) -> ProcessSegment:
    meta: dict = {}
    if weld_params is not None:
        meta["weld_params"] = weld_params
    return ProcessSegment(
        id=str(uuid.uuid4())[:8],
        type=seg_type,
        points=points,
        speed_mm_s=speed,
        arc_enabled=arc_enabled,
        normal_offset_mm=normal_offset,
        stroke_id=stroke_id,
        metadata=meta,
    )


def _get_z(workspace_cfg, kind: str) -> float:
    """读取 WorkspaceConfig 中的绝对 Z 高度。"""
    if workspace_cfg is None:
        return {"work": 305.0, "safe": 315.0, "super_safe": 325.0}.get(kind, 305.0)
    if kind == "work":
        return workspace_cfg.z_work_mm
    if kind == "safe":
        return workspace_cfg.z_safe_mm
    if kind == "super_safe":
        return workspace_cfg.z_super_safe_mm
    return 305.0


def _path_length(pts: list[RobotPoint]) -> float:
    total = 0.0
    for i in range(len(pts) - 1):
        dx = pts[i + 1].x - pts[i].x
        dy = pts[i + 1].y - pts[i].y
        dz = pts[i + 1].z - pts[i].z
        total += math.sqrt(dx * dx + dy * dy + dz * dz)
    return total


def _tangent_extend(
    pts: list[RobotPoint],
    forward: bool,
    length_mm: float,
    spacing_mm: float,
) -> list[RobotPoint]:
    """沿路径端点切线方向延伸一段。

    Args:
        pts: 路径点
        forward: True=从末点向前延伸, False=从首点向后延伸
        length_mm: 延伸长度
        spacing_mm: 输出点间距

    Returns:
        延伸点列表（含端点）。点数不足时返回空列表。
    """
    if len(pts) < 2 or length_mm < 0.01:
        return []

    if forward:
        a, b = pts[-2], pts[-1]
    else:
        a, b = pts[1], pts[0]  # 反向切线

    dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
    seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
    if seg_len < 1e-9:
        return []

    ux, uy, uz = dx / seg_len, dy / seg_len, dz / seg_len
    n_steps = max(1, int(length_mm / max(spacing_mm, 0.1)))
    step = length_mm / n_steps

    result = [b]
    for i in range(1, n_steps + 1):
        t = i * step
        result.append(RobotPoint(
            x=b.x + ux * t, y=b.y + uy * t, z=b.z + uz * t,
            rx=b.rx, ry=b.ry, rz=b.rz,
        ))
    return result


def _copy_path_head(
    pts: list[RobotPoint],
    length_mm: float,
) -> list[RobotPoint]:
    """从路径头部复制点，直到累积距离 >= length_mm。"""
    if len(pts) < 2:
        return []
    result = [pts[0]]
    accum = 0.0
    for i in range(len(pts) - 1):
        dx = pts[i + 1].x - pts[i].x
        dy = pts[i + 1].y - pts[i].y
        dz = pts[i + 1].z - pts[i].z
        step = math.sqrt(dx * dx + dy * dy + dz * dz)
        result.append(pts[i + 1])
        accum += step
        if accum >= length_mm:
            break
    return result


def _resample_robot_points(
    pts: list[RobotPoint],
    spacing_mm: float,
    closed: bool = False,
) -> list[RobotPoint]:
    """对 robot 点做等距弧长重采样。

    开放路径保留首尾点；闭合路径重采样完整回路。
    定位与姿态均做线性插值。
    """
    n = len(pts)
    if n < 2 or spacing_mm <= 0:
        return list(pts)

    # 计算每段长度
    seg_lens = []
    total_len = 0.0
    for i in range(n - 1):
        dx = pts[i + 1].x - pts[i].x
        dy = pts[i + 1].y - pts[i].y
        dz = pts[i + 1].z - pts[i].z
        sl = math.sqrt(dx * dx + dy * dy + dz * dz)
        seg_lens.append(sl)
        total_len += sl

    closure_len = 0.0
    if closed and n >= 3:
        dx = pts[0].x - pts[-1].x
        dy = pts[0].y - pts[-1].y
        dz = pts[0].z - pts[-1].z
        closure_len = math.sqrt(dx * dx + dy * dy + dz * dz)

    target_len = total_len + (closure_len if closed else 0.0)
    if target_len < spacing_mm:
        return list(pts)

    # 累积弧长表
    cum = [0.0]
    for sl in seg_lens:
        cum.append(cum[-1] + sl)

    result = [pts[0]]
    seg_idx = 0
    t = spacing_mm
    n_targets = max(1, int(target_len / spacing_mm))

    while t < target_len - 1e-9 and len(result) < n_targets + 2:
        if closed and t > total_len + 1e-9:
            frac = (t - total_len) / closure_len if closure_len > 1e-9 else 0.0
            frac = max(0.0, min(1.0, frac))
            a, b = pts[-1], pts[0]
        else:
            tc = min(t, total_len)
            while seg_idx < len(cum) - 1 and cum[seg_idx + 1] < tc:
                seg_idx += 1
            if seg_idx >= len(cum) - 1:
                break
            seg_len = cum[seg_idx + 1] - cum[seg_idx]
            frac = (tc - cum[seg_idx]) / seg_len if seg_len > 1e-9 else 0.0
            frac = max(0.0, min(1.0, frac))
            a, b = pts[seg_idx], pts[seg_idx + 1]

        result.append(RobotPoint(
            x=a.x + (b.x - a.x) * frac,
            y=a.y + (b.y - a.y) * frac,
            z=a.z + (b.z - a.z) * frac,
            rx=a.rx + (b.rx - a.rx) * frac,
            ry=a.ry + (b.ry - a.ry) * frac,
            rz=a.rz + (b.rz - a.rz) * frac,
        ))
        t += spacing_mm

    # 开放路径：确保末点存在
    if not closed:
        if len(result) == 0 or not _pts_eq(result[-1], pts[-1], 0.01):
            result.append(pts[-1])

    while len(result) < 2:
        result.append(pts[-1] if pts else RobotPoint(0,0,0,0,0,0))

    return result


def _pts_eq(a: RobotPoint, b: RobotPoint, tol: float = 0.01) -> bool:
    return abs(a.x - b.x) < tol and abs(a.y - b.y) < tol and abs(a.z - b.z) < tol


def _compute_step_stats(pts: list[RobotPoint]) -> dict:
    """计算相邻点 3D 欧氏步长统计。"""
    if len(pts) < 2:
        return {"count": 0, "min": 0, "max": 0, "mean": 0, "median": 0, "p95": 0}
    steps = []
    for i in range(len(pts) - 1):
        dx = pts[i + 1].x - pts[i].x
        dy = pts[i + 1].y - pts[i].y
        dz = pts[i + 1].z - pts[i].z
        steps.append(math.sqrt(dx * dx + dy * dy + dz * dz))
    s = sorted(steps)
    n = len(s)
    p95_i = min(int(n * 0.95), n - 1)
    return {
        "count": n, "min": round(s[0], 3), "max": round(s[-1], 3),
        "mean": round(sum(s) / n, 3), "median": round(s[n // 2], 3),
        "p95": round(s[p95_i], 3),
    }
