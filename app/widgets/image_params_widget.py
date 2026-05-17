"""图片预处理参数面板 — 主页面与预览对话框共用。"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from core.types import ImageProcessConfig
from pipeline.vision import image_presets

_PRESET_TR = {
    image_presets.PRESET_LINEART: "draw_preset_lineart",
    image_presets.PRESET_SILHOUETTE: "draw_preset_silhouette",
    image_presets.PRESET_PHOTO_EDGE_BETA: "draw_preset_photo_edge",
    image_presets.PRESET_PHOTO_COMPLEX_BETA: "draw_preset_photo_complex",
}


class ImageParamsWidget(QWidget):
    """图像处理参数表单；变更时发出 config_changed。"""

    config_changed = Signal()
    preset_selected = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        show_mapping: bool = False,
        compact: bool = False,
    ):
        super().__init__(parent)
        self._show_mapping = show_mapping
        self._compact = compact
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ── 预设 ──
        preset_box = QGroupBox(tr("draw_image_preset"))
        preset_form = QFormLayout(preset_box)
        self._preset = QComboBox()
        for pid in image_presets.list_preset_ids():
            self._preset.addItem(tr(_PRESET_TR[pid]), pid)
        self._preset.currentIndexChanged.connect(self._on_preset)
        preset_form.addRow(tr("draw_image_preset"), self._preset)
        root.addWidget(preset_box)

        # ── 预处理 ──
        pre_box = QGroupBox(tr("draw_img_grp_preprocess"))
        pre = QFormLayout(pre_box)

        self._contrast = QDoubleSpinBox()
        self._contrast.setRange(0.3, 3.0)
        self._contrast.setSingleStep(0.05)
        self._contrast.setValue(1.0)
        self._contrast.setDecimals(2)
        pre.addRow(tr("draw_img_contrast"), self._contrast)

        self._brightness = QSpinBox()
        self._brightness.setRange(-100, 100)
        pre.addRow(tr("draw_img_brightness"), self._brightness)

        self._median = QComboBox()
        for v in (0, 3, 5, 7):
            self._median.addItem(str(v), v)
        pre.addRow(tr("draw_img_median_blur"), self._median)

        self._blur = QComboBox()
        for v in (0, 3, 5, 7, 9, 11):
            self._blur.addItem(str(v), v)
        pre.addRow(tr("draw_image_blur"), self._blur)

        self._gauss_sigma = QDoubleSpinBox()
        self._gauss_sigma.setRange(0.0, 10.0)
        self._gauss_sigma.setDecimals(1)
        self._gauss_sigma.setSingleStep(0.5)
        self._gauss_sigma.setSpecialValueText(tr("draw_img_auto"))
        pre.addRow(tr("draw_img_gauss_sigma"), self._gauss_sigma)

        self._sharpen = QDoubleSpinBox()
        self._sharpen.setRange(0.0, 3.0)
        self._sharpen.setDecimals(2)
        self._sharpen.setSingleStep(0.1)
        self._sharpen.setSpecialValueText(tr("draw_img_off"))
        pre.addRow(tr("draw_img_sharpen"), self._sharpen)

        self._sharpen_sigma = QDoubleSpinBox()
        self._sharpen_sigma.setRange(0.5, 5.0)
        self._sharpen_sigma.setValue(1.0)
        self._sharpen_sigma.setDecimals(1)
        pre.addRow(tr("draw_img_sharpen_sigma"), self._sharpen_sigma)

        root.addWidget(pre_box)

        # ── 二值化 / 边缘 ──
        th_box = QGroupBox(tr("draw_img_grp_threshold"))
        th = QFormLayout(th_box)

        self._thresh_method = QComboBox()
        for mid in ("fixed", "adaptive", "otsu"):
            self._thresh_method.addItem(mid, mid)
        th.addRow(tr("draw_image_threshold_method"), self._thresh_method)

        self._thresh_value = QSpinBox()
        self._thresh_value.setRange(0, 255)
        self._thresh_value.setValue(127)
        th.addRow(tr("draw_image_threshold_value"), self._thresh_value)

        self._adaptive_block = QSpinBox()
        self._adaptive_block.setRange(3, 99)
        self._adaptive_block.setSingleStep(2)
        self._adaptive_block.setValue(11)
        th.addRow(tr("draw_img_adaptive_block"), self._adaptive_block)

        self._adaptive_c = QSpinBox()
        self._adaptive_c.setRange(-20, 20)
        self._adaptive_c.setValue(2)
        th.addRow(tr("draw_img_adaptive_c"), self._adaptive_c)

        self._edge_mode = QComboBox()
        self._edge_mode.addItem(tr("draw_img_edge_none"), "none")
        self._edge_mode.addItem(tr("draw_img_edge_canny"), "canny")
        th.addRow(tr("draw_img_edge_mode"), self._edge_mode)

        self._canny_low = QSpinBox()
        self._canny_low.setRange(0, 255)
        self._canny_low.setValue(50)
        th.addRow(tr("draw_img_canny_low"), self._canny_low)

        self._canny_high = QSpinBox()
        self._canny_high.setRange(0, 255)
        self._canny_high.setValue(150)
        th.addRow(tr("draw_img_canny_high"), self._canny_high)

        self._invert = QCheckBox(tr("draw_image_invert"))
        th.addRow("", self._invert)

        root.addWidget(th_box)

        # ── 形态学 ──
        morph_box = QGroupBox(tr("draw_img_grp_morph"))
        morph = QFormLayout(morph_box)
        self._morph_close = QComboBox()
        self._morph_open = QComboBox()
        for v in (0, 2, 3, 5, 7):
            self._morph_close.addItem(str(v), v)
            self._morph_open.addItem(str(v), v)
        morph.addRow(tr("draw_img_morph_close"), self._morph_close)
        morph.addRow(tr("draw_img_morph_open"), self._morph_open)
        root.addWidget(morph_box)

        # ── 轮廓 ──
        ct_box = QGroupBox(tr("draw_img_grp_contour"))
        ct = QFormLayout(ct_box)

        if compact:
            self._min_area = QSpinBox()
            self._min_area.setRange(0, 500_000)
            self._min_area.setValue(100)
            ct.addRow(tr("draw_image_min_area"), self._min_area)
        else:
            self._min_area_slider = QSlider(Qt.Orientation.Horizontal)
            self._min_area_slider.setRange(0, 5000)
            self._min_area_lbl = QLabel("100")
            row = QHBoxLayout()
            row.addWidget(self._min_area_slider, 1)
            row.addWidget(self._min_area_lbl)
            self._min_area_slider.valueChanged.connect(
                lambda v: self._min_area_lbl.setText(str(v))
            )
            ct.addRow(tr("draw_image_min_area"), row)
            self._min_area = None

        self._max_contours = QSpinBox()
        self._max_contours.setRange(1, 500)
        ct.addRow(tr("draw_image_max_contours"), self._max_contours)

        self._simplify = QDoubleSpinBox()
        self._simplify.setRange(0.1, 50.0)
        self._simplify.setDecimals(2)
        ct.addRow(tr("draw_image_simplify"), self._simplify)

        self._max_points = QSpinBox()
        self._max_points.setRange(100, 500_000)
        ct.addRow(tr("draw_image_max_points"), self._max_points)

        self._keep_external = QCheckBox(tr("draw_img_keep_external"))
        ct.addRow("", self._keep_external)

        root.addWidget(ct_box)

        if show_mapping:
            map_box = QGroupBox(tr("draw_img_grp_mapping"))
            mp = QFormLayout(map_box)
            self._fit = QComboBox()
            self._fit.addItem(tr("draw_image_fit_contain"), "contain")
            self._fit.addItem(tr("draw_image_fit_stretch"), "stretch")
            mp.addRow(tr("draw_image_fit_mode"), self._fit)
            self._margin = QDoubleSpinBox()
            self._margin.setRange(0, 200)
            self._margin.setSuffix(" mm")
            mp.addRow(tr("draw_image_margin"), self._margin)
            root.addWidget(map_box)
        else:
            self._fit = None
            self._margin = None

        for w in self._all_inputs():
            self._connect_change(w)

    def _all_inputs(self):
        widgets = [
            self._contrast, self._brightness, self._median, self._blur,
            self._gauss_sigma, self._sharpen, self._sharpen_sigma,
            self._thresh_method, self._thresh_value, self._adaptive_block,
            self._adaptive_c, self._edge_mode, self._canny_low, self._canny_high,
            self._invert, self._morph_close, self._morph_open,
            self._max_contours, self._simplify, self._max_points, self._keep_external,
        ]
        if self._min_area is not None:
            widgets.append(self._min_area)
        else:
            widgets.append(self._min_area_slider)
        if self._fit is not None:
            widgets.extend([self._fit, self._margin])
        return widgets

    def _connect_change(self, w):
        if isinstance(w, QComboBox):
            w.currentIndexChanged.connect(self._emit_changed)
        elif isinstance(w, QCheckBox):
            w.toggled.connect(self._emit_changed)
        elif isinstance(w, QSlider):
            w.valueChanged.connect(self._emit_changed)
        else:
            w.valueChanged.connect(self._emit_changed)

    def _emit_changed(self, *_args):
        self.config_changed.emit()

    def _on_preset(self):
        pid = str(self._preset.currentData())
        cfg = image_presets.get_preset_config(pid)
        self.set_config(cfg, preset_id=pid, block_signals=True)
        self.preset_selected.emit(pid)
        self.config_changed.emit()

    def set_preset_id(self, preset_id: str) -> None:
        self._set_combo_data(self._preset, preset_id)

    def config(self) -> ImageProcessConfig:
        min_area = (
            float(self._min_area.value())
            if self._min_area is not None
            else float(self._min_area_slider.value())
        )
        return ImageProcessConfig(
            threshold_method=str(self._thresh_method.currentData()),
            threshold_value=int(self._thresh_value.value()),
            blur_kernel=int(self._blur.currentData()),
            morph_kernel_size=int(self._morph_close.currentData()),
            morph_open_size=int(self._morph_open.currentData()),
            invert=self._invert.isChecked(),
            min_contour_area=min_area,
            max_contours=int(self._max_contours.value()),
            simplification_epsilon=float(self._simplify.value()),
            max_total_points=int(self._max_points.value()),
            fit_mode=str(self._fit.currentData()) if self._fit else "contain",
            keep_external_only=self._keep_external.isChecked(),
            contrast=float(self._contrast.value()),
            brightness=int(self._brightness.value()),
            median_blur_kernel=int(self._median.currentData()),
            gaussian_sigma=float(self._gauss_sigma.value()),
            sharpen_amount=float(self._sharpen.value()),
            sharpen_sigma=float(self._sharpen_sigma.value()),
            adaptive_block_size=int(self._adaptive_block.value()),
            adaptive_c=int(self._adaptive_c.value()),
            edge_mode=str(self._edge_mode.currentData()),
            canny_low=int(self._canny_low.value()),
            canny_high=int(self._canny_high.value()),
        )

    @property
    def preset_id(self) -> str:
        return str(self._preset.currentData() or image_presets.PRESET_LINEART)

    def margin_mm(self) -> float:
        return float(self._margin.value()) if self._margin else 0.0

    def set_margin_mm(self, v: float) -> None:
        if self._margin:
            self._margin.setValue(v)

    def set_config(
        self,
        cfg: ImageProcessConfig,
        *,
        preset_id: str | None = None,
        block_signals: bool = False,
    ) -> None:
        block = self._all_inputs() + [self._preset]
        if block_signals:
            for w in block:
                w.blockSignals(True)
        if preset_id:
            self._set_combo_data(self._preset, preset_id)
        self._set_combo_data(self._thresh_method, cfg.threshold_method)
        self._thresh_value.setValue(int(cfg.threshold_value))
        self._set_combo_data(self._blur, cfg.blur_kernel)
        self._set_combo_data(self._morph_close, cfg.morph_kernel_size)
        self._set_combo_data(self._morph_open, cfg.morph_open_size)
        self._invert.setChecked(cfg.invert)
        if self._min_area is not None:
            self._min_area.setValue(int(cfg.min_contour_area))
        else:
            self._min_area_slider.setValue(int(cfg.min_contour_area))
            self._min_area_lbl.setText(str(int(cfg.min_contour_area)))
        self._max_contours.setValue(int(cfg.max_contours))
        self._simplify.setValue(float(cfg.simplification_epsilon))
        self._max_points.setValue(int(cfg.max_total_points))
        self._keep_external.setChecked(cfg.keep_external_only)
        self._contrast.setValue(float(cfg.contrast))
        self._brightness.setValue(int(cfg.brightness))
        self._set_combo_data(self._median, cfg.median_blur_kernel)
        self._gauss_sigma.setValue(float(cfg.gaussian_sigma))
        self._sharpen.setValue(float(cfg.sharpen_amount))
        self._sharpen_sigma.setValue(float(cfg.sharpen_sigma))
        self._adaptive_block.setValue(int(cfg.adaptive_block_size) | 1)
        self._adaptive_c.setValue(int(cfg.adaptive_c))
        self._set_combo_data(self._edge_mode, cfg.edge_mode)
        self._canny_low.setValue(int(cfg.canny_low))
        self._canny_high.setValue(int(cfg.canny_high))
        if self._fit:
            self._set_combo_data(self._fit, cfg.fit_mode)
        if block_signals:
            for w in block:
                w.blockSignals(False)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
