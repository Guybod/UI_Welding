from PySide6.QtCore import QThread


class TcpThread(QThread):
    """TCP 9001/9002 专用线程"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        self.exec()


class UdpThread(QThread):
    """UDP 9030 CRI 专用线程"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        self.exec()

