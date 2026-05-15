"""Phase 7.3 Debug PNG / Preview 导出 — Stroke/ProcessSegment 可视化

DebugExporter: 静态 PNG 预览生成。matplotlib Agg backend。
纯渲染层，不做坐标计算。不生成 Lua/UI/CRI。
"""

from pathlib import Path as _Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.types import Stroke, ProcessSegment

# Segment 类型 → 颜色
_SEG_COLORS = {
    "travel":   "gray",
    "lead_in":  "green",
    "weld":     "blue",
    "overlap":  "red",
    "lead_out": "orange",
    "retreat":  "gray",
}

# Stroke 类型 → 颜色
_STROKE_COLORS = {
    "contour":  "blue",
    "skeleton": "darkgreen",
    "image":    "purple",
}


class DebugExporter:
    """Debug PNG 预览导出器。

    用法:
        exporter = DebugExporter()
        stats = exporter.write_strokes_preview(strokes, "output/strokes.png")
        stats = exporter.write_segments_preview(segments, "output/segments.png")
        stats = exporter.write_combined_preview(strokes, segs, "output/combined.png")
    """

    @staticmethod
    def write_strokes_preview(
        strokes: list[Stroke],
        output_path: str | _Path,
        *,
        title: str = "Stroke Paths",
        show_order: bool = True,
        canvas_w: float | None = None,
        canvas_h: float | None = None,
    ) -> dict:
        """绘制 Stroke 像素路径预览。

        Returns:
            stats dict
        """
        fig, ax = plt.subplots(figsize=(10, 10))
        warnings_list: list[str] = []
        point_count = 0

        for i, s in enumerate(strokes):
            if not s.points_px:
                warnings_list.append(f"stroke {s.id[:6]}: empty points_px, skipped")
                continue

            xs = [p.x for p in s.points_px]
            ys = [p.y for p in s.points_px]
            point_count += len(xs)

            color = _STROKE_COLORS.get(s.source_type, "black")
            linestyle = "--" if s.is_hole else "-"
            if s.closed:
                xs.append(xs[0])
                ys.append(ys[0])

            ax.plot(xs, ys, linestyle, color=color, lw=1.0,
                    label=f"{i}:{s.id[:6]}({s.source_type})")

            if show_order and len(xs) >= 1:
                ax.annotate(str(i), (xs[0], ys[0]),
                           textcoords="offset points", xytext=(3, 3),
                           fontsize=7, color=color)
            if len(xs) >= 2:
                ax.plot(xs[0], ys[0], "go", ms=4)  # start
                ax.plot(xs[-1], ys[-1], "rx", ms=4)  # end

        ax.set_title(title)
        ax.set_xlabel("px")
        ax.set_ylabel("px")
        ax.invert_yaxis()
        if canvas_w and canvas_h:
            ax.set_xlim(0, canvas_w)
            ax.set_ylim(canvas_h, 0)
        if len(strokes) <= 10:
            ax.legend(fontsize=7, loc="upper right")

        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "stroke_count": len(strokes),
            "point_count": point_count,
            "warnings": warnings_list,
        }

    @staticmethod
    def write_segments_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        title: str = "Process Segments",
        show_order: bool = True,
        show_arc_state: bool = True,
    ) -> dict:
        """绘制 ProcessSegment 机器人路径预览（x/y 俯视图）。

        Returns:
            stats dict
        """
        fig, ax = plt.subplots(figsize=(10, 10))
        warnings_list: list[str] = []
        point_count = 0

        for i, seg in enumerate(segments):
            if not seg.points:
                continue
            xs = [p.x for p in seg.points]
            ys = [p.y for p in seg.points]
            point_count += len(xs)

            color = _SEG_COLORS.get(seg.type, "black")
            linestyle = "-" if seg.arc_enabled else ":"
            lw = 1.5 if seg.arc_enabled else 1.0
            label = f"{i}:{seg.type}"
            if show_arc_state:
                label += " arc" if seg.arc_enabled else " noarc"

            ax.plot(xs, ys, linestyle, color=color, lw=lw, label=label)

            if show_order and len(xs) >= 1:
                ax.annotate(str(i), (xs[0], ys[0]),
                           textcoords="offset points", xytext=(3, 3),
                           fontsize=7, color=color)

        ax.set_title(title)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_aspect("equal")
        if len(segments) <= 12:
            ax.legend(fontsize=7, loc="upper right")

        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": len(segments),
            "point_count": point_count,
            "warnings": warnings_list,
        }

    @staticmethod
    def write_combined_preview(
        strokes: list[Stroke],
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        title: str = "Combined Preview",
    ) -> dict:
        """绘制 Stroke + ProcessSegment 组合预览。

        Returns:
            stats dict
        """
        fig, (ax_s, ax_seg) = plt.subplots(1, 2, figsize=(20, 10))
        warnings_list: list[str] = []

        # Left: strokes (pixel space)
        for i, s in enumerate(strokes):
            if not s.points_px:
                continue
            xs = [p.x for p in s.points_px]
            ys = [p.y for p in s.points_px]
            if s.closed:
                xs.append(xs[0]); ys.append(ys[0])
            color = _STROKE_COLORS.get(s.source_type, "black")
            ls = "--" if s.is_hole else "-"
            ax_s.plot(xs, ys, ls, color=color, lw=1.0,
                      label=f"{i}:{s.source_type}")
        ax_s.set_title("Strokes (pixel space)")
        ax_s.invert_yaxis()
        ax_s.set_xlabel("px"); ax_s.set_ylabel("px")
        if len(strokes) <= 8:
            ax_s.legend(fontsize=7)

        # Right: segments (robot x/y)
        for i, seg in enumerate(segments):
            if not seg.points:
                continue
            xs = [p.x for p in seg.points]
            ys = [p.y for p in seg.points]
            color = _SEG_COLORS.get(seg.type, "black")
            ls = "-" if seg.arc_enabled else ":"
            ax_seg.plot(xs, ys, ls, color=color, lw=1.2,
                        label=f"{i}:{seg.type}")
        ax_seg.set_title("Segments (robot XY, top view)")
        ax_seg.set_aspect("equal")
        ax_seg.set_xlabel("X (mm)"); ax_seg.set_ylabel("Y (mm)")
        if len(segments) <= 12:
            ax_seg.legend(fontsize=7)

        fig.suptitle(title, fontsize=12)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "stroke_count": len(strokes),
            "segment_count": len(segments),
            "point_count": sum(len(s.points_px) for s in strokes) +
                           sum(len(s.points) for s in segments),
            "warnings": warnings_list,
        }

    @staticmethod
    def write_weld_only_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        title: str = "Working Path (weld + overlap only)",
    ) -> dict:
        """只绘制实际工作轨迹（weld + overlap），不含 travel/retreat/lead_in/lead_out。

        用于焊接/绘图预览，只看工作路径本身。
        """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 10))
        point_count = 0

        for seg in segments:
            if seg.type not in ("weld", "overlap"):
                continue
            if not seg.points:
                continue
            xs = [p.x for p in seg.points]
            ys = [p.y for p in seg.points]
            point_count += len(xs)
            color = "red" if seg.type == "overlap" else "blue"
            lw = 2.0
            ax.plot(xs, ys, "-", color=color, lw=lw, label=None)

        ax.set_title(title)
        ax.set_xlabel("X (mm)")
        ax.set_ylabel("Y (mm)")
        ax.set_aspect("equal")

        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": sum(1 for s in segments if s.type in ("weld", "overlap")),
            "point_count": point_count,
            "warnings": [],
        }

    @staticmethod
    def write_run_preview(
        strokes: list[Stroke],
        segments: list[ProcessSegment],
        output_dir: str | _Path,
        *,
        title_prefix: str = "",
    ) -> dict:
        """一次性输出三张预览图到指定目录。

        生成: preview_strokes.png, preview_segments.png, preview_combined.png

        Returns:
            dict[str, dict]: 每张图的 stats
        """
        out = _Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        t = f"{title_prefix} - " if title_prefix else ""
        s1 = DebugExporter.write_strokes_preview(
            strokes, str(out / "preview_strokes.png"), title=f"{t}Stroke Paths")
        s2 = DebugExporter.write_segments_preview(
            segments, str(out / "preview_segments.png"), title=f"{t}Process Segments")
        s3 = DebugExporter.write_combined_preview(
            strokes, segments, str(out / "preview_combined.png"), title=f"{t}Combined Preview")

        return {
            "strokes_preview": s1,
            "segments_preview": s2,
            "combined_preview": s3,
        }
