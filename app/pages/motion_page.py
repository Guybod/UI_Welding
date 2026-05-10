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
