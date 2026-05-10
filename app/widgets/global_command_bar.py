from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QDialog, QVBoxLayout, QLabel
)
from PySide6.QtCore import Signal, Qt, QSize


class _ToggleSwitch(QPushButton):
    """椭圆形开关按钮 — 点击切换 checked 状态"""

    toggled = Signal(bool)

    def __init__(self, text_on: str, text_off: str, parent=None):
        super().__init__(text_off, parent)
        self._text_on = text_on
        self._text_off = text_off
        self.setCheckable(True)
        self.setChecked(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(QSize(72, 34))
        self.setStyleSheet(self._style())
        self.toggled.connect(self._on_toggled)

    def set_checked_silent(self, checked: bool):
        """程序设置状态, 不触发 toggled 信号"""
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._on_toggled(checked)

    def _on_toggled(self, checked: bool):
        self.setText(self._text_on if checked else self._text_off)
        self.setStyleSheet(self._style())

    def _style(self):
        checked = self.isChecked()
        bg = "#e94560" if checked else "#2a2a3e"
        return f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                border: none;
                border-radius: 17px;
                font-size: 12px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                background-color: {"#ff5777" if checked else "#3a3a5e"};
            }}
        """


class _ThreeWaySwitch(QWidget):
    """三挡位模式切换 — 椭圆, 三区点击"""

    mode_changed = Signal(int)  # 0=manual, 1=auto, 2=remote

    MODES = ["手动", "自动", "远程"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(180, 34))
        self._current = 1  # default auto
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor, QFont, QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        path = QPainterPath()
        path.addRoundedRect(r.x(), r.y(), r.width(), r.height(), 17, 17)
        p.setClipPath(path)

        w = r.width() / 3
        p.setPen(Qt.NoPen)

        # background
        p.setBrush(QColor("#2a2a3e"))
        p.drawRect(r)

        # active segment
        px = self._current * w
        p.setBrush(QColor("#e94560"))
        p.drawRect(int(px), 0, int(w), r.height())

        # text
        p.setPen(QColor("white"))
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        for i, label in enumerate(self.MODES):
            p.drawText(int(i * w), 0, int(w), r.height(), Qt.AlignCenter, label)
        p.end()

    def mousePressEvent(self, event):
        w = self.width() / 3
        idx = int(event.position().x() // w)
        idx = max(0, min(2, idx))
        if idx != self._current:
            self._current = idx
            self.mode_changed.emit(idx)
            self.update()


class ErrorDialog(QDialog):
    """错误弹窗 — 由 publish/Error 推送触发, 只能由清错按钮关闭"""

    clear_requested = Signal()

    def __init__(self, errors: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("机器人错误")
        self.setMinimumSize(420, 260)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("机器人发生错误:"))
        text = "\n".join(str(e) for e in errors[-20:])
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("background:#111; padding:8px; border-radius:4px;")
        layout.addWidget(label)

        btn = QPushButton("清除错误")
        btn.setFixedHeight(38)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560; color: white; border: none;
                border-radius: 19px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #ff5777; }
        """)
        btn.clicked.connect(self._on_clear)
        layout.addWidget(btn)
        self.setLayout(layout)

    def _on_clear(self):
        self.clear_requested.emit()
        self.accept()

    def closeEvent(self, event):
        event.ignore()  # 只能由清错按钮关闭


class GlobalCommandBar(QWidget):
    """底部全局操作栏 — Part 1D: 只创建禁用按钮/占位信号"""

    switch_on_toggled = Signal(bool)
    stop_move = Signal()
    pause_move = Signal()
    resume_move = Signal()
    project_start = Signal()
    project_stop = Signal()
    project_pause = Signal()
    project_resume = Signal()
    simulation_toggled = Signal(bool)
    mode_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("commandBarPlaceholder")
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # --- 使能开关 ---
        self._btn_enable = _ToggleSwitch("已使能", "未使能")
        self._btn_enable.toggled.connect(self.switch_on_toggled.emit)
        layout.addWidget(self._btn_enable)
        layout.addSpacing(16)

        # --- 运动控制 ---
        self._btn_stop_move = self._add_oval_btn(layout, "停止运动")
        self._btn_pause = self._add_oval_btn(layout, "暂停运动")
        self._btn_resume = self._add_oval_btn(layout, "恢复运动")
        self._btn_resume.hide()
        layout.addSpacing(16)

        # --- 工程 ---
        self._btn_start = self._add_oval_btn(layout, "启动工程")
        self._btn_pause_project = self._add_oval_btn(layout, "暂停工程")
        self._btn_stop_project = self._add_oval_btn(layout, "停止工程")
        layout.addSpacing(16)

        # --- 仿真/实机开关 (右侧) ---
        layout.addStretch()
        self._btn_simulation = _ToggleSwitch("仿真", "实机")
        self._btn_simulation.toggled.connect(self.simulation_toggled.emit)
        layout.addWidget(self._btn_simulation)

        # --- 模式三挡开关 ---
        self._mode_switch = _ThreeWaySwitch()
        self._mode_switch.mode_changed.connect(self.mode_changed.emit)
        layout.addWidget(self._mode_switch)

        # 连接 pause/resume 切换逻辑
        self._btn_pause.clicked.connect(self._on_pause_clicked)
        self._btn_resume.clicked.connect(self._on_resume_clicked)
        self._btn_pause_project.clicked.connect(self._on_project_pause_clicked)
        self._btn_stop_project.clicked.connect(self.project_stop.emit)
        self._btn_start.clicked.connect(self.project_start.emit)
        self._btn_stop_move.clicked.connect(self.stop_move.emit)

        # Part 1D: 全部禁用
        self.set_all_enabled(False)

    def _add_oval_btn(self, layout, text):
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(34)
        btn.setMinimumWidth(80)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a3e; color: white; border: none;
                border-radius: 17px; font-size: 12px; font-weight: bold;
                padding: 4px 16px;
            }
            QPushButton:hover { background-color: #3a3a5e; }
            QPushButton:disabled { background-color: #1a1a2e; color: #555; }
        """)
        layout.addWidget(btn)
        return btn

    def _on_pause_clicked(self):
        self._btn_pause.hide()
        self._btn_resume.show()
        self.pause_move.emit()

    def _on_resume_clicked(self):
        self._btn_resume.hide()
        self._btn_pause.show()
        self.resume_move.emit()

    def _on_project_pause_clicked(self):
        self.project_pause.emit()
        self._btn_start.hide()
        self._btn_pause_project.hide()
        self._btn_stop_project.hide()
        # show resume + stop
        self._btn_resume.show()
        self._btn_stop_project.show()

    def set_motion_paused(self, paused: bool):
        self._btn_pause.setVisible(not paused)
        self._btn_resume.setVisible(paused)

    def set_project_paused(self, paused: bool):
        if paused:
            self._btn_start.hide()
            self._btn_pause_project.hide()
            self._btn_resume.show()
            self._btn_stop_project.show()
        else:
            self._btn_resume.hide()
            self._btn_start.show()
            self._btn_pause_project.show()
            self._btn_stop_project.show()

    def set_enable_state(self, enabled: bool):
        self._btn_enable.set_checked_silent(enabled)

    def set_mode(self, mode: int):
        self._mode_switch._current = mode
        self._mode_switch.update()

    def set_simulation(self, sim: bool):
        self._btn_simulation.set_checked_silent(sim)

    def set_all_enabled(self, enabled: bool):
        for w in self.findChildren(QPushButton):
            if w is not self._btn_enable and w is not self._btn_simulation:
                w.setEnabled(enabled)
        # toggle switches always allow user interaction
