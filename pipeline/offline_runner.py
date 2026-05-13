"""Phase 8.2: OfflinePipelineRunner — 端到端离线 Pipeline 封装

单一 runner 类，封装从文字输入到文件输出的全链路调用。
纯 Python，无 Qt/PySide6，无 CRI，无 Lua。

用法:
    from pipeline.offline_runner import OfflinePipelineRunner, RunResult
    from pipeline.mapping import WorkPlane
    from core.types import RobotPoint

    wp = WorkPlane(
        RobotPoint(0, 0, 100, -180, 0, -135),
        RobotPoint(200, 0, 100, -180, 0, -135),
        RobotPoint(0, 100, 100, -180, 0, -135),
    )
    runner = OfflinePipelineRunner(output_dir="output")
    result = runner.run("Abc", mode="contour", workplane=wp)
"""

from __future__ import annotations

import json as _json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.types import PathConfig, WeldingProcessConfig, WorkspaceConfig
from pipeline.raster import get_default_font_path, render_char


# ── 结果数据类 ──

@dataclass
class StageStats:
    name: str
    status: str = "ok"
    stats: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class RunResult:
    ok: bool
    text: str
    mode: str
    output_dir: str
    files: dict[str, str]
    stage_stats: list[StageStats]
    total_strokes_raw: int = 0
    total_strokes_mapped: int = 0
    total_segments: int = 0
    total_robot_points: int = 0
    duration_ms: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ── 固定输出文件名 ──
POINTS_FILENAME = "points.txt"
JOB_FILENAME = "job.json"
STROKES_PREVIEW = "preview_strokes.png"
SEGMENTS_PREVIEW = "preview_segments.png"
COMBINED_PREVIEW = "preview_combined.png"
SUMMARY_FILENAME = "summary.json"


