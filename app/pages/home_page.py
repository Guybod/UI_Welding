from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.base_page import BasePage
from app.i18n import tr
from services.robot_realtime_state import RobotRealtimeState
from view3d.model_resolver import resolve_glb_name
from view3d.preview_frame import RobotPreviewFrame

_CARD_STYLE = """
    QGroupBox {
        color: #c8d4f0;
        font-size: 12px;
        font-weight: bold;
        border: 1px solid #2c3a64;
        border-radius: 8px;
        margin-top: 10px;
        padding: 10px 8px 8px 8px;
        background-color: rgba(17, 24, 45, 0.85);
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
    }
"""

_VALUE_STYLE = "color: #9fb7ff; font-size: 12px; font-family: Consolas, monospace;"
_LABEL_STYLE = "color: #7a8aaa; font-size: 11px;"
_SECTION_STYLE = "color: #6a7a9a; font-size: 10px; font-weight: bold;"
_COPY_BTN_STYLE = """
    QPushButton {
        background-color: #1e2a48;
        color: #a8c0ff;
        border: 1px solid #3a5088;
        border-radius: 5px;
        padding: 2px 10px;
        font-size: 11px;
    }
    QPushButton:hover { background-color: #2a3a62; color: #e0e8ff; }
    QPushButton:pressed { background-color: #162038; }
"""


def _status_chip(text: str, active: bool, warn: bool = False) -> QLabel:
    if warn:
        bg, fg = "#5c2a2a", "#ff8a8a"
    elif active:
        bg, fg = "#1e4a32", "#6dffb0"
    else:
        bg, fg = "#2a3148", "#8b95b0"
    chip = QLabel(text)
    chip.setStyleSheet(
        f"background-color: {bg}; color: {fg}; font-size: 11px;"
        "font-weight: bold; border-radius: 9px; padding: 3px 9px;"
    )
    return chip


