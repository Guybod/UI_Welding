from PySide6.QtWidgets import QWidget


class BasePage(QWidget):
    """页面基类 — 所有功能页继承此类"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service_provider = None

    @property
    def sp(self):
        """ServiceProvider — 由 PageRouter 注入，提供 cm / cri 访问"""
        return self._service_provider

    def on_enter(self):
        """页面被切换为当前页时调用"""
        pass

    def on_leave(self):
        """页面被切换离开时调用"""
        pass

    def on_connection_changed(self, connected: bool):
        """连接状态变化时调用"""
        pass

    def on_robot_state_changed(self, state):
        """机器人状态变化时调用"""
        pass
