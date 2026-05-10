from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget

from app.base_page import BasePage
from app.page_registry import PageSpec


class PageRouter(QObject):
    """页面路由器 — 懒加载 + 缓存 + on_enter/on_leave"""

    on_stop_jog_requested = Signal()  # Part 1B 空实现, Part 9 连接

    def __init__(self, page_stack: QStackedWidget, parent=None):
        super().__init__(parent)
        self._stack = page_stack
        self._cache: dict[str, BasePage] = {}
        self._current_key: str | None = None

    def navigate(self, spec: PageSpec):
        if spec.key == self._current_key:
            return

        # 旧页 on_leave
        if self._current_key and self._current_key in self._cache:
            self._cache[self._current_key].on_leave()

        # 懒加载
        if spec.key not in self._cache:
            page = spec.factory()
            self._stack.addWidget(page)
            self._cache[spec.key] = page

        page = self._cache[spec.key]
        self._stack.setCurrentWidget(page)
        self._current_key = spec.key

        # 新页 on_enter
        page.on_enter()

    def current_page(self) -> BasePage | None:
        if self._current_key:
            return self._cache.get(self._current_key)
        return None
