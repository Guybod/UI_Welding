import struct


class CriParser:
    """CRI 二进制数据解析 — 固定配置 mask=0xFFFF, highPercision=true, 6轴, 0外部轴, 308字节"""

    HIGH_PERCISION = True       # Float64 (故意沿用控制器拼写)
    AXIS_COUNT = 6
    EXTERNAL_AXIS_COUNT = 0
    EXPECTED_SIZE = 308

    @classmethod
    def parse(cls, data: bytes) -> dict:
        """解析 308 字节 CRI 数据报, 返回 dict"""
        fmt = "<"     # little-endian
        fmt += "q"    # Int64 timestamp (8B)
        fmt += "H"    # UInt16 statusData1 (2B)
        fmt += "H"    # UInt16 statusData2 (2B)
        # bits 3-7: reserved, mask set but no data
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] joint_position (48B)
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] joint_velocity (48B)
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] end_position x,y,z,rx,ry,rz (48B)
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] end_velocity (48B)
        fmt += "d"                    # Float64 linear_speed (8B)
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] joint_torque (48B)
        fmt += "d" * cls.AXIS_COUNT   # Float64[6] joint_force (48B)
        # external_axis_count=0 → no data for bit 15

        values = struct.unpack(fmt, data)

        status1 = values[1]
        status2 = values[2]
        idx = 3

        joint_position = list(values[idx:idx + cls.AXIS_COUNT]); idx += cls.AXIS_COUNT
        joint_velocity = list(values[idx:idx + cls.AXIS_COUNT]); idx += cls.AXIS_COUNT
        end_position = list(values[idx:idx + cls.AXIS_COUNT]); idx += cls.AXIS_COUNT
        end_velocity = list(values[idx:idx + cls.AXIS_COUNT]); idx += cls.AXIS_COUNT
        linear_speed = values[idx]; idx += 1
        joint_torque = list(values[idx:idx + cls.AXIS_COUNT]); idx += cls.AXIS_COUNT
        joint_force = list(values[idx:idx + cls.AXIS_COUNT])

        # statusData1 bit flags
        is_moving = bool(status1 & (1 << 7))
        is_enabled = bool(status1 & (1 << 3))
        is_emergency = bool(status1 & (1 << 12))  # high byte bit4 = overall bit12

        return {
            "timestamp": values[0],
            "joint_position": joint_position,        # rad
            "joint_velocity": joint_velocity,        # rad/s
            "tcp_x": end_position[0],                # m
            "tcp_y": end_position[1],                # m
            "tcp_z": end_position[2],                # m
            "tcp_rx": end_position[3],               # rad
            "tcp_ry": end_position[4],               # rad
            "tcp_rz": end_position[5],               # rad
            "tcp_velocity": end_velocity,            # m/s, rad/s
            "tcp_linear_speed": linear_speed,        # m/s
            "joint_torque": joint_torque,            # Nm
            "joint_external_force": joint_force,     # Nm
            "is_moving": is_moving,
            "is_enabled": is_enabled,
            "is_emergency_stop": is_emergency,
            "status1": status1,
            "status2": status2,
        }
