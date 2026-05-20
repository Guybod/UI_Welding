"""轨道相机 — 左键旋转 · 右键平移 · 滚轮缩放（Z-up 模型）。"""

from __future__ import annotations

import math

import numpy as np

_WORLD_UP = np.array([0.0, 0.0, 1.0], dtype=np.float64)
# 默认画面略向下偏（与右键平移同向：正 dy 等效）
_INITIAL_VIEW_PAN_DOWN_PX = 105.0


class OrbitCamera:
    def __init__(self) -> None:
        self.pivot = np.zeros(3, dtype=np.float64)
        self.pan_offset = np.zeros(3, dtype=np.float64)
        self.distance = 3.0
        self.yaw_deg = 35.0
        self.pitch_deg = 25.0
        self.min_pitch_deg = -10.0
        self.max_pitch_deg = 85.0
        self.min_distance = 0.15
        self.max_distance = 80.0

    def reset_to_model(
        self,
        pivot: np.ndarray,
        radius: float,
        viewport_w: int = 800,
        viewport_h: int = 600,
    ) -> None:
        self.pivot = np.array(pivot, dtype=np.float64)
        self.pan_offset = np.zeros(3, dtype=np.float64)
        r = max(float(radius), 0.05)
        self.distance = max(r * 2.4, 0.8)
        self.yaw_deg = 35.0
        self.pitch_deg = 25.0
        self._apply_initial_view_offset(viewport_w, viewport_h)

    def _apply_initial_view_offset(
        self, viewport_w: int, viewport_h: int
    ) -> None:
        w = max(1, viewport_w)
        h = max(1, viewport_h)
        scale = self.distance / max(w, h) * 2.0
        _, up = self._screen_axes()
        self.pan_offset += up * (_INITIAL_VIEW_PAN_DOWN_PX * scale)

    def _orbit_center(self) -> np.ndarray:
        """轨道中心 = 基座中心 + 平移（旋转与平移共用，避免跳变）。"""
        return self.pivot + self.pan_offset

    def orbit_center(self) -> np.ndarray:
        """当前轨道/旋转中心（世界坐标，供三轴辅助显示）。"""
        return self._orbit_center().copy()

    def rotate(self, dx_px: float, dy_px: float, sensitivity: float = 0.4) -> None:
        self.yaw_deg -= dx_px * sensitivity
        self.pitch_deg += dy_px * sensitivity
        self.pitch_deg = max(
            self.min_pitch_deg, min(self.max_pitch_deg, self.pitch_deg)
        )

    def pan(self, dx_px: float, dy_px: float, viewport_w: int, viewport_h: int) -> None:
        """屏幕平移：轨道中心与相机一起移动。"""
        w = max(1, viewport_w)
        h = max(1, viewport_h)
        scale = self.distance / max(w, h) * 2.0
        right, up = self._screen_axes()
        self.pan_offset += right * (-dx_px * scale) + up * (dy_px * scale)

    def zoom_wheel(self, delta_y: float, factor_per_step: float = 0.12) -> None:
        if abs(delta_y) < 1e-6:
            return
        steps = delta_y / 120.0
        factor = (1.0 - factor_per_step) ** steps
        self.distance = max(
            self.min_distance, min(self.max_distance, self.distance * factor)
        )

    def _spherical_offset(self) -> np.ndarray:
        yaw_r = math.radians(self.yaw_deg)
        pitch_r = math.radians(self.pitch_deg)
        cp = math.cos(pitch_r)
        sp = math.sin(pitch_r)
        return np.array(
            [cp * math.cos(yaw_r), cp * math.sin(yaw_r), sp],
            dtype=np.float64,
        )

    def eye_position(self) -> np.ndarray:
        return self._orbit_center() + self._spherical_offset() * self.distance

    def view_matrix(self) -> np.ndarray:
        focus = self._orbit_center().astype(np.float32)
        eye = self.eye_position().astype(np.float32)
        return look_at(eye, focus, _WORLD_UP.astype(np.float32))

    def _screen_axes(self) -> tuple[np.ndarray, np.ndarray]:
        eye = self.eye_position()
        focus = self._orbit_center()
        forward = focus - eye
        fn = float(np.linalg.norm(forward))
        if fn < 1e-8:
            forward = np.array([0.0, 0.0, -1.0], dtype=np.float64)
        else:
            forward /= fn
        right = np.cross(forward, _WORLD_UP)
        rn = float(np.linalg.norm(right))
        if rn < 1e-8:
            right = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        else:
            right /= rn
        up = np.cross(right, forward)
        up /= max(float(np.linalg.norm(up)), 1e-8)
        return right, up


def look_at(eye, center, up):
    eye = np.asarray(eye, dtype=np.float32)
    center = np.asarray(center, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)

    f = center - eye
    fn = float(np.linalg.norm(f))
    if fn < 1e-8:
        f = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    else:
        f /= fn

    s = np.cross(f, up)
    sn = float(np.linalg.norm(s))
    if sn < 1e-8:
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        s = np.cross(f, up)
        sn = float(np.linalg.norm(s))
    s /= sn
    u = np.cross(s, f)

    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -float(np.dot(s, eye))
    m[1, 3] = -float(np.dot(u, eye))
    m[2, 3] = float(np.dot(f, eye))
    return m


def perspective(fov_deg: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(math.radians(fov_deg) * 0.5)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m
