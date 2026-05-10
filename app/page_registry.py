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


def _program():
    from app.pages.program_editor import ProgramEditorPage
    return ProgramEditorPage()


def _settings():
    from app.pages.settings import SettingsPage
    return SettingsPage()


# HTTP 和 WebSocket 是上传功能的通讯手段，不作为独立页面
# 对应的 http_client / websocket_client 在 network/ 中后续实现
PAGE_REGISTRY = [
    PageSpec("home", "首页", "main", _home),
    PageSpec("motion", "运动", "robot", _motion),
    PageSpec("welding", "焊接", "process", _welding),
    PageSpec("writing", "写字", "process", _writing),
    PageSpec("io", "IO", "robot", _io),
    PageSpec("program", "程序", "robot", _program),
    PageSpec("upload", "上传", "tools", _upload),
    PageSpec("settings", "设置", "system", _settings),
]
