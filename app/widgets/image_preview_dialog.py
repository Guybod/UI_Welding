"""图片预处理实时预览对话框 — 上预览、下参数滑块。"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.widgets.image_params_widget import ImageParamsWidget
from core.types import ImageProcessConfig
from pipeline.vision.image_preprocessor import process_image


def _ndarray_to_pixmap(img: np.ndarray) -> QPixmap:
    if img is None or img.size == 0:
        return QPixmap()
    if len(img.shape) == 2:
        h, w = img.shape
        buf = np.ascontiguousarray(img)
        qimg = QImage(buf.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class ZoomImageView(QWidget):
    """等比显示图片，滑块/滚轮缩放 + 左键拖动平移。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._source = QPixmap()
        self._zoom = 1.0
        self._dragging = False
        self._drag_start_global = None
        self._drag_scroll_origin = (0, 0)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(tr("draw_img_zoom")))
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(10, 800)
        self._zoom_slider.setValue(100)
        self._zoom_slider.valueChanged.connect(self._on_slider)
        bar.addWidget(self._zoom_slider, 1)
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(44)
        bar.addWidget(self._zoom_label)
        fit_btn = QPushButton(tr("draw_img_zoom_fit"))
        fit_btn.clicked.connect(self.fit_to_viewport)
        bar.addWidget(fit_btn)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        self._scroll.setStyleSheet("QScrollArea { background: #f0f0f0; border: 1px solid #ccc; }")
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scroll.setWidget(self._label)
        vp = self._scroll.viewport()
        vp.installEventFilter(self)
        vp.setMouseTracking(True)
        vp.setCursor(Qt.CursorShape.OpenHandCursor)
        root.addWidget(self._scroll, stretch=1)

    def set_pixmap(self, pixmap: QPixmap, *, fit: bool = True) -> None:
        self._source = pixmap if pixmap is not None else QPixmap()
        if self._source.isNull():
            self._label.clear()
            return
        if fit:
            self.fit_to_viewport()
        else:
            self._apply_zoom(self._zoom)

    def fit_to_viewport(self) -> None:
        if self._source.isNull():
            return
        vw = max(self._scroll.viewport().width() - 8, 40)
        vh = max(self._scroll.viewport().height() - 8, 40)
        pw = max(self._source.width(), 1)
        ph = max(self._source.height(), 1)
        scale = min(vw / pw, vh / ph)
        self._set_zoom(scale)

    def _on_slider(self, pct: int) -> None:
        self._set_zoom(pct / 100.0)

    def eventFilter(self, obj, event) -> bool:
        vp = self._scroll.viewport()
        if obj is not vp:
            return super().eventFilter(obj, event)

        et = event.type()
        if et == QEvent.Type.Wheel:
            self._wheel_zoom(event)
            return True

        if et == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and not self._source.isNull():
                self._dragging = True
                self._drag_start_global = event.globalPosition().toPoint()
                h = self._scroll.horizontalScrollBar()
                v = self._scroll.verticalScrollBar()
                self._drag_scroll_origin = (h.value(), v.value())
                vp.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True

        if et == QEvent.Type.MouseMove and self._dragging:
            cur = event.globalPosition().toPoint()
            dx = cur.x() - self._drag_start_global.x()
            dy = cur.y() - self._drag_start_global.y()
            ox, oy = self._drag_scroll_origin
            self._scroll.horizontalScrollBar().setValue(ox - dx)
            self._scroll.verticalScrollBar().setValue(oy - dy)
            return True

        if et == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._dragging:
                self._dragging = False
                self._drag_start_global = None
                vp.setCursor(Qt.CursorShape.OpenHandCursor)
                return True

        return super().eventFilter(obj, event)

    def _wheel_zoom(self, event: QWheelEvent) -> None:
        if self._source.isNull():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else 1.0 / 1.12
        self._set_zoom(self._zoom * factor)

    def _set_zoom(self, scale: float) -> None:
        scale = max(0.1, min(8.0, scale))
        self._zoom = scale
        pct = int(round(scale * 100))
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(pct)
        self._zoom_slider.blockSignals(False)
        self._zoom_label.setText(f"{pct}%")
        self._apply_zoom(scale)

    def _apply_zoom(self, scale: float) -> None:
        if self._source.isNull():
            return
        w = max(1, int(round(self._source.width() * scale)))
        h = max(1, int(round(self._source.height() * scale)))
        scaled = self._source.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(scaled)
        self._label.resize(scaled.size())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._source.isNull():
            return
        if self._zoom_slider.value() == 100 or abs(self._zoom - 1.0) < 0.02:
            QTimer.singleShot(0, self.fit_to_viewport)


