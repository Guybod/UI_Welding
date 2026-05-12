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

        travel_offset = _get_travel_offset(workplane, workspace_cfg, warnings_list)
        work_offset = _get_work_offset(workplane, workspace_cfg, warnings_list)

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

        for s in strokes:
            robot_pts = _get_robot_points(s)
            segs = WeldingProcessPlanner._plan_stroke(
                s, robot_pts, process_cfg,
                workplane, travel_offset, work_offset, weld_params, warnings_list,
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
            "travel_offset_mm": travel_offset,
            "work_offset_mm": work_offset,
            "weld_params_present": True,
            "weld_job": process_cfg.job,
            "weld_current": process_cfg.current,
            "weld_voltage": process_cfg.voltage,
            "weld_inductance": process_cfg.inductance,
            "weld_param_segments_count": weld_param_segments,
            "warnings": warnings_list,
        }

        return all_segments, stats

    # ---- 内部 ----

    @staticmethod
    def _plan_stroke(
        stroke: Stroke,
        robot_pts: list[RobotPoint],
        cfg: WeldingProcessConfig,
        workplane: object | None,
        travel_offset: float,
        work_offset: float,
        weld_params: dict,
        warnings_list: list[str],
    ) -> list[ProcessSegment]:
        if stroke.closed:
            return WeldingProcessPlanner._plan_closed(
                stroke, robot_pts, cfg, workplane,
                travel_offset, work_offset, weld_params, warnings_list,
            )
        else:
            return WeldingProcessPlanner._plan_open(
                stroke, robot_pts, cfg, workplane,
                travel_offset, work_offset, weld_params, warnings_list,
            )

    @staticmethod
    def _plan_open(
        stroke: Stroke,
        pts: list[RobotPoint],
        cfg: WeldingProcessConfig,
        workplane: object | None,
        travel_offset: float,
        work_offset: float,
        weld_params: dict,
        warnings_list: list[str],
    ) -> list[ProcessSegment]:
        """开放路径: travel → lead_in → weld → lead_out → retreat。无 overlap。"""
        segments: list[ProcessSegment] = []

        if len(pts) < 2:
            warnings_list.append(f"stroke {stroke.id[:6]}: <2 robot_points, skipped")
            return segments

        # travel: arc_enabled=False, 不附加 weld_params
        segments.append(_make_segment(
            "travel", stroke.id, [pts[0], pts[0]],
            cfg.travel_speed_mm_s, False, travel_offset,
        ))

        # lead_in: arc_enabled=True, 附加 weld_params
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, li_pts,
                cfg.weld_speed_mm_s, True, work_offset, weld_params,
            ))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")

        # weld: arc_enabled=True
        segments.append(_make_segment(
            "weld", stroke.id, list(pts),
            cfg.weld_speed_mm_s, True, work_offset, weld_params,
        ))

        # lead_out: arc_enabled=True
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, lo_pts,
                cfg.weld_speed_mm_s, True, work_offset, weld_params,
            ))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")

        # retreat: arc_enabled=False
        segments.append(_make_segment(
            "retreat", stroke.id, [pts[-1], pts[-1]],
            cfg.travel_speed_mm_s, False, travel_offset,
        ))

        return segments

    @staticmethod
    def _plan_closed(
        stroke: Stroke,
        pts: list[RobotPoint],
        cfg: WeldingProcessConfig,
        workplane: object | None,
        travel_offset: float,
        work_offset: float,
        weld_params: dict,
        warnings_list: list[str],
    ) -> list[ProcessSegment]:
        """闭合路径: travel → lead_in → weld → overlap → lead_out → retreat。"""
        segments: list[ProcessSegment] = []

        if len(pts) < 3:
            warnings_list.append(f"stroke {stroke.id[:6]}: <3 robot_points, skipped")
            return segments

        # travel: arc_enabled=False
        segments.append(_make_segment(
            "travel", stroke.id, [pts[0], pts[0]],
            cfg.travel_speed_mm_s, False, travel_offset,
        ))

        # lead_in: arc_enabled=True
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, li_pts,
                cfg.weld_speed_mm_s, True, work_offset, weld_params,
            ))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")

        # weld: arc_enabled=True
        segments.append(_make_segment(
            "weld", stroke.id, list(pts),
            cfg.weld_speed_mm_s, True, work_offset, weld_params,
        ))

        # overlap: arc_enabled=True（仅闭合）
        path_len = _path_length(pts)
        effective_overlap = min(cfg.overlap_length_mm, path_len * 0.5)
        if effective_overlap < cfg.overlap_length_mm:
            warnings_list.append(
                f"stroke {stroke.id[:6]}: overlap clamped "
                f"({cfg.overlap_length_mm}→{effective_overlap:.1f} mm, "
                f"path_len={path_len:.1f} mm)"
            )

        if effective_overlap > 0.01:
            ol_pts = _copy_path_head(pts, effective_overlap)
            if len(ol_pts) >= 2:
                segments.append(_make_segment(
                    "overlap", stroke.id, ol_pts,
                    cfg.weld_speed_mm_s, True, work_offset, weld_params,
                ))
            else:
                warnings_list.append(f"stroke {stroke.id[:6]}: overlap too short, skipped")

        # lead_out: arc_enabled=True
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, lo_pts,
                cfg.weld_speed_mm_s, True, work_offset, weld_params,
            ))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")

        # retreat: arc_enabled=False
        segments.append(_make_segment(
            "retreat", stroke.id, [pts[0], pts[0]],
            cfg.travel_speed_mm_s, False, travel_offset,
        ))

        return segments


# ---- 辅助函数 ----

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
    normal_offset: float,
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


def _get_travel_offset(
    workplane: object | None,
    workspace_cfg: WorkspaceConfig | None,
    warnings_list: list[str],
) -> float:
    if workspace_cfg is not None:
        return workspace_cfg.normal_travel_offset_mm
    if workplane is not None:
        return 15.0  # default
    warnings_list.append(
        "safe/approach/retreat height requires mapped safe points "
        "or workplane normal; deferred"
    )
    return 0.0


def _get_work_offset(
    workplane: object | None,
    workspace_cfg: WorkspaceConfig | None,
    warnings_list: list[str],
) -> float:
    if workspace_cfg is not None:
        return workspace_cfg.normal_work_offset_mm
    return 0.0


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
