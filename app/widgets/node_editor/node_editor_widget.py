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

    # 全局发送回调, 由 main.py 注入
    send_tcp = None  # callable(ty, db)

    @classmethod
    def set_global_send_callback(cls, cb):
        cls.send_tcp = cb

    def __init__(self, parent=None):
        super().__init__(parent)

        self._current_path: str = ""
        self._scene = GraphScene(self)
        self._view = GraphView(self._scene, self)
        self._library = NodeLibraryPanel(self)
        self._view._library = self._library
        self._scene._library = self._library
        self._property = PropertyPanel(self)
        self._log = ExecutionLogPanel(self)

        self._library.node_requested.connect(self._on_add_node)
        self._library.var_get_requested.connect(self._on_var_get)
        self._library.var_set_requested.connect(self._on_var_set)
        self._library.variables_changed.connect(self._on_variables_changed)
        self._library.position_requested.connect(self._on_position_requested)
        self._library.positions_changed.connect(self._on_positions_changed)
        self._library.macro_call_requested.connect(self._on_macro_call_requested)
        self._library.macros_changed.connect(self._on_macros_changed)
        self._view.save_macro_requested.connect(self._on_save_macro_selection)
        self._view.macro_edit_requested.connect(self._open_macro_editor)

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
        self._btn_run = QPushButton(tr("node_btn_run"))
        self._btn_run.clicked.connect(self._on_run)
        top.addWidget(self._btn_run)
        self._btn_online = QPushButton(tr("node_btn_online"))
        self._btn_online.clicked.connect(self._on_online_run)
        self._btn_online.setStyleSheet("QPushButton{color:#FF9800;font-weight:bold;}")
        top.addWidget(self._btn_online)
        self._btn_stop = QPushButton(tr("node_btn_stop"))
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_stop.hide()
        top.addWidget(self._btn_stop)
        self._btn_validate = QPushButton(tr("node_btn_compile"))
        self._btn_validate.clicked.connect(self._on_compile)
        top.addWidget(self._btn_validate)
        self._btn_save = QPushButton(tr("node_btn_save"))
        self._btn_save.clicked.connect(self._on_save)
        top.addWidget(self._btn_save)
        self._btn_load = QPushButton(tr("node_btn_load"))
        self._btn_load.clicked.connect(self._on_load)
        top.addWidget(self._btn_load)
        self._btn_tutorial = QPushButton(tr("node_btn_tutorial"))
        self._btn_tutorial.clicked.connect(self._on_tutorial)
        self._btn_tutorial.setStyleSheet("QPushButton{color:#81C784;}")
        top.addWidget(self._btn_tutorial)

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

        self._connection_check = None
        self._engine = ExecutionEngine(self)
        self._engine.set_macro_resolver(self._library.get_macro)
        if NodeEditorWidget.send_tcp:
            self._engine.set_send_callback(NodeEditorWidget.send_tcp)
        self._engine.log_emitted.connect(self._on_engine_log)
        self._engine.node_highlight.connect(self._on_node_highlight)
        self._engine.pin_value_emitted.connect(self._on_pin_value)
        self._engine.graph_started.connect(self._on_graph_run_start)
        self._engine.graph_finished.connect(self._on_graph_run_end)
        self._engine.graph_stopped.connect(self._on_graph_run_end)

        self._view.add_variable_requested.connect(self._library._on_add_variable)
        self._view.add_position_requested.connect(self._library._on_add_position)
        self._view.var_get_requested.connect(self._on_var_get)
        self._view.var_set_requested.connect(self._on_var_set)
        self._view.position_requested.connect(self._on_position_requested)

        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._property.variable_value_changed.connect(self._on_variable_value_changed)
        I18nManager.instance().language_changed.connect(self._on_language_changed)

        if not self._settings.value("nodeEditor/tutorialShown", False, type=bool):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(600, self._on_tutorial_first_run)

    def _on_tutorial_first_run(self) -> None:
        if self._settings.value("nodeEditor/tutorialShown", False, type=bool):
            return
        self._settings.setValue("nodeEditor/tutorialShown", True)
        self._on_tutorial()

    def _on_tutorial(self) -> None:
        from app.widgets.node_editor.node_editor_tutorial_dialog import show_node_editor_tutorial
        show_node_editor_tutorial(self)

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

    def set_send_callback(self, cb):
        self._engine.set_send_callback(cb)

    def set_connection_check(self, cb):
        """在线执行前检查是否已连接机器人。cb() -> bool"""
        self._connection_check = cb

    def stop_execution(self):
        """停止当前图执行（切页、断线、全局停止时调用）。"""
        if self._engine:
            self._engine.stop()

    def _set_running(self, running: bool):
        self._btn_run.setVisible(not running)
        self._btn_run.setEnabled(not running)
        self._btn_online.setVisible(not running)
        self._btn_online.setEnabled(not running)
        self._btn_stop.setVisible(running)

    def _on_stop(self):
        self._engine.stop()

    def _on_run(self):
        self._run_graph(online=False)

    def _on_online_run(self):
        self._run_graph(online=True)

    def _compile_graph(self):
        data = self._scene.to_graph_data()
        data.variables = list(self._library.variables())
        r = GraphValidator().validate(data)
        self._validate_macro_references(data, r)
        self._apply_validation_highlight(r)
        return r

    def _validate_macro_references(self, data, r) -> None:
        from app.widgets.node_editor.macro_validate import validate_macro_references_recursive

        known = {m.macro_id for m in self._library._macros}
        validate_macro_references_recursive(
            data,
            self._library.get_macro,
            known,
            r,
        )

    def _apply_validation_highlight(self, r) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        for item in self._scene.items():
            if isinstance(item, NodeItem):
                nid = item.data(0)
                item.set_validation_error(bool(nid and nid in r.error_node_ids))

    def _clear_all_pin_debug(self) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        for item in self._scene.items():
            if isinstance(item, NodeItem):
                item.clear_port_debug_values()

    def _on_graph_run_start(self) -> None:
        self._set_running(True)
        self._clear_all_pin_debug()

    def _on_graph_run_end(self) -> None:
        self._set_running(False)
        self._clear_all_pin_debug()

    def _on_pin_value(self, node_id: str, port_name: str, value: object) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        text = self._format_pin_value(value)
        for item in self._scene.items():
            if isinstance(item, NodeItem) and item.data(0) == node_id:
                item.set_port_debug_value(port_name, text)
                break

    @staticmethod
    def _format_pin_value(value: object) -> str:
        if isinstance(value, float):
            return f"{value:.4g}"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, dict):
            name = value.get("name")
            if name:
                return str(name)[:24]
            if "x" in value:
                try:
                    return (
                        f"({float(value['x']):.1f},"
                        f"{float(value.get('y', 0)):.1f},"
                        f"{float(value.get('z', 0)):.1f})"
                    )
                except (TypeError, ValueError, KeyError):
                    pass
            return "{…}"
        if isinstance(value, list):
            parts = []
            for x in value[:4]:
                try:
                    parts.append(f"{float(x):.3g}")
                except (TypeError, ValueError):
                    parts.append(str(x)[:6])
            s = "[" + ",".join(parts) + (",…" if len(value) > 4 else "") + "]"
            return s if len(s) <= 24 else s[:21] + "..."
        s = str(value)
        return s if len(s) <= 24 else s[:21] + "..."

    def _run_graph(self, online: bool):
        r = self._compile_graph()
        if not r.ok:
            self._log.clear()
            self._log.append_line(f"{tr('node_compile_fail')} ({len(r.errors)})")
            for err in r.errors:
                self._log.append_line(f"  - {err}")
            self._focus_error_node(r.error_node_ids)
            return
        self._log.clear()
        data = self._scene.to_graph_data()
        data.variables = list(self._library.variables())
        data.positions = list(self._library.positions())
        if online:
            if self._connection_check is not None and not self._connection_check():
                self._log.append_line(tr("node_not_connected"))
                return
            self._engine.run_online(data)
        else:
            self._engine.run_dry(data)

    def _on_engine_log(self, msg: str):
        self._log.append_line(msg)

    def _on_node_highlight(self, node_id: str, on: bool):
        for item in self._scene.items():
            from app.widgets.node_editor.node_item import NodeItem
            if isinstance(item, NodeItem) and item.data(0) == node_id:
                item.set_highlight(on)

    def _on_compile(self):
        r = self._compile_graph()
        self._log.clear()
        if r.ok:
            self._log.append_line(tr("node_compile_pass"))
        else:
            self._log.append_line(f"{tr('node_compile_fail')} ({len(r.errors)})")
            for err in r.errors:
                self._log.append_line(f"  - {err}")
            self._focus_error_node(r.error_node_ids)
        for w in r.warnings:
            self._log.append_line(f"  ⚠ {w}")

    def _on_macro_call_requested(self, macro_id: str, name: str) -> None:
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_macro_call(macro_id, name, view_center.x(), view_center.y())
        self._scene.clearSelection()
        node.setSelected(True)

    def _on_macros_changed(self, _macros: list) -> None:
        self._remove_macro_calls_not_in_library()
        self._refresh_macro_call_nodes()

    def _refresh_macro_call_nodes(self) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        for item in list(self._scene.items()):
            if isinstance(item, NodeItem) and item.node_type() == "MacroCall":
                mid = (item.node_data() or {}).get("macro_id", "")
                if mid:
                    self._scene.rebuild_macro_call(item, mid)

    def _open_macro_editor(self, macro_id: str) -> None:
        macro = self._library.get_macro(macro_id)
        if not macro:
            QMessageBox.warning(self, tr("macro_editor_title").format(name=macro_id), tr("macro_not_found").format(name=macro_id))
            return
        from app.widgets.node_editor.macro_editor_dialog import MacroEditorDialog

        dlg = MacroEditorDialog(macro, self._library, self)
        if dlg.exec() and dlg.was_saved():
            self._library.reload_macros()
            self._refresh_macro_call_nodes()

    def _remove_macro_calls_not_in_library(self) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        known = {m.macro_id for m in self._library._macros}
        for item in list(self._scene.items()):
            if not isinstance(item, NodeItem) or item.node_type() != "MacroCall":
                continue
            mid = (item.node_data() or {}).get("macro_id", "")
            if mid and mid not in known:
                self._scene.remove_node(item)

    def _on_save_macro_selection(self) -> None:
        import uuid
        from PySide6.QtWidgets import QInputDialog

        from app.widgets.node_editor.macro_extract import extract_subgraph, remap_graph_ids
        from app.widgets.node_editor.macro_ports import detect_boundary_params, remap_params
        from app.widgets.node_editor.macro_storage import MacroDef

        ids = self._scene.selected_node_ids()
        if not ids:
            QMessageBox.warning(self, tr("macro_save_title"), tr("macro_empty_selection"))
            return
        full = self._scene.to_graph_data()
        full.variables = list(self._library.variables())
        full.positions = list(self._library.positions())
        params = detect_boundary_params(full, ids)
        subgraph, err = extract_subgraph(ids, full)
        if err == "no_start":
            QMessageBox.warning(self, tr("macro_save_title"), tr("macro_no_start"))
            return
        if subgraph is None:
            QMessageBox.warning(self, tr("macro_save_title"), tr("macro_empty_selection"))
            return
        name, ok = QInputDialog.getText(self, tr("macro_save_title"), tr("macro_name_label"))
        if not ok or not name.strip():
            return
        subgraph, id_map = remap_graph_ids(subgraph)
        params = remap_params(params, id_map)
        macro = MacroDef(
            macro_id=str(uuid.uuid4())[:8],
            name=name.strip(),
            graph=subgraph,
            params=params,
        )
        inner = GraphValidator().validate(subgraph)
        if not inner.ok:
            QMessageBox.warning(
                self,
                tr("macro_save_title"),
                "\n".join(inner.errors[:8]),
            )
            return
        self._library.save_macro_def(macro)
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_macro_call(macro.macro_id, macro.name, view_center.x(), view_center.y())
        self._scene.clearSelection()
        node.setSelected(True)
        QMessageBox.information(self, tr("macro_save_title"), tr("macro_saved_placed").format(name=macro.name))

    def _on_add_node(self, node_type: str):
        view_center = self._view.mapToScene(
            self._view.viewport().rect().center()
        )
        self._scene.add_node(node_type, view_center.x(), view_center.y())

    def _on_var_get(self, var_id: str, name: str, var_type: str, port_type: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_var_node(var_id, name, var_type, port_type, "get", view_center.x(), view_center.y())
        self._scene.clearSelection()
        node.setSelected(True)

    def _on_var_set(self, var_id: str, name: str, var_type: str, port_type: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        self._scene.add_var_node(var_id, name, var_type, port_type, "set", view_center.x(), view_center.y())

    def _on_variables_changed(self, variables: list):
        self._remove_var_nodes_not_in_library()
        self._sync_scene_variables_from_library()

    def _remove_var_nodes_not_in_library(self) -> None:
        """变量从库中删除后，移除画布上绑定该 var_id 的 GetVar/SetVar 节点。"""
        from app.widgets.node_editor.node_item import NodeItem

        lib_ids = {v.var_id for v in self._library.variables() if v.var_id}
        lib_names = {v.name for v in self._library.variables() if v.name}
        for item in list(self._scene.items()):
            if not isinstance(item, NodeItem):
                continue
            if item.node_type() not in ("GetVar", "SetVar"):
                continue
            data = item.node_data() or {}
            vid = (data.get("var_id") or "").strip()
            vname = (data.get("var_name") or "").strip()
            orphan = False
            if vid:
                orphan = vid not in lib_ids
            elif vname:
                orphan = vname not in lib_names
            else:
                orphan = True
            if orphan:
                self._scene.remove_node(item)

    def _on_variable_value_changed(self, var_id: str, value) -> None:
        self._sync_variable_value(var_id, value)

    def _sync_variable_value(self, var_id: str, value) -> None:
        """同一 var_id 的库、所有 GetVar/SetVar 节点、属性面板保持同一值。"""
        from app.widgets.node_editor.node_item import NodeItem
        from app.widgets.node_editor.var_value import format_var_storage, parse_var_storage

        if not var_id:
            return

        var_type = "int"
        lib_var = None
        for v in self._library.variables():
            if v.var_id == var_id:
                lib_var = v
                var_type = v.var_type
                normalized = parse_var_storage(value, var_type)
                v.value = format_var_storage(normalized, var_type)
                value = normalized
                break

        for item in self._scene.items():
            if not isinstance(item, NodeItem):
                continue
            if item.node_type() not in ("GetVar", "SetVar"):
                continue
            data = dict(item.node_data())
            if data.get("var_id") != var_id:
                continue
            node_type = data.get("var_type", var_type)
            data["value"] = parse_var_storage(value, node_type)
            if lib_var:
                data["var_name"] = lib_var.name
                data["var_type"] = lib_var.var_type
            item.set_node_data(data)

        self._scene.refresh_display_titles()
        self._property.refresh_bound_variable_value(var_id, value)
        if self._engine._running and var_id:
            self._engine._refresh_getvar_watches(var_id, value)

    def _sync_scene_variables_from_library(self) -> None:
        """变量库变更后，刷新画布上所有变量节点缓存值与标题。"""
        from app.widgets.node_editor.node_item import NodeItem
        from app.widgets.node_editor.var_value import parse_var_storage

        lib_map = {v.var_id: v for v in self._library.variables()}
        for item in self._scene.items():
            if not isinstance(item, NodeItem):
                continue
            if item.node_type() not in ("GetVar", "SetVar"):
                continue
            data = dict(item.node_data())
            vid = data.get("var_id", "")
            if vid not in lib_map:
                continue
            var = lib_map[vid]
            data["var_name"] = var.name
            data["var_type"] = var.var_type
            data["value"] = parse_var_storage(var.value, var.var_type)
            item.set_node_data(data)

        self._scene.refresh_display_titles()

        items = self._scene.selectedItems()
        for item in items:
            if isinstance(item, NodeItem) and item.node_type() in ("GetVar", "SetVar"):
                self._property.set_node(item)
                break

    def _on_position_requested(self, pos_id: str, name: str):
        view_center = self._view.mapToScene(self._view.viewport().rect().center())
        node = self._scene.add_node("Position", view_center.x(), view_center.y())
        # lookup position data from library
        for p in self._library.positions():
            if p.pos_id == pos_id:
                data = {"pos_id": pos_id, "name": p.name, "jp": list(p.jp),
                        "cp": dict(p.cp), "ep": list(p.ep), "optional": dict(p.optional)}
                node.set_node_data({**data, "_auto_title": True})
                return
        # fallback
        node.set_node_data({"pos_id": pos_id, "name": name, "_auto_title": True})

    def _on_positions_changed(self, positions: list) -> None:
        from app.widgets.node_editor.node_item import NodeItem

        lib_map = {p.pos_id: p for p in positions if p.pos_id}
        for item in self._scene.items():
            if not isinstance(item, NodeItem) or item.node_type() != "Position":
                continue
            data = dict(item.node_data())
            pid = data.get("pos_id", "")
            if pid and pid in lib_map:
                data["name"] = lib_map[pid].name
                item.set_node_data(data)
        self._scene.refresh_display_titles()

    def _on_save(self):
        name = self._project_name.text().strip() or "未命名"
        path = os.path.join(self._projects_dir(), name)
        if not path.endswith(".json"):
            path += ".json"
        try:
            from app.widgets.node_editor.graph_serializer import reconcile_graph_variables

            data = self._scene.to_graph_data()
            data.variables = list(self._library.variables())
            data.positions = list(self._library.positions())
            reconcile_graph_variables(data)
            text = graph_to_json(data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self._current_path = path
            self._log.append_line(f"{tr('node_saved')} {path}")
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
            self._log.append_line(f"{tr('node_loaded')} {path}")
        except Exception as e:
            QMessageBox.critical(self, tr("node_load_failed"), str(e))

    def _on_language_changed(self, lang: str):
        self._proj_label.setText(tr("node_project_label"))
        if not self._current_path:
            self._project_name.setPlaceholderText(tr("node_unnamed"))
        self._btn_run.setText(tr("node_btn_run"))
        self._btn_online.setText(tr("node_btn_online"))
        self._btn_stop.setText(tr("node_btn_stop"))
        self._btn_validate.setText(tr("node_btn_compile"))
        self._btn_save.setText(tr("node_btn_save"))
        self._btn_load.setText(tr("node_btn_load"))
        self._btn_tutorial.setText(tr("node_btn_tutorial"))

    def _save_splitter_state(self):
        self._settings.setValue("nodeEditor/hSplitter", self._h_splitter.sizes())
        self._settings.setValue("nodeEditor/vSplitter", self._v_splitter.sizes())
