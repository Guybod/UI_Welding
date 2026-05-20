from dataclasses import dataclass
from typing import Callable

from app.base_page import BasePage


@dataclass
class PageSpec:
    key: str
    title: str
    category: str
    factory: Callable[[], BasePage]
    icon: str = ""
    enabled: bool = True
    requires_connection: bool = False
    requires_robot_state: bool = False


def _home():
    from app.pages.home_page import HomePage
    return HomePage()


def _motion():
    from app.pages.motion_page import MotionPage
    return MotionPage()


def _welding():
    from app.pages.welding_page import WeldingPage
    return WeldingPage()


def _writing():
    from app.pages.writing_page import WritingPage
    return WritingPage()


def _upload():
    from app.pages.upload_page import UploadPage
    return UploadPage()


def _io():
    from app.pages.io_monitor import IoMonitorPage
    return IoMonitorPage()


def _register():
    from app.pages.register_monitor_page import RegisterMonitorPage
    return RegisterMonitorPage()


def _program():
    from app.pages.program_editor import ProgramEditorPage
    return ProgramEditorPage()


# HTTP / WebSocket 调试能力已并入上传页（RobotProjectSDK），不设独立顶栏页。
PAGE_REGISTRY = [
    PageSpec("home", "首页", "main", _home),
    PageSpec("motion", "运动", "robot", _motion),
    PageSpec("welding", "焊接", "process", _welding),
    PageSpec("writing", "绘图", "process", _writing),
    PageSpec("io", "IO", "robot", _io),
    PageSpec("register", "寄存器", "robot", _register),
    PageSpec("program", "程序", "robot", _program),
    PageSpec("upload", "上传", "tools", _upload, requires_connection=True),
]
