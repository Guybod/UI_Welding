"""变量值解析/序列化 — 供属性面板、节点数据、执行引擎共用。"""

from __future__ import annotations

import json
from typing import Any


def parse_var_storage(raw: Any, var_type: str) -> Any:
    """变量库字符串 / 节点 data → 运行时使用的 Python 值。"""
    if var_type == "int":
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return 0
    if var_type == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0
    if var_type == "bool":
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("true", "1", "yes")
    if var_type == "array":
        if isinstance(raw, list):
            return list(raw)
        text = str(raw).strip() if raw is not None else "[]"
        if not text:
            return []
        try:
            val = json.loads(text)
            return val if isinstance(val, list) else []
        except json.JSONDecodeError:
            inner = text.strip("[]")
            if not inner.strip():
                return []
            parts = [p.strip() for p in inner.split(",") if p.strip()]
            out: list = []
            for p in parts:
                try:
                    out.append(int(p) if "." not in p else float(p))
                except ValueError:
                    out.append(p)
            return out
    return "" if raw is None else str(raw)


def format_var_storage(value: Any, var_type: str) -> str:
    """Python 值 → 变量库 VarDef.value 字符串。"""
    if var_type == "array":
        if isinstance(value, list):
            return json.dumps(value, ensure_ascii=False)
        return str(value) if value is not None else "[]"
    if var_type == "bool":
        return "true" if value else "false"
    return str(value)


def array_to_editor_text(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.strip():
        return value
    return "[]"


def parse_array_editor_text(text: str) -> list:
    raw = text.strip()
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else []
    except json.JSONDecodeError:
        inner = raw.strip("[]")
        if not inner.strip():
            return []
        parts = [p.strip() for p in inner.split(",") if p.strip()]
        out: list = []
        for p in parts:
            try:
                out.append(int(p) if "." not in p else float(p))
            except ValueError:
                out.append(p)
        return out
