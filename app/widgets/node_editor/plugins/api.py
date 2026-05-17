"""自定义节点插件 API — 第三方扩展入口。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Any

from app.widgets.node_editor.models import PortSpec

if TYPE_CHECKING:
    from app.widgets.node_editor.execution_engine import ExecutionEngine
    from app.widgets.node_editor.models import NodeData

# (engine, node) -> None；负责推进 flow（调用 engine._advance_to）
FlowHandler = Callable[["ExecutionEngine", "NodeData"], None]


@dataclass
class NodePluginDefinition:
    """一个可注册到节点库与执行引擎的自定义节点。"""

    node_type: str
    title: str
    category: str = "自定义"
    color: str = "#795548"
    ports: list[PortSpec] = field(default_factory=list)
    on_flow: FlowHandler | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def node_spec(self):
        from app.widgets.node_editor.models import NodeSpec

        return NodeSpec(
            self.node_type,
            self.title,
            self.category,
            list(self.ports),
            color=self.color,
        )