class _PreviewWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, image_path: str, cfg: ImageProcessConfig):
        super().__init__()
        self._path = image_path
        self._cfg = cfg

    def run(self):
        try:
            result = process_image(self._path, self._cfg)
            if not result.ok:
                self.failed.emit(result.error or "preprocess failed")
                return
            points = sum(len(s.points_px) for s in result.strokes_px)
            self.finished.emit({
                "binary": result.binary_image,
                "contour": result.contour_preview_image,
                "original": result.original_image,
                "stroke_count": len(result.strokes_px),
                "total_points_px": points,
                "warnings": list(result.warnings),
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class ImagePreviewDialog(QDialog):
    """图片调参预览：参数变化后防抖刷新二值/轮廓预览。"""

    def __init__(
        self,
        image_path: str,
        initial: ImageProcessConfig,
        *,
        preset_id: str | None = None,
        margin_mm: float = 0.0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._thread: QThread | None = None
        self._worker: _PreviewWorker | None = None
        self._busy = False
        self._pending = False
        self.last_stroke_count = 0
        self.last_points_px = 0
        self._margin_mm = float(margin_mm)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(220)
        self._debounce.timeout.connect(self._run_preview)

        self.setWindowTitle(tr("draw_img_preview_dlg_title"))
        self.resize(920, 720)

        root = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._view_original = ZoomImageView()
        self._view_binary = ZoomImageView()
        self._view_contour = ZoomImageView()
        for view in (self._view_original, self._view_binary, self._view_contour):
            view.setMinimumHeight(340)
        self._tabs.addTab(self._view_original, tr("draw_img_preview_tab_original"))
        self._tabs.addTab(self._view_binary, tr("draw_img_preview_tab_binary"))
        self._tabs.addTab(self._view_contour, tr("draw_img_preview_tab_contours"))
        root.addWidget(self._tabs, stretch=3)

        self._status = QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(400)
        self._params = ImageParamsWidget(show_mapping=True, compact=True)
        self._params.config_changed.connect(self._schedule_refresh)
        scroll.setWidget(self._params)
        root.addWidget(scroll, stretch=2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._params.set_config(initial, preset_id=preset_id or "", block_signals=True)
        self._params.set_margin_mm(self._margin_mm)
        QTimer.singleShot(50, self._run_preview)

    def config(self) -> ImageProcessConfig:
        return self._params.config()

    def sync_to_page(self, page) -> None:
        page._img_params.set_config(
            self._params.config(),
            preset_id=self._params.preset_id,
            block_signals=True,
        )
        page._img_params.set_margin_mm(self._params.margin_mm())

    def _schedule_refresh(self):
        self._debounce.start()

    def _run_preview(self):
        if self._busy:
            self._pending = True
            return
        self._pending = False
        self._busy = True
        self._status.setText(tr("draw_img_previewing"))

        cfg = self._params.config()
        thread = QThread(self)
        worker = _PreviewWorker(self._image_path, cfg)
        worker.moveToThread(thread)

        def _ok(payload: dict):
            self._apply_preview(payload)
            thread.quit()

        def _fail(err: str):
            self._status.setText(tr("draw_exec_failed").format(err=err))
            thread.quit()

        worker.finished.connect(_ok, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(_fail, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _on_thread_finished(self):
        self._thread = None
        self._worker = None
        self._busy = False
        if self._pending:
            self._run_preview()

    def _apply_preview(self, payload: dict):
        self.last_stroke_count = int(payload.get("stroke_count", 0))
        self.last_points_px = int(payload.get("total_points_px", 0))
        orig = payload.get("original")
        binary = payload.get("binary")
        contour = payload.get("contour")
        if orig is not None:
            self._view_original.set_pixmap(_ndarray_to_pixmap(orig))
        if binary is not None:
            self._view_binary.set_pixmap(_ndarray_to_pixmap(binary))
        if contour is not None:
            self._view_contour.set_pixmap(_ndarray_to_pixmap(contour))
        self._status.setText(
            tr("draw_img_preview_status").format(
                contours=payload.get("stroke_count", 0),
                points=payload.get("total_points_px", 0),
            )
        )
        warns = payload.get("warnings") or []
        if warns:
            self._status.setText(self._status.text() + "  " + "; ".join(warns[:2]))

    def closeEvent(self, event):
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(event)
