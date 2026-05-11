"""文本排版引擎：横排/竖排、对齐、缩放、手动换行"""

import numpy as np
from core.types import Point2D, Path2D

from pipeline.font_renderer import render_char
from pipeline.skeleton_extractor import extract_paths


# 换行符常量
NEWLINE = "\n"
# 竖排中表示列分隔
COLUMN_SEP = "\n"


def layout_text(
    text: str,
    font_path: str,
    char_height_mm: float = 20.0,
    char_spacing_mm: float = 2.0,
    line_spacing_mm: float = 5.0,
    direction: str = "horizontal",   # horizontal / vertical
    align: str = "center",           # left / center / right
    flow: str = "left_to_right",     # left_to_right / right_to_left / top_to_bottom
    scale_mode: str = "shrink_to_fit",
    font_size_px: int = 600,
) -> list[Path2D]:
    """排版文字，返回 2D 空间中按 mm 放置的 Path2D 列表。

    每个路径的 Point2D 坐标从像素转换为 mm：
        mm = pixel * (char_height_mm / font_size_px)
    """
    if not text:
        return []

    # 第一步：渲染每个字符，提取骨架路径
    chars = list(text)
    char_paths: list[list[Path2D]] = []
    char_bboxes: list[tuple[float, float]] = []  # (width_mm, height_mm)

    scale = char_height_mm / font_size_px

    for ch in chars:
        if ch == NEWLINE:
            char_paths.append([])
            char_bboxes.append((0.0, 0.0))
            continue
        if ch.isspace():
            # 空格：不渲染，但占用空间
            space_w = char_height_mm * 0.3
            char_paths.append([])
            char_bboxes.append((space_w, char_height_mm))
            continue

        bitmap = render_char(ch, font_path, font_size_px)
        paths = extract_paths(bitmap, char=ch)

        # 将像素坐标转换为 mm
        h_px, w_px = bitmap.shape
        char_w_mm = w_px * scale
        char_h_mm = h_px * scale

        for p in paths:
            p.points = [Point2D(x=pt.x * scale, y=pt.y * scale) for pt in p.points]
            p.metadata["char"] = ch

        char_paths.append(paths)
        char_bboxes.append((char_w_mm, char_h_mm))

    # 第二步：分行/分列
    lines = _split_into_lines(chars, text, direction, flow)

    # 第三步：在每行/每列中放置字符
    result: list[Path2D] = []
    y_offset_mm = 0.0

    if direction == "horizontal":
        for line_indices in lines:
            line_w_mm = sum(char_bboxes[i][0] for i in line_indices) + \
                        char_spacing_mm * max(0, len(line_indices) - 1)
            start_x = _align_offset(line_w_mm, align)

            x_cursor = start_x
            for idx in line_indices:
                paths_for_char = char_paths[idx]
                bw, bh = char_bboxes[idx]

                for p in paths_for_char:
                    # 偏移到当前字符位置
                    offset_path = Path2D(
                        id=p.id,
                        points=[Point2D(x=pt.x + x_cursor, y=pt.y + y_offset_mm)
                                for pt in p.points],
                        closed=p.closed,
                        role=p.role,
                        source=p.source,
                        glyph=p.glyph,
                        metadata={**p.metadata, "line_y": y_offset_mm, "char_x": x_cursor},
                    )
                    result.append(offset_path)

                x_cursor += bw + char_spacing_mm

            y_offset_mm += char_height_mm + line_spacing_mm

    elif direction == "vertical":
        x_offset_mm = 0.0
        for line_indices in lines:
            col_h_mm = char_height_mm * len(line_indices) + \
                       line_spacing_mm * max(0, len(line_indices) - 1)
            start_y = _align_offset(col_h_mm, align)

            y_cursor = start_y
            for idx in line_indices:
                paths_for_char = char_paths[idx]
                bw, bh = char_bboxes[idx]
                # 水平居中字符在其列宽内
                char_x_offset = (char_height_mm - bw) / 2  # approximate centering

                for p in paths_for_char:
                    offset_path = Path2D(
                        id=p.id,
                        points=[Point2D(x=pt.x + x_offset_mm + char_x_offset,
                                        y=pt.y + y_cursor)
                                for pt in p.points],
                        closed=p.closed,
                        role=p.role,
                        source=p.source,
                        glyph=p.glyph,
                        metadata={**p.metadata, "col_x": x_offset_mm, "char_y": y_cursor},
                    )
                    result.append(offset_path)

                y_cursor += char_height_mm + line_spacing_mm

            x_offset_mm += char_height_mm + char_spacing_mm

    return result


def _split_into_lines(chars: list[str], text: str, direction: str,
                      flow: str) -> list[list[int]]:
    """将字符索引按换行符分组成行/列。"""
    lines: list[list[int]] = []
    current: list[int] = []

    for i, ch in enumerate(chars):
        if ch == NEWLINE:
            if current:
                lines.append(current)
                current = []
            continue
        current.append(i)

    if current:
        lines.append(current)

    if not lines:
        return [[]]

    # 处理流向
    if direction == "horizontal" and flow == "right_to_left":
        lines = [list(reversed(line)) for line in lines]

    return lines


def _align_offset(total_size: float, align: str) -> float:
    """返回对齐偏移量。"""
    if align == "left":
        return 0.0
    elif align == "right":
        return -total_size
    else:  # center
        return -total_size / 2.0
