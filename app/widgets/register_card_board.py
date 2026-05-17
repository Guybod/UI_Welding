"""寄存器卡片面板 — 流式网格 + 空状态。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.widgets.register_card import RegisterCard
from services.register_monitor_service import RegisterDef


class RegisterCardBoard(QWidget):
    remove_requested = Signal(str)
    edit_requested = Signal(str)
    selection_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, RegisterCard] = {}
        self._selected_id: str = ""

        self._empty = QLabel(tr("reg_empty_hint"))
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color:#888; font-size:13px; padding:48px;")
        self._empty.setWordWrap(True)

        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(12)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._container)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._empty)
        lay.addWidget(scroll, 1)
        self._scroll = scroll
        scroll.hide()

    def set_registers(self, registers: list[RegisterDef]) -> None:
        for card in list(self._cards.values()):
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        if not registers:
            self._empty.show()
            self._scroll.hide()
            return

        self._empty.hide()
        self._scroll.show()
        cols = 4
        for i, reg in enumerate(registers):
            card = RegisterCard(reg)
            card.remove_requested.connect(self.remove_requested.emit)
            card.edit_requested.connect(self.edit_requested.emit)
            card.selected.connect(self._on_card_selected)
            self._cards[reg.reg_id] = card
            self._grid.addWidget(card, i // cols, i % cols)

    def apply_values(self, values: dict[str, object]) -> None:
        for rid, val in values.items():
            card = self._cards.get(rid)
            if card:
                card.set_value_display(val)

    def set_interactive(self, on: bool) -> None:
        for card in self._cards.values():
            card.setEnabled(on)

    def selected_reg_id(self) -> str:
        return self._selected_id

    def set_selected_reg_id(self, reg_id: str) -> None:
        self._selected_id = reg_id or ""
        for rid, card in self._cards.items():
            card.set_selected(rid == self._selected_id)

    def _on_card_selected(self, reg_id: str) -> None:
        self.set_selected_reg_id(reg_id)
        self.selection_changed.emit(reg_id)
