"""带边框的 3D 机器人预览容器（抽屉 / 首页共用）。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPaintEvent, QPainter, QResizeEvent
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget

from view3d.gl_widget import RobotModelGLWidget


class _AxisLabelOverlay(QWidget):
    """叠在预览上方绘字；鼠标穿透到下方 OpenGL 控件。"""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._hints: list = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)

    def set_hints(self, hints: list) -> None:
        self._hints = hints or []
        self.setVisible(bool(self._hints))

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._hints:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        for hint in self._hints:
            painter.setPen(hint.color)
            painter.drawText(int(hint.screen_x) + 5, int(hint.screen_y) + 4, hint.text)
        painter.end()


class RobotPreviewFrame(QFrame):
    """OpenGL 预览；勿对父级使用 border-radius。"""

    def __init__(self, parent=None, min_height: int = 138):
        super().__init__(parent)
        self.setObjectName("robotPreviewFrame")
        self.setMinimumHeight(min_height)
        self.setStyleSheet("""
            #robotPreviewFrame {
                background-color: #11182d;
                border: 1px solid #2c3a64;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.preview = RobotModelGLWidget(self)
        self.preview.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        layout.addWidget(self.preview, stretch=1)

        self._label_overlay = _AxisLabelOverlay(self)
        self._label_overlay.hide()
        self._label_overlay.raise_()

        self.preview.axis_labels_updated.connect(self._on_axis_labels_updated)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_overlay_geometry()

    def _sync_overlay_geometry(self) -> None:
        self._label_overlay.setGeometry(self.preview.geometry())

    def _on_axis_labels_updated(self, hints: list) -> None:
        self._sync_overlay_geometry()
        self._label_overlay.set_hints(hints)
        if hints:
            self._label_overlay.update()

    def load_robot_type(self, robot_type: str | None) -> None:
        self.preview.load_robot_type(robot_type)

    def load_default_preview(self) -> None:
        self.preview.load_default_preview()

    def update_joint_angles(self, joint_rad: list[float]) -> None:
        self.preview.update_joint_angles(joint_rad)

    def loaded_glb_name(self) -> str:
        return self.preview.loaded_glb_name()

    def refresh(self) -> None:
        self.preview.refresh()

    def reset_camera_view(self) -> None:
        self.preview.reset_camera_view()
