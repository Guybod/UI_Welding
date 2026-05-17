import time
from typing import Any, Callable

import math as _math

from PySide6.QtCore import QObject, Signal, QTimer

from app.i18n import tr
from app.widgets.node_editor.models import GraphData, NodeData, NODE_SPECS, is_pure_node_type


class ExecutionEngine(QObject):
    """节点图执行引擎。

    设计原则：
    - DryRun 只模拟执行，不发送 TCP。
    - Online 只允许已明确实现的节点真实发送 TCP。
    - 运动节点发送 Robot/move 后，不能用 TCP response 判断完成，必须等待 CRI moving。
    - 禁止 time.sleep / 阻塞 while，全部用 QTimer 状态机推进。
    - 执行模型：图遍历（非预计算线性路径）。每个节点执行后根据 flow 输出边决定下一节点。
      控制流节点 (If/For/While/Sequence) 在运行时动态选择分支。
    """

    SEQUENCE_THEN_PORTS = ("then_0", "then_1", "then_2")

    node_highlight = Signal(str, bool)
    pin_value_emitted = Signal(str, str, object)  # node_id, output_port_name, value
    log_emitted = Signal(str)
    graph_started = Signal()
    graph_finished = Signal()
    graph_stopped = Signal()

    MOTION_TIMEOUT_START = 1000      # 等待 moving false -> true 的默认超时，ms
    MOTION_TIMEOUT_FINISH = 60000    # 等待 moving true -> false 的默认超时，ms
    POLL_INTERVAL = 100              # CRI 状态轮询周期，ms

    MOTION_TYPE_MAP = {
        "MoveJ": "movJ",
        "MoveL": "movL",
        "MoveC": "movC",
        "MoveCircle": "movCircle",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._send_cb: Callable | None = None
        self._graph: GraphData | None = None
        self._data_sources: dict[tuple[str, str], tuple[str, str]] = {}
        self._node_idx: dict[str, NodeData] = {}
        self._current_node_id: str | None = None
        self._active_node_id: str | None = None   # for highlight clearing
        self._running: bool = False
        self._online: bool = False
        self._stopping: bool = False

        self._poll_timer: QTimer | None = None
        self._motion_started: bool = False
        self._motion_phase: str = "idle"
        self._wait_start_ms: float = 0.0
        self._active_node: NodeData | None = None
        self._active_target: dict | None = None
        self._run_token: int = 0
        self._return_stack: list = []  # For: (id,i,end,step) | While: ("while", id) | Sequence: ("sequence", id, ports, idx)
        self._runtime_vars: dict[str, object] = {}
        self._value_cache: dict[tuple[str, str], object] = {}
        self._pin_values: dict[tuple[str, str], object] = {}
        self._macro_stack: list[dict] = []
        self._macro_resolver = None  # (macro_id) -> MacroDef | None
        self._macro_param_bindings: dict[tuple[str, str], object] = {}
        self._macro_call_outputs: dict[tuple[str, str], object] = {}

    # ───────────────────────── public ─────────────────────────

    def set_macro_resolver(self, resolver):
        """设置宏查找回调：macro_id -> MacroDef | None。"""
        self._macro_resolver = resolver

    def set_send_callback(self, cb: Callable):
        """设置 TCP 发送回调。

        推荐签名：
            cb(ty, db, on_response=None, on_error=None)

        兼容旧签名：
            cb(ty, db)
        """
        self._send_cb = cb

    def run_dry(self, graph: GraphData):
        self._start(graph, online=False)

    def run_online(self, graph: GraphData):
        self._start(graph, online=True)

    def stop(self):
        """停止图执行。

        Online 模式下会尽量发送 Robot/stopMove。这里不处理 Jog/moveTo，
        因为节点执行引擎当前不应该启动 Jog/moveTo 心跳。
        """
        if not self._running:
            return

        self._stopping = True
        self._running = False
        self._run_token += 1
        self._stop_poll_timer()
        self._clear_highlight()

        if self._online:
            self._send_command(
                "Robot/stopMove",
                {},
                on_response=lambda _db: None,
                on_error=lambda e: self._log(f"[停止] Robot/stopMove 失败: {e}"),
            )

        self._log(tr("log_stopped"))
        self.graph_stopped.emit()

    # ───────────────────────── start / step ─────────────────────────

    def _start(self, graph: GraphData, online: bool):
        self._stop_poll_timer()
        self._graph = graph
        self._online = online
        self._stopping = False
        self._run_token += 1
        self._build_maps()
        self._current_node_id = self._find_start_node()
        self._running = True
        self._motion_started = False
        self._motion_phase = "idle"
        self._active_node = None
        self._active_target = None
        self._return_stack.clear()
        self._path_queue = []
        self._path_node = None
        self._path_index = 0
        self._value_cache = {}
        self._pin_values: dict[tuple[str, str], object] = {}
        self._loop_counters = {}
        self._while_iter_counts: dict[str, int] = {}
        self._macro_stack.clear()
        self._macro_param_bindings.clear()
        self._macro_call_outputs.clear()
        self._runtime_vars = self._init_runtime_vars()

        mode = "[在线]" if online else "[DryRun]"
        self.graph_started.emit()
        self._log(f"{mode} Start")

        if not self._current_node_id:
            self._fail_graph("Start node not found")
            return

        QTimer.singleShot(0, self._step)

    def _step(self):
        if not self._running:
            return

        # If no current node, check return stack (loop / sequence branch completed)
        if not self._current_node_id:
            if self._return_stack:
                ret = self._return_stack.pop()
                if len(ret) >= 4 and ret[0] == "sequence":
                    self._on_sequence_branch_done(ret[1], ret[2], ret[3])
                    return
                if len(ret) == 2 and ret[0] == "while":
                    self._current_node_id = ret[1]
                    QTimer.singleShot(50, lambda: self._step())
                    return
                for_node_id, _i, _end, _step = ret
                self._current_node_id = for_node_id
                QTimer.singleShot(50, lambda: self._step())
                return
            self._finish_graph()
            return

        node_id = self._current_node_id
        node = self._node_idx.get(node_id)
        if not node:
            self._fail_graph(f"Node in execution path not found: {node_id}")
            return

        self._clear_highlight()
        self._active_node_id = node_id
        self.node_highlight.emit(node_id, True)
        self._active_node = node

        nt = node.node_type
        self._log(f"  ▶ {node.title} ({nt})")

        if (node.data or {}).get("disabled"):
            self._log(tr("log_node_disabled").format(title=node.title))
            self._advance_to(self._flow_target(node, "flow"), 50)
            return

        if nt == "End":
            if self._macro_stack:
                self._exit_macro()
                return
            if self._return_stack:
                top = self._return_stack[-1]
                if len(top) >= 4 and top[0] == "sequence":
                    self._return_stack.pop()
                    self._on_sequence_branch_done(top[1], top[2], top[3])
                    return
                if len(top) == 2 and top[0] == "while":
                    _tag, while_id = self._return_stack.pop()
                    self._current_node_id = while_id
                    QTimer.singleShot(50, self._step)
                    return
            self._log(tr("log_end_reached"))
            self._finish_graph()
            return

        if nt in ("Start", "Position", "Comment"):
            self._execute_passive(node)
            return

        if nt == "Wait":
            self._watch_input_ports(node, ("duration_ms",))
            self._exec_wait(node)
            return

        if nt in ("MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"):
            self._watch_motion_inputs(node)
            if self._online:
                self._exec_motion_online(node)
            else:
                self._exec_motion_dry(node)
            return

        if nt in ("SetDO", "SetAO", "ReadDI", "ReadAI", "SetRegister", "ReadRegister", "ArraySet"):
            if self._online and nt != "ArraySet":
                self._exec_io_register_online(node)
            elif nt == "ArraySet":
                self._exec_array_set(node)
            else:
                self._execute_dry(node)
                self._watch_io_register_outputs(node)
                self._advance_to(self._flow_target(node, "flow"), 150)
            return

        if nt == "SetVar":
            self._exec_set_var(node)
            return

        if nt in ("If", "For", "While"):
            self._exec_control_flow(node)
            return

        if nt == "Sequence":
            self._exec_sequence(node)
            return

        if nt == "MacroCall":
            self._enter_macro(node)
            return

        dyn_ports = (node.data or {}).get("_ports")
        if is_pure_node_type(nt, dyn_ports):
            self._log(f"    ⚠ 纯节点 {nt} 不应出现在 flow 链上，已跳过")
            self._advance_to(self._flow_target(node, "flow"), 50)
            return

        if nt == "Print":
            val = self._resolve_input_raw(node, "value")
            self._emit_pin_watch(node.node_id, "value", val)
            self._execute_dry(node)
            self._advance_to(self._flow_target(node, "flow"), 100 if self._online else 150)
            return

        from app.widgets.node_editor.plugins.registry import get_flow_handler

        plugin_flow = get_flow_handler(nt)
        if plugin_flow:
            plugin_flow(self, node)
            return

        self._log(f"    ⚠ 未实现的 flow 节点: {nt}")
        self._advance_to(self._flow_target(node, "flow"), 100 if self._online else 150)

    def _execute_passive(self, node: NodeData):
        if node.node_type == "Position":
            self._log(f"    {tr('log_position')} {node.data.get('name', node.title)}")
        self._advance_to(self._flow_target(node, "flow"), 80)

    def _advance_to(self, next_id: str | None, delay_ms: int = 50):
        """设置下一执行节点并调度 _step。next_id 为 None 时表示分支/路径结束。"""
        token = self._run_token
        self._current_node_id = next_id
        QTimer.singleShot(delay_ms, lambda t=token: self._step_if_token(t))

    def _step_if_token(self, token: int):
        if token != self._run_token or not self._running:
            return
        self._step()

    # ───────────────────────── graph traversal helpers ─────────────────────────

    def _find_start_node(self) -> str | None:
        if not self._graph:
            return None
        for n in self._graph.nodes:
            if n.node_type == "Start":
                return n.node_id
        return None

    def _enter_macro(self, node: NodeData) -> None:
        data = node.data or {}
        macro_id = (data.get("macro_id") or "").strip()
        if not self._macro_resolver or not macro_id:
            self._fail_node(node, tr("macro_missing_resolver"))
            return
        macro = self._macro_resolver(macro_id)
        if not macro:
            self._fail_node(node, tr("macro_not_found").format(name=data.get("macro_name", macro_id)))
            return
        from app.widgets.node_editor.macro_storage import clone_macro_graph

        inner = clone_macro_graph(macro.graph)
        start_id = self._find_start_in_graph(inner)
        if not start_id:
            self._fail_node(node, tr("macro_no_start"))
            return
        return_id = self._flow_target(node, "flow")
        from app.widgets.node_editor.macro_ports import macro_input_params, macro_output_params

        bindings: dict[tuple[str, str], object] = {}
        for p in macro_input_params(macro):
            val = self._resolve_input_raw(node, p.param_id)
            bindings[(p.inner_node_id, p.inner_port_name)] = val
            self._emit_pin_watch(node.node_id, p.param_id, val)
        outer_graph = self._graph
        self._macro_stack.append({
            "graph": outer_graph,
            "return_node_id": return_id,
            "return_stack": list(self._return_stack),
            "loop_counters": dict(getattr(self, "_loop_counters", {})),
            "while_iter_counts": dict(self._while_iter_counts),
            "call_node_id": node.node_id,
            "macro_id": macro_id,
            "output_params": macro_output_params(macro),
        })
        self._return_stack.clear()
        inner.variables = list(outer_graph.variables) if outer_graph else []
        inner.positions = list(outer_graph.positions) if outer_graph else []
        self._graph = inner
        self._macro_param_bindings = bindings
        self._build_maps()
        self._current_node_id = start_id
        self._log(tr("log_macro_enter").format(name=macro.name))
        QTimer.singleShot(50, self._step)

    @staticmethod
    def _find_start_in_graph(graph: GraphData) -> str | None:
        for n in graph.nodes:
            if n.node_type == "Start":
                return n.node_id
        return None

    def _exit_macro(self) -> None:
        if not self._macro_stack:
            self._finish_graph()
            return
        frame = self._macro_stack[-1]
        call_id = frame.get("call_node_id")
        for p in frame.get("output_params") or []:
            val = self._eval_data(p.inner_node_id, p.inner_port_name)
            if call_id:
                self._macro_call_outputs[(call_id, p.param_id)] = val
                self._emit_pin_watch(call_id, p.param_id, val)
        frame = self._macro_stack.pop()
        self._graph = frame["graph"]
        self._return_stack = frame["return_stack"]
        self._loop_counters = frame.get("loop_counters", {})
        self._while_iter_counts = frame.get("while_iter_counts", {})
        self._build_maps()
        self._macro_param_bindings.clear()
        self._current_node_id = frame.get("return_node_id")
        self._log(tr("log_macro_exit"))
        if self._current_node_id:
            QTimer.singleShot(50, self._step)
        else:
            QTimer.singleShot(50, self._step)

    def _flow_target(self, node: NodeData, port_name: str) -> str | None:
        """找到某 flow 输出端口连接的目标节点"""
        for e in self._graph.edges:
            if e.source_node_id == node.node_id and e.source_port_name == port_name:
                return e.target_node_id
        return None

    # ───────────────────────── online motion ─────────────────────────

    def _exec_motion_online(self, node: NodeData):
        if node.node_type == "MovePath":
            self._exec_move_path_online(node)
            return

        db = self._build_move_db(node)
        if db is None:
            self._fail_node(node, f"{node.node_type}: 无法构建合法运动指令")
            return

        self._log(tr("log_motion_send"))
        token = self._run_token

        def _on_response(_db):
            if token != self._run_token or not self._running:
                return
            self._begin_motion_wait(node, db)

        def _on_error(e):
            if token != self._run_token:
                return
            self._fail_node(node, f"Robot/move send failed: {e}")

        self._send_command("Robot/move", db, on_response=_on_response, on_error=_on_error)

    def _exec_move_path_online(self, node: NodeData):
        """MovePath: 顺序发送多个 Robot/move，每个等 CRI moving 完成再下一个"""
        waypoints = self._collect_path_waypoints(node)
        if not waypoints:
            self._fail_node(node, "MovePath 没有合法途径点（需连接至少一个 Position）")
            return

        self._path_queue = list(waypoints)  # [(move_db, label), ...]
        self._path_node = node
        self._path_index = 0
        self._log(f"    🛤 MovePath: {len(waypoints)} waypoints")
        self._send_path_next()

    def _send_path_next(self):
        """发送路径队列中的下一个 move"""
        if not self._running:
            return
        if self._path_index >= len(self._path_queue):
            self._log(f"    ✅ MovePath complete")
            self._advance_to(self._flow_target(self._path_node, "flow"), 50)
            return

        db, label = self._path_queue[self._path_index]
        self._path_index += 1
        self._log(f"    📤 MovePath [{self._path_index}/{len(self._path_queue)}] {label}")

        token = self._run_token

        def _on_response(_db):
            if token != self._run_token or not self._running:
                return
            self._begin_motion_wait(self._path_node, db)

        def _on_error(e):
            if token != self._run_token:
                return
            self._fail_node(self._path_node, f"MovePath 第{self._path_index}段发送失败: {e}")

        self._send_command("Robot/move", db, on_response=_on_response, on_error=_on_error)

    def _collect_path_waypoints(self, node: NodeData) -> list[tuple[list[dict], str]]:
        """收集 MovePath 所有连接的 Position 节点，构建 move 指令列表"""
        waypoints = []
        for port_name in ["pose_1", "pose_2", "pose_3"]:
            pos = self._position_for_input(node, port_name)
            if not pos:
                continue
            name = pos.get("name", "?")
            jp = self._valid_jp(pos)
            cp = self._valid_cp(pos)
            opt = pos.get("optional", {})

            if not jp and not cp:
                continue

            motion: dict = {
                "type": "movJ" if jp else "movL",
                "speed": self._num(opt.get("speed", 200), 200),
                "acc": self._num(opt.get("acc", 500), 500),
                "blend": self._num(opt.get("blend", 0), 0),
            }
            if opt.get("relativeBlend") not in (None, "", "?"):
                motion["relativeBlend"] = self._num(opt.get("relativeBlend"), 0)

            target = {}
            if jp:
                target["jp"] = jp
            else:
                target["cp"] = cp
            target["ep"] = self._valid_ep(pos)
            motion["targetPoint"] = target
            waypoints.append(([motion], name))

        return waypoints

    def _begin_motion_wait(self, node: NodeData, db: list[dict]):
        self._active_node = node
        self._active_target = self._extract_motion_target(node, db)
        self._motion_started = False
        self._motion_phase = "wait_start"
        self._wait_start_ms = self._now_ms()
        self._stop_poll_timer()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self.POLL_INTERVAL)
        self._poll_timer.timeout.connect(self._poll_motion)
        self._poll_timer.start()
        self._log(tr("log_motion_wait_start"))

    def _poll_motion(self):
        if not self._running or not self._active_node:
            self._stop_poll_timer()
            return

        from services.robot_realtime_state import RobotRealtimeState

        state = RobotRealtimeState.instance()
        moving = bool(state.is_moving())
        elapsed = self._now_ms() - self._wait_start_ms

        if not self._motion_started:
            if moving:
                self._motion_started = True
                self._motion_phase = "wait_finish"
                self._wait_start_ms = self._now_ms()
                self._log(tr("log_motion_running"))
                return

            if elapsed >= self.MOTION_TIMEOUT_START:
                if self._is_target_reached(state, self._active_target):
                    self._log("    ✅ No moving=true detected, but position close to target, treating as short motion done")
                    self._finish_motion_success()
                else:
                    self._fail_node(self._active_node, "Motion start timeout, position not close to target")
                return

        else:
            if not moving:
                self._log(f"    {tr('log_motion_done')} ({elapsed:.0f}ms)")
                self._finish_motion_success()
                return

            if elapsed >= self.MOTION_TIMEOUT_FINISH:
                self._fail_node(self._active_node, "Motion finish timeout")
                return

    def _finish_motion_success(self):
        node = self._active_node
        self._stop_poll_timer()
        self._active_target = None
        self._motion_started = False
        self._motion_phase = "idle"
        # MovePath: 还有后续途径点则继续，否则结束
        if node and node.node_type == "MovePath" and hasattr(self, '_path_queue') and self._path_index < len(self._path_queue):
            self._send_path_next()
        else:
            next_id = self._flow_target(node, "flow") if node else None
            self._advance_to(next_id, 50)

    def _build_move_db(self, node: NodeData) -> list[dict] | None:
        """构建 Robot/move 的 db 数组。"""
        nt = node.node_type
        if nt not in self.MOTION_TYPE_MAP:
            return None

        data = node.data or {}
        motion: dict[str, Any] = {
            "type": self.MOTION_TYPE_MAP[nt],
            "speed": self._num(data.get("speed", 200), 200),
            "acc": self._num(data.get("acc", 500), 500),
            "blend": self._num(data.get("blend", 0), 0),
        }

        if data.get("relativeBlend") not in (None, "", "?"):
            motion["relativeBlend"] = self._num(data.get("relativeBlend"), 0)

        if nt == "MoveJ":
            pos = self._position_for_input(node, "target")
            jp = self._valid_jp(pos)
            if not jp:
                return None
            target = {"jp": jp, "ep": self._valid_ep(pos)}
            motion["targetPoint"] = target
            return [motion]

        if nt == "MoveL":
            pos = self._position_for_input(node, "target")
            cp = self._valid_cp(pos)
            if not cp:
                return None
            target = {"cp": cp, "ep": self._valid_ep(pos)}
            motion["targetPoint"] = target
            return [motion]

        if nt in ("MoveC", "MoveCircle"):
            target_pos = self._position_for_input(node, "target")
            middle_pos = self._position_for_input(node, "middle")
            target_cp = self._valid_cp(target_pos)
            middle_cp = self._valid_cp(middle_pos)
            if not target_cp or not middle_cp:
                return None
            motion["targetPoint"] = {"cp": target_cp, "ep": self._valid_ep(target_pos)}
            motion["middlePoint"] = {"cp": middle_cp}
            if nt == "MoveCircle":
                motion["circleNum"] = int(self._num(data.get("circleNum", 1), 1))
            return [motion]

        return None

    # ───────────────────────── dry motion ─────────────────────────

    def _exec_motion_dry(self, node: NodeData):
        if node.node_type == "MovePath":
            waypoints = self._collect_path_waypoints(node)
            if waypoints:
                self._log(f"    🛤 MovePath DryRun: {len(waypoints)} waypoints")
                for i, (db, name) in enumerate(waypoints):
                    motion_type = db[0].get("type", "?")
                    tp = db[0].get("targetPoint", {})
                    self._log(f"       [{i+1}] {name} → {motion_type} target={tp}")
            else:
                self._log("    ⚠ MovePath: no valid waypoints (connect Position nodes)")
            self._advance_to(self._flow_target(node, "flow"), 150)
            return

        db = self._build_move_db(node)
        if db is None:
            self._log(f"    ⚠ {node.node_type}: 无法构建合法运动指令")
        else:
            self._log(f"    🧪 {node.node_type} 将发送 Robot/move db={db}")
        self._advance_to(self._flow_target(node, "flow"), 150)

    # ───────────────────────── control flow: If / For / While / Sequence ─────────────────────────

    def _sequence_connected_ports(self, node: NodeData) -> list[str]:
        return [p for p in self.SEQUENCE_THEN_PORTS if self._flow_target(node, p)]

    def _exec_sequence(self, node: NodeData):
        ports = self._sequence_connected_ports(node)
        self._log(tr("log_sequence_run").format(n=len(ports)))
        if not ports:
            self._advance_to(self._flow_target(node, "done"), 50)
            return
        self._start_sequence_branch(node.node_id, ports, 0)

    def _start_sequence_branch(self, seq_id: str, ports: list[str], idx: int) -> None:
        node = self._node_idx.get(seq_id)
        if not node:
            self._advance_to(None, 50)
            return
        if idx >= len(ports):
            self._advance_to(self._flow_target(node, "done"), 50)
            return
        port = ports[idx]
        target = self._flow_target(node, port)
        if not target:
            self._start_sequence_branch(seq_id, ports, idx + 1)
            return
        self._log(tr("log_sequence_branch").format(port=port))
        if idx + 1 < len(ports):
            self._return_stack.append(("sequence", seq_id, ports, idx))
        self._advance_to(target, 50)

    def _on_sequence_branch_done(self, seq_id: str, ports: list[str], idx: int) -> None:
        self._start_sequence_branch(seq_id, ports, idx + 1)

    def _exec_control_flow(self, node: NodeData):
        nt = node.node_type
        if nt == "If":
            cond_raw = self._resolve_input_raw(node, "condition")
            self._emit_pin_watch(node.node_id, "condition", cond_raw)
            cond = bool(cond_raw)
            self._log(f"    ? Condition: {'True' if cond else 'False'} (={cond_raw!r})")
            branch = "true" if cond else "false"
            target = self._flow_target(node, branch)
            if target:
                self._advance_to(target, 50)
            else:
                self._fail_node(node, f"If branch '{branch}' not connected")
        elif nt == "For":
            start = self._num(self._resolve_input_raw(node, "start"), 0)
            end = self._num(self._resolve_input_raw(node, "end"), 10)
            step = self._num(self._resolve_input_raw(node, "step"), 1)
            if step == 0:
                step = 1
            loop_key = f"for_{node.node_id}"
            if not hasattr(self, '_loop_counters'):
                self._loop_counters: dict[str, float] = {}
            if loop_key not in self._loop_counters:
                self._loop_counters[loop_key] = start
            i = self._loop_counters[loop_key]
            if (step > 0 and i < end) or (step < 0 and i > end):
                self._log(f"    🔁 For i={i}")
                node.data["_for_index"] = i
                self._emit_pin_watch(node.node_id, "index", i)
                self._watch_input_ports(node, ("start", "end", "step"))
                # 清除 For 节点的缓存值，使每次迭代重新读取 _for_index
                if hasattr(self, '_value_cache'):
                    self._value_cache.pop(self._eval_cache_key(node.node_id, None), None)
                    self._value_cache.pop(self._eval_cache_key(node.node_id, "index"), None)
                self._loop_counters[loop_key] = i + step
                self._return_stack.append((node.node_id, i + step, end, step))
                target = self._flow_target(node, "body")
                if target:
                    self._advance_to(target, 50)
                    return
            else:
                self._log(tr("log_for_done"))
                if loop_key in getattr(self, '_loop_counters', {}):
                    del self._loop_counters[loop_key]
                target = self._flow_target(node, "done")
                if target:
                    self._advance_to(target, 50)
                    return
            self._advance_to(None, 50)
        elif nt == "While":
            wc = self._while_iter_counts.get(node.node_id, 0) + 1
            self._while_iter_counts[node.node_id] = wc
            if wc > 10_000:
                self._fail_node(node, "While 超过最大迭代次数 (10000)，请检查条件或自增逻辑")
                return
            self._value_cache.clear()
            cond_raw = self._resolve_input_raw(node, "condition")
            self._emit_pin_watch(node.node_id, "condition", cond_raw)
            cond = bool(cond_raw)
            if cond:
                self._log(f"    {tr('log_while_true')} (条件={cond_raw!r}, 第{wc}轮)")
                self._return_stack.append(("while", node.node_id))
                target = self._flow_target(node, "body")
                if target:
                    self._advance_to(target, 50)
                    return
            else:
                self._log(f"    {tr('log_while_false')} (条件={cond_raw!r})")
                target = self._flow_target(node, "done")
                if target:
                    self._advance_to(target, 50)
                    return
            self._advance_to(None, 50)

    def _exec_set_var(self, node: NodeData):
        data = node.data or {}
        var_id = data.get("var_id", "")
        val = self._resolve_input_raw(node, "value")
        from app.widgets.node_editor.var_value import format_var_storage, parse_var_storage

        var_type = data.get("var_type", "int")
        if var_type == "int":
            val = int(self._num(val, 0))
        elif var_type == "float":
            val = float(self._num(val, 0))
        elif var_type == "bool":
            val = bool(val)
        elif var_type == "string":
            val = "" if val is None else str(val)
        else:
            val = parse_var_storage(val, var_type)
        if var_id:
            self._runtime_vars[var_id] = val
            self._sync_var_to_library(var_id, val)
            self._sync_var_nodes(var_id, val)
        data["value"] = val
        self._value_cache.clear()
        name = data.get("var_name", var_id or node.title)
        self._log(f"    SetVar {name} = {val}")
        self._emit_pin_watch(node.node_id, "value", val)
        if var_id:
            self._refresh_getvar_watches(var_id, val)
        self._advance_to(self._flow_target(node, "flow"), 50)

    def _sync_var_to_library(self, var_id: str, val: object) -> None:
        from app.widgets.node_editor.var_value import format_var_storage

        for v in getattr(self._graph, "variables", []) or []:
            if v.var_id == var_id:
                v.value = format_var_storage(val, v.var_type)

    def _sync_var_nodes(self, var_id: str, val: object) -> None:
        for node in self._node_idx.values():
            if node.node_type not in ("GetVar", "SetVar"):
                continue
            nd = node.data or {}
            if nd.get("var_id") == var_id:
                nd["value"] = val

    # ───────────────────────── wait / IO / register ─────────────────────────

    def _exec_wait(self, node: NodeData):
        ms = self._num(self._resolve_input_raw(node, "duration_ms"), 0)
        if ms < 0:
            self._fail_node(node, f"Wait duration_ms 不能为负数: {ms}")
            return
        ms = int(ms)
        self._log(f"    {tr('log_wait')} {ms} {tr('log_wait_ms')}")
        token = self._run_token
        QTimer.singleShot(ms, lambda t=token: self._wait_done(t, node))

    def _wait_done(self, token: int, node: NodeData):
        if token != self._run_token or not self._running:
            return
        next_id = self._flow_target(node, "flow")
        self._advance_to(next_id, 0)

    def _exec_io_register_online(self, node: NodeData):
        nt = node.node_type
        cmd = self._build_io_register_command(node)
        if cmd is None:
            self._fail_node(node, f"在线模式无法构建 {nt} 指令")
            return

        ty, db = cmd
        self._log(f"    📤 {ty} db={db}")
        token = self._run_token

        def _on_response(resp_db):
            if token != self._run_token or not self._running:
                return
            self._log(f"    ✅ {nt} 完成 response={resp_db}")
            next_id = self._flow_target(node, "flow")
            self._advance_to(next_id, 50)

        def _on_error(e):
            if token != self._run_token:
                return
            self._fail_node(node, f"{nt} 执行失败: {e}")

        self._send_command(ty, db, on_response=_on_response, on_error=_on_error)

    def _build_io_register_command(self, node: NodeData) -> tuple[str, Any] | None:
        nt = node.node_type
        data = node.data or {}

        if nt in ("SetDO", "SetAO"):
            io_type = "DO" if nt == "SetDO" else "AO"
            port = int(self._num(self._resolve_input_raw(node, "port"), data.get("port", 0)))
            value = self._resolve_input_raw(node, "value")
            if value == "?":
                value = data.get("value", 0)
            return "IOManager/SetIOValue", {"type": io_type, "port": port, "value": value}

        if nt in ("ReadDI", "ReadAI"):
            io_type = "DI" if nt == "ReadDI" else "AI"
            port = int(self._num(self._resolve_input_raw(node, "port"), data.get("port", 0)))
            return "IOManager/GetIOValue", [{"type": io_type, "port": port}]

        if nt == "SetRegister":
            address = int(self._num(self._resolve_input_raw(node, "address"), data.get("address", 0)))
            value = self._resolve_input_raw(node, "value")
            if value == "?":
                value = data.get("value", 0)
            return "RegisterManager/SetRegisterValue", {"address": address, "value": value}

        if nt == "ReadRegister":
            address = int(self._num(self._resolve_input_raw(node, "address"), data.get("address", 0)))
            return "RegisterManager/GetRegisterValue", [address]

        return None

    def _exec_array_set(self, node: NodeData):
        """ArraySet: 修改连接的 Array 节点中 index 位置的元素"""
        arr_src = self._data_sources.get((node.node_id, "array"))
        idx_val = self._resolve_input_raw(node, "index")
        val = self._resolve_input_raw(node, "value")

        if arr_src:
            arr_node = self._node_idx.get(arr_src[0])
            if arr_node and arr_node.node_type == "Array":
                data = arr_node.data or {}
                arr = list(data.get("value", []))
                if not isinstance(arr, list):
                    arr = []
                idx = int(self._num(idx_val, 0))
                if 0 <= idx < len(arr):
                    arr[idx] = val
                    arr_node.data["value"] = arr
                    # 清除缓存使得后续 ArrayGet 读到新值
                    if hasattr(self, '_value_cache'):
                        for port in ("", "result"):
                            self._value_cache.pop(self._eval_cache_key(arr_src[0], port), None)
                    self._log(f"    📝 Array[{idx}] = {val}")
                else:
                    self._log(f"    ⚠ ArraySet 索引 {idx} 越界 (长度 {len(arr)})")
            else:
                self._log(f"    ⚠ ArraySet 只能连接到 Array 常量节点")
        else:
            self._log(f"    ⚠ ArraySet 未连接 array 输入")

        self._advance_to(self._flow_target(node, "flow"), 50)

    # ───────────────────────── dry common ─────────────────────────

    def _execute_dry(self, node: NodeData):
        nt = node.node_type
        if nt == "Print":
            val = self._resolve_input_raw(node, "value")
            self._log(f"    {tr('log_print')} {val}")
        elif nt in ("SetDO", "SetAO"):
            port = self._resolve_input_raw(node, "port")
            value = self._resolve_input_raw(node, "value")
            self._log(f"    {tr('log_set_io')} {nt} port={port} val={value}")
        elif nt in ("ReadDI", "ReadAI"):
            port = self._resolve_input_raw(node, "port")
            self._log(f"    {tr('log_read_io')} {nt} port={port}")
        elif nt in ("SetRegister", "ReadRegister"):
            addr = self._resolve_input_raw(node, "address")
            val = self._resolve_input_raw(node, "value")
            self._log(f"    {nt} addr={addr} val={val}")
        elif nt in ("Add", "Sub", "Mul", "Div", "Pow", "Mod", "Square", "Sqrt", "Abs", "Neg",
                     "Sin", "Cos", "Tan", "Deg2Rad", "Rad2Deg", "Int2Float", "Float2Int",
                     "And", "Or", "Not", "Xor", "Gt", "Lt", "Eq", "Ge", "Le",
                     "StrConcat", "StrSplit", "StrFind", "StrReplace", "StrLen", "Num2Str", "Bool2Str",
                     "MatMulL", "MatMulR", "BreakPosition", "MakePosition"):
            val = self._eval_data(node.node_id)
            self._log(f"    {node.title} = {val}")
        elif nt in ("Int", "Float", "Bool", "String", "Array", "GetVar", "SetVar"):
            pass  # 被动数据节点，不打印
        else:
            self._log(f"    {nt}: log only in current phase")

    # ───────────────────────── graph maps ─────────────────────────

    def _build_maps(self):
        """构建节点索引和数据源映射。"""
        if not self._graph:
            return
        self._node_idx = {n.node_id: n for n in self._graph.nodes}
        self._data_sources.clear()

        for e in self._graph.edges:
            # 将非 flow 边登记为数据源
            src_node = self._node_idx.get(e.source_node_id)
            if not self._is_flow_output(src_node, e.source_port_name):
                self._data_sources[(e.target_node_id, e.target_port_name)] = (
                    e.source_node_id,
                    e.source_port_name,
                )

    def _is_flow_output(self, node: NodeData | None, port_name: str) -> bool:
        if not node:
            return False
        spec = NODE_SPECS.get(node.node_type)
        if spec:
            for p in spec.ports:
                if p.name == port_name and p.port_type == "flow" and p.direction == "output":
                    return True
        for pn, pt, pd in (node.data or {}).get("_ports", []):
            if pn == port_name and pt == "flow" and pd == "output":
                return True
        return False

    # ───────────────────────── data helpers ─────────────────────────

    def _position_for_input(self, node: NodeData, port_name: str) -> dict | None:
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return None
        src_node = self._node_idx.get(src[0])
        if not src_node or src_node.node_type != "Position":
            return None
        return src_node.data or {}

    def _valid_jp(self, pos: dict | None) -> list[float] | None:
        if not pos:
            return None
        jp = pos.get("jp")
        if not isinstance(jp, list) or len(jp) < 6:
            return None
        try:
            return [float(x) for x in jp[:6]]
        except (TypeError, ValueError):
            return None

    def _valid_cp(self, pos: dict | None) -> list[float] | None:
        if not pos:
            return None
        cp = pos.get("cp")
        if isinstance(cp, dict):
            keys = ("x", "y", "z", "a", "b", "c")
            try:
                return [float(cp[k]) for k in keys]
            except (KeyError, TypeError, ValueError):
                return None
        if isinstance(cp, list) and len(cp) >= 6:
            try:
                return [float(x) for x in cp[:6]]
            except (TypeError, ValueError):
                return None
        return None

    def _valid_ep(self, pos: dict | None) -> list:
        if not pos:
            return []
        ep = pos.get("ep", [])
        return ep if isinstance(ep, list) else []

    def _extract_motion_target(self, node: NodeData, db: list[dict]) -> dict | None:
        if not db:
            return None
        target = db[0].get("targetPoint", {})
        if "jp" in target:
            return {"kind": "jp", "value": target.get("jp")}
        if "cp" in target:
            return {"kind": "cp", "value": target.get("cp")}
        return None

    def _is_target_reached(self, state, target: dict | None) -> bool:
        """短运动兜底：当前位置是否已接近目标。

        初版使用保守阈值：关节 0.5deg，TCP 2mm / 1deg。
        """
        if not target or not state.is_valid():
            return False
        try:
            if target.get("kind") == "jp":
                current = state.current_joints_deg()
                target_jp = target.get("value") or []
                if len(current) < 6 or len(target_jp) < 6:
                    return False
                return max(abs(float(current[i]) - float(target_jp[i])) for i in range(6)) <= 0.5

            if target.get("kind") == "cp":
                current = state.current_tcp_pose_mm_deg()
                target_cp = target.get("value") or []
                if len(current) < 6 or len(target_cp) < 6:
                    return False
                pos_err = max(abs(float(current[i]) - float(target_cp[i])) for i in range(3))
                rot_err = max(abs(float(current[i]) - float(target_cp[i])) for i in range(3, 6))
                return pos_err <= 2.0 and rot_err <= 1.0
        except Exception:
            return False
        return False

    def _resolve_input_raw(self, node: NodeData, port_name: str):
        """递归解析输入端口的计算值。"""
        bind_key = (node.node_id, port_name)
        if bind_key in self._macro_param_bindings:
            return self._macro_param_bindings[bind_key]
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return (node.data or {}).get(port_name, "?")
        src_node_id, src_port_name = src
        return self._eval_data(src_node_id, src_port_name)

    def _eval_cache_key(self, node_id: str, output_port: str | None) -> tuple[str, str]:
        return (node_id, output_port or "")

    def _eval_data(self, node_id: str, output_port: str | None = None):
        """递归求值数据节点；output_port 指定多输出节点的出口。"""
        key = self._eval_cache_key(node_id, output_port)
        if key in self._value_cache:
            return self._value_cache[key]

        node = self._node_idx.get(node_id)
        if not node:
            return "?"
        if node.node_type == "MacroCall" and output_port:
            out_key = (node_id, output_port)
            if out_key in self._macro_call_outputs:
                return self._macro_call_outputs[out_key]
            return None
        nt = node.node_type
        data = node.data or {}

        def resolve(port_name, default="?"):
            src = self._data_sources.get((node_id, port_name))
            if src:
                return self._eval_data(src[0], src[1])
            return data.get(port_name, default)

        result = self._compute_node(nt, resolve, data, output_port)
        dyn = (data or {}).get("_ports")
        if is_pure_node_type(nt, dyn):
            self._value_cache[key] = result
            self._emit_pure_output_watches(node_id, nt, dyn, result, output_port)
        return result

    def _emit_pin_watch(self, node_id: str, port_name: str, value: object) -> None:
        self._pin_values[(node_id, port_name)] = value
        self.pin_value_emitted.emit(node_id, port_name, value)

    def _emit_pure_output_watches(
        self,
        node_id: str,
        node_type: str,
        dynamic_ports: list | None,
        result: object,
        requested_port: str | None,
    ) -> None:
        """纯节点：在输出引脚旁显示 Watch 值。"""
        if node_type == "BreakPosition":
            pose = result if isinstance(result, dict) else {}
            jp = pose.get("jp", [])
            cp = pose.get("cp", {})
            if requested_port == "jp":
                self._emit_pin_watch(node_id, "jp", jp)
            elif requested_port == "cp":
                self._emit_pin_watch(node_id, "cp", cp)
            else:
                self._emit_pin_watch(node_id, "jp", jp)
                self._emit_pin_watch(node_id, "cp", cp)
            return
        outputs: list[str] = []
        if dynamic_ports:
            outputs = [p[0] for p in dynamic_ports if len(p) >= 3 and p[1] != "flow" and p[2] == "output"]
        else:
            spec = NODE_SPECS.get(node_type)
            if spec:
                outputs = [p.name for p in spec.ports if p.port_type != "flow" and p.direction == "output"]
        if not outputs:
            return
        port = requested_port if requested_port in outputs else outputs[0]
        self._emit_pin_watch(node_id, port, result)

    def _watch_io_register_outputs(self, node: NodeData) -> None:
        """Impure IO/寄存器节点：在数据引脚旁显示最近一次读/写值。"""
        nt = node.node_type
        if nt in ("ReadDI", "ReadAI"):
            self._watch_input_ports(node, ("port",))
            self._emit_pin_watch(node.node_id, "value", 0)
        elif nt == "ReadRegister":
            self._watch_input_ports(node, ("address",))
            self._emit_pin_watch(node.node_id, "value", 0)
        elif nt in ("SetDO", "SetAO", "SetRegister"):
            self._watch_input_ports(node, ("port", "value") if nt != "SetRegister" else ("address", "value"))
            self._emit_pin_watch(node.node_id, "value", self._resolve_input_raw(node, "value"))

    def _watch_input_ports(self, node: NodeData, port_names: tuple[str, ...]) -> None:
        for port_name in port_names:
            self._emit_pin_watch(node.node_id, port_name, self._resolve_input_raw(node, port_name))

    def _pose_port_label(self, node: NodeData, port_name: str) -> str:
        """运动节点 pose 输入所连点位/组合节点的显示名。"""
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return "?"
        src_id, src_port = src
        src_node = self._node_idx.get(src_id)
        if not src_node:
            return "?"
        if src_node.node_type == "Position":
            data = src_node.data or {}
            return (data.get("name") or "").strip() or src_node.title or "Position"
        if src_node.node_type in ("MakePosition", "BreakPosition"):
            val = self._eval_data(src_id, src_port)
            if isinstance(val, dict):
                return (val.get("name") or "").strip() or src_port
        return src_node.title or src_node.node_type

    def _watch_motion_inputs(self, node: NodeData) -> None:
        nt = node.node_type
        if nt == "MovePath":
            for port_name in ("pose_1", "pose_2", "pose_3"):
                if self._data_sources.get((node.node_id, port_name)):
                    self._emit_pin_watch(node.node_id, port_name, self._pose_port_label(node, port_name))
            return
        if self._data_sources.get((node.node_id, "target")):
            self._emit_pin_watch(node.node_id, "target", self._pose_port_label(node, "target"))
        if nt in ("MoveC", "MoveCircle") and self._data_sources.get((node.node_id, "middle")):
            self._emit_pin_watch(node.node_id, "middle", self._pose_port_label(node, "middle"))

    def _refresh_getvar_watches(self, var_id: str, val: object) -> None:
        """SetVar 后同步所有同源 GetVar 引脚的 Watch。"""
        for node in self._node_idx.values():
            if node.node_type != "GetVar":
                continue
            data = node.data or {}
            if data.get("var_id") == var_id:
                self._emit_pin_watch(node.node_id, "value", val)

    def _compute_node(self, nt: str, resolve, data: dict, output_port: str | None = None):
        """根据节点类型计算结果值"""
        if nt == "GetVar":
            var_id = data.get("var_id", "")
            if var_id and var_id in self._runtime_vars:
                return self._runtime_vars[var_id]
            return data.get("value", 0)
        if nt == "Int":
            return int(self._num(data.get("value", 0)))
        if nt == "Float":
            return data.get("value", 0.0)
        if nt == "Bool":
            return data.get("value", False)
        if nt == "String":
            return data.get("value", "")
        if nt == "For":
            return data.get("_for_index", 0)
        if nt == "Position":
            return data
        if nt == "Array":
            return data.get("value", [])

        # math binary
        if nt in ("Add", "Sub", "Mul", "Div", "Pow", "Mod"):
            a = self._num(resolve("a"))
            b = self._num(resolve("b"))
            if nt == "Add": return a + b
            if nt == "Sub": return a - b
            if nt == "Mul": return a * b
            if nt == "Div": return a / b if b != 0 else float('inf')
            if nt == "Pow": return a ** b
            if nt == "Mod": return a % b
        # math unary
        if nt == "Square": return self._num(resolve("a")) ** 2
        if nt == "Sqrt": return _math.sqrt(max(0, self._num(resolve("a"))))
        if nt == "Abs": return abs(self._num(resolve("a")))
        if nt == "Neg": return -self._num(resolve("a"))
        if nt == "Sin": return _math.sin(_math.radians(self._num(resolve("a"))))
        if nt == "Cos": return _math.cos(_math.radians(self._num(resolve("a"))))
        if nt == "Tan": return _math.tan(_math.radians(self._num(resolve("a"))))
        if nt == "Deg2Rad": return _math.radians(self._num(resolve("a")))
        if nt == "Rad2Deg": return _math.degrees(self._num(resolve("a")))
        if nt == "Int2Float": return float(self._num(resolve("a")))
        if nt == "Float2Int": return int(self._num(resolve("a")))
        if nt == "Cast":
            from app.widgets.node_editor.port_types import apply_cast
            return apply_cast(resolve("value"), data.get("cast_to", "float"))
        if nt == "Reroute":
            return resolve("in")
        if nt == "EnumInt":
            opts = data.get("options") or [0, 1]
            idx = int(data.get("selected", 0))
            if 0 <= idx < len(opts):
                return opts[idx]
            return opts[0] if opts else 0
        # logic
        if nt == "And": return bool(resolve("a")) and bool(resolve("b"))
        if nt == "Or": return bool(resolve("a")) or bool(resolve("b"))
        if nt == "Not": return not bool(resolve("a"))
        if nt == "Xor": return bool(resolve("a")) ^ bool(resolve("b"))
        # comparison
        if nt == "Gt": return self._num(resolve("a")) > self._num(resolve("b"))
        if nt == "Lt": return self._num(resolve("a")) < self._num(resolve("b"))
        if nt == "Ge": return self._num(resolve("a")) >= self._num(resolve("b"))
        if nt == "Le": return self._num(resolve("a")) <= self._num(resolve("b"))
        if nt == "Eq":
            a = resolve("a"); b = resolve("b")
            try: return float(a) == float(b)
            except: return str(a) == str(b)
        if nt == "Compare":
            a = resolve("a")
            b = resolve("b")
            try:
                return float(a) == float(b)
            except (TypeError, ValueError):
                return a == b
        # string
        if nt == "StrConcat": return str(resolve("a", "")) + str(resolve("b", ""))
        if nt == "StrSplit": return str(resolve("str", "")).split(str(resolve("sep", ",")))
        if nt == "StrFind": return str(resolve("str", "")).find(str(resolve("sub", "")))
        if nt == "StrReplace": return str(resolve("str", "")).replace(str(resolve("old", "")), str(resolve("new", "")))
        if nt == "StrLen": return len(str(resolve("str", "")))
        if nt == "Num2Str": return str(self._num(resolve("a")))
        if nt == "Bool2Str": return str(bool(resolve("a")))
        # pose
        if nt == "BreakPosition":
            pos_data = resolve("pose")
            if not isinstance(pos_data, dict):
                pos_data = {}
            jp = pos_data.get("jp", [])
            cp = pos_data.get("cp", {})
            jp_list = [float(x) for x in jp[:6]] if isinstance(jp, list) and len(jp) >= 6 else (
                list(jp) if isinstance(jp, list) else []
            )
            cp_dict = dict(cp) if isinstance(cp, dict) else {}
            if output_port == "jp":
                return jp_list
            if output_port == "cp":
                return cp_dict
            return {"jp": jp_list, "cp": cp_dict, "name": pos_data.get("name", "")}
        if nt == "MakePosition":
            jp_in = resolve("jp")
            cp_in = resolve("cp")
            if isinstance(jp_in, dict) and "jp" in jp_in:
                jp_list = jp_in.get("jp", [])
            elif isinstance(jp_in, list):
                jp_list = jp_in
            else:
                jp_list = []
            if isinstance(cp_in, dict) and "cp" in cp_in and isinstance(cp_in.get("cp"), dict):
                cp_dict = dict(cp_in["cp"])
            elif isinstance(cp_in, dict) and "x" in cp_in:
                cp_dict = dict(cp_in)
            else:
                cp_dict = {}
            try:
                jp_out = [float(x) for x in jp_list[:6]]
            except (TypeError, ValueError):
                jp_out = []
            return {
                "name": data.get("name", ""),
                "jp": jp_out,
                "cp": cp_dict,
                "ep": data.get("ep", []),
                "optional": dict(data.get("optional") or {}),
            }
        if nt == "ArrayGet":
            arr = resolve("array")
            idx = int(self._num(resolve("index")))
            if isinstance(arr, str):
                arr = [x.strip() for x in arr.replace("[","").replace("]","").split(",") if x.strip()]
            if isinstance(arr, list) and 0 <= idx < len(arr):
                try: return float(arr[idx])
                except: return arr[idx]
            return "?"
        if nt == "ArrayLen":
            arr = resolve("array")
            if isinstance(arr, str):
                arr = [x.strip() for x in arr.replace("[","").replace("]","").split(",") if x.strip()]
            return len(arr) if isinstance(arr, list) else 0
        return "?"

    # ───────────────────────── command / failure helpers ─────────────────────────

    def _send_command(self, ty: str, db: Any, on_response=None, on_error=None):
        if not self._send_cb:
            if on_error:
                on_error("TCP send callback 未设置")
            return

        try:
            # 新回调签名：cb(ty, db, on_response=None, on_error=None)
            self._send_cb(ty, db, on_response=on_response, on_error=on_error)
        except TypeError:
            # 兼容旧回调签名：cb(ty, db)。旧签名无法得知真实 response，
            # 因此只在发送不抛异常时模拟 response，避免 UI 卡死。
            try:
                self._send_cb(ty, db)
                if on_response:
                    QTimer.singleShot(0, lambda: on_response(None))
            except Exception as e:
                if on_error:
                    on_error(e)
        except Exception as e:
            if on_error:
                on_error(e)

    def _fail_node(self, node: NodeData | None, message: str):
        node_desc = f"{node.title}({node.node_id})" if node else "<unknown>"
        self._fail_graph(f"Node failed: {node_desc}: {message}")

    def _fail_graph(self, message: str):
        self._running = False
        self._stopping = False
        self._run_token += 1
        self._stop_poll_timer()
        self._log(f"{tr('log_error')} {message}")
        self._clear_highlight()
        self.graph_stopped.emit()

    def _finish_graph(self):
        self._running = False
        self._stopping = False
        self._stop_poll_timer()
        self._clear_highlight()
        self._log(tr("log_finished"))
        self.graph_finished.emit()

    def _stop_poll_timer(self):
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

    def _clear_highlight(self):
        if self._active_node_id:
            self.node_highlight.emit(self._active_node_id, False)
            self._active_node_id = None

    def _log(self, msg: str):
        self.log_emitted.emit(msg)

    @staticmethod
    def _now_ms() -> float:
        return time.monotonic() * 1000.0

    def _init_runtime_vars(self) -> dict[str, object]:
        out: dict[str, object] = {}
        if not self._graph:
            return out
        for v in getattr(self._graph, "variables", []) or []:
            if v.var_id:
                out[v.var_id] = self._coerce_var_value(v)
        return out

    @staticmethod
    def _coerce_var_value(var_def) -> object:
        from app.widgets.node_editor.var_value import parse_var_storage

        t = getattr(var_def, "var_type", "int")
        raw = getattr(var_def, "value", "0")
        return parse_var_storage(raw, t)

    @staticmethod
    def _num(value, default=0.0) -> float:
        try:
            if value in (None, "", "?"):
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _op_symbol(self, nt: str) -> str:
        syms = {
            "Add": "+", "Sub": "-", "Mul": "x", "Div": "/",
            "Pow": "^", "Mod": "%", "Gt": ">", "Lt": "<",
            "Eq": "==", "Ge": ">=", "Le": "<=",
        }
        return syms.get(nt, nt)
