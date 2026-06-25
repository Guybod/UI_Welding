"""Phase 4.3 路径排序 — 最近邻贪心 + 双向选择 + Travel 优化

PathScheduler: 多 Stroke 执行顺序优化。
纯像素空间操作。不修改 points_px 坐标值 (除 reverse 的纯列表反转)。
不引入 mm/RobotPoint/ProcessSegment。
"""

import uuid

from core.types import PixelPoint, Stroke
from pipeline.path._shared import dist, dist_sq, calc_path_length_px


class PathScheduler:
    """多 Stroke 执行顺序调度器。

    用法:
        scheduler = PathScheduler()
        ordered_strokes, stats = scheduler.schedule(strokes, strategy="nearest")
    """

    # ---- 公开 API ----

    @staticmethod
    def schedule(
        strokes: list[Stroke],
        strategy: str = "nearest",
        allow_reverse: bool = True,
    ) -> tuple[list[Stroke], dict]:
        """主入口：按策略排序，返回 (ordered_strokes, stats)。

        Args:
            strokes: 输入 stroke 列表（像素空间，已完成 Phase 4.1+4.2b）
            strategy: "stable" | "nearest" | "grouped_nearest"
            allow_reverse: 是否允许开放路径反向以优化 travel

        Returns:
            (ordered_strokes, stats)
            — 排序后的 stroke 列表 + 统计信息。
            — 点数不变；只改变顺序和（可选的）开放路径方向。
        """
        if not strokes:
            return [], _empty_stats(strategy)

        n_input = len(strokes)
        original_travel = PathScheduler.calc_total_travel(strokes)

        if strategy == "stable":
            ordered = PathScheduler._stable_order(strokes)
            strategy_used = "stable"
            warnings_list: list[str] = []
        elif strategy == "grouped_nearest":
            # 降级：grouped_nearest 未实现，使用 nearest
            ordered = PathScheduler._nearest_neighbor(strokes, allow_reverse)
            strategy_used = "nearest"
            warnings_list = [
                "grouped_nearest not implemented, falling back to nearest"
            ]
        else:
            ordered = PathScheduler._nearest_neighbor(strokes, allow_reverse)
            strategy_used = "nearest"
            warnings_list = []

        optimized_travel = PathScheduler.calc_total_travel(ordered)

        # 不退化保护：如果 nearest 比 stable 更差，fallback
        if strategy_used == "nearest" and optimized_travel > original_travel:
            ordered = PathScheduler._stable_order(strokes)
            optimized_travel = original_travel
            strategy_used = "stable"
            warnings_list.append(
                "nearest worsened travel, fallback to stable"
            )

        reversed_count = sum(
            1 for s in ordered if s.metadata.get("scheduler_reversed")
        )

        stats = {
            "phase": "4.3",
            "strategy": strategy_used,
            "input_stroke_count": n_input,
            "output_stroke_count": len(ordered),
            "original_travel_px": round(original_travel, 2),
            "optimized_travel_px": round(optimized_travel, 2),
            "travel_reduction_px": round(original_travel - optimized_travel, 2),
            "travel_reduction_percent": round(
                (original_travel - optimized_travel) / max(original_travel, 1e-9) * 100, 1
            ),
            "reversed_count": reversed_count,
            "allow_reverse": allow_reverse,
            "warnings": warnings_list,
        }

        return ordered, stats

    @staticmethod
    def schedule_by_line_groups(
        strokes: list[Stroke],
        *,
        line_key: str = "layout_line_index",
        strategy: str = "nearest",
        allow_reverse: bool = True,
    ) -> tuple[list[Stroke], dict]:
        """多行模式：按行分组，行内 nearest，行间保持输入顺序。"""
        if not strokes:
            return [], _empty_stats("by_line_groups")

        groups: dict[int, list[Stroke]] = {}
        for s in strokes:
            idx = int(s.metadata.get(line_key, 0))
            groups.setdefault(idx, []).append(s)

        ordered: list[Stroke] = []
        line_stats: list[dict] = []
        total_in = len(strokes)
        for line_idx in sorted(groups.keys()):
            grp = groups[line_idx]
            sched, st = PathScheduler.schedule(
                grp, strategy=strategy, allow_reverse=allow_reverse)
            ordered.extend(sched)
            line_stats.append({"line_index": line_idx, "stroke_count": len(grp), **st})

        stats = {
            "phase": "4.3",
            "strategy": "by_line_groups",
            "inner_strategy": strategy,
            "input_stroke_count": total_in,
            "output_stroke_count": len(ordered),
            "line_group_count": len(groups),
            "line_stats": line_stats,
            "warnings": [],
        }
        return ordered, stats

    @staticmethod
    def schedule_by_char_groups(
        strokes: list[Stroke],
        *,
        char_key: str = "weld_char_index",
        strategy: str = "nearest",
        allow_reverse: bool = True,
    ) -> tuple[list[Stroke], dict]:
        """骨架/按字模式：按字符分组，组内 nearest，组间按字符索引顺序。"""
        if not strokes:
            return [], _empty_stats("by_char_groups")

        groups: dict[int, list[Stroke]] = {}
        for s in strokes:
            raw = s.metadata.get(char_key, 0)
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                idx = 0
            groups.setdefault(idx, []).append(s)

        ordered: list[Stroke] = []
        char_stats: list[dict] = []
        total_in = len(strokes)
        for char_idx in sorted(groups.keys()):
            grp = groups[char_idx]
            sched, st = PathScheduler.schedule(
                grp, strategy=strategy, allow_reverse=allow_reverse,
            )
            ordered.extend(sched)
            char_stats.append({
                "char_index": char_idx,
                "stroke_count": len(grp),
                **st,
            })

        stats = {
            "phase": "4.3",
            "strategy": "by_char_groups",
            "inner_strategy": strategy,
            "input_stroke_count": total_in,
            "output_stroke_count": len(ordered),
            "char_group_count": len(groups),
            "char_stats": char_stats,
            "warnings": [],
        }
        return ordered, stats

    @staticmethod
    def schedule_char_order_nearest_endpoint(
        strokes: list[Stroke],
        *,
        char_key: str = "weld_char_index",
        allow_reverse: bool = True,
    ) -> tuple[list[Stroke], dict]:
        """W1-b：字符顺序固定，字内从上一出口最近端点贪心 + 可反转/旋转闭合环。"""
        if not strokes:
            return [], _empty_stats("char_order_nearest_endpoint")

        groups: dict[int, list[Stroke]] = {}
        for s in strokes:
            try:
                idx = int(s.metadata.get(char_key, 0))
            except (TypeError, ValueError):
                idx = 0
            groups.setdefault(idx, []).append(s)

        ordered: list[Stroke] = []
        char_stats: list[dict] = []
        current_pos: PixelPoint | None = None
        intra_px = 0.0
        inter_px = 0.0
        intra_n = 0
        inter_n = 0
        rev_total = 0
        rot_total = 0

        for char_idx in sorted(groups.keys()):
            grp = list(groups[char_idx])
            next_hint = PathScheduler._char_group_hint(groups, char_idx)
            char_ordered, c_intra, c_intra_n, c_rev, c_rot = (
                PathScheduler._nearest_neighbor_from_position(
                    grp, current_pos, allow_reverse=allow_reverse,
                    next_hint=next_hint,
                )
            )
            if current_pos is not None and char_ordered:
                entry = PathScheduler.get_start_point(char_ordered[0])
                gap = dist(current_pos, entry)
                if gap > 1e-6:
                    inter_px += gap
                    inter_n += 1
            intra_px += c_intra
            intra_n += c_intra_n
            rev_total += c_rev
            rot_total += c_rot
            if char_ordered:
                ordered.extend(char_ordered)
                current_pos = PathScheduler._stroke_exit_point(char_ordered[-1])
            char_stats.append({
                "char_index": char_idx,
                "stroke_count": len(grp),
                "reversed_count": c_rev,
                "rotated_count": c_rot,
            })

        return ordered, {
            "phase": "4.3",
            "strategy": "char_order_nearest_endpoint",
            "skeleton_scheduler": "char_order_nearest_endpoint",
            "input_stroke_count": len(strokes),
            "output_stroke_count": len(ordered),
            "char_group_count": len(groups),
            "reversed_count": rev_total,
            "stroke_reversed_count": rev_total + rot_total,
            "stroke_oriented_count": rev_total + rot_total,
            "rotated_count": rot_total,
            "intra_char_travel_px": round(intra_px, 2),
            "intra_char_travel_count": intra_n,
            "inter_char_travel_px": round(inter_px, 2),
            "inter_char_travel_count": inter_n,
            "char_stats": char_stats,
            "allow_reverse": allow_reverse,
            "warnings": [],
        }

    @staticmethod
    def _stroke_exit_point(stroke: Stroke) -> PixelPoint:
        """焊接后离开点：闭合回到起点，开放为终点。"""
        if stroke.closed:
            return PathScheduler.get_start_point(stroke)
        return PathScheduler.get_end_point(stroke)

    @staticmethod
    def _char_group_hint(groups: dict[int, list[Stroke]], char_idx: int) -> PixelPoint | None:
        """下一字符 bbox 中心，用于闭合环双向启发式旋转。"""
        nxt = groups.get(char_idx + 1)
        if not nxt:
            return None
        xs = [p.x for s in nxt for p in s.points_px]
        ys = [p.y for s in nxt for p in s.points_px]
        if not xs:
            return None
        return PixelPoint((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)

    @staticmethod
    def _closed_vertex_cost(
        stroke: Stroke,
        vertex_i: int,
        pos: PixelPoint,
        next_hint: PixelPoint | None,
    ) -> float:
        p = stroke.points_px[vertex_i]
        c = dist(pos, p)
        if next_hint is not None:
            c += dist(next_hint, p)
        return c

    @staticmethod
    def _virtual_entry_distance(
        stroke: Stroke,
        pos: PixelPoint,
        *,
        allow_reverse: bool = True,
        next_hint: PixelPoint | None = None,
    ) -> float:
        """估算入口距离（不修改 stroke）。"""
        if not stroke.points_px:
            return float("inf")
        if stroke.closed:
            return min(
                PathScheduler._closed_vertex_cost(stroke, i, pos, next_hint)
                for i in range(len(stroke.points_px))
            )
        d0 = dist(pos, PathScheduler.get_start_point(stroke))
        if allow_reverse and PathScheduler._can_reverse(stroke):
            d1 = dist(pos, PathScheduler.get_end_point(stroke))
            return min(d0, d1)
        return d0

    @staticmethod
    def _orient_stroke_entry(
        stroke: Stroke,
        pos: PixelPoint,
        *,
        allow_reverse: bool = True,
        next_hint: PixelPoint | None = None,
    ) -> float:
        """将 stroke 起点对准 pos 最近入口，返回入口距离。"""
        if not stroke.points_px:
            return float("inf")
        if stroke.closed:
            pts = stroke.points_px
            best_i = min(
                range(len(pts)),
                key=lambda i: PathScheduler._closed_vertex_cost(
                    stroke, i, pos, next_hint,
                ),
            )
            if best_i != 0:
                stroke.points_px = pts[best_i:] + pts[:best_i]
                stroke.metadata = {**stroke.metadata, "scheduler_rotated": True}
            return dist(pos, PathScheduler.get_start_point(stroke))
        d0 = dist(pos, PathScheduler.get_start_point(stroke))
        d1 = float("inf")
        if allow_reverse and PathScheduler._can_reverse(stroke):
            d1 = dist(pos, PathScheduler.get_end_point(stroke))
        if d1 < d0 - 1e-9:
            PathScheduler.reverse_stroke(stroke)
            return d1
        return d0

    @staticmethod
    def _nearest_neighbor_from_position(
        strokes: list[Stroke],
        start_pos: PixelPoint | None,
        *,
        allow_reverse: bool = True,
        next_hint: PixelPoint | None = None,
    ) -> tuple[list[Stroke], float, int, int, int]:
        """从 start_pos 对 strokes 最近邻排序；None 时从字 bbox 左上最近入口起步。"""
        if not strokes:
            return [], 0.0, 0, 0, 0

        remaining = list(strokes)
        ordered: list[Stroke] = []
        current = start_pos
        intra_px = 0.0
        intra_n = 0
        rev_total = 0
        rot_total = 0

        if current is None:
            ref_x = min(p.x for s in remaining for p in s.points_px)
            ref_y = min(p.y for s in remaining for p in s.points_px)
            ref = PixelPoint(ref_x, ref_y)
            seed = min(
                remaining,
                key=lambda s: (
                    PathScheduler._virtual_entry_distance(
                        s, ref, allow_reverse=allow_reverse, next_hint=next_hint,
                    ),
                    s.id,
                ),
            )
            remaining.remove(seed)
            PathScheduler._orient_stroke_entry(
                seed, ref, allow_reverse=allow_reverse, next_hint=next_hint,
            )
            ordered.append(seed)
            current = PathScheduler._stroke_exit_point(seed)

        while remaining:
            pick_hint = next_hint if len(ordered) == 0 else None
            best_d = min(
                PathScheduler._virtual_entry_distance(
                    s, current, allow_reverse=allow_reverse, next_hint=pick_hint,
                )
                for s in remaining
            )
            near = [
                s for s in remaining
                if PathScheduler._virtual_entry_distance(
                    s, current, allow_reverse=allow_reverse, next_hint=pick_hint,
                ) <= best_d * 1.12 + 1e-6
            ]
            if len(ordered) == 0 and start_pos is not None:
                open_near = [s for s in near if not s.closed]
                pool = open_near if open_near else near
            else:
                pool = near
            best = min(
                pool,
                key=lambda s: (
                    PathScheduler._virtual_entry_distance(
                        s, current, allow_reverse=allow_reverse, next_hint=pick_hint,
                    ),
                    0 if not s.closed else 1,
                    s.id,
                ),
            )
            best_d = PathScheduler._orient_stroke_entry(
                best, current, allow_reverse=allow_reverse, next_hint=pick_hint,
            )

            if best_d > 1e-6 and not (start_pos is not None and len(ordered) == 0):
                intra_px += best_d
                intra_n += 1

            remaining.remove(best)
            ordered.append(best)
            current = PathScheduler._stroke_exit_point(best)

        rev_total = sum(1 for s in ordered if s.metadata.get("scheduler_reversed"))
        rot_total = sum(1 for s in ordered if s.metadata.get("scheduler_rotated"))
        return ordered, intra_px, intra_n, rev_total, rot_total

    @staticmethod
    def _rotate_closed_to_nearest(stroke: Stroke, pos: PixelPoint) -> Stroke:
        pts = stroke.points_px
        if not stroke.closed or len(pts) < 2:
            return stroke
        best_i = min(range(len(pts)), key=lambda i: dist(pts[i], pos))
        if best_i == 0:
            return stroke
        stroke.points_px = pts[best_i:] + pts[:best_i]
        stroke.metadata = {**stroke.metadata, "scheduler_rotated": True}
        return stroke

    # ---- Travel 计算 ----

    @staticmethod
    def calc_total_travel(strokes: list[Stroke]) -> float:
        """计算各 stroke 间的总空移距离（px）。

        从 stroke[i].points_px[-1] → stroke[i+1].points_px[0]。
        像素空间；scale to mm 是 Phase 5 职责。
        """
        if len(strokes) < 2:
            return 0.0
        total = 0.0
        for i in range(len(strokes) - 1):
            end_prev = PathScheduler.get_end_point(strokes[i])
            start_next = PathScheduler.get_start_point(strokes[i + 1])
            total += dist(end_prev, start_next)
        return total

    @staticmethod
    def calc_stroke_length(stroke: Stroke) -> float:
        """计算单条 stroke 的路径长度（px）。"""
        return calc_path_length_px(stroke.points_px)

    @staticmethod
    def get_start_point(stroke: Stroke) -> PixelPoint:
        """返回 stroke 的首点。"""
        return stroke.points_px[0]

    @staticmethod
    def get_end_point(stroke: Stroke) -> PixelPoint:
        """返回 stroke 的末点。"""
        return stroke.points_px[-1]

    # ---- Stroke 方向操作 ----

    @staticmethod
    def reverse_stroke(stroke: Stroke) -> Stroke:
        """反转 stroke 的 points_px 顺序。

        只改变点序列方向；closed / is_hole / source_type / glyph_id /
        group_id 不变。metadata 标记 "scheduler_reversed"。

        注意：调用方必须确保不反转 is_hole=True 或 closed contour stroke。
        """
        stroke.points_px = list(reversed(stroke.points_px))
        stroke.metadata = {**stroke.metadata, "scheduler_reversed": True}
        return stroke

    @staticmethod
    def _can_reverse(stroke: Stroke) -> bool:
        """判断 stroke 是否允许反向。

        规则：
        - closed stroke: 不反向（保护 ContourExtractor 的 CCW/CW 约定）
        - is_hole=True: 不反向（内轮廓 CW 不能变 CCW）
        - open stroke: 允许反向
        """
        if stroke.closed:
            return False
        if stroke.is_hole:
            return False
        return True

    # ---- 排序策略 ----

    @staticmethod
    def _stable_order(strokes: list[Stroke]) -> list[Stroke]:
        """保持输入顺序不变。"""
        return list(strokes)

    @staticmethod
    def _nearest_neighbor(
        strokes: list[Stroke],
        allow_reverse: bool = True,
    ) -> list[Stroke]:
        """最近邻贪心排序 + 双向选择。

        1. 从最左 stroke（bbox min_x 最小）开始
        2. 每次选择距离当前末端点最近的未访问 stroke
        3. 对允许反向的 stroke，比较正反两种方向，选更短的
        4. 等距候选按 stroke.id 字典序 tiebreak（保证确定性）
        """
        if len(strokes) <= 1:
            return list(strokes)

        remaining = list(strokes)

        # 起点：最左 stroke（bbox min_x 最小）
        def _min_x(s: Stroke) -> float:
            return min(p.x for p in s.points_px)

        first = min(remaining, key=lambda s: (_min_x(s), s.id))
        remaining.remove(first)

        ordered = [first]
        current_end = PathScheduler.get_end_point(first)

        while remaining:
            best_stroke: Stroke | None = None
            best_dist = float("inf")
            best_reversed = False

            for s in remaining:
                # 正向：从 current_end → s.start
                s_start = PathScheduler.get_start_point(s)
                d_forward = dist(current_end, s_start)

                # 反向：从 current_end → s.end（仅当允许且可反向）
                d_reverse = float("inf")
                can_rev = allow_reverse and PathScheduler._can_reverse(s)
                if can_rev:
                    s_end = PathScheduler.get_end_point(s)
                    d_reverse = dist(current_end, s_end)

                if d_forward <= d_reverse:
                    d = d_forward
                    rev = False
                else:
                    d = d_reverse
                    rev = True

                # tiebreaker: stroke.id 保证确定性
                if d < best_dist - 1e-9 or (abs(d - best_dist) < 1e-9 and s.id < getattr(best_stroke, 'id', '')):
                    best_dist = d
                    best_stroke = s
                    best_reversed = rev

            if best_stroke is None:
                break

            if best_reversed:
                PathScheduler.reverse_stroke(best_stroke)

            remaining.remove(best_stroke)
            ordered.append(best_stroke)
            current_end = PathScheduler.get_end_point(best_stroke)

        return ordered


def _empty_stats(strategy: str = "nearest") -> dict:
    return {
        "phase": "4.3",
        "strategy": strategy,
        "input_stroke_count": 0,
        "output_stroke_count": 0,
        "original_travel_px": 0.0,
        "optimized_travel_px": 0.0,
        "travel_reduction_px": 0.0,
        "travel_reduction_percent": 0.0,
        "reversed_count": 0,
        "allow_reverse": True,
        "warnings": [],
    }
