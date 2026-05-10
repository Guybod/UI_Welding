import os

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QMessageBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QSettings, Signal, QPoint, QTimer

from app.i18n import I18nManager, tr
from app.widgets.status_bar import StatusBar
from app.widgets.top_tab_bar import TopTabBar
from app.widgets.global_command_bar import GlobalCommandBar
from app.widgets.robot_control_drawer import RobotControlDrawer
from app.page_router import PageRouter
from app.page_registry import PAGE_REGISTRY


VERSION = "v2.0.0"
SETTINGS_ORG = "Codroid"
SETTINGS_APP = "RobotUI"
SETTINGS_KEY_STYLE = "ui/style"


class MainWindow(QMainWindow):
    """主窗口：顶部功能标签栏 + 中间页面区 + 左侧运动抽屉 + 底部全局命令栏"""

    return_to_login = Signal()

    STYLE_PRESETS = {
        "科技蓝": "styles/theme.qss",
        "暗夜黑": "styles/theme_dark.qss",
        "工业灰": "styles/theme_gray.qss",
        "活力橙": "styles/theme_orange.qss",
        "清新绿": "styles/theme_green.qss",
        "明亮": "styles/theme_light.qss",
        "跟随系统": None,
    }

    DEFAULT_STYLE = "科技蓝"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Codroid 机器人控制终端")
        self.resize(1280, 800)

        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._reset_home_on_next_show = True

        # 加载 QSS
        saved_style = self._settings.value(SETTINGS_KEY_STYLE, self.DEFAULT_STYLE)
        self._apply_style(saved_style)

        # 加载语言
        saved_lang = self._settings.value("ui/language", "zh")
        I18nManager.instance().set_lang(saved_lang)

        # 菜单栏
        self._setup_menu_bar()

        # 中央区域
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶部标签栏
        self._top_tab = TopTabBar()
        root.addWidget(self._top_tab)

        # 页面路由区域
        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("pageStackPlaceholder")

        self._page_router = PageRouter(self._page_stack)
        self._top_tab.tab_clicked.connect(self._page_router.navigate)

        root.addWidget(self._page_stack, stretch=1)

        # 左侧运动控制抽屉
        #
        # parent 挂 MainWindow：
        #   避免被 QStackedWidget 当前页面盖住，导致“运动”按钮点不动。
        #
        # 位置按 page_stack 映射到 MainWindow 的坐标来算：
        #   避免覆盖顶部标签栏和底部命令栏。
        self._drawer = RobotControlDrawer(parent=self)
        self._drawer.hide()

        # 底部全局命令栏
        self._command_bar = GlobalCommandBar()
        root.addWidget(self._command_bar)

        # 状态栏
        self._status_bar = StatusBar()
        self.setStatusBar(self._status_bar)

        # 初始化首页
        self.reset_to_home()

        # 页面切换后重新定位并抬高抽屉，避免被当前页面盖住
        self._page_stack.currentChanged.connect(
            lambda _: self._schedule_drawer_position()
        )

        # 等 Qt 布局完成后再定位抽屉
        QTimer.singleShot(0, self._init_drawer_position)
        QTimer.singleShot(100, self._position_drawer)

    # ════════════════ Qt events ════════════════

    def showEvent(self, event):
        super().showEvent(event)

        # 登录成功切到主界面时，自动回到首页
        if self._reset_home_on_next_show:
            self.reset_to_home()
            self._reset_home_on_next_show = False

        self._schedule_drawer_position()

    def hideEvent(self, event):
        super().hideEvent(event)

        # 从主界面返回登录页后，下次再次登录进来自动回首页
        self._reset_home_on_next_show = True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_drawer_position()

    # ════════════════ 首页 / 抽屉定位 ════════════════

    def reset_to_home(self):
        """切换到首页。登录成功进入主界面时调用。"""
        if not PAGE_REGISTRY:
            return

        home_spec = PAGE_REGISTRY[0]

        try:
            self._page_router.navigate(home_spec)
        except Exception:
            pass

        try:
            self._top_tab.set_active(home_spec.key)
        except Exception:
            pass

        self._schedule_drawer_position()

    def _init_drawer_position(self):
        """首次显示时定位抽屉。"""
        self._drawer.show()
        self._drawer.raise_()
        self._schedule_drawer_position()

    def _schedule_drawer_position(self):
        """
        延迟多次定位，解决窗口刚显示时布局尚未稳定的问题。
        首次启动时 page_stack 的坐标可能还没最终落位，所以需要在事件循环后校正。
        """
        if not hasattr(self, "_drawer"):
            return

        QTimer.singleShot(0, self._position_drawer)
        QTimer.singleShot(30, self._position_drawer)
        QTimer.singleShot(100, self._position_drawer)

    def _position_drawer(self):
        """把左侧抽屉定位到 page_stack 区域内。"""
        if not hasattr(self, "_drawer"):
            return

        if not hasattr(self, "_page_stack"):
            return

        # 把 page_stack 左上角从 page_stack 坐标系转换到 MainWindow 坐标系
        pos = self._page_stack.mapTo(self, QPoint(0, 0))

        width = (
            self._drawer.expanded_width()
            if self._drawer.is_expanded()
            else self._drawer.collapsed_width()
        )

        height = max(1, self._page_stack.height())

        self._drawer.setGeometry(
            pos.x(),
            pos.y(),
            width,
            height,
        )
        self._drawer.raise_()

    # ════════════════ 对外接口：状态栏 / 抽屉 / 命令栏 ════════════════

    @property
    def drawer(self) -> RobotControlDrawer:
        return self._drawer

    @property
    def command_bar(self) -> GlobalCommandBar:
        return self._command_bar

    @property
    def status_bar(self) -> StatusBar:
        return self._status_bar

    def set_robot_model(self, text: str):
        """设置抽屉中的机器人型号显示。"""
        self._drawer.set_robot_model(text)

    def update_joint_display(self, joint_deg: list):
        """更新抽屉中的关节角显示。"""
        self._drawer.update_joint_display(joint_deg)

    def update_tcp_display(self, x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg):
        """更新抽屉中的 TCP 位姿显示。"""
        self._drawer.update_tcp_display(
            x_mm,
            y_mm,
            z_mm,
            rx_deg,
            ry_deg,
            rz_deg,
        )

    # ════════════════ 菜单 / 样式 ════════════════

    def _setup_menu_bar(self):
        self._i18n = I18nManager.instance()
        self._i18n.language_changed.connect(self._on_language_changed)
        menu_bar = self.menuBar()

        # 连接
        self._conn_menu = menu_bar.addMenu(tr("menu_connection"))
        self._login_action = QAction(tr("menu_login"), self)
        self._login_action.triggered.connect(self.return_to_login.emit)
        self._conn_menu.addAction(self._login_action)

        # 设置
        self._settings_menu = menu_bar.addMenu(tr("menu_settings"))
        lang_menu = self._settings_menu.addMenu(tr("menu_language"))
        self._lang_zh_action = QAction(tr("menu_lang_zh"), self)
        self._lang_zh_action.triggered.connect(lambda: self._on_lang("zh"))
        lang_menu.addAction(self._lang_zh_action)
        self._lang_en_action = QAction(tr("menu_lang_en"), self)
        self._lang_en_action.triggered.connect(lambda: self._on_lang("en"))
        lang_menu.addAction(self._lang_en_action)

        # 样式
        self._style_menu = menu_bar.addMenu(tr("menu_style"))
        self._style_actions = {}
        for name in self.STYLE_PRESETS:
            action = QAction(name, self)
            action.triggered.connect(self._make_style_handler(name))
            self._style_menu.addAction(action)
            self._style_actions[name] = action

        # 帮助
        self._help_menu = menu_bar.addMenu(tr("menu_help"))
        self._about_action = QAction(tr("menu_about"), self)
        self._about_action.triggered.connect(self._show_about)
        self._help_menu.addAction(self._about_action)

    def _on_lang(self, lang: str):
        self._i18n.set_lang(lang)
        self._settings.setValue("ui/language", lang)

    def _on_language_changed(self, lang: str):
        """刷新菜单栏文本"""
        self._conn_menu.setTitle(tr("menu_connection"))
        self._login_action.setText(tr("menu_login"))
        self._settings_menu.setTitle(tr("menu_settings"))
        self._style_menu.setTitle(tr("menu_style"))
        self._help_menu.setTitle(tr("menu_help"))
        self._about_action.setText(tr("menu_about"))
        self._lang_zh_action.setText(tr("menu_lang_zh"))
        self._lang_en_action.setText(tr("menu_lang_en"))
        self._login_action.setText(tr("menu_return_login") if self._page_router else tr("menu_login"))

    def _make_style_handler(self, name: str):
        def handler():
            self._apply_style(name)
            self._settings.setValue(SETTINGS_KEY_STYLE, name)

        return handler

    def _apply_style(self, name: str):
        path = self.STYLE_PRESETS.get(name)
        if path is None:
            self.setStyleSheet("")
        else:
            self._load_qss(path)

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 Codroid 机器人控制终端",
            f"Codroid 机器人控制终端\n版本: {VERSION}\n\n"
            "基于 PySide6 开发\n"
            "Codroid 协作机器人远程控制 UI",
        )

    def _load_qss(self, relative_path: str):
        qss_path = os.path.join(os.path.dirname(__file__), relative_path)
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())