import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class LinkVisual:
    base_height_mm: float = 180
    link_lengths_mm: list[float] = field(default_factory=list)
    joint_radius_mm: float = 35


@dataclass
class RobotModelConfig:
    key: str
    display_name: str
    joint_count: int
    model_type: str
    joint_order: list[str]
    raw_joint_unit: str
    raw_tcp_position_unit: str
    raw_tcp_orientation_unit: str
    ui_joint_unit: str
    ui_tcp_position_unit: str
    ui_tcp_orientation_unit: str
    mesh_dir: str = ""
    glb_file: str = ""
    joint_axes: list[str] = field(default_factory=lambda: ["z", "y", "y", "y", "z", "y"])
    joint_signs: list[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    link_visual: LinkVisual = field(default_factory=LinkVisual)


def _load_config() -> dict[str, RobotModelConfig]:
    yaml_path = os.path.join(os.path.dirname(__file__), "..", "config", "robot_models.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    configs = {}
    for key, raw in data.get("robots", {}).items():
        link = raw.get("link_visual", {})
        configs[key] = RobotModelConfig(
            key=key,
            display_name=raw.get("display_name", key),
            joint_count=raw.get("joint_count", 6),
            model_type=raw.get("model_type", "simple_chain"),
            joint_order=raw.get("joint_order", []),
            raw_joint_unit=raw.get("raw_joint_unit", "rad"),
            raw_tcp_position_unit=raw.get("raw_tcp_position_unit", "m"),
            raw_tcp_orientation_unit=raw.get("raw_tcp_orientation_unit", "rad"),
            ui_joint_unit=raw.get("ui_joint_unit", "deg"),
            ui_tcp_position_unit=raw.get("ui_tcp_position_unit", "mm"),
            ui_tcp_orientation_unit=raw.get("ui_tcp_orientation_unit", "deg"),
            mesh_dir=raw.get("mesh_dir", ""),
            glb_file=raw.get("glb_file", ""),
            joint_axes=list(raw.get("joint_axes", ["z", "y", "y", "y", "z", "y"])),
            joint_signs=[float(x) for x in raw.get("joint_signs", [1, 1, 1, 1, 1, 1])],
            link_visual=LinkVisual(
                base_height_mm=link.get("base_height_mm", 180),
                link_lengths_mm=link.get("link_lengths_mm", []),
                joint_radius_mm=link.get("joint_radius_mm", 35),
            ),
        )
    return configs


# 全局加载
_MODELS: dict[str, RobotModelConfig] = _load_config()
DEFAULT_MODEL_KEY = "default_6axis"


def get_model_config(robot_type: Optional[str] = None) -> RobotModelConfig:
    """根据 RobotStatus.db.type 加载模型配置, 找不到回退 default_6axis"""
    if robot_type and robot_type in _MODELS:
        return _MODELS[robot_type]
    return _MODELS.get(DEFAULT_MODEL_KEY, list(_MODELS.values())[0])


def get_available_models() -> dict[str, RobotModelConfig]:
    return dict(_MODELS)
