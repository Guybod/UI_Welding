from PySide6.QtWidgets import QVBoxLayout
from app.base_page import BasePage
from app.widgets.node_editor import NodeEditorWidget


class MotionPage(BasePage):
    """运动节点编排页 — 节点连线式机器人运动流程编排 (plan2.md)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        # 左侧 48px 预留给收起状态的运动抽屉, 展开时需用户手动收回
        layout.setContentsMargins(48, 0, 0, 0)
        self._editor = NodeEditorWidget(self)
        layout.addWidget(self._editor)

    def on_enter(self):
        if self.sp and self.sp.cm:
            self._editor.set_connection_check(
                lambda: bool(self.sp and self.sp.cm and self.sp.cm.is_connected),
            )

    def on_leave(self):
        self._editor.stop_execution()

    def on_connection_changed(self, connected: bool):
        if not connected:
            self._editor.stop_execution()
