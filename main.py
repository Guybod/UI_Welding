import sys
from PySide6.QtWidgets import QApplication, QStackedWidget, QMessageBox
from PySide6.QtCore import QTimer

from app.pages.login_page import LoginPage
from app.main_window import MainWindow
from network.connection_manager import ConnectionManager
from services.robot_service import RobotService
from services.cri_service import CriService
from core.robot_model_config import get_model_config
from core.unit_converter import rad_list_to_deg, m_to_mm, rad_to_deg
from services.robot_realtime_state import RobotRealtimeState


def main():
    app = QApplication(sys.argv)

    stack = QStackedWidget()
    stack.setWindowTitle("Codroid 机器人控制终端")
    stack.resize(1280, 800)

    login = LoginPage()
    main_win = MainWindow()

    stack.addWidget(login)
    stack.addWidget(main_win)
    stack.setCurrentWidget(login)

    cm = ConnectionManager()
    robot_svc = RobotService(cm)
    cri_svc = CriService(cm)

    # ── login → main ──
    _cri_config = None

    def on_connect(config):
        nonlocal _cri_config
        _cri_config = config
        login.set_status("连接中...")
        cm.connect_to_robot(config)

    def on_return_to_login():
        cm.disconnect()
        main_win._status_bar.set_connection_status("未连接")
        main_win._drawer.set_jog_enabled(False)
        login.set_enabled(True)
        login.set_status("准备连接")
        stack.setCurrentWidget(login)

    login.connect_requested.connect(on_connect)
    main_win.return_to_login.connect(on_return_to_login)

    # ── connection success → switch to main ──
    def on_connected_state(state: str):
        if state == "connected":
            stack.setCurrentWidget(main_win)
        main_win._status_bar.set_connection_status(state)

    # ── 连接状态 → 按钮启用/禁用 ──
    def on_connection_changed(state: str):
        if state == "connected":
            main_win._command_bar.set_all_enabled(True)
            main_win._drawer.set_jog_enabled(True)
        else:
            main_win._command_bar.set_all_enabled(False)
            main_win._drawer.set_jog_enabled(False)

    cm.connection_state_changed.connect(on_connected_state)
    cm.connection_state_changed.connect(on_connection_changed)

    # ── connection failure ──
    def on_connection_failed(error_msg: str):
        QMessageBox.critical(login, "连接失败", f"无法连接到机器人:\n{error_msg}")
        login.set_status("未连接")
        login.set_enabled(True)

    cm.connection_failed.connect(on_connection_failed)

    # ── subscribe after connected ──
    _robot_type_received = False

    def on_connected(state: str):
        if state != "connected":
            return

        def _do_subscribe():
            subs = [
                ("publish/RobotStatus", _on_robot_status),
                ("publish/RobotPosture", _on_robot_posture),
                ("publish/ProjectState", _on_project_state),
                ("publish/Error", _on_error, 500),
                ("publish/Log", _on_log),
            ]
            for i, item in enumerate(subs):
                topic, cb = item[0], item[1]
                tc = item[2] if len(item) > 2 else 0
                QTimer.singleShot(
                    i * 100,
                    lambda t=topic, c=cb, ms=tc: cm.send_subscribe(
                        t,
                        c,
                        interval_ms=ms,
                    ),
                )

        def _do_remote():
            cm.send_call(
                "Robot/toRemote",
                {},
                on_response=lambda db: QTimer.singleShot(100, _do_subscribe),
                on_error=lambda e: QTimer.singleShot(100, _do_subscribe),
            )

        cm.send_call(
            "Robot/toAuto",
            {},
            on_response=lambda db: QTimer.singleShot(100, _do_remote),
            on_error=lambda e: QTimer.singleShot(100, _do_remote),
        )

        # 连接后下发默认速度 70%
        QTimer.singleShot(
            2000,
            lambda: cm.send_call(
                "Robot/setManualMoveRate",
                70,
                on_response=lambda d: cm.send_call(
                    "Robot/setAutoMoveRate",
                    70,
                    on_response=lambda d2: None,
                    on_error=lambda e2: print(f"[UI] 设置自动速度失败: {e2}"),
                ),
                on_error=lambda e: print(f"[UI] 设置手动速度失败: {e}"),
            ),
        )

    cm.connection_state_changed.connect(on_connected)

    def _on_robot_status(db: dict):
        nonlocal _robot_type_received
        robot_type = db.get("type", "")
        mode = db.get("mode", 0)
        state_num = db.get("state", 0)

        if robot_type and not _robot_type_received:
            _robot_type_received = True
            cfg = get_model_config(robot_type)
            main_win._drawer.set_robot_model(f"{cfg.display_name} ({robot_type})")

        mode_names = {
            0: "手动",
            1: "自动",
            2: "远程",
        }
        state_names = {
            0: "未使能",
            1: "使能中",
            2: "空闲",
            3: "点动中",
            4: "RunTo",
            5: "拖动中",
        }

        main_win._status_bar.set_connection_status(
            f"已连接 | 型号: {robot_type} | "
            f"{mode_names.get(mode, str(mode))} | "
            f"{state_names.get(state_num, str(state_num))}"
        )
        main_win._command_bar.set_mode(mode)
        main_win._command_bar.set_enable_state(state_num != 0)
        main_win._command_bar.set_simulation(db.get("isSimulation", False))
        main_win._drawer.set_world_coordinate(f"坐标系{db.get('CoordinateId', 0)}")
        main_win._drawer.set_tool_coordinate(f"工具{db.get('ToolId', 0)}")

        moving = db.get("isMoving", False)
        main_win._command_bar.set_motion_paused(not moving)

    def _on_project_state(db: dict):
        state = db.get("state", 0)
        main_win._command_bar.set_project_paused(state == 3)

    def _on_robot_posture(db: dict):
        joint = db.get("joint", [])
        if joint:
            main_win._drawer.update_joint_display(joint)

        end = db.get("end", {})
        if end:
            main_win._drawer.update_tcp_display(
                end.get("x", 0),
                end.get("y", 0),
                end.get("z", 0),
                end.get("a", 0),
                end.get("b", 0),
                end.get("c", 0),
            )

    _error_dialog = None

    def _on_error(db):
        nonlocal _error_dialog
        if not db:
            return

        if _error_dialog is None or not _error_dialog.isVisible():
            from app.widgets.global_command_bar import ErrorDialog

            _error_dialog = ErrorDialog([str(db)], main_win)
            _error_dialog.clear_requested.connect(
                lambda: cm.send_call(
                    "System/clearError",
                    {},
                    on_response=lambda d: None,
                    on_error=lambda e: print(f"[UI] 清错失败: {e}"),
                )
            )
            _error_dialog.show()

    def _on_log(db: dict):
        pass

    # ── 控制按钮 → send_call ──

    def _simple_call(ty: str):
        cm.send_call(
            ty,
            {},
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] {ty} 失败: {e}"),
        )

    main_win._command_bar.switch_on_toggled.connect(
        lambda on: _simple_call("Robot/switchOn" if on else "Robot/switchOff")
    )
    main_win._command_bar.mode_changed.connect(
        lambda m: _simple_call(["Robot/toManual", "Robot/toAuto", "Robot/toRemote"][m])
    )
    main_win._command_bar.simulation_toggled.connect(
        lambda sim: _simple_call("Robot/toSimulation" if sim else "Robot/toActual")
    )
    main_win._command_bar.stop_move.connect(lambda: _simple_call("Robot/stopMove"))
    main_win._command_bar.pause_move.connect(lambda: _simple_call("Robot/pause"))
    main_win._command_bar.resume_move.connect(lambda: _simple_call("Robot/resume"))

    main_win._command_bar.project_start.connect(
        lambda: cm.send_call(
            "project/runByIndex",
            1,
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] 启动工程失败: {e}"),
        )
    )
    main_win._command_bar.project_stop.connect(lambda: _simple_call("project/stop"))
    main_win._command_bar.project_pause.connect(lambda: _simple_call("project/pause"))
    main_win._command_bar.project_resume.connect(lambda: _simple_call("project/resume"))

    # ── 抽屉 Jog：按下开始，松开停止 ──

    _jog_heartbeat_timer = QTimer()
    _jog_heartbeat_timer.setInterval(500)
    _jog_heartbeat_timer.timeout.connect(lambda: _simple_call("Robot/jogHeartbeat"))

    def _on_jog_pressed(mode: int, index: int, sign: int):
        speed = main_win._drawer.speed_rate() / 100.0
        cm.send_call(
            "Robot/jog",
            {
                "mode": mode,
                "speed": sign * speed,
                "index": index + 1,
                "coorType": 0,
                "coorId": 0,
            },
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] jog 失败: {e}"),
        )
        _jog_heartbeat_timer.start()

    def _on_jog_stop():
        _jog_heartbeat_timer.stop()
        cm.send_call(
            "Robot/stopJog",
            {},
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] stopJog 失败: {e}"),
        )

    main_win._drawer.jog_pressed.connect(_on_jog_pressed)
    main_win._drawer.jog_released.connect(_on_jog_stop)

    # ── moveTo 预设点：按下开始，松开立即停止 ──

    _moveto_heartbeat_timer = QTimer()
    _moveto_heartbeat_timer.setInterval(500)

    def _send_moveto_heartbeat():
        cm.send_call(
            "Robot/moveToHeartbeat",
            {},
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] moveToHeartbeat 失败: {e}"),
        )

    _moveto_heartbeat_timer.timeout.connect(_send_moveto_heartbeat)

    _moveto_active = False
    _moveto_generation = 0

    def _send_moveto_stop():
        nonlocal _moveto_active, _moveto_generation

        if not _moveto_active:
            return

        _moveto_active = False
        _moveto_generation += 1
        _moveto_heartbeat_timer.stop()

        print("[UI] moveTo released: stop type=-1")
        cm.send_call(
            "Robot/moveTo",
            {"type": -1},
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] moveTo 停止失败: {e}"),
        )

    def _on_moveto_start_error(e):
        nonlocal _moveto_active, _moveto_generation

        _moveto_active = False
        _moveto_generation += 1
        _moveto_heartbeat_timer.stop()
        print(f"[UI] moveTo 启动失败: {e}")

    def _on_moveto_pressed(move_type: int):
        nonlocal _moveto_active, _moveto_generation

        # 如果正在 RunTo，先停止旧的
        if _moveto_active:
            _send_moveto_stop()

        _moveto_active = True
        _moveto_generation += 1
        current_generation = _moveto_generation

        print(f"[UI] moveTo pressed: type={move_type}")
        cm.send_call(
            "Robot/moveTo",
            {"type": move_type},
            on_response=lambda d, gen=current_generation: (
                _moveto_heartbeat_timer.start()
                if _moveto_active and gen == _moveto_generation
                else None
            ),
            on_error=_on_moveto_start_error,
        )

    def _on_moveto_released():
        _send_moveto_stop()

    main_win._drawer.moveto_pressed.connect(_on_moveto_pressed)
    main_win._drawer.moveto_released.connect(_on_moveto_released)

    # 停止运动按钮也强制停止 moveTo / Jog
    main_win._command_bar.stop_move.connect(_send_moveto_stop)
    main_win._command_bar.stop_move.connect(lambda: _jog_heartbeat_timer.stop())

    # ── 速度条：同时设置手动速度和自动速度 ──

    def _on_speed_changed(rate: int):
        print(f"[UI] speed changed: {rate}%")
        cm.send_call(
            "Robot/setManualMoveRate",
            rate,
            on_response=lambda d: None,
            on_error=lambda e: print(f"[UI] 设置手动速度失败: {e}"),
        )
        QTimer.singleShot(
            100,
            lambda: cm.send_call(
                "Robot/setAutoMoveRate",
                rate,
                on_response=lambda d: None,
                on_error=lambda e: print(f"[UI] 设置自动速度失败: {e}"),
            ),
        )

    main_win._drawer.speed_rate_changed.connect(_on_speed_changed)

    # ── CRI 实时数据 → 抽屉 ──

    def _on_cri_frame(frame: dict):
        # 更新全局实时状态缓存
        RobotRealtimeState.instance().update_from_cri_frame(frame)

        joint_rad = frame.get("joint_position", [])
        if joint_rad:
            main_win._drawer.update_joint_display(rad_list_to_deg(joint_rad))

        main_win._drawer.update_tcp_display(
            m_to_mm(frame.get("tcp_x", 0)),
            m_to_mm(frame.get("tcp_y", 0)),
            m_to_mm(frame.get("tcp_z", 0)),
            rad_to_deg(frame.get("tcp_rx", 0)),
            rad_to_deg(frame.get("tcp_ry", 0)),
            rad_to_deg(frame.get("tcp_rz", 0)),
        )

    cri_svc.cri_frame_received.connect(_on_cri_frame)

    # ── 自动启动 CRI ──

    def _auto_start_cri(state: str):
        nonlocal _cri_config
        if state == "connected" and _cri_config:
            QTimer.singleShot(3000, lambda: cri_svc.start(_cri_config))

    cm.connection_state_changed.connect(_auto_start_cri)

    # ── 退出清理 ──

    def cleanup():
        _jog_heartbeat_timer.stop()
        _moveto_heartbeat_timer.stop()
        cri_svc.stop()
        cm.disconnect()

    app.aboutToQuit.connect(cleanup)

    stack.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()