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


def _welding():
    from app.pages.welding_page import WeldingPage
    return WeldingPage()


def _upload():
    from app.pages.upload_page import UploadPage
    return UploadPage()


# HTTP / WebSocket 调试能力已并入上传页（RobotProjectSDK），不设独立顶栏页。
PAGE_REGISTRY = [
    PageSpec("home", "首页", "main", _home),
    PageSpec("welding", "焊接", "process", _welding),
    PageSpec("upload", "上传", "tools", _upload, requires_connection=True),
]
