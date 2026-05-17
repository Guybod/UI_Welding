"""寄存器监控卡片。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.i18n import tr
from services.register_monitor_service import RegisterDef, format_register_value


class RegisterCard(QFrame):
    """单个寄存器卡片 — 显示类型、地址、当前值。"""

    remove_requested = Signal(str)
    edit_requested = Signal(str)
    selected = Signal(str)

    def __init__(self, reg: RegisterDef, parent=None):
        super().__init__(parent)
        self._reg = reg
        self._selected = False
        self.setObjectName("registerCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(148)
        self.setMaximumWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "#registerCard { background:#353538; border:1px solid #555; border-radius:8px; }"
            "#registerCard:hover { border-color:#777; }"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(4)

        top = QHBoxLayout()
        type_lbl = QLabel(self._type_label())
        type_lbl.setStyleSheet(
            "font-size:10px; font-weight:bold; color:#fff; "
            "background:#5D4037; padding:2px 6px; border-radius:3px;"
            if reg.reg_type == "bool"
            else "font-size:10px; font-weight:bold; color:#fff; "
            "background:#1565C0; padding:2px 6px; border-radius:3px;"
            if reg.reg_type == "int"
            else "font-size:10px; font-weight:bold; color:#fff; "
            "background:#00695C; padding:2px 6px; border-radius:3px;"
        )
        self._btn_rm = QPushButton("×")
        self._btn_rm.setFixedSize(24, 24)
        self._btn_rm.setToolTip(tr("reg_card_delete"))
        self._btn_rm.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rm.setStyleSheet(
            "QPushButton { background:#4a3030; color:#ef9a9a; border:1px solid #755; "
            "border-radius:4px; font-size:15px; font-weight:bold; }"
            "QPushButton:hover { background:#c62828; color:#fff; }"
        )
        self._btn_rm.clicked.connect(self._on_remove_clicked)
        top.addWidget(type_lbl)
        top.addStretch()
        top.addWidget(self._btn_rm)
        root.addLayout(top)

        title = (reg.label or "").strip() or tr("reg_card_default_title").format(addr=reg.address)
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet("font-weight:bold; color:#eee; font-size:11px;")
        self._title_lbl.setWordWrap(True)
        root.addWidget(self._title_lbl)

        size_hint = tr("reg_size_1b") if reg.reg_type == "bool" else tr("reg_size_2b")
        self._addr_lbl = QLabel(f"@{reg.address}  ·  {size_hint}")
        self._addr_lbl.setStyleSheet("color:#999; font-size:10px;")
        root.addWidget(self._addr_lbl)

        self._value_lbl = QLabel("—")
        self._value_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_lbl.setStyleSheet(
            "font-size:18px; font-weight:bold; color:#FFD54F; padding:6px 0;"
        )
        root.addWidget(self._value_lbl)

        hint = tr("reg_card_click_bool") if reg.reg_type == "bool" else tr("reg_card_click_edit")
        hint_lbl = QLabel(hint)
        hint_lbl.setStyleSheet("color:#666; font-size:9px;")
        hint_lbl.setWordWrap(True)
        root.addWidget(hint_lbl)

    def _type_label(self) -> str:
        return {
            "bool": tr("reg_type_bool"),
            "int": tr("reg_type_int"),
            "float": tr("reg_type_float"),
        }.get(self._reg.reg_type, self._reg.reg_type.upper())

    def reg_id(self) -> str:
        return self._reg.reg_id

    def register_def(self) -> RegisterDef:
        return self._reg

    def set_value_display(self, value) -> None:
        self._value_lbl.setText(format_register_value(value, self._reg.reg_type))

    def set_selected(self, on: bool) -> None:
        self._selected = on
        border = "#42A5F5" if on else "#555"
        width = 2 if on else 1
        self.setStyleSheet(
            f"#registerCard {{ background:#353538; border:{width}px solid {border}; "
            "border-radius:8px; }"
            "#registerCard:hover { border-color:#777; }"
        )

    def _on_remove_clicked(self) -> None:
        self.remove_requested.emit(self._reg.reg_id)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child is self._btn_rm or (child and child.parent() is self._btn_rm):
                super().mousePressEvent(event)
                return
            self.selected.emit(self._reg.reg_id)
            self.edit_requested.emit(self._reg.reg_id)
        super().mousePressEvent(event)
