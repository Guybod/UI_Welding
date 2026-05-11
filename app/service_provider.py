from PySide6.QtCore import QObject


class ServiceProvider(QObject):
    """页面访问后端服务的唯一入口。由 main.py 创建，注入 PageRouter。"""

    def __init__(self, connection_manager, cri_service, parent=None):
        super().__init__(parent)
        self.connection_manager = connection_manager
        self.cri_service = cri_service

    @property
    def cm(self):
        return self.connection_manager

    @property
    def cri(self):
        return self.cri_service
