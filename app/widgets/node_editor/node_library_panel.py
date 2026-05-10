from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal, QMimeData
from app.i18n import I18nManager, tr, tr_node

CAT_I18N = {
    "基础": "cat_base", "运动": "cat_motion", "点位": "cat_position",
    "运算": "cat_math", "逻辑": "cat_logic", "字符串": "cat_string",
    "IO": "cat_io", "寄存器": "cat_register", "变量": "cat_variable",
    "自定义": "cat_custom",
}

CATEGORIES = [
    ("基础", ["Start", "End", "Print"]),
    ("运动", ["MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"]),
    ("点位", ["Position"]),
    ("运算", ["Add", "Sub", "Mul", "Div", "Square", "Sqrt", "Pow", "Mod", "Abs", "Neg", "Sin", "Cos", "Tan", "Deg2Rad", "Rad2Deg", "MatMulL", "MatMulR", "Int2Float", "Float2Int"]),
    ("逻辑", ["If", "For", "While", "And", "Or", "Not", "Xor", "Gt", "Lt", "Eq", "Ge", "Le"]),
    ("字符串", ["StrConcat", "StrSplit", "StrFind", "StrReplace", "StrLen", "Num2Str", "Bool2Str"]),
    ("IO", ["SetDO", "ReadDI", "SetAO", "ReadAI"]),
    ("寄存器", ["SetRegister", "ReadRegister"]),
    ("变量", ["Int", "Float", "Bool", "String", "Array"]),
    ("自定义", []),
]

MIME_NODE_TYPE = "application/x-node-type"


class _DraggableTree(QTreeWidget):
    """支持拖拽节点类型到画布的树控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(12)
        self.setAnimated(True)
        self.setDragEnabled(True)

    def mimeTypes(self):
        return [MIME_NODE_TYPE]

    def mimeData(self, items):
        mime = QMimeData()
        for item in items:
            node_type = item.data(0, Qt.UserRole)
            if node_type:
                mime.setData(MIME_NODE_TYPE, node_type.encode())
                break
        return mime


class NodeLibraryPanel(QWidget):
    """节点库面板 — 双击或拖拽节点到画布"""

    node_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeLibraryPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(tr("node_library_title"))
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(self._title)

        self._tree = _DraggableTree()
        self._tree.setObjectName("nodeLibraryTree")
        self._tree.itemDoubleClicked.connect(self._on_double_click)

        self._cat_items: list[QTreeWidgetItem] = []
        self._node_items: dict[str, QTreeWidgetItem] = {}
        for cat_name, items in CATEGORIES:
            i18n_key = CAT_I18N.get(cat_name, cat_name)
            cat_item = QTreeWidgetItem([tr(i18n_key)])
            cat_item.setData(0, Qt.UserRole, i18n_key)
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

        self._tree.expandAll()
        layout.addWidget(self._tree)
        I18nManager.instance().language_changed.connect(self._on_language_changed)

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
        if node_type:
            self.node_requested.emit(node_type)
