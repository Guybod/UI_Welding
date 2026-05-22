"""绘图/写字功能页 — 轮廓字 + 焊接 pipeline + CRI 运动下发。"""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, QSettings, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.base_page import BasePage
from app.i18n import I18nManager, tr
from app.ui_log import append_ui_log
from app.pages.welding_page import (
    _build_font_item_data,
    _find_system_fonts,
    _qsettings_float,
    _qsettings_int,
    normalize_weld_text_input,
)
from config.stroke_fonts.hershey_presets import (
    build_hershey_style_item_data,
    get_default_hershey_style_id,
    list_hershey_style_presets,
)
from config.stroke_fonts.hershey_presets import get_default_hershey_style_id
from pipeline.text_pipeline import (
    TEXT_SOURCE_HANZI_STROKE,
    TEXT_SOURCE_IMAGE_CONTOUR,
    TEXT_SOURCE_LATIN_STROKE,
    TEXT_SOURCE_TTF_CONTOUR,
    build_text_pipeline,
    migrate_welding_text_source,
)
from pipeline.weld_skeleton_latin import validate_weld_skeleton_text
from config.welding_defaults import (
    CHAR_HEIGHT_MM,
    CHAR_SPACING_MM,
    LINE_SPACING_MM,
    MARGIN_LEFT_MM,
    MARGIN_TOP_MM,
)
from core.platform_utils import open_path as _open_path
from core.types import ImageDrawingConfig, ImageProcessConfig, RobotPoint
from pipeline.mapping.workplane import WorkPlane
from pipeline.vision import image_presets
from pipeline.vision.image_preprocessor import contour_strategy_log_messages
from app.widgets.image_params_widget import ImageParamsWidget
from app.widgets.image_preview_dialog import ImagePreviewDialog
from services.image_drawing_service import ImageDrawingService
from services.writing_execution_service import WritingExecConfig, WritingExecutionService

_SETTINGS_PREFIX = "drawing/"
_IMAGE_SETTINGS_PREFIX = "drawing/image/"
_WELD_CORNER_CODES = ("LT", "RT", "LB")
_IMAGE_PREVIEW_DIR = "output/drawing_image_preview"
_IMAGE_RUN_DIR = "output/drawing_image_run"
_PRESET_TR_KEYS = {
    image_presets.PRESET_LINEART: "draw_preset_lineart",
    image_presets.PRESET_SILHOUETTE: "draw_preset_silhouette",
    image_presets.PRESET_PHOTO_EDGE_BETA: "draw_preset_photo_edge",
    image_presets.PRESET_PHOTO_COMPLEX_BETA: "draw_preset_photo_complex",
}


def _corner_label(row: int) -> str:
    if 0 <= row < len(_WELD_CORNER_CODES):
        return _WELD_CORNER_CODES[row]
    return "?"


