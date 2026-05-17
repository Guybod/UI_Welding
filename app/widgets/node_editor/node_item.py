from PySide6.QtWidgets import QGraphicsItem, QStyle, QGraphicsSimpleTextItem, QInputDialog
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QPainter, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF

from app.widgets.node_editor.models import NodeSpec, NODE_SPECS
from app.widgets.node_editor.port_item import PortItem, PORT_SIZE

TITLE_HEIGHT = 22
PORT_SPACING = 20
H_PADDING = 8
V_PADDING_BOTTOM = 6
NODE_WIDTH = 160
_DRAG_INSERT_THRESHOLD = 4.0
BODY_COLOR = QColor(45, 45, 48)
BORDER_COLOR = QColor(80, 80, 85)
BORDER_SELECTED = QColor(100, 140, 220)


class NodeItem(QGraphicsItem):
    """节点图元 — 圆角矩形 + 标题 + 端口"""

    def __init__(self, node_type: str, parent=None, override_spec=None):
        super().__init__(parent)
        self._node_type = node_type
        spec = override_spec or NODE_SPECS.get(node_type)
        self._spec = spec
        self._title = spec.title if spec else node_type
        self._color = QColor(spec.color if spec else "#616161")
        self._ports: list[PortItem] = []
        self._data: dict = {}
        self._highlighted: bool = False
        self._validation_error: bool = False
        self._disabled: bool = False
        self._port_debug_labels: dict[str, QGraphicsSimpleTextItem] = {}
        self._left_press_scene_pos: QPointF | None = None

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

        label_font = QFont()
        label_font.setPointSize(7)

        for i, ps in enumerate(left_ports):
            y = TITLE_HEIGHT + PORT_SPACING * i + PORT_SPACING / 2
            port = PortItem(ps.name, ps.port_type, ps.direction, self)
            port.setPos(0, y)
            self._ports.append(port)
            lbl = QGraphicsSimpleTextItem(ps.name, self)
            lbl.setFont(label_font)
            lbl.setBrush(QColor(180, 180, 180))
            lbl.setPos(10, y - 7)

        for i, ps in enumerate(right_ports):
            y = TITLE_HEIGHT + PORT_SPACING * i + PORT_SPACING / 2
            port = PortItem(ps.name, ps.port_type, ps.direction, self)
            port.setPos(NODE_WIDTH, y)
            self._ports.append(port)
            lbl = QGraphicsSimpleTextItem(ps.name, self)
            lbl.setFont(label_font)
            lbl.setBrush(QColor(180, 180, 180))
            lbl.setPos(NODE_WIDTH - lbl.boundingRect().width() - 10, y - 7)

    def _calc_size(self):
        if self._node_type == "Comment":
            lines = max(1, (self._data.get("text") or "").count("\n") + 1)
            self._body_height = TITLE_HEIGHT + min(120, 14 * lines + 16)
            return
        left_count = sum(1 for p in self._ports if p.direction() == "input")
        right_count = sum(1 for p in self._ports if p.direction() == "output")
        max_side = max(left_count, right_count, 1)
        body_h = PORT_SPACING * max_side + V_PADDING_BOTTOM
        self._body_height = TITLE_HEIGHT + max(body_h, 20)

    def node_type(self) -> str:
        return self._node_type

    def node_data(self) -> dict:
        return self._data

    def set_node_data(self, data: dict):
        self._data = data
        self._disabled = bool(data.get("disabled"))
        scene = self.scene()
        if scene is not None and hasattr(scene, "refresh_display_titles"):
            scene.refresh_display_titles({self})

    def refresh_display_title(self, pose_links: dict[str, str] | None = None) -> None:
        from app.widgets.node_editor.node_display_title import (
            compute_node_display_title,
            should_auto_title,
        )

        if not should_auto_title(self._node_type, self._data):
            return
        title = compute_node_display_title(self._node_type, self._data, pose_links=pose_links)
        if title and title != self._title:
            self._title = title
            self.update()

    def set_highlight(self, on: bool):
        """执行引擎高亮 — 绿色边框 + 浅色填充"""
        self._highlighted = on
        self.update()

    def set_validation_error(self, on: bool) -> None:
        self._validation_error = on
        self.update()

    def clear_port_debug_values(self) -> None:
        for lbl in self._port_debug_labels.values():
            lbl.setParentItem(None)
            if lbl.scene():
                lbl.scene().removeItem(lbl)
        self._port_debug_labels.clear()

    def set_port_debug_value(self, port_name: str, text: str | None) -> None:
        port = next((p for p in self._ports if p.port_name() == port_name), None)
        if port is None:
            return
        lbl = self._port_debug_labels.get(port_name)
        if not text:
            if lbl is not None:
                lbl.setParentItem(None)
                if lbl.scene():
                    lbl.scene().removeItem(lbl)
                del self._port_debug_labels[port_name]
            return
        if lbl is None:
            lbl = QGraphicsSimpleTextItem(self)
            font = QFont()
            font.setPointSize(6)
            lbl.setFont(font)
            lbl.setBrush(QColor(255, 220, 120))
            self._port_debug_labels[port_name] = lbl
        lbl.setText(str(text)[:24])
        if port.direction() == "output":
            lbl.setPos(NODE_WIDTH + 4, port.pos().y() - 6)
        else:
            lbl.setPos(-lbl.boundingRect().width() - 4, port.pos().y() - 6)

    def split_port(self, port_name: str, sub_ports: list[tuple[str, str, str]]):
        """展开某端口为多个子端口 (name, port_type, direction)"""
        target = None
        for p in self._ports:
            if p.port_name() == port_name:
                target = p
                break
        if target is None:
            return
        direction = target.direction()
        for edge in list(target.connected_edges):
            s = self.scene()
            if s and hasattr(s, '_remove_edge'):
                s._remove_edge(edge)
        self.scene().removeItem(target)
        self._ports.remove(target)
        for name, ptype, _ in sub_ports:
            port = PortItem(name, ptype, direction, self)
            self._ports.append(port)
        self._reposition_ports(direction)
        self._calc_size()
        self.update()

    def merge_port(self, port_name: str, sub_names: list[str], new_name: str, new_type: str):
        """合并多个子端口为一个端口"""
        direction = None
        for p in self._ports:
            if p.port_name() in sub_names:
                direction = p.direction()
                break
        if direction is None:
            return
        for p in list(self._ports):
            if p.port_name() in sub_names:
                for edge in list(p.connected_edges):
                    s = self.scene()
                    if s and hasattr(s, '_remove_edge'):
                        s._remove_edge(edge)
                self.scene().removeItem(p)
                self._ports.remove(p)
        port = PortItem(new_name, new_type, direction, self)
        self._ports.append(port)
        self._reposition_ports(direction)
        self._calc_size()
        self.update()

    def _reposition_ports(self, direction: str):
        """重排某侧(左/右)的所有端口位置"""
        side_ports = [p for p in self._ports if p.direction() == direction]
        x = 0 if direction == "input" else NODE_WIDTH
        for i, port in enumerate(side_ports):
            y = TITLE_HEIGHT + PORT_SPACING * i + PORT_SPACING / 2
            port.setPos(x, y)

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
        body_fill = QColor(70, 70, 75) if self._disabled else BODY_COLOR
        painter.fillPath(path, body_fill)

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

        if self._node_type == "Comment":
            painter.setPen(QPen(QColor(200, 200, 200)))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            text = (self._data.get("text") or "").strip() or "…"
            painter.drawText(
                QRectF(6, TITLE_HEIGHT + 4, NODE_WIDTH - 12, self._body_height - TITLE_HEIGHT - 8),
                Qt.AlignLeft | Qt.TextWordWrap,
                text,
            )

        # border
        if self._highlighted:
            pen = QPen(QColor("#4CAF50"), 3)
        elif self._validation_error:
            pen = QPen(QColor("#F44336"), 2)
        elif option.state & QStyle.State_Selected:
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._left_press_scene_pos = event.scenePos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton or self._left_press_scene_pos is None:
            return
        moved = (event.scenePos() - self._left_press_scene_pos).manhattanLength()
        self._left_press_scene_pos = None
        if moved < _DRAG_INSERT_THRESHOLD:
            return
        scene = self.scene()
        if scene is not None and hasattr(scene, "try_insert_node_on_flow_edge"):
            scene.try_insert_node_on_flow_edge(self, event.scenePos())

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() <= TITLE_HEIGHT:
            self._rename_node()
        event.accept()

    def _rename_node(self):
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit,
                                       QPushButton, QHBoxLayout, QGraphicsView)
        from PySide6.QtCore import Qt

        view = None
        s = self.scene()
        if s:
            for v in s.views():
                if isinstance(v, QGraphicsView):
                    view = v
                    break

        class _RenameDialog(QDialog):
            def showEvent(self, event):
                super().showEvent(event)
                if view:
                    top = view.window()  # 软件主窗口
                    if top:
                        gc = top.mapToGlobal(top.rect().center())
                        fg = self.frameGeometry()
                        fg.moveCenter(gc)
                        self.move(fg.topLeft())

        dlg = _RenameDialog(view)
        dlg.setWindowTitle("重命名节点")
        dlg.setFixedSize(280, 120)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #2b2b2e;
                color: #e0e0e0;
            }
            QLabel {
                color: #cccccc;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #3a3a3d;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #3a3a3d;
                color: #e0e0e0;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 6px 18px;
                min-width: 70px;
            }
            QPushButton:hover {
                background-color: #4a4a4d;
            }
        """)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("名称:"))
        edit = QLineEdit(self._title)
        edit.selectAll()
        layout.addWidget(edit)

        btns = QHBoxLayout()
        ok = QPushButton("确定")
        cancel = QPushButton("取消")
        btns.addStretch()
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)

        if dlg.exec():
            name = edit.text().strip()
            if name:
                self._title = name
                self.update()
