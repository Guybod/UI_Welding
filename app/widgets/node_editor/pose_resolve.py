"""静态点位解析 — 编译期沿数据线追溯 Position / MakePosition / BreakPosition。"""

from __future__ import annotations

from app.widgets.node_editor.models import NodeData


def resolve_static_pose(
    node_idx: dict[str, NodeData],
    source_of: dict[tuple[str, str], str],
    node_id: str,
    output_port: str | None = None,
    depth: int = 0,
) -> dict | None:
    if depth > 32 or not node_id:
        return None
    node = node_idx.get(node_id)
    if not node:
        return None
    nt = node.node_type
    data = node.data or {}

    if nt == "Position":
        if data.get("configured") is False:
            return None
        return dict(data)

    if nt == "Reroute":
        up = source_of.get((node_id, "in"))
        return resolve_static_pose(node_idx, source_of, up, None, depth + 1) if up else None

    if nt == "MakePosition":
        jp_src = source_of.get((node_id, "jp"))
        cp_src = source_of.get((node_id, "cp"))
        jp_part = resolve_static_pose(node_idx, source_of, jp_src, "jp", depth + 1) if jp_src else None
        cp_part = resolve_static_pose(node_idx, source_of, cp_src, "cp", depth + 1) if cp_src else None
        jp_list = _extract_jp(jp_part)
        cp_dict = _extract_cp(cp_part)
        if not jp_list and not cp_dict and not data.get("name"):
            return None
        return {
            "name": data.get("name", ""),
            "jp": jp_list,
            "cp": cp_dict,
            "ep": data.get("ep", []),
            "optional": dict(data.get("optional") or {}),
        }

    if nt == "BreakPosition":
        up = source_of.get((node_id, "pose"))
        full = resolve_static_pose(node_idx, source_of, up, None, depth + 1) if up else None
        if not full:
            return None
        if output_port == "jp":
            return {"jp": list(full.get("jp") or [])}
        if output_port == "cp":
            cp = full.get("cp")
            return {"cp": dict(cp) if isinstance(cp, dict) else {}}
        return full

    return None


def _extract_jp(part: dict | None) -> list:
    if not part:
        return []
    if "jp" in part and isinstance(part["jp"], list):
        try:
            return [float(x) for x in part["jp"][:6]]
        except (TypeError, ValueError):
            return []
    return []


def _extract_cp(part: dict | None) -> dict:
    if not part:
        return {}
    cp = part.get("cp")
    if isinstance(cp, dict) and "x" in cp:
        return dict(cp)
    return {}
