"""运动 Beta 节点编辑器 — 可视化分步教程。"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import tr
from app.widgets.node_editor.port_types import PORT_COLORS


@dataclass
class _MiniNode:
    nid: str
    x: float
    y: float
    w: float
    h: float
    title: str
    color: str
    inputs: list[tuple[str, str]] = field(default_factory=list)
    outputs: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _MiniEdge:
    src: str
    src_port: str
    tgt: str
    tgt_port: str
    port_type: str = "flow"


class TutorialDiagramWidget(QWidget):
    """用简化的节点/连线示意图说明概念。"""

    def __init__(self, nodes: list[_MiniNode], edges: list[_MiniEdge], parent=None):
        super().__init__(parent)
        self._nodes = {n.nid: n for n in nodes}
        self._edges = edges
        self.setMinimumHeight(200)
        self.setMinimumWidth(420)

    def _port_pos(self, node: _MiniNode, port_name: str, direction: str) -> tuple[float, float]:
        ports = node.outputs if direction == "output" else node.inputs
        names = [p[0] for p in ports]
        if port_name not in names:
            idx = 0
        else:
            idx = names.index(port_name)
        count = max(len(ports), 1)
        y = node.y + 26 + idx * 16
        x = node.x + node.w if direction == "output" else node.x
        return x, y

    def paintEvent(self, event) -> None:
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(28, 28, 30))

        for edge in self._edges:
            sn = self._nodes.get(edge.src)
            tn = self._nodes.get(edge.tgt)
            if not sn or not tn:
                continue
            x1, y1 = self._port_pos(sn, edge.src_port, "output")
            x2, y2 = self._port_pos(tn, edge.tgt_port, "input")
            color = PORT_COLORS.get(edge.port_type, "#888")
            pen = QPen(QColor(color), 2 if edge.port_type == "flow" else 1.5)
            p.setPen(pen)
            mid = (x1 + x2) / 2
            path = QPainterPath()
            path.moveTo(x1, y1)
            path.cubicTo(mid, y1, mid, y2, x2, y2)
            p.drawPath(path)

        title_font = QFont()
        title_font.setPointSize(8)
        title_font.setBold(True)
        pin_font = QFont()
        pin_font.setPointSize(6)

        for node in self._nodes.values():
            rect_path = QPainterPath()
            rect_path.addRoundedRect(node.x, node.y, node.w, node.h, 5, 5)
            p.fillPath(rect_path, QColor(45, 45, 48))
            p.fillRect(int(node.x), int(node.y), int(node.w), 22, QColor(node.color))
            p.setPen(QPen(QColor(90, 90, 95)))
            p.drawRoundedRect(int(node.x), int(node.y), int(node.w), int(node.h), 5, 5)
            p.setFont(title_font)
            p.setPen(QColor(255, 255, 255))
            p.drawText(
                int(node.x), int(node.y), int(node.w), 22,
                Qt.AlignmentFlag.AlignCenter,
                node.title,
            )
            p.setFont(pin_font)
            for i, (name, ptype) in enumerate(node.inputs):
                cy = node.y + 26 + i * 16
                p.setBrush(QColor(PORT_COLORS.get(ptype, "#888")))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(int(node.x - 4), int(cy - 4), 8, 8)
                p.setPen(QColor(160, 160, 165))
                p.drawText(int(node.x + 8), int(cy - 6), name)
            for i, (name, ptype) in enumerate(node.outputs):
                cy = node.y + 26 + i * 16
                p.setBrush(QColor(PORT_COLORS.get(ptype, "#888")))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(int(node.x + node.w - 4), int(cy - 4), 8, 8)
                p.setPen(QColor(160, 160, 165))
                p.drawText(int(node.x + node.w - 36), int(cy - 6), name)


class _LayoutOverviewWidget(QWidget):
    """四栏布局示意。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)

    def paintEvent(self, event) -> None:
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(28, 28, 30))
        w, h = self.width(), self.height()
        pad = 12
        inner_w = w - pad * 2
        inner_h = h - pad * 2 - 20
        lib_w = inner_w * 0.18
        prop_w = inner_w * 0.22
        mid_w = inner_w - lib_w - prop_w
        y0 = pad + 18
        rects = [
            (pad, y0, lib_w, inner_h, tr("tutorial_panel_library"), "#388E3C"),
            (pad + lib_w + 4, y0, mid_w, inner_h * 0.78, tr("tutorial_panel_canvas"), "#1976D2"),
            (pad + lib_w + 4, y0 + inner_h * 0.8 + 4, mid_w, inner_h * 0.2 - 4, tr("tutorial_panel_log"), "#607D8B"),
            (pad + lib_w + mid_w + 8, y0, prop_w, inner_h, tr("tutorial_panel_property"), "#F57C00"),
        ]
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        for x, y, rw, rh, label, color in rects:
            p.setPen(QPen(QColor(color), 2))
            p.setBrush(QColor(40, 40, 44))
            p.drawRoundedRect(int(x), int(y), int(rw), int(rh), 6, 6)
            p.setPen(QColor(220, 220, 220))
            p.drawText(int(x + 8), int(y + 8), int(rw - 16), 24, Qt.AlignmentFlag.AlignLeft, label)


