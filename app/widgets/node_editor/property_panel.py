from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class PropertyPanel(QWidget):
    """属性面板 — 占位, 后续根据选中节点类型显示参数"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyPanel")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("属性")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-weight: bold; padding: 8px;")
        layout.addWidget(title)

        self._placeholder = QLabel("请选择一个节点")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #888888; padding: 20px;")
        layout.addWidget(self._placeholder)
        layout.addStretch()
