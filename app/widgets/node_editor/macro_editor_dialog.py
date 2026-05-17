"""宏子图编辑器 — 双击 MacroCall 打开。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
)
from PySide6.QtCore import Qt

from app.i18n import tr
from app.widgets.node_editor.graph_scene import GraphScene
from app.widgets.node_editor.graph_view import GraphView
from app.widgets.node_editor.graph_validator import GraphValidator
from app.widgets.node_editor.macro_storage import MacroDef, save_macro
from app.widgets.node_editor.node_library_panel import NodeLibraryPanel


class MacroEditorDialog(QDialog):
    def __init__(self, macro: MacroDef, library: NodeLibraryPanel, parent=None):
        super().__init__(parent)
        self._macro = macro
        self._library = library
        self._saved = False

        self.setWindowTitle(tr("macro_editor_title").format(name=macro.name))
        self.resize(960, 640)

        layout = QVBoxLayout(self)
        hint = QLabel(tr("macro_editor_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #aaa; padding: 4px 0;")
        layout.addWidget(hint)

        self._scene = GraphScene(self)
        self._scene._library = library
        self._view = GraphView(self._scene, self)
        self._view._library = library
        self._scene.load_from_graph_data(macro.graph)
        layout.addWidget(self._view, 1)

        row = QHBoxLayout()
        row.addStretch()
        btn_save = QPushButton(tr("macro_editor_save"))
        btn_save.clicked.connect(self._on_save)
        btn_cancel = QPushButton(tr("macro_editor_cancel"))
        btn_cancel.clicked.connect(self.reject)
        row.addWidget(btn_save)
        row.addWidget(btn_cancel)
        layout.addLayout(row)

    def _on_save(self) -> None:
        graph = self._scene.to_graph_data()
        graph.variables = list(self._library.variables())
        graph.positions = list(self._library.positions())
        from app.widgets.node_editor.macro_validate import validate_macro_references_recursive

        r = GraphValidator().validate(graph)
        known = {m.macro_id for m in self._library._macros}
        validate_macro_references_recursive(
            graph,
            self._library.get_macro,
            known,
            r,
        )
        if not r.ok:
            QMessageBox.warning(
                self,
                tr("macro_editor_title").format(name=self._macro.name),
                "\n".join(r.errors[:10]),
            )
            return
        self._macro.graph = graph
        save_macro(self._macro, self._library._projects_root)
        self._saved = True
        self.accept()

    def was_saved(self) -> bool:
        return self._saved
