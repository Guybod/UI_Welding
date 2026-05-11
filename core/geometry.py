import math
import numpy as np
from core.types import Point3D


def cross(a: Point3D, b: Point3D) -> Point3D:
    return Point3D(
        x=a.y * b.z - a.z * b.y,
        y=a.z * b.x - a.x * b.z,
        z=a.x * b.y - a.y * b.x,
    )


def normalize(v: Point3D) -> Point3D:
    length = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    if length < 1e-12:
        raise ValueError("Cannot normalize zero-length vector")
    return Point3D(x=v.x / length, y=v.y / length, z=v.z / length)


def normal_from_three_points(p1: Point3D, p2: Point3D, p3: Point3D) -> Point3D:
    """三点标定：计算工作平面法向。p1=左上, p2=左下, p3=右下"""
    x_vec = Point3D(x=p3.x - p2.x, y=p3.y - p2.y, z=p3.z - p2.z)
    y_vec = Point3D(x=p1.x - p2.x, y=p1.y - p2.y, z=p1.z - p2.z)
    return normalize(cross(x_vec, y_vec))
