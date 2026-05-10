import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QFileDialog, QMessageBox,
    QLabel, QLineEdit, QPushButton,
)
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt, QSettings

from app.i18n import I18nManager, tr

from app.widgets.node_editor.graph_scene import GraphScene
from app.widgets.node_editor.graph_view import GraphView
from app.widgets.node_editor.graph_serializer import graph_to_json, json_to_graph
from app.widgets.node_editor.node_library_panel import NodeLibraryPanel
from app.widgets.node_editor.property_panel import PropertyPanel
from app.widgets.node_editor.execution_log_panel import ExecutionLogPanel
from app.widgets.node_editor.graph_validator import GraphValidator

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
        self._proj_label = QLabel(tr("node_project_label"))
        top.addWidget(self._proj_label)
        self._project_name = QLineEdit(tr("node_unnamed"))
        self._project_name.setFixedWidth(220)
        self._project_name.setStyleSheet("background: #3a3a3d; border: 1px solid #555; padding: 2px 6px;")
        top.addWidget(self._project_name)
        top.addStretch()
        self._btn_validate = QPushButton(tr("node_btn_validate"))
        self._btn_validate.clicked.connect(self._on_validate)
        top.addWidget(self._btn_validate)
        self._btn_save = QPushButton(tr("node_btn_save"))
        self._btn_save.clicked.connect(self._on_save)
        top.addWidget(self._btn_save)
        self._btn_load = QPushButton(tr("node_btn_load"))
        self._btn_load.clicked.connect(self._on_load)
        top.addWidget(self._btn_load)

        # ── three-column ──
        self._h_splitter = QSplitter(Qt.Horizontal)
        self._h_splitter.addWidget(self._library)
        self._h_splitter.addWidget(self._view)
        self._h_splitter.addWidget(self._property)
        self._h_splitter.setStretchFactor(0, 0)
        self._h_splitter.setStretchFactor(1, 1)
        self._h_splitter.setStretchFactor(2, 0)

        # ── vertical splitter: 画布区 + 日志 ──
        self._v_splitter = QSplitter(Qt.Vertical)
        self._v_splitter.addWidget(self._h_splitter)
        self._v_splitter.addWidget(self._log)
        self._v_splitter.setStretchFactor(0, 1)
        self._v_splitter.setStretchFactor(1, 0)

        self._settings = QSettings("Codroid", "RobotUI")
        h_sizes = self._settings.value("nodeEditor/hSplitter")
        v_sizes = self._settings.value("nodeEditor/vSplitter")
        if h_sizes:
            self._h_splitter.setSizes([int(x) for x in h_sizes])
        else:
            self._h_splitter.setSizes([200, 600, 240])
        if v_sizes:
            self._v_splitter.setSizes([int(x) for x in v_sizes])
        else:
            self._v_splitter.setSizes([500, 150])

        self._h_splitter.splitterMoved.connect(self._save_splitter_state)
        self._v_splitter.splitterMoved.connect(self._save_splitter_state)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(top)
        layout.addWidget(self._v_splitter)

        QShortcut(QKeySequence.Save, self, self._on_save)
        QShortcut(QKeySequence.Open, self, self._on_load)

        self._scene.selectionChanged.connect(self._on_selection_changed)
        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def _on_selection_changed(self):
        items = self._scene.selectedItems()
        from app.widgets.node_editor.node_item import NodeItem
        for item in items:
            if isinstance(item, NodeItem):
                self._property.set_node(item)
                return
        self._property.clear()

    def _projects_dir(self) -> str:
        d = str(DEFAULT_PROJECTS_DIR)
        os.makedirs(d, exist_ok=True)
        return d

    def _on_validate(self):
        data = self._scene.to_graph_data()
        v = GraphValidator()
        r = v.validate(data)
        log = self._log._log
        log.clear()
        if r.ok:
            log.appendPlainText(tr("node_valid_pass"))
        else:
            log.appendPlainText(f"{tr('node_valid_fail')} ({len(r.errors)})")
            for err in r.errors:
                log.appendPlainText(f"  - {err}")
        for w in r.warnings:
            log.appendPlainText(f"  ⚠ {w}")

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
            self._log._log.appendPlainText(f"{tr('node_saved')} {path}")
        except Exception as e:
            QMessageBox.critical(self, tr("node_save_failed"), str(e))

    def _on_load(self):
        proj_dir = self._projects_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, tr("node_load_graph"), proj_dir, "JSON Files (*.json)"
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
            self._log._log.appendPlainText(f"{tr('node_loaded')} {path}")
        except Exception as e:
            QMessageBox.critical(self, tr("node_load_failed"), str(e))

    def _on_language_changed(self, lang: str):
        self._proj_label.setText(tr("node_project_label"))
        if not self._current_path:
            self._project_name.setPlaceholderText(tr("node_unnamed"))
        self._btn_validate.setText(tr("node_btn_validate"))
        self._btn_save.setText(tr("node_btn_save"))
        self._btn_load.setText(tr("node_btn_load"))

    def _save_splitter_state(self):
        self._settings.setValue("nodeEditor/hSplitter", self._h_splitter.sizes())
        self._settings.setValue("nodeEditor/vSplitter", self._v_splitter.sizes())
