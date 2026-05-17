"""宏（子程序）资产 — 磁盘读写与目录管理。"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from app.widgets.node_editor.graph_serializer import graph_to_json, json_to_graph
from app.widgets.node_editor.models import GraphData

MACRO_VERSION = "1.1"
DEFAULT_MACROS_DIR_NAME = "macros"


@dataclass
class MacroParam:
    """宏对外暴露的数据引脚 — 映射到子图内节点引脚。

    direction: "in" 子图输入（外部 → 宏内）；"out" 子图输出（宏内 → 外部）。
    """
    param_id: str
    name: str
    port_type: str
    inner_node_id: str
    inner_port_name: str
    direction: str = "in"

    def to_dict(self) -> dict:
        return {
            "param_id": self.param_id,
            "name": self.name,
            "port_type": self.port_type,
            "inner_node_id": self.inner_node_id,
            "inner_port_name": self.inner_port_name,
            "direction": self.direction,
        }

    @staticmethod
    def from_dict(obj: dict) -> "MacroParam":
        return MacroParam(
            param_id=obj.get("param_id", ""),
            name=obj.get("name", ""),
            port_type=obj.get("port_type", "any"),
            inner_node_id=obj.get("inner_node_id", ""),
            inner_port_name=obj.get("inner_port_name", ""),
            direction=obj.get("direction", "in"),
        )


@dataclass
class MacroDef:
    macro_id: str
    name: str
    graph: GraphData
    description: str = ""
    params: list[MacroParam] = field(default_factory=list)

    def __post_init__(self):
        if not self.macro_id:
            self.macro_id = str(uuid.uuid4())[:8]


def macros_dir(projects_root: Path | None = None) -> Path:
    root = projects_root or Path(__file__).resolve().parents[3] / "projects"
    d = root / DEFAULT_MACROS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def macro_path(macro_id: str, projects_root: Path | None = None) -> Path:
    return macros_dir(projects_root) / f"{macro_id}.json"


def macro_to_json(macro: MacroDef) -> str:
    obj = {
        "macro_version": MACRO_VERSION,
        "macro_id": macro.macro_id,
        "name": macro.name,
        "description": macro.description,
        "params": [p.to_dict() for p in macro.params],
        "graph": json.loads(graph_to_json(macro.graph, merge_nodes_into_variables=True)),
    }
    return json.dumps(obj, ensure_ascii=False, indent=2)


def json_to_macro(text: str) -> MacroDef:
    obj = json.loads(text)
    graph_obj = obj.get("graph") or {}
    graph = json_to_graph(json.dumps(graph_obj, ensure_ascii=False))
    params = [MacroParam.from_dict(p) for p in obj.get("params", [])]
    return MacroDef(
        macro_id=obj.get("macro_id", ""),
        name=obj.get("name", "Macro"),
        graph=graph,
        description=obj.get("description", ""),
        params=params,
    )


def save_macro(macro: MacroDef, projects_root: Path | None = None) -> Path:
    path = macro_path(macro.macro_id, projects_root)
    path.write_text(macro_to_json(macro), encoding="utf-8")
    return path


def load_macro(macro_id: str, projects_root: Path | None = None) -> MacroDef | None:
    path = macro_path(macro_id, projects_root)
    if not path.is_file():
        return None
    try:
        return json_to_macro(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, KeyError):
        return None


def list_macros(projects_root: Path | None = None) -> list[MacroDef]:
    out: list[MacroDef] = []
    for path in sorted(macros_dir(projects_root).glob("*.json")):
        try:
            macro = json_to_macro(path.read_text(encoding="utf-8"))
            if macro.macro_id:
                out.append(macro)
        except (json.JSONDecodeError, OSError):
            continue
    out.sort(key=lambda m: m.name.lower())
    return out


def delete_macro(macro_id: str, projects_root: Path | None = None) -> bool:
    path = macro_path(macro_id, projects_root)
    if path.is_file():
        path.unlink()
        return True
    return False


def clone_macro_graph(graph: GraphData) -> GraphData:
    """运行宏时使用独立副本，避免污染资产。"""
    return deepcopy(graph)
