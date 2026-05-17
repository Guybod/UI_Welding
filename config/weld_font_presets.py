"""焊接文字字体白名单 — 仅允许 config/weld_font_presets.yaml 中的 preset。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import yaml

from core.types import PathConfig

_CONFIG_PATH = Path(__file__).resolve().parent / "weld_font_presets.yaml"
_PROJECT_ROOT = _CONFIG_PATH.parent.parent


class WeldFontPresetError(ValueError):
    pass


@dataclass(frozen=True)
class WeldFontPreset:
    id: str
    family: str
    label_zh: str
    label_en: str
    resolved_path: str


@dataclass(frozen=True)
class SkeletonFontTuning:
    raster_close_px: int = 0
    raster_dilate_px: int = 0
    spur_min_px: float = 3.0
    merge_gap_px: float = 0.0
    branch_cluster_radius_px: int = 5


_DEFAULT_SKELETON_TUNING = SkeletonFontTuning()


def _expand_path_template(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    windir = os.environ.get("WINDIR", r"C:\Windows")
    s = s.replace("${WINDIR}", windir).replace("$WINDIR", windir)
    if not os.path.isabs(s):
        s = str((_PROJECT_ROOT / s).resolve())
    return os.path.normpath(s)


def _platform_key() -> str:
    if sys.platform == "win32":
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def _path_entries(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _resolve_preset_path(preset_raw: dict) -> str | None:
    paths = preset_raw.get("paths") or {}
    if not isinstance(paths, dict):
        return None
    key = _platform_key()
    candidates: list[str] = []
    for k in (key, "win32", "linux", "darwin"):
        candidates.extend(_path_entries(paths.get(k)))
    project = paths.get("project")
    candidates = _path_entries(project) + candidates
    seen: set[str] = set()
    for raw in candidates:
        p = _expand_path_template(raw)
        if not p or p in seen:
            continue
        seen.add(p)
        if os.path.isfile(p):
            return p
    return None


@lru_cache(maxsize=1)
def _load_yaml() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise WeldFontPresetError(f"invalid weld font config: {_CONFIG_PATH}")
    return data


def clear_preset_cache() -> None:
    _load_yaml.cache_clear()
    _preset_raw_by_id.cache_clear()


@lru_cache(maxsize=1)
def _preset_raw_by_id() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for raw in _load_yaml().get("presets") or []:
        if isinstance(raw, dict):
            pid = str(raw.get("id", "")).strip()
            if pid:
                out[pid] = raw
    return out


def _parse_skeleton_tuning(raw: dict | None, *, px_per_mm: float) -> SkeletonFontTuning:
    if not isinstance(raw, dict):
        return _DEFAULT_SKELETON_TUNING
    ppm = max(px_per_mm, 0.1)

    def _mm(key: str, default_mm: float) -> float:
        if key in raw:
            return max(0.0, float(raw[key])) * ppm
        return default_mm * ppm

    return SkeletonFontTuning(
        raster_close_px=max(0, int(raw.get("raster_close_px", 0) or 0)),
        raster_dilate_px=max(0, int(raw.get("raster_dilate_px", 0) or 0)),
        spur_min_px=_mm("spur_min_mm", 0.3),
        merge_gap_px=_mm("merge_gap_mm", 0.0),
        branch_cluster_radius_px=max(3, int(raw.get("branch_cluster_radius_px", 5) or 5)),
    )


def get_skeleton_tuning_for_font_path(
    font_path: str | None,
    *,
    px_per_mm: float = 10.0,
) -> SkeletonFontTuning:
    if not font_path:
        return _DEFAULT_SKELETON_TUNING
    try:
        target = _norm_path(font_path)
    except OSError:
        return _DEFAULT_SKELETON_TUNING
    for preset in list_available_weld_font_presets():
        if _norm_path(preset.resolved_path) != target:
            continue
        raw = _preset_raw_by_id().get(preset.id, {})
        return _parse_skeleton_tuning(raw.get("skeleton"), px_per_mm=px_per_mm)
    return _DEFAULT_SKELETON_TUNING


def apply_skeleton_tuning_to_path_config(
    config: PathConfig,
    font_path: str | None,
    *,
    px_per_mm: float = 10.0,
) -> PathConfig:
    """按字体 preset 写入 PathConfig 中的骨架提取参数。"""
    t = get_skeleton_tuning_for_font_path(font_path, px_per_mm=px_per_mm)
    return replace(
        config,
        skeleton_raster_close_px=t.raster_close_px,
        skeleton_raster_dilate_px=t.raster_dilate_px,
        skeleton_spur_min_px=t.spur_min_px,
        skeleton_merge_gap_px=t.merge_gap_px,
        skeleton_branch_cluster_radius_px=t.branch_cluster_radius_px,
    )


@lru_cache(maxsize=1)
def list_available_weld_font_presets() -> tuple[WeldFontPreset, ...]:
    """返回本机已解析到文件、且配置启用的 preset（顺序与 yaml 一致）。"""
    data = _load_yaml()
    out: list[WeldFontPreset] = []
    for raw in data.get("presets") or []:
        if not isinstance(raw, dict):
            continue
        if raw.get("enabled", True) is False:
            continue
        pid = str(raw.get("id", "")).strip()
        if not pid:
            continue
        path = _resolve_preset_path(raw)
        if not path:
            continue
        label = raw.get("label") or {}
        if not isinstance(label, dict):
            label = {}
        out.append(
            WeldFontPreset(
                id=pid,
                family=str(raw.get("family", pid)),
                label_zh=str(label.get("zh", pid)),
                label_en=str(label.get("en", pid)),
                resolved_path=path,
            )
        )
    return tuple(out)


def get_default_weld_font_preset_id() -> str:
    data = _load_yaml()
    default_id = str(data.get("default_preset_id", "")).strip()
    available = {p.id for p in list_available_weld_font_presets()}
    if default_id in available:
        return default_id
    if available:
        return next(iter(list_available_weld_font_presets())).id
    return default_id or "arial"


def get_weld_font_preset(preset_id: str) -> WeldFontPreset | None:
    pid = (preset_id or "").strip()
    for p in list_available_weld_font_presets():
        if p.id == pid:
            return p
    return None


def _norm_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def allowed_weld_font_paths() -> frozenset[str]:
    return frozenset(_norm_path(p.resolved_path) for p in list_available_weld_font_presets())


def is_allowed_weld_font_path(font_path: str | None) -> bool:
    if not font_path or not str(font_path).strip():
        return False
    try:
        return _norm_path(font_path) in allowed_weld_font_paths()
    except OSError:
        return False


def preset_label(preset: WeldFontPreset, *, lang: str = "zh") -> str:
    return preset.label_en if lang == "en" else preset.label_zh


def build_weld_font_item_data(preset: WeldFontPreset, *, lang: str = "zh") -> dict:
    return {
        "preset_id": preset.id,
        "path": preset.resolved_path,
        "family": preset.family,
        "display": preset_label(preset, lang=lang),
    }


def resolve_weld_font_path(
    font_path: str | None = None,
    preset_id: str | None = None,
) -> str:
    """解析焊接用字体路径；不在白名单则抛 WeldFontPresetError。"""
    if preset_id:
        p = get_weld_font_preset(preset_id)
        if p is not None:
            return p.resolved_path
    if font_path and is_allowed_weld_font_path(font_path):
        for p in list_available_weld_font_presets():
            if _norm_path(p.resolved_path) == _norm_path(font_path):
                return p.resolved_path
    default = get_weld_font_preset(get_default_weld_font_preset_id())
    if default is not None:
        return default.resolved_path
    raise WeldFontPresetError(
        "no weld font preset available on this machine; check config/weld_font_presets.yaml"
    )


def enforce_weld_font_path(
    font_path: str | None = None,
    preset_id: str | None = None,
) -> str:
    """管线入口：强制使用白名单字体。"""
    if preset_id:
        p = get_weld_font_preset(preset_id)
        if p is not None:
            return p.resolved_path
    if font_path:
        if is_allowed_weld_font_path(font_path):
            return resolve_weld_font_path(font_path=font_path)
        raise WeldFontPresetError(
            f"font not in weld preset list: {font_path!r}"
        )
    return resolve_weld_font_path()
