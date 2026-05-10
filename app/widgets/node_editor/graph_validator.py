from dataclasses import dataclass, field
from app.widgets.node_editor.models import GraphData


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GraphValidator:
    """图校验器 — 在 DryRun 或真实执行前校验节点图"""

    def validate(self, graph: GraphData) -> ValidationResult:
        r = ValidationResult()

        self._check_start_end(graph, r)
        self._check_unique_ids(graph, r)
        self._check_edge_refs(graph, r)
        self._check_flow_connectivity(graph, r)
        self._check_required_inputs(graph, r)
        self._check_motion_position(graph, r)

        r.ok = len(r.errors) == 0
        return r

    def _check_start_end(self, graph: GraphData, r: ValidationResult):
        types = {n.node_type for n in graph.nodes}
        if "Start" not in types:
            r.errors.append("缺少 Start 节点")
        if "End" not in types:
            r.errors.append("缺少 End 节点")

    def _check_unique_ids(self, graph: GraphData, r: ValidationResult):
        ids = [n.node_id for n in graph.nodes]
        dupes = {nid for nid in ids if ids.count(nid) > 1}
        for d in dupes:
            r.errors.append(f"节点 ID 重复: {d}")

    def _check_edge_refs(self, graph: GraphData, r: ValidationResult):
        node_ids = {n.node_id for n in graph.nodes}
        # build port lookup: node_id → list of (name, port_type, direction)
        from app.widgets.node_editor.models import NODE_SPECS
        port_map: dict[str, list[tuple[str, str, str]]] = {}
        for n in graph.nodes:
            spec = NODE_SPECS.get(n.node_type)
            if spec:
                port_map[n.node_id] = [(p.name, p.port_type, p.direction) for p in spec.ports]
            else:
                port_map[n.node_id] = []

        for e in graph.edges:
            if e.source_node_id not in node_ids:
                r.errors.append(f"边 {e.edge_id}: 源节点 {e.source_node_id} 不存在")
                continue
            if e.target_node_id not in node_ids:
                r.errors.append(f"边 {e.edge_id}: 目标节点 {e.target_node_id} 不存在")
                continue

            src_ports = port_map.get(e.source_node_id, [])
            tgt_ports = port_map.get(e.target_node_id, [])

            src_match = [(t, d) for n, t, d in src_ports if n == e.source_port_name and d == "output"]
            tgt_match = [(t, d) for n, t, d in tgt_ports if n == e.target_port_name and d == "input"]

            if not src_match:
                r.errors.append(f"边 {e.edge_id}: 源输出端口 {e.source_port_name} 不存在于节点 {e.source_node_id}")
                continue
            if not tgt_match:
                r.errors.append(f"边 {e.edge_id}: 目标输入端口 {e.target_port_name} 不存在于节点 {e.target_node_id}")
                continue

            src_type, _ = src_match[0]
            tgt_type, _ = tgt_match[0]

            if src_type != tgt_type and src_type != "any" and tgt_type != "any":
                r.errors.append(
                    f"边 {e.edge_id}: 端口类型不匹配 ({src_type} → {tgt_type})"
                )

    def _check_flow_connectivity(self, graph: GraphData, r: ValidationResult):
        """检查从 Start 是否可以通过 flow 边到达 End"""
        from app.widgets.node_editor.models import NODE_SPECS

        flow_outs: dict[str, set[str]] = {}
        for n in graph.nodes:
            spec = NODE_SPECS.get(n.node_type)
            if spec:
                flow_out_names = {p.name for p in spec.ports if p.port_type == "flow" and p.direction == "output"}
                targets = set()
                for e in graph.edges:
                    if e.source_node_id == n.node_id and e.source_port_name in flow_out_names:
                        targets.add(e.target_node_id)
                flow_outs[n.node_id] = targets

        # find Start node
        start_node = None
        for n in graph.nodes:
            if n.node_type == "Start":
                start_node = n.node_id
                break
        if not start_node:
            return  # already reported

        # BFS from Start following flow edges
        visited = set()
        queue = [start_node]
        while queue:
            cur = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            for nxt in flow_outs.get(cur, set()):
                if nxt not in visited:
                    queue.append(nxt)

        # check End reachable
        end_nodes = [n.node_id for n in graph.nodes if n.node_type == "End"]
        for end_id in end_nodes:
            if end_id not in visited:
                r.errors.append(f"End 节点 {end_id} 无法从 Start 通过 flow 连线到达")

    def _check_required_inputs(self, graph: GraphData, r: ValidationResult):
        """检查非 Start/End 节点的 flow 输入端口是否有连接"""
        from app.widgets.node_editor.models import NODE_SPECS

        # collect all edge connections: (target_node_id, target_port_name)
        connected_inputs: set[tuple[str, str]] = set()
        for e in graph.edges:
            connected_inputs.add((e.target_node_id, e.target_port_name))

        for n in graph.nodes:
            if n.node_type in ("Start", "End"):
                continue
            spec = NODE_SPECS.get(n.node_type)
            if not spec:
                continue
            for p in spec.ports:
                if p.port_type == "flow" and p.direction == "input":
                    if (n.node_id, p.name) not in connected_inputs:
                        r.warnings.append(f"节点 {n.title}({n.node_id}) 的 flow 输入端口 '{p.name}' 未连接")

    def _check_motion_position(self, graph: GraphData, r: ValidationResult):
        """运动节点的 pose 输入端口必须连接 Position 节点"""
        from app.widgets.node_editor.models import NODE_SPECS

        MOTION_TYPES = {"MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"}

        source_of: dict[tuple[str, str], str] = {}
        for e in graph.edges:
            source_of[(e.target_node_id, e.target_port_name)] = e.source_node_id

        for n in graph.nodes:
            if n.node_type not in MOTION_TYPES:
                continue
            spec = NODE_SPECS.get(n.node_type)
            if not spec:
                continue
            for p in spec.ports:
                if p.port_type == "pose" and p.direction == "input":
                    src_id = source_of.get((n.node_id, p.name))
                    if not src_id:
                        r.errors.append(
                            f"{n.title}({n.node_id}) 的 pose 输入 '{p.name}' 未连接，必须连接 Position 节点"
                        )
                        continue
                    src_node = next((nd for nd in graph.nodes if nd.node_id == src_id), None)
                    if not src_node or src_node.node_type != "Position":
                        r.errors.append(
                            f"{n.title}({n.node_id}) 的 pose 输入 '{p.name}' 连接的不是 Position 节点"
                        )
