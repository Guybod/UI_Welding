"""根据 RobotStatus.type 解析 models/ 目录下的 GLB 文件。"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from core.robot_model_config import get_model_config

_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
_MAP_PATH = Path(__file__).resolve().parents[1] / "config" / "model_glb_map.yaml"
_MAP_CACHE: dict | None = None


def models_dir() -> Path:
    return _MODELS_DIR


def _load_map() -> dict:
    global _MAP_CACHE
    if _MAP_CACHE is not None:
        return _MAP_CACHE
    if _MAP_PATH.is_file():
        with open(_MAP_PATH, encoding="utf-8") as f:
            _MAP_CACHE = yaml.safe_load(f) or {}
    else:
        _MAP_CACHE = {}
    return _MAP_CACHE


def _normalize_type(robot_type: str) -> str:
    return robot_type.strip()


def _match_from_map(robot_type: str) -> str | None:
    m = _load_map()
    exact = m.get("exact") or {}
    if robot_type in exact:
        return exact[robot_type]
    upper = robot_type.upper()
    for key, glb in exact.items():
        if key.upper() == upper:
            return glb
    for item in m.get("patterns") or []:
        needle = str(item.get("contains", "")).upper()
        if needle and needle in upper:
            return item.get("glb")
    return m.get("default_glb")


def _infer_glb_names(robot_type: str) -> list[str]:
    names: list[str] = []
    t = _normalize_type(robot_type)
    if not t:
        return names

    mapped = _match_from_map(t)
    if mapped:
        names.append(mapped)

    names.append(f"{t}.glb")

    upper = t.upper()
    m = re.search(r"S(\d+)", upper)
    if m:
        kg = m.group(1)
        names.append(f"{kg}kg-6axis-model-v2.glb")
        names.append(f"{kg}kg-6axis-model.glb")

    m = re.search(r"(\d+)\s*KG", upper)
    if m:
        kg = m.group(1)
        names.append(f"{kg}kg-6axis-model-v2.glb")

    return names


def resolve_glb_path(robot_type: str | None = None) -> Path | None:
    """
    解析 GLB 路径，优先级：
    1. config/model_glb_map.yaml（精确 / 子串）
    2. robot_models.yaml 中的 glb_file
    3. models/{type}.glb 及 S 系列载荷推断
    4. model_glb_map default_glb
    """
    root = models_dir()
    if not root.is_dir():
        return None

    t = _normalize_type(robot_type or "")
    cfg = get_model_config(t) if t else None

    candidates: list[str] = []
    if t:
        mapped = _match_from_map(t)
        if mapped:
            candidates.append(mapped)
    if cfg and cfg.glb_file:
        candidates.append(cfg.glb_file)
    if t:
        candidates.extend(_infer_glb_names(t))

    default = _load_map().get("default_glb", "10kg-6axis-model-v2.glb")
    candidates.append(default)

    seen: set[str] = set()
    for name in candidates:
        if not name or name in seen:
            continue
        seen.add(name)
        p = root / name
        if p.is_file():
            return p

    glbs = sorted(root.glob("*-6axis-model-v2.glb"))
    return glbs[0] if glbs else None


def resolve_glb_name(robot_type: str | None = None) -> str:
    p = resolve_glb_path(robot_type)
    return p.name if p else ""
