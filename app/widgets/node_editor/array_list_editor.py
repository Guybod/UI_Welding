"""数组列表编辑器 — 属性面板 / 变量对话框 / Array 常量节点共用。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QLabel,
    QScrollArea,
    QFrame,
    QSizePolicy,
)

from app.i18n import tr
from app.widgets.node_editor.var_value import coerce_array_element, format_array_element, parse_var_storage


class ArrayListEditor(QWidget):
    """逐行编辑数组元素，替代 JSON 文本框。"""

    value_changed = Signal(list)

    def __init__(self, parent=None, *, compact: bool = False):
        super().__init__(parent)
        self._blocking = False
        self._row_edits: list[QLineEdit] = []
        self._compact = compact

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4 if compact else 6)

        self._hint = QLabel(tr("array_list_hint"))
        self._hint.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self._hint.setWordWrap(True)
        if compact:
            self._hint.hide()
        outer.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_h = 110 if compact else 180
        scroll.setFixedHeight(scroll_h)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._scroll = scroll

        self._rows_host = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_host)
        outer.addWidget(scroll)

        btn_row = QHBoxLayout()
        self._btn_add = QPushButton(tr("array_list_add"))
        self._btn_add.clicked.connect(self._on_add_row)
        btn_row.addWidget(self._btn_add)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        self._empty_label = QLabel(tr("array_list_empty"))
        self._empty_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px 0;")
        outer.addWidget(self._empty_label)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._update_empty_visible()

    def set_value(self, value) -> None:
        """加载列表（list 或变量库 JSON 字符串）。"""
        self._blocking = True
        try:
            if isinstance(value, list):
                arr = list(value)
            else:
                arr = parse_var_storage(value, "array")
            self._clear_rows()
            for item in arr:
                self._append_row(format_array_element(item), connect=False)
        finally:
            self._blocking = False
        self._update_empty_visible()

    def get_value(self) -> list:
        out: list = []
        for edit in self._row_edits:
            text = edit.text().strip()
            if text == "":
                continue
            out.append(coerce_array_element(text))
        return out

    def _clear_rows(self) -> None:
        for edit in self._row_edits:
            edit.deleteLater()
        self._row_edits.clear()
        while self._rows_layout.count() > 0:
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rows_layout.addStretch()

    def _append_row(self, text: str = "", *, connect: bool = True) -> QLineEdit:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        idx = len(self._row_edits)
        lbl = QLabel(f"{idx}")
        lbl.setFixedWidth(22)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #888; font-size: 11px;")
        edit = QLineEdit(text)
        edit.setPlaceholderText(tr("array_list_elem_ph"))
        edit.setStyleSheet(
            "background: #3a3a3d; color: #e0e0e0; border: 1px solid #555;"
            " border-radius: 3px; padding: 2px 6px;",
        )
        btn_del = QPushButton("×")
        btn_del.setFixedSize(24, 24)
        btn_del.setToolTip(tr("array_list_remove"))
        btn_del.clicked.connect(lambda *a, e=edit: self._remove_row(e))
        row_layout.addWidget(lbl)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(btn_del)
        insert_at = max(0, self._rows_layout.count() - 1)
        self._rows_layout.insertWidget(insert_at, row)
        self._row_edits.append(edit)
        if connect:
            edit.textChanged.connect(self._on_edited)
        self._reindex_labels()
        self._update_empty_visible()
        return edit

    def _remove_row(self, edit: QLineEdit) -> None:
        if edit not in self._row_edits:
            return
        self._row_edits.remove(edit)
        row = edit.parentWidget()
        if row:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._reindex_labels()
        self._update_empty_visible()
        self._emit()

    def _on_add_row(self) -> None:
        self._append_row("")
        self._row_edits[-1].setFocus()
        self._emit()

    def _on_edited(self) -> None:
        self._emit()

    def _emit(self) -> None:
        if self._blocking:
            return
        self.value_changed.emit(self.get_value())

    def _reindex_labels(self) -> None:
        for i, edit in enumerate(self._row_edits):
            row = edit.parentWidget()
            if not row:
                continue
            lbl = row.layout().itemAt(0).widget()
            if isinstance(lbl, QLabel):
                lbl.setText(f"{i}")

    def _update_empty_visible(self) -> None:
        self._empty_label.setVisible(len(self._row_edits) == 0)
