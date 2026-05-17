"""抽屉内机器人 GLB 预览 — 关节角驱动 + 轨道相机。"""

from __future__ import annotations

import ctypes
from pathlib import Path

import numpy as np
from OpenGL.GL import (
    GL_ARRAY_BUFFER,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_ELEMENT_ARRAY_BUFFER,
    GL_FLOAT,
    GL_FRAGMENT_SHADER,
    GL_LESS,
    GL_LINES,
    GL_STATIC_DRAW,
    GL_TRIANGLES,
    GL_UNSIGNED_INT,
    GL_VERTEX_SHADER,
    glBindBuffer,
    glBindVertexArray,
    glBufferData,
    glClear,
    glClearColor,
    glDepthFunc,
    glDrawArrays,
    glDrawElements,
    glEnable,
    glEnableVertexAttribArray,
    glGenBuffers,
    glGenVertexArrays,
    glGetUniformLocation,
    glLineWidth,
    glViewport,
    glUniform3f,
    glUniformMatrix3fv,
    glUniformMatrix4fv,
    glUseProgram,
    glVertexAttribPointer,
)
from OpenGL.GL.shaders import compileProgram, compileShader
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QShowEvent, QWheelEvent
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from core.logger import log
from core.robot_model_config import get_model_config
from view3d.axis_gizmo import BaseAxisGizmo, base_gizmo_matrix, labels_to_screen
from view3d.camera import OrbitCamera, perspective
from view3d.glb_loader import (
    ArticulatedModel,
    compute_world_matrices_for_model,
    find_base_node_index,
    load_articulated_glb,
)
from view3d.model_resolver import resolve_glb_path


class _GpuPart:
    def __init__(self, vao: int, index_count: int, node_index: int):
        self.vao = vao
        self.index_count = index_count
        self.node_index = node_index


