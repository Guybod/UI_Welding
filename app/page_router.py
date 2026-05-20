from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget

from app.base_page import BasePage
from app.page_registry import PageSpec
from core.logger import log


class PageRouter(QObject):
    """页面路由器 — 懒加载 + 缓存 + on_enter/on_leave"""

    on_stop_jog_requested = Signal()  # Part 1B 空实现, Part 9 连接

    def __init__(self, page_stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack = page_stack
        self._cache: dict[str, BasePage] = {}
        self._current_key: str | None = None
        self._service_provider = None

    def set_service_provider(self, sp):
        """注入 ServiceProvider，并监听连接状态变化以通知所有页面。"""
        self._service_provider = sp
        if sp and sp.cm:
            sp.cm.connection_state_changed.connect(self._on_connection_changed)

    def _on_connection_changed(self, state: str):
        connected = state == "connected"
        for page in self._cache.values():
            page.on_connection_changed(connected)

    def notify_robot_mode(self, mode: int) -> None:
        """机器人模式变化时通知所有已缓存页面（IO/寄存器等需远程模式）。"""
        for page in self._cache.values():
            handler = getattr(page, "on_robot_mode_changed", None)
            if callable(handler):
                handler(mode)

    def navigate(self, spec: PageSpec):
        if spec.key == self._current_key:
            return

        from_key = self._current_key or "(none)"
        log.info("[PageRouter] navigate %s -> %s", from_key, spec.key)

        # 旧页 on_leave（切页时停止全局点动）
        if self._current_key and self._current_key in self._cache:
            self.on_stop_jog_requested.emit()
            self._cache[self._current_key].on_leave()

        # 懒加载
        if spec.key not in self._cache:
            log.info("[PageRouter] lazy load page key=%s", spec.key)
            page = spec.factory()
            self._stack.addWidget(page)
            self._cache[spec.key] = page

        page = self._cache[spec.key]

        # 注入 ServiceProvider（仅首次）
        if self._service_provider and page._service_provider is None:
            page._service_provider = self._service_provider

        self._stack.setCurrentWidget(page)
        self._current_key = spec.key

        # 新页 on_enter
        page.on_enter()

    def current_page(self) -> BasePage | None:
        if self._current_key:
            return self._cache.get(self._current_key)
        return None

    def get_cached_page(self, key: str) -> BasePage | None:
        return self._cache.get(key)

    def persist_all_page_settings(self):
        """退出前保存已缓存页面中的 QSettings（不触发 on_leave 副作用）。"""
        for page in self._cache.values():
            saver = getattr(page, "_save_settings", None)
            if callable(saver):
                saver()
