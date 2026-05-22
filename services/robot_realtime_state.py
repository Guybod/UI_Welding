import math
from datetime import datetime
from enum import Enum

from PySide6.QtCore import QObject

from core.logger import log
from core.unit_converter import deg_list_to_rad, deg_to_rad, mm_to_m

RAD_TO_DEG = 180.0 / math.pi


class PoseSource(str, Enum):
    NONE = "none"
    CRI_UDP = "cri_udp"
    TCP_SUBSCRIBE = "tcp_subscribe"


class RobotRealtimeState(QObject):
    """机器人位姿与运行态缓存 — 全局单例，仅 UI 线程访问。"""

    _instance = None

    def __init__(self):
        super().__init__()
        self._pose_source = PoseSource.NONE
        self._cri_primary_valid = False
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
        self._last_switch_to_subscribe_at: str = ""
        self._last_switch_to_cri_at: str = ""
        self._last_posture_db: dict | None = None
        self._tcp_pose_valid: bool = False

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def pose_source(self) -> PoseSource:
        return self._pose_source

    @staticmethod
    def _now_ts() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def last_switch_to_subscribe_at(self) -> str:
        return self._last_switch_to_subscribe_at

    def last_switch_to_cri_at(self) -> str:
        return self._last_switch_to_cri_at

    def has_pose(self) -> bool:
        """任一来源已缓存关节或 TCP（读当前点、填工作空间）。"""
        return len(self._joint_rad) >= 6 or self._tcp_pose_valid

    @staticmethod
    def tcp_mm_deg_from_posture_db(db: dict) -> tuple[float, float, float, float, float, float] | None:
        """从 publish/RobotPosture 的 db 解析 TCP（mm/deg），不改动缓存。"""
        end = db.get("end") or {}
        if not end:
            return None
        return (
            float(end.get("x", 0.0)),
            float(end.get("y", 0.0)),
            float(end.get("z", 0.0)),
            float(end.get("a", 0.0)),
            float(end.get("b", 0.0)),
            float(end.get("c", 0.0)),
        )

    def remember_posture(self, db: dict | None) -> None:
        """保存最近订阅 payload，供无 CRI 时「更新」按钮读取。"""
        if db:
            self._last_posture_db = dict(db)

    def read_pose_for_workspace_update(
        self,
    ) -> tuple[tuple[float, float, float, float, float, float], PoseSource] | None:
        """焊接/绘图工作空间「更新」：CRI 可用用 CRI，否则用最近订阅。"""
        if self.is_cri_primary() and self.has_pose():
            return self.current_tcp_pose_mm_deg(), PoseSource.CRI_UDP
        if self._last_posture_db:
            tcp = self.tcp_mm_deg_from_posture_db(self._last_posture_db)
            if tcp is not None:
                return tcp, PoseSource.TCP_SUBSCRIBE
            if not self.is_cri_primary():
                self.update_from_robot_posture(self._last_posture_db)
                if self.has_pose():
                    return self.current_tcp_pose_mm_deg(), PoseSource.TCP_SUBSCRIBE
        if self.has_pose():
            return self.current_tcp_pose_mm_deg(), self._pose_source
        return None

    def is_cri_primary(self) -> bool:
        """CRI UDP 为位姿权威（执行/起点核对须为 True）。"""
        return self._cri_primary_valid

    def is_valid(self) -> bool:
        """兼容旧调用：等同 has_pose()。"""
        return self.has_pose()

    def update_from_cri_frame(self, frame: dict):
        """CRI UDP 帧：关节 rad，TCP m/rad。"""
        was_subscribe_primary = (
            not self._cri_primary_valid
            and self._pose_source == PoseSource.TCP_SUBSCRIBE
        )
        self._cri_primary_valid = True
        self._pose_source = PoseSource.CRI_UDP
        if was_subscribe_primary:
            ts = self._now_ts()
            self._last_switch_to_cri_at = ts
            log.info(
                "[CRI] %s 位姿数据源恢复: 订阅 publish/RobotPosture -> CRI UDP",
                ts,
            )
        self._joint_rad = list(frame.get("joint_position", []))
        self._tcp_x_m = float(frame.get("tcp_x", 0.0))
        self._tcp_y_m = float(frame.get("tcp_y", 0.0))
        self._tcp_z_m = float(frame.get("tcp_z", 0.0))
        self._tcp_rx_rad = float(frame.get("tcp_rx", 0.0))
        self._tcp_ry_rad = float(frame.get("tcp_ry", 0.0))
        self._tcp_rz_rad = float(frame.get("tcp_rz", 0.0))
        self._is_moving = bool(frame.get("is_moving", False))
        self._is_enabled = bool(frame.get("is_enabled", False))
        self._is_emergency = bool(frame.get("is_emergency_stop", False))
        self._status1 = int(frame.get("status1", 0))
        self._status2 = int(frame.get("status2", 0))
        self._cri_rt_mode = bool(self._status2 & 0x01)
        self._cri_error_code = (self._status2 >> 8) & 0xFF
        self._tcp_pose_valid = True

    def update_from_robot_posture(self, db: dict) -> bool:
        """publish/RobotPosture：关节 deg，TCP mm/deg。CRI 权威时不覆盖。"""
        self.remember_posture(db)
        if self._cri_primary_valid:
            return False
        joint = db.get("joint") or []
        end = db.get("end") or {}
        updated = False
        if joint and len(joint) >= 6:
            self._joint_rad = deg_list_to_rad([float(v) for v in joint[:6]])
            updated = True
        if end:
            self._tcp_x_m = mm_to_m(float(end.get("x", 0.0)))
            self._tcp_y_m = mm_to_m(float(end.get("y", 0.0)))
            self._tcp_z_m = mm_to_m(float(end.get("z", 0.0)))
            self._tcp_rx_rad = deg_to_rad(float(end.get("a", 0.0)))
            self._tcp_ry_rad = deg_to_rad(float(end.get("b", 0.0)))
            self._tcp_rz_rad = deg_to_rad(float(end.get("c", 0.0)))
            self._tcp_pose_valid = True
            updated = True
        if updated:
            self._pose_source = PoseSource.TCP_SUBSCRIBE
        return updated

    def invalidate_cri_primary(self, *, reason: str = "") -> None:
        """连续无完整 CRI 帧：放弃 CRI 权威，保留缓存直至订阅更新。"""
        was_primary = self._cri_primary_valid
        self._cri_primary_valid = False
        if was_primary:
            ts = self._now_ts()
            self._last_switch_to_subscribe_at = ts
            detail = f" ({reason})" if reason else ""
            log.warning(
                "[CRI] %s 位姿数据源切换: CRI UDP -> 订阅 publish/RobotPosture%s",
                ts,
                detail,
            )
        if self._pose_source == PoseSource.CRI_UDP:
            self._pose_source = (
                PoseSource.TCP_SUBSCRIBE
                if self.has_pose()
                else PoseSource.NONE
            )

    def invalidate(self) -> None:
        """CRI 停止或登出：清空位姿缓存。"""
        self._cri_primary_valid = False
        self._pose_source = PoseSource.NONE
        self._last_switch_to_subscribe_at = ""
        self._last_switch_to_cri_at = ""
        self._last_posture_db = None
        self._tcp_pose_valid = False
        self._joint_rad = []
        self._tcp_x_m = 0.0
        self._tcp_y_m = 0.0
        self._tcp_z_m = 0.0
        self._tcp_rx_rad = 0.0
        self._tcp_ry_rad = 0.0
        self._tcp_rz_rad = 0.0

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
        return self._cri_rt_mode

    def cri_error_code(self) -> int:
        return self._cri_error_code

    def status1(self) -> int:
        return self._status1

    def status2(self) -> int:
        return self._status2

    def current_joint_rad(self) -> list[float]:
        return list(self._joint_rad)

    def current_joints_deg(self) -> list[float]:
        return [j * RAD_TO_DEG for j in self._joint_rad]

    def current_tcp_pose_mm_deg(self) -> tuple[float, float, float, float, float, float]:
        return (
            self._tcp_x_m * 1000.0,
            self._tcp_y_m * 1000.0,
            self._tcp_z_m * 1000.0,
            self._tcp_rx_rad * RAD_TO_DEG,
            self._tcp_ry_rad * RAD_TO_DEG,
            self._tcp_rz_rad * RAD_TO_DEG,
        )
