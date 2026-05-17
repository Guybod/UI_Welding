"""示例插件：在 flow 上输出 value 引脚值到日志。"""

from __future__ import annotations

from app.widgets.node_editor.models import PortSpec
from app.widgets.node_editor.plugins.api import NodePluginDefinition
from app.widgets.node_editor.plugins.registry import register_plugin
from app.i18n import tr


def _execute_log_value(engine, node) -> None:
    val = engine._resolve_input_raw(node, "value")
    engine._emit_pin_watch(node.node_id, "value", val)
    engine._log(tr("plugin_log_value").format(value=val))
    engine._advance_to(engine._flow_target(node, "flow"), 80)


def register() -> None:
    register_plugin(NodePluginDefinition(
        node_type="PluginLog",
        title="LogValue",
        category="自定义",
        color="#795548",
        ports=[
            PortSpec("flow", "flow", "input"),
            PortSpec("flow", "flow", "output"),
            PortSpec("value", "any", "input"),
        ],
        on_flow=_execute_log_value,
    ))
