import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox,
    QLabel, QLineEdit, QPushButton,
)
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt

from app.widgets.node_editor.graph_scene import GraphScene
from app.widgets.node_editor.graph_view import GraphView
from app.widgets.node_editor.graph_serializer import graph_to_json, json_to_graph
from app.widgets.node_editor.node_library_panel import NodeLibraryPanel
from app.widgets.node_editor.property_panel import PropertyPanel
from app.widgets.node_editor.execution_log_panel import ExecutionLogPanel

DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent.parent / "projects"


class NodeEditorWidget(QWidget):
    """节点编辑器主组件 — 顶栏工程名 + 三栏 + 底部日志"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_path: str = ""
        self._scene = GraphScene(self)
        self._view = GraphView(self._scene, self)
        self._library = NodeLibraryPanel(self)
        self._property = PropertyPanel(self)
        self._log = ExecutionLogPanel(self)

        self._library.node_requested.connect(self._on_add_node)

        # ── top bar ──
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 6)
        top.addWidget(QLabel("工程:"))
        self._project_name = QLineEdit("未命名")
        self._project_name.setFixedWidth(220)
        self._project_name.setStyleSheet("background: #3a3a3d; border: 1px solid #555; padding: 2px 6px;")
        top.addWidget(self._project_name)
        top.addStretch()
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._on_save)
        top.addWidget(btn_save)
        btn_load = QPushButton("加载")
        btn_load.clicked.connect(self._on_load)
        top.addWidget(btn_load)

        # ── three-column ──
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
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(splitter)
        layout.addWidget(self._log)

        QShortcut(QKeySequence.Save, self, self._on_save)
        QShortcut(QKeySequence.Open, self, self._on_load)

    def _projects_dir(self) -> str:
        d = str(DEFAULT_PROJECTS_DIR)
        os.makedirs(d, exist_ok=True)
        return d

    def _on_add_node(self, node_type: str):
        view_center = self._view.mapToScene(
            self._view.viewport().rect().center()
        )
        self._scene.add_node(node_type, view_center.x(), view_center.y())

    def _on_save(self):
        name = self._project_name.text().strip() or "未命名"
        path = os.path.join(self._projects_dir(), name)
        if not path.endswith(".json"):
            path += ".json"
        try:
            data = self._scene.to_graph_data()
            text = graph_to_json(data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self._current_path = path
            self._log._log.appendPlainText(f"已保存: {path}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _on_load(self):
        proj_dir = self._projects_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "加载节点图", proj_dir, "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            data = json_to_graph(text)
            self._scene.load_from_graph_data(data)
            self._current_path = path
            name = os.path.splitext(os.path.basename(path))[0]
            self._project_name.setText(name)
            self._log._log.appendPlainText(f"已加载: {path}")
        except Exception as e:
            QMessageBox.critical(self, "加载失败", str(e))
