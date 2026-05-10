from PySide6.QtWidgets import QGraphicsItem, QGraphicsSceneMouseEvent, QMenu
from PySide6.QtGui import QPen, QBrush, QColor, QPainter, QPolygonF, QAction
from PySide6.QtCore import Qt, QPointF, QRectF
from app.i18n import tr
from app.widgets.node_editor.models import PORT_COLORS

PORT_SIZE = 5.0
HOVER_SIZE = PORT_SIZE + 2


class PortItem(QGraphicsItem):
    """节点端口图元 — flow三角, data圆形, 支持拖拽连线和右键拆分/合并"""

    def __init__(self, port_name: str, port_type: str, direction: str, parent=None):
        super().__init__(parent)
        self._port_name = port_name
        self._port_type = port_type
        self._direction = direction
        self.connected_edges: list = []
        self._dragging = False
        self._color = QColor(PORT_COLORS.get(port_type, "#9E9E9E"))
        self._size = PORT_SIZE
        self._is_flow = (port_type == "flow")

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

    def boundingRect(self):
        s = self._size + 4
        return QRectF(-s, -s, s * 2, s * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        color = self._color
        painter.setPen(QPen(color.darker(150), 1))
        painter.setBrush(QBrush(color))
        if self._is_flow:
            tri = QPolygonF([
                QPointF(s, 0),
                QPointF(-s * 0.6, -s * 0.75),
                QPointF(-s * 0.6, s * 0.75),
            ])
            painter.drawPolygon(tri)
        else:
            painter.drawEllipse(QPointF(0, 0), s, s)

    def port_name(self) -> str:
        return self._port_name

    def port_type(self) -> str:
        return self._port_type

    def direction(self) -> str:
        return self._direction

    def scene_center(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))

    def add_edge(self, edge):
        if edge not in self.connected_edges:
            self.connected_edges.append(edge)

    def remove_edge(self, edge):
        if edge in self.connected_edges:
            self.connected_edges.remove(edge)

    def update_edges(self):
        for edge in self.connected_edges:
            edge.update_path()

    # ── mouse events ──

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.RightButton:
            # show split/merge for pose ports, or context menu
            if self._port_type == "pose":
                self._show_pose_menu(event.screenPos().toPoint())
                event.accept()
                return
        if event.button() == Qt.LeftButton:
            # allow dragging from any port (input or output)
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
        self._size = HOVER_SIZE
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._size = PORT_SIZE
        self.update()
        super().hoverLeaveEvent(event)

    def _show_pose_menu(self, screen_pos):
        """右键pose端口: 拆分/合并"""
        menu = QMenu()
        parent = self.parentItem()
        if not parent or not hasattr(parent, 'split_port'):
            menu.deleteLater()
            return
        name = self._port_name
        direction = self._direction
        is_split = any(
            p.port_name() in ("X","Y","Z","A","B","C","J1","J2","J3","J4","J5","J6")
            and p.direction() == direction
            for p in parent.ports()
        )
        if is_split:
            act = QAction(tr("port_merge"), menu)
            if name in ("cp", "jp"):
                subs = (["X","Y","Z","A","B","C"] if name == "cp"
                        else [f"J{i}" for i in range(1,7)])
            else:
                subs = [name]
            act.triggered.connect(lambda: parent.merge_port(name, subs, name, "pose"))
            menu.addAction(act)
        else:
            act = QAction(tr("port_split"), menu)
            if name == "cp":
                sub_ports = [("X","number",""),("Y","number",""),("Z","number",""),
                            ("A","number",""),("B","number",""),("C","number","")]
            elif name == "jp":
                sub_ports = [(f"J{i}","number","") for i in range(1,7)]
            else:
                sub_ports = []
            if sub_ports:
                act.triggered.connect(lambda: parent.split_port(name, sub_ports))
                menu.addAction(act)
        menu.exec(screen_pos)
