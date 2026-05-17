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

    def __init__(
        self,
        robot_ip: str,
        robot_port: int = 9030,
        frequency_hz: float = 500.0,
        cartesian: bool = True,
    ):
        self.robot_ip = robot_ip.strip()
        self.robot_port = robot_port
        self.frequency_hz = max(1.0, float(frequency_hz))
        self.cartesian = cartesian
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass

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

    def _pack(self, pose: list[float], c_type: int) -> bytes:
        ts = int(datetime.now().timestamp() * 1e6)
        return struct.pack(self.CMD_FMT, ts, *pose, c_type, 0, 0, 0, 0, 0, 0, 0)

    @staticmethod
    def _convert(pose: list[float], cartesian: bool) -> list[float]:
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

    def send_file(
        self,
        traj_path: str | Path,
        *,
        on_progress: Optional[Callable[[int, int], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> int:
        path = Path(traj_path)
        if not path.is_file():
            raise FileNotFoundError(f"trajectory file not found: {path}")

        points: list[list[float]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                points.append([float(x) for x in parts[:6]])

        if not points:
            return 0

        interval = 1.0 / self.frequency_hz
        start_t = time.time()
        sent = 0
        c_type = 1 if self.cartesian else 0
        total = len(points)

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
                next_wake = start_t + sent * interval
                remain = next_wake - time.time()
                if remain > 0:
                    time.sleep(remain)
        finally:
            pass
        return sent
