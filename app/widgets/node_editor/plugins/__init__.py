"""节点编辑器插件包 — 调用 discover_plugins() 加载扩展。"""

from app.widgets.node_editor.plugins.registry import discover_plugins, register_plugin

__all__ = ["discover_plugins", "register_plugin"]
