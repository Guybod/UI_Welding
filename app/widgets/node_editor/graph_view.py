from PySide6.QtWidgets import QGraphicsView
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent
from PySide6.QtCore import Qt


class GraphView(QGraphicsView):
    """节点编辑器视图 — 滚轮缩放 + 中键/右键拖拽平移 + 抗锯齿"""

    _zoom_min = 0.1
    _zoom_max = 3.0
    _zoom_factor = 1.15

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self._pan_start = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            factor = self._zoom_factor
        else:
            factor = 1.0 / self._zoom_factor
        current = self.transform().m11()
        if current * factor < self._zoom_min or current * factor > self._zoom_max:
            return
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            fake = QMouseEvent(
                event.type(), event.pos(), Qt.LeftButton,
                Qt.LeftButton, event.modifiers()
            )
            super().mousePressEvent(fake)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self.setDragMode(QGraphicsView.NoDrag)
            fake = QMouseEvent(
                event.type(), event.pos(), Qt.LeftButton,
                Qt.LeftButton, event.modifiers()
            )
            super().mouseReleaseEvent(fake)
        else:
            super().mouseReleaseEvent(event)