class HomePage(BasePage):
    """首页 — 3D 预览 + 实时状态仪表盘。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._robot_type = ""
        self._connected = False
        self._mode_text = ""
        self._state_text = ""
        self._tcp_values: list[float | None] = [None] * 6
        self._joint_values: list[float | None] = [None] * 6

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(10)

        # ── 顶栏：标题 + 状态芯片 + 型号 ──
        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("首页")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e8eaf0;")
        header.addWidget(title)

        self._chip_conn = _status_chip("未连接", False)
        self._chip_cri = _status_chip("CRI", False)
        self._chip_enable = _status_chip("未使能", False)
        self._chip_estop = _status_chip("急停", False, warn=True)
        self._chip_motion = _status_chip("静止", False)
        self._chip_mode = _status_chip("—", False)

        for chip in (
            self._chip_conn,
            self._chip_cri,
            self._chip_enable,
            self._chip_estop,
            self._chip_motion,
            self._chip_mode,
        ):
            header.addWidget(chip)

        header.addStretch()
        self._model_label = QLabel("型号: 未连接")
        self._model_label.setStyleSheet("color: #8b9cc8; font-size: 12px;")
        header.addWidget(self._model_label)
        root.addLayout(header)

        # ── 主体：3D + 右侧信息 ──
        body = QHBoxLayout()
        body.setSpacing(12)

        self._preview = RobotPreviewFrame(self, min_height=320)
        body.addWidget(self._preview, stretch=3)

        side = QVBoxLayout()
        side.setSpacing(8)

        pose_box = QGroupBox("位姿数据")
        pose_box.setStyleSheet(_CARD_STYLE)
        pose_layout = QVBoxLayout(pose_box)
        pose_layout.setContentsMargins(8, 14, 8, 8)
        pose_layout.setSpacing(6)

        copy_row = QHBoxLayout()
        copy_row.setSpacing(6)
        self._btn_copy_tcp = QPushButton("复制 TCP")
        self._btn_copy_joint = QPushButton("复制关节")
        for btn in (self._btn_copy_tcp, self._btn_copy_joint):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setStyleSheet(_COPY_BTN_STYLE)
        self._btn_copy_tcp.clicked.connect(self._copy_tcp)
        self._btn_copy_joint.clicked.connect(self._copy_joint)
        copy_row.addWidget(self._btn_copy_tcp)
        copy_row.addWidget(self._btn_copy_joint)
        copy_row.addStretch()
        pose_layout.addLayout(copy_row)

        self._copy_hint = QLabel("")
        self._copy_hint.setStyleSheet("color: #6dffb0; font-size: 10px;")
        self._copy_hint.setVisible(False)
        pose_layout.addWidget(self._copy_hint)

        tcp_hdr = QHBoxLayout()
        tcp_title = QLabel("末端 TCP")
        tcp_title.setStyleSheet(_SECTION_STYLE)
        tcp_unit = QLabel("位置 mm · 姿态 deg")
        tcp_unit.setStyleSheet(_LABEL_STYLE)
        tcp_hdr.addWidget(tcp_title)
        tcp_hdr.addStretch()
        tcp_hdr.addWidget(tcp_unit)
        pose_layout.addLayout(tcp_hdr)

        tcp_block = QWidget()
        tcp_grid = QGridLayout(tcp_block)
        tcp_grid.setContentsMargins(0, 0, 0, 0)
        tcp_grid.setHorizontalSpacing(8)
        tcp_grid.setVerticalSpacing(2)

        self._tcp_labels: dict[str, QLabel] = {}
        for col, key in enumerate(("X", "Y", "Z")):
            name = QLabel(key)
            name.setStyleSheet(_LABEL_STYLE)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(_VALUE_STYLE)
            tcp_grid.addWidget(name, 0, col)
            tcp_grid.addWidget(val, 1, col)
            self._tcp_labels[key] = val
        for col, key in enumerate(("Rx", "Ry", "Rz")):
            name = QLabel(key)
            name.setStyleSheet(_LABEL_STYLE)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(_VALUE_STYLE)
            tcp_grid.addWidget(name, 2, col)
            tcp_grid.addWidget(val, 3, col)
            self._tcp_labels[key] = val
        pose_layout.addWidget(tcp_block)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2c3a64;")
        pose_layout.addWidget(sep)

        joint_hdr = QHBoxLayout()
        joint_title = QLabel("关节角")
        joint_title.setStyleSheet(_SECTION_STYLE)
        joint_unit = QLabel("deg")
        joint_unit.setStyleSheet(_LABEL_STYLE)
        joint_hdr.addWidget(joint_title)
        joint_hdr.addStretch()
        joint_hdr.addWidget(joint_unit)
        pose_layout.addLayout(joint_hdr)

        joint_block = QWidget()
        joint_grid = QGridLayout(joint_block)
        joint_grid.setContentsMargins(0, 0, 0, 0)
        joint_grid.setHorizontalSpacing(6)
        joint_grid.setVerticalSpacing(3)
        self._joint_labels: list[QLabel] = []
        for i in range(6):
            name = QLabel(f"J{i + 1}")
            name.setStyleSheet(_LABEL_STYLE)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val = QLabel("--")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val.setStyleSheet(_VALUE_STYLE)
            joint_grid.addWidget(name, (i // 3) * 2, i % 3)
            joint_grid.addWidget(val, (i // 3) * 2 + 1, i % 3)
            self._joint_labels.append(val)
        pose_layout.addWidget(joint_block)
        side.addWidget(pose_box)

        coord_box = QFrame()
        coord_box.setStyleSheet(
            "background-color: rgba(17, 24, 45, 0.85);"
            "border: 1px solid #2c3a64; border-radius: 8px;"
        )
        coord_layout = QVBoxLayout(coord_box)
        coord_layout.setContentsMargins(10, 8, 10, 8)
        coord_layout.setSpacing(4)
        self._world_coord_label = QLabel("世界坐标系：—")
        self._tool_coord_label = QLabel("工具坐标系：—")
        for lbl in (self._world_coord_label, self._tool_coord_label):
            lbl.setStyleSheet("color: #b8c4e0; font-size: 11px;")
            coord_layout.addWidget(lbl)
        side.addWidget(coord_box)
        side.addStretch()
        body.addLayout(side, stretch=1)
        root.addLayout(body, stretch=1)

        # ── 底栏 ──
        footer = QHBoxLayout()
        hint = QLabel("左键旋转 · 右键平移 · 滚轮缩放")
        hint.setStyleSheet("color: #6a7a9a; font-size: 12px;")
        footer.addWidget(hint)
        footer.addStretch()
        self._glb_hint = QLabel("")
        self._glb_hint.setStyleSheet("color: #5f6f99; font-size: 11px;")
        footer.addWidget(self._glb_hint)
        self._btn_reset_view = QPushButton("复位视角")
        self._btn_reset_view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset_view.setFixedHeight(28)
        self._btn_reset_view.setStyleSheet("""
            QPushButton {
                background-color: #24345c;
                color: #e0e8ff;
                border: 1px solid #3a5088;
                border-radius: 6px;
                padding: 0 14px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #2f4373; }
            QPushButton:pressed { background-color: #1e2c4c; }
        """)
        self._btn_reset_view.clicked.connect(self._preview.reset_camera_view)
        footer.addWidget(self._btn_reset_view)
        root.addLayout(footer)

        self._preview.load_default_preview()
        self._glb_hint.setText(self._preview.loaded_glb_name())

    def on_enter(self):
        if not self._preview.loaded_glb_name():
            self._preview.load_default_preview()
        self._glb_hint.setText(self._preview.loaded_glb_name())
        self._preview.refresh()
        rt = RobotRealtimeState.instance()
        if rt.has_pose():
            from services.robot_realtime_state import PoseSource
            self.update_cri_ui_mode(
                "udp" if rt.pose_source() == PoseSource.CRI_UDP else "subscribe"
            )
            self.update_runtime_flags(
                enabled=rt.is_enabled(),
                moving=rt.is_moving(),
                emergency=rt.is_emergency_stop(),
            )
            tcp = rt.current_tcp_pose_mm_deg()
            self.update_tcp_display(*tcp)
            self.update_joint_display(
                rt.current_joints_deg(),
                joint_rad=rt.current_joint_rad(),
                drive_model=True,
            )
        if self._mode_text or self._state_text:
            self.update_mode_state(self._mode_text, self._state_text)

    def set_robot_model(self, text: str, robot_type: str = "") -> None:
        robot_type = robot_type or ""
        self._robot_type = robot_type
        glb = resolve_glb_name(robot_type) if robot_type else ""
        if glb:
            self._model_label.setText(f"型号: {text}")
            self._glb_hint.setText(glb)
        else:
            self._model_label.setText(f"型号: {text}" if text else "型号: 未连接")
            self._glb_hint.setText(self._preview.loaded_glb_name())
        if robot_type:
            self._preview.load_robot_type(robot_type)
        elif not self._preview.loaded_glb_name():
            self._preview.load_default_preview()

    def update_connection(self, connected: bool) -> None:
        self._connected = connected
        self._apply_chip(self._chip_conn, "已连接" if connected else "未连接", connected)

    def update_cri_status(self, active: bool) -> None:
        """兼容旧调用；True 等同 CRI UDP 权威。"""
        self.update_cri_ui_mode("udp" if active else "off")

    def update_cri_ui_mode(self, mode: str) -> None:
        """CRI 位姿 UI：off | pending | udp | subscribe | bind_fail。"""
        if mode == "udp":
            self._apply_chip(self._chip_cri, "CRI", True)
        elif mode == "subscribe":
            self._apply_chip(
                self._chip_cri, tr("chip_pose_subscribe"), False, caution=True
            )
        elif mode == "pending":
            self._apply_chip(self._chip_cri, "CRI…", False)
        elif mode == "bind_fail":
            self._apply_chip(self._chip_cri, "CRI绑定失败", False, warn=True)
        else:
            self._apply_chip(self._chip_cri, "CRI关", False)

    def update_runtime_flags(
        self,
        *,
        enabled: bool | None = None,
        moving: bool | None = None,
        emergency: bool | None = None,
    ) -> None:
        if enabled is not None:
            self._apply_chip(
                self._chip_enable, "已使能" if enabled else "未使能", enabled
            )
        if emergency is not None:
            active = not emergency
            self._apply_chip(
                self._chip_estop,
                "急停" if emergency else "正常",
                active,
                warn=emergency,
            )
        if moving is not None:
            self._apply_chip(
                self._chip_motion, "运动中" if moving else "静止", moving
            )

    def update_mode_state(self, mode_text: str, state_text: str) -> None:
        if mode_text:
            self._mode_text = mode_text
        if state_text:
            self._state_text = state_text
        text = (
            f"{self._mode_text} · {self._state_text}"
            if self._mode_text and self._state_text
            else (self._mode_text or self._state_text or "—")
        )
        self._apply_chip(self._chip_mode, text, bool(self._mode_text))

    def update_coordinates(self, world_text: str, tool_text: str) -> None:
        self._world_coord_label.setText(f"世界坐标系：{world_text}")
        self._tool_coord_label.setText(f"工具坐标系：{tool_text}")

    def update_tcp_display(
        self, x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg
    ) -> None:
        values = (x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg)
        keys = ("X", "Y", "Z", "Rx", "Ry", "Rz")
        parsed: list[float | None] = []
        for key, raw in zip(keys, values):
            try:
                num = float(raw)
                parsed.append(num)
                self._tcp_labels[key].setText(f"{num:.2f}")
            except (TypeError, ValueError):
                parsed.append(None)
                self._tcp_labels[key].setText("--")
        self._tcp_values = parsed

    def update_joint_display(
        self,
        joint_deg: list,
        joint_rad: list | None = None,
        *,
        drive_model: bool = True,
    ) -> None:
        parsed: list[float | None] = []
        for i, lbl in enumerate(self._joint_labels):
            if i < len(joint_deg):
                try:
                    num = float(joint_deg[i])
                    parsed.append(num)
                    lbl.setText(f"{num:.2f}")
                except (TypeError, ValueError):
                    parsed.append(None)
                    lbl.setText("--")
            else:
                parsed.append(None)
                lbl.setText("--")
        while len(parsed) < 6:
            parsed.append(None)
        self._joint_values = parsed
        if drive_model and joint_rad:
            self._preview.update_joint_angles(joint_rad)

    def _copy_tcp(self) -> None:
        text = self._format_tcp_clipboard()
        if not text:
            self._show_copy_hint("暂无有效 TCP 数据", ok=False)
            return
        QGuiApplication.clipboard().setText(text)
        self._show_copy_hint("已复制 TCP")

    def _copy_joint(self) -> None:
        text = self._format_joint_clipboard()
        if not text:
            self._show_copy_hint("暂无有效关节数据", ok=False)
            return
        QGuiApplication.clipboard().setText(text)
        self._show_copy_hint("已复制关节角")

    def _format_tcp_clipboard(self) -> str:
        if len(self._tcp_values) < 6 or any(v is None for v in self._tcp_values):
            return ""
        x, y, z, rx, ry, rz = self._tcp_values
        return f"[{x:.3f},{y:.3f},{z:.3f},{rx:.3f},{ry:.3f},{rz:.3f}]"

    def _format_joint_clipboard(self) -> str:
        if len(self._joint_values) < 6 or any(v is None for v in self._joint_values):
            return ""
        vals = ", ".join(f"{v:.3f}" for v in self._joint_values)
        return f"[{vals}]"

    def _show_copy_hint(self, message: str, *, ok: bool = True) -> None:
        self._copy_hint.setText(message)
        self._copy_hint.setStyleSheet(
            f"color: {'#6dffb0' if ok else '#ff9a9a'}; font-size: 10px;"
        )
        self._copy_hint.setVisible(True)
        QTimer.singleShot(2000, self._copy_hint.hide)

    @staticmethod
    def _apply_chip(
        chip: QLabel,
        text: str,
        active: bool,
        *,
        warn: bool = False,
        caution: bool = False,
    ) -> None:
        chip.setText(text)
        if warn:
            bg, fg = "#5c2a2a", "#ff8a8a"
        elif caution:
            bg, fg = "#4a3a18", "#ffcc66"
        elif active:
            bg, fg = "#1e4a32", "#6dffb0"
        else:
            bg, fg = "#2a3148", "#8b95b0"
        chip.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-size: 11px;"
            "font-weight: bold; border-radius: 9px; padding: 3px 9px;"
        )
