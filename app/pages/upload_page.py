"""上传功能页 — Lua 工程上传、列表、重名处理、槽位绑定。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QSettings, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.base_page import BasePage
from app.i18n import tr
from services.robot_project_sdk import RobotProjectSDK, RobotProjectSDKError

_SETTINGS_PREFIX = "upload/"
_OUTPUT_DIR = Path("output")


class _AsyncWorker(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object]):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:
            self.failed.emit(str(e))


class UploadPage(BasePage):
    """焊接 Lua 上传、槽位绑定。"""

    MODE_UPLOAD_ONLY = "upload_only"
    MODE_UPLOAD_BIND = "upload_bind"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Codroid", "RobotUI")
        self._thread: Optional[QThread] = None
        self._worker: Optional[_AsyncWorker] = None
        self._async_on_ok: Optional[Callable[[object], None]] = None
        self._async_refresh_after = False
        self._projects: List[dict] = []
        self._project_map: List[str] = []
        self._busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 8, 8, 8)  # 左侧预留给运动抽屉（与焊接页一致）
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        # ── 上传区 ──
        upload_group = QGroupBox(tr("upload_section_upload"))
        upload_form = QFormLayout(upload_group)

        lua_row = QWidget()
        lua_row_layout = QHBoxLayout(lua_row)
        lua_row_layout.setContentsMargins(0, 0, 0, 0)
        self._edit_lua = QLineEdit()
        self._edit_lua.setPlaceholderText(tr("upload_lua_placeholder"))
        lua_row_layout.addWidget(self._edit_lua, 1)
        btn_browse = QPushButton(tr("upload_browse"))
        btn_browse.clicked.connect(self._on_browse_lua)
        lua_row_layout.addWidget(btn_browse)
        btn_latest = QPushButton(tr("upload_pick_latest"))
        btn_latest.clicked.connect(self._on_pick_latest_lua)
        lua_row_layout.addWidget(btn_latest)
        upload_form.addRow(tr("upload_lua_file"), lua_row)

        self._edit_project_name = QLineEdit()
        self._edit_project_name.setPlaceholderText(tr("upload_project_name_ph"))
        upload_form.addRow(tr("upload_project_name"), self._edit_project_name)

        self._combo_upload_mode = QComboBox()
        self._combo_upload_mode.addItem(tr("upload_mode_only"), self.MODE_UPLOAD_ONLY)
        self._combo_upload_mode.addItem(tr("upload_mode_bind"), self.MODE_UPLOAD_BIND)
        self._combo_upload_mode.currentIndexChanged.connect(self._on_upload_mode_changed)
        upload_form.addRow(tr("upload_mode"), self._combo_upload_mode)

        self._spin_upload_slot = QSpinBox()
        self._spin_upload_slot.setRange(0, 127)
        self._spin_upload_slot.setValue(0)
        self._spin_upload_slot.setEnabled(False)
        upload_form.addRow(tr("upload_slot"), self._spin_upload_slot)

        self._btn_upload = QPushButton(tr("upload_btn"))
        self._btn_upload.setMinimumHeight(36)
        self._btn_upload.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2e86c1; }"
            "QPushButton:disabled { background-color: #95a5a6; }"
        )
        self._btn_upload.clicked.connect(self._on_upload)
        upload_form.addRow("", self._btn_upload)

        content_layout.addWidget(upload_group)

        # ── 槽位绑定 ──
        bind_group = QGroupBox(tr("upload_section_bind"))
        bind_layout = QVBoxLayout(bind_group)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self._btn_refresh = QPushButton(tr("upload_refresh"))
        self._btn_refresh.clicked.connect(self._on_refresh_projects)
        refresh_row.addWidget(self._btn_refresh)
        bind_layout.addLayout(refresh_row)

        bind_form = QFormLayout()
        self._spin_bind_slot = QSpinBox()
        self._spin_bind_slot.setRange(0, 127)
        self._spin_bind_slot.setValue(0)
        bind_form.addRow(tr("upload_slot"), self._spin_bind_slot)

        self._combo_bind_project = QComboBox()
        self._combo_bind_project.setMinimumWidth(280)
        self._combo_bind_project.currentIndexChanged.connect(self._on_bind_project_changed)
        bind_form.addRow(tr("upload_bind_project"), self._combo_bind_project)

        self._lbl_project_slots = QLabel(tr("upload_project_not_bound"))
        self._lbl_project_slots.setWordWrap(True)
        self._lbl_project_slots.setStyleSheet("color: #555555;")
        bind_form.addRow(tr("upload_current_binding"), self._lbl_project_slots)

        self._btn_bind = QPushButton(tr("upload_bind_btn"))
        self._btn_bind.clicked.connect(self._on_bind_slot)
        bind_form.addRow("", self._btn_bind)

        bind_layout.addLayout(bind_form)

        overview_group = QGroupBox(tr("upload_bind_overview_title"))
        overview_layout = QVBoxLayout(overview_group)
        self._binding_overview = QPlainTextEdit()
        self._binding_overview.setReadOnly(True)
        self._binding_overview.setMaximumBlockCount(256)
        self._binding_overview.setMinimumHeight(120)
        self._binding_overview.setPlaceholderText(tr("upload_bind_overview_empty"))
        overview_layout.addWidget(self._binding_overview)
        bind_layout.addWidget(overview_group)

        content_layout.addWidget(bind_group)
        content_layout.addStretch()
        scroll.setWidget(content)

        # ── 右侧日志 ──
        right_panel = QWidget()
        right_panel.setObjectName("uploadRightPanel")
        right_panel.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        log_group = QGroupBox(tr("upload_log_title"))
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #80c080; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; }"
        )
        log_layout.addWidget(self._log)
        right_layout.addWidget(log_group, stretch=1)

        horiz = QHBoxLayout()
        horiz.setSpacing(8)
        horiz.addWidget(scroll, stretch=3)
        horiz.addWidget(right_panel, stretch=1)
        root.addLayout(horiz)

        self._restore_settings()
        self._on_upload_mode_changed()
        self._update_controls_enabled()

    def on_enter(self):
        if self.sp and self.sp.cm.is_connected:
            self._on_refresh_projects()

    def on_connection_changed(self, connected: bool):
        self._update_controls_enabled()
        if connected:
            self._on_refresh_projects()

    def _robot_ip(self) -> str:
        return str(self._settings.value("login/robot_ip", "192.168.1.136")).strip()

    def _sdk(self) -> RobotProjectSDK:
        return RobotProjectSDK.from_robot_ip(self._robot_ip(), debug=False)

    def _log_line(self, msg: str):
        self._log.appendPlainText(msg)

    def _is_connected(self) -> bool:
        return bool(self.sp and self.sp.cm.is_connected)

    def _update_controls_enabled(self):
        ok = self._is_connected() and not self._busy
        for w in (
            self._btn_upload,
            self._btn_refresh,
            self._btn_bind,
            self._edit_lua,
            self._edit_project_name,
            self._combo_upload_mode,
            self._spin_upload_slot,
            self._spin_bind_slot,
            self._combo_bind_project,
        ):
            w.setEnabled(ok)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._update_controls_enabled()

    def _on_async_done(self, result: object):
        """主线程槽：处理后台任务成功（须连到 UploadPage，不能连局部函数）。"""
        try:
            if self._async_on_ok:
                self._async_on_ok(result)
        finally:
            if self._thread and self._thread.isRunning():
                self._thread.quit()

    def _on_async_failed(self, err: str):
        """主线程槽：处理后台任务失败。"""
        self._log_line(tr("upload_err").format(err=err))
        if self._thread and self._thread.isRunning():
            self._thread.quit()

    def _on_async_thread_finished(self):
        """主线程槽：线程退出后清理并可选刷新列表。"""
        refresh = self._async_refresh_after
        self._thread = None
        self._worker = None
        self._async_on_ok = None
        self._async_refresh_after = False
        self._set_busy(False)
        if refresh:
            self._on_refresh_projects()

    def _run_async(
        self,
        fn: Callable[[], object],
        on_ok: Callable[[object], None],
        *,
        refresh_after: bool = False,
    ):
        if self._thread and self._thread.isRunning():
            self._log_line(tr("upload_busy"))
            return

        self._set_busy(True)
        self._async_on_ok = on_ok
        self._async_refresh_after = refresh_after

        thread = QThread(self)
        worker = _AsyncWorker(fn)
        worker.moveToThread(thread)

        # QueuedConnection 的槽在「接收方」线程执行，必须接到 UploadPage（主线程）
        worker.done.connect(self._on_async_done, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._on_async_failed, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(
            self._on_async_thread_finished, Qt.ConnectionType.QueuedConnection
        )

        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_upload_mode_changed(self):
        bind = self._combo_upload_mode.currentData() == self.MODE_UPLOAD_BIND
        self._spin_upload_slot.setEnabled(bind and self._is_connected() and not self._busy)

    def _name_by_id(self) -> dict[str, str]:
        return {p["id"]: p["name"] for p in self._projects}

    def _slots_for_project(self, project_id: str) -> List[int]:
        if not project_id:
            return []
        return [
            idx
            for idx, pid in enumerate(self._project_map)
            if pid and str(pid) == str(project_id)
        ]

    def _on_bind_project_changed(self):
        project_id = self._combo_bind_project.currentData()
        slots = self._slots_for_project(project_id or "")
        if not project_id:
            self._lbl_project_slots.setText(tr("upload_select_project_hint"))
        elif slots:
            slots_text = ", ".join(str(s) for s in slots)
            self._lbl_project_slots.setText(
                tr("upload_project_slots").format(slots=slots_text)
            )
        else:
            self._lbl_project_slots.setText(tr("upload_project_not_bound"))

    def _rebuild_bind_project_combo(self):
        current_id = self._combo_bind_project.currentData()
        self._combo_bind_project.blockSignals(True)
        self._combo_bind_project.clear()
        self._combo_bind_project.addItem(tr("upload_select_project"), "")
        for item in self._projects:
            self._combo_bind_project.addItem(item["name"], item["id"])
        if current_id:
            idx = self._combo_bind_project.findData(current_id)
            if idx >= 0:
                self._combo_bind_project.setCurrentIndex(idx)
        self._combo_bind_project.blockSignals(False)
        self._on_bind_project_changed()

    def _rebuild_binding_overview(self):
        name_by_id = self._name_by_id()
        lines: List[str] = []
        for idx, pid in enumerate(self._project_map):
            if not pid:
                continue
            name = name_by_id.get(str(pid), tr("upload_unknown_project"))
            lines.append(tr("upload_slot_entry").format(slot=idx, name=name))
        self._binding_overview.setPlainText("\n".join(lines))

    def _on_browse_lua(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("upload_browse"),
            str(_OUTPUT_DIR) if _OUTPUT_DIR.is_dir() else "",
            "Lua (*.lua);;All (*.*)",
        )
        if path:
            self._edit_lua.setText(path)
            self._maybe_fill_project_name(path)

    def _on_pick_latest_lua(self):
        path = self._find_latest_lua()
        if path:
            self._edit_lua.setText(path)
            self._maybe_fill_project_name(path)
            self._log_line(tr("upload_latest_picked").format(path=path))
        else:
            self._log_line(tr("upload_no_lua_found"))

    @staticmethod
    def _find_latest_lua() -> Optional[str]:
        if not _OUTPUT_DIR.is_dir():
            return None
        candidates = list(_OUTPUT_DIR.rglob("*.lua"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        return str(latest)

    def _maybe_fill_project_name(self, lua_path: str):
        if self._edit_project_name.text().strip():
            return
        stem = Path(lua_path).stem
        if stem:
            self._edit_project_name.setText(stem)

    def _resolve_name_conflict(self, name: str) -> Optional[tuple]:
        """返回 ('new'|'overwrite', final_name) 或 None（取消）。"""
        try:
            existing_id = self._sdk().find_project_id_by_name(name)
        except Exception as e:
            QMessageBox.warning(self, tr("upload_err_title"), str(e))
            return None

        if not existing_id:
            return ("new", name)

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("upload_dup_title"))
        box.setText(tr("upload_dup_msg").format(name=name))
        overwrite_btn = box.addButton(tr("upload_dup_overwrite"), QMessageBox.AcceptRole)
        rename_btn = box.addButton(tr("upload_dup_rename"), QMessageBox.ActionRole)
        cancel_btn = box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return None
        if clicked == overwrite_btn:
            return ("overwrite", name)
        new_name, ok = QInputDialog.getText(
            self,
            tr("upload_dup_rename_title"),
            tr("upload_dup_rename_prompt"),
            text=f"{name}_new",
        )
        if not ok or not new_name.strip():
            return None
        return self._resolve_name_conflict(new_name.strip())

    def _on_upload(self):
        if not self._is_connected():
            self._log_line(tr("upload_need_connection"))
            return

        lua_path = self._edit_lua.text().strip()
        project_name = self._edit_project_name.text().strip()
        if not lua_path:
            self._log_line(tr("upload_need_lua"))
            return
        if not Path(lua_path).is_file():
            self._log_line(tr("upload_lua_missing").format(path=lua_path))
            return
        if not project_name:
            self._log_line(tr("upload_need_name"))
            return

        resolved = self._resolve_name_conflict(project_name)
        if not resolved:
            self._log_line(tr("upload_cancelled"))
            return
        action, final_name = resolved

        bind_mode = self._combo_upload_mode.currentData() == self.MODE_UPLOAD_BIND
        map_index = self._spin_upload_slot.value() if bind_mode else None

        self._persist_settings()
        self._log_line(tr("upload_start").format(name=final_name))

        def task():
            sdk = self._sdk()
            if action == "overwrite":
                pid = sdk.find_project_id_by_name(final_name)
                if not pid:
                    raise RobotProjectSDKError(tr("upload_overwrite_not_found"))
                result = sdk.overwrite_project_lua(pid, lua_path, project_name=final_name)
                if map_index is not None:
                    sdk.bind_project_to_map_index(pid, map_index)
                    result["map_index"] = map_index
                result["action"] = "overwrite"
                return result
            result = sdk.save_new_project(
                project_name=final_name,
                lua_file=lua_path,
                points=[],
                variables={},
                map_index=map_index,
            )
            result["action"] = "new"
            return result

        def on_ok(result):
            action_key = result.get("action", "new")
            if action_key == "overwrite":
                self._log_line(tr("upload_done_overwrite").format(name=final_name))
            else:
                self._log_line(tr("upload_done_new").format(name=final_name))
            if result.get("map_index") is not None:
                self._log_line(
                    tr("upload_bound_slot").format(slot=result["map_index"])
                )

        self._run_async(task, on_ok, refresh_after=True)

    def _on_refresh_projects(self):
        if not self._is_connected():
            self._log_line(tr("upload_need_connection"))
            return

        self._log_line(tr("upload_refreshing"))

        def task():
            sdk = self._sdk()
            projects = sdk.list_projects()
            project_map = sdk.get_project_map()
            return {"projects": projects, "map": project_map}

        def on_ok(data):
            self._projects = data.get("projects", [])
            self._project_map = data.get("map", [])
            self._rebuild_bind_project_combo()
            self._rebuild_binding_overview()
            self._log_line(tr("upload_refreshed").format(count=len(self._projects)))

        self._run_async(task, on_ok)

    def _on_bind_slot(self):
        if not self._is_connected():
            self._log_line(tr("upload_need_connection"))
            return

        project_id = self._combo_bind_project.currentData()
        if not project_id:
            self._log_line(tr("upload_need_project"))
            return
        slot = self._spin_bind_slot.value()
        name = self._combo_bind_project.currentText()
        self._log_line(tr("upload_binding").format(slot=slot, name=name))

        def task():
            sdk = self._sdk()
            sdk.bind_project_to_map_index(project_id, slot)
            return {"slot": slot, "project_id": project_id, "name": name}

        def on_ok(result):
            self._log_line(
                tr("upload_bind_ok").format(
                    slot=result["slot"], name=result["name"]
                )
            )

        self._run_async(task, on_ok, refresh_after=True)

    def _restore_settings(self):
        p = _SETTINGS_PREFIX
        self._edit_lua.setText(str(self._settings.value(f"{p}lua_path", "")))
        self._edit_project_name.setText(str(self._settings.value(f"{p}project_name", "")))
        mode = str(self._settings.value(f"{p}mode", self.MODE_UPLOAD_ONLY))
        idx = self._combo_upload_mode.findData(mode)
        if idx >= 0:
            self._combo_upload_mode.setCurrentIndex(idx)
        self._spin_upload_slot.setValue(int(self._settings.value(f"{p}upload_slot", 0)))
        self._spin_bind_slot.setValue(int(self._settings.value(f"{p}bind_slot", 0)))

    def _persist_settings(self):
        p = _SETTINGS_PREFIX
        self._settings.setValue(f"{p}lua_path", self._edit_lua.text().strip())
        self._settings.setValue(f"{p}project_name", self._edit_project_name.text().strip())
        self._settings.setValue(f"{p}mode", self._combo_upload_mode.currentData())
        self._settings.setValue(f"{p}upload_slot", self._spin_upload_slot.value())
        self._settings.setValue(f"{p}bind_slot", self._spin_bind_slot.value())

    def on_leave(self):
        self._persist_settings()
