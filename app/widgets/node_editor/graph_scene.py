import uuid

from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QKeyEvent
from PySide6.QtCore import QRectF, QPointF, Qt

from app.widgets.node_editor.node_item import NodeItem
from app.widgets.node_editor.port_item import PortItem
from app.widgets.node_editor.edge_item import EdgeItem
from app.widgets.node_editor.models import GraphData, NodeData, EdgeData
from app.widgets.node_editor.node_display_title import AUTO_TITLE_NODE_TYPES


class GraphScene(QGraphicsScene):
    """节点编辑器场景 — 深色背景 + 网格 + 连线管理"""

    BG_COLOR = QColor(30, 30, 32)
    GRID_COLOR = QColor(50, 50, 55, 120)
    GRID_SIZE = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(self.BG_COLOR))
        self.setSceneRect(QRectF(-5000, -5000, 10000, 10000))
        self._temp_edge: EdgeItem | None = None
        self._drag_source: PortItem | None = None
        self._library = None  # set by NodeEditorWidget

    # ── node management ──

    def add_node(self, node_type: str, x: float = 0, y: float = 0, override_spec: list = None) -> NodeItem:
        node = NodeItem(node_type, override_spec=override_spec)
        node.setPos(x, y)
        self.addItem(node)

        # Position 节点创建时自动填入当前位置
        if node_type == "Position":
            self._init_position_data(node)

        # 常量节点默认值
        _CONSTANT_DEFAULTS = {"Int": 0, "Float": 0.0, "Bool": False, "String": "", "Array": []}
        if node_type in _CONSTANT_DEFAULTS:
            node.set_node_data({"value": _CONSTANT_DEFAULTS[node_type], "_auto_title": True})
        if node_type == "EnumInt":
            node.set_node_data({
                "options": [0, 1],
                "labels": ["0", "1"],
                "selected": 0,
                "_auto_title": True,
            })
        if node_type == "Cast":
            node.set_node_data({"cast_to": "float", "_auto_title": True})
        if node_type == "Comment":
            node.set_node_data({"text": ""})

        return node

    def add_var_node(self, var_id: str, var_name: str, var_type: str, port_type: str, mode: str, x: float = 0, y: float = 0) -> NodeItem:
        """创建 GetVar 或 SetVar 节点，绑定到 var_id"""
        from app.widgets.node_editor.models import PortSpec, NodeSpec
        if mode == "get":
            ports = [PortSpec("value", port_type, "output")]
            spec = NodeSpec("GetVar", f"Get {var_name}", "变量", ports, color="#00BCD4")
        else:
            ports = [
                PortSpec("flow", "flow", "input"),
                PortSpec("flow", "flow", "output"),
                PortSpec("value", port_type, "input"),
            ]
            spec = NodeSpec("SetVar", f"Set {var_name}", "变量", ports, color="#00BCD4")
        node = NodeItem("GetVar" if mode == "get" else "SetVar", override_spec=spec)
        from app.widgets.node_editor.var_value import parse_var_storage

        init_val = parse_var_storage(0, var_type)
        if self._library:
            for v in self._library.variables():
                if v.var_id == var_id:
                    init_val = parse_var_storage(v.value, var_type)
                    break
        node.set_node_data({
            "_ports": [(p.name, p.port_type, p.direction) for p in ports],
            "var_id": var_id,
            "var_name": var_name,
            "var_type": var_type,
            "value": init_val,
            "_auto_title": True,
        })
        node.setPos(x, y)
        self.addItem(node)
        node.refresh_display_title()
        return node

    def add_macro_call(self, macro_id: str, macro_name: str, x: float = 0, y: float = 0) -> NodeItem:
        from app.widgets.node_editor.macro_storage import MacroDef
        from app.widgets.node_editor.models import GraphData
        from app.widgets.node_editor.macro_ports import macro_call_node_spec, macro_call_ports_snapshot

        macro = None
        if self._library:
            macro = self._library.get_macro(macro_id)
        if macro is None:
            macro = MacroDef(macro_id=macro_id, name=macro_name, graph=GraphData())
        spec = macro_call_node_spec(macro)
        node = NodeItem("MacroCall", override_spec=spec)
        node.setPos(x, y)
        self.addItem(node)
        node.set_node_data({
            "macro_id": macro_id,
            "macro_name": macro_name,
            "_ports": macro_call_ports_snapshot(macro),
            "_param_in": len([p for p in macro.params or [] if p.direction == "in"]),
            "_param_out": len([p for p in macro.params or [] if p.direction == "out"]),
            "_auto_title": True,
        })
        node.refresh_display_title()
        return node

    def rebuild_macro_call(self, node: NodeItem, macro_id: str | None = None) -> NodeItem:
        """宏定义变更后重建 MacroCall 引脚，尽量保留同名端口连线。"""
        from app.widgets.node_editor.macro_ports import macro_call_node_spec, macro_call_ports_snapshot
        from app.widgets.node_editor.node_item import NodeItem

        data = dict(node.node_data())
        mid = macro_id or data.get("macro_id", "")
        macro = self._library.get_macro(mid) if self._library else None
        if not macro:
            return node
        edge_records: list[tuple[str, str, str, str]] = []
        for port in node.ports():
            for edge in list(port.connected_edges):
                other = edge.target() if edge.source() is port else edge.source()
                if not other:
                    continue
                other_node = other.parentItem()
                if other_node is node or not hasattr(other_node, "data"):
                    continue
                oid = other_node.data(0)
                if not oid:
                    continue
                edge_records.append((
                    port.port_name(),
                    port.direction(),
                    oid,
                    other.port_name(),
                ))
        pos = node.pos()
        nid = node.data(0)
        selected = node.isSelected()
        self.remove_node(node)
        spec = macro_call_node_spec(macro)
        new_node = NodeItem("MacroCall", override_spec=spec)
        new_node.setPos(pos)
        self.addItem(new_node)
        if nid:
            new_node.setData(0, nid)
        data["macro_id"] = macro.macro_id
        data["macro_name"] = macro.name
        data["_ports"] = macro_call_ports_snapshot(macro)
        data["_param_in"] = len([p for p in macro.params or [] if p.direction == "in"])
        data["_param_out"] = len([p for p in macro.params or [] if p.direction == "out"])
        new_node.set_node_data(data)
        new_node.refresh_display_title()
        new_node.setSelected(selected)
        node_by_id = {
            item.data(0): item
            for item in self.items()
            if isinstance(item, NodeItem) and item.data(0)
        }
        port_by_name = {p.port_name(): p for p in new_node.ports()}
        for pname, direction, oid, other_pname in edge_records:
            macro_port = port_by_name.get(pname)
            other_node = node_by_id.get(oid)
            if not macro_port or not other_node:
                continue
            other_port = self._find_port(other_node, other_pname, "output" if direction == "input" else "input")
            if not other_port:
                continue
            if direction == "input":
                self._add_edge(other_port, macro_port)
            else:
                self._add_edge(macro_port, other_port)
        return new_node

    def selected_node_ids(self) -> set[str]:
        from app.widgets.node_editor.node_item import NodeItem

        out: set[str] = set()
        for item in self.selectedItems():
            if isinstance(item, NodeItem):
                nid = item.data(0)
                if nid:
                    out.add(nid)
        return out

    def _init_position_data(self, node: NodeItem):
        from services.robot_realtime_state import RobotRealtimeState
        state = RobotRealtimeState.instance()
        if not state.is_valid():
            return
        joints = state.current_joints_deg()
        x, y, z, a, b, c = state.current_tcp_pose_mm_deg()
        data = {
            "name": "",
            "jp": [round(v, 2) for v in joints],
            "cp": {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                   "a": round(a, 2), "b": round(b, 2), "c": round(c, 2)},
            "ep": [],
            "optional": {"speed": 200, "acc": 500, "blend": 0, "relativeBlend": 0},
        }
        node.set_node_data(data)

    def remove_node(self, node: NodeItem):
        for port in node.ports():
            for edge in list(port.connected_edges):
                self._remove_edge(edge)
        self.removeItem(node)

    def clear_all(self):
        for item in list(self.items()):
            if isinstance(item, EdgeItem):
                item.detach()
                self.removeItem(item)
        for item in list(self.items()):
            if isinstance(item, NodeItem):
                self.removeItem(item)

    # ── serialize / deserialize ──

    def to_graph_data(self) -> GraphData:
        """收集 Scene 中的所有节点和连线为纯数据模型"""
        nodes = []
        edges = []
        edge_id_counter = 0

        node_items: dict[str, NodeItem] = {}
        for item in self.items():
            if isinstance(item, NodeItem):
                nid = item.data(0) or str(uuid.uuid4())[:8]
                item.setData(0, nid)
                node_items[nid] = item
                nodes.append(NodeData(
                    node_id=nid,
                    node_type=item.node_type(),
                    title=item._title,
                    x=item.pos().x(),
                    y=item.pos().y(),
                    data=item.node_data(),
                ))

        seen = set()
        for item in self.items():
            if isinstance(item, EdgeItem):
                src = item.source()
                tgt = item.target()
                if not src or not tgt:
                    continue
                src_node = src.parentItem()
                tgt_node = tgt.parentItem()
                if not isinstance(src_node, NodeItem) or not isinstance(tgt_node, NodeItem):
                    continue
                key = (src_node.data(0), src.port_name(),
                       tgt_node.data(0), tgt.port_name())
                if key in seen:
                    continue
                seen.add(key)
                edge_id_counter += 1
                edges.append(EdgeData(
                    edge_id=f"e{edge_id_counter}",
                    source_node_id=src_node.data(0),
                    source_port_name=src.port_name(),
                    target_node_id=tgt_node.data(0),
                    target_port_name=tgt.port_name(),
                ))
        return GraphData(nodes=nodes, edges=edges)

    def load_from_graph_data(self, data: GraphData):
        """用 GraphData 重建所有节点和连线"""
        self.clear_all()
        node_map: dict[str, NodeItem] = {}
        for nd in data.nodes:
            node = None
            # rebuild dynamic nodes (GetVar/SetVar) with correct ports
            if nd.node_type in ("GetVar", "SetVar") and nd.data.get("_ports"):
                from app.widgets.node_editor.models import PortSpec, NodeSpec, VAR_PORT_TYPE
                from app.widgets.node_editor.port_types import migrate_ports_list

                vtype = nd.data.get("var_type", "int")
                raw_ports = migrate_ports_list(list(nd.data["_ports"]), vtype)
                ports = [PortSpec(p[0], p[1], p[2]) for p in raw_ports]
                nd.data["_ports"] = raw_ports
                if nd.node_type == "GetVar":
                    ptype = VAR_PORT_TYPE.get(vtype, "any")
                    for i, ps in enumerate(ports):
                        if ps.name == "value" and ps.direction == "output":
                            ports[i] = PortSpec("value", ptype, "output")
                spec = NodeSpec(nd.node_type, nd.title, "变量", ports, color="#00BCD4")
                node = self.add_node(nd.node_type, nd.x, nd.y, override_spec=spec)
            elif nd.node_type == "MacroCall":
                from app.widgets.node_editor.macro_ports import macro_call_node_spec, macro_call_ports_snapshot
                from app.widgets.node_editor.macro_storage import MacroDef
                from app.widgets.node_editor.models import GraphData

                macro = None
                if self._library:
                    macro = self._library.get_macro((nd.data or {}).get("macro_id", ""))
                if macro is None:
                    macro = MacroDef(
                        macro_id=(nd.data or {}).get("macro_id", ""),
                        name=(nd.data or {}).get("macro_name", nd.title),
                        graph=GraphData(),
                    )
                raw_ports = (nd.data or {}).get("_ports") or macro_call_ports_snapshot(macro)
                ports = [PortSpec(p[0], p[1], p[2]) for p in raw_ports]
                spec = macro_call_node_spec(macro, nd.title)
                node = self.add_node(nd.node_type, nd.x, nd.y, override_spec=spec)
                nd.data = dict(nd.data or {})
                nd.data["_ports"] = raw_ports
            else:
                node = self.add_node(nd.node_type, nd.x, nd.y)
            node.setData(0, nd.node_id)
            data = dict(nd.data or {})
            if data.get("_auto_title") is False and nd.title:
                data["_auto_title"] = False
            else:
                data.setdefault("_auto_title", True)
            node.set_node_data(data)
            if data.get("_auto_title") is False and nd.title:
                node._title = nd.title
                node.update()
            node_map[nd.node_id] = node

        for ed in data.edges:
            src_node = node_map.get(ed.source_node_id)
            tgt_node = node_map.get(ed.target_node_id)
            if not src_node or not tgt_node:
                continue
            src_port = self._find_port(src_node, ed.source_port_name, "output")
            tgt_port = self._find_port(tgt_node, ed.target_port_name, "input")
            if src_port and tgt_port:
                self._add_edge(src_port, tgt_port)

        self.refresh_display_titles()

    def _find_port(self, node: NodeItem, name: str, direction: str) -> PortItem | None:
        for p in node.ports():
            if p.port_name() == name and p.direction() == direction:
                return p
        return None

    # ── edge management ──

    def _add_edge(self, src: PortItem, tgt: PortItem):
        # validate: output → input, compatible types
        if src.direction() != "output" or tgt.direction() != "input":
            return
        from app.widgets.node_editor.port_types import ports_compatible

        if not ports_compatible(src.port_type(), tgt.port_type()):
            return
        # auto-disconnect old connection on same target port
        for old_edge in list(tgt.connected_edges):
            self._remove_edge(old_edge)
        # flow output can't fork, auto-disconnect if already connected
        if src.port_type() == "flow":
            for old_edge in list(src.connected_edges):
                self._remove_edge(old_edge)

        edge = EdgeItem(src, tgt)
        src.add_edge(edge)
        tgt.add_edge(edge)
        self.addItem(edge)
        edge.update_path()
        self._refresh_titles_for_ports(src, tgt)

    def _remove_edge(self, edge: EdgeItem):
        src = edge.source()
        tgt = edge.target()
        edge.detach()
        self.removeItem(edge)
        if src and tgt:
            self._refresh_titles_for_ports(src, tgt)

    def _refresh_titles_for_ports(self, src: PortItem, tgt: PortItem) -> None:
        nodes: set[NodeItem] = set()
        for port in (src, tgt):
            parent = port.parentItem()
            if isinstance(parent, NodeItem) and parent.node_type() in AUTO_TITLE_NODE_TYPES:
                nodes.add(parent)
        if nodes:
            self.refresh_display_titles(nodes)

    def collect_pose_links(self) -> dict[str, dict[str, str]]:
        """motion_node_id -> {input_port: Position 显示名}"""
        node_by_id: dict[str, NodeItem] = {}
        for item in self.items():
            if isinstance(item, NodeItem):
                nid = item.data(0)
                if nid:
                    node_by_id[nid] = item

        links: dict[str, dict[str, str]] = {}
        for item in self.items():
            if not isinstance(item, EdgeItem):
                continue
            src_port = item.source()
            tgt_port = item.target()
            if not src_port or not tgt_port:
                continue
            src_node = src_port.parentItem()
            tgt_node = tgt_port.parentItem()
            if not isinstance(src_node, NodeItem) or not isinstance(tgt_node, NodeItem):
                continue
            if src_node.node_type() != "Position":
                continue
            if tgt_port.port_type() != "pose":
                continue
            tgt_id = tgt_node.data(0)
            if not tgt_id:
                continue
            pdata = src_node.node_data() or {}
            name = (pdata.get("name") or "").strip() or src_node._title or "Position"
            links.setdefault(tgt_id, {})[tgt_port.port_name()] = name
        return links

    def refresh_display_titles(self, nodes: set[NodeItem] | None = None) -> None:
        pose_map = self.collect_pose_links()
        if nodes is None:
            nodes = {item for item in self.items() if isinstance(item, NodeItem)}
        for node in nodes:
            nid = node.data(0)
            pose_links = pose_map.get(nid, {}) if nid else {}
            node.refresh_display_title(pose_links)

    def _linear_flow_ports(self, node: NodeItem) -> tuple[PortItem | None, PortItem | None]:
        """主 flow 链路上的 in/out（名为 flow 的端口）。"""
        flow_in = None
        flow_out = None
        for p in node.input_ports():
            if p.port_type() == "flow" and p.port_name() == "flow":
                flow_in = p
                break
        for p in node.output_ports():
            if p.port_type() == "flow" and p.port_name() == "flow":
                flow_out = p
                break
        return flow_in, flow_out

    def _edge_at(
        self,
        scene_pos: QPointF,
        *,
        exclude_node: NodeItem | None = None,
        max_dist: float = 15.0,
    ) -> EdgeItem | None:
        """在 scene_pos 附近查找最近的 flow 连线。"""
        best = None
        best_dist = max_dist
        for item in self.items():
            if not isinstance(item, EdgeItem):
                continue
            src = item.source()
            tgt = item.target()
            if not src or not tgt:
                continue
            if src.port_type() != "flow" or tgt.port_type() != "flow":
                continue
            if exclude_node is not None:
                src_node = src.parentItem()
                tgt_node = tgt.parentItem()
                if src_node is exclude_node or tgt_node is exclude_node:
                    continue
            path = item.path()
            length = path.length()
            if length <= 0:
                continue
            step = max(length / 20, 1.0)
            d = 0.0
            while d <= length:
                pt = path.pointAtPercent(d / length)
                dist = (pt - scene_pos).manhattanLength()
                if dist < best_dist:
                    best_dist = dist
                    best = item
                d += step
        return best

    def _node_already_between_ports(
        self,
        node: NodeItem,
        src_port: PortItem,
        tgt_port: PortItem,
    ) -> bool:
        flow_in, flow_out = self._linear_flow_ports(node)
        if flow_in is None or flow_out is None:
            return False
        has_in = any(e.source() is src_port for e in flow_in.connected_edges)
        has_out = any(e.target() is tgt_port for e in flow_out.connected_edges)
        return has_in and has_out

    def try_insert_node_on_flow_edge(
        self,
        node: NodeItem,
        scene_pos: QPointF,
    ) -> bool:
        """将已有/新建节点插入 flow 连线中间。成功返回 True。"""
        flow_in, flow_out = self._linear_flow_ports(node)
        if flow_in is None or flow_out is None:
            return False

        edge = self._edge_at(scene_pos, exclude_node=node)
        if edge is None:
            edge = self._edge_at(node.sceneBoundingRect().center(), exclude_node=node)
        if edge is None:
            return False

        src_port = edge.source()
        tgt_port = edge.target()
        if not src_port or not tgt_port:
            return False

        if self._node_already_between_ports(node, src_port, tgt_port):
            return True

        for port in (flow_in, flow_out):
            for old in list(port.connected_edges):
                self._remove_edge(old)

        self._remove_edge(edge)
        self._add_edge(src_port, flow_in)
        self._add_edge(flow_out, tgt_port)
        return True

    # ── drag-to-connect ──

    def start_connect(self, port: PortItem):
        self._drag_source = port
        self._drag_from_input = (port.direction() == "input")
        if self._drag_from_input:
            # dragging from input: temp edge goes from mouse to input port
            self._temp_edge = EdgeItem(None, port)
        else:
            self._temp_edge = EdgeItem(port, None)
        self.addItem(self._temp_edge)

    def update_connect(self, pos: QPointF):
        if self._temp_edge:
            self._temp_edge.set_temp_end(pos)

    def finish_connect(self, pos: QPointF):
        if not self._temp_edge:
            return
        self.removeItem(self._temp_edge)
        temp = self._temp_edge
        self._temp_edge = None
        src = self._drag_source
        self._drag_source = None

        target = self._port_at(pos)
        if target and target is not src:
            # connect src→target (src is output, target is input)
            if src.direction() == "output":
                self._add_edge(src, target)
            else:
                self._add_edge(target, src)
        elif not target and src.direction() == "input":
            # dragged from input port to empty space → create constant
            from app.widgets.node_editor.port_types import literal_node_for_port

            node_type = literal_node_for_port(src.port_type())
            if not node_type:
                return
            node = self.add_node(node_type, pos.x(), pos.y())
            # set sensible defaults
            default_vals = {"Int": 1, "Float": 1.0, "Bool": True, "String": ""}
            if node_type in default_vals:
                node.set_node_data({"value": default_vals[node_type]})
                node._title = str(default_vals[node_type])
                node.update()
            out_port = node.output_ports()[0] if node.output_ports() else None
            if out_port:
                self._add_edge(out_port, src)

    def _port_at(self, pos: QPointF, radius: float = 16.0) -> PortItem | None:
        """在 pos 周围 radius 范围内查找最近端口"""
        best = None
        best_dist = radius
        # check top-level port items
        for item in self.items():
            if isinstance(item, PortItem):
                d = (item.scene_center() - pos).manhattanLength()
                if d < best_dist:
                    best = item
                    best_dist = d
        # check ports on nodes (children of NodeItem)
        for item in self.items():
            if isinstance(item, NodeItem):
                for port in item.ports():
                    d = (port.scene_center() - pos).manhattanLength()
                    if d < best_dist:
                        best = port
                        best_dist = d
        return best

    # ── draw ──

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in list(self.selectedItems()):
                if isinstance(item, NodeItem):
                    self.remove_node(item)
        super().keyPressEvent(event)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(self.GRID_COLOR, 1)
        painter.setPen(pen)

        gs = self.GRID_SIZE
        left = int(rect.left()) - (int(rect.left()) % gs)
        top = int(rect.top()) - (int(rect.top()) % gs)

        x = left
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += gs
        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += gs
