from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsSceneMouseEvent
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from PySide6.QtCore import Qt, QPointF

from app.widgets.node_editor.models import PORT_COLORS

PORT_RADIUS = 5.0
HOVER_RADIUS = PORT_RADIUS + 2


class PortItem(QGraphicsEllipseItem):
    """节点端口图元 — 圆形, 维护已连接边列表, 支持拖拽连线"""

    def __init__(self, port_name: str, port_type: str, direction: str, parent=None):
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, parent)
        self._port_name = port_name
        self._port_type = port_type
        self._direction = direction
        self.connected_edges: list = []
        self._dragging = False
        self._color = QColor(PORT_COLORS.get(port_type, "#9E9E9E"))

        self.setBrush(QBrush(self._color))
        self.setPen(QPen(self._color.darker(150), 1))
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

    def port_name(self) -> str:
        return self._port_name

    def port_type(self) -> str:
        return self._port_type

    def direction(self) -> str:
        return self._direction

    def scene_center(self) -> QPointF:
        return self.mapToScene(self.boundingRect().center())

    def add_edge(self, edge):
        if edge not in self.connected_edges:
            self.connected_edges.append(edge)

    def remove_edge(self, edge):
        if edge in self.connected_edges:
            self.connected_edges.remove(edge)

    def update_edges(self):
        for edge in self.connected_edges:
            edge.update_path()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.LeftButton and self._direction == "output":
            self._dragging = True
            s = self.scene()
            if hasattr(s, "start_connect"):
                s.start_connect(self)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            s = self.scene()
            if hasattr(s, "update_connect"):
                s.update_connect(event.scenePos())
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            self._dragging = False
            s = self.scene()
            if hasattr(s, "finish_connect"):
                s.finish_connect(event.scenePos())
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event):
        self.setRect(-HOVER_RADIUS, -HOVER_RADIUS, HOVER_RADIUS * 2, HOVER_RADIUS * 2)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setRect(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2)
        super().hoverLeaveEvent(event)
