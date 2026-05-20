"""图片模式后台任务 — 预览预处理 / 生成 CRI 轨迹（无机器人执行）。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Qt, Signal

from core.logger import log
from core.types import ImageDrawingConfig, ImageProcessConfig
from pipeline.image_runner import run_image_to_cri
from pipeline.mapping.workplane import WorkPlane
from pipeline.vision.image_preprocessor import process_image, write_image_debug_previews


class _PreviewWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, image_path: str, cfg: ImageProcessConfig, output_dir: str):
        super().__init__()
        self._image_path = image_path
        self._cfg = cfg
        self._output_dir = output_dir

    def run(self):
        log.info("[ImageDrawing] preview start image=%s", self._image_path)
        try:
            result = process_image(self._image_path, self._cfg)
            if not result.ok:
                log.error("[ImageDrawing] preview failed: %s", result.error)
                self.failed.emit(result.error or "preprocess failed")
                return
            paths = write_image_debug_previews(result, self._output_dir)
            points = sum(len(s.points_px) for s in result.strokes_px)
            log.info(
                "[ImageDrawing] preview done strokes=%d points=%d",
                len(result.strokes_px), points,
            )
            self.finished.emit({
                "paths": paths,
                "stats": result.stats,
                "stroke_count": len(result.strokes_px),
                "total_points_px": points,
                "warnings": list(result.warnings),
            })
        except Exception as exc:
            log.exception("[ImageDrawing] preview exception: %s", exc)
            self.failed.emit(str(exc))


class _GenerateWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        image_path: str,
        workplane: WorkPlane,
        image_cfg: ImageProcessConfig,
        drawing_cfg: ImageDrawingConfig,
        output_dir: str,
    ):
        super().__init__()
        self._image_path = image_path
        self._workplane = workplane
        self._image_cfg = image_cfg
        self._drawing_cfg = drawing_cfg
        self._output_dir = output_dir

    def run(self):
        log.info(
            "[ImageDrawing] generate start image=%s output_dir=%s",
            self._image_path, self._output_dir,
        )
        try:
            run = run_image_to_cri(
                self._image_path,
                self._workplane,
                self._image_cfg,
                self._drawing_cfg,
                self._output_dir,
            )
            if not run.ok:
                log.error("[ImageDrawing] generate failed: %s", run.error)
                self.failed.emit(run.error or "image run failed")
                return
            log.info(
                "[ImageDrawing] generate done output_dir=%s files=%d",
                run.output_dir, len(run.files),
            )
            self.finished.emit({
                "files": dict(run.files),
                "stats": run.stats,
                "warnings": list(run.warnings),
                "output_dir": run.output_dir,
            })
        except Exception as exc:
            log.exception("[ImageDrawing] generate exception: %s", exc)
            self.failed.emit(str(exc))


class ImageDrawingService(QObject):
    """图片模式：仅文件生成，不连接 CRI 执行。"""

    preview_finished = Signal(dict)
    preview_failed = Signal(str)
    generate_finished = Signal(dict)
    generate_failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._busy = False

    @property
    def is_busy(self) -> bool:
        return self._busy

    def _set_busy(self, busy: bool):
        self._busy = busy
        self.busy_changed.emit(busy)

    def _start_worker(self, worker: QObject, on_ok, on_fail):
        if self._busy:
            return False
        self._set_busy(True)
        thread = QThread(self)
        worker.moveToThread(thread)

        def _wrap_ok(payload):
            try:
                on_ok(payload)
            finally:
                thread.quit()

        def _wrap_fail(err: str):
            try:
                on_fail(err)
            finally:
                thread.quit()

        worker.finished.connect(_wrap_ok, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(_wrap_fail, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_done)
        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def _on_thread_done(self):
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def start_preview(
        self,
        image_path: str,
        cfg: ImageProcessConfig,
        output_dir: str | Path,
    ) -> bool:
        if self._busy:
            return False
        log.info("[ImageDrawing] start_preview image=%s", image_path)
        worker = _PreviewWorker(image_path, cfg, str(output_dir))
        return self._start_worker(
            worker,
            self._on_preview_ok,
            self._on_preview_fail,
        )

    def start_generate(
        self,
        image_path: str,
        workplane: WorkPlane,
        image_cfg: ImageProcessConfig,
        drawing_cfg: ImageDrawingConfig,
        output_dir: str | Path,
    ) -> bool:
        if self._busy:
            return False
        log.info("[ImageDrawing] start_generate image=%s output_dir=%s", image_path, output_dir)
        worker = _GenerateWorker(
            image_path, workplane, image_cfg, drawing_cfg, str(output_dir),
        )
        return self._start_worker(
            worker,
            self._on_generate_ok,
            self._on_generate_fail,
        )

    def _on_preview_ok(self, payload: dict):
        self.preview_finished.emit(payload)

    def _on_preview_fail(self, err: str):
        log.error("[ImageDrawing] preview_failed: %s", err)
        self.preview_failed.emit(err)

    def _on_generate_ok(self, payload: dict):
        self.generate_finished.emit(payload)

    def _on_generate_fail(self, err: str):
        log.error("[ImageDrawing] generate_failed: %s", err)
        self.generate_failed.emit(err)
