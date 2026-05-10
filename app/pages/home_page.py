from PySide6.QtWidgets import QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from app.base_page import BasePage


class HomePage(BasePage):
    """首页 — 占位"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        title = QLabel("首页")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title, alignment=Qt.AlignCenter)
        hint = QLabel("连接机器人后可查看实时状态")
        hint.setStyleSheet("color: #888888; font-size: 14px;")
        layout.addWidget(hint, alignment=Qt.AlignCenter)
