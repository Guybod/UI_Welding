from dataclasses import dataclass, field

from app.widgets.node_editor.port_types import PORT_COLORS  # noqa: F401 — re-export

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
    "常量":   "#26A69A",
}

NODE_CATEGORY = {
    "Start": "基础", "End": "基础", "Wait": "基础", "Print": "基础",
    "MoveJ": "运动", "MoveL": "运动", "MoveC": "运动",
    "MoveCircle": "运动", "MovePath": "运动",
    "Position": "点位",
    "SetDO": "IO", "ReadDI": "IO", "SetAO": "IO", "ReadAI": "IO",
    "SetRegister": "寄存器", "ReadRegister": "寄存器",
    "If": "逻辑", "For": "逻辑", "While": "逻辑", "Sequence": "逻辑",
    "Compare": "逻辑", "And": "逻辑", "Or": "逻辑", "Not": "逻辑",
    "Int": "常量", "Float": "常量", "Bool": "常量", "String": "常量", "Array": "常量",
    "ArrayGet": "运算", "ArraySet": "运算", "ArrayLen": "运算",
    "BreakPosition": "运算", "MakePosition": "运算",
    "Cast": "运算", "Reroute": "运算", "EnumInt": "常量",
    "Comment": "基础",
    "MacroCall": "宏",
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
    # 初版先给 3 个固定点位输入，避免多个端口同名导致保存/加载/连线覆盖。
    # 后续如果要任意数量点位，再做动态端口。
    PortSpec("pose_1", "pose", "input"),
    PortSpec("pose_2", "pose", "input"),
    PortSpec("pose_3", "pose", "input"),
]))
_register(NodeSpec("SetDO", "SetDO", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadDI", "ReadDI", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "float", "output"),
]))
_register(NodeSpec("SetAO", "SetAO", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadAI", "ReadAI", "IO", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "float", "output"),
]))
_register(NodeSpec("SetRegister", "SetRegister", "寄存器", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("ReadRegister", "ReadRegister", "寄存器", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "float", "output"),
]))
_register(NodeSpec("If", "If", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("condition", "bool", "input"),
    PortSpec("true", "flow", "output"),
    PortSpec("false", "flow", "output"),
]))
_register(NodeSpec("For", "For", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("start", "int", "input"),
    PortSpec("end", "int", "input"),
    PortSpec("step", "int", "input"),
    PortSpec("body", "flow", "output"),
    PortSpec("done", "flow", "output"),
    PortSpec("index", "int", "output"),
]))
_register(NodeSpec("While", "While", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("condition", "bool", "input"),
    PortSpec("body", "flow", "output"),
    PortSpec("done", "flow", "output"),
]))
_register(NodeSpec("Sequence", "Sequence", "逻辑", [
    PortSpec("flow", "flow", "input"),
    PortSpec("then_0", "flow", "output"),
    PortSpec("then_1", "flow", "output"),
    PortSpec("then_2", "flow", "output"),
    PortSpec("done", "flow", "output"),
]))
_register(NodeSpec("MacroCall", "Macro", "宏", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
]))
_register(NodeSpec("Compare", "Compare", "逻辑", [
    PortSpec("a", "any", "input"),
    PortSpec("b", "any", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("And", "A AND B", "逻辑", [
    PortSpec("a", "bool", "input"),
    PortSpec("b", "bool", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Or", "A OR B", "逻辑", [
    PortSpec("a", "bool", "input"),
    PortSpec("b", "bool", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Not", "NOT A", "逻辑", [
    PortSpec("a", "bool", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Int", "Int", "常量", [
    PortSpec("value", "int", "output"),
]))
_register(NodeSpec("Float", "Float", "常量", [
    PortSpec("value", "float", "output"),
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
# 变量引用节点 (动态端口, 运行时根据 var_type 创建)
_register(NodeSpec("GetVar", "GetVar", "变量", []))
_register(NodeSpec("SetVar", "SetVar", "变量", []))
VAR_PORT_TYPE = {"int": "int", "float": "float", "bool": "bool", "string": "string", "array": "any"}
# 点位拆分/组合
_register(NodeSpec("BreakPosition", "BreakPos", "运算", [
    PortSpec("pose", "pose", "input"),
    PortSpec("jp", "pose", "output"),
    PortSpec("cp", "pose", "output"),
]))
_register(NodeSpec("MakePosition", "MakePos", "运算", [
    PortSpec("jp", "pose", "input"),
    PortSpec("cp", "pose", "input"),
    PortSpec("pose", "pose", "output"),
]))
_register(NodeSpec("Cast", "Cast", "运算", [
    PortSpec("value", "any", "input"),
    PortSpec("result", "any", "output"),
]))
_register(NodeSpec("Reroute", "Reroute", "运算", [
    PortSpec("in", "any", "input"),
    PortSpec("out", "any", "output"),
]))
_register(NodeSpec("EnumInt", "Enum", "常量", [
    PortSpec("value", "int", "output"),
]))
_register(NodeSpec("Comment", "Comment", "基础", []))
# 运算
_register(NodeSpec("Add", "A + B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Sub", "A - B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Mul", "A x B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Div", "A / B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Square", "A^2", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Sqrt", "VA", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
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
_register(NodeSpec("Gt", "A > B", "逻辑", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Lt", "A < B", "逻辑", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Eq", "A == B", "逻辑", [
    PortSpec("a", "any", "input"),
    PortSpec("b", "any", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Ge", "A >= B", "逻辑", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "bool", "output"),
]))
_register(NodeSpec("Le", "A <= B", "逻辑", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "bool", "output"),
]))
# 数学补充
_register(NodeSpec("Pow", "A^B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Mod", "A % B", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("b", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Abs", "|A|", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Neg", "-A", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Sin", "Sin", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Cos", "Cos", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Tan", "Tan", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Deg2Rad", "Deg2Rad", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Rad2Deg", "Rad2Deg", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "float", "output"),
]))
# 逻辑补充
_register(NodeSpec("Xor", "A ^ B", "逻辑", [
    PortSpec("a", "bool", "input"),
    PortSpec("b", "bool", "input"),
    PortSpec("result", "bool", "output"),
]))
# 字符串补充
_register(NodeSpec("StrReplace", "Replace", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("old", "string", "input"),
    PortSpec("new", "string", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("StrLen", "Length", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("result", "int", "output"),
]))
# 类型转换
_register(NodeSpec("Int2Float", "Int2Float", "运算", [
    PortSpec("a", "int", "input"),
    PortSpec("result", "float", "output"),
]))
_register(NodeSpec("Float2Int", "Float2Int", "运算", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "int", "output"),
]))
_register(NodeSpec("Num2Str", "Num2Str", "字符串", [
    PortSpec("a", "float", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("Bool2Str", "Bool2Str", "字符串", [
    PortSpec("a", "bool", "input"),
    PortSpec("result", "string", "output"),
]))
# 数组
_register(NodeSpec("ArrayGet", "Array[i]", "运算", [
    PortSpec("array", "any", "input"),
    PortSpec("index", "int", "input"),
    PortSpec("value", "any", "output"),
]))
_register(NodeSpec("ArraySet", "Array[i]=", "运算", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("array", "any", "input"),
    PortSpec("index", "int", "input"),
    PortSpec("value", "any", "input"),
]))
_register(NodeSpec("ArrayLen", "Length", "运算", [
    PortSpec("array", "any", "input"),
    PortSpec("count", "int", "output"),
]))
# 基础
_register(NodeSpec("Wait", "Wait", "基础", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("duration_ms", "int", "input"),
]))
_register(NodeSpec("Print", "Print", "基础", [
    PortSpec("flow", "flow", "input"),
    PortSpec("flow", "flow", "output"),
    PortSpec("value", "any", "input"),
]))
_register(NodeSpec("StrConcat", "A + B", "字符串", [
    PortSpec("a", "string", "input"),
    PortSpec("b", "string", "input"),
    PortSpec("result", "string", "output"),
]))
_register(NodeSpec("StrSplit", "Split", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("sep", "string", "input"),
    PortSpec("result", "any", "output"),
]))
_register(NodeSpec("StrFind", "Find", "字符串", [
    PortSpec("str", "string", "input"),
    PortSpec("sub", "string", "input"),
    PortSpec("result", "int", "output"),
]))

# ── Blueprint 语义：纯节点 / 含 flow 节点 ──

def node_has_flow_ports(node_type: str, dynamic_ports: list | None = None) -> bool:
    """节点是否带执行流 (flow) 引脚。"""
    if dynamic_ports:
        return any(len(p) >= 2 and p[1] == "flow" for p in dynamic_ports)
    spec = NODE_SPECS.get(node_type)
    if not spec:
        return False
    return any(p.port_type == "flow" for p in spec.ports)


def is_pure_node_type(node_type: str, dynamic_ports: list | None = None) -> bool:
    """纯节点：无 flow，仅在被上游 pull 时求值（类似 UE Pure）。"""
    if node_type == "GetVar":
        return True
    if node_type in ("SetVar", "Start", "End"):
        return False
    if node_type == "Comment":
        return True
    return not node_has_flow_ports(node_type, dynamic_ports)


def is_decorator_node(node_type: str) -> bool:
    return node_type == "Comment"


PURE_NODE_TYPES: frozenset[str] = frozenset(
    nt for nt in NODE_SPECS if is_pure_node_type(nt)
)


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
class VarDef:
    var_id: str = ""
    name: str = ""
    var_type: str = "int"  # "int", "float", "bool", "string", "array"
    value: str = ""  # current value (JSON-compatible string)

    def __post_init__(self):
        if not self.var_id:
            import uuid
            self.var_id = str(uuid.uuid4())[:8]


@dataclass
class PositionDef:
    pos_id: str = ""
    name: str = ""
    jp: list = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    cp: dict = field(default_factory=lambda: {"x": 0, "y": 0, "z": 0, "a": 0, "b": 0, "c": 0})
    ep: list = field(default_factory=list)
    optional: dict = field(default_factory=lambda: {"speed": 200, "acc": 500, "blend": 0, "relativeBlend": 0})

    def __post_init__(self):
        if not self.pos_id:
            import uuid
            self.pos_id = str(uuid.uuid4())[:8]


@dataclass
class GraphData:
    graph_version: str = GRAPH_VERSION
    nodes: list[NodeData] = field(default_factory=list)
    edges: list[EdgeData] = field(default_factory=list)
    variables: list[VarDef] = field(default_factory=list)
    positions: list[PositionDef] = field(default_factory=list)
