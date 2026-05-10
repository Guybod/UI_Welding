from PySide6.QtWidgets import QGraphicsView, QMenu, QApplication
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent, QAction
from PySide6.QtCore import Qt, QPoint

from app.i18n import tr, tr_node


class GraphView(QGraphicsView):
    """节点编辑器视图 — 滚轮缩放 + 中键平移 + 右键菜单 + 接受拖放"""

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
        self.setAcceptDrops(True)
        self._right_press_pos = QPoint()

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
        if event.button() == Qt.RightButton:
            self._right_press_pos = event.pos()
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
        if event.button() == Qt.RightButton:
            delta = event.pos() - self._right_press_pos
            if delta.manhattanLength() < 4:
                self._show_context_menu(event.pos())
        if event.button() in (Qt.MiddleButton, Qt.RightButton):
            self.setDragMode(QGraphicsView.NoDrag)
            fake = QMouseEvent(
                event.type(), event.pos(), Qt.LeftButton,
                Qt.LeftButton, event.modifiers()
            )
            super().mouseReleaseEvent(fake)
        else:
            super().mouseReleaseEvent(event)

    def _show_context_menu(self, view_pos: QPoint):
        scene_pos = self.mapToScene(view_pos)
        s = self.scene()
        menu = QMenu(self)

        # check if right-clicked on a node
        from app.widgets.node_editor.node_item import NodeItem
        item_at = s.itemAt(scene_pos, self.transform())
        # walk up to find the NodeItem parent
        clicked_node = None
        while item_at is not None:
            if isinstance(item_at, NodeItem):
                clicked_node = item_at
                break
            item_at = item_at.parentItem()

        if clicked_node is not None:
            act_del = QAction(tr("node_delete"), menu)
            act_del.triggered.connect(lambda: s.remove_node(clicked_node))
            menu.addAction(act_del)
            act_rename = QAction(tr("node_rename_title"), menu)
            act_rename.triggered.connect(lambda: self._rename_node(clicked_node))
            menu.addAction(act_rename)
        else:
            # add node submenus by category
            cats = [
                ("cat_base", ["Start", "End", "Print"]),
                ("cat_motion", ["MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"]),
                ("cat_position", ["Position"]),
                ("cat_math", ["Add", "Sub", "Mul", "Div", "Square", "Sqrt", "Pow", "Mod",
                              "Abs", "Neg", "Sin", "Cos", "Tan", "Deg2Rad", "Rad2Deg",
                              "MatMulL", "MatMulR", "Int2Float", "Float2Int"]),
                ("cat_logic", ["If", "For", "While", "And", "Or", "Not", "Xor",
                               "Gt", "Lt", "Eq", "Ge", "Le"]),
                ("cat_string", ["StrConcat", "StrSplit", "StrFind", "StrReplace", "StrLen",
                                "Num2Str", "Bool2Str"]),
                ("cat_io", ["SetDO", "ReadDI", "SetAO", "ReadAI"]),
                ("cat_register", ["SetRegister", "ReadRegister"]),
                ("cat_variable", ["Int", "Float", "Bool", "String", "Array"]),
            ]
            for cat_key, node_types in cats:
                sub = menu.addMenu(tr(cat_key))
                for nt in node_types:
                    act = QAction(tr_node(nt), sub)
                    act.triggered.connect(self._make_add_handler(nt, scene_pos))
                    sub.addAction(act)

        menu.exec(self.mapToGlobal(view_pos))

    def _make_add_handler(self, node_type: str, pos):
        def handler():
            s = self.scene()
            if hasattr(s, "add_node"):
                s.add_node(node_type, pos.x(), pos.y())
        return handler

    def _rename_node(self, node):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, tr("node_rename_title"), tr("node_rename_label"), text=node._title)
        if ok and name.strip():
            node._title = name.strip()
            node.update()

    def dragEnterEvent(self, event):
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE
        if event.mimeData().hasFormat(MIME_NODE_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE
        if event.mimeData().hasFormat(MIME_NODE_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE
        data = event.mimeData().data(MIME_NODE_TYPE)
        if data:
            node_type = data.data().decode()
            scene_pos = self.mapToScene(event.position().toPoint())
            s = self.scene()
            if hasattr(s, "add_node"):
                s.add_node(node_type, scene_pos.x(), scene_pos.y())
            event.acceptProposedAction()
