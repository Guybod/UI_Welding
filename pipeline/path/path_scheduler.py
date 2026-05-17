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
