import json
from datetime import datetime
from app.widgets.node_editor.models import GraphData, NodeData, EdgeData, VarDef, PositionDef, GRAPH_VERSION


def graph_to_json(graph: GraphData) -> str:
    """GraphData → JSON 字符串"""
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
        val = v.get("value", v.get("initial", ""))
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
    return GraphData(graph_version=version, nodes=nodes, edges=edges, variables=variables, positions=positions)
