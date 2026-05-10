from dataclasses import dataclass, field

PORT_COLORS = {
    "flow":     "#FFFFFF",
    "pose":     "#FF9800",
    "number":   "#4CAF50",
    "bool":     "#9C27B0",
    "string":   "#00BCD4",
    "io":       "#FFEB3B",
    "register": "#E91E63",
    "any":      "#9E9E9E",
}

NODE_COLORS = {
    "基础":   "#607D8B",
    "运动":   "#1976D2",
    "点位":   "#F57C00",
    "IO":     "#FBC02D",
    "寄存器": "#C2185B",
    "逻辑":   "#7B1FA2",
    "变量":   "#388E3C",
    "自定义": "#616161",
}

NODE_CATEGORY = {
    "Start": "基础", "End": "基础",
    "MoveJ": "运动", "MoveL": "运动", "MoveC": "运动",
    "MoveCircle": "运动", "MovePath": "运动",
    "Position": "点位",
    "SetDO": "IO", "ReadDI": "IO", "SetAO": "IO", "ReadAI": "IO",
    "SetRegister": "寄存器", "ReadRegister": "寄存器",
    "If": "逻辑", "For": "逻辑", "While": "逻辑",
    "Compare": "逻辑", "And": "逻辑", "Or": "逻辑", "Not": "逻辑",
    "Int": "变量", "Float": "变量", "Bool": "变量", "String": "变量", "Array": "变量",
}


@dataclass
class PortSpec:
    name: str
    port_type: str    # flow / pose / number / bool / string / io / register / any
    direction: str    # input / output


@dataclass
class NodeSpec:
    node_type: str
    title: str
    category: str
    ports: list[PortSpec] = field(default_factory=list)
    color: str = ""


NODE_SPECS: dict[str, NodeSpec] = {}


def _register(spec: NodeSpec):
    if not spec.color:
        spec.color = NODE_COLORS.get(spec.category, "#616161")
    NODE_SPECS[spec.node_type] = spec


_register(NodeSpec("Start", "Start", "基础", [
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("End", "End", "基础", [
    PortSpec("flow", "flow", "input"),
]))
_register(NodeSpec("Position", "Position", "点位", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("pose", "pose", "output"),
]))
_register(NodeSpec("MoveJ", "MoveJ", "运动", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("target", "pose", "input"),
]))
_register(NodeSpec("MoveL", "MoveL", "运动", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("target", "pose", "input"),
]))
_register(NodeSpec("MoveC", "MoveC", "运动", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("target", "pose", "input"),
    PortSpec("middle", "pose", "input"),
]))
_register(NodeSpec("MoveCircle", "MoveCircle", "运动", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("target", "pose", "input"),
    PortSpec("middle", "pose", "input"),
]))
_register(NodeSpec("MovePath", "MovePath", "运动", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("poses", "pose", "input"),
    PortSpec("poses", "pose", "input"),
]))
_register(NodeSpec("SetDO", "SetDO", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadDI", "ReadDI", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "number", "output"),
]))
_register(NodeSpec("SetAO", "SetAO", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadAI", "ReadAI", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "number", "output"),
]))
_register(NodeSpec("SetRegister", "SetRegister", "寄存器", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadRegister", "ReadRegister", "寄存器", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "number", "output"),
]))
_register(NodeSpec("If", "If", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("condition", "bool", "input"),
    PortSpec("true", "flow", "output"),
    PortSpec("false", "flow", "output"),
]))
_register(NodeSpec("For", "For", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("count", "number", "input"),
    PortSpec("body", "flow", "output"),
    PortSpec("done", "flow", "output"),
]))
_register(NodeSpec("Compare", "Compare", "逻辑", [
    PortSpec("a", "any", "input"),
    PortSpec("b", "any", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Int", "Int", "变量", [
    PortSpec("value", "number", "output"),
]))
_register(NodeSpec("Float", "Float", "变量", [
    PortSpec("value", "number", "output"),
]))
_register(NodeSpec("Bool", "Bool", "变量", [
    PortSpec("value", "bool", "output"),
]))
_register(NodeSpec("String", "String", "变量", [
    PortSpec("value", "string", "output"),
]))
_register(NodeSpec("Array", "Array", "变量", [
    PortSpec("value", "any", "output"),
]))

# ── serialization data models ──

GRAPH_VERSION = "1.0.0"


@dataclass
class NodeData:
    node_id: str
    node_type: str
    title: str
    x: float
    y: float


@dataclass
class EdgeData:
    edge_id: str
    source_node_id: str
    source_port_name: str
    target_node_id: str
    target_port_name: str


@dataclass
class GraphData:
    graph_version: str = GRAPH_VERSION
    nodes: list[NodeData] = field(default_factory=list)
    edges: list[EdgeData] = field(default_factory=list)
