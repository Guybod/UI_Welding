"""节点编辑器包 — 延迟导入 NodeEditorWidget，避免无 GUI 环境拉取 PySide6。"""

from __future__ import annotations

__all__ = ["NodeEditorWidget"]


def __getattr__(name: str):
    if name == "NodeEditorWidget":
        from app.widgets.node_editor.node_editor_widget import NodeEditorWidget

        return NodeEditorWidget
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
