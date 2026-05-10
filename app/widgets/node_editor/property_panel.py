from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QFormLayout, QScrollArea, QDoubleSpinBox,
)
from PySide6.QtCore import Qt, Signal, QEvent
from app.i18n import I18nManager, tr
from services.robot_realtime_state import RobotRealtimeState


class PropertyPanel(QWidget):
    """属性面板 — 根据选中节点类型显示参数, 支持双语"""

    apply_requested = Signal(object, dict)  # node_item, data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyPanel")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)
        self._node = None
        self._title_label = None

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)

        self._show_placeholder()
        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def set_node(self, node):
        """选中节点变化时调用, node 可为 None"""
        self._node = node
        if node is None:
            self._show_placeholder()
            return
        nt = node.node_type()
        if nt == "Position":
            self._show_position(node)
        elif nt in ("MoveJ", "MoveL", "MoveC", "MoveCircle", "MovePath"):
            self._show_motion(node)
        elif nt == "Wait":
            self._show_placeholder()  # duration 完全由数据连线提供
        elif nt in ("Int",):
            self._show_generic(node, [("value", "int", "")])
        elif nt in ("Float",):
            self._show_generic(node, [("value", "float", "")])
        elif nt == "Bool":
            self._show_bool(node)
        elif nt == "String":
            self._show_generic(node, [("value", "string", "")])
        elif nt in ("SetDO", "SetAO"):
            self._show_generic(node, [("port", "int", ""), ("value", "int", "")])
        elif nt in ("ReadDI", "ReadAI"):
            self._show_generic(node, [("port", "int", "")])
        elif nt == "GetVar":
            self._show_var_value(node)
        elif nt == "SetRegister":
            self._show_generic(node, [("address", "int", ""), ("value", "int", "")])
        elif nt == "ReadRegister":
            self._show_generic(node, [("address", "int", "")])
        else:
            self._show_placeholder()

    def _show_motion(self, node):
        """MoveJ/L/C/Circle/Path 运动参数"""
        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(f"{node._title} - {tr('pos_opt_group')}"))
        form = QFormLayout()
        speed = self._mk_spin(Range=(1, 5000))
        speed.setValue(data.get("speed", 200))
        speed.setSuffix(" mm/s")
        form.addRow(tr("pos_speed"), speed)
        acc = self._mk_spin(Range=(1, 50000))
        acc.setValue(data.get("acc", 500))
        acc.setSuffix(" mm/s²")
        form.addRow(tr("pos_acc"), acc)
        blend = self._mk_spin(Range=(0, 1000), Decimals=1)
        blend.setValue(data.get("blend", 0))
        blend.setSuffix(" mm")
        form.addRow(tr("pos_blend_abs"), blend)
        rel_blend = self._mk_spin(Range=(0, 100), Decimals=1)
        rel_blend.setValue(data.get("relativeBlend", 0))
        rel_blend.setSuffix(" %")
        form.addRow(tr("pos_blend_rel"), rel_blend)
        root.addLayout(form)

        def apply():
            node.set_node_data({"speed": speed.value(), "acc": acc.value(),
                                "blend": blend.value(), "relativeBlend": rel_blend.value()})
        speed.valueChanged.connect(apply)
        acc.valueChanged.connect(apply)
        blend.valueChanged.connect(apply)
        rel_blend.valueChanged.connect(apply)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_bool(self, node):
        from PySide6.QtWidgets import QCheckBox
        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(f"{node._title}"))
        cb = QCheckBox("True")
        cb.setChecked(data.get("value", False))
        cb.toggled.connect(lambda v: node.set_node_data({"value": v}))
        root.addWidget(cb)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_var_value(self, node):
        """GetVar 节点 — 显示变量当前值, 可修改, 同步全局"""
        data = node.node_data()
        var_id = data.get("var_id", "")
        var_name = data.get("var_name", "?")
        var_type = data.get("var_type", "int")
        val = data.get("value", 0)

        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(f"变量: {var_name} ({var_type})"))

        form = QFormLayout()
        widgets = {}
        if var_type in ("int",):
            spin = self._mk_spin(Range=(-999999, 999999))
            spin.setDecimals(0)
            spin.setValue(int(float(str(val))))
            form.addRow("值:", spin)
            widgets["value"] = ("int", spin)
        elif var_type in ("float",):
            spin = self._mk_spin(Range=(-999999, 999999), Decimals=4)
            spin.setValue(float(val))
            form.addRow("值:", spin)
            widgets["value"] = ("float", spin)
        elif var_type == "bool":
            from PySide6.QtWidgets import QCheckBox
            cb = QCheckBox("True")
            cb.setChecked(bool(val))
            root.addWidget(cb)
            widgets["value"] = ("bool", cb)
        elif var_type == "string":
            line = QLineEdit(str(val))
            form.addRow("值:", line)
            widgets["value"] = ("string", line)
        root.addLayout(form)

        def apply():
            for key, (ftype, wdg) in widgets.items():
                if ftype in ("int",):
                    v = int(wdg.value())
                elif ftype == "float":
                    v = wdg.value()
                elif ftype == "bool":
                    v = wdg.isChecked()
                else:
                    v = wdg.text()
                # update library
                s = node.scene()
                lib = getattr(s, '_library', None)
                if lib and var_id:
                    for var in lib.variables():
                        if var.var_id == var_id:
                            var.value = str(v)
                            break
                # update all GetVar nodes for same var_id on canvas
                if s:
                    from app.widgets.node_editor.node_item import NodeItem
                    for item in s.items():
                        if isinstance(item, NodeItem) and item.node_type() == "GetVar":
                            d = item.node_data()
                            if d.get("var_id") == var_id:
                                d["value"] = v
                                item.set_node_data(d)
        btn = QPushButton(tr("node_btn_apply"))
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_generic(self, node, fields: list[tuple[str, str, str]]):
        """通用属性面板: fields = [(key, type, suffix), ...]"""
        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        form = QFormLayout()
        widgets = {}
        for key, ftype, suffix in fields:
            if ftype == "int":
                spin = self._mk_spin(Range=(-999999, 999999))
                spin.setDecimals(0)
                spin.setValue(int(float(str(data.get(key, 0)))))
                spin.setSuffix(f" {suffix}" if suffix else "")
                form.addRow(f"{key}:", spin)
                widgets[key] = ("int", spin)
            elif ftype == "number" or ftype == "float":
                spin = self._mk_spin(Range=(-999999, 999999), Decimals=2)
                spin.setValue(float(data.get(key, 0)))
                spin.setSuffix(f" {suffix}" if suffix else "")
                form.addRow(f"{key}:", spin)
                widgets[key] = ("float", spin)
            elif ftype == "string":
                line = QLineEdit(str(data.get(key, "")))
                form.addRow(f"{key}:", line)
                widgets[key] = ("string", line)
        root.addLayout(form)

        def apply():
            d = {}
            for key, (ftype, wdg) in widgets.items():
                if ftype in ("int",):
                    d[key] = int(wdg.value())
                elif ftype == "float":
                    d[key] = wdg.value()
                elif ftype == "string":
                    d[key] = wdg.text()
            node.set_node_data(d)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_placeholder(self):
        w = QWidget()
        l = QVBoxLayout(w)
        l.addStretch()
        hint = QLabel(tr("node_select_hint"))
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #888888;")
        hint.setObjectName("propHint")
        l.addWidget(hint)
        l.addStretch()
        self._scroll.setWidget(w)
        self._hint_label = hint

    def _mk_spin(self, **kw):
        """创建完全不响应滚轮的 QDoubleSpinBox"""
        spin = QDoubleSpinBox()
        spin.setFocusPolicy(Qt.StrongFocus)
        spin.installEventFilter(self)
        for k, v in kw.items():
            method = getattr(spin, f"set{k[0].upper()}{k[1:]}")
            if isinstance(v, tuple):
                method(*v)
            else:
                method(v)
        return spin

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            return True  # eat wheel event
        return super().eventFilter(obj, event)

    def _show_position(self, node):
        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)

        jp_checked = data.get("jp_enabled", True)
        cp_checked = data.get("cp_enabled", False)

        # ── 名称 ──
        name_layout = QFormLayout()
        self._pos_name = QLineEdit(data.get("name", ""))
        self._pos_name.setPlaceholderText("P1")
        self._pos_name_label = QLabel(tr("pos_name"))
        self._pos_name.textChanged.connect(lambda: self._pos_apply(node))
        name_layout.addRow(self._pos_name_label, self._pos_name)
        root.addLayout(name_layout)

        # ── 关节角 jp (带勾选框) ──
        from PySide6.QtWidgets import QCheckBox
        self._jp_cb = QCheckBox(tr("pos_jp_group"))
        self._jp_cb.setChecked(jp_checked)
        self._jp_cb.toggled.connect(lambda checked: self._jp_toggle(node, checked))
        root.addWidget(self._jp_cb)
        self._jp_group = QGroupBox()
        jp_layout = QFormLayout()
        jp = data.get("jp", [0, 0, 0, 0, 0, 0])
        self._jp_spins: list[QDoubleSpinBox] = []
        for i in range(6):
            spin = self._mk_spin(Range=(-360, 360))
            spin.setDecimals(2)
            spin.setValue(jp[i] if i < len(jp) else 0)
            spin.setSingleStep(1.0)
            spin.valueChanged.connect(lambda v, n=node: self._pos_apply(n))
            jp_layout.addRow(f"J{i + 1}:", spin)
            self._jp_spins.append(spin)
        self._jp_group.setLayout(jp_layout)
        self._jp_group.setVisible(jp_checked)
        root.addWidget(self._jp_group)

        # ── 笛卡尔 cp (带勾选框) ──
        self._cp_cb = QCheckBox(tr("pos_cp_group"))
        self._cp_cb.setChecked(cp_checked)
        self._cp_cb.toggled.connect(lambda checked: self._cp_toggle(node, checked))
        root.addWidget(self._cp_cb)
        self._cp_group = QGroupBox()
        cp_layout = QFormLayout()
        cp = data.get("cp", {"x": 0, "y": 0, "z": 0, "a": 0, "b": 0, "c": 0})
        self._cp_spins: dict[str, QDoubleSpinBox] = {}
        for key in ("x", "y", "z"):
            spin = self._mk_spin(Range=(-9999, 9999), Decimals=1)
            spin.setValue(cp.get(key, 0))
            spin.setSingleStep(10.0)
            spin.valueChanged.connect(lambda v, n=node: self._pos_apply(n))
            cp_layout.addRow(f"{key.upper()}:", spin)
            self._cp_spins[key] = spin
        for key in ("a", "b", "c"):
            spin = self._mk_spin(Range=(-360, 360), Decimals=2)
            spin.setValue(cp.get(key, 0))
            spin.setSingleStep(1.0)
            spin.valueChanged.connect(lambda v, n=node: self._pos_apply(n))
            cp_layout.addRow(f"{key.upper()}:", spin)
            self._cp_spins[key] = spin
        self._cp_group.setLayout(cp_layout)
        self._cp_group.setVisible(cp_checked)
        root.addWidget(self._cp_group)

        # ── optional ──
        self._opt_group = QGroupBox(tr("pos_opt_group"))
        opt_layout = QFormLayout()
        opt = data.get("optional", {"speed": 200, "acc": 500, "blend": 0, "relativeBlend": 0})
        self._opt_speed = self._mk_spin(Range=(1, 5000))
        self._opt_speed.setDecimals(0)
        self._opt_speed.setValue(opt.get("speed", 200))
        self._opt_speed.setSuffix(" mm/s")
        self._opt_speed.valueChanged.connect(lambda v: self._pos_apply(node))
        self._opt_speed_label = QLabel(tr("pos_speed"))
        opt_layout.addRow(self._opt_speed_label, self._opt_speed)
        self._opt_acc = self._mk_spin(Range=(1, 50000))
        self._opt_acc.setDecimals(0)
        self._opt_acc.setValue(opt.get("acc", 500))
        self._opt_acc.setSuffix(" mm/s²")
        self._opt_acc.valueChanged.connect(lambda v: self._pos_apply(node))
        self._opt_acc_label = QLabel(tr("pos_acc"))
        opt_layout.addRow(self._opt_acc_label, self._opt_acc)
        self._opt_blend = self._mk_spin(Range=(0, 1000), Decimals=1)
        self._opt_blend.setValue(opt.get("blend", 0))
        self._opt_blend.setSuffix(" mm")
        self._opt_blend.valueChanged.connect(lambda v: self._pos_apply(node))
        self._opt_blend_abs_label = QLabel(tr("pos_blend_abs"))
        opt_layout.addRow(self._opt_blend_abs_label, self._opt_blend)
        self._opt_rel_blend = self._mk_spin(Range=(0, 100), Decimals=1)
        self._opt_rel_blend.setValue(opt.get("relativeBlend", 0))
        self._opt_rel_blend.setSuffix(" %")
        self._opt_rel_blend.valueChanged.connect(lambda v: self._pos_apply(node))
        self._opt_rel_blend_rel_label = QLabel(tr("pos_blend_rel"))
        opt_layout.addRow(self._opt_rel_blend_rel_label, self._opt_rel_blend)
        self._opt_group.setLayout(opt_layout)
        root.addWidget(self._opt_group)

        # ── 按钮 ──
        self._btn_update_pos = QPushButton(tr("node_btn_update_pos"))
        self._btn_update_pos.setEnabled(RobotRealtimeState.instance().is_valid())
        self._btn_update_pos.clicked.connect(lambda: self._on_update_current(node))
        root.addWidget(self._btn_update_pos)

        root.addStretch()
        self._scroll.setWidget(w)

    def _pos_apply(self, node):
        """即时应用 Position 修改"""
        jp = [s.value() for s in self._jp_spins] if hasattr(self, '_jp_spins') else []
        cp = {k: s.value() for k, s in self._cp_spins.items()} if hasattr(self, '_cp_spins') else {}
        data = {
            "name": self._pos_name.text().strip(),
            "jp": jp, "cp": cp, "ep": [],
            "jp_enabled": self._jp_cb.isChecked() if hasattr(self, '_jp_cb') else True,
            "cp_enabled": self._cp_cb.isChecked() if hasattr(self, '_cp_cb') else False,
            "optional": {
                "speed": self._opt_speed.value(), "acc": self._opt_acc.value(),
                "blend": self._opt_blend.value(), "relativeBlend": self._opt_rel_blend.value(),
            },
        }
        node.set_node_data(data)
        name = data["name"] or "Position"
        if node._title != name:
            node._title = name
            node.update()

    def _jp_toggle(self, node, checked):
        self._jp_group.setVisible(checked)
        self._pos_apply(node)

    def _cp_toggle(self, node, checked):
        self._cp_group.setVisible(checked)
        self._pos_apply(node)

    def _on_language_changed(self, lang: str):
        # 重建面板避免已销毁控件的引用
        if self._node is not None:
            self.set_node(self._node)
        else:
            self._show_placeholder()

    def _on_update_current(self, node):
        state = RobotRealtimeState.instance()
        if not state.is_valid():
            return
        joints = state.current_joints_deg()
        for i, spin in enumerate(self._jp_spins):
            if i < len(joints):
                spin.setValue(round(joints[i], 2))
        x, y, z, a, b, c = state.current_tcp_pose_mm_deg()
        self._cp_spins["x"].setValue(round(x, 1))
        self._cp_spins["y"].setValue(round(y, 1))
        self._cp_spins["z"].setValue(round(z, 1))
        self._cp_spins["a"].setValue(round(a, 2))
        self._cp_spins["b"].setValue(round(b, 2))
        self._cp_spins["c"].setValue(round(c, 2))
        self._pos_apply(node)

    def _on_apply(self):
        if not self._node:
            return
        jp = [s.value() for s in self._jp_spins]
        cp = {k: s.value() for k, s in self._cp_spins.items()}
        data = {
            "name": self._pos_name.text().strip(),
            "jp": jp,
            "cp": cp,
            "ep": [],
            "optional": {
                "speed": self._opt_speed.value(),
                "acc": self._opt_acc.value(),
                "blend": self._opt_blend.value(),
                "relativeBlend": self._opt_rel_blend.value(),
            },
        }
        self._node.set_node_data(data)
        name = data["name"] or "Position"
        if self._node._title != name:
            self._node._title = name
            self._node.update()
        self.apply_requested.emit(self._node, data)

    def clear(self):
        self._node = None
        self._show_placeholder()
