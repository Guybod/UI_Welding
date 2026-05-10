from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt
from app.widgets.node_editor.graph_scene import GraphScene
from app.widgets.node_editor.graph_view import GraphView
from app.widgets.node_editor.node_library_panel import NodeLibraryPanel
from app.widgets.node_editor.property_panel import PropertyPanel
from app.widgets.node_editor.execution_log_panel import ExecutionLogPanel


class NodeEditorWidget(QWidget):
    """节点编辑器主组件 — 三栏 + 底部日志布局"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._scene = GraphScene(self)
        self._view = GraphView(self._scene, self)
        self._library = NodeLibraryPanel(self)
        self._property = PropertyPanel(self)
        self._log = ExecutionLogPanel(self)

        self._library.node_requested.connect(self._on_add_node)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._library)
        splitter.addWidget(self._view)
        splitter.addWidget(self._property)
        splitter.setSizes([200, 600, 240])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        layout.addWidget(self._log)

    def _on_add_node(self, node_type: str):
        view_center = self._view.mapToScene(
            self._view.viewport().rect().center()
        )
        self._scene.add_node(node_type, view_center.x(), view_center.y())
