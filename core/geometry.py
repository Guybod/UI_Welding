from __future__ import annotations
import math
import numpy as np
from core.types import Point3D, Quaternion


# ---- 基础向量运算 ----


def cross(a: Point3D, b: Point3D) -> Point3D:
    """叉积"""
    return Point3D(
        x=a.y * b.z - a.z * b.y,
        y=a.z * b.x - a.x * b.z,
        z=a.x * b.y - a.y * b.x,
    )


def dot(a: Point3D, b: Point3D) -> float:
    """点积"""
    return a.x * b.x + a.y * b.y + a.z * b.z


def length(v: Point3D) -> float:
    """向量长度"""
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def distance(a: Point3D, b: Point3D) -> float:
    """两点欧几里得距离"""
    return length(Point3D(x=a.x - b.x, y=a.y - b.y, z=a.z - b.z))


def normalize(v: Point3D) -> Point3D:
    """归一化"""
    n = length(v)
    if n < 1e-12:
        raise ValueError("Cannot normalize zero-length vector")
    return Point3D(x=v.x / n, y=v.y / n, z=v.z / n)


def normal_from_three_points(p1: Point3D, p2: Point3D, p3: Point3D) -> Point3D:
    """三点标定：计算工作平面法向。p1=左上, p2=左下, p3=右下"""
    x_vec = Point3D(x=p3.x - p2.x, y=p3.y - p2.y, z=p3.z - p2.z)
    y_vec = Point3D(x=p1.x - p2.x, y=p1.y - p2.y, z=p1.z - p2.z)
    return normalize(cross(x_vec, y_vec))


# ---- 四元数转换（预留，本轮主流程不使用） ----


def euler_deg_to_quat(rx: float, ry: float, rz: float) -> Quaternion:
    """欧拉角(deg) → 四元数。ZYX 内旋顺序。预留函数。"""
    rx_r, ry_r, rz_r = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(rx_r * 0.5), math.sin(rx_r * 0.5)
    cy, sy = math.cos(ry_r * 0.5), math.sin(ry_r * 0.5)
    cz, sz = math.cos(rz_r * 0.5), math.sin(rz_r * 0.5)
    return Quaternion(
        w=cx * cy * cz + sx * sy * sz,
        x=sx * cy * cz - cx * sy * sz,
        y=cx * sy * cz + sx * cy * sz,
        z=cx * cy * sz - sx * sy * cz,
    )


def quat_to_euler_deg(q: Quaternion) -> tuple[float, float, float]:
    """四元数 → 欧拉角(deg)。ZYX 内旋顺序。预留函数。"""
    sinr_cosp = 2 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1 - 2 * (q.x * q.x + q.y * q.y)
    rx = math.degrees(math.atan2(sinr_cosp, cosr_cosp))

    sinp = 2 * (q.w * q.y - q.z * q.x)
    if abs(sinp) >= 1:
        ry = math.degrees(math.copysign(math.pi / 2, sinp))
    else:
        ry = math.degrees(math.asin(sinp))

    siny_cosp = 2 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
    rz = math.degrees(math.atan2(siny_cosp, cosy_cosp))

    return (rx, ry, rz)
