from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QGroupBox, QGridLayout, QTextEdit
)
from PySide6.QtCore import Qt
from app.base_page import BasePage


class MotionPage(BasePage):
    """运动指令页 — movJ / movL / movC / move_path (Part 10)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title = QLabel("运动指令")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        # 指令类型
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("类型:"))
        self._cmd_type = QComboBox()
        self._cmd_type.addItems(["movJ", "movL", "movC", "movCircle", "move_path"])
        type_row.addWidget(self._cmd_type)
        type_row.addStretch()
        layout.addLayout(type_row)

        # 目标点
        target_group = QGroupBox("目标点 (关节角 deg / 笛卡尔坐标 mm+deg)")
        target_layout = QGridLayout(target_group)
        self._target_inputs = []
        labels = ["J1/X:", "J2/Y:", "J3/Z:", "J4/Rx:", "J5/Ry:", "J6/Rz:"]
        for i, lbl in enumerate(labels):
            target_layout.addWidget(QLabel(lbl), i // 3, (i % 3) * 2)
            inp = QLineEdit("0")
            inp.setFixedWidth(80)
            target_layout.addWidget(inp, i // 3, (i % 3) * 2 + 1)
            self._target_inputs.append(inp)
        layout.addWidget(target_group)

        # 参数行
        param_row = QHBoxLayout()
        param_row.addWidget(QLabel("速度:"))
        self._speed = QLineEdit("60")
        self._speed.setFixedWidth(60)
        param_row.addWidget(self._speed)
        param_row.addWidget(QLabel("加速度:"))
        self._acc = QLineEdit("150")
        self._acc.setFixedWidth(60)
        param_row.addWidget(self._acc)
        param_row.addWidget(QLabel("过渡半径:"))
        self._blend = QLineEdit("20")
        self._blend.setFixedWidth(60)
        param_row.addStretch()
        layout.addLayout(param_row)

        # 发送按钮
        btn_row = QHBoxLayout()
        self._btn_send = QPushButton("发送指令")
        self._btn_send.setFixedHeight(36)
        self._btn_send.setEnabled(False)
        self._btn_send.setCursor(Qt.PointingHandCursor)
        self._btn_send.setStyleSheet(
            "QPushButton { background-color: #e94560; color: white; border: none;"
            "border-radius: 18px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #ff5777; }"
            "QPushButton:disabled { background-color: #2a2a3e; color: #555; }"
        )
        btn_row.addWidget(self._btn_send)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # 日志
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        self._log.setStyleSheet(
            "background-color: #0d1b36; color: #a0a0a0; border: 1px solid #0f3460; font-size: 11px;"
        )
        layout.addWidget(self._log)

        layout.addStretch()

    def set_enabled(self, enabled: bool):
        self._btn_send.setEnabled(enabled)

    def append_log(self, text: str):
        self._log.append(text)
