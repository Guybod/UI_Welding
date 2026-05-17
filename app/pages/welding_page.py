"""焊接功能页 — 送气/送丝/退丝 + 文字输入 + 排版 + 工作空间标定 + 焊接参数 + 生成/预览/导出"""

import logging
import math
import os
import sys
import time
from datetime import datetime

from core.types import RobotPoint
from core.platform_utils import open_path as _open_path
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QGroupBox, QPushButton, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QAbstractSpinBox,
    QPlainTextEdit, QScrollArea, QApplication,
    QWidget, QFrame, QLabel, QFileDialog,
)
from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from app.base_page import BasePage
from app.i18n import tr, I18nManager
from app.widgets.hold_button import HoldButton
from config.welding_defaults import (
    CHAR_HEIGHT_MM, CHAR_SPACING_MM, LINE_SPACING_MM, MARGIN_LEFT_MM, MARGIN_TOP_MM,
    LEAD_IN_MM, LEAD_OUT_MM, OVERLAP_MM, POINT_SPACING_MM,
)

_sys_log = logging.getLogger("codroid")

# 正式主线默认（Beta 检测用；与 pipeline 当前行为一致）
_BETA_DEFAULT_ALIGN = "center"
_BETA_DEFAULT_DIRECTION = "horizontal"
_BETA_DEFAULT_FLOW = "ltr"

_WELD_CORNER_KEYS = ("weld_log_corner_lt", "weld_log_corner_rt", "weld_log_corner_lb")
_WELD_CORNER_CODES = ("LT", "RT", "LB")
# welder/sendparams — Welder/command: 1送丝 2退丝 3送气 0停止（planAPI §23）
_WELDER_KIND_TO_CMD = {"wire_feed": 1, "wire_retract": 2, "gas": 3}
_WELDER_KIND_I18N = {
    "wire_feed": "weld_wire_feed",
    "wire_retract": "weld_wire_retract",
    "gas": "weld_gas_on",
}


def _weld_corner_label(row: int) -> str:
    if 0 <= row < len(_WELD_CORNER_KEYS):
        return tr(_WELD_CORNER_KEYS[row])
    return "?"
_LEGACY_FLOW_TO_DATA = {
    "left_to_right": "ltr",
    "right_to_left": "rtl",
    "top_to_bottom": "ttb",
}
_LEGACY_ALIGN_INDEX = ("left", "center", "right")


def normalize_weld_text_input(raw: str) -> str:
    """焊接文字：统一为真实换行；兼容单行框误输入的字面量 \\n / \\r\\n。"""
    if not raw:
        return ""
    if "\n" in raw or "\r" in raw:
        return raw.replace("\r\n", "\n").replace("\r", "\n")
    if "\\n" in raw or "\\r" in raw:
        return raw.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    return raw


def detect_beta_features(
    *,
    mode: str,
    text: str,
    line_spacing_mm: float,
    align: str,
    direction: str,
    flow: str,
    line_spacing_default: float = LINE_SPACING_MM,
) -> list[str]:
    """检测当前是否使用 Beta 排版/模式（纯函数，可供测试）。"""
    beta: list[str] = []
    if mode == "skeleton":
        beta.append("骨架字")
    has_multiline = "\n" in text or "\r" in text
    if has_multiline and mode == "skeleton":
        beta.append("多行文字")
    if abs(line_spacing_mm - line_spacing_default) > 0.01:
        if mode == "skeleton" or (has_multiline and mode != "contour"):
            beta.append("行距")
        # contour 多行：行距为正式参数，不标 Beta
    if align != _BETA_DEFAULT_ALIGN:
        beta.append("对齐模式")
    if direction != _BETA_DEFAULT_DIRECTION:
        beta.append("排版方向")
    flow_key = _LEGACY_FLOW_TO_DATA.get(flow, flow)
    if flow_key != _BETA_DEFAULT_FLOW:
        beta.append("流向")
    return beta


def _normalize_flow_setting(value) -> str:
    """QSettings 中 flow 可能是旧值 left_to_right 或新值 ltr。"""
    if value is None:
        return _BETA_DEFAULT_FLOW
    s = str(value)
    return _LEGACY_FLOW_TO_DATA.get(s, s)


def _normalize_align_setting(value) -> str:
    if value is None:
        return _BETA_DEFAULT_ALIGN
    if isinstance(value, (int, float)) or (isinstance(value, str) and str(value).isdigit()):
        idx = int(value)
        return _LEGACY_ALIGN_INDEX[max(0, min(2, idx))]
    return str(value)


def _combo_current_data(combo: QComboBox, default: str) -> str:
    idx = combo.currentIndex()
    if idx < 0:
        return default
    data = combo.itemData(idx)
    return data if data is not None else default


