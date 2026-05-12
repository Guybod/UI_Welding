"""Phase 5.1 工作平面 — 三点 UV 映射 + 法向偏移

WorkPlane: TL/TR/BL 三点定义倾斜工作平面。
坐标规则: P_robot = TL + u_mm * U + v_mm * V + normal_offset_mm * N
只做位置映射；工具姿态固定沿用 orientation_source 或 TL 的 rx/ry/rz。
"""

import math

from core.types import PixelPoint, PlanePoint, RobotPoint, Stroke
from core.errors import WorkplaneError

# validate 安全阈值
_MIN_WIDTH_HEIGHT_MM = 1.0       # 工作平面最小宽/高
_MIN_CROSS_SIN = 0.17            # sin(10°) ≈ 0.174，U/V 夹角安全下限


def _length(pt: RobotPoint) -> float:
    """RobotPoint 位置分量的欧氏长度。"""
    return math.sqrt(pt.x * pt.x + pt.y * pt.y + pt.z * pt.z)


def _normalize_rp(v: RobotPoint) -> RobotPoint:
    """归一化 RobotPoint（仅位置分量）。"""
    length = _length(v)
    if length < 1e-12:
        raise WorkplaneError("cannot normalize zero-length vector")
    return v / length


def _cross(a: RobotPoint, b: RobotPoint) -> RobotPoint:
    """RobotPoint 位置分量叉积。"""
    return RobotPoint(
        x=a.y * b.z - a.z * b.y,
        y=a.z * b.x - a.x * b.z,
        z=a.x * b.y - a.y * b.x,
        rx=0.0, ry=0.0, rz=0.0,
    )


