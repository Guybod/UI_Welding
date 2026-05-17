from PySide6.QtWidgets import QGraphicsView, QMenu, QApplication
from PySide6.QtGui import QPainter, QWheelEvent, QMouseEvent, QAction
from PySide6.QtCore import Qt, QPoint, Signal

from app.i18n import tr, tr_node


class GraphView(QGraphicsView):
    """节点编辑器视图 — 滚轮缩放 + 中键平移 + 右键菜单 + 接受拖放"""

    add_variable_requested = Signal()
    add_position_requested = Signal()
    var_get_requested = Signal(str, str, str, str)
    var_set_requested = Signal(str, str, str, str)
    position_requested = Signal(str, str)

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
        self._library = None  # set by NodeEditorWidget

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
            menu.addSeparator()
        # node library menu (shown both on empty and on node right-click)
        from app.widgets.node_editor.node_library_panel import CATEGORIES, CAT_I18N
        for cat_name, items in CATEGORIES:
            i18n_key = CAT_I18N.get(cat_name, cat_name)
            sub = menu.addMenu(tr(i18n_key))
            # dynamic categories: 变量 and 点位
            if cat_name == "变量" and self._library:
                act_add = QAction(tr("var_add"), sub)
                act_add.triggered.connect(self.add_variable_requested.emit)
                sub.addAction(act_add)
                if self._library.variables():
                    sub.addSeparator()
                for v in self._library.variables():
                    var_menu = sub.addMenu(f"{v.name} ({v.var_type})")
                    port_type = {"int":"number","float":"number","bool":"bool","string":"string","array":"any"}.get(v.var_type,"any")
                    act_get = QAction(tr("var_get"), var_menu)
                    act_get.triggered.connect(lambda *a, vid=v.var_id, n=v.name, t=v.var_type, p=port_type: self.var_get_requested.emit(vid, n, t, p))
                    var_menu.addAction(act_get)
                    act_set = QAction(tr("var_set"), var_menu)
                    act_set.triggered.connect(lambda *a, vid=v.var_id, n=v.name, t=v.var_type, p=port_type: self.var_set_requested.emit(vid, n, t, p))
                    var_menu.addAction(act_set)
                continue
            if cat_name == "点位" and self._library:
                act_add = QAction(tr("pos_add"), sub)
                act_add.triggered.connect(self.add_position_requested.emit)
                sub.addAction(act_add)
                if self._library.positions():
                    sub.addSeparator()
                for pos in self._library.positions():
                    act = QAction(pos.name, sub)
                    act.triggered.connect(lambda *a, pid=pos.pos_id, n=pos.name: self.position_requested.emit(pid, n))
                    sub.addAction(act)
                continue
            for node_name in items:
                act = QAction(tr_node(node_name), sub)
                act.triggered.connect(self._make_add_handler(node_name, scene_pos))
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
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION
        if any(event.mimeData().hasFormat(f) for f in [MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION]):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION
        if any(event.mimeData().hasFormat(f) for f in [MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION]):
            event.acceptProposedAction()

    def dropEvent(self, event):
        from app.widgets.node_editor.node_library_panel import MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION as MP
        scene_pos = self.mapToScene(event.position().toPoint())
        s = self.scene()
        md = event.mimeData()

        # variable drop → show Get/Set menu
        var_info = None
        if md.hasFormat(MIME_VAR_GET):
            var_info = md.data(MIME_VAR_GET).data().decode()
        elif md.hasFormat(MIME_VAR_SET):
            var_info = md.data(MIME_VAR_SET).data().decode()

        if var_info and hasattr(s, "add_var_node"):
            import json
            info = json.loads(var_info)
            menu = QMenu(self)
            act_get = QAction(tr("var_get"), menu)
            act_get.triggered.connect(lambda: s.add_var_node(info.get("var_id",""), info["name"], info["var_type"], info["port_type"], "get", scene_pos.x(), scene_pos.y()))
            menu.addAction(act_get)
            act_set = QAction(tr("var_set"), menu)
            act_set.triggered.connect(lambda: s.add_var_node(info.get("var_id",""), info["name"], info["var_type"], info["port_type"], "set", scene_pos.x(), scene_pos.y()))
            menu.addAction(act_set)
            menu.exec(self.mapToGlobal(event.position().toPoint()))
            event.acceptProposedAction()
            return

        # position drop
        if md.hasFormat(MP):
            pos_name = md.data(MP).data().decode()
            if hasattr(s, "add_node") and s._library:
                for p in s._library.positions():
                    if p.name == pos_name:
                        node = s.add_node("Position", scene_pos.x(), scene_pos.y())
                        data = {"pos_id": p.pos_id, "name": p.name, "jp": list(p.jp),
                                "cp": dict(p.cp), "ep": list(p.ep), "optional": dict(p.optional)}
                        node.set_node_data(data)
                        node._title = p.name
                        node.update()
                        break
            event.acceptProposedAction()
            return

        # regular node drop — add then try insert onto flow edge
        if md.hasFormat(MIME_NODE_TYPE):
            node_type = md.data(MIME_NODE_TYPE).data().decode()
            if hasattr(s, "add_node"):
                node = s.add_node(node_type, scene_pos.x(), scene_pos.y())
                if hasattr(s, "try_insert_node_on_flow_edge"):
                    s.try_insert_node_on_flow_edge(node, scene_pos)
            event.acceptProposedAction()
