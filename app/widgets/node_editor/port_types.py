"""端口类型系统 — int / float 分离，兼容旧版 number。"""

from __future__ import annotations

# 引脚颜色（int 深绿，float 浅绿，与 UE 风格接近）
PORT_COLORS: dict[str, str] = {
    "flow": "#FFFFFF",
    "pose": "#FF9800",
    "int": "#2E7D32",
    "float": "#66BB6A",
    "number": "#4CAF50",  # 旧工程连线兼容显示
    "bool": "#9C27B0",
    "string": "#00BCD4",
    "io": "#FFEB3B",
    "register": "#E91E63",
    "any": "#9E9E9E",
    "enum": "#FF7043",
}

_NUMERIC = frozenset({"int", "float", "number"})


def normalize_port_type(port_type: str) -> str:
    t = (port_type or "").strip()
    if t == "number":
        return "float"  # 旧工程里的 number 按 float 处理
    return t


def migrate_ports_list(ports: list, var_type: str = "") -> list:
    """将节点 data._ports 中的 number 迁移为 int/float。"""
    out = []
    for p in ports:
        if not p or len(p) < 3:
            continue
        name, ptype, direction = p[0], p[1], p[2]
        if ptype == "number":
            if var_type == "int":
                ptype = "int"
            elif var_type == "float":
                ptype = "float"
            else:
                ptype = "float"
        out.append([name, ptype, direction])
    return out


def ports_compatible(src_type: str, tgt_type: str) -> bool:
    """源输出类型能否连到目标输入。int 可提升到 float。"""
    src = normalize_port_type(src_type)
    tgt = normalize_port_type(tgt_type)
    if src == tgt:
        return True
    if src == "any" or tgt == "any":
        return True
    if src == "int" and tgt == "float":
        return True
    if src == "bool" and tgt == "int":
        return True
    if src == "enum" and tgt == "int":
        return True
    if src == "int" and tgt == "enum":
        return True
    return False


def port_type_label(port_type: str) -> str:
    t = normalize_port_type(port_type)
    if t in ("int", "float", "bool", "string"):
        return t
    return port_type or "?"


def literal_node_for_port(port_type: str) -> str | None:
    """从输入端口拖线到空白时，生成的常量节点类型。"""
    t = normalize_port_type(port_type)
    if t == "int":
        return "Int"
    if t == "float":
        return "Float"
    if t == "bool":
        return "Bool"
    if t == "string":
        return "String"
    if t == "pose":
        return "Position"
    return None


def apply_cast(value, cast_to: str):
    """Cast 节点运行时转换。"""
    t = (cast_to or "float").strip().lower()
    if t == "int":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
    if t == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    if t == "bool":
        return bool(value)
    if t == "string":
        return str(value)
    return value


def conversion_hint(src_type: str, tgt_type: str) -> str:
    src = normalize_port_type(src_type)
    tgt = normalize_port_type(tgt_type)
    if src == "float" and tgt == "int":
        return "请插入 Float2Int 节点"
    if src == "int" and tgt == "float":
        return "可插入 Int2Float，或改用 Float 常量"
    if src in _NUMERIC and tgt not in _NUMERIC:
        return f"类型 {src} 与 {tgt} 不兼容"
    return f"{src} → {tgt} 不兼容"


def var_port_type(var_type: str) -> str:
    return {
        "int": "int",
        "float": "float",
        "bool": "bool",
        "string": "string",
        "array": "any",
    }.get(var_type, "any")
