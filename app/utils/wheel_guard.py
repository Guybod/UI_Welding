"""全局鼠标滚轮防护 — 禁止 QSpinBox/QDoubleSpinBox/QComboBox 通过滚轮改值。

用法（在 QApplication 创建后调用一次）:
    from app.utils.wheel_guard import install_wheel_guard
    install_wheel_guard(app)
"""

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox

_WHEEL_BLOCKED_TYPES = (QSpinBox, QDoubleSpinBox, QComboBox)


class _WheelGuardFilter(QObject):
    """全局 eventFilter — 拦截滚轮控件上的 Wheel 事件并转发给父级。

    转发给父级使 QScrollArea 等容器仍可正常滚动，
    同时阻止滚轮改变 SpinBox/ComboBox 的值。
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, _WHEEL_BLOCKED_TYPES):
            parent = obj.parent()
            if parent is not None:
                from PySide6.QtCore import QCoreApplication
                QCoreApplication.sendEvent(parent, event)
            return True
        return super().eventFilter(obj, event)


def install_wheel_guard(app):
    """在 QApplication 上安装全局滚轮防护。返回 guard 对象（需保持引用）。"""
    guard = _WheelGuardFilter(app)
    app.installEventFilter(guard)
    return guard
