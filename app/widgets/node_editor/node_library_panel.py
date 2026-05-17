from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QMenu, QInputDialog, QMessageBox, QPlainTextEdit,
)
from functools import partial

from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QAction
from app.i18n import I18nManager, tr, tr_node
from pathlib import Path

from app.widgets.node_editor.models import VarDef, PositionDef, VAR_PORT_TYPE
from app.widgets.node_editor.macro_storage import (
    MacroDef,
    delete_macro,
    list_macros,
    save_macro,
    macros_dir,
)
from app.widgets.node_editor.node_catalog import LIBRARY_CATEGORIES, validate_library_catalog

CAT_I18N = {
    "基础": "cat_base", "运动": "cat_motion", "点位": "cat_position",
    "运算": "cat_math", "逻辑": "cat_logic", "字符串": "cat_string",
    "IO": "cat_io", "寄存器": "cat_register", "变量": "cat_variable",
    "常量": "cat_constant", "宏": "cat_macro", "自定义": "cat_custom",
}

CATEGORIES = LIBRARY_CATEGORIES

MIME_POSITION = "application/x-position"

MIME_NODE_TYPE = "application/x-node-type"
MIME_VAR_GET = "application/x-var-get"
MIME_VAR_SET = "application/x-var-set"
MIME_MACRO = "application/x-macro-call"

VAR_TYPES = {"int": "int", "float": "float", "bool": "bool", "string": "string", "array": "any"}

# 变量树节点数据角色（避免 UserRole+4 在部分环境下读不到 var_id）
_ROLE_VAR_KIND = Qt.ItemDataRole.UserRole
_ROLE_VAR_NAME = Qt.ItemDataRole.UserRole + 1
_ROLE_VAR_TYPE = Qt.ItemDataRole.UserRole + 2
_ROLE_VAR_PORT = Qt.ItemDataRole.UserRole + 3
_ROLE_VAR_ID = Qt.ItemDataRole.UserRole + 4


