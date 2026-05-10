import uuid

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QKeyEvent
from PySide6.QtCore import QRectF, QPointF, Qt

from app.widgets.node_editor.node_item import NodeItem
from app.widgets.node_editor.port_item import PortItem
from app.widgets.node_editor.edge_item import EdgeItem
from app.widgets.node_editor.models import GraphData, NodeData, EdgeData


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

    def clear_all(self):
        for item in list(self.items()):
            if isinstance(item, EdgeItem):
                item.detach()
                self.removeItem(item)
        for item in list(self.items()):
            if isinstance(item, NodeItem):
                self.removeItem(item)

    # ── serialize / deserialize ──

    def to_graph_data(self) -> GraphData:
        """收集 Scene 中的所有节点和连线为纯数据模型"""
        nodes = []
        edges = []
        edge_id_counter = 0

        node_items: dict[str, NodeItem] = {}
        for item in self.items():
            if isinstance(item, NodeItem):
                nid = item.data(0) or str(uuid.uuid4())[:8]
                item.setData(0, nid)
                node_items[nid] = item
                nodes.append(NodeData(
                    node_id=nid,
                    node_type=item.node_type(),
                    title=item._title,
                    x=item.pos().x(),
                    y=item.pos().y(),
                    data=item.node_data(),
                ))

        seen = set()
        for item in self.items():
            if isinstance(item, EdgeItem):
                src = item.source()
                tgt = item.target()
                if not src or not tgt:
                    continue
                src_node = src.parentItem()
                tgt_node = tgt.parentItem()
                if not isinstance(src_node, NodeItem) or not isinstance(tgt_node, NodeItem):
                    continue
                key = (src_node.data(0), src.port_name(),
                       tgt_node.data(0), tgt.port_name())
                if key in seen:
                    continue
                seen.add(key)
                edge_id_counter += 1
                edges.append(EdgeData(
                    edge_id=f"e{edge_id_counter}",
                    source_node_id=src_node.data(0),
                    source_port_name=src.port_name(),
                    target_node_id=tgt_node.data(0),
                    target_port_name=tgt.port_name(),
                ))
        return GraphData(nodes=nodes, edges=edges)

    def load_from_graph_data(self, data: GraphData):
        """用 GraphData 重建所有节点和连线"""
        self.clear_all()
        node_map: dict[str, NodeItem] = {}
        for nd in data.nodes:
            node = self.add_node(nd.node_type, nd.x, nd.y)
            node.setData(0, nd.node_id)
            node.set_node_data(nd.data)
            if nd.title != nd.node_type:
                node._title = nd.title
            node_map[nd.node_id] = node

        for ed in data.edges:
            src_node = node_map.get(ed.source_node_id)
            tgt_node = node_map.get(ed.target_node_id)
            if not src_node or not tgt_node:
                continue
            src_port = self._find_port(src_node, ed.source_port_name, "output")
            tgt_port = self._find_port(tgt_node, ed.target_port_name, "input")
            if src_port and tgt_port:
                self._add_edge(src_port, tgt_port)

    def _find_port(self, node: NodeItem, name: str, direction: str) -> PortItem | None:
        for p in node.ports():
            if p.port_name() == name and p.direction() == direction:
                return p
        return None

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
