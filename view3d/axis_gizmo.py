"""基座坐标系 — 带箭头与 XYZ 标识（随 Base 节点变换）。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_DEPTH_TEST,
    GL_ELEMENT_ARRAY_BUFFER,
    GL_FLOAT,
    GL_LINES,
    GL_POLYGON_OFFSET_FILL,
    GL_STATIC_DRAW,
    GL_TRIANGLES,
    GL_UNSIGNED_INT,
    glBindBuffer,
    glBindVertexArray,
    glBufferData,
    glDisable,
    glDisableVertexAttribArray,
    glDrawArrays,
    glDrawElements,
    glEnable,
    glEnableVertexAttribArray,
    glGenBuffers,
    glGenVertexArrays,
    glLineWidth,
    glPolygonOffset,
    glUniform3f,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribPointer,
)
from PySide6.QtGui import QColor

_SHAFT_END = 0.78
_TIP = 1.0
_CONE_RADIUS = 0.06
_CONE_SEGMENTS = 10

_AXIS_DIRS = (
    np.array([1.0, 0.0, 0.0], dtype=np.float64),
    np.array([0.0, -1.0, 0.0], dtype=np.float64),
    np.array([0.0, 0.0, 1.0], dtype=np.float64),
)
_AXIS_COLORS = (
    (1.0, 0.28, 0.28),
    (0.28, 0.95, 0.42),
    (0.38, 0.58, 1.0),
)
_AXIS_LABELS = ("X", "Y", "Z")
_QT_COLORS = (
    QColor(255, 90, 90),
    QColor(90, 240, 120),
    QColor(120, 160, 255),
)


@dataclass
class AxisLabelHint:
    screen_x: float
    screen_y: float
    text: str
    color: QColor


def rotation_from_world(world: np.ndarray) -> np.ndarray:
    """去掉缩放，保留基座朝向（3x3 正交）。"""
    m = np.asarray(world[:3, :3], dtype=np.float64)
    cols = []
    for i in range(3):
        v = m[:, i]
        n = float(np.linalg.norm(v))
        cols.append(v / n if n > 1e-8 else np.eye(3, dtype=np.float64)[:, i])
    r = np.column_stack(cols)
    if np.linalg.det(r) < 0:
        r[:, 1] *= -1.0
    return r


def base_gizmo_matrix(
    base_world: np.ndarray, length: float, flip_y: bool = True
) -> np.ndarray:
    r = rotation_from_world(base_world)
    if flip_y:
        r[:, 1] *= -1.0
    m = np.eye(4, dtype=np.float32)
    m[:3, :3] = (r * float(length)).astype(np.float32)
    m[:3, 3] = np.asarray(base_world[:3, 3], dtype=np.float32)
    return m


def _perp_vectors(direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = direction / max(float(np.linalg.norm(direction)), 1e-8)
    ref = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(np.dot(d, ref))) > 0.9:
        ref = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    u = np.cross(d, ref)
    u /= max(float(np.linalg.norm(u)), 1e-8)
    v = np.cross(d, u)
    v /= max(float(np.linalg.norm(v)), 1e-8)
    return u, v


def _bind_axis_vao(vao: int, verts: np.ndarray, indices: np.ndarray | None) -> None:
    vbo = glGenBuffers(1)
    glBindVertexArray(vao)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
    if indices is not None:
        ebo = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
    glDisableVertexAttribArray(1)


def _build_geometry() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lines: list[list[float]] = []
    verts: list[list[float]] = []
    indices: list[int] = []

    for direction in _AXIS_DIRS:
        d = direction / max(float(np.linalg.norm(direction)), 1e-8)
        lines.append([0.0, 0.0, 0.0])
        lines.append((d * _SHAFT_END).tolist())
        base_c = d * _SHAFT_END
        tip = d * _TIP
        u, v = _perp_vectors(d)
        ring: list[int] = []
        for i in range(_CONE_SEGMENTS):
            ang = 2.0 * np.pi * i / _CONE_SEGMENTS
            p = base_c + (u * np.cos(ang) + v * np.sin(ang)) * _CONE_RADIUS
            ring.append(len(verts))
            verts.append(p.tolist())
        tip_i = len(verts)
        verts.append(tip.tolist())
        for i in range(_CONE_SEGMENTS):
            indices.extend([ring[i], ring[(i + 1) % _CONE_SEGMENTS], tip_i])

    return (
        np.asarray(lines, dtype=np.float32),
        np.asarray(verts, dtype=np.float32),
        np.asarray(indices, dtype=np.uint32),
    )


class BaseAxisGizmo:
    def __init__(self) -> None:
        self._line_vao = 0
        self._cone_vaos: list[int] = []
        self._cone_index_count = 0
        self._ready = False

    def upload(self) -> None:
        line_verts, cone_verts, cone_idx = _build_geometry()
        self._line_vao = glGenVertexArrays(1)
        _bind_axis_vao(self._line_vao, line_verts, None)

        verts_per_cone = _CONE_SEGMENTS + 1
        tri_count = _CONE_SEGMENTS * 3
        self._cone_index_count = tri_count
        self._cone_vaos = []
        for axis_i in range(3):
            v_start = axis_i * verts_per_cone
            v_end = v_start + verts_per_cone
            i_start = axis_i * tri_count
            i_end = i_start + tri_count
            axis_verts = cone_verts[v_start:v_end]
            axis_idx = (cone_idx[i_start:i_end] - v_start).astype(np.uint32)
            vao = glGenVertexArrays(1)
            _bind_axis_vao(vao, axis_verts, axis_idx)
            self._cone_vaos.append(vao)
        glBindVertexArray(0)
        self._ready = True

    def draw(
        self,
        gizmo_world: np.ndarray,
        proj: np.ndarray,
        view: np.ndarray,
        program: int,
        u_mvp: int,
        u_color: int,
    ) -> list[tuple[np.ndarray, str, QColor]]:
        if not self._ready:
            return []
        labels: list[tuple[np.ndarray, str, QColor]] = []

        glBindVertexArray(0)
        glUseProgram(program)
        glLineWidth(2.5)
        mvp = (proj @ view @ gizmo_world).astype(np.float32)
        glEnable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(2.0, 2.0)

        for i in range(3):
            rgb = _AXIS_COLORS[i]
            glUniform3f(u_color, *rgb)
            glUniformMatrix4fv(u_mvp, 1, True, mvp)

            glBindVertexArray(self._line_vao)
            glDrawArrays(GL_LINES, i * 2, 2)
            glBindVertexArray(self._cone_vaos[i])
            glDrawElements(
                GL_TRIANGLES,
                self._cone_index_count,
                GL_UNSIGNED_INT,
                None,
            )

            tip_local = np.append(_AXIS_DIRS[i] * _TIP, 1.0)
            tip_world = (gizmo_world @ tip_local)[:3]
            labels.append((tip_world.astype(np.float64), _AXIS_LABELS[i], _QT_COLORS[i]))

        glDisable(GL_POLYGON_OFFSET_FILL)
        glBindVertexArray(0)
        glEnable(GL_DEPTH_TEST)
        return labels


def project_world_to_screen(
    world: np.ndarray, mvp: np.ndarray, width: int, height: int
) -> tuple[float, float] | None:
    p = np.array([*world, 1.0], dtype=np.float32)
    clip = mvp @ p
    w = float(clip[3])
    if w <= 1e-6:
        return None
    ndc = clip[:3] / w
    if ndc[0] < -1.2 or ndc[0] > 1.2 or ndc[1] < -1.2 or ndc[1] > 1.2:
        return None
    x = (float(ndc[0]) * 0.5 + 0.5) * max(1, width)
    y = (1.0 - (float(ndc[1]) * 0.5 + 0.5)) * max(1, height)
    return x, y


def labels_to_screen(
    label_worlds: list[tuple[np.ndarray, str, QColor]],
    proj: np.ndarray,
    view: np.ndarray,
    width: int,
    height: int,
) -> list[AxisLabelHint]:
    mvp = (proj @ view).astype(np.float32)
    out: list[AxisLabelHint] = []
    for world, text, color in label_worlds:
        pt = project_world_to_screen(world, mvp, width, height)
        if pt is None:
            continue
        out.append(AxisLabelHint(pt[0], pt[1], text, color))
    return out
