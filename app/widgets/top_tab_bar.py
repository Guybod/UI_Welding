from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QScrollArea
from PySide6.QtCore import Qt, Signal

from app.page_registry import PAGE_REGISTRY, PageSpec
from app.i18n import I18nManager, tr

TAB_I18N_KEYS = {
    "home": "tab_home",
    "welding": "tab_welding",
    "upload": "tab_upload",
}


class TopTabBar(QWidget):
    """顶部功能页标签栏 — 横向排列, 滚轮滚动, 选中高亮, 支持双语"""

    tab_clicked = Signal(PageSpec)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("topTabBarPlaceholder")
        self.setFixedHeight(48)

        self._buttons: dict[str, QPushButton] = {}

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._layout = QHBoxLayout(container)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()

        for spec in PAGE_REGISTRY:
            i18n_key = TAB_I18N_KEYS.get(spec.key, spec.title)
            btn = QPushButton(tr(i18n_key))
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self._make_handler(spec))
            self._layout.insertWidget(self._layout.count() - 1, btn)
            self._buttons[spec.key] = btn

        self._scroll.setWidget(container)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._scroll)

        self.setFocusPolicy(Qt.NoFocus)

        if PAGE_REGISTRY:
            self._buttons[PAGE_REGISTRY[0].key].setChecked(True)

        I18nManager.instance().language_changed.connect(self._on_language_changed)

    def _make_handler(self, spec: PageSpec):
        def handler():
            self.set_active(spec.key)
            self.tab_clicked.emit(spec)
        return handler

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.setChecked(k == key)

    def wheelEvent(self, event):
        bar = self._scroll.horizontalScrollBar()
        delta = event.angleDelta().y()
        bar.setValue(bar.value() - delta)
        event.accept()

    def _on_language_changed(self, lang: str):
        for spec in PAGE_REGISTRY:
            if spec.key in self._buttons:
                i18n_key = TAB_I18N_KEYS.get(spec.key, spec.title)
                self._buttons[spec.key].setText(tr(i18n_key))
