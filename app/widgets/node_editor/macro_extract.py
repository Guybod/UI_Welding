"""从画布选区提取宏子图。"""

from __future__ import annotations

import uuid
from copy import deepcopy

from app.widgets.node_editor.models import EdgeData, GraphData, NodeData


def extract_subgraph(selected_ids: set[str], full: GraphData) -> tuple[GraphData | None, str]:
    """提取选区节点与内部连线。返回 (graph, error_message)。"""
    if not selected_ids:
        return None, "empty"

    nodes = [deepcopy(n) for n in full.nodes if n.node_id in selected_ids]
    if not nodes:
        return None, "empty"

    has_start = any(n.node_type == "Start" for n in nodes)
    if not has_start:
        return None, "no_start"

    edges = [
        deepcopy(e)
        for e in full.edges
        if e.source_node_id in selected_ids and e.target_node_id in selected_ids
    ]

    return GraphData(
        graph_version=full.graph_version,
        nodes=nodes,
        edges=edges,
        variables=deepcopy(full.variables),
        positions=deepcopy(full.positions),
    ), ""


def remap_graph_ids(graph: GraphData) -> tuple[GraphData, dict[str, str]]:
    """保存宏时重写 node_id，避免与主图冲突。返回 (新图, 旧id→新id)。"""
    id_map = {n.node_id: str(uuid.uuid4())[:8] for n in graph.nodes}
    nodes = [
        NodeData(
            node_id=id_map[n.node_id],
            node_type=n.node_type,
            title=n.title,
            x=n.x,
            y=n.y,
            data=deepcopy(n.data),
        )
        for n in graph.nodes
    ]
    edges = [
        EdgeData(
            edge_id=str(uuid.uuid4())[:8],
            source_node_id=id_map[e.source_node_id],
            source_port_name=e.source_port_name,
            target_node_id=id_map[e.target_node_id],
            target_port_name=e.target_port_name,
        )
        for e in graph.edges
    ]
    return GraphData(
        graph_version=graph.graph_version,
        nodes=nodes,
        edges=edges,
        variables=deepcopy(graph.variables),
        positions=deepcopy(graph.positions),
    ), id_map
