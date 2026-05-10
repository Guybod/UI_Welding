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
from app.widgets.node_editor.execution_engine import ExecutionEngine

DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent.parent / "projects"


class NodeEditorWidget(QWidget):
    """节点编辑器主组件 — 顶栏工程名 + 三栏 + 底部日志"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_path: str = ""
        self._scene = GraphScene(self)
        self._view = GraphView(self._scene, self)
        self._library = NodeLibraryPanel(self)
        self._view._library = self._library
        self._property = PropertyPanel(self)
        self._log = ExecutionLogPanel(self)

        self._library.node_requested.connect(self._on_add_node)
        self._library.var_get_requested.connect(self._on_var_get)
        self._library.var_set_requested.connect(self._on_var_set)
        self._library.variables_changed.connect(self._on_variables_changed)
        self._library.position_requested.connect(self._on_position_requested)
        self._library.positions_changed.connect(self._on_positions_changed)

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
        self._btn_run = QPushButton("▶ 运行")
        self._btn_run.clicked.connect(self._on_run)
        top.addWidget(self._btn_run)
        self._btn_stop = QPushButton("⏹ 停止")
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        top.addWidget(self._btn_stop)
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

        self._engine = ExecutionEngine(self)
        self._engine.log_emitted.connect(self._on_engine_log)
        self._engine.node_highlight.connect(self._on_node_highlight)
        self._engine.graph_started.connect(lambda: self._set_running(True))
        self._engine.graph_finished.connect(lambda: self._set_running(False))
        self._engine.graph_stopped.connect(lambda: self._set_running(False))

        self._view.add_variable_requested.connect(self._library._on_add_variable)
        self._view.add_position_requested.connect(self._library._on_add_position)
        self._view.var_get_requested.connect(self._on_var_get)
        self._view.var_set_requested.connect(self._on_var_set)
        self._view.position_requested.connect(self._on_position_requested)

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

    def _set_running(self, running: bool):
        self._btn_run.setVisible(not running)
        self._btn_run.setEnabled(not running)
        self._btn_stop.setVisible(running)

    def _on_stop(self):
        self._engine.stop()

    def _on_run(self):
        data = self._scene.to_graph_data()
        v = GraphValidator()
        r = v.validate(data)
        if not r.ok:
            log = self._log._log
            log.clear()
            log.appendPlainText(tr("node_valid_fail"))
            for err in r.errors:
                log.appendPlainText(f"  - {err}")
            return
        self._log._log.clear()
        self._engine.run_dry(data)

    def _on_engine_log(self, msg: str):
        self._log._log.appendPlainText(msg)

    def _on_node_highlight(self, node_id: str, on: bool):
        for item in self._scene.items():
            from app.widgets.node_editor.node_item import NodeItem
            if isinstance(item, NodeItem) and item.data(0) == node_id:
                item.set_highlight(on)

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

    def _on_var_get(self, name: str, var_type: str, port_type: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_var_node(name, var_type, port_type, "get", view_center.x(), view_center.y())
        # select the node so property panel shows its value
        self._scene.clearSelection()
        node.setSelected(True)

    def _on_var_set(self, name: str, var_type: str, port_type: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        self._scene.add_var_node(name, var_type, port_type, "set", view_center.x(), view_center.y())

    def _on_variables_changed(self, variables: list):
        pass

    def _on_position_requested(self, name: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_node("Position", view_center.x(), view_center.y())
        data = node.node_data()
        data["name"] = name
        node.set_node_data(data)

    def _on_positions_changed(self, positions: list):
        pass

    def _on_save(self):
        name = self._project_name.text().strip() or "未命名"
        path = os.path.join(self._projects_dir(), name)
        if not path.endswith(".json"):
            path += ".json"
        try:
            data = self._scene.to_graph_data()
            data.variables = self._library.variables()
            data.positions = self._library.positions()
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
            self._library.set_variables(data.variables)
            self._library.set_positions(data.positions)
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
