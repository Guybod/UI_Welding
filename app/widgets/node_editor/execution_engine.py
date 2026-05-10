import time
from PySide6.QtCore import QObject, Signal, QTimer
from app.widgets.node_editor.models import GraphData, NODE_SPECS


class ExecutionEngine(QObject):
    """图执行引擎 — DryRun + Online(真实TCP指令)"""

    node_highlight = Signal(str, bool)
    log_emitted = Signal(str)
    graph_started = Signal()
    graph_finished = Signal()
    graph_stopped = Signal()

    MOTION_TIMEOUT_START = 3000    # ms to wait for moving=true
    MOTION_TIMEOUT_FINISH = 60000  # ms to wait for moving=false
    POLL_INTERVAL = 100            # ms between polls

    def __init__(self, parent=None):
        super().__init__(parent)
        self._send_cb = None       # callable(ty, db) for TCP commands
        self._graph: GraphData | None = None
        self._flow_map: dict[str, str] = {}
        self._data_sources: dict[tuple[str, str], tuple[str, str]] = {}
        self._node_idx: dict = {}
        self._path: list[str] = []
        self._cursor: int = 0
        self._running: bool = False
        self._online: bool = False
        self._poll_timer: QTimer | None = None
        self._motion_started: bool = False
        self._wait_start: float = 0

    # ── public ──

    def set_send_callback(self, cb):
        self._send_cb = cb

    def run_dry(self, graph: GraphData):
        self._start(graph, online=False)

    def run_online(self, graph: GraphData):
        self._start(graph, online=True)

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._poll_timer:
            self._poll_timer.stop()
        self._clear_highlight()
        # send stopMove if in online mode
        if self._online and self._send_cb:
            try:
                self._send_cb("Robot/stopMove", {})
            except Exception:
                pass
        self.log_emitted.emit("[执行] 已停止")
        self.graph_stopped.emit()

    # ── start ──

    def _start(self, graph: GraphData, online: bool):
        self._graph = graph
        self._online = online
        self._build_maps()
        self._build_path()
        self._cursor = 0
        self._running = True
        self._motion_started = False
        mode = "[在线]" if online else "[DryRun]"
        self.graph_started.emit()
        self.log_emitted.emit(f"{mode} 开始执行")
        self._step()

    # ── step ──

    def _step(self):
        if not self._running:
            return
        if self._cursor >= len(self._path):
            self._running = False
            self.log_emitted.emit("[执行] 完成")
            self.graph_finished.emit()
            self._clear_highlight()
            return

        node_id = self._path[self._cursor]
        node = self._node_idx[node_id]
        self._clear_highlight()
        self.node_highlight.emit(node_id, True)

        nt = node.node_type
        self.log_emitted.emit(f"  ▶ {node.title} ({nt})")

        if nt in ("MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"):
            if self._online:
                self._exec_motion_online(node)
                return  # will continue in poll
            else:
                self._exec_motion_dry(node)
        else:
            self._execute_dry(node)

        self._cursor += 1
        QTimer.singleShot(100 if self._online else 150, self._step)

    # ── motion online ──

    def _exec_motion_online(self, node):
        """发送 Robot/move 指令, 等待 CRI moving"""
        payload = self._build_move_payload(node)
        if payload is None:
            self.log_emitted.emit(f"    ⚠ {node.node_type}: 无法构建运动指令")
            self._cursor += 1
            QTimer.singleShot(50, self._step)
            return

        self.log_emitted.emit(f"    📤 Robot/move db={payload}")
        if self._send_cb:
            self._send_cb("Robot/move", payload)

        self._motion_started = False
        self._wait_start = time.time() * 1000
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_motion)
        self._poll_timer.start(self.POLL_INTERVAL)

    def _poll_motion(self):
        from services.robot_realtime_state import RobotRealtimeState
        state = RobotRealtimeState.instance()
        moving = state.is_moving()
        elapsed = time.time() * 1000 - self._wait_start

        if not self._motion_started:
            if moving:
                self._motion_started = True
                self._wait_start = time.time() * 1000
                self.log_emitted.emit("    🏃 运动中...")
            elif elapsed > self.MOTION_TIMEOUT_START:
                self.log_emitted.emit("    ⚠ 运动启动超时, 跳过")
                self._finish_motion_poll()
                return
        else:
            if not moving:
                self.log_emitted.emit(f"    ✅ 运动完成 ({elapsed:.0f}ms)")
                self._finish_motion_poll()
                return
            if elapsed > self.MOTION_TIMEOUT_FINISH:
                self.log_emitted.emit("    ⚠ 运动完成超时, 跳过")
                self._finish_motion_poll()
                return

    def _finish_motion_poll(self):
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        self._cursor += 1
        if self._running:
            QTimer.singleShot(50, self._step)

    def _build_move_payload(self, node) -> list | None:
        """构建 Robot/move 的 db 数组"""
        nt = node.node_type
        data = node.data
        spec = NODE_SPECS.get(nt)
        if not spec:
            return None

        jp = None
        cp = None
        for p in spec.ports:
            if p.port_type == "pose" and p.direction == "input":
                src = self._data_sources.get((node.node_id, p.name))
                if src:
                    src_node = self._node_idx.get(src[0])
                    if src_node and src_node.node_type == "Position":
                        pd = src_node.data
                        jp = pd.get("jp")
                        cp_raw = pd.get("cp", {})
                        if isinstance(cp_raw, dict):
                            cp = [cp_raw.get("x",0), cp_raw.get("y",0), cp_raw.get("z",0),
                                  cp_raw.get("a",0), cp_raw.get("b",0), cp_raw.get("c",0)]

        if nt == "MoveJ" and jp:
            tp = {"jp": jp, "ep": []}
        elif cp:
            tp = {"cp": cp, "ep": []}
        else:
            return None

        motion = {
            "type": nt if nt != "MovePath" else "movJ",
            "speed": data.get("speed", 200),
            "acc": data.get("acc", 500),
            "blend": data.get("blend", 0),
            "targetPoint": tp,
        }
        return [motion]

    # ── motion dryrun ──

    def _exec_motion_dry(self, node):
        spec = NODE_SPECS.get(node.node_type)
        if not spec:
            return
        for p in spec.ports:
            if p.port_type == "pose" and p.direction == "input":
                src = self._data_sources.get((node.node_id, p.name))
                if src:
                    src_node = self._node_idx.get(src[0])
                    if src_node and src_node.node_type == "Position":
                        pos_data = src_node.data
                        name = pos_data.get("name", src_node.title)
                        jp = pos_data.get("jp", [])
                        cp = pos_data.get("cp", {})
                        data = node.data
                        if node.node_type == "MoveJ":
                            target = f"jp={jp}"
                        else:
                            target = f"cp={cp}"
                        self.log_emitted.emit(
                            f"    🏃 {node.node_type} → {name} {target}"
                            f" speed={data.get('speed','?')}mm/s"
                        )
                        return
        self.log_emitted.emit(f"    ⚠ {node.node_type}: 未找到点位数据")

    # ── common dryrun ──

    def _execute_dry(self, node):
        nt = node.node_type
        if nt in ("Start", "End"):
            if nt == "End":
                self.log_emitted.emit("  ⏹ 到达 End")
        elif nt == "Position":
            data = node.data
            self.log_emitted.emit(f"    点位: {data.get('name', node.title)}")
        elif nt == "Print":
            val = self._resolve_input_raw(node, "value")
            self.log_emitted.emit(f"    🖨 打印: {val}")
        elif nt == "Wait":
            dur = self._resolve_input_raw(node, "duration")
            self.log_emitted.emit(f"    等待 {dur} 秒")
        elif nt in ("SetDO", "SetAO"):
            port = self._resolve_input_raw(node, "port")
            value = self._resolve_input_raw(node, "value")
            self.log_emitted.emit(f"    设置 {nt} port={port} val={value}")
        elif nt in ("ReadDI", "ReadAI"):
            port = self._resolve_input_raw(node, "port")
            self.log_emitted.emit(f"    读取 {nt} port={port}")
        elif nt in ("SetRegister", "ReadRegister"):
            addr = self._resolve_input_raw(node, "address")
            val = self._resolve_input_raw(node, "value")
            self.log_emitted.emit(f"    {nt} addr={addr} val={val}")
        elif nt in ("Add", "Sub", "Mul", "Div", "Pow", "Mod",
                     "Gt", "Lt", "Eq", "Ge", "Le"):
            a = self._resolve_input_raw(node, "a")
            b = self._resolve_input_raw(node, "b")
            self.log_emitted.emit(f"    {nt}: {a} {self._op_symbol(nt)} {b}")
        elif nt in ("Int", "Float", "Bool", "String", "Array"):
            self.log_emitted.emit(f"    常量 {nt}")

    def _resolve_input_raw(self, node, port_name):
        """解析输入端口的值 (返回原始 Python 值)"""
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return node.data.get(port_name, "?")
        src_node_id, src_port_name = src
        src_node = self._node_idx.get(src_node_id)
        if not src_node:
            return "?"
        if src_node.node_type == "GetVar":
            return src_node.data.get("var_value", "?")
        if src_node.node_type in ("Int",):
            return src_node.data.get("value", 0)
        if src_node.node_type in ("Float",):
            return src_node.data.get("value", 0.0)
        if src_node.node_type == "Bool":
            return src_node.data.get("value", False)
        if src_node.node_type == "String":
            return src_node.data.get("value", "")
        if src_node.node_type == "Position":
            return src_node.data.get("name", src_node.title)
        return "?"

    # ── common ──

    def _build_maps(self):
        self._node_idx = {n.node_id: n for n in self._graph.nodes}
        self._flow_map.clear()
        self._data_sources.clear()
        for e in self._graph.edges:
            is_flow = False
            src_node = self._node_idx.get(e.source_node_id)
            if src_node:
                src_spec = NODE_SPECS.get(src_node.node_type)
                if src_spec:
                    for p in src_spec.ports:
                        if p.name == e.source_port_name and p.port_type == "flow" and p.direction == "output":
                            is_flow = True
                            break
            # also check dynamic ports stored in data
            if not is_flow and src_node and src_node.data.get("_ports"):
                for pn, pt, pd in src_node.data["_ports"]:
                    if pn == e.source_port_name and pt == "flow" and pd == "output":
                        is_flow = True
                        break
            if is_flow:
                self._flow_map[e.source_node_id] = e.target_node_id
            else:
                self._data_sources[(e.target_node_id, e.target_port_name)] = (e.source_node_id, e.source_port_name)

    def _build_path(self):
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

    def _op_symbol(self, nt: str) -> str:
        syms = {"Add": "+", "Sub": "-", "Mul": "x", "Div": "/", "Pow": "^",
                "Mod": "%", "Gt": ">", "Lt": "<", "Eq": "==", "Ge": ">=", "Le": "<="}
        return syms.get(nt, nt)

    def _clear_highlight(self):
        for nid in self._path:
            self.node_highlight.emit(nid, False)
