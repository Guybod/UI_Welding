import sys
from PySide6.QtWidgets import QApplication

from network.connection_manager import ConnectionManager
from services.cri_service import CriService
from services.robot_service import RobotService
from app.widgets.node_editor.node_editor_widget import NodeEditorWidget
from app.bootstrap import create_app_stack
from app.signal_binder import bind_all
from app.service_provider import ServiceProvider


def main():
    app = QApplication(sys.argv)

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
                      lambda e: print(f"[NodeEditor] {ty} 失败: {e}")),
        )

    NodeEditorWidget.set_global_send_callback(_send_tcp)

    # 4. 服务注入到页面路由（所有页面通过 sp.cm / sp.cri 访问后端）
    sp = ServiceProvider(cm, cri_svc)
    main_win._page_router.set_service_provider(sp)

    # 5. 所有 UI ↔ Service 信号连接
    bind_all(cm, cri_svc, login, main_win, stack)

    # 6. 退出清理
    def cleanup():
        cri_svc.stop()
        cm.disconnect()

    app.aboutToQuit.connect(cleanup)

    stack.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
