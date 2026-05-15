"""焊接功能页 — 送气/送丝/退丝 + 文字输入 + 排版 + 工作空间标定 + 焊接参数 + 生成/预览/导出"""

import os
import sys
from core.types import RobotPoint
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QPushButton, QLineEdit, QComboBox,
    QDoubleSpinBox, QPlainTextEdit, QScrollArea,
    QWidget, QFrame, QLabel, QFileDialog,
)
from PySide6.QtCore import Qt, Signal
from app.base_page import BasePage
from app.i18n import tr
from config.welding_defaults import (
    CHAR_HEIGHT_MM, CHAR_SPACING_MM, LINE_SPACING_MM,
    LEAD_IN_MM, LEAD_OUT_MM, OVERLAP_MM, POINT_SPACING_MM,
)


def _open_file(path: str):
    """跨平台打开文件/目录。"""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        import subprocess; subprocess.run(["open", path])
    else:
        import subprocess; subprocess.run(["xdg-open", path])


def _find_system_fonts() -> list[str]:
    """列出系统可用字体路径。"""
    fonts = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        font_dir = os.path.join(windir, "Fonts")
        for name in ["arial.ttf", "msyh.ttf", "simhei.ttf", "simsun.ttc",
                     "cour.ttf", "times.ttf", "segui.ttf", "consola.ttf"]:
            p = os.path.join(font_dir, name)
            if os.path.exists(p):
                fonts.append(p)
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
        for p in candidates:
            if os.path.exists(p):
                fonts.append(p)
    return fonts