@dataclass
class _TutorialStep:
    title_key: str
    body_key: str
    diagram: QWidget | None = None
    diagram_factory: str | None = None


def _flow_data_diagram() -> QWidget:
    return TutorialDiagramWidget(
        [
            _MiniNode("s", 24, 50, 72, 52, "Start", "#607D8B", outputs=[("flow", "flow")]),
            _MiniNode("m", 130, 42, 80, 68, "MoveJ", "#1976D2",
                      inputs=[("flow", "flow"), ("target", "pose")],
                      outputs=[("flow", "flow")]),
            _MiniNode("e", 244, 50, 64, 52, "End", "#607D8B", inputs=[("flow", "flow")]),
            _MiniNode("p", 130, 8, 72, 40, "Position", "#F57C00", outputs=[("pose", "pose")]),
        ],
        [
            _MiniEdge("s", "flow", "m", "flow", "flow"),
            _MiniEdge("m", "flow", "e", "flow", "flow"),
            _MiniEdge("p", "pose", "m", "target", "pose"),
        ],
    )


def _pure_diagram() -> QWidget:
    return TutorialDiagramWidget(
        [
            _MiniNode("s", 20, 55, 70, 50, "Start", "#607D8B", outputs=[("flow", "flow")]),
            _MiniNode("w", 120, 48, 78, 62, "While", "#7B1FA2",
                      inputs=[("flow", "flow"), ("condition", "bool")],
                      outputs=[("body", "flow"), ("done", "flow")]),
            _MiniNode("e", 230, 55, 64, 50, "End", "#607D8B", inputs=[("flow", "flow")]),
            _MiniNode("a", 12, 8, 48, 38, "10", "#26A69A", outputs=[("result", "int")]),
            _MiniNode("i", 68, 8, 52, 38, "index", "#388E3C", outputs=[("value", "int")]),
            _MiniNode("gt", 132, 8, 56, 38, "Gt", "#00897B",
                      inputs=[("a", "int"), ("b", "int")], outputs=[("result", "bool")]),
        ],
        [
            _MiniEdge("s", "flow", "w", "flow", "flow"),
            _MiniEdge("w", "done", "e", "flow", "flow"),
            _MiniEdge("a", "result", "gt", "a", "int"),
            _MiniEdge("i", "value", "gt", "b", "int"),
            _MiniEdge("gt", "result", "w", "condition", "bool"),
        ],
    )


def _macro_diagram() -> QWidget:
    return TutorialDiagramWidget(
        [
            _MiniNode("mc", 40, 45, 96, 70, "Macro", "#9C27B0",
                      inputs=[("flow", "flow"), ("in_0", "int")],
                      outputs=[("flow", "flow"), ("out_0", "int")]),
            _MiniNode("pr", 170, 48, 72, 58, "Print", "#607D8B",
                      inputs=[("flow", "flow"), ("value", "any")],
                      outputs=[("flow", "flow")]),
            _MiniNode("v", 40, 8, 56, 38, "9", "#26A69A", outputs=[("result", "int")]),
        ],
        [
            _MiniEdge("v", "result", "mc", "in_0", "int"),
            _MiniEdge("mc", "out_0", "pr", "value", "any"),
            _MiniEdge("mc", "flow", "pr", "flow", "flow"),
        ],
    )


