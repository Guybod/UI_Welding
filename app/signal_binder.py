"""把所有 UI Signal ↔ Service 的连线集中管理。main.py 只调用 bind_all() 一次。

每个 _bind_xxx() 是独立函数，不共享闭包变量。
跨函数共享的状态通过 state dict 传递。
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from core.logger import log
from core.robot_model_config import get_model_config
from core.unit_converter import deg_list_to_rad, rad_list_to_deg, m_to_mm, rad_to_deg
from services.cri_service import CriService
from services.robot_realtime_state import RobotRealtimeState


def _cri_pose_active(state: dict) -> bool:
    """CRI 已启用且收到过有效关节帧时，位姿以 CRI 为准。"""
    cri_svc = state.get("cri_svc")
    if not isinstance(cri_svc, CriService) or not cri_svc.is_enabled:
        return False
    return RobotRealtimeState.instance().is_valid()


def _bind_login_flow(cm, login, main_win, stack, state):
    """Login → Main → Login 三窗口切换"""
    def on_connect(config):
        state["cri_config"] = config
        login.set_status("连接中...")
        log.info("[Login] user connect request %s:9001", config.robot_ip)
        cm.connect_to_robot(config)

    def on_return_to_login():
        log.info("[Login] return to login / logout cleanup")
        stop = state.get("stop_all_motion")
        if stop:
            stop()
        main_win.reset_to_home(reason="logout")
        cm.disconnect()
        main_win._status_bar.set_connection_status("未连接")
        main_win.update_home_connection(False)
        main_win.update_home_cri(False)
        main_win._drawer.set_jog_enabled(False)
        login.set_enabled(True)
        login.set_status("准备连接")
        stack.setCurrentWidget(login)

    login.connect_requested.connect(on_connect)
    main_win.return_to_login.connect(on_return_to_login)


def _bind_connection_state(cm, login, main_win, stack, state):
    """连接成功→切主窗口；连接失败→弹错误"""
    def on_connected_state(state_str: str):
        if state_str == "connected":
            stack.setCurrentWidget(main_win)
        main_win._status_bar.set_connection_status(state_str)

    def on_connection_changed(state_str: str):
        log.info("[Login] connection_state_changed state=%s", state_str)
        connected = state_str == "connected"
        main_win.update_home_connection(connected)
        if connected:
            main_win._command_bar.set_all_enabled(True)
            main_win._drawer.set_jog_enabled(True)
        else:
            stop = state.get("stop_all_motion")
            if stop:
                stop()
            main_win._command_bar.set_all_enabled(False)
            main_win._drawer.set_jog_enabled(False)
            main_win.update_home_cri(False)

    def on_connection_failed(error_msg: str):
        QMessageBox.critical(login, "连接失败",
                             f"无法连接到机器人:\n{error_msg}")
        login.set_status("未连接")
        login.set_enabled(True)

    cm.connection_state_changed.connect(on_connected_state)
    cm.connection_state_changed.connect(on_connection_changed)
    cm.connection_failed.connect(on_connection_failed)


def _bind_subscriptions(cm, cri_svc, main_win, state):
    """连接成功后：toAuto→toRemote→订阅 5 个 topic→默认速度 70%"""
    _last_robot_type = [""]
    _last_robot_mode = [None]

    def on_connected(sub_state: str):
        if sub_state != "connected":
            return

        def _do_subscribe():
            subs = [
                ("publish/RobotStatus", _on_robot_status),
                ("publish/RobotPosture", _on_robot_posture),
                ("publish/ProjectState", _on_project_state),
                ("publish/Error", _on_error, 500),
                ("publish/Log", _on_log),
            ]
            log.info(
                "[Login] subscriptions: %s",
                ", ".join(item[0] for item in subs),
            )
            for i, item in enumerate(subs):
                topic, cb = item[0], item[1]
                tc = item[2] if len(item) > 2 else 0
                QTimer.singleShot(
                    i * 100,
                    lambda t=topic, c=cb, ms=tc: cm.send_subscribe(t, c, interval_ms=ms),
                )

        def _do_remote():
            log.info("[Login] Robot/toRemote")
            cm.send_call(
                "Robot/toRemote", {},
                on_response=lambda db: QTimer.singleShot(100, _do_subscribe),
                on_error=lambda e: QTimer.singleShot(100, _do_subscribe),
            )

        log.info("[Login] Robot/toAuto")
        cm.send_call(
            "Robot/toAuto", {},
            on_response=lambda db: QTimer.singleShot(100, _do_remote),
            on_error=lambda e: QTimer.singleShot(100, _do_remote),
        )

        # 连接后下发默认速度 70%
        QTimer.singleShot(2000, lambda: cm.send_call(
            "Robot/setManualMoveRate", 70,
            on_response=lambda d: cm.send_call(
                "Robot/setAutoMoveRate", 70,
                on_response=lambda d2: None,
                on_error=lambda e2: log.info(f"[UI] 设置自动速度失败: {e2}"),
            ),
            on_error=lambda e: log.info(f"[UI] 设置手动速度失败: {e}"),
        ))

    def _on_robot_status(db: dict):
        RobotRealtimeState.instance().update_robot_status(db)
        robot_type = db.get("type", "")
        mode = db.get("mode", 0)
        state_num = db.get("state", 0)

        if robot_type and robot_type != _last_robot_type[0]:
            _last_robot_type[0] = robot_type
            log.info("[Login] robot_type changed: %s", robot_type)
            cfg = get_model_config(robot_type)
            main_win.set_robot_model(
                f"{cfg.display_name} ({robot_type})", robot_type=robot_type
            )

        mode_names = {0: "手动", 1: "自动", 2: "远程"}
        state_names = {
            0: "未使能", 1: "使能中", 2: "空闲",
            3: "点动中", 4: "RunTo", 5: "拖动中",
        }
        main_win._status_bar.set_connection_status(
            f"已连接 | 型号: {robot_type} | "
            f"{mode_names.get(mode, str(mode))} | "
            f"{state_names.get(state_num, str(state_num))}"
        )
        main_win._command_bar.set_mode(mode)
        if _last_robot_mode[0] != mode:
            _last_robot_mode[0] = mode
            main_win._page_router.notify_robot_mode(mode)
        main_win._command_bar.set_enable_state(state_num != 0)
        main_win._command_bar.set_simulation(db.get("isSimulation", False))
        main_win.update_coordinates(
            f"坐标系{db.get('CoordinateId', 0)}",
            f"工具{db.get('ToolId', 0)}",
        )
        main_win.update_home_runtime(
            mode_text=mode_names.get(mode, str(mode)),
            state_text=state_names.get(state_num, str(state_num)),
        )

        moving = db.get("isMoving", False)
        main_win._command_bar.set_motion_paused(not moving)

    def _on_project_state(db: dict):
        state_num = db.get("state", 0)
        main_win._command_bar.set_project_paused(state_num == 3)

    def _on_robot_posture(db: dict):
        """fallback：仅 CRI 未就绪时更新 3D；CRI 在线时只刷新标签，避免与笛卡尔 TCP 不一致。"""
        joint = db.get("joint", [])
        cri_ok = _cri_pose_active(state)
        if joint:
            main_win.update_joint_display(
                joint,
                joint_rad=deg_list_to_rad(joint) if not cri_ok else None,
                drive_model=not cri_ok,
            )
        end = db.get("end", {})
        if end and not cri_ok:
            main_win.update_tcp_display(
                end.get("x", 0),
                end.get("y", 0),
                end.get("z", 0),
                end.get("a", 0),
                end.get("b", 0),
                end.get("c", 0),
            )
        if not cri_ok:
            main_win.update_home_cri(False)

    _error_dialog_data = [None]

    def _on_error(db):
        if not db:
            return
        log.warning("[Login] publish/Error payload=%s", str(db)[:200])
        try:
            RobotRealtimeState.instance().set_last_error(str(db))
        except Exception:
            pass
        if _error_dialog_data[0] is None or not _error_dialog_data[0].isVisible():
            from app.widgets.global_command_bar import ErrorDialog
            _error_dialog_data[0] = ErrorDialog([str(db)], main_win)
            _error_dialog_data[0].clear_requested.connect(
                lambda: cm.send_call(
                    "System/clearError", {},
                    on_response=lambda d: None,
                    on_error=lambda e: log.info(f"[UI] 清错失败: {e}"),
                )
            )
            _error_dialog_data[0].show()

    def _on_log(db: dict):
        pass

    cm.connection_state_changed.connect(on_connected)


def _bind_command_bar(cm, main_win, state):
    """全局命令栏按钮 → send_call"""
    def _simple_call(ty: str):
        cm.send_call(ty, {}, on_response=lambda d: None,
                     on_error=lambda e: log.info(f"[UI] {ty} 失败: {e}"))

    main_win._command_bar.switch_on_toggled.connect(
        lambda on: _simple_call("Robot/switchOn" if on else "Robot/switchOff"))
    main_win._command_bar.mode_changed.connect(
        lambda m: _simple_call(["Robot/toManual", "Robot/toAuto", "Robot/toRemote"][m]))
    main_win._command_bar.simulation_toggled.connect(
        lambda sim: _simple_call("Robot/toSimulation" if sim else "Robot/toActual"))
    main_win._command_bar.stop_move.connect(lambda: _simple_call("Robot/stopMove"))
    main_win._command_bar.pause_move.connect(lambda: _simple_call("Robot/pause"))
    main_win._command_bar.resume_move.connect(lambda: _simple_call("Robot/resume"))

    main_win._command_bar.project_start.connect(
        lambda: cm.send_call("project/runByIndex", 1,
                             on_response=lambda d: None,
                             on_error=lambda e: log.info(f"[UI] 启动工程失败: {e}")))
    main_win._command_bar.project_stop.connect(lambda: _simple_call("project/stop"))
    main_win._command_bar.project_pause.connect(lambda: _simple_call("project/pause"))
    main_win._command_bar.project_resume.connect(lambda: _simple_call("project/resume"))


def _bind_jog(cm, main_win, state):
    """Jog 点动：按下开始 + 心跳，松开停止"""
    _jog_heartbeat_timer = QTimer()
    _jog_heartbeat_timer.setInterval(500)
    _jog_active = [False]

    def _send_jog_heartbeat():
        cm.send_call("Robot/jogHeartbeat", {},
                     on_response=lambda d: None,
                     on_error=lambda e: log.info(f"[UI] jogHeartbeat 失败: {e}"))

    _jog_heartbeat_timer.timeout.connect(_send_jog_heartbeat)

    def _on_jog_pressed(mode: int, index: int, sign: int):
        _jog_active[0] = True
        speed = main_win._drawer.speed_rate() / 100.0

        def _on_jog_ok(d):
            if _jog_active[0]:
                _jog_heartbeat_timer.start()

        def _on_jog_fail(e):
            _jog_active[0] = False
            _jog_heartbeat_timer.stop()
            log.info(f"[UI] jog 失败: {e}")

        cm.send_call(
            "Robot/jog",
            {"mode": mode, "speed": sign * speed, "index": index + 1,
             "coorType": 0, "coorId": 0},
            on_response=_on_jog_ok,
            on_error=_on_jog_fail,
        )

    def _on_jog_stop(*, send_tcp: bool = True):
        _jog_active[0] = False
        _jog_heartbeat_timer.stop()
        if send_tcp:
            cm.send_call("Robot/stopJog", {},
                         on_response=lambda d: None,
                         on_error=lambda e: log.info(f"[UI] stopJog 失败: {e}"))

    main_win._drawer.jog_pressed.connect(_on_jog_pressed)
    main_win._drawer.jog_released.connect(_on_jog_stop)

    state["stop_jog"] = _on_jog_stop


def _bind_moveto(cm, main_win, state):
    """MoveTo 预设点：按下开始 + 心跳，松开立即停止"""
    _moveto_heartbeat_timer = QTimer()
    _moveto_heartbeat_timer.setInterval(500)
    _moveto_active = [False]
    _moveto_generation = [0]

    def _send_moveto_heartbeat():
        cm.send_call("Robot/moveToHeartbeat", {},
                     on_response=lambda d: None,
                     on_error=lambda e: log.info(f"[UI] moveToHeartbeat 失败: {e}"))

    _moveto_heartbeat_timer.timeout.connect(_send_moveto_heartbeat)

    def _send_moveto_stop(*, send_tcp: bool = True):
        if not _moveto_active[0]:
            return
        _moveto_active[0] = False
        _moveto_generation[0] += 1
        _moveto_heartbeat_timer.stop()
        if send_tcp:
            log.info("[UI] moveTo released: stop type=-1")
            cm.send_call("Robot/moveTo", {"type": -1},
                         on_response=lambda d: None,
                         on_error=lambda e: log.info(f"[UI] moveTo 停止失败: {e}"))

    def _force_moveto_stop(*, send_tcp: bool = True):
        _moveto_active[0] = False
        _moveto_generation[0] += 1
        _moveto_heartbeat_timer.stop()
        if send_tcp:
            cm.send_call("Robot/moveTo", {"type": -1},
                         on_response=lambda d: None,
                         on_error=lambda e: log.info(f"[UI] moveTo 停止失败: {e}"))

    def _on_moveto_start_error(e):
        _moveto_active[0] = False
        _moveto_generation[0] += 1
        _moveto_heartbeat_timer.stop()
        log.info(f"[UI] moveTo 启动失败: {e}")

    def _on_moveto_pressed(move_type: int):
        if _moveto_active[0]:
            _send_moveto_stop()
        _moveto_active[0] = True
        _moveto_generation[0] += 1
        current_generation = _moveto_generation[0]
        log.info(f"[UI] moveTo pressed: type={move_type}")
        cm.send_call(
            "Robot/moveTo", {"type": move_type},
            on_response=lambda d, gen=current_generation: (
                _moveto_heartbeat_timer.start()
                if _moveto_active[0] and gen == _moveto_generation[0]
                else None
            ),
            on_error=_on_moveto_start_error,
        )

    def _on_moveto_released():
        _send_moveto_stop()

    main_win._drawer.moveto_pressed.connect(_on_moveto_pressed)
    main_win._drawer.moveto_released.connect(_on_moveto_released)

    state["stop_moveto"] = _send_moveto_stop
    state["force_stop_moveto"] = _force_moveto_stop


def _bind_speed(cm, main_win, state):
    """速度条变化 → 同时设置手动速度和自动速度"""
    def _on_speed_changed(rate: int):
        log.info(f"[UI] speed changed: {rate}%")
        cm.send_call("Robot/setManualMoveRate", rate,
                     on_response=lambda d: None,
                     on_error=lambda e: log.info(f"[UI] 设置手动速度失败: {e}"))
        QTimer.singleShot(100, lambda: cm.send_call(
            "Robot/setAutoMoveRate", rate,
            on_response=lambda d: None,
            on_error=lambda e: log.info(f"[UI] 设置自动速度失败: {e}"),
        ))

    main_win._drawer.speed_rate_changed.connect(_on_speed_changed)


def _bind_cri(cri_svc, main_win, state):
    """CRI 实时数据 → 抽屉 + RobotRealtimeState（3D 模型仅由此关节角驱动）"""
    def _on_cri_stopped():
        RobotRealtimeState.instance().invalidate()
        main_win.update_home_cri(False)

    cri_svc.cri_stopped.connect(_on_cri_stopped)

    def _on_cri_frame(frame: dict):
        RobotRealtimeState.instance().update_from_cri_frame(frame)
        rt = RobotRealtimeState.instance()

        joint_rad = frame.get("joint_position", [])
        if joint_rad:
            main_win.update_joint_display(
                rad_list_to_deg(joint_rad),
                joint_rad=joint_rad,
                drive_model=True,
            )

        main_win.update_tcp_display(
            m_to_mm(frame.get("tcp_x", 0)),
            m_to_mm(frame.get("tcp_y", 0)),
            m_to_mm(frame.get("tcp_z", 0)),
            rad_to_deg(frame.get("tcp_rx", 0)),
            rad_to_deg(frame.get("tcp_ry", 0)),
            rad_to_deg(frame.get("tcp_rz", 0)),
        )
        main_win.update_home_cri(_cri_pose_active(state))
        main_win.update_home_runtime(
            enabled=rt.is_enabled(),
            moving=rt.is_moving(),
            emergency=rt.is_emergency_stop(),
        )

    cri_svc.cri_frame_received.connect(_on_cri_frame)

    def _on_cri_started():
        main_win.update_home_cri(True)

    cri_svc.cri_started.connect(_on_cri_started)

    # 连接后 3 秒自动启动 CRI
    def _auto_start_cri(sub_state: str):
        config = state.get("cri_config")
        if sub_state == "connected" and config:
            QTimer.singleShot(3000, lambda: cri_svc.start(config))

    # 注意：cm 来自 state，需在 bind_all 中先连好
    if state.get("cm"):
        state["cm"].connection_state_changed.connect(_auto_start_cri)


def bind_all(cm, cri_svc, login, main_win, stack):
    """连接所有信号。纯函数，不创建任何对象。"""
    state = {
        "cri_config": None,
        "cm": cm,
        "cri_svc": cri_svc,
    }

    _bind_login_flow(cm, login, main_win, stack, state)
    _bind_connection_state(cm, login, main_win, stack, state)
    _bind_subscriptions(cm, cri_svc, main_win, state)
    _bind_command_bar(cm, main_win, state)
    _bind_jog(cm, main_win, state)
    _bind_moveto(cm, main_win, state)
    _bind_speed(cm, main_win, state)
    _bind_cri(cri_svc, main_win, state)

    def _stop_motion_graph():
        router = main_win._page_router
        for page in router._cache.values():
            editor = getattr(page, "_editor", None)
            if editor is not None:
                stop_fn = getattr(editor, "stop_execution", None)
                if callable(stop_fn):
                    stop_fn()

    def stop_all_motion(*, send_tcp: bool = True):
        _stop_motion_graph()
        stop_jog = state.get("stop_jog")
        force_moveto = state.get("force_stop_moveto")
        if stop_jog:
            stop_jog(send_tcp=send_tcp)
        if force_moveto:
            force_moveto(send_tcp=send_tcp)

    state["stop_all_motion"] = stop_all_motion
    state["motion_cleanup"] = lambda: stop_all_motion(send_tcp=False)

    main_win._command_bar.stop_move.connect(stop_all_motion)

    def _on_page_stop_jog():
        stop_jog = state.get("stop_jog")
        if stop_jog:
            stop_jog(send_tcp=True)

    main_win._page_router.on_stop_jog_requested.connect(_on_page_stop_jog)

    return state
