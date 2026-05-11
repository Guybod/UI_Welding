import time
from typing import Any, Callable

import math as _math

from PySide6.QtCore import QObject, Signal, QTimer

from app.widgets.node_editor.models import GraphData, NodeData, NODE_SPECS


class ExecutionEngine(QObject):
    """节点图执行引擎。

    设计原则：
    - DryRun 只模拟执行，不发送 TCP。
    - Online 只允许已明确实现的节点真实发送 TCP。
    - 运动节点发送 Robot/move 后，不能用 TCP response 判断完成，必须等待 CRI moving。
    - 禁止 time.sleep / 阻塞 while，全部用 QTimer 状态机推进。
    - 执行模型：图遍历（非预计算线性路径）。每个节点执行后根据 flow 输出边决定下一节点。
      控制流节点 (If/For/While) 在运行时动态选择分支。
    """

    node_highlight = Signal(str, bool)
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
        self._return_stack: list[tuple[str, float, float, float]] = []  # (for_node_id, current_i, end, step)

    # ───────────────────────── public ─────────────────────────

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

        self._log("[执行] 已停止")
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

        mode = "[在线]" if online else "[DryRun]"
        self.graph_started.emit()
        self._log(f"{mode} 开始执行")

        if not self._current_node_id:
            self._fail_graph("未找到 Start 节点")
            return

        QTimer.singleShot(0, self._step)

    def _step(self):
        if not self._running:
            return

        # If no current node, check return stack (loop body completed)
        if not self._current_node_id:
            if self._return_stack:
                ret = self._return_stack.pop()
                for_node_id, i, end, step = ret
                self._current_node_id = for_node_id
                QTimer.singleShot(50, lambda: self._step())
                return
            self._finish_graph()
            return

        node_id = self._current_node_id
        node = self._node_idx.get(node_id)
        if not node:
            self._fail_graph(f"执行路径中的节点不存在: {node_id}")
            return

        self._clear_highlight()
        self._active_node_id = node_id
        self.node_highlight.emit(node_id, True)
        self._active_node = node

        nt = node.node_type
        self._log(f"  ▶ {node.title} ({nt})")

        if nt == "End":
            self._log("  ⏹ 到达 End")
            self._finish_graph()
            return

        if nt in ("Start", "Position"):
            self._execute_passive(node)
            return

        if nt == "Wait":
            self._exec_wait(node)
            return

        if nt in ("MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"):
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
                self._advance_to(self._flow_target(node, "flow"), 150)
            return

        if nt in ("If", "For", "While"):
            self._exec_control_flow(node)
            return

        # Data nodes and other passive nodes on flow path
        if nt in ("Int", "Float", "Bool", "String", "Array", "GetVar", "SetVar",
                  "Add", "Sub", "Mul", "Div", "Pow", "Mod", "Square", "Sqrt", "Abs", "Neg",
                  "Sin", "Cos", "Tan", "Deg2Rad", "Rad2Deg", "Int2Float", "Float2Int",
                  "And", "Or", "Not", "Xor", "Gt", "Lt", "Eq", "Ge", "Le",
                  "StrConcat", "StrSplit", "StrFind", "StrReplace", "StrLen", "Num2Str", "Bool2Str",
                  "MatMulL", "MatMulR", "BreakPosition", "MakePosition",
                  "ArrayGet", "ArrayLen", "Print"):
            self._execute_dry(node)
            self._advance_to(self._flow_target(node, "flow"), 100 if self._online else 150)
            return

        # Unknown node types: log and advance
        self._execute_dry(node)
        self._advance_to(self._flow_target(node, "flow"), 100 if self._online else 150)

    def _execute_passive(self, node: NodeData):
        if node.node_type == "Position":
            self._log(f"    点位: {node.data.get('name', node.title)}")
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

    def _flow_target(self, node: NodeData, port_name: str) -> str | None:
        """找到某 flow 输出端口连接的目标节点"""
        for e in self._graph.edges:
            if e.source_node_id == node.node_id and e.source_port_name == port_name:
                return e.target_node_id
        return None

    # ───────────────────────── online motion ─────────────────────────

    def _exec_motion_online(self, node: NodeData):
        if node.node_type == "MovePath":
            self._fail_node(node, "MovePath 在线执行暂未开放，请先使用 MoveJ/MoveL 或 DryRun")
            return

        db = self._build_move_db(node)
        if db is None:
            self._fail_node(node, f"{node.node_type}: 无法构建合法运动指令")
            return

        self._log(f"    📤 发送运动指令")
        token = self._run_token

        def _on_response(_db):
            if token != self._run_token or not self._running:
                return
            self._begin_motion_wait(node, db)

        def _on_error(e):
            if token != self._run_token:
                return
            self._fail_node(node, f"Robot/move 发送失败: {e}")

        self._send_command("Robot/move", db, on_response=_on_response, on_error=_on_error)

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
        self._log("    ⏳ 等待 CRI moving: false → true")

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
                self._log("    🏃 CRI moving=true，运动已开始")
                return

            if elapsed >= self.MOTION_TIMEOUT_START:
                if self._is_target_reached(state, self._active_target):
                    self._log("    ✅ 未检测到 moving=true，但当前位置已接近目标，按短运动完成处理")
                    self._finish_motion_success()
                else:
                    self._fail_node(self._active_node, "运动启动超时，且当前位置未接近目标")
                return

        else:
            if not moving:
                self._log(f"    ✅ CRI moving=false，运动完成 ({elapsed:.0f}ms)")
                self._finish_motion_success()
                return

            if elapsed >= self.MOTION_TIMEOUT_FINISH:
                self._fail_node(self._active_node, "运动完成超时")
                return

    def _finish_motion_success(self):
        node = self._active_node
        self._stop_poll_timer()
        self._active_target = None
        self._motion_started = False
        self._motion_phase = "idle"
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
            self._log("    🧪 MovePath DryRun：当前版本仅占位，在线执行未开放")
            self._advance_to(self._flow_target(node, "flow"), 150)
            return

        db = self._build_move_db(node)
        if db is None:
            self._log(f"    ⚠ {node.node_type}: 无法构建合法运动指令")
        else:
            self._log(f"    🧪 {node.node_type} 将发送 Robot/move db={db}")
        self._advance_to(self._flow_target(node, "flow"), 150)

    # ───────────────────────── control flow: If / For / While ─────────────────────────

    def _exec_control_flow(self, node: NodeData):
        nt = node.node_type
        if nt == "If":
            cond = bool(self._resolve_input_raw(node, "condition"))
            self._log(f"    ? 条件: {'True' if cond else 'False'}")
            branch = "true" if cond else "false"
            target = self._flow_target(node, branch)
            if target:
                self._advance_to(target, 50)
            else:
                self._fail_node(node, f"If 分支 '{branch}' 未连接")
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
                # 清除 For 节点的缓存值，使每次迭代重新读取 _for_index
                if hasattr(self, '_value_cache'):
                    self._value_cache.pop(node.node_id, None)
                self._loop_counters[loop_key] = i + step
                self._return_stack.append((node.node_id, i + step, end, step))
                target = self._flow_target(node, "body")
                if target:
                    self._advance_to(target, 50)
                    return
            else:
                self._log(f"    ✅ For 完成")
                if loop_key in getattr(self, '_loop_counters', {}):
                    del self._loop_counters[loop_key]
                target = self._flow_target(node, "done")
                if target:
                    self._advance_to(target, 50)
                    return
            self._advance_to(None, 50)
        elif nt == "While":
            cond = bool(self._resolve_input_raw(node, "condition"))
            if cond:
                self._log(f"    🔁 While 条件为 True, 执行循环体")
                target = self._flow_target(node, "body")
                if target:
                    self._advance_to(target, 50)
                    return
            else:
                self._log(f"    ✅ While 条件为 False, 退出")
                target = self._flow_target(node, "done")
                if target:
                    self._advance_to(target, 50)
                    return
            self._advance_to(None, 50)

    # ───────────────────────── wait / IO / register ─────────────────────────

    def _exec_wait(self, node: NodeData):
        ms = self._num(self._resolve_input_raw(node, "duration_ms"), 0)
        if ms < 0:
            self._fail_node(node, f"Wait duration_ms 不能为负数: {ms}")
            return
        ms = int(ms)
        self._log(f"    ⏱ 等待 {ms} ms")
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
                        self._value_cache.pop(arr_src[0], None)
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
            self._log(f"    🖨 打印: {val}")
        elif nt in ("SetDO", "SetAO"):
            port = self._resolve_input_raw(node, "port")
            value = self._resolve_input_raw(node, "value")
            self._log(f"    设置 {nt} port={port} val={value}")
        elif nt in ("ReadDI", "ReadAI"):
            port = self._resolve_input_raw(node, "port")
            self._log(f"    读取 {nt} port={port}")
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
            self._log(f"    {nt}: 当前阶段仅记录日志")

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
        src = self._data_sources.get((node.node_id, port_name))
        if not src:
            return (node.data or {}).get(port_name, "?")
        src_node_id, _src_port_name = src
        return self._eval_data(src_node_id)

    def _eval_data(self, node_id: str):
        """递归求值数据节点, 返回其 output 值。缓存避免重复计算。"""
        if not hasattr(self, '_value_cache'):
            self._value_cache: dict[str, object] = {}
        if node_id in self._value_cache:
            return self._value_cache[node_id]

        node = self._node_idx.get(node_id)
        if not node:
            return "?"
        nt = node.node_type
        data = node.data or {}

        def resolve(port_name, default="?"):
            src = self._data_sources.get((node_id, port_name))
            if src:
                return self._eval_data(src[0])
            return data.get(port_name, default)

        result = self._compute_node(nt, resolve, data)
        # 不要缓存依赖可变数据源的节点（ArrayGet/ArrayLen 依赖 Array，可能被 ArraySet 修改）
        if nt not in ("ArrayGet", "ArrayLen"):
            self._value_cache[node_id] = result
        return result

    def _compute_node(self, nt: str, resolve, data: dict):
        """根据节点类型计算结果值"""
        if nt == "GetVar":
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
            pos_src = self._data_sources.get((node.node_id, "pose"))
            pos_data = (self._eval_data(pos_src[0]) if pos_src else data) or {}
            return pos_data  # caller extracts specific fields
        if nt == "MakePosition":
            return data
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
        self._fail_graph(f"节点失败: {node_desc}: {message}")

    def _fail_graph(self, message: str):
        self._running = False
        self._stopping = False
        self._run_token += 1
        self._stop_poll_timer()
        self._log(f"[错误] {message}")
        self._clear_highlight()
        self.graph_stopped.emit()

    def _finish_graph(self):
        self._running = False
        self._stopping = False
        self._stop_poll_timer()
        self._clear_highlight()
        self._log("[执行] 完成")
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