def _qsettings_bool(val, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return default


def _qsettings_float(val, default: float) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _qsettings_int(val, default: int) -> int:
    if val is None:
        return default
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _find_system_fonts() -> list:
    """列出系统可用字体路径。"""
    fonts = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        font_dir = os.path.join(windir, "Fonts")
        font_names = [
            # 中文字体
            "msyh.ttf", "msyh.ttc", "simhei.ttf",
            "simsun.ttc", "simsun.ttf",
            "kaiti.ttf",
            "fangsong.ttf", "fangsong.ttc",
            "nsimsun.ttf", "nsimsun.ttc",
            "msjh.ttf", "msjh.ttc",
            # 英文字体
            "arial.ttf", "cour.ttf", "times.ttf", "segui.ttf", "consola.ttf",
        ]
        for name in font_names:
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


# 字体显示名映射（key 为小写文件名）
_FONT_DISPLAY_NAMES: dict[str, str] = {
    "msyh.ttf":  "微软雅黑 (Microsoft YaHei)",
    "msyh.ttc":  "微软雅黑 (Microsoft YaHei)",
    "simhei.ttf": "黑体 (SimHei)",
    "simsun.ttc": "宋体 (SimSun)",
    "simsun.ttf": "宋体 (SimSun)",
    "kaiti.ttf":  "楷体 (KaiTi)",
    "fangsong.ttf": "仿宋 (FangSong)",
    "fangsong.ttc": "仿宋 (FangSong)",
    "nsimsun.ttf": "新宋体 (NSimSun)",
    "nsimsun.ttc": "新宋体 (NSimSun)",
    "msjh.ttf":   "微软正黑体 (Microsoft JhengHei)",
    "msjh.ttc":   "微软正黑体 (Microsoft JhengHei)",
    "arial.ttf":  "Arial",
    "cour.ttf":   "Courier New",
    "times.ttf":  "Times New Roman",
    "segui.ttf":  "Segoe UI",
    "consola.ttf": "Consolas",
}


def _get_font_display_name(filepath: str) -> str:
    """返回字体文件的人类可读显示名。未知字体返回文件名去扩展名。"""
    basename = os.path.basename(filepath).lower()
    if basename in _FONT_DISPLAY_NAMES:
        return _FONT_DISPLAY_NAMES[basename]
    return os.path.splitext(os.path.basename(filepath))[0]


def _get_font_family(filepath: str) -> str:
    """从文件路径提取字体族名。从显示名括号中解析，未知字体 fallback 到文件名去扩展名。"""
    display = _get_font_display_name(filepath)
    if "(" in display and ")" in display:
        start = display.index("(") + 1
        end = display.index(")", start)
        return display[start:end]
    return display


def _build_font_item_data(filepath: str) -> dict:
    return {
        "path": filepath,
        "family": _get_font_family(filepath),
        "display": _get_font_display_name(filepath),
    }


class WeldingPage(BasePage):
    """焊接功能页"""

    # 生成请求
    generate_requested = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._welding_service = None
        self._moveto_active_row: int | None = None
        self._moveto_heartbeat: QTimer | None = None
        self._welder_active_kind: str | None = None
        self._welder_heartbeat: QTimer | None = None

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

        self._btn_gas = HoldButton(tr("weld_gas_on"))
        self._btn_gas.setFixedWidth(80)
        self._btn_gas.hold_started.connect(lambda: self._on_welder_hold_started("gas"))
        self._btn_gas.hold_stopped.connect(lambda: self._on_welder_hold_stopped("gas"))
        gas_row.addWidget(self._btn_gas)

        self._btn_wire_feed = HoldButton(tr("weld_wire_feed"))
        self._btn_wire_feed.setFixedWidth(80)
        self._btn_wire_feed.hold_started.connect(
            lambda: self._on_welder_hold_started("wire_feed"))
        self._btn_wire_feed.hold_stopped.connect(
            lambda: self._on_welder_hold_stopped("wire_feed"))
        gas_row.addWidget(self._btn_wire_feed)

        self._btn_wire_retract = HoldButton(tr("weld_wire_retract"))
        self._btn_wire_retract.setFixedWidth(80)
        self._btn_wire_retract.hold_started.connect(
            lambda: self._on_welder_hold_started("wire_retract"))
        self._btn_wire_retract.hold_stopped.connect(
            lambda: self._on_welder_hold_stopped("wire_retract"))
        gas_row.addWidget(self._btn_wire_retract)

        content_layout.addWidget(gas_bar)

        # ── 2. TextInputSection ──
        text_group = QGroupBox(tr("weld_text_input"))
        text_layout = QVBoxLayout(text_group)

        text_layout.addWidget(QLabel(tr("weld_text_input") + ":"))
        self._text_input = QPlainTextEdit()
        self._text_input.setPlaceholderText(tr("weld_text_placeholder"))
        self._text_input.setToolTip(tr("weld_text_tip"))
        self._text_input.setPlainText("Abc123")
        self._text_input.setFixedHeight(72)
        self._text_input.setTabChangesFocus(True)
        text_layout.addWidget(self._text_input)

        font_row = QHBoxLayout()
        font_row.addWidget(QLabel(tr("weld_font") + ":"))
        self._font_combo = QComboBox()
        for fp in _find_system_fonts():
            data = _build_font_item_data(fp)
            self._font_combo.addItem(data["display"], data)
        if self._font_combo.count() == 0:
            self._font_combo.addItem("(未找到字体)", {
                "path": "", "family": "", "display": "(未找到字体)",
            })
        font_row.addWidget(self._font_combo)
        font_row.addStretch()
        text_layout.addLayout(font_row)

        # Mode selector (contour / skeleton)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("weld_mode") + ":"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem(tr("weld_mode_contour"), "contour")
        self._mode_combo.addItem(tr("weld_mode_skeleton_beta"), "skeleton")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        text_layout.addLayout(mode_row)

        content_layout.addWidget(text_group)

        # ── 3. LayoutParamsSection ──
        layout_group = QGroupBox(tr("weld_layout_group"))
        layout_grid = QGridLayout(layout_group)

        self._spin_char_h = QDoubleSpinBox()
        self._spin_char_h.setRange(1, 500); self._spin_char_h.setValue(CHAR_HEIGHT_MM)
        self._spin_char_h.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("weld_char_height")), 0, 0)
        layout_grid.addWidget(self._spin_char_h, 0, 1)

        self._spin_margin_left = QDoubleSpinBox()
        self._spin_margin_left.setRange(0, 500)
        self._spin_margin_left.setValue(MARGIN_LEFT_MM)
        self._spin_margin_left.setSuffix(" mm")
        self._spin_margin_left.setToolTip(tr("weld_margin_left_tip"))
        lbl_margin_l = QLabel(tr("weld_margin_left"))
        lbl_margin_l.setToolTip(tr("weld_margin_left_tip"))
        layout_grid.addWidget(lbl_margin_l, 0, 2)
        layout_grid.addWidget(self._spin_margin_left, 0, 3)

        self._spin_margin_top = QDoubleSpinBox()
        self._spin_margin_top.setRange(0, 500)
        self._spin_margin_top.setValue(MARGIN_TOP_MM)
        self._spin_margin_top.setSuffix(" mm")
        self._spin_margin_top.setToolTip(tr("weld_margin_top_tip"))
        lbl_margin_t = QLabel(tr("weld_margin_top"))
        lbl_margin_t.setToolTip(tr("weld_margin_top_tip"))
        layout_grid.addWidget(lbl_margin_t, 0, 4)
        layout_grid.addWidget(self._spin_margin_top, 0, 5)

        self._spin_char_s = QDoubleSpinBox()
        self._spin_char_s.setRange(0, 100); self._spin_char_s.setValue(CHAR_SPACING_MM)
        self._spin_char_s.setSuffix(" mm")
        self._spin_char_s.setToolTip(tr("weld_char_spacing_tip"))
        lbl_char_s = QLabel(tr("weld_char_spacing"))
        lbl_char_s.setToolTip(tr("weld_char_spacing_tip"))
        layout_grid.addWidget(lbl_char_s, 1, 0)
        layout_grid.addWidget(self._spin_char_s, 1, 1)

        self._spin_line_s = QDoubleSpinBox()
        self._spin_line_s.setRange(0, 200); self._spin_line_s.setValue(LINE_SPACING_MM)
        self._spin_line_s.setSuffix(" mm")
        self._spin_line_s.setToolTip(tr("weld_line_spacing_tip"))
        lbl_line_s = QLabel(tr("weld_line_spacing"))
        lbl_line_s.setToolTip(tr("weld_line_spacing_tip"))
        layout_grid.addWidget(lbl_line_s, 1, 2)
        layout_grid.addWidget(self._spin_line_s, 1, 3)

        layout_grid.addWidget(QLabel(tr("weld_direction")), 2, 0)
        self._combo_dir = QComboBox()
        self._combo_dir.addItem(f"{tr('weld_horizontal')} [Beta]", "horizontal")
        self._combo_dir.addItem(f"{tr('weld_vertical')} [Beta]", "vertical")
        layout_grid.addWidget(self._combo_dir, 2, 1)

        layout_grid.addWidget(QLabel(tr("weld_align")), 2, 2)
        self._combo_align = QComboBox()
        self._combo_align.addItem(f"{tr('weld_align_left')}对齐 [Beta]", "left")
        self._combo_align.addItem(f"{tr('weld_align_center')}对齐 [Beta]", "center")
        self._combo_align.addItem(f"{tr('weld_align_right')}对齐 [Beta]", "right")
        self._combo_align.setCurrentIndex(1)
        layout_grid.addWidget(self._combo_align, 2, 3)

        layout_grid.addWidget(QLabel(tr("weld_flow")), 2, 4)
        self._combo_flow = QComboBox()
        self._combo_flow.addItem(f"{tr('weld_flow_ltr')} [Beta]", "ltr")
        self._combo_flow.addItem(f"{tr('weld_flow_rtl')} [Beta]", "rtl")
        self._combo_flow.addItem(f"{tr('weld_flow_ttb')} [Beta]", "ttb")
        layout_grid.addWidget(self._combo_flow, 2, 5)

        content_layout.addWidget(layout_group)

        # ── 4. WorkspaceCalibrationSection ──
        ws_group = QGroupBox(tr("weld_workspace"))
        ws_grid = QGridLayout(ws_group)

        headers = ["X mm", "Y mm", "Z mm", "Rx deg", "Ry deg", "Rz deg"]
        for j, h in enumerate(headers):
            ws_grid.addWidget(QLabel(h), 0, j + 1)

        point_labels = [
            tr("weld_ws_left_top"), tr("weld_ws_right_top"), tr("weld_ws_left_bot"),
        ]
        defaults_ws = [
            (100, 200, 300, 180, 0, 90),   # LT: 左上
            (300, 200, 300, 180, 0, 90),   # RT: 右上
            (100, 400, 300, 180, 0, 90),   # LB: 左下
        ]
        self._ws_spins: list[list[QDoubleSpinBox]] = []

        for i, (label, defs) in enumerate(zip(point_labels, defaults_ws)):
            ws_grid.addWidget(QLabel(label), i + 1, 0)
            row_spins = []
            for j, dv in enumerate(defs):
                spin = QDoubleSpinBox()
                spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
                spin.setRange(-9999, 9999)
                spin.setDecimals(3)
                spin.setValue(float(dv))
                spin.setMaximumWidth(90)
                ws_grid.addWidget(spin, i + 1, j + 1)
                row_spins.append(spin)
            self._ws_spins.append(row_spins)

            update_btn = QPushButton(tr("weld_ws_update"))
            update_btn.setFixedWidth(64)
            update_btn.setToolTip(tr("weld_ws_update_tip"))
            update_btn.clicked.connect(lambda checked, row=i: self._update_ws_from_current(row))
            ws_grid.addWidget(update_btn, i + 1, 7)

            moveto_btn = QPushButton(tr("weld_ws_moveto"))
            moveto_btn.setFixedWidth(72)
            moveto_btn.setToolTip(tr("weld_ws_moveto_tip"))
            moveto_btn.pressed.connect(lambda row=i: self._on_moveto_pressed(row))
            moveto_btn.released.connect(lambda row=i: self._on_moveto_released(row))
            ws_grid.addWidget(moveto_btn, i + 1, 8)

            copy_btn = QPushButton(tr("weld_ws_copy"))
            copy_btn.setFixedWidth(56)
            copy_btn.setToolTip(tr("weld_ws_copy_tip"))
            copy_btn.clicked.connect(lambda checked, row=i: self._copy_ws_point(row))
            ws_grid.addWidget(copy_btn, i + 1, 9)

        # Restore defaults button
        restore_btn = QPushButton(tr("weld_restore_btn"))
        restore_btn.clicked.connect(self._restore_ws_defaults)
        ws_grid.addWidget(restore_btn, 4, 0, 1, 10)

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
        self._spin_pt_space.setDecimals(2)
        weld_form.addRow(tr("weld_point_space"), self._spin_pt_space)

        content_layout.addWidget(weld_group)

        # ── 5b. ProcessParamsSection ──
        proc_group = QGroupBox(tr("weld_process_params"))
        proc_grid = QGridLayout(proc_group)

        self._spin_voltage = QDoubleSpinBox()
        self._spin_voltage.setRange(0, 100); self._spin_voltage.setValue(24.0)
        self._spin_voltage.setSuffix(" V"); self._spin_voltage.setDecimals(1)
        proc_grid.addWidget(QLabel(tr("weld_voltage")), 0, 0)
        proc_grid.addWidget(self._spin_voltage, 0, 1)

        self._spin_current = QDoubleSpinBox()
        self._spin_current.setRange(0, 500); self._spin_current.setValue(150.0)
        self._spin_current.setSuffix(" A"); self._spin_current.setDecimals(1)
        proc_grid.addWidget(QLabel(tr("weld_current")), 1, 0)
        proc_grid.addWidget(self._spin_current, 1, 1)

        self._spin_weld_speed = QDoubleSpinBox()
        self._spin_weld_speed.setRange(0.1, 1000); self._spin_weld_speed.setValue(30.0)
        self._spin_weld_speed.setSuffix(" mm/s"); self._spin_weld_speed.setDecimals(1)
        proc_grid.addWidget(QLabel(tr("weld_weld_speed")), 0, 2)
        proc_grid.addWidget(self._spin_weld_speed, 0, 3)

        self._spin_travel_speed = QDoubleSpinBox()
        self._spin_travel_speed.setRange(0.1, 2000); self._spin_travel_speed.setValue(80.0)
        self._spin_travel_speed.setSuffix(" mm/s"); self._spin_travel_speed.setDecimals(1)
        proc_grid.addWidget(QLabel(tr("weld_travel_speed")), 1, 2)
        proc_grid.addWidget(self._spin_travel_speed, 1, 3)

        self._spin_job = QSpinBox()
        self._spin_job.setRange(0, 999); self._spin_job.setValue(0)
        proc_grid.addWidget(QLabel(tr("weld_job")), 2, 0)
        proc_grid.addWidget(self._spin_job, 2, 1)

        self._spin_inductance = QDoubleSpinBox()
        self._spin_inductance.setRange(0, 100); self._spin_inductance.setValue(0.0)
        self._spin_inductance.setDecimals(1)
        proc_grid.addWidget(QLabel(tr("weld_inductance")), 2, 2)
        proc_grid.addWidget(self._spin_inductance, 2, 3)

        content_layout.addWidget(proc_group)

        # ── 5c. WorkspaceZSection (absolute Z heights) ──
        offset_group = QGroupBox(tr("weld_workspace_z"))
        offset_form = QFormLayout(offset_group)

        self._spin_z_work = QDoubleSpinBox()
        self._spin_z_work.setRange(-2000, 2000); self._spin_z_work.setValue(300.0)
        self._spin_z_work.setSuffix(" mm"); self._spin_z_work.setDecimals(1)
        offset_form.addRow(tr("weld_z_work"), self._spin_z_work)

        self._spin_z_safe = QDoubleSpinBox()
        self._spin_z_safe.setRange(-2000, 3000); self._spin_z_safe.setValue(310.0)
        self._spin_z_safe.setSuffix(" mm"); self._spin_z_safe.setDecimals(1)
        offset_form.addRow(tr("weld_z_safe"), self._spin_z_safe)

        self._spin_z_super_extra = QDoubleSpinBox()
        self._spin_z_super_extra.setRange(0, 200); self._spin_z_super_extra.setValue(10.0)
        self._spin_z_super_extra.setSuffix(" mm"); self._spin_z_super_extra.setDecimals(1)
        offset_form.addRow(tr("weld_z_super_extra"), self._spin_z_super_extra)

        content_layout.addWidget(offset_group)

        # ── 5d. LuaMotionParamsSection ──
        lua_group = QGroupBox(tr("weld_lua_motion"))
        lua_form = QFormLayout(lua_group)

        self._spin_lua_accel = QDoubleSpinBox()
        self._spin_lua_accel.setRange(1, 5000); self._spin_lua_accel.setValue(300)
        self._spin_lua_accel.setSuffix(" mm/s²"); self._spin_lua_accel.setDecimals(0)
        lua_form.addRow(tr("weld_lua_accel"), self._spin_lua_accel)

        self._combo_blend_mode = QComboBox()
        self._combo_blend_mode.addItem(tr("weld_blend_absolute"), "absolute")
        self._combo_blend_mode.addItem(tr("weld_blend_relative"), "relative")
        self._combo_blend_mode.currentIndexChanged.connect(self._on_blend_mode_changed)
        lua_form.addRow(tr("weld_lua_blend_mode"), self._combo_blend_mode)

        self._spin_blend_radius = QDoubleSpinBox()
        self._spin_blend_radius.setRange(0, 100); self._spin_blend_radius.setValue(2.0)
        self._spin_blend_radius.setDecimals(2); self._spin_blend_radius.setSingleStep(0.1)
        self._spin_blend_radius.setSuffix(" mm")
        lua_form.addRow(tr("weld_lua_blend_radius"), self._spin_blend_radius)

        self._spin_blend_ratio = QSpinBox()
        self._spin_blend_ratio.setRange(1, 100); self._spin_blend_ratio.setValue(50)
        self._spin_blend_ratio.setSuffix(" %")
        self._spin_blend_ratio.setEnabled(False)
        lua_form.addRow(tr("weld_lua_blend_ratio"), self._spin_blend_ratio)

        self._chk_wait_enabled = QCheckBox(tr("weld_wait_enabled"))
        self._chk_wait_enabled.setChecked(False)
        self._chk_wait_enabled.toggled.connect(self._on_wait_enabled_toggled)
        lua_form.addRow("", self._chk_wait_enabled)

        self._spin_wait_count = QSpinBox()
        self._spin_wait_count.setRange(1, 10000); self._spin_wait_count.setValue(30)
        self._spin_wait_count.setEnabled(False)
        lua_form.addRow(tr("weld_wait_count"), self._spin_wait_count)

        self._spin_wait_duration_ms = QSpinBox()
        self._spin_wait_duration_ms.setRange(1, 100000); self._spin_wait_duration_ms.setValue(1)
        self._spin_wait_duration_ms.setSuffix(" ms")
        self._spin_wait_duration_ms.setEnabled(False)
        lua_form.addRow(tr("weld_wait_duration"), self._spin_wait_duration_ms)

        content_layout.addWidget(lua_group)

        content_layout.addStretch()
        scroll.setWidget(content)

        # ── 右面板: 按钮 + 日志 ──
        right_panel = QWidget()
        right_panel.setObjectName("weldingRightPanel")
        right_panel.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self._btn_generate = QPushButton(tr("weld_gen_btn"))
        self._btn_generate.setMinimumHeight(40)
        self._btn_generate.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2e86c1; }")
        self._btn_generate.clicked.connect(self._on_generate)
        right_layout.addWidget(self._btn_generate)

        self._btn_preview = QPushButton(tr("weld_preview_btn"))
        self._btn_preview.setMinimumHeight(36)
        self._btn_preview.clicked.connect(self._on_preview)
        right_layout.addWidget(self._btn_preview)

        self._btn_export = QPushButton(tr("weld_export_btn"))
        self._btn_export.setMinimumHeight(36)
        self._btn_export.clicked.connect(self._on_export)
        right_layout.addWidget(self._btn_export)

        log_group = QGroupBox(tr("weld_log_title"))
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #80c080; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; }")
        log_layout.addWidget(self._log)
        right_layout.addWidget(log_group, stretch=1)

        # ── 水平拆分: 左参数(scroll) + 右(按钮+日志) ──
        horiz = QHBoxLayout()
        horiz.setSpacing(8)
        horiz.addWidget(scroll, stretch=3)
        horiz.addWidget(right_panel, stretch=1)
        root.addLayout(horiz)

        self._last_txt_path = ""
        self._last_json_path = ""
        self._last_preview_path = ""

        self._init_settings_persistence()

    def _init_settings_persistence(self):
        """修改后防抖写入 QSettings；应用退出时再保存一次。"""
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(400)
        self._settings_save_timer.timeout.connect(self._save_settings)

        def _schedule_save(*_args):
            self._settings_save_timer.start()

        self._text_input.textChanged.connect(_schedule_save)
        for combo in (
            self._font_combo,
            self._mode_combo,
            self._combo_dir,
            self._combo_align,
            self._combo_flow,
            self._combo_blend_mode,
        ):
            combo.currentIndexChanged.connect(_schedule_save)
        for spin in self._iter_persist_spinboxes():
            spin.valueChanged.connect(_schedule_save)
        self._chk_wait_enabled.toggled.connect(_schedule_save)

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._save_settings)

    def _iter_persist_spinboxes(self):
        """所有需要持久化的数值控件。"""
        for spin in (
            self._spin_char_h,
            self._spin_margin_left,
            self._spin_margin_top,
            self._spin_char_s,
            self._spin_line_s,
            self._spin_lead_in,
            self._spin_lead_out,
            self._spin_overlap,
            self._spin_pt_space,
            self._spin_voltage,
            self._spin_current,
            self._spin_job,
            self._spin_inductance,
            self._spin_weld_speed,
            self._spin_travel_speed,
            self._spin_z_work,
            self._spin_z_safe,
            self._spin_z_super_extra,
            self._spin_lua_accel,
            self._spin_blend_radius,
            self._spin_blend_ratio,
            self._spin_wait_count,
            self._spin_wait_duration_ms,
        ):
            yield spin
        for row in self._ws_spins:
            for spin in row:
                yield spin

    def on_enter(self):
        self._restore_settings()
        self._ensure_service()

    def on_leave(self):
        self._save_settings()
        if self._moveto_active_row is not None:
            self._stop_moveto(reason="离开页面")
        if self._welder_active_kind is not None:
            self._stop_welder(silent=True)
        self._teardown_service()

    # ── Service 管理 (V2 only) ──

    def _teardown_service(self):
        """安全断开所有信号并释放当前 welding service。"""
        svc = self._welding_service
        if svc is None:
            return
        for sig_name in ["progress", "error_occurred", "log_message",
                          "state_changed", "finished", "preview_ready"]:
            sig = getattr(svc, sig_name, None)
            if sig is not None:
                try:
                    sig.disconnect(self)
                except (TypeError, RuntimeError):
                    pass
        svc.deleteLater()
        self._welding_service = None

    def _ensure_service(self):
        """确保 WeldingServiceV2 已实例化并连接信号。"""
        if self._welding_service is not None:
            return
        from services.welding_service_v2 import WeldingServiceV2
        self._welding_service = WeldingServiceV2(self, output_dir="output")
        self._welding_service.progress.connect(self._on_progress)
        self._welding_service.error_occurred.connect(self._on_service_error)
        self._welding_service.log_message.connect(self._append_log)
        self._welding_service.state_changed.connect(self._on_state_changed)
        self._welding_service.finished.connect(self._on_finished)
        self._welding_service.preview_ready.connect(self._on_preview_ready)

    # ── 参数持久化 ──

    _SETTINGS_PREFIX = "welding/"

    def _save_settings(self):
        """保存所有 UI 参数到 QSettings。"""
        try:
            s = QSettings("Codroid", "RobotUI")
            p = self._SETTINGS_PREFIX

            # 文字与字体
            s.setValue(p + "text", normalize_weld_text_input(self._text_input.toPlainText()))
            font_idx = self._font_combo.currentIndex()
            if font_idx >= 0:
                data = self._font_combo.itemData(font_idx)
                if isinstance(data, dict) and data.get("path"):
                    s.setValue(p + "font_path", data["path"])
                    s.setValue(p + "font_family", data.get("family", ""))
            s.setValue(p + "mode", self._mode_combo.currentData())

            # 排版
            s.setValue(p + "char_height_mm", self._spin_char_h.value())
            s.setValue(p + "margin_left_mm", self._spin_margin_left.value())
            s.setValue(p + "margin_top_mm", self._spin_margin_top.value())
            s.setValue(p + "char_spacing_mm", self._spin_char_s.value())
            s.setValue(p + "line_spacing_mm", self._spin_line_s.value())
            s.setValue(p + "direction", _combo_current_data(self._combo_dir, _BETA_DEFAULT_DIRECTION))
            s.setValue(p + "align", _combo_current_data(self._combo_align, _BETA_DEFAULT_ALIGN))
            s.setValue(p + "flow", _combo_current_data(self._combo_flow, _BETA_DEFAULT_FLOW))

            # 焊接参数
            s.setValue(p + "lead_in_mm", self._spin_lead_in.value())
            s.setValue(p + "lead_out_mm", self._spin_lead_out.value())
            s.setValue(p + "overlap_mm", self._spin_overlap.value())
            s.setValue(p + "point_spacing_mm", self._spin_pt_space.value())

            # 工艺参数
            s.setValue(p + "voltage", self._spin_voltage.value())
            s.setValue(p + "current", self._spin_current.value())
            s.setValue(p + "job", int(self._spin_job.value()))
            s.setValue(p + "inductance", self._spin_inductance.value())
            s.setValue(p + "weld_speed_mm_s", self._spin_weld_speed.value())
            s.setValue(p + "travel_speed_mm_s", self._spin_travel_speed.value())

            # 工作空间偏移
            s.setValue(p + "z_work", self._spin_z_work.value())
            s.setValue(p + "z_safe", self._spin_z_safe.value())
            s.setValue(p + "super_safe_extra_mm", self._spin_z_super_extra.value())

            # Lua 运动参数
            lua_accel = int(self._spin_lua_accel.value())
            blend_mode = _combo_current_data(self._combo_blend_mode, "absolute")
            blend_radius = self._spin_blend_radius.value()
            blend_ratio = int(self._spin_blend_ratio.value())
            wait_enabled = self._chk_wait_enabled.isChecked()
            wait_count = int(self._spin_wait_count.value())
            wait_ms = int(self._spin_wait_duration_ms.value())
            s.setValue(p + "lua_acceleration_mm_s2", lua_accel)
            s.setValue(p + "lua_blend_mode", blend_mode)
            s.setValue(p + "lua_blend_mode_index", self._combo_blend_mode.currentIndex())
            s.setValue(p + "lua_blend_radius_mm", blend_radius)
            s.setValue(p + "lua_blend_ratio_percent", blend_ratio)
            s.setValue(p + "lua_insert_wait_enabled", wait_enabled)
            s.setValue(p + "lua_wait_every_movl_count", wait_count)
            s.setValue(p + "lua_wait_duration_ms", wait_ms)
            # 旧版 key，便于升级前配置迁移
            s.setValue(p + "lua_accel", lua_accel)
            s.setValue(p + "lua_blend_radius", blend_radius)
            s.setValue(p + "lua_blend_ratio", blend_ratio)
            s.setValue(p + "lua_wait_duration", wait_ms)

            # 工作空间标定点
            for row, label in enumerate(["left_top", "right_top", "left_bot"]):
                for col, axis in enumerate(["x", "y", "z", "rx", "ry", "rz"]):
                    s.setValue(
                        f"{p}ws/{label}/{axis}",
                        self._ws_spins[row][col].value(),
                    )

            s.sync()
        except Exception as exc:
            _sys_log.warning("welding settings save failed: %s", exc)

    def _restore_settings(self):
        """从 QSettings 恢复上次保存的 UI 参数。无保存值时保留默认。"""
        s = QSettings("Codroid", "RobotUI")
        p = self._SETTINGS_PREFIX

        block_widgets = [
            self._text_input,
            self._font_combo,
            self._mode_combo,
            self._combo_dir,
            self._combo_align,
            self._combo_flow,
            self._combo_blend_mode,
            self._chk_wait_enabled,
            *self._iter_persist_spinboxes(),
        ]
        for w in block_widgets:
            w.blockSignals(True)
        try:
            self._restore_settings_values(s, p)
        except Exception as exc:
            _sys_log.warning("welding settings restore failed: %s", exc)
        finally:
            for w in block_widgets:
                w.blockSignals(False)
            self._on_blend_mode_changed(self._combo_blend_mode.currentIndex())
            self._on_wait_enabled_toggled(self._chk_wait_enabled.isChecked())

    def _restore_settings_values(self, s: QSettings, p: str):
        def _str(key, default=""):
            v = s.value(p + key, default)
            return "" if v is None else str(v)

        # 文字
        txt = _str("text", "Abc123")
        if txt:
            self._text_input.setPlainText(normalize_weld_text_input(txt))

        # Mode
        mode_val = _str("mode", "contour")
        idx = self._mode_combo.findData(mode_val)
        if idx >= 0:
            self._mode_combo.setCurrentIndex(idx)

        # 字体恢复（三级回退：path → family → 默认 index 0）
        font_path = _str("font_path", "")
        font_family = _str("font_family", "")
        selected = False

        if font_path and os.path.exists(font_path):
            for i in range(self._font_combo.count()):
                data = self._font_combo.itemData(i)
                if isinstance(data, dict) and data.get("path") == font_path:
                    self._font_combo.setCurrentIndex(i)
                    selected = True
                    break

        if not selected and font_family:
            for i in range(self._font_combo.count()):
                data = self._font_combo.itemData(i)
                if isinstance(data, dict) and data.get("family", "").lower() == font_family.lower():
                    self._font_combo.setCurrentIndex(i)
                    selected = True
                    break

        if not selected and font_path:
            self._append_log(tr("weld_log_font_unavailable").format(path=font_path))

        # 排版
        self._spin_char_h.setValue(_qsettings_float(s.value(p + "char_height_mm"), CHAR_HEIGHT_MM))
        legacy_margin = s.value(p + "workspace_margin_mm")
        self._spin_margin_left.setValue(
            _qsettings_float(
                s.value(p + "margin_left_mm"),
                _qsettings_float(legacy_margin, MARGIN_LEFT_MM),
            )
        )
        self._spin_margin_top.setValue(
            _qsettings_float(
                s.value(p + "margin_top_mm"),
                _qsettings_float(legacy_margin, MARGIN_TOP_MM),
            )
        )
        self._spin_char_s.setValue(_qsettings_float(s.value(p + "char_spacing_mm"), CHAR_SPACING_MM))
        self._spin_line_s.setValue(_qsettings_float(s.value(p + "line_spacing_mm"), LINE_SPACING_MM))

        dv = _str("direction", _BETA_DEFAULT_DIRECTION)
        di = self._combo_dir.findData(dv)
        if di >= 0:
            self._combo_dir.setCurrentIndex(di)
        av = _normalize_align_setting(s.value(p + "align", _BETA_DEFAULT_ALIGN))
        ai = self._combo_align.findData(av)
        if ai >= 0:
            self._combo_align.setCurrentIndex(ai)
        fv = _normalize_flow_setting(s.value(p + "flow", _BETA_DEFAULT_FLOW))
        fi = self._combo_flow.findData(fv)
        if fi >= 0:
            self._combo_flow.setCurrentIndex(fi)

        # 焊接参数
        self._spin_lead_in.setValue(_qsettings_float(s.value(p + "lead_in_mm"), LEAD_IN_MM))
        self._spin_lead_out.setValue(_qsettings_float(s.value(p + "lead_out_mm"), LEAD_OUT_MM))
        self._spin_overlap.setValue(_qsettings_float(s.value(p + "overlap_mm"), OVERLAP_MM))
        self._spin_pt_space.setValue(_qsettings_float(s.value(p + "point_spacing_mm"), POINT_SPACING_MM))

        # 工艺参数
        self._spin_voltage.setValue(_qsettings_float(s.value(p + "voltage"), 24.0))
        self._spin_current.setValue(_qsettings_float(s.value(p + "current"), 150.0))
        self._spin_job.setValue(_qsettings_int(s.value(p + "job"), 0))
        self._spin_inductance.setValue(_qsettings_float(s.value(p + "inductance"), 0.0))
        self._spin_weld_speed.setValue(_qsettings_float(s.value(p + "weld_speed_mm_s"), 30.0))
        self._spin_travel_speed.setValue(_qsettings_float(s.value(p + "travel_speed_mm_s"), 80.0))

        # 工作空间偏移
        z_work_val = s.value(p + "z_work")
        if z_work_val is not None:
            self._spin_z_work.setValue(_qsettings_float(z_work_val, self._spin_z_work.value()))
        else:
            avg_z = sum(self._ws_spins[i][2].value() for i in range(3)) / 3.0
            self._spin_z_work.setValue(round(avg_z, 1))
        z_safe_val = s.value(p + "z_safe")
        self._spin_z_safe.setValue(
            _qsettings_float(z_safe_val, self._spin_z_work.value() + 10.0)
            if z_safe_val is not None
            else self._spin_z_work.value() + 10.0
        )
        self._spin_z_super_extra.setValue(
            _qsettings_float(s.value(p + "super_safe_extra_mm"), 10.0)
        )

        # Lua 运动参数（新 key 优先，旧 key 回退）
        lua_accel_val = s.value(p + "lua_acceleration_mm_s2")
        if lua_accel_val is None:
            lua_accel_val = s.value(p + "lua_accel")
        self._spin_lua_accel.setValue(_qsettings_float(lua_accel_val, 300.0))

        bm_raw = s.value(p + "lua_blend_mode")
        bi = -1
        if bm_raw is not None:
            bm = str(bm_raw)
            bi = self._combo_blend_mode.findData(bm)
            if bi < 0:
                bi = self._combo_blend_mode.findText(bm)
        if bi < 0:
            bi = _qsettings_int(s.value(p + "lua_blend_mode_index"), -1)
        if bi >= 0:
            self._combo_blend_mode.setCurrentIndex(bi)

        blend_r_val = s.value(p + "lua_blend_radius_mm")
        if blend_r_val is None:
            blend_r_val = s.value(p + "lua_blend_radius")
        self._spin_blend_radius.setValue(_qsettings_float(blend_r_val, 2.0))

        blend_ratio_val = s.value(p + "lua_blend_ratio_percent")
        if blend_ratio_val is None:
            blend_ratio_val = s.value(p + "lua_blend_ratio")
        self._spin_blend_ratio.setValue(_qsettings_int(blend_ratio_val, 50))

        self._chk_wait_enabled.setChecked(
            _qsettings_bool(s.value(p + "lua_insert_wait_enabled"), False)
        )
        self._spin_wait_count.setValue(
            _qsettings_int(s.value(p + "lua_wait_every_movl_count"), 30)
        )
        wait_ms_val = s.value(p + "lua_wait_duration_ms")
        if wait_ms_val is None:
            wait_ms_val = s.value(p + "lua_wait_duration")
        self._spin_wait_duration_ms.setValue(max(1, _qsettings_int(wait_ms_val, 1)))

        # 工作空间标定点
        for row, label in enumerate(["left_top", "right_top", "left_bot"]):
            for col, axis in enumerate(["x", "y", "z", "rx", "ry", "rz"]):
                key = f"{p}ws/{label}/{axis}"
                v = s.value(key)
                if v is not None:
                    self._ws_spins[row][col].setValue(_qsettings_float(v, 0.0))

    def _on_mode_changed(self, index: int):
        if self._mode_combo.itemData(index) == "skeleton":
            self._append_log(tr("weld_mode_skeleton_tip"))

    def _on_blend_mode_changed(self, index: int):
        mode = self._combo_blend_mode.itemData(index)
        if mode == "absolute":
            self._spin_blend_radius.setEnabled(True)
            self._spin_blend_ratio.setEnabled(False)
        elif mode == "relative":
            self._spin_blend_radius.setEnabled(False)
            self._spin_blend_ratio.setEnabled(True)

    def _on_wait_enabled_toggled(self, checked: bool):
        self._spin_wait_count.setEnabled(checked)
        self._spin_wait_duration_ms.setEnabled(checked)

    def _append_log(self, msg: str):
        self._log.appendPlainText(msg)
        _sys_log.info(f"[Welding] {msg}")

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
        索引: row 0=左上, 1=右上, 2=左下。
        U = right_top - left_top, V = left_bottom - left_top。
        right_bottom = left_top + U + V。
        """
        def _rp(row):
            spins = self._ws_spins[row]
            return RobotPoint(
                x=spins[0].value(), y=spins[1].value(), z=spins[2].value(),
                rx=spins[3].value(), ry=spins[4].value(), rz=spins[5].value(),
            )
        lt = _rp(0)  # 左上
        rt = _rp(1)  # 右上
        lb = _rp(2)  # 左下
        # 推导右下
        rb = RobotPoint(
            x=lt.x + (rt.x - lt.x) + (lb.x - lt.x),
            y=lt.y + (rt.y - lt.y) + (lb.y - lt.y),
            z=lt.z + (rt.z - lt.z) + (lb.z - lt.z),
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
        self._append_log(tr("weld_log_service_error").format(msg=msg))

    def _on_preview_ready(self, png_path: str):
        self._last_preview_path = png_path

    def _collect_params(self) -> dict:
        font_idx = self._font_combo.currentIndex()
        font_data = self._font_combo.itemData(font_idx) if font_idx >= 0 else {}
        if isinstance(font_data, dict):
            font_path = font_data.get("path", "")
        else:
            font_path = font_data or ""

        return {
            "text": normalize_weld_text_input(self._text_input.toPlainText()),
            "font_path": font_path or "",
            "char_height_mm": self._spin_char_h.value(),
            "margin_left_mm": self._spin_margin_left.value(),
            "margin_top_mm": self._spin_margin_top.value(),
            "char_spacing_mm": self._spin_char_s.value(),
            "line_spacing_mm": self._spin_line_s.value(),
            "direction": _combo_current_data(self._combo_dir, _BETA_DEFAULT_DIRECTION),
            "align": _combo_current_data(self._combo_align, _BETA_DEFAULT_ALIGN),
            "flow": _combo_current_data(self._combo_flow, _BETA_DEFAULT_FLOW),
            "lead_in_mm": self._spin_lead_in.value(),
            "lead_out_mm": self._spin_lead_out.value(),
            "overlap_mm": self._spin_overlap.value(),
            "point_spacing_mm": self._spin_pt_space.value(),
        }

    def _on_generate(self):
        if self._welding_service is None:
            self._append_log(tr("weld_log_no_service"))
            return
        params = self._collect_params()
        if not params["text"]:
            self._append_log(tr("weld_log_no_text"))
            return
        self._save_settings()
        # 清空上次生成的状态
        self._last_txt_path = ""
        self._last_json_path = ""
        self._last_preview_path = ""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = self._mode_combo.currentData() or "contour"
        text_log = params["text"].replace("\n", " ↵ ")
        self._append_log(tr("weld_log_generate_header").format(
            ts=ts, text=text_log, mode=mode))
        beta_opts = detect_beta_features(
            mode=str(mode),
            text=params["text"],
            line_spacing_mm=params["line_spacing_mm"],
            align=params["align"],
            direction=params["direction"],
            flow=params["flow"],
        )
        if beta_opts:
            self._append_log(tr("weld_beta_features").format(features=", ".join(beta_opts)))
            self._append_log(tr("weld_beta_recommend"))
        else:
            self._append_log(tr("weld_production_line"))
        self._btn_export.setEnabled(False)
        self._btn_preview.setEnabled(False)
        # 防重入：生成进行中禁止再次点击
        self._btn_generate.setEnabled(False)

        ws = self._read_workspace_calibration()
        self._welding_service.generate(
            text=params["text"],
            mode=mode,
            left_top=ws["left_top"],
            right_top=ws["right_top"],
            left_bottom=ws["left_bottom"],
            font_path=params["font_path"] or None,
            font_size_px=600,
            px_per_mm=10.0,
            char_height_mm=params["char_height_mm"],
            char_spacing_mm=params["char_spacing_mm"],
            line_spacing_mm=params["line_spacing_mm"],
            margin_left_mm=params["margin_left_mm"],
            margin_top_mm=params["margin_top_mm"],
            lead_in_mm=params["lead_in_mm"],
            lead_out_mm=params["lead_out_mm"],
            overlap_mm=params["overlap_mm"],
            weld_point_spacing_mm=params["point_spacing_mm"],
            voltage=self._spin_voltage.value(),
            current=self._spin_current.value(),
            job=self._spin_job.value(),
            inductance=self._spin_inductance.value(),
            weld_speed=self._spin_weld_speed.value(),
            travel_speed=self._spin_travel_speed.value(),
            z_work_mm=self._spin_z_work.value(),
            z_safe_mm=self._spin_z_safe.value(),
            z_super_safe_mm=self._spin_z_safe.value() + self._spin_z_super_extra.value(),
            lua_accel=self._spin_lua_accel.value(),
            lua_blend_mode=self._combo_blend_mode.currentData(),
            lua_blend_radius=self._spin_blend_radius.value(),
            lua_blend_ratio=self._spin_blend_ratio.value(),
            wait_enabled=self._chk_wait_enabled.isChecked(),
            wait_count=self._spin_wait_count.value(),
            wait_duration_ms=self._spin_wait_duration_ms.value(),
            user_lang=I18nManager.instance().lang,
        )

    def _on_preview(self):
        if self._last_preview_path and os.path.exists(self._last_preview_path):
            _open_path(self._last_preview_path)
        else:
            self._append_log(tr("weld_log_preview_first"))

    def _on_export(self):
        if self._last_txt_path:
            _open_path(os.path.dirname(self._last_txt_path))
        else:
            self._append_log(tr("weld_log_preview_first"))

    def _update_ws_from_current(self, row: int):
        """从 RobotRealtimeState 读取当前 TCP 位姿，填入工作空间第 row 行。"""
        from services.robot_realtime_state import RobotRealtimeState
        state = RobotRealtimeState.instance()
        if not state.is_valid():
            self._append_log(tr("weld_log_cri_no_data"))
            return
        x, y, z, rx, ry, rz = state.current_tcp_pose_mm_deg()
        self._ws_spins[row][0].setValue(round(x, 3))
        self._ws_spins[row][1].setValue(round(y, 3))
        self._ws_spins[row][2].setValue(round(z, 3))
        self._ws_spins[row][3].setValue(round(rx, 3))
        self._ws_spins[row][4].setValue(round(ry, 3))
        self._ws_spins[row][5].setValue(round(rz, 3))
        self._append_log(tr("weld_log_ws_updated").format(
            corner=_weld_corner_label(row),
            x=x, y=y, z=z, rx=rx, ry=ry, rz=rz,
        ))

    def _welder_kind_label(self, kind: str | None) -> str:
        if kind and kind in _WELDER_KIND_I18N:
            return tr(_WELDER_KIND_I18N[kind])
        return "?"

    def _welder_sendparams(self, payload, *, on_ok=None, on_err=None):
        sp = self.sp
        if sp is None or sp.cm is None or not sp.cm.is_connected:
            if on_err:
                on_err(Exception("not connected"))
            return
        sp.cm.send_call(
            "welder/sendparams",
            payload,
            on_response=lambda _d: on_ok() if on_ok else None,
            on_error=on_err or (lambda e: self._append_log(
                tr("weld_log_welder_failed").format(err=e))),
        )

    def _welder_send_command(self, value: int):
        self._welder_sendparams([{"path": "Welder/command", "value": int(value)}])

    def _welder_send_heartbeat(self):
        self._welder_sendparams(
            [{"path": "Welder/commandHeart", "value": int(time.time() * 1000)}],
            on_err=lambda e: self._stop_welder(
                reason=tr("weld_log_welder_hb_failed").format(err=e)),
        )

    def _start_welder_heartbeat(self):
        if self._welder_heartbeat is None:
            self._welder_heartbeat = QTimer(self)
            self._welder_heartbeat.setInterval(500)
            self._welder_heartbeat.timeout.connect(self._welder_send_heartbeat)
        self._welder_heartbeat.start()

    def _stop_welder(self, reason: str = "", *, silent: bool = False):
        kind = self._welder_active_kind
        self._welder_active_kind = None
        if self._welder_heartbeat is not None:
            self._welder_heartbeat.stop()
        sp = self.sp
        if sp and sp.cm and sp.cm.is_connected:
            self._welder_sendparams(
                [{"path": "Welder/command", "value": 0}],
                on_ok=lambda: (
                    None if silent
                    else self._append_log(tr("weld_log_welder_stop_sent"))
                ),
                on_err=lambda e: (
                    None if silent
                    else self._append_log(
                        tr("weld_log_welder_stop_failed").format(err=e))
                ),
            )
        if not silent:
            suffix = f": {reason}" if reason else ""
            self._append_log(tr("weld_log_welder_stop").format(
                name=self._welder_kind_label(kind), reason=suffix))

    def _on_welder_hold_started(self, kind: str):
        cmd = _WELDER_KIND_TO_CMD.get(kind)
        if cmd is None:
            return
        sp = self.sp
        if sp is None or sp.cm is None or not sp.cm.is_connected:
            self._append_log(tr("weld_log_not_connected"))
            return
        if self._welder_active_kind and self._welder_active_kind != kind:
            self._stop_welder(silent=True)
        self._welder_active_kind = kind
        label = self._welder_kind_label(kind)
        self._append_log(tr("weld_log_welder_press").format(name=label, cmd=cmd))

        def _on_start_ok():
            self._start_welder_heartbeat()
            self._append_log(tr("weld_log_welder_hb_start"))

        def _on_start_err(e):
            self._welder_active_kind = None
            self._append_log(tr("weld_log_welder_failed").format(err=e))

        self._welder_sendparams(
            [{"path": "Welder/command", "value": cmd}],
            on_ok=_on_start_ok,
            on_err=_on_start_err,
        )

    def _on_welder_hold_stopped(self, kind: str):
        if self._welder_active_kind != kind:
            return
        self._stop_welder(reason=tr("weld_log_welder_released"))

    def _on_moveto_pressed(self, row: int):
        """按压: 发送 Robot/moveTo type=5 + 启动 heartbeat。"""
        # 并发保护
        if self._moveto_active_row is not None:
            self._append_log(tr("weld_log_moveto_busy").format(
                corner=_WELD_CORNER_CODES[self._moveto_active_row]))
            return
        sp = self.sp
        if sp is None or sp.cm is None or not sp.cm.is_connected:
            self._append_log(tr("weld_log_not_connected"))
            return
        spins = self._ws_spins[row]
        cp = [spins[0].value(), spins[1].value(), spins[2].value(),
              spins[3].value(), spins[4].value(), spins[5].value()]
        corner = _weld_corner_label(row)
        if any(not isinstance(v, (int,float)) or (isinstance(v,float) and math.isnan(v)) for v in cp):
            self._append_log(tr("weld_log_invalid_coords").format(coords=cp))
            return

        self._moveto_active_row = row
        db = {"type":5,"target":{"cp":cp,"jp":[],"ep":[]}}
        self._append_log(tr("weld_log_moveto_press").format(
            corner=corner, x=cp[0], y=cp[1], z=cp[2], rx=cp[3], ry=cp[4], rz=cp[5]))
        sp.cm.send_call("Robot/moveTo", db,
            on_response=lambda d: self._append_log(tr("weld_log_moveto_sent")),
            on_error=lambda e: self._append_log(tr("weld_log_moveto_failed").format(err=e)))

        self._moveto_heartbeat = QTimer(self)
        self._moveto_heartbeat.setInterval(500)
        def _hb():
            if sp.cm and sp.cm.is_connected:
                sp.cm.send_call("Robot/moveToHeartbeat", {},
                    on_response=None,
                    on_error=lambda e: self._stop_moveto(
                        reason=tr("weld_log_moveto_hb_failed").format(err=e)))
        self._moveto_heartbeat.timeout.connect(_hb)
        self._moveto_heartbeat.start()
        self._append_log(tr("weld_log_moveto_hb_start"))

    def _on_moveto_released(self, row: int):
        """松开: 停止 heartbeat + 发送 type=-1。"""
        if self._moveto_active_row != row:
            return
        self._stop_moveto(reason=tr("weld_log_moveto_released").format(
            corner=_weld_corner_label(row)))

    def _stop_moveto(self, reason: str = ""):
        """统一停止: heartbeat stop + type=-1 + 清空状态。"""
        row = self._moveto_active_row
        self._moveto_active_row = None
        if self._moveto_heartbeat:
            self._moveto_heartbeat.stop()
            self._moveto_heartbeat.deleteLater()
            self._moveto_heartbeat = None
        corner = _weld_corner_label(row) if row is not None else "?"
        suffix = f": {reason}" if reason else ""
        self._append_log(tr("weld_log_moveto_stop").format(corner=corner, reason=suffix))
        sp = self.sp
        if sp and sp.cm and sp.cm.is_connected:
            sp.cm.send_call("Robot/moveTo", {"type":-1},
                on_response=lambda d: self._append_log(tr("weld_log_moveto_stop_sent")),
                on_error=lambda e: self._append_log(
                    tr("weld_log_moveto_stop_failed").format(err=e)))

    def _copy_ws_point(self, row: int):
        """复制标定点坐标到剪贴板。"""
        spins = self._ws_spins[row]
        text = f"[{spins[0].value():.3f},{spins[1].value():.3f},{spins[2].value():.3f},{spins[3].value():.3f},{spins[4].value():.3f},{spins[5].value():.3f}]"
        QApplication.clipboard().setText(text)
        self._append_log(tr("weld_log_copied").format(
            corner=_weld_corner_label(row), text=text))

    def _restore_ws_defaults(self):
        defaults = [
            (100, 200, 300, 180, 0, 90),
            (100, 400, 300, 180, 0, 90),
            (300, 400, 300, 180, 0, 90),
        ]
        for i, defs in enumerate(defaults):
            for j, dv in enumerate(defs):
                self._ws_spins[i][j].setValue(float(dv))
