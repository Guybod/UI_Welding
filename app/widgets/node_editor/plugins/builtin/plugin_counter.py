"""示例插件：累加 flow 经过次数（调试用）。"""

from __future__ import annotations

from app.widgets.node_editor.models import PortSpec
from app.widgets.node_editor.plugins.api import NodePluginDefinition
from app.widgets.node_editor.plugins.registry import register_plugin
from app.i18n import tr


def _execute_counter(engine, node) -> None:
    data = node.data or {}
    n = int(data.get("_count", 0)) + 1
    data["_count"] = n
    engine._log(tr("plugin_counter_tick").format(n=n))
    engine._advance_to(engine._flow_target(node, "flow"), 60)


def register() -> None:
    register_plugin(NodePluginDefinition(
        node_type="PluginCounter",
        title="FlowCounter",
        category="自定义",
        color="#5D4037",
        ports=[
            PortSpec("flow", "flow", "input"),
            PortSpec("flow", "flow", "output"),
        ],
        on_flow=_execute_counter,
    ))
