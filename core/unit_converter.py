import math

RAD_TO_DEG = 180.0 / math.pi
M_TO_MM = 1000.0


def rad_to_deg(rad: float) -> float:
    return rad * RAD_TO_DEG


def rad_list_to_deg(rad_list: list[float]) -> list[float]:
    return [v * RAD_TO_DEG for v in rad_list]


def m_to_mm(m: float) -> float:
    return m * M_TO_MM


def deg_to_rad(deg: float) -> float:
    return deg / RAD_TO_DEG


def mm_to_m(mm: float) -> float:
    return mm / M_TO_MM
