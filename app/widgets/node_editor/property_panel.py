from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QFormLayout, QScrollArea, QDoubleSpinBox,
)
from PySide6.QtCore import Qt, Signal
from app.i18n import I18nManager, tr


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
        elif node.node_type() == "Position":
            self._show_position(node)
        else:
            self._show_placeholder()

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

    def _show_position(self, node):
        data = node.node_data()
        w = QWidget()
        root = QVBoxLayout(w)

        # ── 名称 ──
        name_layout = QFormLayout()
        self._pos_name = QLineEdit(data.get("name", ""))
        self._pos_name.setPlaceholderText("P1")
        self._pos_name_label = QLabel(tr("pos_name"))
        name_layout.addRow(self._pos_name_label, self._pos_name)
        root.addLayout(name_layout)

        # ── 关节角 jp ──
        self._jp_group = QGroupBox(tr("pos_jp_group"))
        jp_layout = QFormLayout()
        jp = data.get("jp", [0, 0, 0, 0, 0, 0])
        self._jp_spins: list[QDoubleSpinBox] = []
        for i in range(6):
            spin = QDoubleSpinBox()
            spin.setRange(-360, 360)
            spin.setDecimals(2)
            spin.setValue(jp[i] if i < len(jp) else 0)
            spin.setSingleStep(1.0)
            jp_layout.addRow(f"J{i + 1}:", spin)
            self._jp_spins.append(spin)
        self._jp_group.setLayout(jp_layout)
        root.addWidget(self._jp_group)

        # ── 笛卡尔 cp ──
        self._cp_group = QGroupBox(tr("pos_cp_group"))
        cp_layout = QFormLayout()
        cp = data.get("cp", {"x": 0, "y": 0, "z": 0, "a": 0, "b": 0, "c": 0})
        self._cp_spins: dict[str, QDoubleSpinBox] = {}
        for key in ("x", "y", "z"):
            spin = QDoubleSpinBox()
            spin.setRange(-9999, 9999)
            spin.setDecimals(1)
            spin.setValue(cp.get(key, 0))
            spin.setSingleStep(10.0)
            cp_layout.addRow(f"{key.upper()}:", spin)
            self._cp_spins[key] = spin
        for key in ("a", "b", "c"):
            spin = QDoubleSpinBox()
            spin.setRange(-360, 360)
            spin.setDecimals(2)
            spin.setValue(cp.get(key, 0))
            spin.setSingleStep(1.0)
            cp_layout.addRow(f"{key.upper()}:", spin)
            self._cp_spins[key] = spin
        self._cp_group.setLayout(cp_layout)
        root.addWidget(self._cp_group)

        # ── optional ──
        self._opt_group = QGroupBox(tr("pos_opt_group"))
        opt_layout = QFormLayout()
        opt = data.get("optional", {"speed": 200, "acc": 500, "blend": 0, "relativeBlend": 0})
        self._opt_speed = QDoubleSpinBox()
        self._opt_speed.setRange(1, 5000)
        self._opt_speed.setDecimals(0)
        self._opt_speed.setValue(opt.get("speed", 200))
        self._opt_speed.setSuffix(" mm/s")
        self._opt_speed_label = QLabel(tr("pos_speed"))
        opt_layout.addRow(self._opt_speed_label, self._opt_speed)
        self._opt_acc = QDoubleSpinBox()
        self._opt_acc.setRange(1, 50000)
        self._opt_acc.setDecimals(0)
        self._opt_acc.setValue(opt.get("acc", 500))
        self._opt_acc.setSuffix(" mm/s²")
        self._opt_acc_label = QLabel(tr("pos_acc"))
        opt_layout.addRow(self._opt_acc_label, self._opt_acc)
        self._opt_blend = QDoubleSpinBox()
        self._opt_blend.setRange(0, 1000)
        self._opt_blend.setDecimals(1)
        self._opt_blend.setValue(opt.get("blend", 0))
        self._opt_blend.setSuffix(" mm")
        self._opt_blend_abs_label = QLabel(tr("pos_blend_abs"))
        opt_layout.addRow(self._opt_blend_abs_label, self._opt_blend)
        self._opt_rel_blend = QDoubleSpinBox()
        self._opt_rel_blend.setRange(0, 100)
        self._opt_rel_blend.setDecimals(1)
        self._opt_rel_blend.setValue(opt.get("relativeBlend", 0))
        self._opt_rel_blend.setSuffix(" %")
        self._opt_rel_blend_rel_label = QLabel(tr("pos_blend_rel"))
        opt_layout.addRow(self._opt_rel_blend_rel_label, self._opt_rel_blend)
        self._opt_group.setLayout(opt_layout)
        root.addWidget(self._opt_group)

        # ── 按钮 ──
        self._btn_update_pos = QPushButton(tr("node_btn_update_pos"))
        self._btn_update_pos.setEnabled(False)
        self._btn_update_pos.setToolTip("需要 CRI 实时数据 (阶段 7)")
        root.addWidget(self._btn_update_pos)
        self._btn_apply = QPushButton(tr("node_btn_apply"))
        self._btn_apply.clicked.connect(self._on_apply)
        root.addWidget(self._btn_apply)

        root.addStretch()
        self._scroll.setWidget(w)

    def _on_language_changed(self, lang: str):
        # 重建面板避免已销毁控件的引用
        if self._node is not None:
            self.set_node(self._node)
        else:
            self._show_placeholder()

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