class WorkPlane:
    """三点定义的工作平面。

    TL (left-top):     UV 原点
    TR (right-top):    U 方向终点
    BL (left-bottom):  V 方向终点

    U = normalize(TR - TL)
    V = normalize(BL - TL)
    N = normalize(U × V)  # internally _normalize_rp
    """

    def __init__(
        self, tl: RobotPoint, tr: RobotPoint, bl: RobotPoint,
        mapping_mode: str = "uv",
    ):
        self.tl = tl
        self.tr = tr
        self.bl = bl
        self.mapping_mode = mapping_mode

        # 预计算向量
        raw_u = tr - tl
        raw_v = bl - tl
        w = _length(raw_u)
        h = _length(raw_v)

        self.width_mm = w
        self.height_mm = h

        # validate
        ok, msg = self.validate()
        if not ok:
            raise WorkplaneError(msg)

        # 归一化
        self.u_vec = _normalize_rp(raw_u)
        self.v_vec = _normalize_rp(raw_v)
        self.normal = _normalize_rp(_cross(self.u_vec, self.v_vec))

        # 姿态固定沿用 TL 的 rx/ry/rz
        self.orientation_source = tl

        # 兼容模式元数据
        self.compat_metadata: dict = {}

    def validate(self) -> tuple[bool, str]:
        """检查三点合法性。

        Returns:
            (ok, message)
        """
        w, h = self.width_mm, self.height_mm
        if w < _MIN_WIDTH_HEIGHT_MM:
            return False, f"workplane width too small: {w:.2f} mm < {_MIN_WIDTH_HEIGHT_MM}"
        if h < _MIN_WIDTH_HEIGHT_MM:
            return False, f"workplane height too small: {h:.2f} mm < {_MIN_WIDTH_HEIGHT_MM}"

        if self.tl.x == self.tr.x and self.tl.y == self.tr.y and self.tl.z == self.tr.z:
            return False, "TL and TR are the same point"
        if self.tl.x == self.bl.x and self.tl.y == self.bl.y and self.tl.z == self.bl.z:
            return False, "TL and BL are the same point"

        # U/V 夹角检测（通过原始向量叉积）
        raw_u = self.tr - self.tl
        raw_v = self.bl - self.tl
        cross_v = _cross(raw_u, raw_v)
        cross_len = _length(cross_v)
        uv_product = w * h
        if uv_product < 1e-12:
            return False, "U/V vectors degenerate"
        sin_angle = cross_len / uv_product
        if sin_angle < _MIN_CROSS_SIN:
            return False, (
                f"U/V angle too small: sin={sin_angle:.4f} < {_MIN_CROSS_SIN} "
                f"(angle ≈ {math.degrees(math.asin(max(0, min(1, sin_angle)))):.1f}°)"
            )

        return True, "OK"

    # ---- 工厂方法（兼容模式）----

    @classmethod
    def from_ortho(
        cls,
        origin: RobotPoint,
        pixel_per_mm: float,
        canvas_w: float,
        canvas_h: float,
        orientation_source: RobotPoint | None = None,
    ) -> "WorkPlane":
        """正交映射兼容模式。

        U=全局X正方向, V=全局Y正方向。
        width_mm = canvas_w / pixel_per_mm, height_mm = canvas_h / pixel_per_mm。

        normal_offset 仍沿 N=(0,0,1) 偏移，通过 plane_to_robot 统一路径。
        """
        orient = orientation_source if orientation_source is not None else origin
        U = RobotPoint(1, 0, 0, 0, 0, 0)
        V = RobotPoint(0, 1, 0, 0, 0, 0)
        w_mm = canvas_w / pixel_per_mm if pixel_per_mm > 0 else 0.0
        h_mm = canvas_h / pixel_per_mm if pixel_per_mm > 0 else 0.0

        tl = origin
        tr = RobotPoint(
            x=origin.x + U.x * w_mm,
            y=origin.y + U.y * w_mm,
            z=origin.z,
            rx=orient.rx, ry=orient.ry, rz=orient.rz,
        )
        bl = RobotPoint(
            x=origin.x + V.x * h_mm,
            y=origin.y + V.y * h_mm,
            z=origin.z,
            rx=orient.rx, ry=orient.ry, rz=orient.rz,
        )

        wp = cls(tl, tr, bl, mapping_mode="ortho")
        wp.orientation_source = orient
        wp.compat_metadata["pixel_per_mm"] = pixel_per_mm
        return wp

    @classmethod
    def from_four_corners(
        cls,
        tl: RobotPoint,
        tr: RobotPoint,
        bl: RobotPoint,
        br: RobotPoint,
        br_tolerance_mm: float = 5.0,
    ) -> "WorkPlane":
        """四角标定兼容模式。

        使用 TL/TR/BL 定义平面，BR 作为冗余校验点。
        BR 到平面的距离存入 compat_metadata["br_plane_error_mm"]。
        若偏差 > br_tolerance_mm，记录 warning 但不抛异常。
        """
        wp = cls(tl, tr, bl, mapping_mode="four_corners")

        # BR 到平面的距离
        br_vec = br - tl
        br_dist = abs(
            br_vec.x * wp.normal.x +
            br_vec.y * wp.normal.y +
            br_vec.z * wp.normal.z
        )
        wp.compat_metadata["br_plane_error_mm"] = round(br_dist, 4)
        wp.compat_metadata["br_tolerance_mm"] = br_tolerance_mm
        wp.compat_metadata["br_point"] = br

        if br_dist > br_tolerance_mm:
            wp.compat_metadata["br_warning"] = (
                f"BR point deviates {br_dist:.2f} mm from TL/TR/BL plane "
                f"(tolerance {br_tolerance_mm} mm)"
            )

        return wp

    # ---- 坐标映射 ----

    def pixel_to_plane(
        self, px: PixelPoint, canvas_w: float, canvas_h: float,
    ) -> PlanePoint:
        """像素坐标 → UV 平面坐标 (mm)。

        pixel (0,0) → PlanePoint(0, 0) (TL)
        pixel (canvas_w, 0) → PlanePoint(width_mm, 0) (TR)
        pixel (0, canvas_h) → PlanePoint(0, height_mm) (BL)
        """
        u_mm = (px.x / canvas_w) * self.width_mm if canvas_w > 0 else 0.0
        v_mm = (px.y / canvas_h) * self.height_mm if canvas_h > 0 else 0.0
        return PlanePoint(u_mm=u_mm, v_mm=v_mm)

    def plane_to_robot(
        self,
        pm: PlanePoint,
        normal_offset_mm: float = 0.0,
        orientation_source: RobotPoint | None = None,
    ) -> RobotPoint:
        """UV 平面坐标 → 机器人笛卡尔坐标。

        P_robot = TL + u_mm * U + v_mm * V + normal_offset_mm * N
        姿态固定沿用 orientation_source 或 TL 的 rx/ry/rz。

        Args:
            pm: UV 平面坐标 (mm)
            normal_offset_mm: 沿法向的偏移量
            orientation_source: 姿态来源 RobotPoint，None 则用 TL

        Returns:
            RobotPoint
        """
        orient = orientation_source if orientation_source is not None else self.orientation_source
        p = (
            self.tl
            + self.u_vec * pm.u_mm
            + self.v_vec * pm.v_mm
            + self.normal * normal_offset_mm
        )
        return RobotPoint(
            x=p.x, y=p.y, z=p.z,
            rx=orient.rx, ry=orient.ry, rz=orient.rz,
        )

    def map_point(
        self,
        px: PixelPoint,
        canvas_w: float,
        canvas_h: float,
        normal_offset_mm: float = 0.0,
        orientation_source: RobotPoint | None = None,
    ) -> RobotPoint:
        """快捷映射：pixel → plane → robot。"""
        pm = self.pixel_to_plane(px, canvas_w, canvas_h)
        return self.plane_to_robot(pm, normal_offset_mm, orientation_source)

    def map_stroke(
        self,
        stroke: Stroke,
        canvas_w: float,
        canvas_h: float,
        normal_offset_mm: float = 0.0,
        orientation_source: RobotPoint | None = None,
    ) -> Stroke:
        """映射单条 Stroke。

        返回新 Stroke 对象；原 points_px 保留；points_mm 填入 PlanePoint，
        metadata["robot_points"] 填入 RobotPoint。
        """
        import dataclasses

        plane_points: list[PlanePoint] = []
        robot_points: list[RobotPoint] = []
        orient = orientation_source if orientation_source is not None else self.orientation_source

        for px in stroke.points_px:
            pm = self.pixel_to_plane(px, canvas_w, canvas_h)
            rp = self.plane_to_robot(pm, normal_offset_mm, orient)
            plane_points.append(pm)
            robot_points.append(rp)

        return dataclasses.replace(
            stroke,
            points_mm=plane_points,
            metadata={
                **stroke.metadata,
                "robot_points": robot_points,
            },
        )

    # ---- 诊断 ----

    @property
    def normal_direction_info(self) -> dict:
        """返回法向方向诊断信息，用于 stats/warnings。"""
        n = self.normal
        return {
            "normal_x": round(n.x, 6),
            "normal_y": round(n.y, 6),
            "normal_z": round(n.z, 6),
            "note": "normal_offset_mm > 0 moves along +N; verify N points away from workpiece",
        }
