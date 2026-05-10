import math
from PySide6.QtCore import QObject

RAD_TO_DEG = 180.0 / math.pi


class RobotRealtimeState(QObject):
    """CRI 实时状态缓存 — 全局单例, 线程安全(仅 UI 线程访问)"""

    _instance = None

    def __init__(self):
        super().__init__()
        self._valid = False
        self._joint_rad: list[float] = []
        self._tcp_x_m: float = 0.0
        self._tcp_y_m: float = 0.0
        self._tcp_z_m: float = 0.0
        self._tcp_rx_rad: float = 0.0
        self._tcp_ry_rad: float = 0.0
        self._tcp_rz_rad: float = 0.0
        self._is_moving: bool = False

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def update_from_cri_frame(self, frame: dict):
        """CRI 帧到达时调用, frame 包含 joint_position(rad), tcp_x/y/z(m), tcp_rx/ry/rz(rad)"""
        self._valid = True
        self._joint_rad = frame.get("joint_position", [])
        self._tcp_x_m = frame.get("tcp_x", 0.0)
        self._tcp_y_m = frame.get("tcp_y", 0.0)
        self._tcp_z_m = frame.get("tcp_z", 0.0)
        self._tcp_rx_rad = frame.get("tcp_rx", 0.0)
        self._tcp_ry_rad = frame.get("tcp_ry", 0.0)
        self._tcp_rz_rad = frame.get("tcp_rz", 0.0)
        # is_moving from statusData1 bit7 (placeholder)
        self._is_moving = frame.get("is_moving", False)

    def is_valid(self) -> bool:
        return self._valid

    def is_moving(self) -> bool:
        return self._is_moving

    def current_joints_deg(self) -> list[float]:
        """返回 J1~J6 关节角 (deg)"""
        return [j * RAD_TO_DEG for j in self._joint_rad]

    def current_tcp_pose_mm_deg(self) -> tuple[float, float, float, float, float, float]:
        """返回 (x_mm, y_mm, z_mm, a_deg, b_deg, c_deg)"""
        return (
            self._tcp_x_m * 1000.0,
            self._tcp_y_m * 1000.0,
            self._tcp_z_m * 1000.0,
            self._tcp_rx_rad * RAD_TO_DEG,
            self._tcp_ry_rad * RAD_TO_DEG,
            self._tcp_rz_rad * RAD_TO_DEG,
        )
