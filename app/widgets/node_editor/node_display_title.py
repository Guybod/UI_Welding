"""节点标题栏显示文案 — 绑定变量名、点位名、常量值等。"""

from __future__ import annotations

from app.i18n import tr_node
from app.widgets.node_editor.models import NODE_SPECS
from app.widgets.node_editor.var_value import parse_var_storage

AUTO_TITLE_NODE_TYPES = frozenset({
    "GetVar",
    "SetVar",
    "MacroCall",
    "Position",
    "MoveJ",
    "MoveL",
    "MoveC",
    "MoveCircle",
    "MovePath",
    "Int",
    "Float",
    "Bool",
    "String",
    "Array",
    "Wait",
    "Cast",
    "EnumInt",
})

MOTION_TYPES = frozenset({"MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"})
MAX_TITLE_LEN = 20


def truncate_title(text: str, max_len: int = MAX_TITLE_LEN) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_value_preview(value, var_type: str) -> str | None:
    """短预览，用于 GetVar 标题；过长类型返回 None。"""
    if var_type == "array":
        return None
    try:
        v = parse_var_storage(value, var_type)
    except (TypeError, ValueError):
        v = value
    if var_type == "bool":
        return "true" if v else "false"
    if var_type == "string":
        s = str(v)
        if len(s) > 8:
            return f'"{s[:7]}…"'
        return f'"{s}"'
    if var_type == "float":
        s = f"{float(v):g}"
        return s if len(s) <= 10 else s[:9] + "…"
    if var_type == "int":
        return str(int(v))
    return None


def compute_node_display_title(
    node_type: str,
    data: dict | None,
    *,
    pose_links: dict[str, str] | None = None,
) -> str:
    """根据节点类型与数据生成标题栏文字。"""
    data = data or {}
    pose_links = pose_links or {}

    if node_type == "GetVar":
        name = (data.get("var_name") or "?").strip()
        title = f"Get {name}"
        preview = format_value_preview(data.get("value"), data.get("var_type", "int"))
        if preview is not None:
            title = f"{title}={preview}"
        return truncate_title(title)

    if node_type == "SetVar":
        name = (data.get("var_name") or "?").strip()
        return truncate_title(f"Set {name}")

    if node_type == "MacroCall":
        name = (data.get("macro_name") or data.get("macro_id") or "?").strip()
        nin = int(data.get("_param_in", 0))
        nout = int(data.get("_param_out", 0))
        parts = []
        if nin:
            parts.append(f"↓{nin}")
        if nout:
            parts.append(f"↑{nout}")
        suffix = f" ({','.join(parts)})" if parts else ""
        return truncate_title(f"Macro {name}{suffix}")

    if node_type == "Position":
        return truncate_title((data.get("name") or "").strip() or tr_node("Position"))

    if node_type in MOTION_TYPES:
        base = tr_node(node_type)
        if node_type == "MovePath":
            n = sum(1 for p in ("pose_1", "pose_2", "pose_3") if pose_links.get(p))
            if n:
                return truncate_title(f"{base} ·{n}pt")
            return base
        target = pose_links.get("target") or pose_links.get("middle")
        if target:
            return truncate_title(f"{base}→{target}")
        return base

    if node_type in ("Int", "Float", "Bool", "String"):
        val = data.get("value")
        if node_type == "Bool":
            return "true" if val else "false"
        if node_type == "String":
            s = str(val if val is not None else "")
            return truncate_title(f'"{s}"' if s else tr_node("String"))
        if val is None or val == "":
            return tr_node(node_type)
        return truncate_title(str(val))

    if node_type == "Array":
        val = data.get("value", [])
        if isinstance(val, list):
            if not val:
                return tr_node("Array")
            preview = ", ".join(str(v)[:8] for v in val[:3])
            if len(val) > 3:
                preview += "…"
            return truncate_title(f"[{preview}]")
        return tr_node("Array")

    if node_type == "Cast":
        return truncate_title(f"Cast→{data.get('cast_to', 'float')}")

    if node_type == "EnumInt":
        opts = data.get("options") or [0]
        idx = int(data.get("selected", 0))
        if 0 <= idx < len(opts):
            return truncate_title(f"Enum={opts[idx]}")
        return tr_node("EnumInt")

    if node_type == "Wait":
        ms = data.get("duration_ms")
        if ms is not None:
            return truncate_title(f"{tr_node('Wait')} {int(ms)}ms")
        return tr_node("Wait")

    spec = NODE_SPECS.get(node_type)
    return tr_node(node_type) if node_type else (spec.title if spec else node_type)


def should_auto_title(node_type: str, data: dict | None) -> bool:
    data = data or {}
    if node_type not in AUTO_TITLE_NODE_TYPES:
        return False
    return data.get("_auto_title", True) is not False
