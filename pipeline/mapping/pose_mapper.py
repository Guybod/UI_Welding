"""Phase 5.1 姿态映射 — 批量 Stroke 坐标映射

PoseMapper: pixel → UV plane mm → robot xyz。
只做位置映射。工具姿态固定沿用 orientation_source（当前默认 TL）。
"""

from core.types import RobotPoint, Stroke
from pipeline.mapping.workplane import WorkPlane


# 工具姿态策略（当前固定，后续扩展）
# - "fixed": 固定姿态，当前 Phase 5.1 默认
# - "align_to_normal": TODO — 根据工作平面法向 N 对齐工具轴
# - "normal_with_tangent": TODO — 根据 N + 路径切线生成焊枪姿态
_ORIENTATION_MODE = "fixed"


class PoseMapper:
    """批量 Stroke 坐标映射器。

    用法:
        wp = WorkPlane(tl, tr, bl)
        mapper = PoseMapper()
        mapped_strokes, stats = mapper.map_strokes(strokes, wp, canvas_w, canvas_h)
    """

    @staticmethod
    def map_strokes(
        strokes: list[Stroke],
        workplane: WorkPlane,
        canvas_w: float,
        canvas_h: float,
        normal_offset_mm: float = 0.0,
        orientation_source: RobotPoint | None = None,
    ) -> tuple[list[Stroke], dict]:
        """批量映射 Stroke。

        Args:
            strokes: 已完成 Phase 4 的 stroke 列表
            workplane: WorkPlane 实例
            canvas_w: 渲染画布宽度 (px)
            canvas_h: 渲染画布高度 (px)
            normal_offset_mm: 沿法向的偏移量 (mm)
            orientation_source: 姿态来源，None 则用 workplane.orientation_source (TL)

        Returns:
            (mapped_strokes, stats)
        """
        orient = orientation_source if orientation_source is not None else workplane.orientation_source
        warnings_list: list[str] = [
            "tool orientation is fixed in Phase 5.1; "
            "normal-based orientation is reserved for later phase"
        ]
        # 收集 WorkPlane 兼容层 warning
        if "br_warning" in workplane.compat_metadata:
            warnings_list.append(workplane.compat_metadata["br_warning"])

        mapped: list[Stroke] = []
        input_points = 0

        for s in strokes:
            input_points += len(s.points_px)
            ms = workplane.map_stroke(s, canvas_w, canvas_h, normal_offset_mm, orient)
            mapped.append(ms)

        stats = {
            "phase": "5.1",
            "input_stroke_count": len(strokes),
            "output_stroke_count": len(mapped),
            "input_point_count": input_points,
            "mapped_point_count": sum(len(s.points_px) for s in mapped),
            "workplane_width_mm": round(workplane.width_mm, 4),
            "workplane_height_mm": round(workplane.height_mm, 4),
            "u_vector": _vec_to_dict(workplane.u_vec),
            "v_vector": _vec_to_dict(workplane.v_vec),
            "normal_vector": _vec_to_dict(workplane.normal),
            "normal_offset_mm": normal_offset_mm,
            "orientation_mode": _ORIENTATION_MODE,
            "orientation_source": (
                "provided" if orientation_source is not None else "TL"
            ),
            "mapping_mode": workplane.mapping_mode,
            "compatibility_mode_used": workplane.mapping_mode != "uv",
            "compat_metadata": workplane.compat_metadata,
            "normal_direction": workplane.normal_direction_info,
            "warnings": warnings_list,
        }

        return mapped, stats

    @staticmethod
    def map_stroke_points_to_robot(
        stroke: Stroke,
        workplane: WorkPlane,
        canvas_w: float,
        canvas_h: float,
        normal_offset_mm: float = 0.0,
        orientation_source: RobotPoint | None = None,
    ) -> list[RobotPoint]:
        """提取单条 stroke 的 robot_points（便捷方法）。"""
        orient = orientation_source if orientation_source is not None else workplane.orientation_source
        return [
            workplane.map_point(px, canvas_w, canvas_h, normal_offset_mm, orient)
            for px in stroke.points_px
        ]


def _vec_to_dict(v: RobotPoint) -> dict:
    return {"x": round(v.x, 6), "y": round(v.y, 6), "z": round(v.z, 6)}
