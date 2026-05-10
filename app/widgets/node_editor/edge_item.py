import math
from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui import QPen, QColor, QPainterPath, QPolygonF, QPainter
from PySide6.QtCore import QPointF, Qt
from app.widgets.node_editor.models import PORT_COLORS

FLOW_COLOR = QColor(180, 180, 190)
FLOW_WIDTH = 2.5


class EdgeItem(QGraphicsPathItem):
    """连线图元 — 贝塞尔曲线连接两个端口, flow 线带方向箭头"""

    def __init__(self, source_port, target_port=None, parent=None):
        super().__init__(parent)
        self._source = source_port
        self._target = target_port
        self._temp_end = QPointF(0, 0)
        self._arrow = QPolygonF()

        color = self._edge_color()
        w = FLOW_WIDTH if (source_port and source_port.port_type() == "flow") else 2
        self.setPen(QPen(color, w))
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    def _is_flow(self) -> bool:
        return self._source is not None and self._source.port_type() == "flow"

    def _edge_color(self):
        if self._is_flow():
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

        # compute arrow triangle at midpoint for flow edges
        if self._is_flow():
            t = 0.5
            mt = 1 - t
            mid = (mt**3) * p1 + 3 * (mt**2) * t * cp1 + 3 * mt * (t**2) * cp2 + (t**3) * p2
            # tangent at midpoint
            tan = (3 * (mt**2)) * (cp1 - p1) + (6 * mt * t) * (cp2 - cp1) + (3 * (t**2)) * (p2 - cp2)
            angle = math.atan2(tan.y(), tan.x())
            size = 7.0
            a1 = angle + math.pi * 0.75
            a2 = angle - math.pi * 0.75
            self._arrow = QPolygonF([
                mid + QPointF(math.cos(angle) * size, math.sin(angle) * size),
                mid + QPointF(math.cos(a1) * size * 0.6, math.sin(a1) * size * 0.6),
                mid + QPointF(math.cos(a2) * size * 0.6, math.sin(a2) * size * 0.6),
            ])
        else:
            self._arrow = QPolygonF()

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if not self._arrow.isEmpty():
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.pen().color())
            painter.drawPolygon(self._arrow)

    def detach(self):
        if self._source:
            self._source.remove_edge(self)
        if self._target:
            self._target.remove_edge(self)

    def hoverEnterEvent(self, event):
        pen = self.pen()
        pen.setWidth(pen.width() + 2)
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        pen = self.pen()
        pen.setWidth(pen.width() - 2)
        self.setPen(pen)
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        s = self.scene()
        if hasattr(s, "_remove_edge"):
            s._remove_edge(self)
        event.accept()
