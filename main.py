import sys

from PySide6.QtGui import QFont, QSurfaceFormat
from PySide6.QtWidgets import QApplication


def _configure_opengl() -> None:
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setVersion(2, 1)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
    QSurfaceFormat.setDefaultFormat(fmt)

from core.logger import log, setup_logger

setup_logger("codroid")

from network.connection_manager import ConnectionManager
from services.cri_service import CriService
from services.robot_service import RobotService
from app.widgets.node_editor.node_editor_widget import NodeEditorWidget
from app.bootstrap import create_app_stack
from app.signal_binder import bind_all
from app.service_provider import ServiceProvider


def main():
    import platform

    from PySide6 import __version__ as pyside_version

    _configure_opengl()
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))  # 固定默认字体避免 pointSize=-1 警告
    log.info(
        "[Main] application start python=%s pyside6=%s platform=%s",
        platform.python_version(),
        pyside_version,
        platform.platform(),
    )

    # 0. 全局滚轮防护（禁止 spinbox/combobox 通过滚轮误改值）
    from app.utils.wheel_guard import install_wheel_guard
    install_wheel_guard(app)

    # 1. 窗口
    stack, login, main_win = create_app_stack()

    # 2. 后端服务
    cm = ConnectionManager()
    cri_svc = CriService(cm)
    _robot_svc = RobotService(cm)

    # 3. 节点编辑器全局回调注入
    def _send_tcp(ty, db, on_response=None, on_error=None):
        cm.send_call(
            ty, db,
            on_response=(on_response if on_response else lambda r: None),
            on_error=(on_error if on_error else
                      lambda e, _ty=ty: log.warning(
                          "[Main] NodeEditor send_tcp failed ty=%s: %s", _ty, e)),
        )

    NodeEditorWidget.set_global_send_callback(_send_tcp)

    # 4. 服务注入到页面路由（所有页面通过 sp.cm / sp.cri 访问后端）
    sp = ServiceProvider(cm, cri_svc)
    main_win._page_router.set_service_provider(sp)

    # 5. 所有 UI ↔ Service 信号连接
    binder_state = bind_all(cm, cri_svc, login, main_win, stack)

    # 6. 退出清理
    def cleanup():
        log.info("[Main] aboutToQuit cleanup start")
        try:
            cri_svc.stop()
        except Exception as exc:
            log.warning("[Main] cleanup cri_svc.stop failed: %s", exc)
        try:
            cm.disconnect()
        except Exception as exc:
            log.warning("[Main] cleanup cm.disconnect failed: %s", exc)
        stop_motion = binder_state.get("motion_cleanup")
        if stop_motion:
            try:
                stop_motion()
            except Exception as exc:
                log.warning("[Main] cleanup motion_cleanup failed: %s", exc)
        log.info("[Main] aboutToQuit cleanup done")

    app.aboutToQuit.connect(cleanup)

    stack.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
