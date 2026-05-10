from PySide6.QtCore import QObject, Signal, QTimer
from app.widgets.node_editor.models import GraphData, NODE_SPECS


class ExecutionEngine(QObject):
    """图执行引擎 — DryRun 不发送真实 TCP 指令"""

    node_highlight = Signal(str, bool)  # node_id, highlight on/off
    log_emitted = Signal(str)          # log message
    graph_started = Signal()
    graph_finished = Signal()
    graph_stopped = Signal()
    step_done = Signal()               # internal: advance to next step

    def __init__(self, parent=None):
        super().__init__(parent)
        self._graph: GraphData | None = None
        self._flow_map: dict[str, str] = {}        # node_id → next node_id via flow
        self._data_sources: dict[tuple[str, str], tuple[str, str]] = {}  # (node,port)→(src_node,src_port)
        self._node_idx: dict[str, GraphData.__annotations__] = {}  # node_id → NodeData
        self._path: list[str] = []   # execution order
        self._cursor: int = 0
        self._running: bool = False
        self._timer: QTimer | None = None

    # ── public ──

    def run_dry(self, graph: GraphData):
        self._graph = graph
        self._build_maps()
        self._build_path()
        self._cursor = 0
        self._running = True
        self.graph_started.emit()
        self.log_emitted.emit("[DryRun] 开始执行")
        self._step()

    def stop(self):
        if self._running:
            self._running = False
            if self._timer:
                self._timer.stop()
            self._clear_highlight()
            self.log_emitted.emit("[DryRun] 执行已停止")
            self.graph_stopped.emit()

    # ── internal ──

    def _build_maps(self):
        self._node_idx = {n.node_id: n for n in self._graph.nodes}
        self._flow_map.clear()
        self._data_sources.clear()

        for e in self._graph.edges:
            # distinguish flow vs data
            is_flow = False
            src_node = self._node_idx.get(e.source_node_id)
            if src_node:
                src_spec = NODE_SPECS.get(src_node.node_type)
                if src_spec:
                    for p in src_spec.ports:
                        if p.name == e.source_port_name and p.port_type == "flow" and p.direction == "output":
                            is_flow = True
                            break
            if is_flow:
                self._flow_map[e.source_node_id] = e.target_node_id
            else:
                self._data_sources[(e.target_node_id, e.target_port_name)] = (e.source_node_id, e.source_port_name)

    def _build_path(self):
        """沿 flow 边从 Start 走到 End"""
        self._path = []
        start_id = None
        for n in self._graph.nodes:
            if n.node_type == "Start":
                start_id = n.node_id
                break
        if not start_id:
            return
        cur = start_id
        while cur:
            self._path.append(cur)
            if self._node_idx[cur].node_type == "End":
                break
            cur = self._flow_map.get(cur)

    def _step(self):
        if not self._running:
            return
        if self._cursor >= len(self._path):
            self._running = False
            self.log_emitted.emit("[DryRun] 执行完成")
            self.graph_finished.emit()
            return

        node_id = self._path[self._cursor]
        node = self._node_idx[node_id]
        self._clear_highlight()
        self.node_highlight.emit(node_id, True)
        self._execute_dry(node)
        self._cursor += 1

        self._timer = QTimer.singleShot(150, self._step)

    def _execute_dry(self, node):
        nt = node.node_type
        self.log_emitted.emit(f"  ▶ {node.title} ({nt})")

        if nt == "Start":
            pass
        elif nt == "End":
            self.log_emitted.emit("  ⏹ 到达 End")
        elif nt == "Position":
            data = node.data
            name = data.get("name", node.title)
            jp = data.get("jp", [])
            cp = data.get("cp", {})
            self.log_emitted.emit(f"    点位: {name} jp={jp} cp={cp}")
        elif nt == "Print":
            val = self._resolve_input(node, "value")
            self.log_emitted.emit(f"    🖨 打印: {val}")
        elif nt in ("MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"):
            self._exec_motion_dry(node)
        elif nt == "Wait":
            dur = self._resolve_input(node, "duration")
            self.log_emitted.emit(f"    等待 {dur} 秒")
        elif nt == "SetDO":
            port = self._resolve_input(node, "port")
            value = self._resolve_input(node, "value")
            self.log_emitted.emit(f"    设置 DO{port} = {value}")
        elif nt == "ReadDI":
            port = self._resolve_input(node, "port")
            self.log_emitted.emit(f"    读取 DI{port}")
        elif nt == "SetAO":
            port = self._resolve_input(node, "port")
            value = self._resolve_input(node, "value")
            self.log_emitted.emit(f"    设置 AO{port} = {value}")
        elif nt == "ReadAI":
            port = self._resolve_input(node, "port")
            self.log_emitted.emit(f"    读取 AI{port}")
        elif nt in ("Add", "Sub", "Mul", "Div", "Pow", "Mod"):
            a = self._resolve_input(node, "a")
            b = self._resolve_input(node, "b")
            self.log_emitted.emit(f"    运算 {nt}: {a} {self._op_symbol(nt)} {b}")
        elif nt in ("Gt", "Lt", "Eq", "Ge", "Le"):
            a = self._resolve_input(node, "a")
            b = self._resolve_input(node, "b")
            self.log_emitted.emit(f"    比较 {nt}: {a} {self._op_symbol(nt)} {b}")
        elif nt in ("Int", "Float", "Bool", "String", "Array"):
            self.log_emitted.emit(f"    变量 {nt}")

    def _exec_motion_dry(self, node):
        """DryRun 运动节点: 解析 pose 输入 → 打印运动指令"""
        # find which ports need pose data
        spec = NODE_SPECS.get(node.node_type)
        if not spec:
            return
        for p in spec.ports:
            if p.port_type == "pose" and p.direction == "input":
                src = self._data_sources.get((node.node_id, p.name))
                if src:
                    src_node_id, src_port_name = src
                    src_node = self._node_idx.get(src_node_id)
                    if src_node and src_node.node_type == "Position":
                        pos_data = src_node.data
                        name = pos_data.get("name", src_node.title)
                        jp = pos_data.get("jp", [])
                        cp = pos_data.get("cp", {})
                        opt = pos_data.get("optional", {})
                        # select jp or cp based on motion type
                        if node.node_type == "MoveJ":
                            target = f"jp={jp}"
                        else:
                            target = f"cp={cp}"
                        self.log_emitted.emit(
                            f"    🏃 {node.node_type} → {name} {target}"
                            f" speed={opt.get('speed','?')}mm/s acc={opt.get('acc','?')}mm/s²"
                        )
                        return
        self.log_emitted.emit(f"    ⚠ {node.node_type}: 未找到点位数据")

    def _resolve_input(self, node, port_name) -> str:
        """解析节点的某个输入端口的值"""
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return "?"
        src_node_id, src_port_name = src
        src_node = self._node_idx.get(src_node_id)
        if not src_node:
            return "?"
        if src_node.node_type in ("Int", "Float"):
            return str(src_node.data.get("value", "?"))
        if src_node.node_type == "Bool":
            return str(src_node.data.get("value", False))
        if src_node.node_type == "String":
            return src_node.data.get("value", "")
        if src_node.node_type == "Position":
            return src_node.data.get("name", src_node.title)
        return "?"

    def _op_symbol(self, nt: str) -> str:
        syms = {"Add": "+", "Sub": "-", "Mul": "×", "Div": "÷", "Pow": "^",
                "Mod": "%", "Gt": ">", "Lt": "<", "Eq": "==", "Ge": "≥", "Le": "≤"}
        return syms.get(nt, nt)

    def _clear_highlight(self):
        for nid in self._path:
            self.node_highlight.emit(nid, False)
