from dataclasses import dataclass, field
from typing import Any

from app.widgets.node_editor.models import GraphData, NODE_SPECS, NodeData


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GraphValidator:
    """图校验器。

    目标：把明显危险或无法执行的图挡在执行引擎之前。
    """

    MOTION_TYPES = {"MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"}

    def validate(self, graph: GraphData) -> ValidationResult:
        r = ValidationResult()

        self._node_idx = {n.node_id: n for n in graph.nodes}
        self._port_map = self._build_port_map(graph)
        self._source_of = {(e.target_node_id, e.target_port_name): e.source_node_id for e in graph.edges}

        self._check_start_end(graph, r)
        self._check_unique_ids(graph, r)
        self._check_edge_refs(graph, r)
        self._check_flow_connectivity(graph, r)
        self._check_flow_cycle(graph, r)
        self._check_required_inputs(graph, r)
        self._check_motion_position(graph, r)
        self._check_motion_params(graph, r)
        self._check_flow_unique_output(graph, r)

        r.ok = len(r.errors) == 0
        return r

    # ───────────────────────── basic checks ─────────────────────────

    def _check_start_end(self, graph: GraphData, r: ValidationResult):
        start_count = sum(1 for n in graph.nodes if n.node_type == "Start")
        end_count = sum(1 for n in graph.nodes if n.node_type == "End")
        if start_count == 0:
            r.errors.append("缺少 Start 节点")
        if end_count == 0:
            r.errors.append("缺少 End 节点")
        if start_count > 1:
            r.warnings.append(f"存在多个 Start 节点({start_count})，当前执行引擎只会从第一个 Start 开始")

    def _check_unique_ids(self, graph: GraphData, r: ValidationResult):
        ids = [n.node_id for n in graph.nodes]
        seen = set()
        dupes = set()
        for nid in ids:
            if nid in seen:
                dupes.add(nid)
            seen.add(nid)
        for d in dupes:
            r.errors.append(f"节点 ID 重复: {d}")

    def _build_port_map(self, graph: GraphData) -> dict[str, list[tuple[str, str, str]]]:
        port_map: dict[str, list[tuple[str, str, str]]] = {}
        for n in graph.nodes:
            dynamic_ports = (n.data or {}).get("_ports")
            if dynamic_ports:
                port_map[n.node_id] = [tuple(p) for p in dynamic_ports]
                continue

            spec = NODE_SPECS.get(n.node_type)
            if spec:
                port_map[n.node_id] = [(p.name, p.port_type, p.direction) for p in spec.ports]
            else:
                port_map[n.node_id] = []
        return port_map

    def _check_edge_refs(self, graph: GraphData, r: ValidationResult):
        node_ids = set(self._node_idx.keys())

        for e in graph.edges:
            if e.source_node_id not in node_ids:
                r.errors.append(f"边 {e.edge_id}: 源节点 {e.source_node_id} 不存在")
                continue
            if e.target_node_id not in node_ids:
                r.errors.append(f"边 {e.edge_id}: 目标节点 {e.target_node_id} 不存在")
                continue

            src_ports = self._port_map.get(e.source_node_id, [])
            tgt_ports = self._port_map.get(e.target_node_id, [])

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
                r.errors.append(f"边 {e.edge_id}: 端口类型不匹配 ({src_type} → {tgt_type})")

    def _check_flow_connectivity(self, graph: GraphData, r: ValidationResult):
        flow_outs: dict[str, set[str]] = {}
        for n in graph.nodes:
            out_names = {
                name for name, port_type, direction in self._port_map.get(n.node_id, [])
                if port_type == "flow" and direction == "output"
            }
            targets = set()
            for e in graph.edges:
                if e.source_node_id == n.node_id and e.source_port_name in out_names:
                    targets.add(e.target_node_id)
            flow_outs[n.node_id] = targets

        start_node = next((n.node_id for n in graph.nodes if n.node_type == "Start"), None)
        if not start_node:
            return

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

        for end_id in [n.node_id for n in graph.nodes if n.node_type == "End"]:
            if end_id not in visited:
                r.errors.append(f"End 节点 {end_id} 无法从 Start 通过 flow 连线到达")

    def _check_flow_cycle(self, graph: GraphData, r: ValidationResult):
        """检测 flow 路径中的循环 (仅检查主线, 跳过If/For/While分支)"""
        CONTROL_NODES = {"If", "For", "While"}
        flow_graph: dict[str, str] = {}
        for e in graph.edges:
            src_ports = self._port_map.get(e.source_node_id, [])
            for n, t, d in src_ports:
                if n == e.source_port_name and t == "flow" and d == "output":
                    src_node = self._node_idx.get(e.source_node_id)
                    if src_node and src_node.node_type in CONTROL_NODES:
                        continue  # 控制流分支, 跳过
                    if e.source_node_id in flow_graph:
                        r.errors.append(f"节点 {e.source_node_id} 的 flow 输出连接了多条边，不能分叉且不能形成循环")
                    flow_graph[e.source_node_id] = e.target_node_id
        # detect cycle using visited + path set
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {nid: WHITE for nid in flow_graph}
        for nid in list(flow_graph):
            if nid not in color:
                color[nid] = WHITE
        def dfs(u, path):
            color[u] = GRAY
            v = flow_graph.get(u)
            if v:
                if color.get(v) == GRAY:
                    path.append(v)
                    r.errors.append(f"Flow 路径存在循环: {' → '.join(path)}")
                    return
                if color.get(v) == WHITE:
                    dfs(v, path + [v])
            color[u] = BLACK
        for nid in list(flow_graph.keys()):
            if color.get(nid) == WHITE:
                dfs(nid, [nid])

    def _check_required_inputs(self, graph: GraphData, r: ValidationResult):
        connected_inputs = {(e.target_node_id, e.target_port_name) for e in graph.edges}

        for n in graph.nodes:
            if n.node_type in ("Start", "End"):
                continue
            for port_name, port_type, direction in self._port_map.get(n.node_id, []):
                if port_type == "flow" and direction == "input":
                    if (n.node_id, port_name) not in connected_inputs:
                        r.warnings.append(f"节点 {n.title}({n.node_id}) 的 flow 输入端口 '{port_name}' 未连接")

    # ───────────────────────── motion checks ─────────────────────────

    def _check_motion_position(self, graph: GraphData, r: ValidationResult):
        for n in graph.nodes:
            if n.node_type not in self.MOTION_TYPES:
                continue

            if n.node_type == "MovePath":
                r.warnings.append(f"{n.title}({n.node_id}) MovePath 在线执行当前未开放，建议先使用 DryRun 或拆成 MoveJ/MoveL")
                # MovePath 暂不做强校验，避免旧图因为端口重构全部报错。
                continue

            if n.node_type == "MoveJ":
                pos = self._position_input(n, "target")
                if not pos:
                    r.errors.append(f"{n.title}({n.node_id}) 必须连接 target Position")
                elif not self._valid_jp(pos):
                    r.errors.append(f"{n.title}({n.node_id}) 的 target Position 必须包含合法 jp[6]，MoveJ 初版不允许 cp fallback")
                continue

            if n.node_type == "MoveL":
                pos = self._position_input(n, "target")
                if not pos:
                    r.errors.append(f"{n.title}({n.node_id}) 必须连接 target Position")
                elif not self._valid_cp(pos):
                    r.errors.append(f"{n.title}({n.node_id}) 的 target Position 必须包含合法 cp[x,y,z,a,b,c]")
                continue

            if n.node_type in ("MoveC", "MoveCircle"):
                target = self._position_input(n, "target")
                middle = self._position_input(n, "middle")
                if not target:
                    r.errors.append(f"{n.title}({n.node_id}) 必须连接 target Position")
                elif not self._valid_cp(target):
                    r.errors.append(f"{n.title}({n.node_id}) 的 target Position 必须包含合法 cp，{n.node_type} 不能用 jp")

                if not middle:
                    r.errors.append(f"{n.title}({n.node_id}) 必须连接 middle Position")
                elif not self._valid_cp(middle):
                    r.errors.append(f"{n.title}({n.node_id}) 的 middle Position 必须包含合法 cp，{n.node_type} 不能用 jp")

    def _check_motion_params(self, graph: GraphData, r: ValidationResult):
        for n in graph.nodes:
            if n.node_type not in self.MOTION_TYPES:
                continue
            data = n.data or {}
            for key in ("speed", "acc"):
                if key in data and data.get(key) not in (None, "", "?"):
                    val = self._to_float(data.get(key))
                    if val is None or val <= 0:
                        r.errors.append(f"{n.title}({n.node_id}) 参数 {key} 必须为正数")
            for key in ("blend", "relativeBlend"):
                if key in data and data.get(key) not in (None, "", "?"):
                    val = self._to_float(data.get(key))
                    if val is None or val < 0:
                        r.errors.append(f"{n.title}({n.node_id}) 参数 {key} 不能为负数")
            if "relativeBlend" in data and data.get("relativeBlend") not in (None, "", "?"):
                val = self._to_float(data.get("relativeBlend"))
                if val is not None and val > 100:
                    r.errors.append(f"{n.title}({n.node_id}) 参数 relativeBlend 必须在 0~100")
            if "coor" in data and data.get("coor") == []:
                r.errors.append(f"{n.title}({n.node_id}) 禁止传 coor=[]，已知会导致后端崩溃")
            if "tool" in data and data.get("tool") == []:
                r.errors.append(f"{n.title}({n.node_id}) 禁止传 tool=[]，已知会导致后端崩溃")

    def _position_input(self, node: NodeData, port_name: str) -> dict | None:
        src_id = self._source_of.get((node.node_id, port_name))
        if not src_id:
            return None
        src_node = self._node_idx.get(src_id)
        if not src_node or src_node.node_type != "Position":
            return None
        data = src_node.data or {}
        if data.get("configured") is False:
            return None
        return data

    @staticmethod
    def _valid_jp(pos: dict | None) -> bool:
        if not pos:
            return False
        jp = pos.get("jp")
        if not isinstance(jp, list) or len(jp) < 6:
            return False
        try:
            [float(x) for x in jp[:6]]
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _valid_cp(pos: dict | None) -> bool:
        if not pos:
            return False
        cp = pos.get("cp")
        try:
            if isinstance(cp, dict):
                [float(cp[k]) for k in ("x", "y", "z", "a", "b", "c")]
                return True
            if isinstance(cp, list) and len(cp) >= 6:
                [float(x) for x in cp[:6]]
                return True
        except (KeyError, TypeError, ValueError):
            return False
        return False

    def _check_flow_unique_output(self, graph: GraphData, r: ValidationResult):
        """每个 flow 输出端口最多只能连一条边 (If/For/While除外)"""
        CONTROL_NODES = {"If", "For", "While"}
        flow_out_edges: dict[tuple[str, str], list[str]] = {}
        for e in graph.edges:
            src_ports = self._port_map.get(e.source_node_id, [])
            is_flow_out = any(n == e.source_port_name and t == "flow" and d == "output" for n, t, d in src_ports)
            if is_flow_out:
                key = (e.source_node_id, e.source_port_name)
                flow_out_edges.setdefault(key, []).append(e.edge_id)
        for (nid, port), eids in flow_out_edges.items():
            if len(eids) > 1:
                node = self._node_idx.get(nid)
                if node and node.node_type in CONTROL_NODES:
                    continue  # 控制流节点允许多个 flow 输出
                title = node.title if node else nid
                r.errors.append(f"{title}({nid}) 的 flow 输出 '{port}' 连接了 {len(eids)} 条边，不能分叉")

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
