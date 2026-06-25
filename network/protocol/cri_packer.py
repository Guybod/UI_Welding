"""CRI CommandData 二进制打包 — struct.pack 方向（小端）

CommandData struct (64 bytes):
    Int64   timestamp       (8 bytes)
    Float64 position[6]     (48 bytes) — x, y, z, rx, ry, rz
    UInt8   type            (1 byte)   — 0: joint, 1: end
    UInt8   nc[7]           (7 bytes)  — reserved
"""

import struct
from core.unit_converter import mm_to_m, deg_to_rad

# 小端格式: q=Int64, d=Float64, B=UInt8
_FMT = "<q6dB7B"


def pack_command_data(
    timestamp: int,
    position: list[float],  # [x, y, z, rx, ry, rz] in mm and deg
    type_: int = 1,         # 1 = 末端控制
) -> bytes:
    """打包 CommandData 为 64 字节小端二进制。

    Args:
        timestamp: 时间戳（整数，毫秒或自定义计数）
        position: [x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg]
        type_: 0=关节控制, 1=末端控制

    Returns:
        64 字节 bytes
    """
    x_m, y_m, z_m = mm_to_m(position[0]), mm_to_m(position[1]), mm_to_m(position[2])
    rx_rad, ry_rad, rz_rad = (
        deg_to_rad(position[3]),
        deg_to_rad(position[4]),
        deg_to_rad(position[5]),
    )
    nc = (0, 0, 0, 0, 0, 0, 0)
    return struct.pack(_FMT, timestamp, x_m, y_m, z_m, rx_rad, ry_rad, rz_rad, type_, *nc)


def pack_size() -> int:
    """返回 CommandData 结构的大小。"""
    return struct.calcsize(_FMT)
