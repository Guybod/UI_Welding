from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QAbstractItemView,
    QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox,
    QMenu, QInputDialog, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint
from PySide6.QtGui import QAction
from app.i18n import I18nManager, tr, tr_node
from app.widgets.node_editor.models import VarDef

CAT_I18N = {
    "基础": "cat_base", "运动": "cat_motion", "点位": "cat_position",
    "运算": "cat_math", "逻辑": "cat_logic", "字符串": "cat_string",
    "IO": "cat_io", "寄存器": "cat_register", "变量": "cat_variable",
    "常量": "cat_variable", "自定义": "cat_custom",
}

CATEGORIES = [
    ("基础", ["Start", "End", "Wait", "Print"]),
    ("变量", []),
    ("点位", []),
    ("运动", ["MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"]),
    ("运算", ["Add", "Sub", "Mul", "Div", "Square", "Sqrt", "Pow", "Mod", "Abs", "Neg", "Sin", "Cos", "Tan", "Deg2Rad", "Rad2Deg", "MatMulL", "MatMulR", "Int2Float", "Float2Int"]),
    ("逻辑", ["If", "For", "While", "And", "Or", "Not", "Xor", "Gt", "Lt", "Eq", "Ge", "Le"]),
    ("字符串", ["StrConcat", "StrSplit", "StrFind", "StrReplace", "StrLen", "Num2Str", "Bool2Str"]),
    ("IO", ["SetDO", "ReadDI", "SetAO", "ReadAI"]),
    ("寄存器", ["SetRegister", "ReadRegister"]),
    ("常量", ["Int", "Float", "Bool", "String", "Array"]),
]

MIME_POSITION = "application/x-position"

MIME_NODE_TYPE = "application/x-node-type"
MIME_VAR_GET = "application/x-var-get"
MIME_VAR_SET = "application/x-var-set"

VAR_TYPES = {"int": "number", "float": "number", "bool": "bool", "string": "string", "array": "any"}


