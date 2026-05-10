from PySide6.QtWidgets import QGraphicsItem, QStyle
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPainterPath
from PySide6.QtCore import Qt, QRectF

from app.widgets.node_editor.models import NodeSpec, NODE_SPECS
from app.widgets.node_editor.port_item import PortItem, PORT_RADIUS

TITLE_HEIGHT = 22
PORT_SPACING = 20
H_PADDING = 8
V_PADDING_BOTTOM = 6
NODE_WIDTH = 160
BODY_COLOR = QColor(45, 45, 48)
BORDER_COLOR = QColor(80, 80, 85)
BORDER_SELECTED = QColor(100, 140, 220)


class NodeItem(QGraphicsItem):
    """节点图元 — 圆角矩形 + 标题 + 端口"""

    def __init__(self, node_type: str, parent=None):
        super().__init__(parent)
        self._node_type = node_type
        spec = NODE_SPECS.get(node_type)
        self._spec = spec
        self._title = spec.title if spec else node_type
        self._color = QColor(spec.color if spec else "#616161")
        self._ports: list[PortItem] = []

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        if spec:
            self._build_ports(spec)

        self._calc_size()

    def _build_ports(self, spec: NodeSpec):
        left_ports = [p for p in spec.ports if p.direction == "input"]
        right_ports = [p for p in spec.ports if p.direction == "output"]

        for i, ps in enumerate(left_ports):
            y = TITLE_HEIGHT + PORT_SPACING * i + PORT_SPACING / 2
            port = PortItem(ps.name, ps.port_type, ps.direction, self)
            port.setPos(0, y)
            self._ports.append(port)

        for i, ps in enumerate(right_ports):
            y = TITLE_HEIGHT + PORT_SPACING * i + PORT_SPACING / 2
            port = PortItem(ps.name, ps.port_type, ps.direction, self)
            port.setPos(NODE_WIDTH, y)
            self._ports.append(port)

    def _calc_size(self):
        max_side = max(
            sum(1 for p in self._spec.ports if p.direction == "input") if self._spec else 1,
            sum(1 for p in self._spec.ports if p.direction == "output") if self._spec else 1,
            1,
        )
        body_h = PORT_SPACING * max_side + V_PADDING_BOTTOM
        self._body_height = TITLE_HEIGHT + max(body_h, 20)

    def node_type(self) -> str:
        return self._node_type

    def ports(self) -> list[PortItem]:
        return self._ports

    def input_ports(self) -> list[PortItem]:
        return [p for p in self._ports if p.direction() == "input"]

    def output_ports(self) -> list[PortItem]:
        return [p for p in self._ports if p.direction() == "output"]

    def boundingRect(self):
        return QRectF(0, 0, NODE_WIDTH, self._body_height)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect()

        # body
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.fillPath(path, BODY_COLOR)

        # title bar
        title_rect = QRectF(0, 0, NODE_WIDTH, TITLE_HEIGHT)
        title_path = QPainterPath()
        title_path.addRoundedRect(title_rect, 6, 6)
        # flatten bottom corners
        painter.fillPath(title_path, self._color)

        painter.setPen(QPen(QColor(255, 255, 255, 200)))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, NODE_WIDTH, TITLE_HEIGHT), Qt.AlignCenter, self._title)

        # border
        if option.state & QStyle.State_Selected:
            pen = QPen(BORDER_SELECTED, 2)
        else:
            pen = QPen(BORDER_COLOR, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 6, 6)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for port in self._ports:
                port.update_edges()
        return super().itemChange(change, value)
