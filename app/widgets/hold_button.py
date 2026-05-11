from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Signal, QTimer, Qt


class HoldButton(QPushButton):
    """按住保持型按钮：pressed→hold_started，released→hold_stopped。

    用于焊接送气/送丝/退丝、绘图 CRI 执行等需要按住保持的操作。
    内置 50ms debounce 防抖。
    """

    hold_started = Signal()
    hold_stopped = Signal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(50)
        self.pressed.connect(self._on_pressed)
        self.released.connect(self._on_released)

    def _on_pressed(self):
        self._debounce.timeout.connect(self.hold_started.emit)
        self._debounce.start()

    def _on_released(self):
        self._debounce.stop()
        try:
            self._debounce.timeout.disconnect(self.hold_started.emit)
        except (TypeError, RuntimeError):
            pass
        self.hold_stopped.emit()
