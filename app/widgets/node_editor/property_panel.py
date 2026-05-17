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
    variable_value_changed = Signal(str, object)  # var_id, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("propertyPanel")
        self.setMinimumWidth(200)
        self.setMaximumWidth(360)
        self._node = None
        self._title_label = None
        self._var_bound_id: str | None = None
        self._var_value_widget = None
        self._var_value_type: str | None = None

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
        elif nt == "Array":
            self._show_array(node)
        elif nt == "ArraySet":
            self._show_placeholder()
        elif nt in ("SetDO", "SetAO"):
            self._show_generic(node, [("port", "int", ""), ("value", "int", "")])
        elif nt in ("ReadDI", "ReadAI"):
            self._show_generic(node, [("port", "int", "")])
        elif nt in ("GetVar", "SetVar"):
            self._show_var_value(node)
        elif nt == "MacroCall":
            self._show_macro_call(node)
        elif nt == "Cast":
            self._show_cast(node)
        elif nt == "EnumInt":
            self._show_enum_int(node)
        elif nt == "Comment":
            self._show_comment(node)
        elif nt == "MakePosition":
            self._show_make_position(node)
        elif nt in ("Print", "Wait"):
            self._show_flow_options(node)
        elif nt == "SetRegister":
            self._show_generic(node, [("address", "int", ""), ("value", "int", "")])
        elif nt == "ReadRegister":
            self._show_generic(node, [("address", "int", "")])
        else:
            self._show_placeholder()

    def _append_disabled_toggle(self, root, node) -> None:
        from PySide6.QtWidgets import QCheckBox

        cb = QCheckBox(tr("node_disabled"))
        cb.setChecked(bool((node.node_data() or {}).get("disabled")))
        cb.toggled.connect(lambda v: self._set_node_disabled(node, v))
        root.addWidget(cb)

    @staticmethod
    def _set_node_disabled(node, disabled: bool) -> None:
        data = dict(node.node_data() or {})
        data["disabled"] = disabled
        node.set_node_data(data)

    def _show_flow_options(self, node) -> None:
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        self._append_disabled_toggle(root, node)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_cast(self, node) -> None:
        from PySide6.QtWidgets import QComboBox

        data = node.node_data() or {}
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        combo = QComboBox()
        for t in ("int", "float", "bool", "string"):
            combo.addItem(t, t)
        cur = (data.get("cast_to") or "float").lower()
        combo.setCurrentIndex(max(0, combo.findData(cur)))

        def apply():
            d = dict(node.node_data() or {})
            d["cast_to"] = combo.currentData()
            d["_auto_title"] = True
            node.set_node_data(d)

        combo.currentIndexChanged.connect(apply)
        root.addWidget(combo)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_enum_int(self, node) -> None:
        data = node.node_data() or {}
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        opts = QLineEdit(",".join(str(x) for x in (data.get("options") or [0, 1])))
        root.addWidget(QLabel(tr("enum_options")))
        root.addWidget(opts)
        sel = QLineEdit(str(int(data.get("selected", 0))))
        root.addWidget(QLabel(tr("enum_selected_index")))
        root.addWidget(sel)

        def apply():
            parts = [p.strip() for p in opts.text().split(",") if p.strip()]
            values = []
            for p in parts:
                try:
                    values.append(int(p))
                except ValueError:
                    values.append(0)
            if not values:
                values = [0]
            try:
                index = int(sel.text())
            except ValueError:
                index = 0
            index = max(0, min(index, len(values) - 1))
            node.set_node_data({
                "options": values,
                "selected": index,
                "_auto_title": True,
            })

        opts.editingFinished.connect(apply)
        sel.editingFinished.connect(apply)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_comment(self, node) -> None:
        from PySide6.QtWidgets import QTextEdit

        data = node.node_data() or {}
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        edit = QTextEdit()
        edit.setPlainText(data.get("text", ""))
        edit.setMaximumHeight(120)

        def apply():
            text = edit.toPlainText()
            node.set_node_data({"text": text})
            node._calc_size()
            node.update()

        edit.textChanged.connect(apply)
        root.addWidget(edit)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_make_position(self, node) -> None:
        data = node.node_data() or {}
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        name = QLineEdit(str(data.get("name", "")))
        root.addWidget(QLabel(tr("pos_name")))
        root.addWidget(name)

        def apply():
            d = dict(node.node_data() or {})
            d["name"] = name.text().strip()
            d["_auto_title"] = True
            node.set_node_data(d)

        name.editingFinished.connect(apply)
        root.addStretch()
        self._scroll.setWidget(w)

    def _show_macro_call(self, node) -> None:
        data = node.node_data() or {}
        macro_id = data.get("macro_id", "")
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        root.addWidget(QLabel(tr("macro_prop_id").format(id=macro_id)))
        macro = None
        scene = node.scene()
        lib = getattr(scene, "_library", None) if scene else None
        if lib and macro_id:
            macro = lib.get_macro(macro_id)
        if macro and macro.params:
            ins = [p for p in macro.params if p.direction == "in"]
            outs = [p for p in macro.params if p.direction == "out"]
            if ins:
                root.addWidget(QLabel(tr("macro_prop_inputs")))
                for p in ins:
                    root.addWidget(QLabel(f"  ↓ {p.param_id}: {p.name} ({p.port_type})"))
            if outs:
                root.addWidget(QLabel(tr("macro_prop_outputs")))
                for p in outs:
                    root.addWidget(QLabel(f"  ↑ {p.param_id}: {p.name} ({p.port_type})"))
        btn = QPushButton(tr("macro_edit"))
        btn.clicked.connect(lambda: self._request_macro_edit(macro_id))
        root.addWidget(btn)
        root.addStretch()
        self._scroll.setWidget(w)

    def _request_macro_edit(self, macro_id: str) -> None:
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "_open_macro_editor"):
                parent._open_macro_editor(macro_id)
                return
            parent = parent.parent()

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
        self._append_disabled_toggle(root, node)
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

    def _show_array(self, node):
        from app.widgets.node_editor.array_list_editor import ArrayListEditor

        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(node._title))
        editor = ArrayListEditor()
        editor.set_value(data.get("value", []))

        def apply(val: list) -> None:
            data = dict(node.node_data())
            data["value"] = val
            data["_auto_title"] = True
            node.set_node_data(data)

        editor.value_changed.connect(apply)
        root.addWidget(editor)
        root.addStretch()
        self._scroll.setWidget(w)

    @staticmethod
    def _array_node_title(val: list) -> str:
        if not val:
            return "Array"
        preview = ", ".join(str(v)[:10] for v in val[:3])
        if len(val) > 3:
            preview += "..."
        return f"[{preview}]"

    def _show_var_value(self, node):
        """GetVar/SetVar — 显示并编辑绑定变量的当前值，全类型同步。"""
        from PySide6.QtWidgets import QCheckBox
        from app.widgets.node_editor.array_list_editor import ArrayListEditor
        from app.widgets.node_editor.var_value import parse_var_storage

        data = node.node_data()
        var_id = data.get("var_id", "")
        var_name = data.get("var_name", "?")
        var_type = data.get("var_type", "int")
        mode = "Get" if node.node_type() == "GetVar" else "Set"

        val = parse_var_storage(data.get("value"), var_type)
        scene = node.scene()
        lib = getattr(scene, "_library", None) if scene else None
        if lib and var_id:
            for var in lib.variables():
                if var.var_id == var_id:
                    val = parse_var_storage(var.value, var_type)
                    break

        self._var_bound_id = var_id or None
        self._var_value_widget = None
        self._var_value_type = var_type

        w = QWidget()
        root = QVBoxLayout(w)
        root.addWidget(QLabel(f"{mode} · {var_name} ({var_type})"))

        form = QFormLayout()
        widgets: dict = {}

        if var_type == "int":
            spin = self._mk_spin(Range=(-999999, 999999))
            spin.setDecimals(0)
            spin.setValue(int(float(str(val))))
            form.addRow("值:", spin)
            widgets["value"] = ("int", spin)
            self._var_value_widget = spin
        elif var_type == "float":
            spin = self._mk_spin(Range=(-999999, 999999), Decimals=4)
            spin.setValue(float(val))
            form.addRow("值:", spin)
            widgets["value"] = ("float", spin)
            self._var_value_widget = spin
        elif var_type == "bool":
            cb = QCheckBox("True")
            cb.setChecked(bool(val))
            form.addRow("值:", cb)
            widgets["value"] = ("bool", cb)
            self._var_value_widget = cb
        elif var_type == "string":
            line = QLineEdit(str(val))
            form.addRow("值:", line)
            widgets["value"] = ("string", line)
            self._var_value_widget = line
        elif var_type == "array":
            editor = ArrayListEditor()
            editor.set_value(val)
            root.addWidget(editor)
            widgets["value"] = ("array", editor)
            self._var_value_widget = editor
        else:
            line = QLineEdit(str(val))
            form.addRow("值:", line)
            widgets["value"] = ("string", line)
            self._var_value_widget = line

        root.addLayout(form)

        def apply():
            if not var_id:
                return
            for _key, (ftype, wdg) in widgets.items():
                if ftype == "int":
                    v = int(wdg.value())
                elif ftype == "float":
                    v = float(wdg.value())
                elif ftype == "bool":
                    v = bool(wdg.isChecked())
                elif ftype == "array":
                    v = wdg.get_value()
                else:
                    v = wdg.text()
            self.variable_value_changed.emit(var_id, v)

        for _key, (ftype, wdg) in widgets.items():
            if ftype in ("int", "float"):
                wdg.valueChanged.connect(apply)
            elif ftype == "bool":
                wdg.toggled.connect(apply)
            elif ftype == "array":
                wdg.value_changed.connect(apply)
            else:
                wdg.editingFinished.connect(apply)

        root.addStretch()
        self._scroll.setWidget(w)

    def refresh_bound_variable_value(self, var_id: str, value) -> None:
        """同 var_id 在别处被修改时，刷新右侧显示（不触发回写）。"""
        from app.widgets.node_editor.array_list_editor import ArrayListEditor
        from app.widgets.node_editor.var_value import parse_var_storage

        if not var_id or var_id != self._var_bound_id:
            return
        w = self._var_value_widget
        if w is None:
            return
        val = parse_var_storage(value, self._var_value_type or "int")
        w.blockSignals(True)
        try:
            vt = self._var_value_type
            if vt == "int":
                w.setValue(int(float(val)))
            elif vt == "float":
                w.setValue(float(val))
            elif vt == "bool":
                w.setChecked(bool(val))
            elif vt == "array" and isinstance(w, ArrayListEditor):
                w.set_value(val)
            else:
                w.setText(str(val))
        finally:
            w.blockSignals(False)

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

        for key, (ftype, wdg) in widgets.items():
            if ftype in ("int", "float"):
                wdg.valueChanged.connect(apply)
            elif ftype == "string":
                wdg.textChanged.connect(apply)

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
        data["_auto_title"] = True
        node.set_node_data(data)

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
        data["_auto_title"] = True
        self._node.set_node_data(data)
        self.apply_requested.emit(self._node, data)

    def clear(self):
        self._node = None
        self._var_bound_id = None
        self._var_value_widget = None
        self._var_value_type = None
        self._show_placeholder()
