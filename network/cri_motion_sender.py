"""CRI 运动指令 UDP 发送（端口 9030，与 write4.0 robot_udp_sender 协议一致）。"""

from __future__ import annotations

import math
import socket
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional


class CriMotionSender:
    CMD_FMT = "<q6dBBBBBBBB"
    PACKET_SIZE_BYTES = struct.calcsize(CMD_FMT)

    def __init__(
        self,
        robot_ip: str,
        robot_port: int = 9030,
        frequency_hz: float = 500.0,
        cartesian: bool = True,
        bind_local_ip: str = "",
    ):
        self.robot_ip = robot_ip.strip()
        self.robot_port = int(robot_port)
        self.frequency_hz = max(1.0, float(frequency_hz))
        self.cartesian = cartesian
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if bind_local_ip:
            try:
                self._sock.bind((bind_local_ip.strip(), 0))
            except OSError:
                pass

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass

    def socket_endpoint_info(self) -> dict:
        """本机绑定与 UDP 目标（sendto 目的地）。"""
        local_ip, local_port = "", 0
        try:
            local_ip, local_port = self._sock.getsockname()
        except OSError:
            pass
        fam = self._sock.family
        fam_name = "AF_INET" if fam == socket.AF_INET else str(fam)
        return {
            "robot_ip": self.robot_ip,
            "udp_target_ip": self.robot_ip,
            "udp_target_port": self.robot_port,
            "local_bind_ip": local_ip or "(未绑定/由系统选择)",
            "local_bind_port": local_port,
            "socket_family": fam_name,
            "control_frequency_hz": self.frequency_hz,
            "packet_size_bytes": self.PACKET_SIZE_BYTES,
            "cartesian_mode": self.cartesian,
        }

    @staticmethod
    def read_first_point(traj_path: str | Path) -> Optional[List[float]]:
        path = Path(traj_path)
        if not path.is_file():
            return None
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                return [float(x) for x in parts[:6]]
        return None

    @staticmethod
    def load_points(traj_path: str | Path) -> list[list[float]]:
        path = Path(traj_path)
        points: list[list[float]] = []
        if not path.is_file():
            return points
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                points.append([float(x) for x in parts[:6]])
        return points

    def _convert(self, pose: list[float], cartesian: bool) -> list[float]:
        out = list(pose)
        if cartesian:
            out[0] /= 1000.0
            out[1] /= 1000.0
            out[2] /= 1000.0
            for i in range(3, 6):
                out[i] = math.radians(out[i])
        else:
            for i in range(6):
                out[i] = math.radians(out[i])
        return out

    def _pack(self, pose: list[float], c_type: int) -> bytes:
        ts = int(datetime.now().timestamp() * 1e6)
        return struct.pack(self.CMD_FMT, ts, *pose, c_type, 0, 0, 0, 0, 0, 0, 0)

    @classmethod
    def decode_packet(cls, packet: bytes, *, cartesian: bool) -> dict:
        """解析 64 字节控制包（用于诊断日志）。"""
        if len(packet) != cls.PACKET_SIZE_BYTES:
            return {"error": f"长度异常 len={len(packet)}"}
        ts, x, y, z, rx, ry, rz, ctype, *nc = struct.unpack(cls.CMD_FMT, packet)
        out = {
            "timestamp_us": ts,
            "type": int(ctype),
            "type_name": "末端" if ctype == 1 else "关节",
            "reserved": list(nc),
            "x_m": x,
            "y_m": y,
            "z_m": z,
            "rx_rad": rx,
            "ry_rad": ry,
            "rz_rad": rz,
        }
        if cartesian:
            out["x_mm"] = x * 1000.0
            out["y_mm"] = y * 1000.0
            out["z_mm"] = z * 1000.0
            out["rx_deg"] = math.degrees(rx)
            out["ry_deg"] = math.degrees(ry)
            out["rz_deg"] = math.degrees(rz)
        else:
            out["joint_deg"] = [math.degrees(v) for v in (x, y, z, rx, ry, rz)]
        return out

    def preview_packets(self, traj_path: str | Path) -> dict:
        """预读首末包（不发送）。"""
        points = self.load_points(traj_path)
        if not points:
            return {}
        c_type = 1 if self.cartesian else 0
        first_pkt = self._pack(self._convert(points[0], self.cartesian), c_type)
        last_pkt = self._pack(self._convert(points[-1], self.cartesian), c_type)
        return {
            "first_packet_hex": first_pkt.hex(),
            "first_decoded": self.decode_packet(first_pkt, cartesian=self.cartesian),
            "last_packet_hex": last_pkt.hex(),
            "last_decoded": self.decode_packet(last_pkt, cartesian=self.cartesian),
        }

    def send_file(
        self,
        traj_path: str | Path,
        *,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_elapsed: Optional[Callable[[float, int, int], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> int:
        path = Path(traj_path)
        if not path.is_file():
            raise FileNotFoundError(f"trajectory file not found: {path}")

        points = self.load_points(path)
        if not points:
            return 0

        interval = 1.0 / self.frequency_hz
        start_t = time.time()
        sent = 0
        c_type = 1 if self.cartesian else 0
        total = len(points)
        next_probe = start_t

        try:
            for raw in points:
                if should_stop and should_stop():
                    break
                target = self._convert(raw, self.cartesian)
                packet = self._pack(target, c_type)
                self._sock.sendto(packet, (self.robot_ip, self.robot_port))
                sent += 1
                if on_progress:
                    on_progress(sent, total)
                now = time.time()
                if on_elapsed and (sent == 1 or now - next_probe >= 1.0):
                    on_elapsed(now - start_t, sent, total)
                    next_probe = now
                next_wake = start_t + sent * interval
                remain = next_wake - time.time()
                if remain > 0:
                    time.sleep(remain)
        finally:
            pass
        return sent
