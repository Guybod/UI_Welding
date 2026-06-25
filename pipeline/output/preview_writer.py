"""Phase 7.3 / 9.d — Preview PNG 导出（仅显示层，不改变真实点位）

纸面约定（与 wledfont2_UI/ui_main + robot_text_gen 一致）：
  预览图左下 = 示教 LB，右上 = RT；U 沿 LT→RT，V 沿 LT→LB（显示 invert_y 使 V 向下）。
  execution/weld 在 WorkPlane UV(mm) 上绘制，与像素预览同一视觉朝向。
  points.txt / Lua 仍为原始机器人坐标，不做 y_flip。
"""

from __future__ import annotations

import math
import os as _os
import sys as _sys
from pathlib import Path as _Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from core.types import Stroke, ProcessSegment, RobotPoint

# ── CJK 字体（预览 PNG 标题中文，与焊接 raster 字体无关）──

_CJK_FP = None

# 预览元数据（写入 summary.json；transform 仅作用于 PNG 显示）
PREVIEW_META_DEFAULTS: dict[str, Any] = {
    "source": "process_segments",
    "basis": "workplane_uv_paper",
    "transform": "display_invert_y",
    "transform_scope": "preview_png_only",
    "paper_corners": "LB_bl_rt",
    "equal_aspect": True,
    "show_travel_in_execution": True,
    "show_travel_in_weld_only": False,
}

# Segment 样式（机器人 XY 图）
_SEG_STYLE: dict[str, dict[str, Any]] = {
    "travel":   {"color": "gray",     "linestyle": "--", "lw": 0.9, "alpha": 0.45, "zorder": 1},
    "retreat":  {"color": "#aaaaaa",  "linestyle": "--", "lw": 0.9, "alpha": 0.45, "zorder": 1},
    "lead_in":  {"color": "orange",   "linestyle": "-",  "lw": 1.3, "alpha": 1.0,  "zorder": 4},
    "weld":     {"color": "blue",     "linestyle": "-",  "lw": 1.5, "alpha": 1.0,  "zorder": 5},
    "overlap":  {"color": "red",      "linestyle": "-",  "lw": 1.5, "alpha": 1.0,  "zorder": 5},
    "lead_out": {"color": "purple",   "linestyle": "-",  "lw": 1.3, "alpha": 1.0,  "zorder": 4},
}

_WELD_ONLY_TYPES = frozenset({"weld", "overlap", "lead_in", "lead_out"})
_TRAVEL_TYPES = frozenset({"travel", "retreat"})

# 绘图模式 segment 样式（仅 write_drawing_execution_preview 使用）
_DRAWING_SEG_STYLE: dict[str, dict[str, Any]] = {
    "travel": {"color": "gray", "linestyle": "--", "lw": 0.9, "alpha": 0.45, "zorder": 1},
    "draw": {"color": "blue", "linestyle": "-", "lw": 1.6, "alpha": 1.0, "zorder": 5},
    "retreat": {"color": "#aaaaaa", "linestyle": "--", "lw": 0.9, "alpha": 0.45, "zorder": 1},
}

_STROKE_COLORS = {
    "contour": "blue",
    "skeleton": "darkgreen",
    "image": "purple",
}

_TITLE_RAW = "Raw Strokes Preview"
_TITLE_EXEC = "Execution Preview (paper-aligned)"
_TITLE_WELD = "Weld Path Preview"
_TITLE_DRAW = "Draw Path Preview"
_TITLE_COMBINED = "Combined Preview"
_DRAW_ONLY_TYPES = frozenset({"draw"})


def _find_cjk_font() -> str | None:
    """预览图标题/占位中文用（与焊接 preset 字体无关）。"""
    candidates: list[str] = []
    if _sys.platform == "win32":
        windir = _os.environ.get("WINDIR", "C:\\Windows")
        candidates.extend([
            _os.path.join(windir, "Fonts", "msyh.ttc"),
            _os.path.join(windir, "Fonts", "msyhbd.ttc"),
            _os.path.join(windir, "Fonts", "simhei.ttf"),
        ])
    elif _sys.platform == "darwin":
        candidates.extend([
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
        ])
    candidates.extend([
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ])
    for p in candidates:
        if _os.path.isfile(p):
            return p
    return None