class _DraggableTree(QTreeWidget):
    def __init__(self, panel: "NodeLibraryPanel", parent=None):
        super().__init__(parent)
        self._panel = panel
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setAnimated(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setFocusPolicy(Qt.StrongFocus)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            item = self.currentItem()
            if item is not None:
                kind = item.data(0, _ROLE_VAR_KIND) or item.data(0, Qt.UserRole)
                if kind == "__var__":
                    name = item.data(0, _ROLE_VAR_NAME) or ""
                    var_id = item.data(0, _ROLE_VAR_ID) or ""
                    if name or var_id:
                        self._panel._on_delete_variable(name=name, var_id=var_id)
                        event.accept()
                        return
                if kind == "__pos__":
                    name = item.data(0, Qt.UserRole + 1) or ""
                    if name:
                        self._panel._on_delete_position(name)
                        event.accept()
                        return
        super().keyPressEvent(event)

    def mimeTypes(self):
        return [MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION, MIME_MACRO]

    def mimeData(self, items):
        import json
        mime = QMimeData()
        for item in items:
            node_type = item.data(0, _ROLE_VAR_KIND) or item.data(0, Qt.UserRole)
            if node_type == "__var__":
                var_name = item.data(0, _ROLE_VAR_NAME)
                var_type = item.data(0, _ROLE_VAR_TYPE) or ""
                port_type = item.data(0, _ROLE_VAR_PORT) or "any"
                var_id = item.data(0, _ROLE_VAR_ID) or ""
                info = json.dumps({"var_id": var_id, "name": var_name, "var_type": var_type, "port_type": port_type})
                mime.setData(MIME_VAR_GET, info.encode())
            elif node_type == "__pos__":
                pos_name = item.data(0, Qt.UserRole + 1) or ""
                mime.setData(MIME_POSITION, pos_name.encode())
            elif node_type == "__macro__":
                macro_id = item.data(0, _ROLE_VAR_ID) or ""
                macro_name = item.data(0, _ROLE_VAR_NAME) or ""
                info = json.dumps({"macro_id": macro_id, "name": macro_name})
                mime.setData(MIME_MACRO, info.encode())
            elif node_type:
                mime.setData(MIME_NODE_TYPE, node_type.encode())
            break
        return mime


class _VarDialog(QDialog):
    def __init__(self, parent=None, var: VarDef = None):
        super().__init__(parent)
        self._edit_var = var
        self.setWindowTitle(tr("var_edit") if var else tr("var_add"))
        self.setMinimumWidth(300)
        self.resize(320, 220)
        layout = QFormLayout(self)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self._name = QLineEdit(var.name if var else "")
        layout.addRow(tr("var_name"), self._name)
        self._type = QComboBox()
        self._type.addItems(["int", "float", "bool", "string", "array"])
        self._type.currentTextChanged.connect(self._on_type_changed)
        if var:
            self._type.setCurrentText(var.var_type)
        layout.addRow(tr("var_type"), self._type)
        self._init_line = QLineEdit()
        self._array_host = QWidget()
        array_layout = QVBoxLayout(self._array_host)
        array_layout.setContentsMargins(0, 0, 0, 0)
        from app.widgets.node_editor.array_list_editor import ArrayListEditor

        self._init_array = ArrayListEditor(compact=True)
        array_layout.addWidget(self._init_array)
        layout.addRow(tr("var_initial"), self._init_line)
        layout.addRow("", self._array_host)
        self._array_host.hide()
        init_val = var.value if var else "0"
        if var and var.var_type == "array":
            self._init_array.set_value(init_val)
        else:
            self._init_line.setText(init_val)
        self._on_type_changed(self._type.currentText())
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def _on_type_changed(self, t: str):
        is_array = (t == "array")
        self._init_line.setVisible(not is_array)
        self._array_host.setVisible(is_array)
        if is_array:
            self.resize(320, max(self.height(), 340))
        else:
            self.resize(320, 220)

    def result(self) -> VarDef:
        from app.widgets.node_editor.var_value import format_var_storage

        t = self._type.currentText()
        if t == "array":
            val = format_var_storage(self._init_array.get_value(), "array")
        else:
            val = self._init_line.text().strip()
        out = VarDef(name=self._name.text().strip(), var_type=t, value=val)
        if self._edit_var and self._edit_var.var_id:
            out.var_id = self._edit_var.var_id
        return out


class NodeLibraryPanel(QWidget):
    node_requested = Signal(str)
    var_get_requested = Signal(str, str, str, str)   # var_id, var_name, var_type, port_type
    var_set_requested = Signal(str, str, str, str)
    variables_changed = Signal(list)
    position_requested = Signal(str, str)  # pos_id, name
    positions_changed = Signal(list)
    macro_call_requested = Signal(str, str)  # macro_id, name
    macros_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeLibraryPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)
        self._variables: list[VarDef] = []
        self._positions: list[PositionDef] = []
        self._var_category: QTreeWidgetItem | None = None
        self._pos_category: QTreeWidgetItem | None = None
        self._macro_category: QTreeWidgetItem | None = None
        self._macros: list[MacroDef] = []
        self._projects_root = Path(__file__).resolve().parents[3] / "projects"

        from app.widgets.node_editor.plugins.registry import discover_plugins, sync_custom_catalog

        discover_plugins()
        sync_custom_catalog(CATEGORIES)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(tr("node_library_title"))
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(self._title)

        self._tree = _DraggableTree(self)
        self._tree.setObjectName("nodeLibraryTree")
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        self._cat_items: list[QTreeWidgetItem] = []
        self._node_items: dict[str, QTreeWidgetItem] = {}
        for cat_name, items in CATEGORIES:
            i18n_key = CAT_I18N.get(cat_name, cat_name)
            cat_item = QTreeWidgetItem([tr(i18n_key)])
            cat_item.setData(0, Qt.UserRole, i18n_key)
            cat_item.setData(0, Qt.UserRole + 1, cat_name)  # store original category name
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            for node_name in items:
                display = tr_node(node_name)
                node_item = QTreeWidgetItem([display])
                node_item.setData(0, Qt.UserRole, node_name)
                node_item.setFlags(node_item.flags() | Qt.ItemIsDragEnabled)
                cat_item.addChild(node_item)
                self._node_items[node_name] = node_item
            self._tree.addTopLevelItem(cat_item)
            self._cat_items.append(cat_item)
            if cat_name == "变量":
                self._var_category = cat_item
            elif cat_name == "点位":
                self._pos_category = cat_item
            elif cat_name == "宏":
                self._macro_category = cat_item

        self._custom_category = None
        for cat_name, _items in CATEGORIES:
            if cat_name == "自定义":
                for i in range(self._tree.topLevelItemCount()):
                    top = self._tree.topLevelItem(i)
                    if top.data(0, Qt.UserRole + 1) == cat_name:
                        self._custom_category = top
                        break
                break

        self._tree.collapseAll()
        layout.addWidget(self._tree)
        self.reload_macros()
        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def set_variables(self, variables: list[VarDef]):
        self._variables = list(variables)
        self._refresh_var_items()

    def variables(self) -> list[VarDef]:
        return self._variables

    def set_positions(self, positions: list[PositionDef]):
        self._positions = positions
        self._refresh_pos_items()

    def positions(self) -> list[PositionDef]:
        return self._positions

    def reload_macros(self) -> None:
        self._macros = list_macros(self._projects_root)
        self._refresh_macro_items()
        self.macros_changed.emit(self._macros)

    def get_macro(self, macro_id: str) -> MacroDef | None:
        for m in self._macros:
            if m.macro_id == macro_id:
                return m
        return None

    def save_macro_def(self, macro: MacroDef) -> None:
        save_macro(macro, self._projects_root)
        self.reload_macros()

    def _refresh_macro_items(self) -> None:
        if not self._macro_category:
            return
        while self._macro_category.childCount():
            self._macro_category.removeChild(self._macro_category.child(0))
        for m in self._macros:
            item = QTreeWidgetItem([m.name])
            item.setData(0, _ROLE_VAR_KIND, "__macro__")
            item.setData(0, _ROLE_VAR_NAME, m.name)
            item.setData(0, _ROLE_VAR_ID, m.macro_id)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self._macro_category.addChild(item)

    def _refresh_pos_items(self):
        if not self._pos_category:
            return
        for i in range(self._pos_category.childCount() - 1, -1, -1):
            self._pos_category.removeChild(self._pos_category.child(i))
        for p in self._positions:
            item = QTreeWidgetItem([p.name])
            item.setData(0, Qt.UserRole, "__pos__")
            item.setData(0, Qt.UserRole + 1, p.name)
            item.setData(0, Qt.UserRole + 2, p.pos_id)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self._pos_category.addChild(item)

    def _refresh_var_items(self):
        if not self._var_category:
            return
        # remove old variable children
        for i in range(self._var_category.childCount() - 1, -1, -1):
            child = self._var_category.child(i)
            self._var_category.removeChild(child)
        for v in self._variables:
            port_type = VAR_TYPES.get(v.var_type, "any")
            item = QTreeWidgetItem([f"{v.name} ({v.var_type})"])
            item.setData(0, _ROLE_VAR_KIND, "__var__")
            item.setData(0, _ROLE_VAR_NAME, v.name)
            item.setData(0, _ROLE_VAR_TYPE, v.var_type)
            item.setData(0, _ROLE_VAR_PORT, port_type)
            item.setData(0, _ROLE_VAR_ID, v.var_id or "")
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self._var_category.addChild(item)

    def _item_at_menu_pos(self, pos: QPoint) -> QTreeWidgetItem | None:
        idx = self._tree.indexAt(pos)
        item = self._tree.itemFromIndex(idx) if idx.isValid() else None
        if item is not None:
            return item
        return self._tree.currentItem()

    def _var_item_name(self, item: QTreeWidgetItem) -> str:
        return (item.data(0, _ROLE_VAR_NAME) or item.data(0, Qt.UserRole + 1) or "").strip()

    def _var_item_id(self, item: QTreeWidgetItem) -> str:
        return (item.data(0, _ROLE_VAR_ID) or item.data(0, Qt.UserRole + 4) or "").strip()

    def _append_var_item_menu(self, menu: QMenu, item: QTreeWidgetItem) -> None:
        name = self._var_item_name(item)
        var_id = self._var_item_id(item)
        act_get = QAction(tr("var_get"), menu)
        act_get.triggered.connect(partial(self._emit_var_get, name))
        menu.addAction(act_get)
        act_set = QAction(tr("var_set"), menu)
        act_set.triggered.connect(partial(self._emit_var_set, name))
        menu.addAction(act_set)
        menu.addSeparator()
        act_del = QAction(tr("var_delete"), menu)
        act_del.setProperty("var_name", name)
        act_del.setProperty("var_id", var_id)
        act_del.triggered.connect(self._on_delete_var_action)
        menu.addAction(act_del)

    def _on_delete_var_action(self) -> None:
        act = self.sender()
        if not isinstance(act, QAction):
            return
        self._on_delete_variable(
            name=(act.property("var_name") or ""),
            var_id=(act.property("var_id") or ""),
        )

    def _on_context_menu(self, pos: QPoint):
        item = self._item_at_menu_pos(pos)
        menu = QMenu(self)
        global_pos = self._tree.viewport().mapToGlobal(pos)

        if item is self._var_category:
            act_add = QAction(tr("var_add"), menu)
            act_add.triggered.connect(self._on_add_variable)
            menu.addAction(act_add)
            cur = self._tree.currentItem()
            if cur and cur.data(0, _ROLE_VAR_KIND) == "__var__":
                menu.addSeparator()
                self._append_var_item_menu(menu, cur)
            if menu.actions():
                menu.exec(global_pos)
            return

        if item is self._pos_category:
            act_add = QAction(tr("pos_add"), menu)
            act_add.triggered.connect(self._on_add_position)
            menu.addAction(act_add)
            menu.exec(global_pos)
            return

        if item is self._macro_category:
            cur = self._tree.currentItem()
            if cur and cur.data(0, _ROLE_VAR_KIND) == "__macro__":
                macro_id = self._var_item_id(cur)
                act_del = QAction(tr("macro_delete"), menu)
                act_del.triggered.connect(lambda mid=macro_id: self._on_delete_macro(mid))
                menu.addAction(act_del)
            if menu.actions():
                menu.exec(global_pos)
            return

        if item is None:
            return

        node_type = item.data(0, _ROLE_VAR_KIND) or item.data(0, Qt.UserRole)
        if node_type == "__var__":
            self._tree.setCurrentItem(item)
            self._append_var_item_menu(menu, item)
            menu.exec(global_pos)
        elif node_type == "__pos__":
            name = item.data(0, Qt.UserRole + 1) or ""
            act_del = QAction(tr("pos_delete"), menu)
            act_del.triggered.connect(lambda n=name: self._on_delete_position(n))
            menu.addAction(act_del)
            menu.exec(global_pos)
        elif node_type == "__macro__":
            macro_id = self._var_item_id(item)
            macro_name = self._var_item_name(item)
            act_del = QAction(tr("macro_delete"), menu)
            act_del.triggered.connect(lambda mid=macro_id: self._on_delete_macro(mid))
            menu.addAction(act_del)
            menu.exec(global_pos)

    def _on_delete_macro(self, macro_id: str) -> None:
        if not macro_id:
            return
        if delete_macro(macro_id, self._projects_root):
            self.reload_macros()

    def _emit_var_get(self, name):
        v = next((x for x in self._variables if x.name == name), None)
        if v:
            port_type = VAR_PORT_TYPE.get(v.var_type, "any")
            self.var_get_requested.emit(v.var_id, name, v.var_type, port_type)

    def _emit_var_set(self, name):
        v = next((x for x in self._variables if x.name == name), None)
        if v:
            port_type = VAR_PORT_TYPE.get(v.var_type, "any")
            self.var_set_requested.emit(v.var_id, name, v.var_type, port_type)

    def _on_add_variable(self):
        dlg = _VarDialog(self)
        if dlg.exec():
            v = dlg.result()
            if v.name:
                # 禁止同名变量
                existing = self._variables
                if any(x.name == v.name for x in existing):
                    QMessageBox.warning(self, tr("var_edit"), f"变量名 '{v.name}' 已存在")
                    return
                self._variables.append(v)
                self._refresh_var_items()
                self.variables_changed.emit(self._variables)

    def _on_delete_variable(self, var_id: str = "", name: str = ""):
        name = (name or "").strip()
        var_id = (var_id or "").strip()
        before = len(self._variables)
        if name:
            self._variables = [v for v in self._variables if v.name != name]
        elif var_id:
            self._variables = [v for v in self._variables if v.var_id != var_id]
        else:
            return
        if len(self._variables) == before:
            QMessageBox.warning(self, tr("var_delete"), tr("var_delete_failed"))
            return
        self._refresh_var_items()
        self.variables_changed.emit(list(self._variables))

    def _on_add_position(self):
        name, ok = QInputDialog.getText(self, tr("pos_add"), tr("pos_name"))
        if ok and name.strip():
            if any(p.name == name.strip() for p in self._positions):
                QMessageBox.warning(self, tr("pos_add"), f"点位名 '{name.strip()}' 已存在")
                return
            p = PositionDef(name=name.strip())
            self._positions.append(p)
            self._refresh_pos_items()
            self.positions_changed.emit(self._positions)

    def _on_delete_position(self, name):
        self._positions = [p for p in self._positions if p.name != name]
        self._refresh_pos_items()
        self.positions_changed.emit(self._positions)

    def _on_language_changed(self, lang: str):
        self._title.setText(tr("node_library_title"))
        for cat_item in self._cat_items:
            i18n_key = cat_item.data(0, Qt.UserRole)
            if i18n_key:
                cat_item.setText(0, tr(i18n_key))
        for node_name, item in self._node_items.items():
            item.setText(0, tr_node(node_name))

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, _ROLE_VAR_KIND) or item.data(0, Qt.UserRole)
        if node_type == "__var__":
            menu = QMenu(self)
            self._append_var_item_menu(menu, item)
            menu.exec(self._tree.viewport().mapToGlobal(
                self._tree.visualItemRect(item).center()
            ))
        elif node_type == "__pos__":
            pos_id = item.data(0, Qt.UserRole + 2) or ""
            name = item.data(0, Qt.UserRole + 1) or ""
            self.position_requested.emit(pos_id, name)
        elif node_type == "__macro__":
            self.macro_call_requested.emit(
                self._var_item_id(item),
                self._var_item_name(item),
            )
        elif node_type:
            self.node_requested.emit(node_type)
