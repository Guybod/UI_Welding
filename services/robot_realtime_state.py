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
        self._is_enabled: bool = False
        self._is_emergency: bool = False
        self._robot_mode: int = -1
        self._robot_state: int = -1
        self._last_error: str = ""
        self._status1: int = 0
        self._status2: int = 0
        self._cri_rt_mode: bool = False
        self._cri_error_code: int = 0

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
        self._is_enabled = frame.get("is_enabled", False)
        self._is_emergency = frame.get("is_emergency_stop", False)
        self._status1 = int(frame.get("status1", 0))
        self._status2 = int(frame.get("status2", 0))
        self._cri_rt_mode = bool(self._status2 & 0x01)
        self._cri_error_code = (self._status2 >> 8) & 0xFF

    def is_valid(self) -> bool:
        return self._valid

    def invalidate(self) -> None:
        """CRI 停止后清除，允许 RobotPosture 兜底驱动 3D。"""
        self._valid = False
        self._joint_rad = []

    def is_moving(self) -> bool:
        return self._is_moving

    def is_enabled(self) -> bool:
        return self._is_enabled

    def is_emergency_stop(self) -> bool:
        return self._is_emergency

    def update_robot_status(self, db: dict) -> None:
        """由 publish/RobotStatus 更新（模式/状态）。"""
        if "mode" in db:
            self._robot_mode = int(db.get("mode", -1))
        if "state" in db:
            self._robot_state = int(db.get("state", -1))

    def set_last_error(self, text: str) -> None:
        self._last_error = text or ""

    def robot_mode(self) -> int:
        return self._robot_mode

    def robot_state(self) -> int:
        return self._robot_state

    def last_error(self) -> str:
        return self._last_error

    def cri_realtime_mode(self) -> bool:
        """statusData2 低字节 bit0：是否处于 CRI 实时控制模式。"""
        return self._cri_rt_mode

    def cri_error_code(self) -> int:
        """statusData2 高字节：CRI 实时控制错误码。"""
        return self._cri_error_code

    def status1(self) -> int:
        return self._status1

    def status2(self) -> int:
        return self._status2

    def current_joint_rad(self) -> list[float]:
        return list(self._joint_rad)

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
