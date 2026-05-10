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
    "运算":   "#00897B",
    "IO":     "#FBC02D",
    "寄存器": "#C2185B",
    "逻辑":   "#7B1FA2",
    "变量":   "#388E3C",
    "字符串": "#00ACC1",
    "自定义": "#616161",
}

NODE_CATEGORY = {
    "Start": "基础", "End": "基础", "Print": "基础",
    "MoveJ": "运动", "MoveL": "运动", "MoveC": "运动",
    "MoveCircle": "运动", "MovePath": "运动",
    "Position": "点位",
    "SetDO": "IO", "ReadDI": "IO", "SetAO": "IO", "ReadAI": "IO",
    "SetRegister": "寄存器", "ReadRegister": "寄存器",
    "If": "逻辑", "For": "逻辑", "While": "逻辑",
    "Compare": "逻辑", "And": "逻辑", "Or": "逻辑", "Not": "逻辑",
    "Int": "变量", "Float": "变量", "Bool": "变量", "String": "变量", "Array": "变量",
    "Add": "运算", "Sub": "运算", "Mul": "运算", "Div": "运算",
    "Square": "运算", "Sqrt": "运算", "MatMulL": "运算", "MatMulR": "运算",
    "Gt": "逻辑", "Lt": "逻辑", "Eq": "逻辑", "Ge": "逻辑", "Le": "逻辑",
    "Pow": "运算", "Mod": "运算", "Abs": "运算", "Neg": "运算",
    "Sin": "运算", "Cos": "运算", "Tan": "运算", "Deg2Rad": "运算", "Rad2Deg": "运算",
    "Int2Float": "运算", "Float2Int": "运算",
    "Xor": "逻辑",
    "StrConcat": "字符串", "StrSplit": "字符串", "StrFind": "字符串",
    "StrReplace": "字符串", "StrLen": "字符串",
    "Num2Str": "字符串", "Bool2Str": "字符串",
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
# 运算
_register(NodeSpec("Add", "Add", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Sub", "Sub", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Mul", "Mul", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Div", "Div", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Square", "Square", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Sqrt", "Sqrt", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("MatMulL", "MatMulL", "运算", [
    PortSpec("a", "pose", "input"),
    PortSpec("b", "pose", "input"),
    PortSpec("result", "pose", "output"),
]))
_register(NodeSpec("MatMulR", "MatMulR", "运算", [
    PortSpec("a", "pose", "input"),
    PortSpec("b", "pose", "input"),
    PortSpec("result", "pose", "output"),
]))
# 比较
_register(NodeSpec("Gt", "Gt", "逻辑", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Lt", "Lt", "逻辑", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Eq", "Eq", "逻辑", [
    PortSpec("a", "any", "input"),
    PortSpec("b", "any", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Ge", "Ge", "逻辑", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Le", "Le", "逻辑", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "bool", "output"),
]))
# 数学补充
_register(NodeSpec("Pow", "Pow", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Mod", "Mod", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("b", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Abs", "Abs", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Neg", "Neg", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Sin", "Sin", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Cos", "Cos", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Tan", "Tan", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Deg2Rad", "Deg2Rad", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Rad2Deg", "Rad2Deg", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
# 逻辑补充
_register(NodeSpec("Xor", "Xor", "逻辑", [
    PortSpec("a", "bool", "input"),
    PortSpec("b", "bool", "input"),
    PortSpec("result", "bool", "output"),
]))
# 字符串补充
_register(NodeSpec("StrReplace", "StrReplace", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("old", "string", "input"),
    PortSpec("new", "string", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("StrLen", "StrLen", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("result", "number", "output"),
]))
# 类型转换
_register(NodeSpec("Int2Float", "Int2Float", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Float2Int", "Float2Int", "运算", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "number", "output"),
]))
_register(NodeSpec("Num2Str", "Num2Str", "字符串", [
    PortSpec("a", "number", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("Bool2Str", "Bool2Str", "字符串", [
    PortSpec("a", "bool", "input"),
    PortSpec("result", "string", "output"),
]))
# 字符串
_register(NodeSpec("Print", "Print", "基础", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "any", "input"),
]))
_register(NodeSpec("StrConcat", "StrConcat", "字符串", [
    PortSpec("a", "string", "input"),
    PortSpec("b", "string", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("StrSplit", "StrSplit", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("sep", "string", "input"),
    PortSpec("result", "any", "output"),
]))
_register(NodeSpec("StrFind", "StrFind", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("sub", "string", "input"),
    PortSpec("result", "number", "output"),
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
    data: dict = field(default_factory=dict)


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
