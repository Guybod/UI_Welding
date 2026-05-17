"""Pipeline / 焊接服务面向用户的日志与错误文案（zh/en）。"""

from __future__ import annotations


def normalize_lang(lang: str | None) -> str:
    return "en" if lang == "en" else "zh"


def workplane_overflow_message(
    required_w: float,
    required_h: float,
    available_w: float,
    available_h: float,
    shortage_w: float,
    shortage_h: float,
    *,
    lang: str = "zh",
) -> str:
    lang = normalize_lang(lang)
    if lang == "en":
        return (
            f"Text size exceeds workplane: "
            f"required {required_w:.1f}×{required_h:.1f} mm, "
            f"available {available_w:.1f}×{available_h:.1f} mm, "
            f"shortage {shortage_w:.1f}×{shortage_h:.1f} mm"
        )
    return (
        f"文字尺寸超出工作区："
        f"需要 {required_w:.1f}×{required_h:.1f} mm，"
        f"可用 {available_w:.1f}×{available_h:.1f} mm，"
        f"缺口 {shortage_w:.1f}×{shortage_h:.1f} mm"
    )


def pipeline_failed_prefix(*, lang: str = "zh") -> str:
    return "Pipeline FAILED: " if normalize_lang(lang) == "en" else "生成失败："


def weld_font_not_allowed(font_path: str, *, lang: str = "zh") -> str:
    lang = normalize_lang(lang)
    if lang == "en":
        return f"Font not in weld preset allowlist: {font_path}"
    return f"字体不在焊接预设白名单中: {font_path}"


def stage_error(stage: str, exc: Exception | str, *, lang: str = "zh") -> str:
    lang = normalize_lang(lang)
    detail = str(exc)
    if lang == "en":
        return f"{stage}: {detail}"
    labels = {
        "extract": "轮廓提取",
        "clean": "路径清洗",
        "refine": "路径优化",
        "schedule": "路径排序",
        "map": "坐标映射",
        "plan": "工艺规划",
        "export": "文件导出",
    }
    label = labels.get(stage, stage)
    return f"{label}失败: {detail}"


def no_strokes_extracted(*, lang: str = "zh") -> str:
    if normalize_lang(lang) == "en":
        return "no strokes extracted"
    return "未提取到任何笔画轮廓"


def skeleton_baseline_drift_warning(max_shift_mm: float, *, lang: str = "zh") -> str:
    if normalize_lang(lang) == "en":
        return (
            f"skeleton baseline drift detected between chars "
            f"(max {max_shift_mm:.1f} mm). Check skeleton extraction."
        )
    return f"骨架字基线漂移过大（最大 {max_shift_mm:.1f} mm），请检查骨架提取效果"


def workplane_log(
    width_mm: float,
    height_mm: float,
    nx: float,
    ny: float,
    nz: float,
    *,
    lang: str = "zh",
) -> str:
    if normalize_lang(lang) == "en":
        return (
            f"WorkPlane: {width_mm:.0f}×{height_mm:.0f} mm, "
            f"N=({nx:.3f},{ny:.3f},{nz:.3f})"
        )
    return (
        f"工作平面: {width_mm:.0f}×{height_mm:.0f} mm, "
        f"法向 N=({nx:.3f},{ny:.3f},{nz:.3f})"
    )


def pipeline_start_log(text: str, mode: str, *, lang: str = "zh") -> str:
    if normalize_lang(lang) == "en":
        return f"Pipeline: text='{text}' mode={mode}"
    return f"开始生成: 文字='{text}' 模式={mode}"


def pipeline_done_log(
    strokes_raw: int,
    segments: int,
    robot_points: int,
    duration_ms: float,
    *,
    lang: str = "zh",
) -> str:
    if normalize_lang(lang) == "en":
        return (
            f"Done: {strokes_raw} strokes → {segments} segments, "
            f"{robot_points} points, {duration_ms:.0f}ms"
        )
    return (
        f"完成: {strokes_raw} 条原始笔画 → {segments} 个工艺段, "
        f"{robot_points} 个机器人点, 耗时 {duration_ms:.0f}ms"
    )


def output_file_log(label: str, path: str, *, lang: str = "zh") -> str:
    # 路径与文件名不翻译
    return f"  {label}: {path}"


def unexpected_error_log(exc: Exception | str, *, lang: str = "zh") -> str:
    if normalize_lang(lang) == "en":
        return f"ERROR: {exc}"
    return f"异常: {exc}"