class WeldingPage(BasePage):
    """焊接功能页"""

    # 送气/送丝/退丝信号（连接到 main.py 的 send_call）
    gas_started = Signal(str)   # "gas" / "wire_feed" / "wire_retract"
    gas_stopped = Signal(str)

    # 生成请求
    generate_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._welding_service = None
        self._use_v2_service = True  # True=V2 (new pipeline), False=V1 (fallback)

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 8, 8, 8)  # 左侧 48px 预留给收起状态的运动抽屉
        root.setSpacing(6)

        # ── QScrollArea ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("weldingContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        # ── 1. GasWireControlBar ──
        gas_bar = QFrame()
        gas_bar.setObjectName("weldingGasWireBar")
        gas_row = QHBoxLayout(gas_bar)
        gas_row.setContentsMargins(0, 0, 0, 0)

        gas_label = QLabel(tr("weld_gas_on"))
        gas_label.setStyleSheet("font-weight: bold;")
        gas_row.addWidget(gas_label)
        gas_row.addStretch()

        from app.widgets.hold_button import HoldButton

        self._btn_gas = HoldButton(tr("weld_gas_on"))
        self._btn_gas.setFixedWidth(80)
        self._btn_gas.hold_started.connect(lambda: self.gas_started.emit("gas"))
        self._btn_gas.hold_stopped.connect(lambda: self.gas_stopped.emit("gas"))
        gas_row.addWidget(self._btn_gas)

        self._btn_wire_feed = HoldButton(tr("weld_wire_feed"))
        self._btn_wire_feed.setFixedWidth(80)
        self._btn_wire_feed.hold_started.connect(lambda: self.gas_started.emit("wire_feed"))
        self._btn_wire_feed.hold_stopped.connect(lambda: self.gas_stopped.emit("wire_feed"))
        gas_row.addWidget(self._btn_wire_feed)

        self._btn_wire_retract = HoldButton(tr("weld_wire_retract"))
        self._btn_wire_retract.setFixedWidth(80)
        self._btn_wire_retract.hold_started.connect(lambda: self.gas_started.emit("wire_retract"))
        self._btn_wire_retract.hold_stopped.connect(lambda: self.gas_stopped.emit("wire_retract"))
        gas_row.addWidget(self._btn_wire_retract)

        content_layout.addWidget(gas_bar)

        # ── 2. TextInputSection ──
        text_group = QGroupBox(tr("weld_text_input"))
        text_layout = QVBoxLayout(text_group)

        text_row = QHBoxLayout()
        text_row.addWidget(QLabel(tr("weld_text_input") + ":"))
        self._text_input = QLineEdit()
        self._text_input.setPlaceholderText("Abc123")
        self._text_input.setText("Abc123")
        text_row.addWidget(self._text_input)
        text_layout.addLayout(text_row)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel(tr("weld_font") + ":"))
        self._font_combo = QComboBox()
        for fp in _find_system_fonts():
            name = os.path.basename(fp)
            self._font_combo.addItem(name, fp)
        if self._font_combo.count() == 0:
            self._font_combo.addItem("(未找到字体)", "")
        font_row.addWidget(self._font_combo)
        font_row.addStretch()
        text_layout.addLayout(font_row)

        # Mode selector (contour / skeleton)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("weld_text_input") + " mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("contour (轮廓字)", "contour")
        self._mode_combo.addItem("skeleton (骨架字)", "skeleton")
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        text_layout.addLayout(mode_row)

        content_layout.addWidget(text_group)

        # ── 3. LayoutParamsSection ──
        layout_group = QGroupBox("Layout")
        layout_grid = QGridLayout(layout_group)

        self._spin_char_h = QDoubleSpinBox()
        self._spin_char_h.setRange(1, 500); self._spin_char_h.setValue(CHAR_HEIGHT_MM)
        self._spin_char_h.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("weld_char_height")), 0, 0)
        layout_grid.addWidget(self._spin_char_h, 0, 1)

        self._spin_char_s = QDoubleSpinBox()
        self._spin_char_s.setRange(0, 100); self._spin_char_s.setValue(CHAR_SPACING_MM)
        self._spin_char_s.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("weld_char_spacing")), 0, 2)
        layout_grid.addWidget(self._spin_char_s, 0, 3)

        self._spin_line_s = QDoubleSpinBox()
        self._spin_line_s.setRange(0, 200); self._spin_line_s.setValue(LINE_SPACING_MM)
        self._spin_line_s.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("weld_line_spacing")), 0, 4)
        layout_grid.addWidget(self._spin_line_s, 0, 5)

        layout_grid.addWidget(QLabel(tr("weld_direction")), 1, 0)
        self._combo_dir = QComboBox()
        self._combo_dir.addItems([tr("weld_horizontal"), tr("weld_vertical")])
        layout_grid.addWidget(self._combo_dir, 1, 1)

        layout_grid.addWidget(QLabel(tr("weld_align")), 1, 2)
        self._combo_align = QComboBox()
        self._combo_align.addItems([
            tr("weld_align_left"), tr("weld_align_center"), tr("weld_align_right")
        ])
        self._combo_align.setCurrentIndex(1)
        layout_grid.addWidget(self._combo_align, 1, 3)

        layout_grid.addWidget(QLabel(tr("weld_flow")), 1, 4)
        self._combo_flow = QComboBox()
        self._combo_flow.addItems([
            tr("weld_flow_ltr"), tr("weld_flow_rtl"), tr("weld_flow_ttb")
        ])
        layout_grid.addWidget(self._combo_flow, 1, 5)

        content_layout.addWidget(layout_group)

        # ── 4. WorkspaceCalibrationSection ──
        ws_group = QGroupBox(tr("weld_workspace"))
        ws_grid = QGridLayout(ws_group)

        headers = ["X mm", "Y mm", "Z mm", "Rx deg", "Ry deg", "Rz deg"]
        for j, h in enumerate(headers):
            ws_grid.addWidget(QLabel(h), 0, j + 1)

        point_labels = [
            tr("weld_ws_left_top"), tr("weld_ws_left_bot"), tr("weld_ws_right_bot")
        ]
        defaults_ws = [
            (100, 200, 300, 180, 0, 90),
            (100, 400, 300, 180, 0, 90),
            (300, 400, 300, 180, 0, 90),
        ]
        self._ws_spins: list[list[QDoubleSpinBox]] = []

        for i, (label, defs) in enumerate(zip(point_labels, defaults_ws)):
            ws_grid.addWidget(QLabel(label), i + 1, 0)
            row_spins = []
            for j, dv in enumerate(defs):
                spin = QDoubleSpinBox()
                spin.setRange(-9999, 9999)
                spin.setDecimals(3)
                spin.setValue(float(dv))
                spin.setMaximumWidth(90)
                ws_grid.addWidget(spin, i + 1, j + 1)
                row_spins.append(spin)
            self._ws_spins.append(row_spins)

            # 更新为当前位置按钮
            update_btn = QPushButton("更新坐标")
            update_btn.setFixedWidth(88)
            update_btn.setToolTip("更新为当前 TCP 位姿")
            update_btn.clicked.connect(lambda checked, row=i: self._update_ws_from_current(row))
            ws_grid.addWidget(update_btn, i + 1, 7)

        # Restore defaults button
        restore_btn = QPushButton(tr("weld_restore_btn"))
        restore_btn.clicked.connect(self._restore_ws_defaults)
        ws_grid.addWidget(restore_btn, 4, 0, 1, 8)

        content_layout.addWidget(ws_group)

        # ── 5. WeldParamsSection ──
        weld_group = QGroupBox(tr("weld_params"))
        weld_form = QFormLayout(weld_group)

        self._spin_lead_in = QDoubleSpinBox()
        self._spin_lead_in.setRange(0, 50); self._spin_lead_in.setValue(LEAD_IN_MM)
        self._spin_lead_in.setSuffix(" mm")
        weld_form.addRow(tr("weld_lead_in"), self._spin_lead_in)

        self._spin_lead_out = QDoubleSpinBox()
        self._spin_lead_out.setRange(0, 50); self._spin_lead_out.setValue(LEAD_OUT_MM)
        self._spin_lead_out.setSuffix(" mm")
        weld_form.addRow(tr("weld_lead_out"), self._spin_lead_out)

        self._spin_overlap = QDoubleSpinBox()
        self._spin_overlap.setRange(0, 20); self._spin_overlap.setValue(OVERLAP_MM)
        self._spin_overlap.setSuffix(" mm")
        weld_form.addRow(tr("weld_overlap"), self._spin_overlap)

        self._spin_pt_space = QDoubleSpinBox()
        self._spin_pt_space.setRange(0.1, 10); self._spin_pt_space.setValue(POINT_SPACING_MM)
        self._spin_pt_space.setSuffix(" mm")
        weld_form.addRow(tr("weld_point_space"), self._spin_pt_space)

        content_layout.addWidget(weld_group)

        # ── 6. ActionBar ──
        action_bar = QWidget()
        action_row = QHBoxLayout(action_bar)
        action_row.setContentsMargins(0, 0, 0, 0)

        self._btn_generate = QPushButton(tr("weld_gen_btn"))
        self._btn_generate.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2e86c1; }")
        self._btn_generate.clicked.connect(self._on_generate)
        action_row.addWidget(self._btn_generate)

        self._btn_preview = QPushButton(tr("weld_preview_btn"))
        self._btn_preview.clicked.connect(self._on_preview)
        action_row.addWidget(self._btn_preview)

        self._btn_export = QPushButton(tr("weld_export_btn"))
        self._btn_export.clicked.connect(self._on_export)
        action_row.addWidget(self._btn_export)

        action_row.addStretch()
        content_layout.addWidget(action_bar)

        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        # ── 7. Log output ──
        log_group = QGroupBox(tr("weld_log_title"))
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #80c080; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; }")
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

        self._last_txt_path = ""
        self._last_json_path = ""
        self._last_preview_path = ""

    def on_enter(self):
        self._ensure_service()

    def _ensure_service(self):
        if self._welding_service is not None:
            return
        if self.sp is None:
            return

        if self._use_v2_service:
            from services.welding_service_v2 import WeldingServiceV2
            self._welding_service = WeldingServiceV2(self, output_dir="output")
            self._welding_service.progress.connect(self._on_progress)
            self._welding_service.error_occurred.connect(self._on_service_error)
        else:
            from services.welding_service import WeldingService
            self._welding_service = WeldingService(self)

        self._welding_service.log_message.connect(self._append_log)
        self._welding_service.state_changed.connect(self._on_state_changed)
        self._welding_service.finished.connect(self._on_finished)
        self._welding_service.preview_ready.connect(self._on_preview_ready)

    def _append_log(self, msg: str):
        self._log.appendPlainText(msg)

    def _on_state_changed(self, state: str):
        self._btn_generate.setEnabled(state != "GENERATING")

    def _on_finished(self, txt_path: str, json_path: str):
        self._last_txt_path = txt_path
        self._last_json_path = json_path
        self._btn_export.setEnabled(True)
        self._btn_preview.setEnabled(True)

    def _read_workspace_calibration(self) -> dict:
        """从 UI 控件读取三点标定数据，推导第四角。

        返回 {left_top, right_top, left_bottom, right_bottom} 各为 RobotPoint。
        索引: row 0=left_top, 1=left_bottom, 2=right_bottom

        right_top 由 left_top + (right_bottom - left_bottom) 推导，
        确保 WorkPlane 的 U/V/N 正确 (N 指向 +Z 安全方向)。
        """
        def _rp(row):
            spins = self._ws_spins[row]
            return RobotPoint(
                x=spins[0].value(), y=spins[1].value(), z=spins[2].value(),
                rx=spins[3].value(), ry=spins[4].value(), rz=spins[5].value(),
            )
        lt = _rp(0)
        lb = _rp(1)
        rb = _rp(2)
        # 推导 right_top: 从 left_top 沿水平方向偏移 (right_bottom - left_bottom)
        rt = RobotPoint(
            x=lt.x + (rb.x - lb.x),
            y=lt.y + (rb.y - lb.y),
            z=lt.z + (rb.z - lb.z),
            rx=lt.rx, ry=lt.ry, rz=lt.rz,
        )
        return {
            "left_top": lt,
            "right_top": rt,
            "left_bottom": lb,
            "right_bottom": rb,
        }

    def _on_progress(self, current: int, total: int):
        pass  # 当前仅接收，UI 可后续加进度条

    def _on_service_error(self, msg: str):
        self._append_log(f"SERVICE ERROR: {msg}")

    def _on_preview_ready(self, png_path: str):
        self._last_preview_path = png_path

    def _collect_params(self) -> dict:
        font_idx = self._font_combo.currentIndex()
        font_path = self._font_combo.itemData(font_idx) if font_idx >= 0 else ""

        dir_map = {tr("weld_horizontal"): "horizontal", tr("weld_vertical"): "vertical"}
        align_map = {tr("weld_align_left"): "left", tr("weld_align_center"): "center",
                     tr("weld_align_right"): "right"}
        flow_map = {tr("weld_flow_ltr"): "left_to_right", tr("weld_flow_rtl"): "right_to_left",
                    tr("weld_flow_ttb"): "top_to_bottom"}

        return {
            "text": self._text_input.text(),
            "font_path": font_path or "",
            "char_height_mm": self._spin_char_h.value(),
            "char_spacing_mm": self._spin_char_s.value(),
            "line_spacing_mm": self._spin_line_s.value(),
            "direction": dir_map.get(self._combo_dir.currentText(), "horizontal"),
            "align": align_map.get(self._combo_align.currentText(), "center"),
            "flow": flow_map.get(self._combo_flow.currentText(), "left_to_right"),
            "lead_in_mm": self._spin_lead_in.value(),
            "lead_out_mm": self._spin_lead_out.value(),
            "overlap_mm": self._spin_overlap.value(),
            "point_spacing_mm": self._spin_pt_space.value(),
        }

    def _on_generate(self):
        if self._welding_service is None:
            self._append_log("ERROR: 服务未初始化 (未连接?)")
            return
        params = self._collect_params()
        if not params["text"]:
            self._append_log("ERROR: 请输入文字")
            return
        self._log.clear()
        self._btn_export.setEnabled(False)
        self._btn_preview.setEnabled(False)

        if self._use_v2_service:
            # V2: read workspace calibration from UI spin boxes
            mode = self._mode_combo.currentData()
            ws = self._read_workspace_calibration()
            self._welding_service.generate(
                text=params["text"],
                mode=mode,
                left_top=ws["left_top"],
                right_top=ws["right_top"],
                left_bottom=ws["left_bottom"],
                font_size_px=600,
                px_per_mm=10.0,
                char_spacing_mm=params["char_spacing_mm"],
            )
        else:
            self._welding_service.generate_weld_points(**params)

    def _on_preview(self):
        if self._last_preview_path and os.path.exists(self._last_preview_path):
            _open_file(self._last_preview_path)
        else:
            self._append_log("请先生成焊接点")

    def _on_export(self):
        if self._last_txt_path:
            dir_path = os.path.dirname(self._last_txt_path)
            _open_file(dir_path)
        else:
            self._append_log("请先生成焊接点")

    def _update_ws_from_current(self, row: int):
        """从 RobotRealtimeState 读取当前 TCP 位姿，填入工作空间第 row 行。"""
        from services.robot_realtime_state import RobotRealtimeState
        state = RobotRealtimeState.instance()
        if not state.is_valid():
            self._append_log("WARNING: CRI 无数据，无法获取当前位置")
            return
        x, y, z, rx, ry, rz = state.current_tcp_pose_mm_deg()
        self._ws_spins[row][0].setValue(round(x, 3))
        self._ws_spins[row][1].setValue(round(y, 3))
        self._ws_spins[row][2].setValue(round(z, 3))
        self._ws_spins[row][3].setValue(round(rx, 3))
        self._ws_spins[row][4].setValue(round(ry, 3))
        self._ws_spins[row][5].setValue(round(rz, 3))
        self._append_log(f"已更新 {['左上','左下','右下'][row]} 点位: "
                         f"({x:.1f}, {y:.1f}, {z:.1f}, {rx:.1f}, {ry:.1f}, {rz:.1f})")

    def _restore_ws_defaults(self):
        defaults = [
            (100, 200, 300, 180, 0, 90),
            (100, 400, 300, 180, 0, 90),
            (300, 400, 300, 180, 0, 90),
        ]
        for i, defs in enumerate(defaults):
            for j, dv in enumerate(defs):
                self._ws_spins[i][j].setValue(float(dv))
