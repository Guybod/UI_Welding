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
        *,
        mode: str = "contour",
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

        forced_close_count = 0
        closed_stroke_indices: list[int] = []
        process_closed_segment_count = 0

        prepared: list[tuple[Stroke, list[RobotPoint]]] = []
        for s in strokes:
            if (s.metadata or {}).get("extract_algorithm") == "hershey":
                from pipeline.raster.hershey_font_renderer import (
                    enforce_hershey_stroke_semantics,
                )
                if enforce_hershey_stroke_semantics(s):
                    forced_close_count += 1
            if s.closed:
                closed_stroke_indices.append(
                    int(s.metadata.get("glyph_stroke_index", -1))
                    if s.metadata.get("extract_algorithm") == "hershey"
                    else len(closed_stroke_indices)
                )
            robot_pts = _get_robot_points(s)
            pts_before = len(robot_pts)
            use_closed_resample = _stroke_use_closed_semantics(s)
            robot_pts = _resample_robot_points(
                robot_pts, process_cfg.weld_point_spacing_mm, closed=use_closed_resample)
            pts_after = len(robot_pts)
            weld_pts_before += pts_before
            weld_pts_after += pts_after
            step_s = _compute_step_stats(robot_pts)
            if step_s["max"] > 0.75:
                resample_warnings += 1
                warnings_list.append(
                    f"stroke {s.id[:6]}: max weld step {step_s['max']}mm "
                    f"> 0.75mm (mean={step_s['mean']}mm, p95={step_s['p95']}mm)")
            prepared.append((s, robot_pts))

        continuous_merged = 0
        use_continuous = (
            mode == "skeleton"
            and process_cfg.skeleton_continuous_junctions
        )
        sk_extra: dict = {}
        if use_continuous:
            all_segments, continuous_merged, sk_extra = (
                WeldingProcessPlanner._plan_skeleton_continuous(
                    prepared, process_cfg, z_work, z_safe, weld_params, warnings_list,
                )
            )
        else:
            for s, robot_pts in prepared:
                segs = WeldingProcessPlanner._plan_stroke(
                    s, robot_pts, process_cfg,
                    None, z_work, z_safe, weld_params, warnings_list,
                )
                all_segments.extend(segs)

        for seg in all_segments:
            stats_counts[seg.type] = stats_counts.get(seg.type, 0) + 1
            total_points += len(seg.points)
            if seg.metadata.get("weld_params"):
                weld_param_segments += 1
            if seg.type == "overlap":
                process_closed_segment_count += 1

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
            "skeleton_continuous_junctions": use_continuous,
            "junction_merge_mm": (
                process_cfg.skeleton_junction_merge_mm if use_continuous else 0.0
            ),
            "continuous_junctions_enabled": use_continuous,
            "continuous_junctions_merged_count": continuous_merged,
            "stroke_reversed_count": sk_extra.get("stroke_reversed_count", 0),
            "intra_char_travel_count": sk_extra.get("intra_char_travel_count", 0),
            "intra_char_travel_length_mm": sk_extra.get(
                "intra_char_travel_length_mm", 0.0,
            ),
            "inter_char_travel_count": sk_extra.get("inter_char_travel_count", 0),
            "inter_char_travel_length_mm": sk_extra.get(
                "inter_char_travel_length_mm", 0.0,
            ),
            "forced_close_count": forced_close_count,
            "closed_stroke_indices": closed_stroke_indices,
            "process_closed_segment_count": process_closed_segment_count,
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
    def _group_strokes_by_char(
        prepared: list[tuple[Stroke, list[RobotPoint]]],
    ) -> list[list[tuple[Stroke, list[RobotPoint]]]]:
        """按 weld_char_index 分组；无 metadata 时每 stroke 单独成组。"""
        if not prepared:
            return []
        groups: list[list[tuple[Stroke, list[RobotPoint]]]] = []
        current_key: int | str | None = None
        bucket: list[tuple[Stroke, list[RobotPoint]]] = []
        for stroke, pts in prepared:
            key = stroke.metadata.get("weld_char_index", stroke.id)
            if current_key is None:
                current_key = key
            if key != current_key and bucket:
                groups.append(bucket)
                bucket = []
            current_key = key
            bucket.append((stroke, pts))
        if bucket:
            groups.append(bucket)
        return groups

    @staticmethod
    def _plan_skeleton_continuous(
        prepared: list[tuple[Stroke, list[RobotPoint]]],
        cfg: WeldingProcessConfig,
        z_work: float,
        z_safe: float,
        weld_params: dict,
        warnings_list: list[str],
    ) -> tuple[list[ProcessSegment], int, dict]:
        """W1-b 骨架连续焊：按调度后顺序走字，近端连续则省 lead。"""
        merge_mm = max(0.0, float(cfg.skeleton_junction_merge_mm))
        all_segments: list[ProcessSegment] = []
        merged_pairs = 0
        char_groups = WeldingProcessPlanner._group_strokes_by_char(prepared)
        intra_travel_len = 0.0
        inter_travel_len = 0.0
        intra_travel_count = 0
        inter_travel_count = 0
        stroke_reversed_count = sum(
            1 for s, _ in prepared
            if s.metadata.get("scheduler_reversed")
            or s.metadata.get("scheduler_rotated")
        )

        for gi, group in enumerate(char_groups):
            n = len(group)
            for i, (stroke, pts) in enumerate(group):
                prev_stroke_pts = group[i - 1] if i > 0 else None
                next_stroke_pts = group[i + 1] if i < n - 1 else None
                continuous_prev = False
                continuous_next = False
                if prev_stroke_pts:
                    ps, pp = prev_stroke_pts
                    continuous_prev = (
                        _skeleton_stroke_gap_mm(ps, pp, stroke, pts) <= merge_mm
                    )
                if next_stroke_pts:
                    ns, np = next_stroke_pts
                    continuous_next = (
                        _skeleton_stroke_gap_mm(stroke, pts, ns, np) <= merge_mm
                    )

                if _stroke_use_closed_semantics(stroke):
                    skip_entry_travel = False
                    if gi > 0 and i == 0:
                        ps, pp = char_groups[gi - 1][-1]
                        prev_end = pp[0] if _stroke_use_closed_semantics(ps) else pp[-1]
                        gap = _endpoint_gap_mm([prev_end], pts[:1])
                        if gap > 0.05:
                            inter_travel_len += gap
                            inter_travel_count += 1
                            all_segments.append(_make_segment(
                                "travel", stroke.id,
                                _with_z([prev_end, pts[0]], z_safe),
                                cfg.travel_speed_mm_s, False, stroke=stroke,
                            ))
                        skip_entry_travel = True
                    elif continuous_prev and prev_stroke_pts:
                        ps, pp = prev_stroke_pts
                        prev_end = pp[0] if _stroke_use_closed_semantics(ps) else pp[-1]
                        gap = _endpoint_gap_mm([prev_end], pts[:1])
                        if gap > 0.05:
                            intra_travel_len += gap
                            intra_travel_count += 1
                            all_segments.append(_make_segment(
                                "travel", stroke.id,
                                _with_z([prev_end, pts[0]], z_safe),
                                cfg.travel_speed_mm_s, False, stroke=stroke,
                            ))
                        skip_entry_travel = True
                    segs = WeldingProcessPlanner._plan_closed_skeleton(
                        stroke, pts, cfg, z_work, z_safe, weld_params,
                        warnings_list,
                        skip_entry_travel=skip_entry_travel,
                        skip_lead_in=continuous_prev,
                        skip_lead_out_retreat=continuous_next and i < n - 1,
                    )
                    all_segments.extend(segs)
                    if continuous_next and i < n - 1:
                        merged_pairs += 1
                    continue

                if len(pts) < 2:
                    warnings_list.append(
                        f"stroke {stroke.id[:6]}: <2 robot_points, skipped")
                    continue
                is_first = i == 0
                is_last = i == n - 1

                travel_from: RobotPoint | None = None
                if gi == 0 and is_first:
                    travel_from = pts[0]
                elif is_first and gi > 0:
                    prev_stroke, prev_pts = char_groups[gi - 1][-1]
                    travel_from = (
                        prev_pts[0]
                        if _stroke_use_closed_semantics(prev_stroke)
                        else prev_pts[-1]
                    )
                elif not continuous_prev:
                    travel_from = group[i - 1][1][-1]

                if travel_from is not None:
                    gap = _endpoint_gap_mm([travel_from], pts[:1])
                    if gap > 0.05:
                        if is_first and gi > 0:
                            inter_travel_len += gap
                            inter_travel_count += 1
                        elif not is_first:
                            intra_travel_len += gap
                            intra_travel_count += 1
                        all_segments.append(_make_segment(
                            "travel", stroke.id,
                            _with_z([travel_from, pts[0]], z_safe),
                            cfg.travel_speed_mm_s, False, stroke=stroke,
                        ))

                need_lead_in = (
                    (is_first and gi == 0)
                    or (is_first and gi > 0)
                    or (not continuous_prev)
                )
                if need_lead_in:
                    li_pts = _tangent_extend(
                        pts, forward=False, length_mm=cfg.lead_in_length_mm,
                        spacing_mm=cfg.weld_point_spacing_mm,
                    )
                    if len(li_pts) >= 2:
                        all_segments.append(_make_segment(
                            "lead_in", stroke.id, _with_z(li_pts, z_work),
                            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                        ))

                all_segments.append(_make_segment(
                    "weld", stroke.id, _with_z(list(pts), z_work),
                    cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                ))

                if is_last:
                    lo_pts = _tangent_extend(
                        pts, forward=True, length_mm=cfg.lead_out_length_mm,
                        spacing_mm=cfg.weld_point_spacing_mm,
                    )
                    if len(lo_pts) >= 2:
                        all_segments.append(_make_segment(
                            "lead_out", stroke.id, _with_z(lo_pts, z_work),
                            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                        ))
                    all_segments.append(_make_segment(
                        "retreat", stroke.id,
                        _with_z([pts[-1], pts[-1]], z_safe),
                        cfg.travel_speed_mm_s, False, stroke=stroke,
                    ))
                elif continuous_next:
                    merged_pairs += 1
                else:
                    lo_pts = _tangent_extend(
                        pts, forward=True, length_mm=cfg.lead_out_length_mm,
                        spacing_mm=cfg.weld_point_spacing_mm,
                    )
                    if len(lo_pts) >= 2:
                        all_segments.append(_make_segment(
                            "lead_out", stroke.id, _with_z(lo_pts, z_work),
                            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                        ))
                    all_segments.append(_make_segment(
                        "retreat", stroke.id,
                        _with_z([pts[-1], pts[-1]], z_safe),
                        cfg.travel_speed_mm_s, False, stroke=stroke,
                    ))

        return all_segments, merged_pairs, {
            "stroke_reversed_count": stroke_reversed_count,
            "intra_char_travel_count": intra_travel_count,
            "intra_char_travel_length_mm": round(intra_travel_len, 2),
            "inter_char_travel_count": inter_travel_count,
            "inter_char_travel_length_mm": round(inter_travel_len, 2),
        }

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
        if _stroke_use_closed_semantics(stroke):
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
            cfg.travel_speed_mm_s, False, stroke=stroke))
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, _with_z(li_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")
        segments.append(_make_segment(
            "weld", stroke.id, _with_z(list(pts), z_work),
            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, _with_z(lo_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")
        segments.append(_make_segment(
            "retreat", stroke.id, _with_z([pts[-1], pts[-1]], z_safe),
            cfg.travel_speed_mm_s, False, stroke=stroke))
        return segments

    @staticmethod
    def _plan_closed_skeleton(
        stroke: Stroke,
        pts: list[RobotPoint],
        cfg: WeldingProcessConfig,
        z_work: float,
        z_safe: float,
        weld_params: dict,
        warnings_list: list[str],
        *,
        skip_entry_travel: bool = False,
        skip_lead_in: bool = False,
        skip_lead_out_retreat: bool = False,
    ) -> list[ProcessSegment]:
        """骨架闭合 stroke：可跳过入口 travel / 连续分叉 lead。"""
        segments: list[ProcessSegment] = []
        if len(pts) < 3:
            warnings_list.append(f"stroke {stroke.id[:6]}: <3 robot_points, skipped")
            return segments
        if not skip_entry_travel:
            segments.append(_make_segment(
                "travel", stroke.id, _with_z([pts[0], pts[0]], z_safe),
                cfg.travel_speed_mm_s, False, stroke=stroke,
            ))
        if not skip_lead_in:
            li_pts = _tangent_extend(
                pts, forward=False, length_mm=cfg.lead_in_length_mm,
                spacing_mm=cfg.weld_point_spacing_mm,
            )
            if len(li_pts) >= 2:
                segments.append(_make_segment(
                    "lead_in", stroke.id, _with_z(li_pts, z_work),
                    cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                ))
        segments.append(_make_segment(
            "weld", stroke.id, _with_z(list(pts), z_work),
            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
        ))
        path_len = _path_length(pts)
        effective_overlap = min(cfg.overlap_length_mm, path_len * 0.5)
        if effective_overlap > 0.01:
            ol_pts = _copy_path_head(pts, effective_overlap)
            if len(ol_pts) >= 2:
                segments.append(_make_segment(
                    "overlap", stroke.id, _with_z(ol_pts, z_work),
                    cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                ))
        if not skip_lead_out_retreat:
            lo_pts = _tangent_extend(
                pts, forward=True, length_mm=cfg.lead_out_length_mm,
                spacing_mm=cfg.weld_point_spacing_mm,
            )
            if len(lo_pts) >= 2:
                segments.append(_make_segment(
                    "lead_out", stroke.id, _with_z(lo_pts, z_work),
                    cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke,
                ))
            segments.append(_make_segment(
                "retreat", stroke.id, _with_z([pts[0], pts[0]], z_safe),
                cfg.travel_speed_mm_s, False, stroke=stroke,
            ))
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
            cfg.travel_speed_mm_s, False, stroke=stroke))
        li_pts = _tangent_extend(pts, forward=False, length_mm=cfg.lead_in_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(li_pts) >= 2:
            segments.append(_make_segment(
                "lead_in", stroke.id, _with_z(li_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_in too short, skipped")
        segments.append(_make_segment(
            "weld", stroke.id, _with_z(list(pts), z_work),
            cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
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
                    cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
            else:
                warnings_list.append(f"stroke {stroke.id[:6]}: overlap too short, skipped")
        lo_pts = _tangent_extend(pts, forward=True, length_mm=cfg.lead_out_length_mm,
                                  spacing_mm=cfg.weld_point_spacing_mm)
        if len(lo_pts) >= 2:
            segments.append(_make_segment(
                "lead_out", stroke.id, _with_z(lo_pts, z_work),
                cfg.weld_speed_mm_s, True, 0.0, weld_params, stroke=stroke))
        else:
            warnings_list.append(f"stroke {stroke.id[:6]}: lead_out too short, skipped")
        segments.append(_make_segment(
            "retreat", stroke.id, _with_z([pts[0], pts[0]], z_safe),
            cfg.travel_speed_mm_s, False, stroke=stroke))
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


def _stroke_lua_meta(stroke: Stroke | None) -> dict:
    """从笔画 metadata 提取 Lua 注释所需字段。"""
    if stroke is None:
        return {}
    m = stroke.metadata or {}
    out: dict = {}
    ch = m.get("weld_char")
    if ch is None:
        ch = m.get("hanzi_char")
    if ch is not None:
        out["weld_char"] = ch
    for key in (
        "weld_char_index",
        "layout_line_index",
        "layout_line_text",
        "glyph_stroke_index",
        "extract_algorithm",
    ):
        if key in m:
            out[key] = m[key]
    return out


def _make_segment(
    seg_type: str,
    stroke_id: str,
    points: list[RobotPoint],
    speed: float,
    arc_enabled: bool,
    normal_offset: float = 0.0,
    weld_params: dict | None = None,
    *,
    stroke: Stroke | None = None,
) -> ProcessSegment:
    meta = _stroke_lua_meta(stroke)
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


def _reverse_prepared_stroke(
    stroke: Stroke, pts: list[RobotPoint],
) -> tuple[Stroke, list[RobotPoint]]:
    stroke.points_px = list(reversed(stroke.points_px))
    pts = list(reversed(pts))
    stroke.metadata = {**stroke.metadata, "skeleton_chain_reversed": True}
    return stroke, pts


def _split_prepared_by_connectivity(
    group: list[tuple[Stroke, list[RobotPoint]]],
    merge_mm: float,
) -> list[list[tuple[Stroke, list[RobotPoint]]]]:
    """按端点邻接（≤ merge_mm）拆成连通子组（如 6 的上钩与下环）。"""
    n = len(group)
    if n <= 1:
        return [group] if group else []

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        _, pts_i = group[i]
        if len(pts_i) < 1:
            continue
        ends_i = (pts_i[0], pts_i[-1])
        for j in range(i + 1, n):
            _, pts_j = group[j]
            if len(pts_j) < 1:
                continue
            ends_j = (pts_j[0], pts_j[-1])
            min_gap = min(
                math.hypot(ei.x - ej.x, ei.y - ej.y, ei.z - ej.z)
                for ei in ends_i for ej in ends_j
            )
            if min_gap <= merge_mm:
                union(i, j)

    buckets: dict[int, list[tuple[Stroke, list[RobotPoint]]]] = {}
    for i in range(n):
        root = find(i)
        buckets.setdefault(root, []).append(group[i])
    return list(buckets.values())


def _reorder_prepared_by_endpoint_chain(
    group: list[tuple[Stroke, list[RobotPoint]]],
    merge_mm: float,
) -> list[tuple[Stroke, list[RobotPoint]]]:
    """组内按端点邻接重排，使分叉 stroke 在列表中相邻，便于连续焊。"""
    if len(group) <= 1:
        return group

    open_items: list[tuple[Stroke, list[RobotPoint]]] = []
    closed_items: list[tuple[Stroke, list[RobotPoint]]] = []
    for stroke, pts in group:
        if _stroke_use_closed_semantics(stroke):
            closed_items.append((stroke, pts))
        else:
            open_items.append((stroke, pts))

    if not open_items:
        return group

    remaining = list(open_items)
    seed_i = min(
        range(len(remaining)),
        key=lambda i: remaining[i][1][0].x if remaining[i][1] else 0.0,
    )
    ordered: list[tuple[Stroke, list[RobotPoint]]] = [remaining.pop(seed_i)]

    while remaining:
        _, last_pts = ordered[-1]
        best_j = -1
        best_rev = False
        best_gap = merge_mm + 1.0
        for j, (stroke, pts) in enumerate(remaining):
            for rev in (False, True):
                if rev:
                    start = pts[-1]
                else:
                    start = pts[0]
                g = _endpoint_gap_mm(last_pts, [start])
                if g < best_gap:
                    best_gap = g
                    best_j = j
                    best_rev = rev
        if best_j < 0 or best_gap > merge_mm:
            ordered.extend(remaining)
            break
        stroke, pts = remaining.pop(best_j)
        if best_rev:
            stroke, pts = _reverse_prepared_stroke(stroke, pts)
        ordered.append((stroke, pts))

    ordered.extend(closed_items)
    return ordered


def _robot_pts_coincide(a: RobotPoint, b: RobotPoint, tol: float = 0.05) -> bool:
    return (
        abs(a.x - b.x) < tol
        and abs(a.y - b.y) < tol
        and abs(a.z - b.z) < tol
    )


def _stroke_use_closed_semantics(stroke: Stroke) -> bool:
    """Hershey 仅当 glyph_stroke_closed 且首尾重合时才按闭合工艺处理。"""
    meta = stroke.metadata or {}
    if meta.get("extract_algorithm") != "hershey":
        return bool(stroke.closed)
    return bool(meta.get("glyph_stroke_closed", False))


def _skeleton_stroke_gap_mm(
    stroke_a: Stroke,
    pts_a: list[RobotPoint],
    stroke_b: Stroke,
    pts_b: list[RobotPoint],
) -> float:
    """骨架连续焊：上一 stroke 出口 → 下一 stroke 入口（闭合出口=起点）。"""
    if not pts_a or not pts_b:
        return float("inf")
    exit_a = pts_a[0] if _stroke_use_closed_semantics(stroke_a) else pts_a[-1]
    return _endpoint_gap_mm([exit_a], pts_b)


def _endpoint_gap_mm(
    pts_a: list[RobotPoint],
    pts_b: list[RobotPoint],
) -> float:
    if not pts_a or not pts_b:
        return float("inf")
    a, b = pts_a[-1], pts_b[0]
    return math.hypot(b.x - a.x, b.y - a.y, b.z - a.z)


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
