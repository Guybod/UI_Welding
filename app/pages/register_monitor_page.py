"""寄存器监控页 — 用户添加寄存器卡片，轮询读写。"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.base_page import BasePage
from app.i18n import I18nManager, tr
from app.robot_mode import is_remote_mode, query_robot_mode
from app.widgets.register_card_board import RegisterCardBoard
from services.register_monitor_service import (
    RegisterDef,
    RegisterMonitorClient,
    address_conflict,
    coerce_value,
    load_register_defs,
    save_register_defs,
    toggle_bool_value,
)


class _AddRegisterDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("reg_add_title"))
        form = QFormLayout(self)
        self._type = QComboBox()
        self._type.addItem(tr("reg_type_bool"), "bool")
        self._type.addItem(tr("reg_type_int"), "int")
        self._type.addItem(tr("reg_type_float"), "float")
        form.addRow(tr("reg_field_type"), self._type)
        self._addr = QSpinBox()
        self._addr.setRange(0, 999999)
        form.addRow(tr("reg_field_address"), self._addr)
        self._label = QLineEdit()
        self._label.setPlaceholderText(tr("reg_field_label_ph"))
        form.addRow(tr("reg_field_label"), self._label)
        self._size_hint = QLabel(tr("reg_add_size_bool"))
        self._size_hint.setStyleSheet("color:#888; font-size:11px;")
        self._size_hint.setWordWrap(True)
        form.addRow(self._size_hint)
        self._type.currentIndexChanged.connect(self._on_type_changed)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_type_changed(self) -> None:
        t = self._type.currentData()
        if t == "bool":
            self._size_hint.setText(tr("reg_add_size_bool"))
        else:
            self._size_hint.setText(tr("reg_add_size_word"))

    def build_register(self) -> RegisterDef:
        return RegisterDef(
            reg_id="",
            address=self._addr.value(),
            reg_type=self._type.currentData(),
            label=self._label.text().strip(),
        )


class RegisterMonitorPage(BasePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Codroid", "RobotUI")
        self._registers: list[RegisterDef] = load_register_defs(self._settings)
        self._values: dict[str, object] = {}
        self._client: RegisterMonitorClient | None = None
        self._poll_busy = False
        self._write_busy = False
        self._active = False
        self._robot_mode = query_robot_mode(self)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_once)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 8, 8, 8)

        toolbar = QHBoxLayout()
        self._status = QLabel(tr("reg_status_disconnected"))
        self._status.setStyleSheet("color:#888;")
        toolbar.addWidget(self._status)
        toolbar.addStretch()
        self._btn_add = QPushButton(tr("reg_btn_add"))
        self._btn_add.clicked.connect(self._on_add_register)
        toolbar.addWidget(self._btn_add)
        self._btn_delete = QPushButton(tr("reg_btn_delete"))
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._on_delete_selected)
        self._btn_delete.setStyleSheet("QPushButton { color:#ef9a9a; }")
        toolbar.addWidget(self._btn_delete)
        toolbar.addWidget(QLabel(tr("reg_poll_interval")))
        self._interval = QSpinBox()
        self._interval.setRange(200, 5000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(" ms")
        self._interval.setValue(int(self._settings.value("register/pollIntervalMs", 500, type=int)))
        self._interval.valueChanged.connect(self._on_interval_changed)
        toolbar.addWidget(self._interval)
        layout.addLayout(toolbar)

        self._board = RegisterCardBoard(self)
        self._board.remove_requested.connect(self._on_remove_register)
        self._board.edit_requested.connect(self._on_edit_register)
        self._board.selection_changed.connect(self._on_selection_changed)
        layout.addWidget(self._board, 1)
        self._rebuild_board()

        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def _rebuild_board(self) -> None:
        self._board.set_registers(self._registers)
        if self._values:
            self._board.apply_values(self._values)

    def _persist(self) -> None:
        save_register_defs(self._registers, self._settings)

    def _on_language_changed(self, _lang: str) -> None:
        self._btn_add.setText(tr("reg_btn_add"))
        self._btn_delete.setText(tr("reg_btn_delete"))
        self._update_status_label()

    def _on_interval_changed(self, ms: int) -> None:
        self._settings.setValue("register/pollIntervalMs", ms)
        if self._poll_timer.isActive():
            self._poll_timer.start(ms)

    def _ensure_client(self) -> RegisterMonitorClient | None:
        if self.sp and self.sp.cm:
            if self._client is None:
                self._client = RegisterMonitorClient(self.sp.cm)
            return self._client
        self._client = None
        return None

    def on_enter(self) -> None:
        self._active = True
        self._robot_mode = query_robot_mode(self)
        self._registers = load_register_defs(self._settings)
        self._rebuild_board()
        client = self._ensure_client()
        connected = bool(client and client.connected)
        self._board.set_interactive(connected and bool(self._registers))
        self._update_status_label()
        if connected and self._registers:
            self._poll_once()
            self._poll_timer.start(self._interval.value())
        else:
            self._poll_timer.stop()

    def on_leave(self) -> None:
        self._active = False
        self._poll_timer.stop()
        self._persist()

    def on_connection_changed(self, connected: bool) -> None:
        self._ensure_client()
        self._board.set_interactive(connected and bool(self._registers))
        if not connected:
            self._poll_timer.stop()
            self._values.clear()
            self._board.apply_values({})
        self._update_status_label()
        if self._active and connected and self._registers:
            self._poll_once()
            self._poll_timer.start(self._interval.value())
        elif not connected:
            self._poll_timer.stop()

    def on_robot_mode_changed(self, mode: int) -> None:
        """由 RobotStatus 订阅推送，仅更新状态栏显示。"""
        if self._robot_mode == mode:
            return
        self._robot_mode = mode
        self._update_status_label()

    def _update_status_label(self) -> None:
        client = self._ensure_client()
        connected = bool(client and client.connected)
        if not connected:
            self._status.setText(tr("reg_status_disconnected"))
            self._status.setStyleSheet("color:#888;")
        elif not is_remote_mode(self._robot_mode):
            self._status.setText(tr("reg_status_need_remote"))
            self._status.setStyleSheet("color:#FFB74D;")
        else:
            n = len(self._registers)
            self._status.setText(tr("reg_status_connected").format(n=n))
            self._status.setStyleSheet("color:#81C784;")

    def _poll_once(self) -> None:
        if not self._active or not self._registers:
            return
        client = self._ensure_client()
        if not client or not client.connected:
            return
        if self._poll_busy or self._write_busy:
            return
        self._poll_busy = True

        def _ok(values):
            self._poll_busy = False
            self._values = values
            self._board.apply_values(values)
            self._update_status_label()

        def _err(exc):
            self._poll_busy = False
            if is_remote_mode(self._robot_mode):
                self._status.setText(tr("reg_status_error").format(msg=str(exc)[:80]))
                self._status.setStyleSheet("color:#E57373;")
            else:
                self._update_status_label()

        client.poll(self._registers, on_ok=_ok, on_error=_err, log_traffic=False)

    def _on_add_register(self) -> None:
        dlg = _AddRegisterDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        reg = dlg.build_register()
        conflict = address_conflict(reg, self._registers)
        if conflict:
            QMessageBox.warning(
                self,
                tr("reg_add_title"),
                tr("reg_address_conflict").format(
                    addr=reg.address,
                    other=conflict.address,
                ),
            )
            return
        self._registers.append(reg)
        self._persist()
        self._rebuild_board()
        client = self._ensure_client()
        if self._active and client and client.connected:
            self._poll_once()
            if not self._poll_timer.isActive():
                self._poll_timer.start(self._interval.value())

    def _on_selection_changed(self, reg_id: str) -> None:
        self._btn_delete.setEnabled(bool(reg_id))

    def _on_delete_selected(self) -> None:
        reg_id = self._board.selected_reg_id()
        if reg_id:
            self._confirm_remove_register(reg_id)

    def _confirm_remove_register(self, reg_id: str) -> None:
        reg = self._find_reg(reg_id)
        if not reg:
            return
        name = (reg.label or "").strip() or tr("reg_card_default_title").format(addr=reg.address)
        ans = QMessageBox.question(
            self,
            tr("reg_delete_title"),
            tr("reg_delete_confirm").format(name=name, addr=reg.address),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._remove_register(reg_id)

    def _on_remove_register(self, reg_id: str) -> None:
        self._confirm_remove_register(reg_id)

    def _remove_register(self, reg_id: str) -> None:
        self._registers = [r for r in self._registers if r.reg_id != reg_id]
        self._values.pop(reg_id, None)
        self._persist()
        self._rebuild_board()
        self._btn_delete.setEnabled(False)
        if not self._registers:
            self._poll_timer.stop()

    def _find_reg(self, reg_id: str) -> RegisterDef | None:
        for r in self._registers:
            if r.reg_id == reg_id:
                return r
        return None

    def _on_edit_register(self, reg_id: str) -> None:
        reg = self._find_reg(reg_id)
        if not reg:
            return
        client = self._ensure_client()
        if (
            not client
            or not client.connected
            or not io_register_api_ready(True, self._robot_mode)
            or self._write_busy
        ):
            return
        current = self._values.get(reg_id, 0)
        if reg.reg_type == "bool":
            new_val = toggle_bool_value(current)
            self._write_register(reg, new_val)
            return
        from PySide6.QtWidgets import QInputDialog
        if reg.reg_type == "float":
            val, ok = QInputDialog.getDouble(
                self,
                tr("reg_edit_title").format(addr=reg.address),
                tr("reg_edit_value"),
                float(coerce_value(current, "float")),
                -1e9,
                1e9,
                4,
            )
        else:
            val, ok = QInputDialog.getInt(
                self,
                tr("reg_edit_title").format(addr=reg.address),
                tr("reg_edit_value"),
                int(coerce_value(current, "int")),
                -32768,
                32767,
                1,
            )
        if ok:
            self._write_register(reg, val)

    def _write_register(self, reg: RegisterDef, value) -> None:
        client = self._ensure_client()
        if not client or not client.connected:
            return
        self._write_busy = True
        self._board.set_interactive(False)

        def _ok():
            self._write_busy = False
            self._board.set_interactive(True)
            self._poll_once()

        def _err(exc):
            self._write_busy = False
            self._board.set_interactive(True)
            if is_remote_mode(self._robot_mode):
                self._status.setText(tr("reg_status_error").format(msg=str(exc)[:80]))
                self._status.setStyleSheet("color:#E57373;")
            else:
                self._update_status_label()

        client.set_value(reg, value, on_ok=_ok, on_error=_err, log_traffic=True)
