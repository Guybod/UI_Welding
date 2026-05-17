"""IO 监控页 — 轮询显示 DI/DO/AI/AO；DO 翻转；AO 设置浮点值。"""

from __future__ import annotations

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from app.base_page import BasePage
from app.i18n import I18nManager, tr
from app.robot_mode import is_remote_mode, query_robot_mode
from app.widgets.io_port_panel import IoMonitorBoard
from services.io_monitor_service import IoMonitorClient, toggle_digital_value


class IoMonitorPage(BasePage):
    """IO 监控 — 16DI / 16DO / 4AI / 4AO，TCP IOManager 轮询。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Codroid", "RobotUI")
        self._client: IoMonitorClient | None = None
        self._values: dict[tuple[str, int], float | int] = {}
        self._poll_busy = False
        self._write_busy = False
        self._active = False
        self._robot_mode = query_robot_mode(self)

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_once)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 8, 8, 8)

        toolbar = QHBoxLayout()
        self._status = QLabel(tr("io_status_disconnected"))
        self._status.setStyleSheet("color:#888;")
        toolbar.addWidget(self._status)
        toolbar.addStretch()
        toolbar.addWidget(QLabel(tr("io_poll_interval")))
        self._interval = QSpinBox()
        self._interval.setRange(200, 5000)
        self._interval.setSingleStep(100)
        self._interval.setSuffix(" ms")
        self._interval.setValue(int(self._settings.value("io/pollIntervalMs", 500, type=int)))
        self._interval.valueChanged.connect(self._on_interval_changed)
        toolbar.addWidget(self._interval)
        layout.addLayout(toolbar)

        self._board = IoMonitorBoard(self)
        self._board.do_toggle_requested.connect(self._on_do_toggle)
        self._board.ao_set_requested.connect(self._on_ao_set_dialog)
        layout.addWidget(self._board, 1)

        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def _on_language_changed(self, _lang: str) -> None:
        self._update_status_label()

    def _on_interval_changed(self, ms: int) -> None:
        self._settings.setValue("io/pollIntervalMs", ms)
        if self._poll_timer.isActive():
            self._poll_timer.start(ms)

    def _ensure_client(self) -> IoMonitorClient | None:
        if self.sp and self.sp.cm:
            if self._client is None:
                self._client = IoMonitorClient(self.sp.cm)
            return self._client
        self._client = None
        return None

    def on_enter(self) -> None:
        self._active = True
        self._robot_mode = query_robot_mode(self)
        client = self._ensure_client()
        connected = bool(client and client.connected)
        self._board.set_interactive(connected)
        self._update_status_label()
        if connected:
            self._poll_once()
            self._poll_timer.start(self._interval.value())
        else:
            self._poll_timer.stop()

    def on_leave(self) -> None:
        self._active = False
        self._poll_timer.stop()

    def on_connection_changed(self, connected: bool) -> None:
        self._ensure_client()
        self._board.set_interactive(connected)
        if not connected:
            self._poll_timer.stop()
            self._values.clear()
            self._board.apply_values({})
        self._update_status_label()
        if self._active and connected:
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
            self._status.setText(tr("io_status_disconnected"))
            self._status.setStyleSheet("color:#888;")
        elif not is_remote_mode(self._robot_mode):
            self._status.setText(tr("io_status_need_remote"))
            self._status.setStyleSheet("color:#FFB74D;")
        else:
            self._status.setText(tr("io_status_connected"))
            self._status.setStyleSheet("color:#81C784;")

    def _poll_once(self) -> None:
        if not self._active:
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
                self._status.setText(tr("io_status_error").format(msg=str(exc)[:80]))
                self._status.setStyleSheet("color:#E57373;")
            else:
                self._update_status_label()

        client.poll(on_ok=_ok, on_error=_err, log_traffic=False)

    def _on_do_toggle(self, port: int) -> None:
        self._write_io_value("DO", port, toggle_digital_value(self._values.get(("DO", port), 0)))

    def _on_ao_set_dialog(self, port: int, current: float) -> None:
        val, ok = QInputDialog.getDouble(
            self,
            tr("io_ao_dialog_title").format(port=port),
            tr("io_ao_dialog_label"),
            float(current),
            -1e6,
            1e6,
            4,
        )
        if ok:
            self._write_io_value("AO", port, float(val))

    def _write_io_value(self, io_type: str, port: int, value: int | float) -> None:
        client = self._ensure_client()
        if not client or not client.connected or self._write_busy:
            return
        self._write_busy = True
        self._board.set_interactive(False)

        def _ok():
            self._write_busy = False
            self._board.set_interactive(True)
            self._poll_once()

        def _err(exc):
            self._write_busy = False
            self._board.set_interactive(client.connected)
            if is_remote_mode(self._robot_mode):
                self._status.setText(tr("io_status_error").format(msg=str(exc)[:80]))
                self._status.setStyleSheet("color:#E57373;")
            else:
                self._update_status_label()

        client.set_value(io_type, port, value, on_ok=_ok, on_error=_err, log_traffic=True)
