from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QKeyEvent
from PySide6.QtCore import QRectF, QPointF, Qt

from app.widgets.node_editor.node_item import NodeItem
from app.widgets.node_editor.port_item import PortItem
from app.widgets.node_editor.edge_item import EdgeItem


class GraphScene(QGraphicsScene):
    """节点编辑器场景 — 深色背景 + 网格 + 连线管理"""

    BG_COLOR = QColor(30, 30, 32)
    GRID_COLOR = QColor(50, 50, 55, 120)
    GRID_SIZE = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(self.BG_COLOR))
        self.setSceneRect(QRectF(-5000, -5000, 10000, 10000))
        self._temp_edge: EdgeItem | None = None
        self._drag_source: PortItem | None = None

    # ── node management ──

    def add_node(self, node_type: str, x: float = 0, y: float = 0) -> NodeItem:
        node = NodeItem(node_type)
        node.setPos(x, y)
        self.addItem(node)
        return node

    def remove_node(self, node: NodeItem):
        for port in node.ports():
            for edge in list(port.connected_edges):
                self._remove_edge(edge)
        self.removeItem(node)

    # ── edge management ──

    def _add_edge(self, src: PortItem, tgt: PortItem):
        # validate: output → input, compatible types
        if src.direction() != "output" or tgt.direction() != "input":
            return
        if src.port_type() != tgt.port_type() and src.port_type() != "any" and tgt.port_type() != "any":
            return

        edge = EdgeItem(src, tgt)
        src.add_edge(edge)
        tgt.add_edge(edge)
        self.addItem(edge)
        edge.update_path()

    def _remove_edge(self, edge: EdgeItem):
        edge.detach()
        self.removeItem(edge)

    # ── drag-to-connect ──

    def start_connect(self, port: PortItem):
        self._drag_source = port
        self._temp_edge = EdgeItem(port, None)
        self.addItem(self._temp_edge)

    def update_connect(self, pos: QPointF):
        if self._temp_edge:
            self._temp_edge.set_temp_end(pos)

    def finish_connect(self, pos: QPointF):
        if not self._temp_edge:
            return
        self.removeItem(self._temp_edge)
        temp = self._temp_edge
        self._temp_edge = None
        src = self._drag_source
        self._drag_source = None

        target = self._port_at(pos)
        if target and target is not src:
            self._add_edge(src, target)

    def _port_at(self, pos: QPointF, radius: float = 16.0) -> PortItem | None:
        """在 pos 周围 radius 范围内查找最近端口"""
        best = None
        best_dist = radius
        # check top-level port items
        for item in self.items():
            if isinstance(item, PortItem):
                d = (item.scene_center() - pos).manhattanLength()
                if d < best_dist:
                    best = item
                    best_dist = d
        # check ports on nodes (children of NodeItem)
        for item in self.items():
            if isinstance(item, NodeItem):
                for port in item.ports():
                    d = (port.scene_center() - pos).manhattanLength()
                    if d < best_dist:
                        best = port
                        best_dist = d
        return best

    # ── draw ──

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self.selectedItems()):
                if isinstance(item, NodeItem):
                    self.remove_node(item)
        super().keyPressEvent(event)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(self.GRID_COLOR, 1)
        painter.setPen(pen)

        gs = self.GRID_SIZE
        left = int(rect.left()) - (int(rect.left()) % gs)
        top = int(rect.top()) - (int(rect.top()) % gs)

        x = left
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += gs
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += gs
