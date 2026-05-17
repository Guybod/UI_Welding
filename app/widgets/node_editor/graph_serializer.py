import json
from datetime import datetime
from app.widgets.node_editor.models import GraphData, NodeData, EdgeData, VarDef, PositionDef, GRAPH_VERSION


def reconcile_graph_variables(graph: GraphData) -> None:
    """从画布 GetVar/SetVar 补全 variables 表（兼容缺 variables 段或库不完整的 JSON）。"""
    from app.widgets.node_editor.var_value import format_var_storage, parse_var_storage

    by_id: dict[str, VarDef] = {}
    for v in graph.variables:
        if v.var_id:
            by_id[v.var_id] = v

    for nd in graph.nodes:
        if nd.node_type not in ("GetVar", "SetVar"):
            continue
        d = nd.data or {}
        vid = d.get("var_id", "")
        if not vid:
            continue

        vtype = d.get("var_type", "int")
        name = (d.get("var_name") or "").strip()
        if not name:
            title = (nd.title or "").strip()
            if title.lower().startswith("get "):
                name = title[4:].strip()
            elif title.lower().startswith("set "):
                name = title[4:].strip()
            else:
                name = vid

        if vid not in by_id:
            val = parse_var_storage(d.get("value"), vtype)
            by_id[vid] = VarDef(
                var_id=vid,
                name=name,
                var_type=vtype,
                value=format_var_storage(val, vtype),
            )
            continue

        existing = by_id[vid]
        if not existing.name.strip() and name:
            existing.name = name
        if not existing.var_type:
            existing.var_type = vtype

    graph.variables = list(by_id.values())


def graph_to_json(graph: GraphData, *, merge_nodes_into_variables: bool = True) -> str:
    """GraphData → JSON 字符串"""
    if merge_nodes_into_variables:
        reconcile_graph_variables(graph)
    obj = {
        "graph_version": graph.graph_version,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nodes": [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "title": n.title,
                "x": n.x,
                "y": n.y,
                "data": n.data,
            }
            for n in graph.nodes
        ],
        "edges": [
            {
                "edge_id": e.edge_id,
                "source_node_id": e.source_node_id,
                "source_port_name": e.source_port_name,
                "target_node_id": e.target_node_id,
                "target_port_name": e.target_port_name,
            }
            for e in graph.edges
        ],
    }
    obj["positions"] = [
        {"pos_id": p.pos_id, "name": p.name, "jp": p.jp, "cp": p.cp, "ep": p.ep, "optional": p.optional}
        for p in graph.positions
    ]
    obj["variables"] = [
        {"var_id": v.var_id, "name": v.name, "var_type": v.var_type, "value": v.value}
        for v in graph.variables
    ]
    return json.dumps(obj, ensure_ascii=False, indent=2)


def json_to_graph(text: str) -> GraphData:
    """JSON 字符串 → GraphData"""
    obj = json.loads(text)
    version = obj.get("graph_version", "1.0.0")
    if version != GRAPH_VERSION:
        pass  # 预留 migration

    nodes = [
        NodeData(
            node_id=n["node_id"],
            node_type=n["node_type"],
            title=n.get("title", n["node_type"]),
            x=n["x"],
            y=n["y"],
            data=n.get("data", {}),
        )
        for n in obj.get("nodes", [])
    ]
    edges = [
        EdgeData(
            edge_id=e["edge_id"],
            source_node_id=e["source_node_id"],
            source_port_name=e["source_port_name"],
            target_node_id=e["target_node_id"],
            target_port_name=e["target_port_name"],
        )
        for e in obj.get("edges", [])
    ]
    positions_raw = obj.get("positions", [])
    positions = []
    for p in positions_raw:
        if isinstance(p, str):
            # migrate old string-only format
            positions.append(PositionDef(name=p))
        else:
            positions.append(PositionDef(
                pos_id=p.get("pos_id", p.get("id", "")),
                name=p.get("name", ""),
                jp=p.get("jp", [0.0]*6),
                cp=p.get("cp", {"x":0,"y":0,"z":0,"a":0,"b":0,"c":0}),
                ep=p.get("ep", []),
                optional=p.get("optional", {"speed":200,"acc":500,"blend":0,"relativeBlend":0}),
            ))
    variables = []
    for v in obj.get("variables", []):
        val = v.get("value", v.get("initial", v.get("default", "")))
        if val is None:
            val = ""
        variables.append(VarDef(
            var_id=v.get("var_id", v.get("id", "")),
            name=v.get("name", ""),
            var_type=v.get("var_type", v.get("type", "int")),
            value=str(val),
        ))
    # migrate old Wait duration → duration_ms
    for nd in nodes:
        if nd.node_type == "Wait":
            d = nd.data or {}
            if "duration" in d and "duration_ms" not in d:
                d["duration_ms"] = int(float(d.pop("duration")) * 1000)
            if "duration_sec" in d and "duration_ms" not in d:
                d["duration_ms"] = int(float(d.pop("duration_sec")) * 1000)
    graph = GraphData(graph_version=version, nodes=nodes, edges=edges, variables=variables, positions=positions)
    reconcile_graph_variables(graph)
    return graph
