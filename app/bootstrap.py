"""App 窗口创建。不持有任何业务信号或网络连接。"""
from PySide6.QtWidgets import QStackedWidget
from app.pages.login_page import LoginPage
from app.main_window import MainWindow


def create_app_stack():
    """返回 (stack, login, main_win)。"""
    stack = QStackedWidget()
    stack.setWindowTitle("Codroid 机器人控制终端")
    stack.resize(1280, 800)

    login = LoginPage()
    main_win = MainWindow()
    stack.addWidget(login)
    stack.addWidget(main_win)
    stack.setCurrentWidget(login)

    return stack, login, main_win
