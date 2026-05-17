"""宏参数引脚 — 边界检测与 MacroCall 动态端口。"""

from __future__ import annotations

from app.widgets.node_editor.models import GraphData, NodeSpec, PortSpec, NODE_SPECS
from app.widgets.node_editor.macro_storage import MacroDef, MacroParam


def _port_type_of_node_port(node_type: str, port_name: str, direction: str) -> str:
    spec = NODE_SPECS.get(node_type)
    if spec:
        for p in spec.ports:
            if p.name == port_name and p.direction == direction:
                return p.port_type
    return "any"


def detect_boundary_inputs(full: GraphData, selected_ids: set[str]) -> list[MacroParam]:
    """选区外连入的 data 边 → 宏输入参数。"""
    node_by_id = {n.node_id: n for n in full.nodes}
    params: list[MacroParam] = []
    seen: set[tuple[str, str]] = set()
    idx = 0

    for e in full.edges:
        if e.target_node_id not in selected_ids:
            continue
        if e.source_node_id in selected_ids:
            continue
        tgt = node_by_id.get(e.target_node_id)
        if not tgt:
            continue
        pt = _port_type_of_node_port(tgt.node_type, e.target_port_name, "input")
        if pt == "flow":
            continue
        key = (e.target_node_id, e.target_port_name)
        if key in seen:
            continue
        seen.add(key)
        label = f"{tgt.title}.{e.target_port_name}"
        params.append(MacroParam(
            param_id=f"in_{idx}",
            name=label,
            port_type=pt,
            inner_node_id=e.target_node_id,
            inner_port_name=e.target_port_name,
            direction="in",
        ))
        idx += 1
    return params


def detect_boundary_outputs(full: GraphData, selected_ids: set[str]) -> list[MacroParam]:
    """选区内连出的 data 边 → 宏输出参数。"""
    node_by_id = {n.node_id: n for n in full.nodes}
    params: list[MacroParam] = []
    seen: set[tuple[str, str]] = set()
    idx = 0

    for e in full.edges:
        if e.source_node_id not in selected_ids:
            continue
        if e.target_node_id in selected_ids:
            continue
        src = node_by_id.get(e.source_node_id)
        if not src:
            continue
        pt = _port_type_of_node_port(src.node_type, e.source_port_name, "output")
        if pt == "flow":
            continue
        key = (e.source_node_id, e.source_port_name)
        if key in seen:
            continue
        seen.add(key)
        label = f"{src.title}.{e.source_port_name}"
        params.append(MacroParam(
            param_id=f"out_{idx}",
            name=label,
            port_type=pt,
            inner_node_id=e.source_node_id,
            inner_port_name=e.source_port_name,
            direction="out",
        ))
        idx += 1
    return params


def detect_boundary_params(full: GraphData, selected_ids: set[str]) -> list[MacroParam]:
    return detect_boundary_inputs(full, selected_ids) + detect_boundary_outputs(full, selected_ids)


def remap_params(params: list[MacroParam], id_map: dict[str, str]) -> list[MacroParam]:
    out: list[MacroParam] = []
    for p in params:
        inner_id = id_map.get(p.inner_node_id, p.inner_node_id)
        out.append(MacroParam(
            param_id=p.param_id,
            name=p.name,
            port_type=p.port_type,
            inner_node_id=inner_id,
            inner_port_name=p.inner_port_name,
            direction=p.direction,
        ))
    return out


def macro_input_params(macro: MacroDef) -> list[MacroParam]:
    return [p for p in (macro.params or []) if p.direction == "in"]


def macro_output_params(macro: MacroDef) -> list[MacroParam]:
    return [p for p in (macro.params or []) if p.direction == "out"]


def macro_call_node_spec(macro: MacroDef, title: str | None = None) -> NodeSpec:
    ports = [
        PortSpec("flow", "flow", "input"),
        PortSpec("flow", "flow", "output"),
    ]
    for p in macro_input_params(macro):
        ports.append(PortSpec(p.param_id, p.port_type, "input"))
    for p in macro_output_params(macro):
        ports.append(PortSpec(p.param_id, p.port_type, "output"))
    return NodeSpec(
        "MacroCall",
        title or f"Macro {macro.name}",
        "宏",
        ports,
        color="#9C27B0",
    )


def macro_call_ports_snapshot(macro: MacroDef) -> list[tuple[str, str, str]]:
    spec = macro_call_node_spec(macro)
    return [(p.name, p.port_type, p.direction) for p in spec.ports]