class _DraggableTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setAnimated(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def mimeTypes(self):
        return [MIME_NODE_TYPE, MIME_VAR_GET, MIME_VAR_SET, MIME_POSITION]

    def mimeData(self, items):
        import json
        mime = QMimeData()
        for item in items:
            node_type = item.data(0, Qt.UserRole)
            if node_type == "__var__":
                var_name = item.data(0, Qt.UserRole + 1)
                var_type = item.data(0, Qt.UserRole + 2) or ""
                port_type = item.data(0, Qt.UserRole + 3) or "any"
                info = json.dumps({"name": var_name, "var_type": var_type, "port_type": port_type})
                mime.setData(MIME_VAR_GET, info.encode())
            elif node_type == "__pos__":
                pos_name = item.data(0, Qt.UserRole + 1) or ""
                mime.setData(MIME_POSITION, pos_name.encode())
            elif node_type:
                mime.setData(MIME_NODE_TYPE, node_type.encode())
            break
        return mime


class _VarDialog(QDialog):
    def __init__(self, parent=None, var: VarDef = None):
        super().__init__(parent)
        self.setWindowTitle(tr("var_edit") if var else tr("var_add"))
        layout = QFormLayout(self)
        self._name = QLineEdit(var.name if var else "")
        layout.addRow(tr("var_name"), self._name)
        self._type = QComboBox()
        self._type.addItems(["int", "float", "bool", "string", "array"])
        if var:
            self._type.setCurrentText(var.var_type)
        layout.addRow(tr("var_type"), self._type)
        self._init = QLineEdit(var.initial if var else "0")
        layout.addRow(tr("var_initial"), self._init)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def result(self) -> VarDef:
        return VarDef(name=self._name.text().strip(), var_type=self._type.currentText(), initial=self._init.text())


class NodeLibraryPanel(QWidget):
    node_requested = Signal(str)
    var_get_requested = Signal(str, str, str)   # var_name, var_type, port_type
    var_set_requested = Signal(str, str, str)
    variables_changed = Signal(list)
    position_requested = Signal(str)  # position name
    positions_changed = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeLibraryPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)
        self._variables: list[VarDef] = []
        self._positions: list[str] = []  # position names
        self._var_category: QTreeWidgetItem | None = None
        self._pos_category: QTreeWidgetItem | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(tr("node_library_title"))
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(self._title)

        self._tree = _DraggableTree()
        self._tree.setObjectName("nodeLibraryTree")
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        self._tree.itemClicked.connect(self._on_item_clicked)

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

        self._tree.expandAll()
        layout.addWidget(self._tree)
        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def set_variables(self, variables: list[VarDef]):
        self._variables = variables
        self._refresh_var_items()

    def variables(self) -> list[VarDef]:
        return self._variables

    def set_positions(self, positions: list[str]):
        self._positions = positions
        self._refresh_pos_items()

    def positions(self) -> list[str]:
        return self._positions

    def _refresh_pos_items(self):
        if not self._pos_category:
            return
        for i in range(self._pos_category.childCount() - 1, -1, -1):
            self._pos_category.removeChild(self._pos_category.child(i))
        for pname in self._positions:
            item = QTreeWidgetItem([pname])
            item.setData(0, Qt.UserRole, "__pos__")
            item.setData(0, Qt.UserRole + 1, pname)
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
            item.setData(0, Qt.UserRole, "__var__")
            item.setData(0, Qt.UserRole + 1, v.name)
            item.setData(0, Qt.UserRole + 2, v.var_type)
            item.setData(0, Qt.UserRole + 3, port_type)
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled)
            self._var_category.addChild(item)

    def _on_item_clicked(self, item, col):
        """Detect right-click area for Get/Set context menu on variables"""
        pass

    def _on_context_menu(self, pos: QPoint):
        item = self._tree.itemAt(pos)
        menu = QMenu(self)

        if item is self._var_category:
            act_add = QAction(tr("var_add"), menu)
            act_add.triggered.connect(self._on_add_variable)
            menu.addAction(act_add)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        if item is self._pos_category:
            act_add = QAction(tr("pos_add"), menu)
            act_add.triggered.connect(self._on_add_position)
            menu.addAction(act_add)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        if item:
            node_type = item.data(0, Qt.UserRole)
            name = item.data(0, Qt.UserRole + 1)
            if node_type == "__var__":
                act_get = QAction(tr("var_get"), menu)
                act_get.triggered.connect(lambda n=name: self._emit_var_get(n))
                menu.addAction(act_get)
                act_set = QAction(tr("var_set"), menu)
                act_set.triggered.connect(lambda n=name: self._emit_var_set(n))
                menu.addAction(act_set)
                menu.addSeparator()
                act_del = QAction(tr("var_delete"), menu)
                act_del.triggered.connect(lambda n=name: self._on_delete_variable(n))
                menu.addAction(act_del)
                menu.exec(self._tree.viewport().mapToGlobal(pos))
            elif node_type == "__pos__":
                act_del = QAction(tr("pos_delete"), menu)
                act_del.triggered.connect(lambda n=name: self._on_delete_position(n))
                menu.addAction(act_del)
                menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _emit_var_get(self, name):
        v = next((x for x in self._variables if x.name == name), None)
        if v:
            self.var_get_requested.emit(name, v.var_type, VAR_TYPES.get(v.var_type, "any"))

    def _emit_var_set(self, name):
        v = next((x for x in self._variables if x.name == name), None)
        if v:
            self.var_set_requested.emit(name, v.var_type, VAR_TYPES.get(v.var_type, "any"))

    def _on_add_variable(self):
        dlg = _VarDialog(self)
        if dlg.exec():
            v = dlg.result()
            if v.name:
                self._variables.append(v)
                self._refresh_var_items()
                self.variables_changed.emit(self._variables)

    def _on_delete_variable(self, name):
        self._variables = [v for v in self._variables if v.name != name]
        self._refresh_var_items()
        self.variables_changed.emit(self._variables)

    def _on_add_position(self):
        name, ok = QInputDialog.getText(self, tr("pos_add"), tr("pos_name"))
        if ok and name.strip():
            self._positions.append(name.strip())
            self._refresh_pos_items()
            self.positions_changed.emit(self._positions)

    def _on_delete_position(self, name):
        self._positions = [p for p in self._positions if p != name]
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
        node_type = item.data(0, Qt.UserRole)
        if node_type == "__var__":
            var_name = item.data(0, Qt.UserRole + 1)
            menu = QMenu(self)
            act_get = QAction(tr("var_get"), menu)
            act_get.triggered.connect(lambda n=var_name: self._emit_var_get(n))
            menu.addAction(act_get)
            act_set = QAction(tr("var_set"), menu)
            act_set.triggered.connect(lambda n=var_name: self._emit_var_set(n))
            menu.addAction(act_set)
            menu.exec(self._tree.viewport().mapToGlobal(
                self._tree.visualItemRect(item).center()
            ))
        elif node_type == "__pos__":
            name = item.data(0, Qt.UserRole + 1)
            self.position_requested.emit(name)
        elif node_type:
            self.node_requested.emit(node_type)
