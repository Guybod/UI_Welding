"""焊接/绘图路径预览 — matplotlib PNG 输出"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from core.types import Path2D, Path3D, WeldPointSegment, PenSegment


def _arrow_at(points, idx, ax, color, scale=1.0):
    """在路径指定位置画方向箭头。"""
    if idx >= len(points) - 1:
        return
    p0, p1 = points[idx], points[idx + 1]
    dx = p1.x - p0.x
    dy = p1.y - p0.y
    ax.annotate("", xy=(p1.x, p1.y), xytext=(p0.x, p0.y),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.0, alpha=0.7))


def preview_paths_2d(paths: list[Path2D], output_path: str, title: str = "Path Preview"):
    """2D 路径预览：编号 + 方向箭头 + 端点/闭环标记。"""
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_aspect("equal")
    ax.set_title(title)
    ax.invert_yaxis()  # 图像坐标 Y 向下

    colors = plt.cm.tab10.colors
    for i, path in enumerate(paths):
        color = colors[i % len(colors)]
        xs = [p.x for p in path.points]
        ys = [p.y for p in path.points]

        style = "-" if not path.closed else "-"
        ax.plot(xs, ys, style, color=color, lw=1.0, label=f"{path.id} ({path.role})")

        # 方向箭头
        mid = len(path.points) // 2
        if mid < len(path.points) - 1:
            _arrow_at(path.points, mid, ax, color)

        # 端点标记
        if len(path.points) >= 2:
            ax.plot(xs[0], ys[0], "o", color=color, ms=4)
            if path.closed:
                ax.plot(xs[-1], ys[-1], "s", color=color, ms=4)  # 闭环终点用方块

    ax.legend(loc="upper right", fontsize=7, ncol=2)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def preview_weld_segments(
    segments: list[WeldPointSegment],
    output_path: str,
    title: str = "Weld Preview",
):
    """焊接段预览：主路径/引入/引出/搭接 用不同颜色。"""
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect("equal")
    ax.set_title(title)

    phase_colors = {
        "main": "blue",
        "lead_in": "green",
        "lead_out": "orange",
        "overlap": "red",
        "approach": "gray",
        "arc_start": "cyan",
        "arc_end": "magenta",
        "retreat": "gray",
    }

    for seg in segments:
        phases = [
            ("approach", seg.approach_path),
            ("arc_start", seg.arc_start_path),
            ("lead_in", seg.lead_in_path),
            ("main", seg.main_weld_path),
            ("overlap", seg.overlap_path),
            ("lead_out", seg.lead_out_path),
            ("arc_end", seg.arc_end_path),
            ("retreat", seg.retreat_path),
        ]
        for phase_name, poses in phases:
            if len(poses) < 2:
                continue
            color = phase_colors.get(phase_name, "black")
            xs = [p.position.x for p in poses]
            ys = [p.position.y for p in poses]
            ax.plot(xs, ys, "-", color=color, lw=1.0, alpha=0.8)

        # 标注段 ID
        if seg.main_weld_path:
            mid = len(seg.main_weld_path) // 2
            p = seg.main_weld_path[mid].position
            ax.text(p.x, p.y, seg.id, fontsize=6, color="black",
                    ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="yellow", alpha=0.7))

    # 图例
    legend_patches = [
        mpatches.Patch(color=c, label=n) for n, c in phase_colors.items()
    ]
    ax.legend(handles=legend_patches, loc="upper right", fontsize=7)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def preview_pen_segments(
    segments: list[PenSegment],
    output_path: str,
    title: str = "Pen Preview",
):
    """写字/绘图段预览：绘制线 + 空移线分开显示。"""
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_aspect("equal")
    ax.set_title(title)
    # Note: PenSegment uses 3D poses;  we project to XY for preview
    for seg in segments:
        for phase_name, phase_poses, color in [
            ("approach", seg.approach, "gray"),
            ("pen_down", seg.pen_down, "orange"),
            ("draw", seg.draw_path, "blue"),
            ("pen_up", seg.pen_up, "orange"),
            ("travel", seg.travel_to_next, "red"),
        ]:
            if len(phase_poses) < 2:
                continue
            xs = [p.position.x for p in phase_poses]
            ys = [p.position.y for p in phase_poses]
            ax.plot(xs, ys, "-", color=color, lw=1.0, alpha=0.8,
                    label=phase_name if phase_name != "draw" else "")

    # Deduplicate legend
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=7)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
