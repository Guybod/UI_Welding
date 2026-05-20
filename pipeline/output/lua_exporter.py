"""Phase 9: Lua 焊接脚本导出器

LuaExporter: 从 ProcessSegment 列表生成机器人可执行 Lua 焊接脚本。
纯 Python，无 Qt/PySide6，无 CRI，无网络。
"""

import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.types import ProcessSegment, RobotPoint, LuaExportConfig

# Windows 保留名 (大小写不敏感)
_WIN_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# 非法文件名字符 (Windows + 通用)
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_SEGMENT_TYPE_CN = {
    "weld": "焊接",
    "travel": "空走",
    "lead_in": "引入",
    "lead_out": "引出",
    "overlap": "搭接",
    "retreat": "抬枪",
    "approach": "接近",
}

_MODE_CN = {
    "outline": "轮廓",
    "skeleton": "骨架",
    "fill": "填充",
}


def _as_lua_comment_lines(*blocks: str) -> list[str]:
    """将多行文本转为 Lua 注释行，每行均以 ``--`` 开头。"""
    out: list[str] = []
    for block in blocks:
        if block is None:
            continue
        text = str(block)
        if not text:
            out.append("--")
            continue
        for line in text.splitlines():
            line = line.rstrip()
            out.append("--" if line == "" else f"-- {line}")
    return out


def sanitize_lua_filename(text: str, fallback: str = "job") -> str:
    """将用户输入文字转为安全的 Lua 文件名。

    Args:
        text: 用户输入文字 (可为空或含任意 Unicode)
        fallback: 空文本时的 fallback 名

    Returns:
        安全的文件名 (不含 .lua 扩展名), e.g. "Abc123" 或 "A_B_C_D"
    """
    if not text or not text.strip():
        return fallback

    # 1. Unicode NFKC 规范化
    name = unicodedata.normalize("NFKC", text.strip())

    # 2. 替换非法文件名字符为 "_"
    name = _ILLEGAL_CHARS_RE.sub("_", name)

    # 3. 去掉首尾空白和点号 (Windows 不允许尾随点)
    name = name.strip(" .")

    # 4. 连续空白 → 单个 "_"
    name = re.sub(r'\s+', '_', name)

    # 5. 长度限制 100 字符
    if len(name) > 100:
        name = name[:100].rstrip("_")

    # 6. Windows 保留名保护
    if name.lower() in _WIN_RESERVED:
        name = f"text_{name}"

    # 7. 空字符串 fallback
    if not name:
        return fallback

    return name