class RobotModelGLWidget(QOpenGLWidget):
    """左键旋转 · 右键平移 · 滚轮缩放。"""

    axis_labels_updated = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._robot_type: str = ""
        self._glb_name: str = ""
        self._model: ArticulatedModel | None = None
        self._joint_axes: list[str] = ["z", "y", "y", "y", "z", "y"]
        self._joint_signs: list[float] = [1.0, 1.0, 1.0, -1.0, -1.0, 1.0]
        self._joint_rad: list[float] = [0.0] * 6
        self._gpu_parts: list[_GpuPart] = []
        self._program = None
        self._u_mvp = 0
        self._u_model = 0
        self._u_normal = 0
        self._u_light = 0
        self._u_color = 0
        self._gl_ready = False
        self._view = np.eye(4, dtype=np.float32)
        self._proj = np.eye(4, dtype=np.float32)
        self._cam = OrbitCamera()
        self._drag_mode: str | None = None
        self._last_mouse = None
        self._press_mouse = None
        self._drag_active = False
        self._drag_threshold_px = 3.0
        self._mouse_grabbed = False
        self._axis_program = None
        self._axis_u_mvp = 0
        self._axis_u_color = 0
        self._axis_length = 0.12
        self._base_axes = BaseAxisGizmo()
        self._show_base_axes = True

        self.setMinimumHeight(100)
        self.setUpdateBehavior(QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def load_default_preview(self) -> None:
        self.load_robot_type("")

    def refresh(self) -> None:
        self.update()

    def reset_camera_view(self) -> None:
        if not self._model:
            return
        self._cam.reset_to_model(
            self._model.orbit_pivot,
            self._model.radius,
            self.width(),
            self.height(),
        )
        self.update()

    def load_robot_type(self, robot_type: str | None) -> None:
        robot_type = robot_type or ""
        path = resolve_glb_path(robot_type or None)
        glb_name = path.name if path else ""

        if robot_type == self._robot_type and glb_name == self._glb_name and self._model:
            return

        self._robot_type = robot_type
        self._glb_name = glb_name
        cfg = get_model_config(self._robot_type) if self._robot_type else None
        if cfg:
            self._joint_axes = list(cfg.joint_axes or self._joint_axes)
            self._joint_signs = list(cfg.joint_signs or self._joint_signs)

        if path is None:
            log.info("[3D] 未找到 GLB 模型 type=%s", self._robot_type)
            self._model = None
        else:
            try:
                self._model = load_articulated_glb(path)
                log.info(
                    "[3D] 型号=%s -> %s (%d 零件)",
                    self._robot_type or "?",
                    path.name,
                    len(self._model.parts),
                )
            except Exception as exc:
                log.info("[3D] 加载失败 %s: %s", path, exc)
                self._model = None
        self._gpu_parts.clear()
        if self._model:
            self._cam.reset_to_model(
                self._model.orbit_pivot,
                self._model.radius,
                self.width(),
                self.height(),
            )
            self._axis_length = max(float(self._model.radius) * 0.22, 0.08)
        if self._gl_ready:
            self.makeCurrent()
            self._upload_parts()
        self._update_projection()
        self.update()

    def loaded_glb_name(self) -> str:
        return self._glb_name

    def update_joint_angles(self, joint_rad: list[float]) -> None:
        if not joint_rad:
            return
        n = min(6, len(joint_rad))
        self._joint_rad = [float(joint_rad[i]) for i in range(n)] + [0.0] * (6 - n)
        self.update()

    def _grab_drag_mouse(self) -> None:
        if not self._mouse_grabbed:
            self.grabMouse()
            self._mouse_grabbed = True

    def _end_drag(self) -> None:
        if self._mouse_grabbed:
            try:
                self.releaseMouse()
            except RuntimeError:
                pass
            self._mouse_grabbed = False
        self._drag_mode = None
        self._last_mouse = None
        self._press_mouse = None
        self._drag_active = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = "rotate"
            self._drag_active = False
            self._press_mouse = event.position()
            self._last_mouse = event.position()
            self._grab_drag_mouse()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._drag_mode = "pan"
            self._drag_active = False
            self._press_mouse = event.position()
            self._last_mouse = event.position()
            self._grab_drag_mouse()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode == "rotate" and not (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self._end_drag()
            return
        if self._drag_mode == "pan" and not (
            event.buttons() & Qt.MouseButton.RightButton
        ):
            self._end_drag()
            return
        if self._drag_mode and self._last_mouse is not None:
            pos = event.position()
            if not self._drag_active and self._press_mouse is not None:
                ox = pos.x() - self._press_mouse.x()
                oy = pos.y() - self._press_mouse.y()
                if (ox * ox + oy * oy) < self._drag_threshold_px ** 2:
                    return
                self._drag_active = True
            dx = pos.x() - self._last_mouse.x()
            dy = pos.y() - self._last_mouse.y()
            if self._drag_mode == "rotate":
                self._cam.rotate(dx, dy)
            elif self._drag_mode == "pan":
                self._cam.pan(dx, dy, self.width(), self.height())
            self._last_mouse = pos
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        btn = event.button()
        if btn == Qt.MouseButton.LeftButton and self._drag_mode == "rotate":
            self._end_drag()
            event.accept()
        elif btn == Qt.MouseButton.RightButton and self._drag_mode == "pan":
            self._end_drag()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:
        self._end_drag()
        super().leaveEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta:
            self._cam.zoom_wheel(float(delta))
            self.update()
            event.accept()
            return
        super().wheelEvent(event)

    def initializeGL(self) -> None:
        glClearColor(0.067, 0.094, 0.176, 1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        self._program = self._build_program()
        self._u_mvp = glGetUniformLocation(self._program, "u_mvp")
        self._u_model = glGetUniformLocation(self._program, "u_model")
        self._u_normal = glGetUniformLocation(self._program, "u_normal_mat")
        self._u_light = glGetUniformLocation(self._program, "u_light_dir")
        self._u_color = glGetUniformLocation(self._program, "u_base_color")
        self._axis_program = self._build_axis_program()
        self._axis_u_mvp = glGetUniformLocation(self._axis_program, "u_mvp")
        self._axis_u_color = glGetUniformLocation(self._axis_program, "u_color")
        self._base_axes.upload()
        self._gl_ready = True
        if self._model:
            self._upload_parts()
            self._cam.reset_to_model(
                self._model.orbit_pivot,
                self._model.radius,
                self.width(),
                self.height(),
            )
            self._axis_length = max(float(self._model.radius) * 0.22, 0.08)
        self._update_projection()

    def resizeGL(self, w: int, h: int) -> None:
        glViewport(0, 0, max(1, w), max(1, h))
        self._update_projection()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._model and self._gl_ready and not self._gpu_parts:
            self.makeCurrent()
            self._upload_parts()
            self.update()

    def paintGL(self) -> None:
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if not self._program or not self._model:
            self.axis_labels_updated.emit([])
            return
        if not self._gpu_parts:
            self._upload_parts()
        if not self._gpu_parts:
            self.axis_labels_updated.emit([])
            return

        self._view = self._cam.view_matrix()

        worlds = compute_world_matrices_for_model(
            self._model,
            self._joint_rad,
            self._joint_axes,
            self._joint_signs,
        )

        label_hints = []
        if self._show_base_axes:
            base_idx = find_base_node_index(self._model)
            if 0 <= base_idx < len(worlds):
                gizmo = base_gizmo_matrix(
                    worlds[base_idx].astype(np.float64), self._axis_length
                )
                raw_labels = self._base_axes.draw(
                    gizmo,
                    self._proj,
                    self._view,
                    self._axis_program,
                    self._axis_u_mvp,
                    self._axis_u_color,
                )
                label_hints = labels_to_screen(
                    raw_labels,
                    self._proj,
                    self._view,
                    self.width(),
                    self.height(),
                )

        glUseProgram(self._program)
        glUniform3f(self._u_light, 0.35, 0.75, 0.55)
        glUniform3f(self._u_color, 0.58, 0.65, 0.82)

        for part in self._gpu_parts:
            world = worlds[part.node_index].astype(np.float32)
            mvp = self._proj @ self._view @ world
            try:
                normal_mat = np.linalg.inv((self._view @ world)[:3, :3]).T.astype(
                    np.float32
                )
            except np.linalg.LinAlgError:
                continue
            glUniformMatrix4fv(self._u_mvp, 1, True, mvp)
            glUniformMatrix4fv(self._u_model, 1, True, np.eye(4, dtype=np.float32))
            glUniformMatrix3fv(self._u_normal, 1, True, normal_mat)
            glBindVertexArray(part.vao)
            glDrawElements(GL_TRIANGLES, part.index_count, GL_UNSIGNED_INT, None)
        self._restore_gl_state()
        self.axis_labels_updated.emit(label_hints)

    def _restore_gl_state(self) -> None:
        glBindVertexArray(0)
        glUseProgram(self._program)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)

    def _build_program(self):
        shader_dir = Path(__file__).parent / "shaders"
        vert_src = (shader_dir / "vertex.glsl").read_text(encoding="utf-8")
        frag_src = (shader_dir / "fragment.glsl").read_text(encoding="utf-8")
        return compileProgram(
            compileShader(vert_src, GL_VERTEX_SHADER),
            compileShader(frag_src, GL_FRAGMENT_SHADER),
        )

    def _build_axis_program(self):
        shader_dir = Path(__file__).parent / "shaders"
        vert_src = (shader_dir / "axis_vertex.glsl").read_text(encoding="utf-8")
        frag_src = (shader_dir / "axis_fragment.glsl").read_text(encoding="utf-8")
        return compileProgram(
            compileShader(vert_src, GL_VERTEX_SHADER),
            compileShader(frag_src, GL_FRAGMENT_SHADER),
        )

    def _upload_parts(self) -> None:
        self._gpu_parts.clear()
        if not self._model:
            return
        for part in self._model.parts:
            interleaved = np.hstack([part.vertices, part.normals]).astype(np.float32)
            vao = glGenVertexArrays(1)
            vbo = glGenBuffers(1)
            ebo = glGenBuffers(1)
            glBindVertexArray(vao)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes, interleaved, GL_STATIC_DRAW)
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
            glBufferData(
                GL_ELEMENT_ARRAY_BUFFER, part.indices.nbytes, part.indices, GL_STATIC_DRAW
            )
            stride = 6 * 4
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(0, 3, GL_FLOAT, False, stride, None)
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(1, 3, GL_FLOAT, False, stride, ctypes.c_void_p(12))
            glBindVertexArray(0)
            self._gpu_parts.append(
                _GpuPart(vao, int(part.indices.size), part.node_index)
            )

    def _update_projection(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        aspect = w / h
        radius = self._model.radius if self._model else 1.0
        near = max(radius * 0.02, 0.05)
        far = max(radius * 30.0, 50.0)
        self._proj = perspective(45.0, aspect, near, far)
