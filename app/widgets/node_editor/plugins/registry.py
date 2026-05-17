"""插件注册表 — 扫描并注册自定义节点类型。"""

from __future__ import annotations

from app.widgets.node_editor.plugins.api import NodePluginDefinition

_PLUGINS: dict[str, NodePluginDefinition] = {}
_DISCOVERED = False


def register_plugin(defn: NodePluginDefinition) -> None:
    from app.widgets.node_editor.models import NODE_SPECS

    _PLUGINS[defn.node_type] = defn
    NODE_SPECS[defn.node_type] = defn.node_spec()


def get_plugin(node_type: str) -> NodePluginDefinition | None:
    return _PLUGINS.get(node_type)


def get_flow_handler(node_type: str):
    defn = _PLUGINS.get(node_type)
    return defn.on_flow if defn else None


def plugin_node_types() -> list[str]:
    return sorted(_PLUGINS.keys())


def sync_custom_catalog(categories: list[tuple[str, list[str]]]) -> None:
    """将已注册插件写入「自定义」分类。"""
    for i, (cat, items) in enumerate(categories):
        if cat == "自定义":
            categories[i] = (cat, plugin_node_types())
            return
    categories.append(("自定义", plugin_node_types()))


def _load_module_register(module) -> None:
    fn = getattr(module, "register", None)
    if callable(fn):
        fn()


def _scan_plugin_dir(directory) -> None:
    import importlib.util
    from pathlib import Path

    d = Path(directory)
    if not d.is_dir():
        return
    for py in sorted(d.glob("*.py")):
        if py.name.startswith("_"):
            continue
        mod_name = f"_node_plugin_{py.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, py)
        if not spec or not spec.loader:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
            _load_module_register(mod)
        except Exception:
            continue


def discover_plugins() -> None:
    global _DISCOVERED
    if _DISCOVERED:
        return
    from pathlib import Path

    from app.widgets.node_editor.plugins.builtin import plugin_counter, plugin_log

    plugin_log.register()
    plugin_counter.register()
    user_dir = Path(__file__).resolve().parent / "user"
    _scan_plugin_dir(user_dir)
    _DISCOVERED = True


def all_plugins() -> list[NodePluginDefinition]:
    return list(_PLUGINS.values())
