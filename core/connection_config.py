import random
import socket
from dataclasses import dataclass


@dataclass
class LocalNetworkInterface:
    name: str           # 网卡名称, 如 "以太网"
    description: str    # 描述, 如 "Intel(R) Ethernet Controller..."
    ipv4: str           # IPv4 地址
    is_up: bool = True
    is_loopback: bool = False
    is_virtual: bool = False


@dataclass
class ConnectionConfig:
    robot_ip: str = "192.168.1.136"
    local_ip: str = ""
    local_interface: LocalNetworkInterface | None = None
    udp_port: int = 0   # 0 = 未分配, 由 pick_available_udp_port() 生成

    def is_valid(self) -> bool:
        return bool(self.robot_ip and self.local_ip and self.udp_port > 0)


def pick_available_udp_port(min_port: int = 10000, max_port: int = 65535, retry: int = 10) -> int:
    """预检查端口可用性，失败自动重试"""
    for _ in range(retry):
        port = random.randint(min_port, max_port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()
    raise RuntimeError("无法自动分配可用 UDP 端口，请手动指定")