class WritingPage(BasePage):
    """轮廓字写字 — 布局/映射同焊接，运动经 CRI UDP。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = QSettings("Codroid", "RobotUI")
        self._writing_service = None
        self._image_service = ImageDrawingService(self)
        self._exec_service = WritingExecutionService(self)
        self._last_traj_path = ""
        self._last_points_path = ""
        self._last_preview_path = ""
        self._last_image_contour_preview = ""
        self._last_image_preview_dir = ""
        self._at_start_ready = False
        self._moveto_active_row: int | None = None
        self._moveto_heartbeat: QTimer | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 8, 8, 8)
        root.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content.setObjectName("writingContent")
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(10)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel(tr("draw_mode") + ":"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem(tr("draw_text_mode"), "text")
        self._mode_combo.addItem(tr("draw_image_mode"), "image")
        self._mode_combo.currentIndexChanged.connect(self._on_draw_mode_changed)
        mode_row.addWidget(self._mode_combo, 1)
        content_layout.addLayout(mode_row)

        # ── 文字 ──
        self._text_group = QGroupBox(tr("draw_text_group"))
        text_group = self._text_group
        text_layout = QVBoxLayout(text_group)
        self._text_input = QPlainTextEdit()
        self._text_input.setPlaceholderText(tr("draw_text_placeholder"))
        self._text_input.setToolTip(tr("draw_text_tip"))
        self._text_input.setPlainText("Abc123")
        self._text_input.setFixedHeight(72)
        self._text_input.setTabChangesFocus(True)
        text_layout.addWidget(self._text_input)

        text_src_row = QHBoxLayout()
        text_src_row.addWidget(QLabel(tr("draw_text_gen_mode") + ":"))
        self._text_source_combo = QComboBox()
        self._text_source_combo.addItem(tr("draw_mode_contour"), TEXT_SOURCE_TTF_CONTOUR)
        self._text_source_combo.addItem(tr("draw_mode_latin_stroke"), TEXT_SOURCE_LATIN_STROKE)
        self._text_source_combo.addItem(tr("draw_mode_hanzi_stroke"), TEXT_SOURCE_HANZI_STROKE)
        self._text_source_combo.currentIndexChanged.connect(self._on_text_source_changed)
        text_src_row.addWidget(self._text_source_combo, 1)
        text_layout.addLayout(text_src_row)

        font_row = QHBoxLayout()
        self._font_label = QLabel(tr("draw_font") + ":")
        font_row.addWidget(self._font_label)
        self._font_combo = QComboBox()
        font_row.addWidget(self._font_combo, 1)
        text_layout.addLayout(font_row)
        self._populate_draw_font_combo()
        content_layout.addWidget(text_group)

        self._image_group = self._build_image_group()
        self._image_group.setVisible(False)
        content_layout.addWidget(self._image_group)

        # ── 排版 ──
        self._layout_group = QGroupBox(tr("draw_layout_group"))
        layout_group = self._layout_group
        layout_grid = QGridLayout(layout_group)

        self._spin_char_h = QDoubleSpinBox()
        self._spin_char_h.setRange(1, 500)
        self._spin_char_h.setValue(CHAR_HEIGHT_MM)
        self._spin_char_h.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("draw_char_height")), 0, 0)
        layout_grid.addWidget(self._spin_char_h, 0, 1)

        self._spin_margin_left = QDoubleSpinBox()
        self._spin_margin_left.setRange(0, 500)
        self._spin_margin_left.setValue(MARGIN_LEFT_MM)
        self._spin_margin_left.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("draw_margin_left")), 0, 2)
        layout_grid.addWidget(self._spin_margin_left, 0, 3)

        self._spin_margin_top = QDoubleSpinBox()
        self._spin_margin_top.setRange(0, 500)
        self._spin_margin_top.setValue(MARGIN_TOP_MM)
        self._spin_margin_top.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("draw_margin_top")), 0, 4)
        layout_grid.addWidget(self._spin_margin_top, 0, 5)

        self._spin_char_s = QDoubleSpinBox()
        self._spin_char_s.setRange(0, 100)
        self._spin_char_s.setValue(CHAR_SPACING_MM)
        self._spin_char_s.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("draw_char_spacing")), 1, 0)
        layout_grid.addWidget(self._spin_char_s, 1, 1)

        self._spin_line_s = QDoubleSpinBox()
        self._spin_line_s.setRange(0, 200)
        self._spin_line_s.setValue(LINE_SPACING_MM)
        self._spin_line_s.setSuffix(" mm")
        layout_grid.addWidget(QLabel(tr("draw_line_spacing")), 1, 2)
        layout_grid.addWidget(self._spin_line_s, 1, 3)

        content_layout.addWidget(layout_group)

        # ── 工作空间 ──
        ws_group = QGroupBox(tr("draw_workspace"))
        ws_grid = QGridLayout(ws_group)
        headers = ["X", "Y", "Z", "Rx", "Ry", "Rz"]
        for j, h in enumerate(headers):
            ws_grid.addWidget(QLabel(h), 0, j + 1)
        point_labels = [tr("weld_ws_left_top"), tr("weld_ws_right_top"), tr("weld_ws_left_bot")]
        defaults_ws = [
            (100, 200, 300, 180, 0, 90),
            (300, 200, 300, 180, 0, 90),
            (100, 400, 300, 180, 0, 90),
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
            upd_btn = QPushButton(tr("draw_ws_update"))
            upd_btn.setFixedWidth(64)
            upd_btn.setToolTip(tr("weld_ws_update_tip"))
            upd_btn.clicked.connect(lambda _c=False, row=i: self._update_ws_from_current(row))
            ws_grid.addWidget(upd_btn, i + 1, 7)
            moveto_btn = QPushButton(tr("draw_ws_moveto"))
            moveto_btn.setFixedWidth(72)
            moveto_btn.setToolTip(tr("weld_ws_moveto_tip"))
            moveto_btn.pressed.connect(lambda row=i: self._on_moveto_pressed(row))
            moveto_btn.released.connect(lambda row=i: self._on_moveto_released(row))
            ws_grid.addWidget(moveto_btn, i + 1, 8)
            copy_btn = QPushButton(tr("draw_ws_copy"))
            copy_btn.setFixedWidth(56)
            copy_btn.setToolTip(tr("weld_ws_copy_tip"))
            copy_btn.clicked.connect(lambda _c=False, row=i: self._copy_ws_point(row))
            ws_grid.addWidget(copy_btn, i + 1, 9)
        restore_btn = QPushButton(tr("draw_restore_ws"))
        restore_btn.clicked.connect(self._restore_ws_defaults)
        ws_grid.addWidget(restore_btn, 4, 0, 1, 10)
        content_layout.addWidget(ws_group)

        # ── 落笔高度 + 轨迹点距 ──
        pen_group = QGroupBox(tr("draw_pen_heights"))
        pen_form = QFormLayout(pen_group)
        self._spin_z_work = QDoubleSpinBox()
        self._spin_z_work.setRange(-2000, 2000)
        self._spin_z_work.setValue(305.0)
        self._spin_z_work.setSuffix(" mm")
        pen_form.addRow(tr("draw_z_work"), self._spin_z_work)
        self._spin_z_safe = QDoubleSpinBox()
        self._spin_z_safe.setRange(-2000, 2000)
        self._spin_z_safe.setValue(315.0)
        self._spin_z_safe.setSuffix(" mm")
        pen_form.addRow(tr("draw_z_safe"), self._spin_z_safe)
        self._spin_z_super = QDoubleSpinBox()
        self._spin_z_super.setRange(0, 50)
        self._spin_z_super.setValue(10.0)
        self._spin_z_super.setSuffix(" mm")
        pen_form.addRow(tr("draw_z_super_extra"), self._spin_z_super)
        self._spin_pt_space = QDoubleSpinBox()
        self._spin_pt_space.setRange(0.1, 10)
        self._spin_pt_space.setValue(0.5)
        self._spin_pt_space.setDecimals(2)
        self._spin_pt_space.setSuffix(" mm")
        pen_form.addRow(tr("draw_point_spacing"), self._spin_pt_space)
        content_layout.addWidget(pen_group)

        # ── CRI 参数 ──
        cri_group = QGroupBox(tr("draw_cri_params"))
        cri_form = QFormLayout(cri_group)
        self._spin_sample_rate = QSpinBox()
        self._spin_sample_rate.setRange(50, 2000)
        self._spin_sample_rate.setValue(500)
        self._spin_sample_rate.setSuffix(" Hz")
        cri_form.addRow(tr("draw_sample_rate"), self._spin_sample_rate)
        self._spin_speed = QDoubleSpinBox()
        self._spin_speed.setRange(1, 500)
        self._spin_speed.setValue(50.0)
        self._spin_speed.setSuffix(" mm/s")
        cri_form.addRow(tr("draw_speed"), self._spin_speed)
        self._spin_acc = QDoubleSpinBox()
        self._spin_acc.setRange(1, 5000)
        self._spin_acc.setValue(200.0)
        self._spin_acc.setSuffix(" mm/s²")
        cri_form.addRow(tr("draw_acc"), self._spin_acc)
        self._spin_filter = QSpinBox()
        self._spin_filter.setRange(0, 10)
        self._spin_filter.setValue(1)
        cri_form.addRow(tr("draw_cri_filter"), self._spin_filter)
        self._spin_buffer = QSpinBox()
        self._spin_buffer.setRange(0, 100)
        self._spin_buffer.setValue(5)
        cri_form.addRow(tr("draw_cri_buffer"), self._spin_buffer)
        content_layout.addWidget(cri_group)
        content_layout.addStretch()
        scroll.setWidget(content)

        # ── 右侧 ──
        right = QWidget()
        right.setObjectName("writingRightPanel")
        right.setMinimumWidth(260)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self._btn_generate = QPushButton(tr("draw_gen_btn"))
        self._btn_generate.setMinimumHeight(40)
        self._btn_generate.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2e86c1; }"
        )
        self._btn_generate.clicked.connect(self._on_generate)
        right_layout.addWidget(self._btn_generate)

        self._btn_image_preview = QPushButton(tr("draw_img_preview_btn"))
        self._btn_image_preview.setMinimumHeight(36)
        self._btn_image_preview.clicked.connect(self._on_image_preview)
        self._btn_image_preview.setVisible(False)
        right_layout.addWidget(self._btn_image_preview)

        self._btn_image_generate = QPushButton(tr("draw_img_gen_btn"))
        self._btn_image_generate.setMinimumHeight(40)
        self._btn_image_generate.setStyleSheet(
            "QPushButton { background-color: #1a5276; color: white; font-weight: bold; "
            "padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2e86c1; }"
        )
        self._btn_image_generate.clicked.connect(self._on_image_generate)
        self._btn_image_generate.setVisible(False)
        right_layout.addWidget(self._btn_image_generate)

        self._btn_prepare = QPushButton(tr("draw_prepare_btn"))
        self._btn_prepare.setMinimumHeight(36)
        self._btn_prepare.clicked.connect(self._on_prepare)
        right_layout.addWidget(self._btn_prepare)

        self._btn_execute = QPushButton(tr("draw_execute_btn"))
        self._btn_execute.setMinimumHeight(36)
        self._btn_execute.clicked.connect(self._on_execute)
        right_layout.addWidget(self._btn_execute)

        self._btn_cri_minimal = QPushButton("CRI最小测试(Z±10mm)")
        self._btn_cri_minimal.setMinimumHeight(32)
        self._btn_cri_minimal.setToolTip(
            "读取当前 TCP 为起点，生成 Z 轴 ±10mm 往返轨迹；先移至起点再 CRI 执行"
        )
        self._btn_cri_minimal.clicked.connect(self._on_cri_minimal_test)
        right_layout.addWidget(self._btn_cri_minimal)

        self._btn_stop = QPushButton(tr("draw_stop_btn"))
        self._btn_stop.clicked.connect(self._on_stop)
        right_layout.addWidget(self._btn_stop)

        self._btn_preview = QPushButton(tr("draw_preview"))
        self._btn_preview.clicked.connect(self._on_preview)
        right_layout.addWidget(self._btn_preview)

        log_group = QGroupBox(tr("draw_log_title"))
        log_layout = QVBoxLayout(log_group)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        self._log.setStyleSheet(
            "QPlainTextEdit { background-color: #0d1117; color: #80c080; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 12px; }"
        )
        log_layout.addWidget(self._log)
        right_layout.addWidget(log_group, stretch=1)

        horiz = QHBoxLayout()
        horiz.setSpacing(8)
        horiz.addWidget(scroll, stretch=3)
        horiz.addWidget(right, stretch=1)
        root.addLayout(horiz)

        self._exec_service.log_message.connect(self._append_log)
        self._exec_service.error_occurred.connect(self._on_exec_error)
        self._exec_service.finished.connect(self._on_exec_finished)

        qc = Qt.ConnectionType.QueuedConnection
        self._image_service.generate_finished.connect(
            self._on_image_generate_finished, qc)
        self._image_service.generate_failed.connect(
            self._on_image_generate_failed, qc)
        self._image_service.busy_changed.connect(
            lambda _: self._update_action_buttons(), qc)

        self._restore_settings()
        self._on_draw_mode_changed()
        self._update_action_buttons()

    def on_enter(self):
        self._ensure_writing_service()

    def on_leave(self):
        self._save_settings()

    def on_connection_changed(self, connected: bool):
        self._update_action_buttons()

    def _append_log(self, msg: str):
        append_ui_log(self._log, msg, source="Drawing")

    def _is_connected(self) -> bool:
        return bool(self.sp and self.sp.cm.is_connected)

    def _robot_ip(self) -> str:
        return str(self._settings.value("login/robot_ip", "192.168.1.136")).strip()

    def _is_image_mode(self) -> bool:
        return self._mode_combo.currentData() == "image"

    def _update_action_buttons(self):
        has_traj = bool(self._last_traj_path and os.path.isfile(self._last_traj_path))
        conn = self._is_connected()
        busy_gen = bool(
            self._writing_service and self._writing_service.is_generating
        )
        busy_img = self._image_service.is_busy
        busy_exec = self._exec_service.is_busy
        busy = busy_gen or busy_exec or busy_img
        if self._is_image_mode():
            has_img = bool(self._image_path_edit.text().strip())
            self._btn_image_preview.setEnabled(has_img and not busy)
            self._btn_image_generate.setEnabled(has_img and not busy)
        else:
            self._btn_generate.setEnabled(not busy)
        self._btn_prepare.setEnabled(conn and has_traj and not busy)
        self._btn_execute.setEnabled(
            conn and has_traj and self._at_start_ready and not busy
        )
        self._btn_stop.setEnabled(busy_exec or busy_gen)
        if self._is_image_mode():
            can_preview = bool(
                (self._last_preview_path and os.path.isfile(self._last_preview_path))
                or (self._last_traj_path and os.path.isfile(self._last_traj_path))
            )
        else:
            can_preview = bool(self._last_preview_path)
        self._btn_preview.setEnabled(can_preview and not busy)

    def _ensure_writing_service(self):
        if self._writing_service is not None:
            return
        from services.writing_service import WritingService

        self._writing_service = WritingService(self, output_dir="output")
        self._writing_service.log_message.connect(self._append_log)
        self._writing_service.error_occurred.connect(
            lambda m: self._append_log(tr("draw_exec_failed").format(err=m))
        )
        self._writing_service.finished.connect(self._on_generate_finished)
        self._writing_service.preview_ready.connect(self._on_preview_ready)
        self._writing_service.state_changed.connect(lambda _: self._update_action_buttons())
        self._writing_service.generate_busy.connect(self._on_generate_busy)

    def _read_workspace(self) -> dict:
        def _rp(row):
            s = self._ws_spins[row]
            return RobotPoint(
                x=s[0].value(), y=s[1].value(), z=s[2].value(),
                rx=s[3].value(), ry=s[4].value(), rz=s[5].value(),
            )

        lt, rt, lb = _rp(0), _rp(1), _rp(2)
        rb = RobotPoint(
            x=lt.x + (rt.x - lt.x) + (lb.x - lt.x),
            y=lt.y + (rt.y - lt.y) + (lb.y - lt.y),
            z=lt.z + (rt.z - lt.z) + (lb.z - lt.z),
            rx=lt.rx, ry=lt.ry, rz=lt.rz,
        )
        return {"left_top": lt, "right_top": rt, "left_bottom": lb, "right_bottom": rb}

    def _current_font_item(self) -> dict:
        idx = self._font_combo.currentIndex()
        if idx < 0:
            return {}
        data = self._font_combo.itemData(idx)
        return data if isinstance(data, dict) else {}

    def _collect_font_path(self) -> str:
        return str(self._current_font_item().get("path", "") or "")

    def _current_hershey_style(self) -> str:
        if self._current_text_source() != TEXT_SOURCE_LATIN_STROKE:
            return get_default_hershey_style_id()
        return (
            self._current_font_item().get("hershey_style")
            or get_default_hershey_style_id()
        )

    def _exec_config(self) -> WritingExecConfig:
        cri_cfg = getattr(self.sp.cri, "_config", None)
        push_ip = getattr(cri_cfg, "local_ip", "") if cri_cfg else ""
        push_port = int(getattr(cri_cfg, "udp_port", 0) or 0) if cri_cfg else 0
        return WritingExecConfig(
            traj_path=self._last_traj_path,
            robot_ip=self._robot_ip(),
            write_speed_mm_s=self._spin_speed.value(),
            move_acc=self._spin_acc.value(),
            sample_rate_hz=self._spin_sample_rate.value(),
            filter_type=self._spin_filter.value(),
            start_buffer=self._spin_buffer.value(),
            cartesian=True,
            z_draw_mm=self._spin_z_work.value(),
            z_safe_mm=self._spin_z_safe.value(),
            cri_data_push_ip=push_ip,
            cri_data_push_port=push_port,
        )

    def _on_generate_busy(self):
        QMessageBox.warning(
            self,
            tr("draw_gen_busy_title"),
            tr("draw_gen_busy_msg"),
        )

    def _on_generate(self):
        self._ensure_writing_service()
        if self._writing_service.is_generating:
            self._on_generate_busy()
            return
        text = normalize_weld_text_input(self._text_input.toPlainText())
        if not text:
            self._append_log(tr("draw_need_text"))
            return
        text_source = self._current_text_source()
        pipeline = build_text_pipeline(text_source, target_process="drawing")
        self._append_log(
            f"text_pipeline: text_source={pipeline['text_source']} "
            f"target_process={pipeline.get('target_process', 'drawing')}"
        )
        if text_source == TEXT_SOURCE_LATIN_STROKE:
            sk_err = validate_weld_skeleton_text(
                text, lang=I18nManager.instance().lang,
            )
            if sk_err:
                self._append_log(sk_err)
                return
        self._save_settings()
        self._last_traj_path = ""
        self._last_points_path = ""
        self._last_preview_path = ""
        self._at_start_ready = False
        self._update_action_buttons()
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append_log(f"[{ts}] {tr('draw_gen_btn')}: {text.replace(chr(10), ' ↵ ')}")
        self._append_log(tr("draw_planning"))
        ws = self._read_workspace()
        z_safe = self._spin_z_safe.value()
        gen_kwargs = dict(
            text=text,
            text_source=text_source,
            left_top=ws["left_top"],
            right_top=ws["right_top"],
            left_bottom=ws["left_bottom"],
            char_height_mm=self._spin_char_h.value(),
            margin_left_mm=self._spin_margin_left.value(),
            margin_top_mm=self._spin_margin_top.value(),
            char_spacing_mm=self._spin_char_s.value(),
            line_spacing_mm=self._spin_line_s.value(),
            point_spacing_mm=self._spin_pt_space.value(),
            z_work_mm=self._spin_z_work.value(),
            z_safe_mm=z_safe,
            z_super_safe_mm=z_safe + self._spin_z_super.value(),
            write_speed_mm_s=self._spin_speed.value(),
            travel_speed_mm_s=self._spin_speed.value(),
            sample_rate_hz=self._spin_sample_rate.value(),
            px_per_mm=10.0,
            user_lang=I18nManager.instance().lang,
        )
        if text_source == TEXT_SOURCE_TTF_CONTOUR:
            gen_kwargs["font_path"] = self._collect_font_path() or None
        if text_source == TEXT_SOURCE_LATIN_STROKE:
            gen_kwargs["hershey_style"] = self._current_hershey_style()
        self._writing_service.start_generate(**gen_kwargs)
        self._update_action_buttons()

    def _on_generate_finished(self, traj_path: str, points_path: str, preview_path: str):
        self._last_traj_path = traj_path
        self._last_points_path = points_path
        self._last_preview_path = preview_path
        self._at_start_ready = False
        self._btn_preview.setEnabled(bool(preview_path))
        self._append_log(tr("draw_gen_done"))
        self._append_log(tr("draw_prepare_reset"))
        self._update_action_buttons()

    def _on_preview_ready(self, png_path: str):
        self._last_preview_path = png_path

    def _on_preview(self):
        if self._is_image_mode():
            if self._last_preview_path and os.path.isfile(self._last_preview_path):
                _open_path(self._last_preview_path)
            elif self._last_traj_path and os.path.isfile(self._last_traj_path):
                _open_path(os.path.dirname(self._last_traj_path))
            elif self._last_image_preview_dir and os.path.isdir(self._last_image_preview_dir):
                _open_path(self._last_image_preview_dir)
            else:
                self._append_log(tr("draw_need_traj"))
            return
        if self._last_preview_path and os.path.isfile(self._last_preview_path):
            _open_path(self._last_preview_path)
        elif self._last_traj_path:
            _open_path(os.path.dirname(self._last_traj_path))
        else:
            self._append_log(tr("draw_need_traj"))

    def _on_prepare(self):
        if not self._is_connected():
            self._append_log(tr("draw_need_connect"))
            return
        if not self._last_traj_path:
            self._append_log(tr("draw_need_traj"))
            return
        if self._exec_service.is_busy:
            self._append_log(tr("draw_busy"))
            return
        self._at_start_ready = False
        self._update_action_buttons()
        self._append_log(tr("draw_prepare_btn") + "...")
        self._exec_service.run_prepare(self._exec_config(), self.sp.cm, self.sp.cri)

    def _on_execute(self):
        if not self._is_connected():
            self._append_log(tr("draw_need_connect"))
            return
        if not self._last_traj_path:
            self._append_log(tr("draw_need_traj"))
            return
        if not self._at_start_ready:
            self._append_log(tr("draw_need_at_start"))
            QMessageBox.warning(self, tr("draw_execute_btn"), tr("draw_need_at_start"))
            return
        if self._exec_service.is_busy:
            self._append_log(tr("draw_busy"))
            return
        self._append_log(tr("draw_execute_btn") + "...")
        self._update_action_buttons()
        self._exec_service.run_execute(self._exec_config(), self.sp.cm, self.sp.cri)

    def _on_cri_minimal_test(self):
        if not self._is_connected():
            self._append_log(tr("draw_need_connect"))
            return
        if self._exec_service.is_busy:
            self._append_log(tr("draw_busy"))
            return
        from services.robot_realtime_state import RobotRealtimeState

        if not RobotRealtimeState.instance().is_cri_primary():
            self._append_log("CRI 最小测试需要 CRI UDP 实时位姿：请确认数据推送正常")
            return
        self._append_log("CRI 最小测试(Z±10mm, 先移至起点, 3s)...")
        self._update_action_buttons()
        self._exec_service.run_minimal_test(self._exec_config(), self.sp.cm, self.sp.cri)

    def _on_stop(self):
        self._exec_service.stop()

    def _on_exec_error(self, err: str):
        self._at_start_ready = False
        self._append_log(tr("draw_exec_failed").format(err=err))
        self._update_action_buttons()

    def _on_exec_finished(self, task: str):
        if task == "prepare":
            self._at_start_ready = True
            self._append_log(tr("draw_exec_prepare_done"))
        elif task == "execute":
            self._append_log(tr("draw_exec_done"))
        elif task == "minimal_test":
            self._append_log("CRI 最小测试(Z±10mm)完成")
        self._update_action_buttons()

    def _update_ws_from_current(self, row: int):
        from services.robot_realtime_state import PoseSource, RobotRealtimeState

        if not self._is_connected():
            self._append_log(tr("draw_need_connect"))
            return

        state = RobotRealtimeState.instance()
        read = state.read_pose_for_workspace_update()
        if read is None:
            self._append_log(tr("weld_log_no_pose_wait_subscribe"))
            return
        pose, source = read
        if source != PoseSource.CRI_UDP:
            ts = state.last_switch_to_subscribe_at()
            if ts:
                self._append_log(f"{tr('weld_log_cri_pose_subscribe')} ({ts})")
            else:
                self._append_log(tr("weld_log_cri_pose_subscribe"))
        x, y, z, rx, ry, rz = pose
        for j, v in enumerate((x, y, z, rx, ry, rz)):
            self._ws_spins[row][j].setValue(round(v, 3))
        self._append_log(tr("weld_log_ws_updated").format(
            corner=_corner_label(row), x=x, y=y, z=z, rx=rx, ry=ry, rz=rz,
        ))

    def _on_moveto_pressed(self, row: int):
        if self._moveto_active_row is not None:
            return
        if not self._is_connected():
            self._append_log(tr("draw_need_connect"))
            return
        spins = self._ws_spins[row]
        cp = [spins[i].value() for i in range(6)]
        self._moveto_active_row = row
        self.sp.cm.send_call(
            "Robot/moveTo",
            {"type": 5, "target": {"cp": cp, "jp": [], "ep": []}},
            on_response=lambda _: None,
            on_error=lambda e: self._append_log(tr("weld_log_moveto_failed").format(err=e)),
        )
        self._moveto_heartbeat = QTimer(self)
        self._moveto_heartbeat.setInterval(500)
        self._moveto_heartbeat.timeout.connect(
            lambda: self.sp.cm.send_call("Robot/moveToHeartbeat", {}, on_response=None, on_error=None)
        )
        self._moveto_heartbeat.start()

    def _on_moveto_released(self, row: int):
        if self._moveto_active_row != row:
            return
        self._moveto_active_row = None
        if self._moveto_heartbeat:
            self._moveto_heartbeat.stop()
            self._moveto_heartbeat.deleteLater()
            self._moveto_heartbeat = None
        if self._is_connected():
            self.sp.cm.send_call(
                "Robot/moveTo", {"type": -1},
                on_response=None, on_error=None,
            )

    def _copy_ws_point(self, row: int):
        spins = self._ws_spins[row]
        text = (
            f"[{spins[0].value():.3f},{spins[1].value():.3f},{spins[2].value():.3f},"
            f"{spins[3].value():.3f},{spins[4].value():.3f},{spins[5].value():.3f}]"
        )
        QApplication.clipboard().setText(text)
        self._append_log(tr("weld_log_copied").format(
            corner=_corner_label(row), text=text,
        ))

    def _restore_ws_defaults(self):
        defaults = [
            (100, 200, 300, 180, 0, 90),
            (300, 200, 300, 180, 0, 90),
            (100, 400, 300, 180, 0, 90),
        ]
        for row, defs in enumerate(defaults):
            for j, v in enumerate(defs):
                self._ws_spins[row][j].setValue(float(v))

    def _build_image_group(self) -> QGroupBox:
        group = QGroupBox(tr("draw_image_group"))
        layout = QVBoxLayout(group)

        disclaimer = QLabel(tr("draw_image_disclaimer"))
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(disclaimer)

        path_row = QHBoxLayout()
        self._image_path_edit = QLineEdit()
        self._image_path_edit.setReadOnly(True)
        self._image_path_edit.setPlaceholderText(tr("draw_image_path"))
        path_row.addWidget(self._image_path_edit, 1)
        pick_btn = QPushButton(tr("draw_image_pick"))
        pick_btn.clicked.connect(self._on_pick_image)
        path_row.addWidget(pick_btn)
        layout.addLayout(path_row)

        params_hint = QLabel(tr("draw_image_params_in_preview"))
        params_hint.setWordWrap(True)
        params_hint.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(params_hint)

        # 参数仅在「预览处理结果」对话框中编辑；此处隐藏容器用于保存/同步配置
        self._img_params = ImageParamsWidget(parent=group, show_mapping=True)
        self._img_params.setVisible(False)
        self._img_params.preset_selected.connect(self._on_image_preset_log)
        return group

    def _current_text_source(self) -> str:
        if self._is_image_mode():
            return TEXT_SOURCE_IMAGE_CONTOUR
        data = self._text_source_combo.currentData()
        if data in (TEXT_SOURCE_TTF_CONTOUR, TEXT_SOURCE_LATIN_STROKE, TEXT_SOURCE_HANZI_STROKE):
            return str(data)
        return TEXT_SOURCE_TTF_CONTOUR

    def _populate_draw_font_combo(self) -> None:
        self._font_combo.clear()
        lang = I18nManager.instance().lang
        ts = self._current_text_source()
        if ts == TEXT_SOURCE_LATIN_STROKE:
            self._font_label.setText(tr("draw_hershey_style") + ":")
            default_id = get_default_hershey_style_id()
            for preset in list_hershey_style_presets():
                data = build_hershey_style_item_data(preset, lang=lang)
                self._font_combo.addItem(data["display"], data)
            for i in range(self._font_combo.count()):
                d = self._font_combo.itemData(i)
                if isinstance(d, dict) and d.get("hershey_style") == default_id:
                    self._font_combo.setCurrentIndex(i)
                    break
        elif ts == TEXT_SOURCE_TTF_CONTOUR:
            self._font_label.setText(tr("draw_font") + ":")
            for fp in _find_system_fonts():
                item = _build_font_item_data(fp)
                self._font_combo.addItem(item["display"], item)
            if self._font_combo.count() == 0:
                self._font_combo.addItem("(no font)", {"path": "", "display": "(no font)"})
        else:
            self._font_combo.addItem(tr("draw_hanzi_not_implemented"), {"path": "", "display": ""})

    def _on_text_source_changed(self, _index: int = 0) -> None:
        self._populate_draw_font_combo()
        self._update_text_source_ui()

    def _update_text_source_ui(self) -> None:
        if self._is_image_mode():
            return
        ts = self._current_text_source()
        show_font = ts in (TEXT_SOURCE_TTF_CONTOUR, TEXT_SOURCE_LATIN_STROKE)
        self._font_combo.setVisible(show_font)
        self._font_label.setVisible(show_font)

    def _on_draw_mode_changed(self):
        image = self._is_image_mode()
        self._text_group.setVisible(not image)
        self._layout_group.setVisible(not image)
        self._image_group.setVisible(image)
        self._btn_generate.setVisible(not image)
        self._btn_image_preview.setVisible(image)
        self._btn_image_generate.setVisible(image)
        if hasattr(self, "_text_source_combo"):
            self._text_source_combo.parentWidget()
            self._text_source_combo.setEnabled(not image)
        self._settings.setValue(_SETTINGS_PREFIX + "source_mode", self._mode_combo.currentData())
        self._update_text_source_ui()
        self._update_action_buttons()

    def _on_pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("draw_image_pick"),
            str(self._image_path_edit.text() or ""),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All (*.*)",
        )
        if path:
            self._image_path_edit.setText(path)
            self._settings.setValue(_IMAGE_SETTINGS_PREFIX + "image_path", path)
            self._update_action_buttons()

    def _on_image_preset_log(self, preset_id: str) -> None:
        hint = image_presets.preset_beta_hint(str(preset_id))
        if hint:
            self._append_log(hint)

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _collect_image_process_config(self) -> ImageProcessConfig:
        return self._img_params.config()

    def _collect_image_drawing_config(self) -> ImageDrawingConfig:
        cfg = self._img_params.config()
        return ImageDrawingConfig(
            z_draw_mm=self._spin_z_work.value(),
            z_safe_mm=self._spin_z_safe.value(),
            point_spacing_mm=self._spin_pt_space.value(),
            travel_speed_mm_s=self._spin_speed.value(),
            draw_speed_mm_s=self._spin_speed.value(),
            margin_mm=self._img_params.margin_mm(),
            max_total_points=int(cfg.max_total_points),
            sample_rate_hz=int(self._spin_sample_rate.value()),
        )

    def _build_workplane(self) -> WorkPlane:
        ws = self._read_workspace()
        return WorkPlane(
            tl=ws["left_top"],
            tr=ws["right_top"],
            bl=ws["left_bottom"],
        )

    def _save_image_settings(self) -> None:
        import dataclasses
        import json

        p = _IMAGE_SETTINGS_PREFIX
        self._settings.setValue(p + "image_path", self._image_path_edit.text())
        self._settings.setValue(p + "preset", self._img_params.preset_id)
        cfg = self._img_params.config()
        self._settings.setValue(
            p + "config_json",
            json.dumps(dataclasses.asdict(cfg)),
        )
        self._settings.setValue(p + "contour_strategy", cfg.contour_strategy)
        self._settings.setValue(p + "fill_before_contour", cfg.fill_before_contour)
        self._settings.setValue(p + "keep_external_only", cfg.keep_external_only)
        self._settings.setValue(p + "fill_holes", cfg.fill_holes)
        self._settings.setValue(p + "margin_mm", self._img_params.margin_mm())

    def _restore_image_settings(self) -> None:
        import dataclasses
        import json

        p = _IMAGE_SETTINGS_PREFIX
        path = self._settings.value(p + "image_path")
        if path:
            self._image_path_edit.setText(str(path))
        preset = str(self._settings.value(p + "preset", image_presets.PRESET_LINEART))
        margin = _qsettings_float(self._settings.value(p + "margin_mm"), 0.0)
        raw = self._settings.value(p + "config_json")
        if raw:
            try:
                data = json.loads(str(raw))
                fields = {f.name for f in dataclasses.fields(ImageProcessConfig)}
                cfg = ImageProcessConfig(**{k: v for k, v in data.items() if k in fields})
            except (json.JSONDecodeError, TypeError, ValueError):
                cfg = image_presets.get_preset_config(preset)
        else:
            cfg = ImageProcessConfig(
                threshold_method=str(self._settings.value(p + "threshold_method", "adaptive")),
                threshold_value=_qsettings_int(self._settings.value(p + "threshold_value"), 127),
                blur_kernel=_qsettings_int(self._settings.value(p + "blur_kernel"), 3),
                morph_kernel_size=_qsettings_int(self._settings.value(p + "morph_kernel_size"), 2),
                invert=str(self._settings.value(p + "invert", "")).lower() in ("1", "true", "yes"),
                min_contour_area=_qsettings_float(self._settings.value(p + "min_contour_area"), 100.0),
                max_contours=_qsettings_int(self._settings.value(p + "max_contours"), 50),
                simplification_epsilon=_qsettings_float(
                    self._settings.value(p + "simplification_epsilon"), 1.5,
                ),
                max_total_points=_qsettings_int(self._settings.value(p + "max_total_points"), 20000),
                fit_mode=str(self._settings.value(p + "fit_mode", "contain")),
                contour_strategy=str(
                    self._settings.value(p + "contour_strategy", "external"),
                ),
                fill_before_contour=str(
                    self._settings.value(p + "fill_before_contour", "true"),
                ).lower() in ("1", "true", "yes"),
                keep_external_only=str(
                    self._settings.value(p + "keep_external_only", "true"),
                ).lower() in ("1", "true", "yes"),
                fill_holes=str(
                    self._settings.value(p + "fill_holes", "true"),
                ).lower() in ("1", "true", "yes"),
            )
        self._img_params.set_config(cfg, preset_id=preset, block_signals=True)
        self._img_params.set_margin_mm(margin)

    def _on_image_preview(self):
        path = self._image_path_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._append_log(tr("draw_img_need_path"))
            return
        self._save_image_settings()
        dlg = ImagePreviewDialog(
            path,
            self._collect_image_process_config(),
            preset_id=self._img_params.preset_id,
            margin_mm=self._img_params.margin_mm(),
            parent=self,
        )
        if dlg.exec():
            dlg.sync_to_page(self)
            self._save_image_settings()
            self._append_log(
                tr("draw_img_preview_done").format(
                    contours=dlg.last_stroke_count,
                    points=dlg.last_points_px,
                )
            )
            self._append_log(tr("draw_img_hint_fragmented"))
            self._append_log(tr("draw_img_hint_invert"))
            for msg in contour_strategy_log_messages(self._img_params.config()):
                self._append_log(msg)
            hint = image_presets.preset_beta_hint(self._img_params.preset_id)
            if hint:
                self._append_log(hint)
        self._update_action_buttons()

    def _on_image_generate(self):
        path = self._image_path_edit.text().strip()
        if not path or not os.path.isfile(path):
            self._append_log(tr("draw_img_need_path"))
            return
        if self._image_service.is_busy:
            self._append_log(tr("draw_img_busy"))
            return
        if self._writing_service and self._writing_service.is_generating:
            self._on_generate_busy()
            return
        self._save_settings()
        self._last_traj_path = ""
        self._last_points_path = ""
        self._last_preview_path = ""
        self._at_start_ready = False
        self._append_log(tr("draw_img_gen_planning"))
        out_dir = os.path.join(
            _IMAGE_RUN_DIR,
            datetime.now().strftime("%Y%m%d_%H%M%S"),
        )
        if not self._image_service.start_generate(
            path,
            self._build_workplane(),
            self._collect_image_process_config(),
            self._collect_image_drawing_config(),
            out_dir,
        ):
            self._append_log(tr("draw_img_busy"))
        self._update_action_buttons()

    def _on_image_generate_finished(self, payload: dict):
        files = payload.get("files", {})
        traj = files.get("trajectory_cri.txt", "")
        preview = files.get("preview_execution.png", "")
        self._last_traj_path = traj
        self._last_preview_path = preview
        self._last_image_preview_dir = str(payload.get("output_dir", "") or "")
        contour_png = files.get("preview_image_contours.png", "")
        self._last_image_contour_preview = contour_png if contour_png else ""
        self._at_start_ready = False
        self._append_log(tr("draw_img_gen_done"))
        self._append_log(tr("draw_prepare_reset"))
        for w in payload.get("warnings", []):
            self._append_log(f"[warn] {w}")
        if preview and os.path.isfile(preview):
            self._btn_preview.setEnabled(True)
        self._update_action_buttons()

    def _on_image_generate_failed(self, err: str):
        self._append_log(tr("draw_exec_failed").format(err=err))
        self._update_action_buttons()

    def _save_settings(self):
        p = _SETTINGS_PREFIX
        self._settings.setValue(p + "source_mode", self._mode_combo.currentData())
        if hasattr(self, "_text_source_combo"):
            self._settings.setValue(p + "text_source", self._text_source_combo.currentData())
        if self._current_text_source() == TEXT_SOURCE_LATIN_STROKE:
            self._settings.setValue(p + "hershey_style", self._current_hershey_style())
        self._settings.setValue(p + "text", self._text_input.toPlainText())
        self._settings.setValue(p + "font_index", self._font_combo.currentIndex())
        self._settings.setValue(p + "char_height_mm", self._spin_char_h.value())
        self._settings.setValue(p + "margin_left_mm", self._spin_margin_left.value())
        self._settings.setValue(p + "margin_top_mm", self._spin_margin_top.value())
        self._settings.setValue(p + "char_spacing_mm", self._spin_char_s.value())
        self._settings.setValue(p + "line_spacing_mm", self._spin_line_s.value())
        self._settings.setValue(p + "z_work_mm", self._spin_z_work.value())
        self._settings.setValue(p + "z_safe_mm", self._spin_z_safe.value())
        self._settings.setValue(p + "z_super_extra_mm", self._spin_z_super.value())
        self._settings.setValue(p + "point_spacing_mm", self._spin_pt_space.value())
        self._settings.setValue(p + "sample_rate_hz", self._spin_sample_rate.value())
        self._settings.setValue(p + "speed_mm_s", self._spin_speed.value())
        self._settings.setValue(p + "acc_mm_s2", self._spin_acc.value())
        self._settings.setValue(p + "cri_filter", self._spin_filter.value())
        self._settings.setValue(p + "cri_buffer", self._spin_buffer.value())
        for i, row in enumerate(self._ws_spins):
            for j, spin in enumerate(row):
                self._settings.setValue(f"{p}ws_{i}_{j}", spin.value())
        self._save_image_settings()

    def _restore_settings(self):
        p = _SETTINGS_PREFIX
        mode = self._settings.value(p + "source_mode", "text")
        self._set_combo_by_data(self._mode_combo, str(mode))
        if hasattr(self, "_text_source_combo"):
            ts = migrate_welding_text_source(
                text_source=str(self._settings.value(p + "text_source", "") or ""),
                legacy_mode="contour",
            )
            self._set_combo_by_data(self._text_source_combo, ts)
            self._populate_draw_font_combo()
        text = self._settings.value(p + "text")
        if text:
            self._text_input.setPlainText(str(text))
        fi = _qsettings_int(self._settings.value(p + "font_index"), 0)
        if 0 <= fi < self._font_combo.count():
            self._font_combo.setCurrentIndex(fi)
        self._update_text_source_ui()
        self._spin_char_h.setValue(_qsettings_float(self._settings.value(p + "char_height_mm"), CHAR_HEIGHT_MM))
        self._spin_margin_left.setValue(_qsettings_float(self._settings.value(p + "margin_left_mm"), MARGIN_LEFT_MM))
        self._spin_margin_top.setValue(_qsettings_float(self._settings.value(p + "margin_top_mm"), MARGIN_TOP_MM))
        self._spin_char_s.setValue(_qsettings_float(self._settings.value(p + "char_spacing_mm"), CHAR_SPACING_MM))
        self._spin_line_s.setValue(_qsettings_float(self._settings.value(p + "line_spacing_mm"), LINE_SPACING_MM))
        self._spin_z_work.setValue(_qsettings_float(self._settings.value(p + "z_work_mm"), 305.0))
        self._spin_z_safe.setValue(_qsettings_float(self._settings.value(p + "z_safe_mm"), 315.0))
        self._spin_z_super.setValue(_qsettings_float(self._settings.value(p + "z_super_extra_mm"), 10.0))
        self._spin_pt_space.setValue(_qsettings_float(self._settings.value(p + "point_spacing_mm"), 0.5))
        self._spin_sample_rate.setValue(_qsettings_int(self._settings.value(p + "sample_rate_hz"), 500))
        self._spin_speed.setValue(_qsettings_float(self._settings.value(p + "speed_mm_s"), 50.0))
        self._spin_acc.setValue(_qsettings_float(self._settings.value(p + "acc_mm_s2"), 200.0))
        self._spin_filter.setValue(_qsettings_int(self._settings.value(p + "cri_filter"), 1))
        self._spin_buffer.setValue(_qsettings_int(self._settings.value(p + "cri_buffer"), 5))
        for i, row in enumerate(self._ws_spins):
            for j, spin in enumerate(row):
                v = self._settings.value(f"{p}ws_{i}_{j}")
                if v is not None:
                    spin.setValue(float(v))
        self._restore_image_settings()