class OfflinePipelineRunner:
    """离线 Pipeline 端到端运行器。

    输入: text / mode / workplane / output_dir
    输出: 固定目录结构
    """

    def __init__(
        self,
        output_dir: str = "output",
        font_path: str | None = None,
        font_size_px: int = 600,
        canvas_w_px: float = 600.0,
        canvas_h_px: float = 600.0,
        px_per_mm: float = 10.0,
        y_flip: bool = True,
        path_config: PathConfig | None = None,
        process_config: WeldingProcessConfig | None = None,
        workspace_config: WorkspaceConfig | None = None,
        char_spacing_mm: float = 2.0,
    ):
        self.output_dir = output_dir
        self.font_path = font_path or get_default_font_path()
        self.font_size_px = font_size_px
        self.canvas_w_px = canvas_w_px
        self.canvas_h_px = canvas_h_px
        self.y_flip = y_flip
        self.px_per_mm = px_per_mm
        self.char_spacing_mm = char_spacing_mm
        self.path_config = path_config or PathConfig()
        self.process_config = process_config or WeldingProcessConfig()
        self.workspace_config = workspace_config or WorkspaceConfig()

    def run(
        self, text: str, mode: str, workplane: Any,
        *, extra_metadata: dict | None = None,
    ) -> RunResult:
        t_start = datetime.now()
        stage_stats: list[StageStats] = []
        warnings: list[str] = []
        errors: list[str] = []

        # 输出子目录
        # 过滤非法文件名字符（仅保留 alnum + _ - .）
        safe_text = "".join(c if c.isalnum() or c in "_-." else "_" for c in text)[:30]
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(self.output_dir, f"{ts}_{safe_text}_{mode}")
        os.makedirs(run_dir, exist_ok=True)
        files: dict[str, str] = {}

        # ── Stage 1-2: render + extract ──
        try:
            from pipeline.vision import ContourExtractor, SkeletonExtractor
            from core.types import PixelPoint
            strokes_raw = []
            ch_counts: dict[str, int] = {}
            x_cursor_px = 0.0
            for ch in text:
                binary = render_char(ch, self.font_path, self.font_size_px)
                if mode == "contour":
                    ext = ContourExtractor()
                    strokes = ext.extract(binary, config=self.path_config)
                elif mode == "skeleton":
                    strokes, _ = SkeletonExtractor.extract(binary, config=self.path_config, backend="auto")
                else:
                    raise ValueError(f"unknown mode: {mode!r}")
                # 字符排版：累加水平偏移
                if x_cursor_px > 0:
                    for s in strokes:
                        s.points_px = [PixelPoint(x=p.x + x_cursor_px, y=p.y) for p in s.points_px]
                char_w_px = binary.shape[1]
                spacing_px = self.char_spacing_mm * self.px_per_mm
                x_cursor_px += char_w_px + spacing_px
                for s in strokes:
                    assert len(s.points_px) >= 2
                strokes_raw.extend(strokes)
                ch_counts[ch] = len(strokes)
            stage_stats.append(StageStats(name="extract", status="ok",
                stats={"chars": len(text), "strokes": len(strokes_raw), "per_char": ch_counts}))
        except Exception as exc:
            errors.append(f"extract: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        if not strokes_raw:
            errors.append("no strokes extracted")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 3: clean ──
        try:
            from pipeline.path import clean_and_resample_strokes
            strokes_cl, s3 = clean_and_resample_strokes(strokes_raw, px_per_mm=self.px_per_mm, config=self.path_config)
            stage_stats.append(StageStats(name="clean", status="ok", stats=s3))
        except Exception as exc:
            errors.append(f"clean: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 4: refine ──
        try:
            from pipeline.path import AdaptivePathRefiner
            strokes_rf, s4 = AdaptivePathRefiner.refine_strokes(strokes_cl, self.path_config, px_per_mm=self.px_per_mm)
            stage_stats.append(StageStats(name="refine", status="ok", stats=s4))
        except Exception as exc:
            errors.append(f"refine: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 5: schedule ──
        try:
            from pipeline.path import PathScheduler
            strokes_sc, s5 = PathScheduler.schedule(strokes_rf, strategy="nearest", allow_reverse=True)
            stage_stats.append(StageStats(name="schedule", status="ok", stats=s5))
        except Exception as exc:
            errors.append(f"schedule: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 6: map ──
        try:
            from pipeline.mapping import PoseMapper

            # bbox 归一化：多字符 pixel 缩放/平移到 WorkPlane 内
            map_w, map_h = self.canvas_w_px, self.canvas_h_px
            source_bbox = None
            strokes_to_map = strokes_sc
            if strokes_sc:
                from core.types import PixelPoint
                all_x = [p.x for s in strokes_sc for p in s.points_px]
                all_y = [p.y for s in strokes_sc for p in s.points_px]
                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)
                bbox_w = max_x - min_x
                bbox_h = max_y - min_y
                source_bbox = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}

                # 平移到原点
                import copy as _copy
                strokes_to_map = []
                for s in strokes_sc:
                    pts = [PixelPoint(x=p.x - min_x, y=p.y - min_y) for p in s.points_px]
                    import dataclasses
                    strokes_to_map.append(dataclasses.replace(s, points_px=pts))

                if bbox_w > 0 and bbox_h > 0:
                    map_w, map_h = bbox_w, bbox_h

            if self.y_flip and map_h > 0:
                strokes_to_map = _flip_strokes_y(strokes_to_map, map_h)
            strokes_mp, s6 = PoseMapper.map_strokes(strokes_to_map, workplane, map_w, map_h)
            if source_bbox:
                s6["source_bbox_px"] = source_bbox
                s6["normalized_canvas_w"] = round(map_w, 1)
                s6["normalized_canvas_h"] = round(map_h, 1)
            stage_stats.append(StageStats(name="map", status="ok", stats=s6))
        except Exception as exc:
            errors.append(f"map: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 7: plan ──
        try:
            from pipeline.process import WeldingProcessPlanner
            segs, s7 = WeldingProcessPlanner.plan(
                strokes_mp, self.process_config,
                workplane=workplane, workspace_cfg=self.workspace_config,
            )
            stage_stats.append(StageStats(name="plan", status="ok", stats=s7))
        except Exception as exc:
            errors.append(f"plan: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── Stage 8: export ──
        try:
            from pipeline.output import PointsWriter, JobWriter, DebugExporter
            pt = str(Path(run_dir) / POINTS_FILENAME)
            jb = str(Path(run_dir) / JOB_FILENAME)
            PointsWriter.write_points_txt(segs, pt, workplane=workplane)
            JobWriter.write_job_json(jb,
                input_info={"text": text, "mode": mode},
                configs={"process": self.process_config, "path": self.path_config, "workspace": self.workspace_config},
                workplane=workplane, strokes=strokes_mp, segments=segs,
                export_files={"points_txt": pt, "job_json": jb},
                stage_stats={s.name: s.stats for s in stage_stats},
                metadata=extra_metadata,
            )
            DebugExporter.write_run_preview(strokes_mp, segs, run_dir,
                                            title_prefix=f"{text} ({mode})")

            files["points_txt"] = pt
            files["job_json"] = jb
            files["strokes_preview_png"] = str(Path(run_dir) / STROKES_PREVIEW)
            files["segments_preview_png"] = str(Path(run_dir) / SEGMENTS_PREVIEW)
            files["combined_preview_png"] = str(Path(run_dir) / COMBINED_PREVIEW)
            stage_stats.append(StageStats(name="export", status="ok"))
        except Exception as exc:
            errors.append(f"export: {exc}")
            return _fail(text, mode, run_dir, stage_stats, errors)

        # ── 汇总 ──
        total_rp = sum(len(s.points) for s in segs)
        dur = (datetime.now() - t_start).total_seconds() * 1000
        summary = {
            "pipeline_version": "8.2b",
            "text": text,
            "mode": mode,
            "ok": True,
            "duration_ms": round(dur, 1),
            "stats": {"strokes_raw": len(strokes_raw), "strokes_mapped": len(strokes_mp),
                      "segments": len(segs), "robot_points": total_rp},
            "output_files": {k: os.path.basename(v) for k, v in files.items()},
            "stage_stats": [{"name": s.name, "status": s.status, "stats": s.stats}
                           for s in stage_stats],
            "warnings": warnings,
            "errors": errors,
        }
        spath = str(Path(run_dir) / SUMMARY_FILENAME)
        with open(spath, "w", encoding="utf-8") as f:
            _json.dump(summary, f, ensure_ascii=False, indent=2)
        files["summary_json"] = spath

        return RunResult(
            ok=True, text=text, mode=mode, output_dir=run_dir, files=files,
            stage_stats=stage_stats, total_strokes_raw=len(strokes_raw),
            total_strokes_mapped=len(strokes_mp), total_segments=len(segs),
            total_robot_points=total_rp, duration_ms=dur,
            warnings=warnings, errors=errors,
        )


def _flip_strokes_y(strokes, canvas_h):
    """复制 Stroke 列表并翻转 points_px 的 y 坐标（Y↓ → Y↑）。

    pixel(0,0) → (0, canvas_h); pixel(0, canvas_h) → (0, 0).
    不改原始 Stroke。
    """
    import copy
    from core.types import PixelPoint, Stroke as _Stroke
    result = []
    for s in strokes:
        flipped_px = [PixelPoint(x=p.x, y=canvas_h - p.y) for p in s.points_px]
        # 用 dataclasses.replace 保持所有元数据
        import dataclasses
        ns = dataclasses.replace(s, points_px=flipped_px)
        result.append(ns)
    return result


def _fail(text, mode, run_dir, stages, errors):
    s = {"pipeline_version": "8.2b", "text": text, "mode": mode, "ok": False,
         "duration_ms": 0, "output_files": {},
         "stage_stats": [{"name": x.name, "status": x.status, "error": x.error} for x in stages],
         "warnings": [], "errors": errors}
    sp = str(Path(run_dir) / SUMMARY_FILENAME)
    with open(sp, "w", encoding="utf-8") as f:
        _json.dump(s, f, ensure_ascii=False, indent=2)
    return RunResult(ok=False, text=text, mode=mode, output_dir=run_dir,
        files={"summary_json": sp}, stage_stats=stages, errors=errors)
