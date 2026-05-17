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


def _set_tip(widget: QWidget, tip_key: str) -> None:
    text = tr(tip_key)
    if text:
        widget.setToolTip(text)


def _form_row(form: QFormLayout, label_key: str, widget: QWidget, tip_key: str) -> None:
    label = QLabel(tr(label_key))
    _set_tip(label, tip_key)
    _set_tip(widget, tip_key)
    form.addRow(label, widget)


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
        self._step_groups: list[QGroupBox] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ── 预设（无流程开关）──
        preset_box = QGroupBox(tr("draw_image_preset"))
        preset_form = QFormLayout(preset_box)
        self._preset = QComboBox()
        for pid in image_presets.list_preset_ids():
            self._preset.addItem(tr(_PRESET_TR[pid]), pid)
        _set_tip(self._preset, "draw_tip_preset")
        self._preset.currentIndexChanged.connect(self._on_preset)
        preset_form.addRow(tr("draw_image_preset"), self._preset)
        root.addWidget(preset_box)

        # ── ① 预处理 ──
        pre_box, pre = self._add_step_group(
            root, "draw_img_step_preprocess", "draw_tip_step_preprocess",
        )
        self._step_preprocess_box = pre_box

        self._contrast = QDoubleSpinBox()
        self._contrast.setRange(0.3, 3.0)
        self._contrast.setSingleStep(0.05)
        self._contrast.setValue(1.0)
        self._contrast.setDecimals(2)
        _form_row(pre, "draw_img_contrast", self._contrast, "draw_tip_contrast")

        self._brightness = QSpinBox()
        self._brightness.setRange(-100, 100)
        _form_row(pre, "draw_img_brightness", self._brightness, "draw_tip_brightness")

        self._median = QComboBox()
        for v in (0, 3, 5, 7):
            self._median.addItem(str(v), v)
        _form_row(pre, "draw_img_median_blur", self._median, "draw_tip_median")

        self._blur = QComboBox()
        for v in (0, 3, 5, 7, 9, 11):
            self._blur.addItem(str(v), v)
        _form_row(pre, "draw_image_blur", self._blur, "draw_tip_blur")

        self._gauss_sigma = QDoubleSpinBox()
        self._gauss_sigma.setRange(0.0, 10.0)
        self._gauss_sigma.setDecimals(1)
        self._gauss_sigma.setSingleStep(0.5)
        self._gauss_sigma.setSpecialValueText(tr("draw_img_auto"))
        _form_row(pre, "draw_img_gauss_sigma", self._gauss_sigma, "draw_tip_gauss_sigma")

        self._sharpen = QDoubleSpinBox()
        self._sharpen.setRange(0.0, 3.0)
        self._sharpen.setDecimals(2)
        self._sharpen.setSingleStep(0.1)
        self._sharpen.setSpecialValueText(tr("draw_img_off"))
        _form_row(pre, "draw_img_sharpen", self._sharpen, "draw_tip_sharpen")

        self._sharpen_sigma = QDoubleSpinBox()
        self._sharpen_sigma.setRange(0.5, 5.0)
        self._sharpen_sigma.setValue(1.0)
        self._sharpen_sigma.setDecimals(1)
        _form_row(pre, "draw_img_sharpen_sigma", self._sharpen_sigma, "draw_tip_sharpen_sigma")

        # ── ② 二值化 ──
        th_box, th = self._add_step_group(
            root, "draw_img_step_binarize", "draw_tip_step_binarize",
        )
        self._step_binarize_box = th_box

        self._thresh_method = QComboBox()
        for mid in ("fixed", "adaptive", "otsu"):
            self._thresh_method.addItem(mid, mid)
        _form_row(th, "draw_image_threshold_method", self._thresh_method, "draw_tip_thresh_method")

        self._thresh_value = QSpinBox()
        self._thresh_value.setRange(0, 255)
        self._thresh_value.setValue(127)
        _form_row(th, "draw_image_threshold_value", self._thresh_value, "draw_tip_thresh_value")

        self._adaptive_block = QSpinBox()
        self._adaptive_block.setRange(3, 99)
        self._adaptive_block.setSingleStep(2)
        self._adaptive_block.setValue(11)
        _form_row(th, "draw_img_adaptive_block", self._adaptive_block, "draw_tip_adaptive_block")

        self._adaptive_c = QSpinBox()
        self._adaptive_c.setRange(-20, 20)
        self._adaptive_c.setValue(2)
        _form_row(th, "draw_img_adaptive_c", self._adaptive_c, "draw_tip_adaptive_c")

        self._edge_mode = QComboBox()
        self._edge_mode.addItem(tr("draw_img_edge_none"), "none")
        self._edge_mode.addItem(tr("draw_img_edge_canny"), "canny")
        _form_row(th, "draw_img_edge_mode", self._edge_mode, "draw_tip_edge_mode")

        self._canny_low = QSpinBox()
        self._canny_low.setRange(0, 255)
        self._canny_low.setValue(50)
        _form_row(th, "draw_img_canny_low", self._canny_low, "draw_tip_canny_low")

        self._canny_high = QSpinBox()
        self._canny_high.setRange(0, 255)
        self._canny_high.setValue(150)
        _form_row(th, "draw_img_canny_high", self._canny_high, "draw_tip_canny_high")

        self._invert = QCheckBox(tr("draw_image_invert"))
        _set_tip(self._invert, "draw_tip_invert")
        th.addRow("", self._invert)

        # ── ③ 形态学 ──
        morph_box, morph = self._add_step_group(
            root, "draw_img_step_morphology", "draw_tip_step_morphology",
        )
        self._step_morphology_box = morph_box

        self._morph_mode = QComboBox()
        for mode_id, key in (
            ("none", "draw_img_morph_none"),
            ("close", "draw_img_morph_close_only"),
            ("open", "draw_img_morph_open_only"),
            ("open_close", "draw_img_morph_open_close"),
            ("close_open", "draw_img_morph_close_open"),
        ):
            self._morph_mode.addItem(tr(key), mode_id)
        self._morph_mode.currentIndexChanged.connect(self._on_morph_mode_changed)
        _form_row(morph, "draw_img_morph_mode", self._morph_mode, "draw_tip_morph_mode")

        self._morph_close = QComboBox()
        self._morph_open = QComboBox()
        for v in (0, 2, 3, 5, 7):
            self._morph_close.addItem(str(v), v)
            self._morph_open.addItem(str(v), v)
        _form_row(morph, "draw_img_morph_close", self._morph_close, "draw_tip_morph_close")
        _form_row(morph, "draw_img_morph_open", self._morph_open, "draw_tip_morph_open")
        self._on_morph_mode_changed()

        # ── ④ 区域 Mask ──
        mask_box, mask_form = self._add_step_group(
            root, "draw_img_step_region_mask", "draw_tip_step_region_mask",
        )
        self._step_region_mask_box = mask_box

        self._fill_before = QCheckBox(tr("draw_img_fill_before"))
        self._fill_before.setChecked(True)
        _set_tip(self._fill_before, "draw_tip_fill_before")
        mask_form.addRow("", self._fill_before)

        self._fill_holes = QCheckBox(tr("draw_img_fill_holes"))
        self._fill_holes.setChecked(True)
        _set_tip(self._fill_holes, "draw_tip_fill_holes")
        mask_form.addRow("", self._fill_holes)

        # ── ⑤ 轮廓提取 ──
        ext_box, ext = self._add_step_group(
            root, "draw_img_step_contour_extract", "draw_tip_step_contour_extract",
        )
        self._step_contour_extract_box = ext_box

        self._contour_strategy = QComboBox()
        self._contour_strategy.addItem(tr("draw_img_strategy_external"), "external")
        self._contour_strategy.addItem(tr("draw_img_strategy_all"), "all")
        self._contour_strategy.addItem(tr("draw_img_strategy_centerline"), "centerline_beta")
        self._contour_strategy.currentIndexChanged.connect(self._on_contour_strategy_changed)
        _form_row(ext, "draw_img_contour_strategy", self._contour_strategy, "draw_tip_contour_strategy")

        self._strategy_hint = QLabel(tr("draw_img_strategy_external_hint"))
        self._strategy_hint.setWordWrap(True)
        self._strategy_hint.setStyleSheet("color: #666; font-size: 11px;")
        ext.addRow("", self._strategy_hint)

        self._keep_external = QCheckBox(tr("draw_img_keep_external"))
        _set_tip(self._keep_external, "draw_tip_keep_external")
        ext.addRow("", self._keep_external)

        self._contour_dedup = QCheckBox(tr("draw_img_contour_dedup"))
        self._contour_dedup.setChecked(True)
        _set_tip(self._contour_dedup, "draw_tip_contour_dedup")
        ext.addRow("", self._contour_dedup)

        # ── ⑥ 轮廓筛选 ──
        filt_box, ct = self._add_step_group(
            root, "draw_img_step_contour_filter", "draw_tip_step_contour_filter",
        )
        self._step_contour_filter_box = filt_box

        if compact:
            self._min_area = QSpinBox()
            self._min_area.setRange(0, 500_000)
            self._min_area.setValue(100)
            _form_row(ct, "draw_image_min_area", self._min_area, "draw_tip_min_area")
        else:
            self._min_area_slider = QSlider(Qt.Orientation.Horizontal)
            self._min_area_slider.setRange(0, 5000)
            self._min_area_slider.setValue(100)
            self._min_area_lbl = QLabel("100")
            row = QHBoxLayout()
            row.addWidget(self._min_area_slider, 1)
            row.addWidget(self._min_area_lbl)
            self._min_area_slider.valueChanged.connect(
                lambda v: self._min_area_lbl.setText(str(v))
            )
            min_lbl = QLabel(tr("draw_image_min_area"))
            _set_tip(min_lbl, "draw_tip_min_area")
            _set_tip(self._min_area_slider, "draw_tip_min_area")
            ct.addRow(min_lbl, row)
            self._min_area = None

        self._max_contours = QSpinBox()
        self._max_contours.setRange(1, 500)
        _form_row(ct, "draw_image_max_contours", self._max_contours, "draw_tip_max_contours")

        self._simplify = QDoubleSpinBox()
        self._simplify.setRange(0.1, 50.0)
        self._simplify.setDecimals(2)
        _form_row(ct, "draw_image_simplify", self._simplify, "draw_tip_simplify")

        self._max_points = QSpinBox()
        self._max_points.setRange(100, 500_000)
        _form_row(ct, "draw_image_max_points", self._max_points, "draw_tip_max_points")

        # ── ⑦ 工作区映射（生成轨迹时）──
        if show_mapping:
            map_box, mp = self._add_step_group(
                root, "draw_img_step_mapping", "draw_tip_step_mapping",
            )
            self._step_mapping_box = map_box
            self._fit = QComboBox()
            self._fit.addItem(tr("draw_image_fit_contain"), "contain")
            self._fit.addItem(tr("draw_image_fit_stretch"), "stretch")
            _form_row(mp, "draw_image_fit_mode", self._fit, "draw_tip_fit_mode")
            self._margin = QDoubleSpinBox()
            self._margin.setRange(0, 200)
            self._margin.setSuffix(" mm")
            _form_row(mp, "draw_image_margin", self._margin, "draw_tip_margin")
        else:
            self._step_mapping_box = None
            self._fit = None
            self._margin = None

        for w in self._all_inputs():
            self._connect_change(w)

        self._on_contour_strategy_changed()

    def _add_step_group(
        self, root: QVBoxLayout, title_key: str, tip_key: str,
    ) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(tr(title_key))
        box.setCheckable(True)
        box.setChecked(True)
        _set_tip(box, tip_key)
        form = QFormLayout(box)
        root.addWidget(box)
        box.toggled.connect(lambda checked, b=box: self._on_step_group_toggled(b, checked))
        self._step_groups.append(box)
        return box, form

    def _on_morph_mode_changed(self) -> None:
        mode = str(self._morph_mode.currentData() or "close_open")
        need_close = mode in ("close", "open_close", "close_open")
        need_open = mode in ("open", "open_close", "close_open")
        self._morph_close.setEnabled(need_close)
        self._morph_open.setEnabled(need_open)
        self._emit_changed()

    def _on_step_group_toggled(self, box: QGroupBox, checked: bool) -> None:
        lay = box.layout()
        if lay is None:
            return
        for i in range(lay.count()):
            item = lay.itemAt(i)
            w = item.widget()
            if w is not None and w is not box:
                w.setEnabled(checked)
            sub = item.layout()
            if sub is not None:
                for j in range(sub.count()):
                    sw = sub.itemAt(j).widget()
                    if sw is not None:
                        sw.setEnabled(checked)
        self._emit_changed()

    def _all_inputs(self):
        widgets = [
            self._contrast, self._brightness, self._median, self._blur,
            self._gauss_sigma, self._sharpen, self._sharpen_sigma,
            self._thresh_method, self._thresh_value, self._adaptive_block,
            self._adaptive_c, self._edge_mode, self._canny_low, self._canny_high,
            self._invert, self._morph_mode, self._morph_close, self._morph_open,
            self._fill_before, self._fill_holes,
            self._max_contours, self._simplify, self._max_points, self._keep_external,
            self._contour_strategy, self._contour_dedup,
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

    def _on_contour_strategy_changed(self) -> None:
        strategy = str(self._contour_strategy.currentData() or "external")
        hints = {
            "external": tr("draw_img_strategy_external_hint"),
            "all": tr("draw_img_strategy_all_hint"),
            "centerline_beta": tr("draw_img_strategy_centerline_hint"),
        }
        self._strategy_hint.setText(hints.get(strategy, hints["external"]))
        if strategy == "external":
            self._keep_external.setChecked(True)
            self._keep_external.setEnabled(False)
        elif strategy == "centerline_beta":
            self._keep_external.setChecked(True)
            self._keep_external.setEnabled(False)
        else:
            self._keep_external.setChecked(False)
            if self._step_contour_extract_box.isChecked():
                self._keep_external.setEnabled(True)
        self._emit_changed()

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
        strategy = str(self._contour_strategy.currentData() or "external")
        if strategy == "external" or strategy == "centerline_beta":
            keep_ext = True
        else:
            keep_ext = self._keep_external.isChecked()

        return ImageProcessConfig(
            threshold_method=str(self._thresh_method.currentData()),
            threshold_value=int(self._thresh_value.value()),
            blur_kernel=int(self._blur.currentData()),
            morph_mode=str(self._morph_mode.currentData() or "close_open"),
            morph_kernel_size=int(self._morph_close.currentData()),
            morph_open_size=int(self._morph_open.currentData()),
            invert=self._invert.isChecked(),
            min_contour_area=min_area,
            max_contours=int(self._max_contours.value()),
            simplification_epsilon=float(self._simplify.value()),
            max_total_points=int(self._max_points.value()),
            fit_mode=str(self._fit.currentData()) if self._fit else "contain",
            contour_strategy=strategy,
            fill_before_contour=self._fill_before.isChecked(),
            fill_holes=self._fill_holes.isChecked(),
            keep_external_only=keep_ext,
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
            step_preprocess=self._step_preprocess_box.isChecked(),
            step_binarize=self._step_binarize_box.isChecked(),
            step_morphology=self._step_morphology_box.isChecked(),
            step_region_mask=self._step_region_mask_box.isChecked(),
            step_contour_extract=self._step_contour_extract_box.isChecked(),
            step_contour_dedup=self._contour_dedup.isChecked(),
            step_contour_filter=self._step_contour_filter_box.isChecked(),
            step_mapping=(
                self._step_mapping_box.isChecked()
                if self._step_mapping_box is not None
                else True
            ),
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
        block = self._all_inputs() + [self._preset] + self._step_groups
        if self._step_mapping_box is not None:
            block.append(self._step_mapping_box)
        if block_signals:
            for w in block:
                w.blockSignals(True)
        if preset_id:
            self._set_combo_data(self._preset, preset_id)

        self._step_preprocess_box.setChecked(getattr(cfg, "step_preprocess", True))
        self._step_binarize_box.setChecked(getattr(cfg, "step_binarize", True))
        self._step_morphology_box.setChecked(getattr(cfg, "step_morphology", True))
        self._step_region_mask_box.setChecked(getattr(cfg, "step_region_mask", True))
        self._step_contour_extract_box.setChecked(getattr(cfg, "step_contour_extract", True))
        self._step_contour_filter_box.setChecked(getattr(cfg, "step_contour_filter", True))
        if self._step_mapping_box is not None:
            self._step_mapping_box.setChecked(getattr(cfg, "step_mapping", True))
        self._contour_dedup.setChecked(getattr(cfg, "step_contour_dedup", True))

        for box in self._step_groups:
            self._on_step_group_toggled(box, box.isChecked())

        self._set_combo_data(self._thresh_method, cfg.threshold_method)
        self._thresh_value.setValue(int(cfg.threshold_value))
        self._set_combo_data(self._blur, cfg.blur_kernel)
        self._set_combo_data(
            self._morph_mode,
            getattr(cfg, "morph_mode", "close_open"),
        )
        self._on_morph_mode_changed()
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
        self._set_combo_data(self._contour_strategy, cfg.contour_strategy)
        self._fill_before.setChecked(cfg.fill_before_contour)
        self._fill_holes.setChecked(cfg.fill_holes)
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
        self._on_contour_strategy_changed()
        if block_signals:
            for w in block:
                w.blockSignals(False)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
