import json
from datetime import datetime
from app.widgets.node_editor.models import GraphData, NodeData, EdgeData, GRAPH_VERSION


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
    return GraphData(graph_version=version, nodes=nodes, edges=edges)