def _cjk_fontproperties(preferred: str | None = None):
    """返回含中文的预览用 FontProperties；失败返回 None。"""
    global _CJK_FP
    if _CJK_FP is not None:
        return _CJK_FP
    font_path = (preferred or "").strip() or _find_cjk_font()
    if not font_path or not _os.path.isfile(font_path):
        return None
    from matplotlib.font_manager import FontProperties, fontManager
    try:
        fontManager.addfont(font_path)
        _CJK_FP = FontProperties(fname=font_path)
        plt.rcParams["axes.unicode_minus"] = False
        return _CJK_FP
    except Exception:
        return None


def _configure_cjk_font(preferred: str | None = None) -> None:
    _cjk_fontproperties(preferred)


def _text_kw(preferred: str | None = None) -> dict:
    fp = _cjk_fontproperties(preferred)
    return {"fontproperties": fp} if fp is not None else {}


def _set_mpl_title(ax, title: str, *, preferred: str | None = None, **kwargs) -> None:
    ax.set_title(title, **_text_kw(preferred), **kwargs)


def _set_mpl_suptitle(fig, title: str, *, preferred: str | None = None, **kwargs) -> None:
    fig.suptitle(title, **_text_kw(preferred), **kwargs)


def _mpl_text(ax, x, y, s: str, *, preferred: str | None = None, **kwargs) -> None:
    ax.text(x, y, s, **_text_kw(preferred), **kwargs)


def _stroke_close_for_display(stroke: Stroke) -> bool:
    """预览层闭合线：Hershey 仅 glyph_stroke_closed 且首尾重合时画闭合。"""
    meta = stroke.metadata or {}
    if meta.get("extract_algorithm") != "hershey":
        return bool(stroke.closed)
    if not meta.get("glyph_stroke_closed", False):
        return False
    if not stroke.points_px or len(stroke.points_px) < 2:
        return False
    from pipeline.raster.hershey_font_renderer import endpoints_coincide_px
    return endpoints_coincide_px(stroke.points_px)


def _savefig(fig, output_path: str | _Path, **kwargs) -> None:
    path = _Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, **kwargs)


def _uv_projector(workplane):
    """机器人 XY → 纸面 U-V(mm)，与 WorkPlane.pixel_to_plane / robot_text_gen 四角一致。"""
    lt = workplane.tl
    raw_u = workplane.tr - lt
    raw_v = workplane.bl - lt
    w_mm = max(workplane.width_mm, 1e-9)
    h_mm = max(workplane.height_mm, 1e-9)
    ux, uy = raw_u.x / w_mm, raw_u.y / w_mm
    vx, vy = raw_v.x / h_mm, raw_v.y / h_mm
    ox, oy = lt.x, lt.y

    def to_uv(pt: RobotPoint) -> tuple[float, float]:
        du = (pt.x - ox) * ux + (pt.y - oy) * uy
        dv = (pt.x - ox) * vx + (pt.y - oy) * vy
        return du, dv

    return to_uv


def _workplane_corners_uv(workplane) -> dict[str, tuple[float, float]] | None:
    if workplane is None or not hasattr(workplane, "tl"):
        return None
    w = workplane.width_mm
    h = workplane.height_mm
    return {
        "LT": (0.0, 0.0),
        "RT": (w, 0.0),
        "LB": (0.0, h),
        "RB": (w, h),
    }


def _draw_workplane_frame_uv(ax, corners: dict[str, tuple[float, float]]) -> None:
    order = ["LT", "RT", "RB", "LB", "LT"]
    xs = [corners[k][0] for k in order]
    ys = [corners[k][1] for k in order]
    ax.plot(xs, ys, "k--", lw=1.0, alpha=0.85, zorder=2, label="_workplane_border")
    for label, (x, y) in corners.items():
        ax.plot(x, y, "ko", ms=5, zorder=6)
        ax.annotate(
            label, (x, y), textcoords="offset points", xytext=(4, 4),
            fontsize=9, fontweight="bold", color="black", zorder=7,
        )


