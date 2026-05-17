"""宏引用递归校验 — 含嵌套 MacroCall 与环检测。"""

from __future__ import annotations

from typing import Callable

from app.i18n import tr
from app.widgets.node_editor.graph_validator import GraphValidator, ValidationResult
from app.widgets.node_editor.macro_storage import MacroDef
from app.widgets.node_editor.models import GraphData


def validate_macro_references_recursive(
    graph: GraphData,
    get_macro: Callable[[str], MacroDef | None],
    known_ids: set[str],
    result: ValidationResult,
    visiting: frozenset[str] | None = None,
) -> None:
    """校验图中 MacroCall，并递归校验被引用宏的子图。"""
    visiting = visiting or frozenset()
    for n in graph.nodes:
        if n.node_type != "MacroCall":
            continue
        d = n.data or {}
        mid = (d.get("macro_id") or "").strip()
        name = d.get("macro_name") or mid or n.title
        if not mid:
            result.add_error(tr("macro_invalid_ref").format(name=name), n.node_id)
            continue
        if mid not in known_ids:
            result.add_error(tr("macro_invalid_ref").format(name=name), n.node_id)
            continue
        if mid in visiting:
            result.add_error(tr("macro_cycle").format(name=name), n.node_id)
            continue
        macro = get_macro(mid)
        if not macro:
            result.add_error(tr("macro_invalid_ref").format(name=name), n.node_id)
            continue
        inner = GraphValidator().validate(macro.graph)
        if not inner.ok:
            result.add_error(tr("macro_compile_fail").format(name=macro.name), n.node_id)
        validate_macro_references_recursive(
            macro.graph,
            get_macro,
            known_ids,
            result,
            visiting | {mid},
        )