def _tools_diagram() -> QWidget:
    return TutorialDiagramWidget(
        [
            _MiniNode("c", 30, 50, 68, 48, "Cast", "#00897B",
                      inputs=[("value", "any")], outputs=[("result", "float")]),
            _MiniNode("r", 130, 54, 56, 40, "···", "#616161",
                      inputs=[("in", "any")], outputs=[("out", "any")]),
            _MiniNode("cm", 220, 20, 100, 90, "Comment", "#455A64"),
        ],
        [
            _MiniEdge("c", "result", "r", "in", "any"),
        ],
    )


class NodeEditorTutorialDialog(QDialog):
    """分步可视化教程 — 左侧目录 + 右侧示意图与说明。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("tutorial_title"))
        self.resize(820, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        root = QHBoxLayout(self)
        self._nav = QListWidget()
        self._nav.setFixedWidth(200)
        self._nav.currentRowChanged.connect(self._on_nav_changed)

        right = QVBoxLayout()
        self._title = QLabel()
        self._title.setStyleSheet("font-size: 15px; font-weight: bold; color: #eee;")
        self._title.setWordWrap(True)
        self._body = QLabel()
        self._body.setWordWrap(True)
        self._body.setStyleSheet("color: #bbb; font-size: 12px; line-height: 1.4;")
        self._body.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._stack = QStackedWidget()
        right.addWidget(self._title)
        right.addWidget(self._body)
        right.addWidget(self._stack, 1)

        nav_row = QHBoxLayout()
        self._btn_prev = QPushButton(tr("tutorial_prev"))
        self._btn_next = QPushButton(tr("tutorial_next"))
        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        nav_row.addWidget(self._btn_prev)
        nav_row.addWidget(self._btn_next)
        nav_row.addStretch()
        right.addLayout(nav_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)

        root.addWidget(self._nav)
        root.addLayout(right, 1)

        self._steps: list[tuple[str, str, QWidget]] = [
            (tr("tutorial_step_layout_t"), tr("tutorial_step_layout_b"), _LayoutOverviewWidget()),
            (tr("tutorial_step_flow_t"), tr("tutorial_step_flow_b"), _flow_data_diagram()),
            (tr("tutorial_step_pure_t"), tr("tutorial_step_pure_b"), _pure_diagram()),
            (tr("tutorial_step_compile_t"), tr("tutorial_step_compile_b"), _flow_data_diagram()),
            (tr("tutorial_step_assets_t"), tr("tutorial_step_assets_b"), _flow_data_diagram()),
            (tr("tutorial_step_macro_t"), tr("tutorial_step_macro_b"), _macro_diagram()),
            (tr("tutorial_step_tools_t"), tr("tutorial_step_tools_b"), _tools_diagram()),
        ]
        for title, body, diagram in self._steps:
            self._nav.addItem(QListWidgetItem(title.split("—")[0].strip()[:18]))
            page = QWidget()
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(diagram)
            self._stack.addWidget(page)

        self._nav.setCurrentRow(0)
        self.setStyleSheet(
            "QDialog { background: #2d2d30; }"
            "QListWidget { background: #252526; color: #ccc; border: 1px solid #444; }"
            "QListWidget::item:selected { background: #094771; color: #fff; }"
            "QPushButton { background: #3a3a3d; color: #eee; padding: 6px 14px; border: 1px solid #555; }"
            "QPushButton:hover { background: #454548; }"
        )

    def _on_nav_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._steps):
            return
        title, body, _ = self._steps[row]
        self._title.setText(title)
        self._body.setText(body)
        self._stack.setCurrentIndex(row)
        self._btn_prev.setEnabled(row > 0)
        self._btn_next.setEnabled(row < len(self._steps) - 1)

    def _go_prev(self) -> None:
        r = max(0, self._nav.currentRow() - 1)
        self._nav.setCurrentRow(r)

    def _go_next(self) -> None:
        r = min(len(self._steps) - 1, self._nav.currentRow() + 1)
        self._nav.setCurrentRow(r)


def show_node_editor_tutorial(parent=None) -> None:
    dlg = NodeEditorTutorialDialog(parent)
    dlg.exec()
