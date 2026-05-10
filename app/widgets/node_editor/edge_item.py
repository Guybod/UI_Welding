from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPen, QColor, QPainterPath
from PySide6.QtCore import QPointF, Qt
from app.widgets.node_editor.models import PORT_COLORS

FLOW_COLOR = QColor(180, 180, 190)


class EdgeItem(QGraphicsPathItem):
    """连线图元 — 贝塞尔曲线连接两个端口"""

    def __init__(self, source_port, target_port=None, parent=None):
        super().__init__(parent)
        self._source = source_port
        self._target = target_port
        self._temp_end = QPointF(0, 0)

        color = self._edge_color()
        self.setPen(QPen(color, 2))
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def _edge_color(self):
        if self._source and self._source.port_type() == "flow":
            return FLOW_COLOR
        pt = self._source.port_type() if self._source else "any"
        return QColor(PORT_COLORS.get(pt, "#9E9E9E"))

    def source(self):
        return self._source

    def target(self):
        return self._target

    def set_temp_end(self, pos: QPointF):
        self._temp_end = pos
        self.update_path()

    def set_target(self, target_port):
        self._target = target_port
        self.update_path()

    def update_path(self):
        p1 = self._source.scene_center() if self._source else self._temp_end
        p2 = self._target.scene_center() if self._target else self._temp_end

        dx = abs(p2.x() - p1.x()) * 0.5
        dx = max(dx, 40)
        cp1 = QPointF(p1.x() + dx, p1.y())
        cp2 = QPointF(p2.x() - dx, p2.y())

        path = QPainterPath()
        path.moveTo(p1)
        path.cubicTo(cp1, cp2, p2)
        self.setPath(path)

    def detach(self):
        if self._source:
            self._source.remove_edge(self)
        if self._target:
            self._target.remove_edge(self)

    def hoverEnterEvent(self, event):
        pen = self.pen()
        pen.setWidth(4)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        pen = self.pen()
        pen.setWidth(2)
        self.setPen(pen)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        s = self.scene()
        if hasattr(s, "_remove_edge"):
            s._remove_edge(self)
        event.accept()
