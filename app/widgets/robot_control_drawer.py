from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QStackedWidget,
    QButtonGroup,
    QSlider,
)
from PySide6.QtCore import (
    Property,
    QSettings,
    Signal,
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QSize,
)

from view3d.model_resolver import resolve_glb_name
from view3d.preview_frame import RobotPreviewFrame


COLLAPSED_WIDTH = 48
EXPANDED_WIDTH = 348
SIDEBAR_WIDTH = 48
CONTENT_WIDTH = EXPANDED_WIDTH - SIDEBAR_WIDTH


class RobotControlDrawer(QWidget):
    """
    左侧可收缩运动控制抽屉。

    收起状态:
        只显示 48px 左侧窄条，按钮为“运动”。

    展开状态:
        左侧窄条仍然存在，右侧展开示教器风格运动控制面板。
    """

    # Jog：按下开始，松开停止
    jog_pressed = Signal(int, int, int)   # mode(1关节/2笛卡尔), index(0-5), sign(±1)
    jog_released = Signal()

    # moveTo：按下开始，松开停止
    moveto_pressed = Signal(int)          # 0=零点, 1=安全点, 2=蜡烛位, 3=打包位
    moveto_released = Signal()

    # 速度变化
    speed_rate_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("robotControlDrawer")

        self._expanded = False
        self._collapsed_width = COLLAPSED_WIDTH
        self._expanded_width = EXPANDED_WIDTH
        self._hide_content_connected = False
        self._drawer_width = self._collapsed_width

        self.setFixedWidth(self._collapsed_width)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy(),
        )

        self.setStyleSheet("""
            #robotControlDrawer {
                background-color: transparent;
            }
        """)

        self._anim = QPropertyAnimation(self, b"drawer_width", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._sidebar = self._build_sidebar()
        self._content = self._build_content()

        root.addWidget(self._sidebar)
        root.addWidget(self._content)

        self._content.setVisible(False)

    def get_drawer_width(self) -> int:
        return self._drawer_width

    def set_drawer_width(self, width: int) -> None:
        width = int(width)
        if width == self._drawer_width:
            return
        self._drawer_width = width
        self.setFixedWidth(width)
        self.updateGeometry()

    drawer_width = Property(int, get_drawer_width, set_drawer_width)

    # ════════════════ UI 构建 ════════════════

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("drawerSidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setStyleSheet("""
            #drawerSidebar {
                background-color: #16213e;
                border-right: 1px solid #0f3460;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(8)

        self._btn_toggle = QPushButton("运动")
        self._btn_toggle.setFixedSize(QSize(38, 58))
        self._btn_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_toggle.setStyleSheet("""
            QPushButton {
                background-color: #e94560;
                color: white;
                border: none;
                border-radius: 7px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #ff5777;
            }
            QPushButton:pressed {
                background-color: #d53b55;
            }
        """)
        self._btn_toggle.clicked.connect(self._toggle)

        layout.addWidget(self._btn_toggle, alignment=Qt.AlignTop | Qt.AlignHCenter)
        layout.addStretch()

        return sidebar

    def _build_content(self) -> QWidget:
        content = QFrame()
        content.setObjectName("drawerContent")
        content.setFixedWidth(CONTENT_WIDTH)
        content.setStyleSheet("""
            #drawerContent {
                background-color: #16213e;
                border-right: 1px solid #0f3460;
            }

            QLabel {
                color: #d8d8d8;
                font-size: 12px;
            }

            QPushButton {
                background-color: #24345c;
                color: #e8e8e8;
                border: 1px solid #33456f;
                border-radius: 6px;
                min-height: 24px;
                padding: 0px;
            }

            QPushButton:hover {
                background-color: #2f4373;
            }

            QPushButton:pressed {
                background-color: #1e2c4c;
            }

            QPushButton:disabled {
                background-color: #2a2a3e;
                color: #666666;
                border: 1px solid #333333;
            }

            QSlider::groove:horizontal {
                height: 5px;
                background: #2a2a3e;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                width: 14px;
                height: 14px;
                margin: -5px 0px;
                border-radius: 7px;
                background: #e94560;
            }

            QSlider::sub-page:horizontal {
                background: #e94560;
                border-radius: 2px;
            }

            QSlider::add-page:horizontal {
                background: #2a2a3e;
                border-radius: 2px;
            }
        """)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 顶部标题
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(4)

        title = QLabel("机器人运动控制")
        title.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #e94560;
            }
        """)

        self._btn_close = QPushButton("×")
        self._btn_close.setFixedSize(QSize(24, 24))
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.clicked.connect(self.collapse)
        self._btn_close.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #a0a0a0;
                border: none;
                font-size: 18px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                color: white;
                background-color: #24345c;
                border-radius: 12px;
            }
        """)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self._btn_close)
        layout.addLayout(title_row)

        self._model_label = QLabel("型号: --")
        self._model_label.setStyleSheet("color: #a0a0a0; font-size: 11px;")
        layout.addWidget(self._model_label)

        # 坐标系信息行
        coord_info_row = QHBoxLayout()
        coord_info_row.setContentsMargins(0, 0, 0, 0)
        coord_info_row.setSpacing(4)

        self._world_coord_label = QLabel("世界坐标系：坐标系0")
        self._tool_coord_label = QLabel("工具坐标系：工具0")

        self._world_coord_label.setStyleSheet("color: #b8b8c8; font-size: 10px;")
        self._tool_coord_label.setStyleSheet("color: #b8b8c8; font-size: 10px;")

        coord_info_row.addWidget(self._world_coord_label)
        coord_info_row.addStretch()
        coord_info_row.addWidget(self._tool_coord_label)
        layout.addLayout(coord_info_row)

        self._model_view = RobotPreviewFrame(min_height=138)
        self._gl_view = self._model_view.preview
        self._model_view.load_default_preview()
        layout.addWidget(self._model_view, stretch=1)

        # 点动模式切换
        self._mode_bar = QFrame()
        self._mode_bar.setObjectName("jogModeBar")
        self._mode_bar.setFixedHeight(32)
        self._mode_bar.setStyleSheet("""
            #jogModeBar {
                background-color: #10172a;
                border-radius: 16px;
                border: 1px solid #26375f;
            }
        """)

        mode_layout = QHBoxLayout(self._mode_bar)
        mode_layout.setContentsMargins(2, 2, 2, 2)
        mode_layout.setSpacing(2)

        self._btn_joint_mode = QPushButton("关节点动")
        self._btn_cart_mode = QPushButton("坐标系点动")

        for btn in (self._btn_joint_mode, self._btn_cart_mode):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #b8b8c8;
                    border: none;
                    border-radius: 14px;
                    font-size: 12px;
                    font-weight: bold;
                    padding: 0px;
                }
                QPushButton:checked {
                    background-color: #3f6fd8;
                    color: white;
                }
                QPushButton:hover {
                    background-color: #2f4373;
                    color: white;
                }
            """)

        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._btn_joint_mode, 0)
        self._mode_group.addButton(self._btn_cart_mode, 1)
        self._mode_group.idClicked.connect(self._on_mode_changed)

        self._btn_joint_mode.setChecked(True)

        mode_layout.addWidget(self._btn_joint_mode)
        mode_layout.addWidget(self._btn_cart_mode)

        layout.addWidget(self._mode_bar)

        # 点动行堆栈
        self._jog_stack = QStackedWidget()
        self._jog_stack.setObjectName("jogStack")
        self._jog_stack.setStyleSheet("""
            #jogStack {
                background-color: transparent;
                border: none;
            }
        """)

        self._joint_page = self._build_joint_jog_page()
        self._cart_page = self._build_cart_jog_page()

        self._jog_stack.addWidget(self._joint_page)
        self._jog_stack.addWidget(self._cart_page)
        self._jog_stack.setCurrentIndex(0)

        layout.addWidget(self._jog_stack)

        layout.addStretch()

        # moveTo 预设点按钮：2x2，按下开始，松开停止
        preset_grid = QVBoxLayout()
        preset_grid.setContentsMargins(0, 0, 0, 0)
        preset_grid.setSpacing(5)

        preset_row_1 = QHBoxLayout()
        preset_row_1.setContentsMargins(0, 0, 0, 0)
        preset_row_1.setSpacing(5)

        preset_row_2 = QHBoxLayout()
        preset_row_2.setContentsMargins(0, 0, 0, 0)
        preset_row_2.setSpacing(5)

        self._btn_zero_point = self._make_moveto_button("零点", 0)
        self._btn_safe_point = self._make_moveto_button("安全点", 1)
        self._btn_candle_point = self._make_moveto_button("蜡烛位", 2)
        self._btn_pack_point = self._make_moveto_button("打包位", 3)

        preset_row_1.addWidget(self._btn_zero_point)
        preset_row_1.addWidget(self._btn_safe_point)

        preset_row_2.addWidget(self._btn_candle_point)
        preset_row_2.addWidget(self._btn_pack_point)

        preset_grid.addLayout(preset_row_1)
        preset_grid.addLayout(preset_row_2)

        layout.addLayout(preset_grid)

        # 速度条
        speed_row = QHBoxLayout()
        speed_row.setContentsMargins(0, 0, 0, 0)
        speed_row.setSpacing(6)

        speed_title = QLabel("速度")
        speed_title.setFixedWidth(30)
        speed_title.setStyleSheet("color: #d8d8d8; font-size: 11px;")

        self._speed_label = QLabel("70%")
        self._speed_label.setFixedWidth(34)
        self._speed_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._speed_label.setStyleSheet("color: #e94560; font-size: 11px; font-weight: bold;")

        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(1, 100)
        self._speed_slider.setCursor(Qt.PointingHandCursor)
        self._speed_slider.valueChanged.connect(self._on_speed_value_changed)
        self._speed_slider.sliderReleased.connect(self._emit_speed_rate_changed)

        # 恢复上次保存的速度
        saved_speed = QSettings("Codroid", "RobotUI").value("drawer/speed", 70, type=int)
        self._speed_slider.setValue(saved_speed)

        speed_row.addWidget(speed_title)
        speed_row.addWidget(self._speed_slider, stretch=1)
        speed_row.addWidget(self._speed_label)

        layout.addLayout(speed_row)

        return content

    def _make_moveto_button(self, text: str, move_type: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(26)
        btn.setCursor(Qt.PointingHandCursor)

        btn.pressed.connect(lambda t=move_type: self.moveto_pressed.emit(t))
        btn.released.connect(self.moveto_released.emit)

        btn.setStyleSheet("""
            QPushButton {
                background-color: #10172a;
                color: #c8d6ff;
                border: 1px solid #33456f;
                border-radius: 13px;
                font-size: 11px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #2f4373;
                color: white;
            }
            QPushButton:pressed {
                background-color: #1e2c4c;
            }
            QPushButton:disabled {
                background-color: #2a2a3e;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        return btn

    def _build_joint_jog_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(5)

        self._joint_value_labels = []
        self._joint_minus_buttons = []
        self._joint_plus_buttons = []

        joint_names = ["J1", "J2", "J3", "J4", "J5", "J6"]
        default_values = ["0 deg", "0 deg", "90 deg", "0 deg", "0 deg", "0 deg"]

        for i, joint in enumerate(joint_names):
            row = self._build_jog_row(
                minus_text=f"{joint}-",
                value_text=default_values[i],
                plus_text=f"{joint}+",
            )
            btn_minus = row["minus"]
            btn_plus = row["plus"]

            self._joint_minus_buttons.append(btn_minus)
            self._joint_plus_buttons.append(btn_plus)
            self._joint_value_labels.append(row["value"])

            btn_minus.pressed.connect(lambda idx=i: self.jog_pressed.emit(1, idx, -1))
            btn_minus.released.connect(self.jog_released.emit)
            btn_plus.pressed.connect(lambda idx=i: self.jog_pressed.emit(1, idx, 1))
            btn_plus.released.connect(self.jog_released.emit)

            layout.addWidget(row["widget"])

        layout.addStretch()
        return page

    def _build_cart_jog_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(5)

        self._cart_value_labels = []
        self._cart_minus_buttons = []
        self._cart_plus_buttons = []

        axis_names = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
        default_values = ["0 mm", "0 mm", "0 mm", "0 deg", "0 deg", "0 deg"]

        for i, axis in enumerate(axis_names):
            row = self._build_jog_row(
                minus_text=f"{axis}-",
                value_text=default_values[i],
                plus_text=f"{axis}+",
            )
            btn_minus = row["minus"]
            btn_plus = row["plus"]

            self._cart_minus_buttons.append(btn_minus)
            self._cart_plus_buttons.append(btn_plus)
            self._cart_value_labels.append(row["value"])

            btn_minus.pressed.connect(lambda idx=i: self.jog_pressed.emit(2, idx, -1))
            btn_minus.released.connect(self.jog_released.emit)
            btn_plus.pressed.connect(lambda idx=i: self.jog_pressed.emit(2, idx, 1))
            btn_plus.released.connect(self.jog_released.emit)

            layout.addWidget(row["widget"])

        layout.addStretch()
        return page

    def _build_jog_row(self, minus_text: str, value_text: str, plus_text: str) -> dict:
        row = QFrame()
        row.setObjectName("jogRow")
        row.setFixedHeight(31)
        row.setStyleSheet("""
            #jogRow {
                background-color: rgba(16, 23, 42, 130);
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(row)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(5)

        btn_minus = QPushButton(minus_text)
        btn_plus = QPushButton(plus_text)
        value = QLabel(value_text)

        btn_minus.setFixedSize(QSize(54, 25))
        btn_plus.setFixedSize(QSize(54, 25))

        btn_minus.setEnabled(False)
        btn_plus.setEnabled(False)

        btn_minus.setCursor(Qt.PointingHandCursor)
        btn_plus.setCursor(Qt.PointingHandCursor)

        value.setMinimumWidth(70)
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("""
            QLabel {
                color: #9fb7ff;
                font-size: 11px;
                background-color: transparent;
            }
        """)

        btn_minus.setStyleSheet(self._jog_button_style())
        btn_plus.setStyleSheet(self._jog_button_style())

        layout.addWidget(btn_minus)
        layout.addWidget(value, stretch=1)
        layout.addWidget(btn_plus)

        return {
            "widget": row,
            "minus": btn_minus,
            "value": value,
            "plus": btn_plus,
        }

    def _jog_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #24345c;
                color: #d8d8d8;
                border: 1px solid #33456f;
                border-radius: 12px;
                font-size: 11px;
                padding: 0px;
            }

            QPushButton:hover {
                background-color: #2f4373;
            }

            QPushButton:pressed {
                background-color: #1e2c4c;
            }

            QPushButton:disabled {
                background-color: #2a2a3e;
                color: #666666;
                border: 1px solid #333333;
            }
        """

    # ════════════════ 模式 / 速度 ════════════════

    def _on_mode_changed(self, mode_id: int):
        self._jog_stack.setCurrentIndex(mode_id)

    def _on_speed_value_changed(self, value: int):
        self._speed_label.setText(f"{value}%")

    def _emit_speed_rate_changed(self):
        val = self._speed_slider.value()
        QSettings("Codroid", "RobotUI").setValue("drawer/speed", val)
        self.speed_rate_changed.emit(val)

    def speed_rate(self) -> int:
        return self._speed_slider.value()

    def set_speed_rate(self, value: int):
        value = max(1, min(100, int(value)))
        self._speed_slider.setValue(value)
        self._speed_label.setText(f"{value}%")

    def set_jog_enabled(self, enabled: bool):
        """启用/禁用所有点动按钮、moveTo 按钮和速度条。"""
        for btn in (
            self._joint_minus_buttons
            + self._joint_plus_buttons
            + self._cart_minus_buttons
            + self._cart_plus_buttons
        ):
            btn.setEnabled(enabled)

        self._speed_slider.setEnabled(enabled)

        for btn in (
            self._btn_zero_point,
            self._btn_safe_point,
            self._btn_candle_point,
            self._btn_pack_point,
        ):
            btn.setEnabled(enabled)

    # ════════════════ 状态接口 ════════════════

    def is_expanded(self) -> bool:
        return self._expanded

    def collapsed_width(self) -> int:
        return self._collapsed_width

    def expanded_width(self) -> int:
        return self._expanded_width

    # ════════════════ 外部布局接口 ════════════════

    def set_parent_height(self, h: int):
        """兼容旧代码。只改高度，不强制移动 x/y。"""
        g = self.geometry()
        width = self._expanded_width if self._expanded else self._collapsed_width
        self.setGeometry(g.x(), g.y(), width, max(1, h))
        self.raise_()

    def show_trigger(self, x: int = 0, y: int = 0):
        """兼容旧 MainWindow 调用。"""
        self.show()
        self.raise_()

    def reposition(self):
        """兼容旧调用：仅校正宽度。"""
        target = self._expanded_width if self._expanded else self._collapsed_width
        self.set_drawer_width(target)

    # ════════════════ 展开 / 收起动画 ════════════════

    def _toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self._expanded:
            return

        self._expanded = True
        self._btn_toggle.setText("收起")
        self._content.setVisible(True)
        self._model_view.refresh()

        self._disconnect_anim_finished()
        self._anim.stop()
        self._anim.setStartValue(self._drawer_width)
        self._anim.setEndValue(self._expanded_width)
        self._anim.start()

    def collapse(self):
        if not self._expanded:
            return

        self._expanded = False
        self._btn_toggle.setText("运动")

        self._disconnect_anim_finished()
        self._anim.finished.connect(self._hide_content_after_collapse)
        self._hide_content_connected = True

        self._anim.stop()
        self._anim.setStartValue(self._drawer_width)
        self._anim.setEndValue(self._collapsed_width)
        self._anim.start()

    def _hide_content_after_collapse(self):
        if not self._expanded:
            self._content.setVisible(False)

        self._disconnect_anim_finished()

    def _disconnect_anim_finished(self):
        if not self._hide_content_connected:
            return

        try:
            self._anim.finished.disconnect(self._hide_content_after_collapse)
        except (TypeError, RuntimeError):
            pass

        self._hide_content_connected = False

    # ════════════════ 对外显示更新接口 ════════════════

    def set_robot_model(self, text: str, robot_type: str = ""):
        glb = resolve_glb_name(robot_type) if robot_type else ""
        if glb:
            self._model_label.setText(f"型号: {text} · {glb}")
        else:
            self._model_label.setText(f"型号: {text}")
        if robot_type:
            self.load_robot_model(robot_type)

    def load_robot_model(self, robot_type: str | None) -> None:
        """根据 RobotStatus.type 加载 models/ 下对应 GLB。"""
        self._model_view.load_robot_type(robot_type)

    def set_world_coordinate(self, text: str):
        self._world_coord_label.setText(f"世界坐标系：{text}")

    def set_tool_coordinate(self, text: str):
        self._tool_coord_label.setText(f"工具坐标系：{text}")

    def update_joint_display(
        self,
        joint_deg: list,
        joint_rad: list | None = None,
        *,
        drive_model: bool = True,
    ):
        for i, lbl in enumerate(self._joint_value_labels):
            if i < len(joint_deg):
                try:
                    lbl.setText(f"{float(joint_deg[i]):.1f} deg")
                except (TypeError, ValueError):
                    lbl.setText("-- deg")
        if drive_model and joint_rad:
            self._model_view.update_joint_angles(joint_rad)

    def update_tcp_display(self, x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg):
        try:
            x = float(x_mm)
            y = float(y_mm)
            z = float(z_mm)
            rx = float(rx_deg)
            ry = float(ry_deg)
            rz = float(rz_deg)

            cart_values = [
                f"{x:.1f} mm",
                f"{y:.1f} mm",
                f"{z:.1f} mm",
                f"{rx:.1f} deg",
                f"{ry:.1f} deg",
                f"{rz:.1f} deg",
            ]

            for i, lbl in enumerate(self._cart_value_labels):
                lbl.setText(cart_values[i])

        except (TypeError, ValueError):
            for lbl in self._cart_value_labels:
                lbl.setText("--")