def _apply_paper_view(ax, workplane) -> None:
    """纸面显示：LB 在图左下、RT 在右上（与 OpenCV 像素预览同向）。"""
    ax.invert_yaxis()
    if workplane is not None:
        w = workplane.width_mm
        h = workplane.height_mm
        pad = max(w, h) * 0.03
        ax.set_xlim(-pad, w + pad)
        ax.set_ylim(h + pad, -pad)


def _draw_paper_axes_arrows(ax, corners: dict[str, tuple[float, float]]) -> None:
    """+U 沿 LT→RT（向右）；+V 沿 LT→LB（invert 后向下）。"""
    lt = corners["LT"]
    rt = corners["RT"]
    lb = corners["LB"]
    ux = rt[0] - lt[0]
    uy = rt[1] - lt[1]
    vx = lb[0] - lt[0]
    vy = lb[1] - lt[1]
    u_len = math.hypot(ux, uy) or 1.0
    v_len = math.hypot(vx, vy) or 1.0
    arrow_len = min(u_len, v_len) * 0.12
    if arrow_len < 1.0:
        arrow_len = max(u_len, v_len) * 0.08
        if arrow_len < 5.0:
            arrow_len = 20.0
    ox, oy = lt
    ax.add_patch(FancyArrowPatch(
        (ox, oy), (ox + ux / u_len * arrow_len, oy + uy / u_len * arrow_len),
        arrowstyle="-|>", mutation_scale=12, color="darkgreen", lw=1.5, zorder=8,
    ))
    ax.annotate("+U", (ox + ux / u_len * arrow_len * 1.05, oy + uy / u_len * arrow_len * 1.05),
                fontsize=9, color="darkgreen", fontweight="bold", ha="center", va="center")
    ax.add_patch(FancyArrowPatch(
        (ox, oy), (ox + vx / v_len * arrow_len, oy + vy / v_len * arrow_len),
        arrowstyle="-|>", mutation_scale=12, color="darkblue", lw=1.5, zorder=8,
    ))
    ax.annotate("+V", (ox + vx / v_len * arrow_len * 1.05, oy + vy / v_len * arrow_len * 1.05),
                fontsize=9, color="darkblue", fontweight="bold", ha="center", va="center")


def _plot_segments_on_ax(
    ax,
    segments: list[ProcessSegment],
    *,
    to_uv=None,
    allowed_types: frozenset[str] | None = None,
    show_travel: bool = True,
    legend: bool = True,
    seg_style: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, int]:
    """在 ax 上绘制 segment；to_uv 非空时投影到纸面 U-V(mm)。返回 (visible, point_count)。"""
    seen_labels: set[str] = set()
    visible = 0
    point_count = 0
    for seg in segments:
        if not seg.points:
            continue
        if allowed_types is not None and seg.type not in allowed_types:
            continue
        if not show_travel and seg.type in _TRAVEL_TYPES:
            continue
        style_map = seg_style if seg_style is not None else _SEG_STYLE
        style = style_map.get(
            seg.type, {"color": "black", "linestyle": "-", "lw": 1.0, "alpha": 1.0, "zorder": 3},
        )
        if to_uv is not None:
            uv = [to_uv(p) for p in seg.points]
            xs = [u for u, _ in uv]
            ys = [v for _, v in uv]
        else:
            xs = [p.x for p in seg.points]
            ys = [p.y for p in seg.points]
        point_count += len(xs)
        visible += 1
        label = seg.type if seg.type not in seen_labels else None
        if label:
            seen_labels.add(seg.type)
        ax.plot(xs, ys, linestyle=style["linestyle"], color=style["color"],
                lw=style["lw"], alpha=style["alpha"], zorder=style["zorder"],
                label=label)
    if legend and seen_labels:
        ax.legend(fontsize=8, loc="upper right", title="segment")
    return visible, point_count


