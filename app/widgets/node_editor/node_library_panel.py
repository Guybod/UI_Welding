from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem
from PySide6.QtCore import Qt, Signal

CATEGORIES = [
    ("基础", ["Start", "End"]),
    ("运动", ["MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"]),
    ("点位", ["Position"]),
    ("IO", ["SetDO", "ReadDI", "SetAO", "ReadAI"]),
    ("寄存器", ["SetRegister", "ReadRegister"]),
    ("逻辑", ["If", "For", "While", "Compare", "And", "Or", "Not"]),
    ("变量", ["Int", "Float", "Bool", "String", "Array"]),
    ("自定义", []),
]


class NodeLibraryPanel(QWidget):
    """节点库面板 — 双击节点类型添加到画布"""

    node_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("nodeLibraryPanel")
        self.setMinimumWidth(180)
        self.setMaximumWidth(280)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("节点库")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(title)

        self._tree = QTreeWidget()
        self._tree.setObjectName("nodeLibraryTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(12)
        self._tree.setAnimated(True)
        self._tree.itemDoubleClicked.connect(self._on_double_click)

        for cat_name, items in CATEGORIES:
            cat_item = QTreeWidgetItem([cat_name])
            cat_item.setFlags(cat_item.flags() & ~Qt.ItemIsSelectable)
            font = cat_item.font(0)
            font.setBold(True)
            cat_item.setFont(0, font)
            for node_name in items:
                node_item = QTreeWidgetItem([node_name])
                node_item.setData(0, Qt.UserRole, node_name)
                cat_item.addChild(node_item)
            self._tree.addTopLevelItem(cat_item)

        self._tree.expandAll()
        layout.addWidget(self._tree)

    def _on_double_click(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, Qt.UserRole)
        if node_type:
            self.node_requested.emit(node_type)
