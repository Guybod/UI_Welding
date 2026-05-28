import logging
import os

from PySide6.QtWidgets import (
    QMainWindow, QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QMessageBox,
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QSettings, Signal, QTimer

from app.i18n import I18nManager, tr
from app.widgets.status_bar import StatusBar
from app.widgets.top_tab_bar import TopTabBar
from app.widgets.global_command_bar import GlobalCommandBar
from app.widgets.robot_control_drawer import RobotControlDrawer
from app.page_router import PageRouter
from app.page_registry import PAGE_REGISTRY
from app.help_manuals import welding_manual_html, upload_manual_html
from app.widgets.help_manual_dialog import HelpManualDialog


VERSION = "v2.0.0"
SETTINGS_ORG = "Codroid"
SETTINGS_APP = "RobotUI"
SETTINGS_KEY_STYLE = "ui/style"

# reset_to_home 仅允许以下 reason（显式调用，禁止 show/hide 自动触发）
_RESET_HOME_REASONS = frozenset({"app_init", "user_click_home", "logout"})
_log = logging.getLogger("codroid")


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
        self._curr_user_page: str = "home"

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

        # 中间：左侧抽屉 + 页面区（并排布局，避免抽屉盖住首页）
        self._content_row = QWidget()
        content_layout = QHBoxLayout(self._content_row)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._drawer = RobotControlDrawer(parent=self._content_row)
        self._page_stack = QStackedWidget()
        self._page_stack.setObjectName("pageStackPlaceholder")

        content_layout.addWidget(self._drawer)
        content_layout.addWidget(self._page_stack, stretch=1)

        self._page_router = PageRouter(self._page_stack)
        self._top_tab.tab_clicked.connect(self._on_user_tab_clicked)

        root.addWidget(self._content_row, stretch=1)

        # 底部全局命令栏
        self._command_bar = GlobalCommandBar()
        root.addWidget(self._command_bar)

        # 状态栏
        self._status_bar = StatusBar()
        self.setStatusBar(self._status_bar)

        # 初始化首页（仅此一处 app_init）
        self.reset_to_home(reason="app_init")

        self._page_stack.currentChanged.connect(self._on_page_changed)

    # ════════════════ 页面导航 ════════════════

    def _on_user_tab_clicked(self, spec):
        home_key = PAGE_REGISTRY[0].key if PAGE_REGISTRY else "home"
        if spec.key == home_key:
            self.reset_to_home(reason="user_click_home")
        else:
            self._page_router.navigate(spec)
            try:
                self._top_tab.set_active(spec.key)
            except Exception:
                pass
        self._curr_user_page = spec.key

    def reset_to_home(self, reason: str = ""):
        """切换到首页。仅允许 app_init / user_click_home / logout。"""
        if reason not in _RESET_HOME_REASONS:
            _log.warning(
                "[MainWindow] reset_to_home rejected: invalid reason=%r "
                "(allowed: %s)",
                reason,
                ", ".join(sorted(_RESET_HOME_REASONS)),
            )
            return
        if not PAGE_REGISTRY:
            return
        _log.info("[MainWindow] reset_to_home: reason=%s", reason)
        home_spec = PAGE_REGISTRY[0]
        try:
            self._page_router.navigate(home_spec)
        except Exception:
            pass
        try:
            self._top_tab.set_active(home_spec.key)
        except Exception:
            pass
        self._curr_user_page = home_spec.key
        self._refresh_home_preview()

    def _on_page_changed(self, _index: int) -> None:
        self._refresh_home_preview()

    def _refresh_home_preview(self) -> None:
        home = self._page_router.get_cached_page("home")
        if home is not None and hasattr(home, "on_enter"):
            home.on_enter()

    # ════════════════ Qt events ════════════════

    def changeEvent(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                _log.debug("[MainWindow] window minimized (no page change)")
            elif self.isVisible():
                _log.debug("[MainWindow] window restored (no page change)")
        super().changeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._refresh_home_preview)

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

    def set_robot_model(self, text: str, robot_type: str = ""):
        """同步抽屉与首页的机器人型号与 3D 模型。"""
        self._drawer.set_robot_model(text, robot_type=robot_type)
        home = self._page_router.get_cached_page("home")
        if home is not None:
            home.set_robot_model(text, robot_type=robot_type)

    def update_joint_display(
        self,
        joint_deg: list,
        joint_rad: list | None = None,
        *,
        drive_model: bool = True,
    ):
        """同步抽屉与首页的关节角显示；3D 仅当 drive_model 且提供 joint_rad 时更新。"""
        self._drawer.update_joint_display(
            joint_deg, joint_rad=joint_rad, drive_model=drive_model
        )
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_joint_display", None)
            if callable(updater):
                updater(joint_deg, joint_rad=joint_rad, drive_model=drive_model)

    def update_tcp_display(self, x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg):
        """更新抽屉与首页的 TCP 位姿显示。"""
        self._drawer.update_tcp_display(
            x_mm,
            y_mm,
            z_mm,
            rx_deg,
            ry_deg,
            rz_deg,
        )
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_tcp_display", None)
            if callable(updater):
                updater(x_mm, y_mm, z_mm, rx_deg, ry_deg, rz_deg)

    def update_home_connection(self, connected: bool) -> None:
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_connection", None)
            if callable(updater):
                updater(connected)

    def update_home_cri(self, active: bool) -> None:
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_cri_status", None)
            if callable(updater):
                updater(active)

    def update_home_cri_ui_mode(self, mode: str) -> None:
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_cri_ui_mode", None)
            if callable(updater):
                updater(mode)

    def update_home_runtime(
        self,
        *,
        enabled: bool | None = None,
        moving: bool | None = None,
        emergency: bool | None = None,
        mode_text: str | None = None,
        state_text: str | None = None,
    ) -> None:
        home = self._page_router.get_cached_page("home")
        if home is None:
            return
        flags = getattr(home, "update_runtime_flags", None)
        if callable(flags) and any(
            v is not None for v in (enabled, moving, emergency)
        ):
            flags(enabled=enabled, moving=moving, emergency=emergency)
        mode_state = getattr(home, "update_mode_state", None)
        if callable(mode_state) and (mode_text is not None or state_text is not None):
            mode_state(mode_text or "", state_text or "")

    def update_coordinates(self, world_text: str, tool_text: str) -> None:
        self._drawer.set_world_coordinate(world_text)
        self._drawer.set_tool_coordinate(tool_text)
        home = self._page_router.get_cached_page("home")
        if home is not None:
            updater = getattr(home, "update_coordinates", None)
            if callable(updater):
                updater(world_text, tool_text)

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
        self._help_welding_action = QAction(tr("menu_help_welding"), self)
        self._help_welding_action.triggered.connect(self._show_welding_help)
        self._help_menu.addAction(self._help_welding_action)
        self._help_upload_action = QAction(tr("menu_help_upload"), self)
        self._help_upload_action.triggered.connect(self._show_upload_help)
        self._help_menu.addAction(self._help_upload_action)
        self._help_menu.addSeparator()
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
        self._help_welding_action.setText(tr("menu_help_welding"))
        self._help_upload_action.setText(tr("menu_help_upload"))
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
            QApplication.instance().setStyleSheet("")
        else:
            self._load_qss(path)

    def _show_welding_help(self):
        dlg = HelpManualDialog(tr("menu_help_welding"), welding_manual_html(), self)
        dlg.exec()

    def _show_upload_help(self):
        dlg = HelpManualDialog(tr("menu_help_upload"), upload_manual_html(), self)
        dlg.exec()

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
                QApplication.instance().setStyleSheet(f.read())

    def closeEvent(self, event):
        self._page_router.persist_all_page_settings()
        super().closeEvent(event)