def _finalize_paper_ax(ax, *, title: str, workplane) -> None:
    _set_mpl_title(ax, title, fontsize=11)
    if workplane is not None:
        ax.set_xlabel("Paper U (mm) · LT→RT")
        ax.set_ylabel("Paper V (mm) · LT→LB")
    else:
        ax.set_xlabel("Robot X (mm)")
        ax.set_ylabel("Robot Y (mm)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.35)
    if workplane is not None:
        _apply_paper_view(ax, workplane)


class DebugExporter:
    """Debug / 正式验收 PNG 导出（纯渲染，不修改点位）。"""

    @staticmethod
    def configure_cjk_font(preferred: str | None = None):
        _configure_cjk_font(preferred)

    @staticmethod
    def write_strokes_preview(
        strokes: list[Stroke],
        output_path: str | _Path,
        *,
        title: str = _TITLE_RAW,
        show_order: bool = False,
        canvas_w: float | None = None,
        canvas_h: float | None = None,
    ) -> dict:
        """像素空间字形轮廓（可 invert_yaxis，不代表机器人方向）。"""
        _configure_cjk_font()
        fig, ax = plt.subplots(figsize=(10, 10))
        warnings_list: list[str] = []
        point_count = 0
        for i, s in enumerate(strokes):
            if not s.points_px:
                continue
            xs = [p.x for p in s.points_px]
            ys = [p.y for p in s.points_px]
            point_count += len(xs)
            color = _STROKE_COLORS.get(s.source_type, "black")
            linestyle = "--" if s.is_hole else "-"
            close_vis = _stroke_close_for_display(s)
            if close_vis:
                xs = xs + [xs[0]]
                ys = ys + [ys[0]]
            ax.plot(xs, ys, linestyle, color=color, lw=1.2,
                    label=f"{s.source_type}" if i == 0 else None)
            if show_order and xs:
                ax.annotate(str(i), (xs[0], ys[0]), fontsize=7, xytext=(3, 3),
                            textcoords="offset points")
        _set_mpl_title(ax, title)
        ax.set_xlabel("pixel X")
        ax.set_ylabel("pixel Y")
        ax.invert_yaxis()
        ax.text(
            0.02, 0.02, "pixel space (not robot coords)",
            transform=ax.transAxes, fontsize=8, color="gray", va="bottom",
        )
        if canvas_w and canvas_h:
            ax.set_xlim(0, canvas_w)
            ax.set_ylim(canvas_h, 0)
        if len(strokes) <= 6:
            ax.legend(fontsize=7, loc="upper right")
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "stroke_count": len(strokes),
            "point_count": point_count,
            "invert_yaxis": True,
            "warnings": warnings_list,
        }

    @staticmethod
    def write_execution_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        workplane=None,
        title: str = _TITLE_EXEC,
        show_travel: bool = True,
    ) -> dict:
        """正式执行预览：点位与 points/Lua 同源；纸面 UV 显示 LB 左下 / RT 右上。"""
        _configure_cjk_font()
        fig, ax = plt.subplots(figsize=(11, 10))
        to_uv = _uv_projector(workplane) if workplane is not None else None
        corners = _workplane_corners_uv(workplane)
        visible, point_count = _plot_segments_on_ax(
            ax, segments, to_uv=to_uv, show_travel=show_travel, legend=True)
        if corners:
            _draw_workplane_frame_uv(ax, corners)
            _draw_paper_axes_arrows(ax, corners)
        _finalize_paper_ax(ax, title=title, workplane=workplane)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": len(segments),
            "visible_segments": visible,
            "point_count": point_count,
            "display_invert_yaxis": True,
            "transform": "display_invert_y",
            "basis": "workplane_uv_paper",
            "warnings": [],
        }

    @staticmethod
    def write_drawing_execution_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        workplane=None,
        title: str = "Drawing Execution Preview",
        show_travel: bool = True,
    ) -> dict:
        """绘图模式执行预览：travel 灰虚线、draw 蓝实线；数据源与 trajectory 同源。"""
        fig, ax = plt.subplots(figsize=(11, 10))
        to_uv = _uv_projector(workplane) if workplane is not None else None
        corners = _workplane_corners_uv(workplane)
        visible, point_count = _plot_segments_on_ax(
            ax,
            segments,
            to_uv=to_uv,
            show_travel=show_travel,
            legend=True,
            seg_style=_DRAWING_SEG_STYLE,
        )
        if corners:
            _draw_workplane_frame_uv(ax, corners)
            _draw_paper_axes_arrows(ax, corners)
        _finalize_paper_ax(ax, title=title, workplane=workplane)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": len(segments),
            "visible_segments": visible,
            "point_count": point_count,
            "display_invert_yaxis": True,
            "transform": "display_invert_y",
            "basis": "workplane_uv_paper",
            "mode": "drawing",
            "warnings": [],
        }

    @staticmethod
    def write_segments_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        title: str = _TITLE_EXEC,
        show_travel: bool = True,
        workplane=None,
    ) -> dict:
        """兼容旧文件名 preview_segments.png，与 execution 同源。"""
        return DebugExporter.write_execution_preview(
            segments, output_path, workplane=workplane, title=title, show_travel=show_travel)

    @staticmethod
    def write_draw_only_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        workplane=None,
        title: str = _TITLE_DRAW,
    ) -> dict:
        """绘图模式：仅落笔绘制段（不含 travel / retreat）。"""
        _configure_cjk_font()
        fig, ax = plt.subplots(figsize=(10, 10))
        to_uv = _uv_projector(workplane) if workplane is not None else None
        corners = _workplane_corners_uv(workplane)
        if corners:
            _draw_workplane_frame_uv(ax, corners)
        visible, point_count = _plot_segments_on_ax(
            ax,
            segments,
            to_uv=to_uv,
            allowed_types=_DRAW_ONLY_TYPES,
            show_travel=False,
            legend=True,
            seg_style=_DRAWING_SEG_STYLE,
        )
        _finalize_paper_ax(ax, title=title, workplane=workplane)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": visible,
            "point_count": point_count,
            "display_invert_yaxis": True,
            "transform": "display_invert_y",
            "types_shown": sorted(_DRAW_ONLY_TYPES),
            "mode": "drawing",
            "warnings": [],
        }

    @staticmethod
    def write_weld_only_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        workplane=None,
        title: str = _TITLE_WELD,
    ) -> dict:
        """焊接相关轨迹：weld / overlap / lead_in / lead_out，不含 travel/retreat。"""
        _configure_cjk_font()
        fig, ax = plt.subplots(figsize=(10, 10))
        to_uv = _uv_projector(workplane) if workplane is not None else None
        corners = _workplane_corners_uv(workplane)
        if corners:
            _draw_workplane_frame_uv(ax, corners)
        visible, point_count = _plot_segments_on_ax(
            ax, segments, to_uv=to_uv, allowed_types=_WELD_ONLY_TYPES,
            show_travel=False, legend=True)
        _finalize_paper_ax(ax, title=title, workplane=workplane)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "segment_count": visible,
            "point_count": point_count,
            "display_invert_yaxis": True,
            "transform": "display_invert_y",
            "types_shown": sorted(_WELD_ONLY_TYPES),
            "warnings": [],
        }

    @staticmethod
    def write_combined_preview(
        strokes: list[Stroke],
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        title: str = _TITLE_COMBINED,
        workplane=None,
    ) -> dict:
        """三栏：Raw Strokes | Weld Only | Execution (Base Z+)。"""
        _configure_cjk_font()
        fig, axes = plt.subplots(1, 3, figsize=(24, 8))

        # 左：像素 raw
        ax0 = axes[0]
        for s in strokes:
            if not s.points_px:
                continue
            xs = [p.x for p in s.points_px]
            ys = [p.y for p in s.points_px]
            close_vis = _stroke_close_for_display(s)
            if close_vis:
                xs = xs + [xs[0]]
                ys = ys + [ys[0]]
            ax0.plot(xs, ys, "-", color=_STROKE_COLORS.get(s.source_type, "black"), lw=1.2)
        ax0.set_title("Raw Strokes")
        ax0.set_xlabel("px")
        ax0.set_ylabel("px")
        ax0.invert_yaxis()

        # 中：weld only（纸面 UV）
        ax1 = axes[1]
        to_uv = _uv_projector(workplane) if workplane is not None else None
        corners = _workplane_corners_uv(workplane)
        if corners:
            _draw_workplane_frame_uv(ax1, corners)
        _plot_segments_on_ax(ax1, segments, to_uv=to_uv, allowed_types=_WELD_ONLY_TYPES,
                             show_travel=False, legend=True)
        _finalize_paper_ax(ax1, title="Weld Path", workplane=workplane)

        # 右：execution（纸面 UV）
        ax2 = axes[2]
        _plot_segments_on_ax(ax2, segments, to_uv=to_uv, show_travel=True, legend=True)
        if corners:
            _draw_workplane_frame_uv(ax2, corners)
            _draw_paper_axes_arrows(ax2, corners)
        _finalize_paper_ax(ax2, title="Execution", workplane=workplane)

        _set_mpl_suptitle(fig, title, fontsize=12, y=1.02)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {
            "output_path": str(path),
            "file_size_bytes": path.stat().st_size,
            "panels": ["raw_strokes", "weld_only", "execution"],
            "warnings": [],
        }

    @staticmethod
    def write_overflow_preview_placeholder(
        output_path: str | _Path,
        *,
        reason: str,
        title: str = "Preview Not Generated",
    ) -> dict:
        """空间不足等失败时：占位图，避免误用旧成功图。"""
        _configure_cjk_font()
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.axis("off")
        _mpl_text(
            ax, 0.5, 0.55, title,
            ha="center", va="center", fontsize=14, fontweight="bold",
        )
        _mpl_text(
            ax, 0.5, 0.35, reason[:200],
            ha="center", va="center", fontsize=10, wrap=True,
        )
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return {"output_path": str(path), "placeholder": True, "reason": reason}

    @staticmethod
    def write_workplane_preview(
        segments: list[ProcessSegment],
        output_path: str | _Path,
        *,
        workplane=None,
        title: str = "WorkPlane Local View",
    ) -> dict:
        """U-V 局部视图（debug）；可 invert_yaxis，非正式验收图。"""
        fig, ax = plt.subplots(figsize=(10, 10))
        warnings: list[str] = []
        if workplane is None or not hasattr(workplane, "tl"):
            warnings.append("WorkPlane not available")
            ax.text(0.5, 0.5, "WorkPlane N/A", transform=ax.transAxes, ha="center")
        else:
            left_top = workplane.tl
            right_top = workplane.tr
            left_bottom = workplane.bl
            raw_u = RobotPoint(right_top.x - left_top.x, right_top.y - left_top.y,
                               right_top.z - left_top.z, 0, 0, 0)
            raw_v = RobotPoint(left_bottom.x - left_top.x, left_bottom.y - left_top.y,
                               left_bottom.z - left_top.z, 0, 0, 0)
            w_mm = math.hypot(raw_u.x, raw_u.y, raw_u.z)
            h_mm = math.hypot(raw_v.x, raw_v.y, raw_v.z)
            ux, uy = raw_u.x / w_mm, raw_u.y / w_mm
            vx, vy = raw_v.x / h_mm, raw_v.y / h_mm

            def _local(pt):
                du = (pt.x - left_top.x) * ux + (pt.y - left_top.y) * uy
                dv = (pt.x - left_top.x) * vx + (pt.y - left_top.y) * vy
                return du, dv

            corners = {
                "LT": _local(left_top), "RT": _local(right_top),
                "LB": _local(left_bottom),
                "RB": _local(RobotPoint(
                    left_top.x + raw_u.x + raw_v.x, left_top.y + raw_u.y + raw_v.y,
                    left_top.z, left_top.rx, left_top.ry, left_top.rz)),
            }
            for a, b in [("LT", "RT"), ("RT", "RB"), ("RB", "LB"), ("LB", "LT")]:
                ax.plot([corners[a][0], corners[b][0]], [corners[a][1], corners[b][1]],
                        "k--", lw=0.8)
            for label, (lx, ly) in corners.items():
                ax.annotate(label, (lx, ly), fontsize=7, xytext=(3, 3),
                            textcoords="offset points")
            for seg in segments:
                if seg.type not in _WELD_ONLY_TYPES or not seg.points:
                    continue
                lx, ly = zip(*[_local(p) for p in seg.points])
                color = _SEG_STYLE[seg.type]["color"]
                ax.plot(lx, ly, "-", color=color, lw=1.2)
            ax.invert_yaxis()
            ax.set_aspect("equal")
        _set_mpl_title(ax, title)
        path = _Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _savefig(fig, path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return {"output_path": str(path), "warnings": warnings}

    @staticmethod
    def build_preview_meta(output_dir: str | _Path, *, generated: bool = True,
                           reason: str = "") -> dict[str, Any]:
        out = _Path(output_dir)
        meta = dict(PREVIEW_META_DEFAULTS)
        meta["generated"] = generated
        if not generated:
            meta["not_generated_reason"] = reason
            return meta
        meta.update({
            "raw_strokes_preview_path": "preview_strokes.png",
            "execution_preview_path": "preview_execution.png",
            "segments_preview_path": "preview_segments.png",
            "weld_only_preview_path": "preview_weld_only.png",
            "combined_preview_path": "preview_combined.png",
            "workplane_preview_path": "preview_workplane.png"
            if (out / "preview_workplane.png").exists() else None,
        })
        return meta

    @staticmethod
    def write_run_preview(
        strokes: list[Stroke],
        segments: list[ProcessSegment],
        output_dir: str | _Path,
        *,
        title_prefix: str = "",
        workplane=None,
        show_travel_in_execution: bool = True,
    ) -> dict:
        """输出全套预览 PNG + preview_meta（供 summary.json）。"""
        out = _Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        t = f"{title_prefix}\n" if title_prefix else ""

        s_raw = DebugExporter.write_strokes_preview(
            strokes, out / "preview_strokes.png",
            title=f"{t}{_TITLE_RAW}".strip())
        s_exec = DebugExporter.write_execution_preview(
            segments, out / "preview_execution.png",
            workplane=workplane, title=f"{t}{_TITLE_EXEC}".strip(),
            show_travel=show_travel_in_execution)
        s_seg = DebugExporter.write_segments_preview(
            segments, out / "preview_segments.png",
            workplane=workplane, title=f"{t}{_TITLE_EXEC}".strip(),
            show_travel=show_travel_in_execution)
        s_weld = DebugExporter.write_weld_only_preview(
            segments, out / "preview_weld_only.png",
            workplane=workplane, title=f"{t}{_TITLE_WELD}".strip())
        s_comb = DebugExporter.write_combined_preview(
            strokes, segments, out / "preview_combined.png",
            title=f"{t}{_TITLE_COMBINED}".strip(), workplane=workplane)

        result: dict[str, Any] = {
            "strokes_preview": s_raw,
            "execution_preview": s_exec,
            "segments_preview": s_seg,
            "weld_only_preview": s_weld,
            "combined_preview": s_comb,
        }
        if workplane is not None:
            try:
                result["workplane_preview"] = DebugExporter.write_workplane_preview(
                    segments, out / "preview_workplane.png", workplane=workplane)
            except Exception:
                pass
        result["preview_meta"] = DebugExporter.build_preview_meta(out, generated=True)
        return result
