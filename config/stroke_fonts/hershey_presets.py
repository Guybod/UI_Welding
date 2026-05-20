"""Hershey stroke font 预设 — 焊接 skeleton 正式数据源配置。"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG_PATH = Path(__file__).resolve().parent / "hershey_presets.yaml"


@dataclass(frozen=True)
class HersheyStylePreset:
    id: str
    label_zh: str
    label_en: str
    hershey_jhf_name: str


class HersheyPresetError(ValueError):
    pass


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    if not _CONFIG_PATH.is_file():
        return {"default_style": "futural", "styles": []}
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@lru_cache(maxsize=1)
def list_hershey_style_presets() -> tuple[HersheyStylePreset, ...]:
    raw = _load_raw()
    out: list[HersheyStylePreset] = []
    for item in raw.get("styles") or []:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        if not pid:
            continue
        label = item.get("label") or {}
        jhf = str(item.get("hershey_jhf_name", pid)).strip() or pid
        out.append(
            HersheyStylePreset(
                id=pid,
                label_zh=str(label.get("zh", pid)),
                label_en=str(label.get("en", pid)),
                hershey_jhf_name=jhf,
            )
        )
    return tuple(out)


def get_default_hershey_style_id() -> str:
    return str(_load_raw().get("default_style", "futural")).strip() or "futural"


def get_hershey_style_preset(style_id: str | None) -> HersheyStylePreset | None:
    sid = (style_id or "").strip() or get_default_hershey_style_id()
    for p in list_hershey_style_presets():
        if p.id == sid:
            return p
    return None


def resolve_hershey_jhf_name(style_id: str | None) -> str:
    preset = get_hershey_style_preset(style_id)
    if preset is None:
        raise HersheyPresetError(f"unknown Hershey style: {style_id!r}")
    return preset.hershey_jhf_name


def build_hershey_style_item_data(preset: HersheyStylePreset, *, lang: str = "zh") -> dict:
    return {
        "preset_id": preset.id,
        "hershey_style": preset.id,
        "hershey_jhf_name": preset.hershey_jhf_name,
        "display": preset.label_zh if lang == "zh" else preset.label_en,
        "path": "",  # 无 TTF 路径
        "family": "Hershey",
    }