class LuaExporter:
    """Lua 焊接脚本导出器。

    Usage:
        exporter = LuaExporter(config=LuaExportConfig())
        stats = exporter.export(segments, "output/weld.lua")
    """

    def __init__(self, config: LuaExportConfig | None = None):
        self.cfg = config or LuaExportConfig()

    def export(
        self,
        segments: list[ProcessSegment],
        output_path: str | Path,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """主入口：ProcessSegment 列表 → Lua 文件 + 统计。"""
        meta = metadata or {}
        warnings: list[str] = []
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        val_warnings = self._validate(segments)
        warnings.extend(val_warnings)

        lua_lines, arc_stats, dup_skipped = self._build_lines(segments, warnings)

        # Write file
        with open(path, "w", encoding="utf-8") as f:
            self._write_header(f, meta)
            f.write("\n")

            # setWelderParam from first weld segment
            weld_params = self._extract_weld_params(segments, warnings)
            for line in _as_lua_comment_lines("焊机参数"):
                f.write(line + "\n")
            f.write(f"setWelderParam({{job={weld_params['job']},"
                    f"I={weld_params['I']},U={weld_params['U']},"
                    f"L={weld_params['L']}}})\n\n")

            for line in lua_lines:
                f.write(line + "\n")

            for line in _as_lua_comment_lines("脚本结束"):
                f.write(line + "\n")

        size = path.stat().st_size
        return {
            "output_path": str(path),
            "file_size_bytes": size,
            "segment_count": len(segments),
            "total_points_in": sum(len(s.points) for s in segments),
            "total_movl_lines": sum(1 for l in lua_lines if l.strip().startswith("movL(")),
            "duplicates_skipped": dup_skipped,
            "arc_on_count": arc_stats["on_count"],
            "arc_off_count": arc_stats["off_count"],
            "arc_warnings": arc_stats.get("warnings", []),
            "wait_insert_count": arc_stats.get("wait_insert_count", 0),
            "validation_warnings": val_warnings,
            "warnings": warnings,
        }

    # ── Validation ──

    def _validate(self, segments: list[ProcessSegment]) -> list[str]:
        w: list[str] = []
        if not segments:
            w.append("no segments to export")
            return w
        total_pts = sum(len(s.points) for s in segments)
        if total_pts == 0:
            w.append("all segments have zero points")
        for seg in segments:
            for p in seg.points:
                for field, val in [("x", p.x), ("y", p.y), ("z", p.z),
                                   ("rx", p.rx), ("ry", p.ry), ("rz", p.rz)]:
                    if math.isnan(val) or math.isinf(val):
                        raise ValueError(
                            f"segment {seg.id[:6]} point has {field}={val}")
        return w

    # ── Header ──

    def _write_header(self, f, meta: dict):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        header: list[str] = [
            "机器人焊接 Lua 脚本",
            f"生成器: pipeline.output.lua_exporter",
            f"生成时间: {ts}",
            "警告: 离线生成脚本，执行前必须仿真/低速空跑验证",
        ]
        mode = meta.get("mode")
        if mode:
            mode_cn = _MODE_CN.get(str(mode), str(mode))
            header.append(f"工艺模式: {mode_cn} ({mode})")
        if meta.get("text_source"):
            header.append(f"文字来源: {meta['text_source']}")
        if meta.get("char_height_mm") not in (None, "", 0):
            header.append(f"字高: {meta['char_height_mm']} mm")
        header.append(f"焊点间距: {meta.get('point_spacing', 'N/A')} mm")
        if meta.get("weld_speed_mm_s") is not None:
            header.append(f"焊接速度: {meta['weld_speed_mm_s']} mm/s")
        if meta.get("travel_speed_mm_s") is not None:
            header.append(f"空走速度: {meta['travel_speed_mm_s']} mm/s")
        line_count = meta.get("line_count")
        if line_count is not None:
            header.append(f"排版行数: {line_count}")
        for line in _as_lua_comment_lines(*header):
            f.write(line + "\n")
        if meta.get("text"):
            f.write("\n")
            for line in _as_lua_comment_lines("文字内容:", meta["text"]):
                f.write(line + "\n")

    # ── Weld params ──

    def _extract_weld_params(self, segments: list[ProcessSegment],
                              warnings: list[str]) -> dict:
        """从第一个 weld 段提取焊接参数。"""
        for seg in segments:
            wp = seg.metadata.get("weld_params")
            if wp:
                return {
                    "job": int(wp.get("job", 0)),
                    "I": int(wp.get("current", 150)),
                    "U": int(wp.get("voltage", 24)),
                    "L": int(wp.get("inductance", 0)),
                }
        warnings.append("no weld_params found in any segment, using defaults")
        return {"job": 0, "I": 150, "U": 24, "L": 0}

    # ── Core line building ──

    def _build_lines(self, segments: list[ProcessSegment],
                     warnings: list[str]) -> tuple[list[str], dict, int]:
        """构建 Lua 行列表 + arc 统计 + 跳过重复计数。"""
        lines: list[str] = []
        arc_on = False
        arc_on_count = 0
        arc_off_count = 0
        arc_warnings: list[str] = []
        dup_skipped = 0
        movl_since_wait = 0
        wait_insert_count = 0

        prev_point: RobotPoint | None = None

        def emit_movl(p: RobotPoint, spd: float) -> bool:
            """返回 True 表示输出了 movL"""
            nonlocal prev_point, dup_skipped, movl_since_wait, wait_insert_count
            if self.cfg.skip_duplicate_points and prev_point is not None:
                if self._is_duplicate(prev_point, p):
                    dup_skipped += 1
                    return False
            prev_point = p
            lines.append(self._format_movl(p, spd))
            # wait() injection
            if self.cfg.insert_wait and self.cfg.wait_every_movl > 0:
                movl_since_wait += 1
                if movl_since_wait >= self.cfg.wait_every_movl:
                    lines.append(f"wait({self.cfg.wait_duration_ms})")
                    movl_since_wait = 0
                    wait_insert_count += 1
            return True

        for seg in segments:
            if not seg.points:
                continue
            seg_type = seg.type
            pts = seg.points
            speed = getattr(seg, "speed_mm_s", 30.0)

            if self.cfg.include_comments:
                lines.extend(self._segment_comment_lines(seg))

            # Arc state transition BEFORE emitting segment points
            if seg.arc_enabled and not arc_on:
                lines.append("arcOn()")
                arc_on = True
                arc_on_count += 1
            elif not seg.arc_enabled and arc_on:
                lines.append("arcOff()")
                arc_on = False
                arc_off_count += 1

            # Emit movL (skip travel/retreat if config says so)
            if seg_type in ("travel", "retreat") and not self.cfg.include_travel:
                continue

            for p in pts:
                emit_movl(p, speed)

        # Safety: force arc off at end
        if arc_on:
            lines.append("arcOff()")
            arc_off_count += 1
            arc_warnings.append("force arcOff at end of script")

        return lines, {
            "on_count": arc_on_count,
            "off_count": arc_off_count,
            "warnings": arc_warnings,
            "wait_insert_count": wait_insert_count,
        }, dup_skipped

    def _segment_comment_lines(self, seg: ProcessSegment) -> list[str]:
        meta = seg.metadata or {}
        type_cn = _SEGMENT_TYPE_CN.get(seg.type, seg.type)
        arc_cn = "开弧" if seg.arc_enabled else "关弧"
        speed = getattr(seg, "speed_mm_s", 0.0)
        body = [
            "── 工艺段 ──",
            f"段ID: {seg.id[:8]}  笔画ID: {str(seg.stroke_id)[:8]}",
            f"类型: {type_cn}  点数: {len(seg.points)}",
            f"速度: {speed:.1f} mm/s  电弧: {arc_cn}",
        ]
        ch = meta.get("weld_char")
        if ch is None:
            ch = meta.get("hanzi_char")
        if ch is not None and str(ch):
            body.append(f"当前字符: {ch!r}")
        if meta.get("weld_char_index") is not None:
            body.append(f"字符序号: {int(meta['weld_char_index']) + 1}")
        line_idx = meta.get("layout_line_index")
        if line_idx is not None:
            line_txt = meta.get("layout_line_text", "")
            body.append(
                f"排版行: {int(line_idx) + 1}"
                + (f"  行内容: {line_txt!r}" if line_txt else "")
            )
        gi = meta.get("glyph_stroke_index")
        if gi is not None:
            body.append(f"字内笔画: {int(gi) + 1}")
        algo = meta.get("extract_algorithm")
        if algo:
            body.append(f"提取算法: {algo}")
        return _as_lua_comment_lines(*body)

    # ── Formatting ──

    def _format_movl(self, p: RobotPoint, speed: float) -> str:
        prec = self.cfg.precision
        sp = self.cfg.speed_precision
        cp = f"{{{p.x:.{prec}f},{p.y:.{prec}f},{p.z:.{prec}f},{p.rx:.{prec}f},{p.ry:.{prec}f},{p.rz:.{prec}f}}}"
        opt_parts = [f"v={speed:.{sp}f}", f"a={self.cfg.acceleration:.0f}"]
        if self.cfg.blend_mode == "relative":
            opt_parts.append(f"rb={self.cfg.blend_ratio}")
        else:
            opt_parts.append(f"b={self.cfg.blend_radius:.0f}")
        opt = ",".join(opt_parts)
        return f"movL({{cp={cp}}},{{{opt}}})"

    def _is_duplicate(self, p1: RobotPoint, p2: RobotPoint) -> bool:
        tol = self.cfg.duplicate_tolerance_mm
        dx, dy, dz = p1.x - p2.x, p1.y - p2.y, p1.z - p2.z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > tol:
            return False
        angle_tol = tol * 10
        return (abs(p1.rx - p2.rx) < angle_tol and
                abs(p1.ry - p2.ry) < angle_tol and
                abs(p1.rz - p2.rz) < angle_tol)
