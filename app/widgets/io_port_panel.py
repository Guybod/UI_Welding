"""IO 端口网格 — DO 数字翻转；AO 点击设置模拟量；AI/DI 只读。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from services.io_monitor_service import (
    IO_COUNTS,
    DIGITAL_WRITABLE_TYPES,
    ANALOG_WRITABLE_TYPES,
    format_display_value,
    is_digital_high,
)


class _IoReadCell(QPushButton):
    """DI / AI 只读显示。"""

    def __init__(self, io_type: str, port: int, parent=None):
        super().__init__(parent)
        self.io_type = io_type
        self.port = port
        self.setMinimumSize(52, 36)
        self.setEnabled(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_io_value(self, value: float | int) -> None:
        disp = format_display_value(value, self.io_type)
        self.setText(f"{self.io_type}{self.port}\n{disp}")
        if self.io_type == "AI":
            self.setStyleSheet(
                "QPushButton { background:#37474F; color:#B0BEC5; border:1px solid #546E7A; "
                "font-size:10px; padding:2px; }"
            )
        else:
            high = is_digital_high(value, self.io_type)
            bg = "#2E7D32" if high else "#424242"
            self.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:#ddd; border:1px solid #616161; "
                "font-size:10px; padding:2px; }"
            )


class _DoCell(QPushButton):
    """DO — 点击翻转 0/1。"""

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.io_type = "DO"
        self.port = port
        self._value: float | int = 0
        self.setMinimumSize(52, 36)

    def set_io_value(self, value: float | int) -> None:
        self._value = value
        disp = format_display_value(value, "DO")
        self.setText(f"DO{self.port}\n{disp}")
        high = is_digital_high(value, "DO")
        if high:
            self.setStyleSheet(
                "QPushButton { background:#2E7D32; color:#fff; border:1px solid #66BB6A; "
                "font-weight:bold; font-size:10px; padding:2px; }"
                "QPushButton:hover { background:#388E3C; }"
            )
        else:
            self.setStyleSheet(
                "QPushButton { background:#424242; color:#ccc; border:1px solid #616161; "
                "font-size:10px; padding:2px; }"
                "QPushButton:hover { background:#4E4E4E; }"
            )

    def value(self) -> float | int:
        return self._value


class _AoCell(QPushButton):
    """AO — 点击设置浮点模拟量。"""

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.io_type = "AO"
        self.port = port
        self._value: float = 0.0
        self.setMinimumSize(64, 40)
        self.setToolTip(tr("io_ao_click_set"))

    def set_io_value(self, value: float | int) -> None:
        try:
            self._value = float(value)
        except (TypeError, ValueError):
            self._value = 0.0
        disp = format_display_value(self._value, "AO")
        self.setText(f"AO{self.port}\n{disp}")
        self.setStyleSheet(
            "QPushButton { background:#004D40; color:#80CBC4; border:1px solid #00897B; "
            "font-size:10px; padding:2px; }"
            "QPushButton:hover { background:#00695C; }"
            "QPushButton:disabled { background:#333; color:#666; border:1px solid #444; }"
        )

    def value(self) -> float:
        return self._value


class IoPortPanel(QWidget):
    """单类 IO（DI/DO/AI/AO）端口面板。"""

    do_toggle_requested = Signal(int)
    ao_edit_requested = Signal(int)

    def __init__(self, io_type: str, parent=None):
        super().__init__(parent)
        self._io_type = io_type.upper()
        self._cells: dict[int, QWidget] = {}
        count = IO_COUNTS.get(self._io_type, 0)

        box = QGroupBox(self._title_for_type())
        grid = QGridLayout(box)
        grid.setSpacing(6)
        cols = 8 if count > 8 else max(count, 1)
        for port in range(count):
            cell = self._make_cell(port)
            self._cells[port] = cell
            if self._io_type == "DO":
                cell.clicked.connect(lambda checked=False, p=port: self.do_toggle_requested.emit(p))
            elif self._io_type == "AO":
                cell.clicked.connect(lambda checked=False, p=port: self.ao_edit_requested.emit(p))
            grid.addWidget(cell, port // cols, port % cols)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(box)

    def _make_cell(self, port: int) -> QWidget:
        if self._io_type == "DO":
            return _DoCell(port, self)
        if self._io_type == "AO":
            return _AoCell(port, self)
        return _IoReadCell(self._io_type, port, self)

    def _title_for_type(self) -> str:
        key = {
            "DI": "io_panel_di",
            "DO": "io_panel_do",
            "AI": "io_panel_ai",
            "AO": "io_panel_ao",
        }.get(self._io_type, self._io_type)
        return tr(key)

    def update_values(self, values: dict[tuple[str, int], float | int]) -> None:
        for port, cell in self._cells.items():
            val = values.get((self._io_type, port), 0)
            if hasattr(cell, "set_io_value"):
                cell.set_io_value(val)

    def set_interactive(self, on: bool) -> None:
        if self._io_type in DIGITAL_WRITABLE_TYPES:
            for cell in self._cells.values():
                cell.setEnabled(on)
        elif self._io_type in ANALOG_WRITABLE_TYPES:
            for cell in self._cells.values():
                cell.setEnabled(on)
        else:
            for cell in self._cells.values():
                cell.setEnabled(False)


class IoMonitorBoard(QWidget):
    """四组 IO 面板。"""

    do_toggle_requested = Signal(int)
    ao_set_requested = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panels = {
            t: IoPortPanel(t, self)
            for t in ("DI", "DO", "AI", "AO")
        }
        self._panels["DO"].do_toggle_requested.connect(self.do_toggle_requested.emit)
        self._panels["AO"].ao_edit_requested.connect(self._on_ao_edit)

        top = QWidget()
        top_lay = QGridLayout(top)
        top_lay.addWidget(self._panels["DI"], 0, 0)
        top_lay.addWidget(self._panels["DO"], 0, 1)
        bottom = QWidget()
        bot_lay = QGridLayout(bottom)
        bot_lay.addWidget(self._panels["AI"], 0, 0)
        bot_lay.addWidget(self._panels["AO"], 0, 1)

        lay = QVBoxLayout(self)
        lay.addWidget(top)
        lay.addWidget(bottom)
        from PySide6.QtWidgets import QLabel
        hint = QLabel(tr("io_click_hint"))
        hint.setStyleSheet("color:#888; font-size:11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

    def _on_ao_edit(self, port: int) -> None:
        cell = self._panels["AO"]._cells.get(port)
        current = cell.value() if isinstance(cell, _AoCell) else 0.0
        self.ao_set_requested.emit(port, current)

    def apply_values(self, values: dict[tuple[str, int], float | int]) -> None:
        for panel in self._panels.values():
            panel.update_values(values)

    def set_interactive(self, on: bool) -> None:
        for panel in self._panels.values():
            panel.set_interactive(on)
