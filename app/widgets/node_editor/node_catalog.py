"""节点库分类 — 与 NODE_SPECS 对齐的唯一来源（P0）。"""

from __future__ import annotations

from app.widgets.node_editor.models import NODE_SPECS

# (分类名, 节点类型列表) — 变量/点位条目由 NodeLibraryPanel 动态填充
LIBRARY_CATEGORIES: list[tuple[str, list[str]]] = [
    ("基础", ["Start", "End", "Wait", "Print", "Comment"]),
    ("变量", []),
    ("点位", []),
    ("运动", ["MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"]),
    (
        "运算",
        [
            "BreakPosition",
            "MakePosition",
            "ArrayGet",
            "ArraySet",
            "ArrayLen",
            "Add",
            "Sub",
            "Mul",
            "Div",
            "Square",
            "Sqrt",
            "Pow",
            "Mod",
            "Abs",
            "Neg",
            "Sin",
            "Cos",
            "Tan",
            "Deg2Rad",
            "Rad2Deg",
            "MatMulL",
            "MatMulR",
            "Int2Float",
            "Float2Int",
            "Cast",
            "Reroute",
        ],
    ),
    (
        "逻辑",
        [
            "If",
            "For",
            "While",
            "Sequence",
            "Compare",
            "And",
            "Or",
            "Not",
            "Xor",
            "Gt",
            "Lt",
            "Eq",
            "Ge",
            "Le",
        ],
    ),
    (
        "字符串",
        [
            "StrConcat",
            "StrSplit",
            "StrFind",
            "StrReplace",
            "StrLen",
            "Num2Str",
            "Bool2Str",
        ],
    ),
    ("IO", ["SetDO", "ReadDI", "SetAO", "ReadAI"]),
    ("寄存器", ["SetRegister", "ReadRegister"]),
    ("常量", ["Int", "Float", "Bool", "String", "Array", "EnumInt"]),
    ("宏", []),
    ("自定义", []),
]


def validate_library_catalog() -> list[str]:
    """返回库面板中未在 NODE_SPECS 注册的节点类型。"""
    errors: list[str] = []
    for _cat, types in LIBRARY_CATEGORIES:
        for node_type in types:
            if node_type not in NODE_SPECS:
                errors.append(f"库面板节点 '{node_type}' 未在 NODE_SPECS 注册")
    return errors


def all_library_node_types() -> set[str]:
    out: set[str] = set()
    for _cat, types in LIBRARY_CATEGORIES:
        out.update(types)
    return out
