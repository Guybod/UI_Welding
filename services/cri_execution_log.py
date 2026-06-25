"""CRI 执行链路 — 带毫秒时间戳的中文诊断日志（仅观测，不改变控制语义）。"""

from __future__ import annotations

import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import math

from network.connection_manager import ConnectionManager
from network.cri_motion_sender import CriMotionSender
from services.robot_realtime_state import RobotRealtimeState

_MODE_NAMES = {0: "手动", 1: "自动", 2: "远程", -1: "未知"}
_STATE_NAMES = {
    0: "未使能", 1: "使能中", 2: "空闲", 3: "点动中",
    4: "RunTo", 5: "拖动中", -1: "未知",
}


def format_ts_ms() -> str:
    """``[HH:MM:SS.mmm]``"""
    now = datetime.now()
    return now.strftime("[%H:%M:%S.") + f"{now.microsecond // 1000:03d}]"


class CriExecutionTrace:
    """CRI 执行阶段耗时与异常标记。"""

    def __init__(self) -> None:
        self.socket_error = False
        self.timeout = False
        self.start_control_error = False
        self.stop_control_error = False

    def summary_lines(self) -> list[str]:
        return [
            f"socket 错误: {'是' if self.socket_error else '否'}",
            f"超时: {'是' if self.timeout else '否'}",
            f"StartControl 错误: {'是' if self.start_control_error else '否'}",
            f"StopControl 错误: {'是' if self.stop_control_error else '否'}",
        ]


def trajectory_file_stats(traj_path: str | Path) -> dict[str, Any]:
    """读取 trajectory_cri.txt 采样点统计。"""
    path = Path(traj_path)
    points: list[list[float]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                points.append([float(x) for x in parts[:6]])

    if not points:
        return {
            "path": str(path.resolve()),
            "sample_count": 0,
            "first_point": None,
            "last_point": None,
            "min_x": None,
            "max_x": None,
            "min_y": None,
            "max_y": None,
            "min_z": None,
            "max_z": None,
        }

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {
        "path": str(path.resolve()),
        "sample_count": len(points),
        "first_point": points[0],
        "last_point": points[-1],
        "min_x": min(xs),
        "max_x": max(xs),
        "min_y": min(ys),
        "max_y": max(ys),
        "min_z": min(zs),
        "max_z": max(zs),
    }


def log_trajectory_summary(
    emit: Callable[[str], None],
    traj_path: str | Path,
    frequency_hz: float,
) -> dict[str, Any]:
    """输出轨迹文件摘要（项 1–6）。"""
    stats = trajectory_file_stats(traj_path)
    n = int(stats["sample_count"])
    freq = max(1.0, float(frequency_hz))
    expected = n / freq if n > 0 else 0.0

    emit(f"{format_ts_ms()} 轨迹文件: {stats['path']}")
    emit(f"{format_ts_ms()} 采样点数 sample_count={n}")
    emit(f"{format_ts_ms()} 下发频率 frequency={freq:.1f} Hz")
    emit(f"{format_ts_ms()} 预期时长 expected_duration_s={expected:.3f} s (sample_count/frequency)")

    if n > 0:
        fp = stats["first_point"]
        lp = stats["last_point"]
        emit(
            f"{format_ts_ms()} 首点 first: "
            f"X={fp[0]:.3f} Y={fp[1]:.3f} Z={fp[2]:.3f} "
            f"Rx={fp[3]:.3f} Ry={fp[4]:.3f} Rz={fp[5]:.3f}"
        )
        emit(
            f"{format_ts_ms()} 末点 last: "
            f"X={lp[0]:.3f} Y={lp[1]:.3f} Z={lp[2]:.3f} "
            f"Rx={lp[3]:.3f} Ry={lp[4]:.3f} Rz={lp[5]:.3f}"
        )
        emit(
            f"{format_ts_ms()} 范围 min/max: "
            f"X=[{stats['min_x']:.3f}, {stats['max_x']:.3f}] "
            f"Y=[{stats['min_y']:.3f}, {stats['max_y']:.3f}] "
            f"Z=[{stats['min_z']:.3f}, {stats['max_z']:.3f}]"
        )
    else:
        emit(f"{format_ts_ms()} 警告: 轨迹文件无有效采样点")

    stats["frequency_hz"] = freq
    stats["expected_duration_s"] = expected
    return stats


def _sync_tcp_call(
    cm: ConnectionManager,
    ty: str,
    db: Any,
    *,
    timeout_s: float = 5.0,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[bool, Any | None, float, str | None]:
    """在后台线程阻塞等待 TCP 响应（与 Robot/move 相同模式）。"""
    state: dict[str, Any] = {}

    def on_ok(data):
        state["ok"] = True
        state["data"] = data
        state["t_resp"] = time.perf_counter()

    def on_err(exc: Exception):
        state["err"] = exc
        state["t_resp"] = time.perf_counter()

    t_req = time.perf_counter()
    cm.send_call(ty, db, on_ok, on_err, timeout=timeout_s)

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if should_stop and should_stop():
            return False, None, (time.perf_counter() - t_req) * 1000.0, "已取消"
        if "ok" in state or "err" in state:
            break
        time.sleep(0.01)

    if "ok" not in state and "err" not in state:
        return False, None, (time.perf_counter() - t_req) * 1000.0, "等待响应超时"

    if "err" in state:
        err = state["err"]
        return False, None, (state["t_resp"] - t_req) * 1000.0, str(err)

    return True, state.get("data"), (state["t_resp"] - t_req) * 1000.0, None


def log_cri_stop_control(
    emit: Callable[[str], None],
    cm: ConnectionManager,
    trace: CriExecutionTrace,
    *,
    phase: str,
    timeout_s: float = 5.0,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """CRI/StopControl — 记录请求/响应时刻。"""
    label = f"StopControl({phase})"
    emit(f"{format_ts_ms()} CRI {label} 请求发送...")
    ok, _data, dt_ms, err = _sync_tcp_call(
        cm, "CRI/StopControl", {}, timeout_s=timeout_s, should_stop=should_stop,
    )
    if ok:
        emit(f"{format_ts_ms()} CRI {label} 应答 OK, 耗时 dt={dt_ms:.0f}ms")
    else:
        trace.stop_control_error = True
        if err == "等待响应超时":
            trace.timeout = True
            emit(f"{format_ts_ms()} CRI {label} 应答超时, dt={dt_ms:.0f}ms")
        else:
            emit(f"{format_ts_ms()} CRI {label} 应答失败: {err}, dt={dt_ms:.0f}ms")


def log_cri_start_control(
    emit: Callable[[str], None],
    cm: ConnectionManager,
    trace: CriExecutionTrace,
    *,
    filter_type: int,
    duration_ms: int,
    start_buffer: int,
    frequency_hz: float,
    timeout_s: float = 5.0,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """CRI/StartControl — 记录请求/响应时刻。"""
    db = {
        "filterType": filter_type,
        "duration": duration_ms,
        "startBuffer": start_buffer,
    }
    emit(
        f"{format_ts_ms()} CRI StartControl 请求发送: "
        f"frequency={frequency_hz:.1f}Hz, duration_ms={duration_ms}, "
        f"filterType={filter_type}, startBuffer={start_buffer}"
    )
    ok, _data, dt_ms, err = _sync_tcp_call(
        cm, "CRI/StartControl", db, timeout_s=timeout_s, should_stop=should_stop,
    )
    if ok:
        emit(f"{format_ts_ms()} CRI StartControl 应答 OK, 耗时 dt={dt_ms:.0f}ms")
    else:
        trace.start_control_error = True
        if err == "等待响应超时":
            trace.timeout = True
            emit(f"{format_ts_ms()} CRI StartControl 应答超时, dt={dt_ms:.0f}ms")
        else:
            emit(f"{format_ts_ms()} CRI StartControl 应答失败: {err}, dt={dt_ms:.0f}ms")


def log_udp_send_begin(
    emit: Callable[[str], None],
    *,
    sample_count: int,
    frequency_hz: float,
    expected_duration_s: float,
) -> None:
    emit(
        f"{format_ts_ms()} UDP 发送开始: samples={sample_count}, "
        f"freq={frequency_hz:.1f}Hz, 预期时长={expected_duration_s:.3f}s"
    )


def log_udp_send_summary(
    emit: Callable[[str], None],
    *,
    sent_count: int,
    actual_duration_s: float,
    socket_error: bool,
    interrupted: bool,
) -> None:
    """UDP 发送结束与实测频率。"""
    actual_freq = sent_count / actual_duration_s if actual_duration_s > 0 else 0.0
    end_msg = (
        f"{format_ts_ms()} UDP 发送结束: 已发={sent_count}, "
        f"实测时长={actual_duration_s:.3f}s, 实测频率={actual_freq:.1f}Hz"
    )
    if interrupted:
        end_msg += ", 状态=用户中断"
    if socket_error:
        end_msg += ", 状态=socket错误"
    emit(end_msg)


def log_execution_footer(emit: Callable[[str], None], trace: CriExecutionTrace) -> None:
    emit(f"{format_ts_ms()} —— CRI 执行诊断汇总 ——")
    for line in trace.summary_lines():
        emit(f"{format_ts_ms()} {line}")


def _format_decoded_fields(dec: dict) -> str:
    if "error" in dec:
        return dec["error"]
    if "x_mm" in dec:
        return (
            f"type={dec.get('type_name')} ts_us={dec.get('timestamp_us')} "
            f"X={dec['x_mm']:.3f}mm Y={dec['y_mm']:.3f}mm Z={dec['z_mm']:.3f}mm "
            f"Rx={dec['rx_deg']:.3f}° Ry={dec['ry_deg']:.3f}° Rz={dec['rz_deg']:.3f}°"
        )
    return str(dec)


def log_udp_target_and_packets(
    emit: Callable[[str], None],
    sender: CriMotionSender,
    traj_path: str | Path,
    *,
    cri_data_push_ip: str = "",
    cri_data_push_port: int = 0,
) -> None:
    """UDP 目标、本机绑定、包大小与首末包解析。"""
    info = sender.socket_endpoint_info()
    emit(f"{format_ts_ms()} —— UDP 控制通道诊断 ——")
    emit(f"{format_ts_ms()} robot_ip(配置)={info['robot_ip']}")
    emit(
        f"{format_ts_ms()} udp_target={info['udp_target_ip']}:{info['udp_target_port']} "
        f"(客户端→机器人实时控制，非本机监听口)"
    )
    emit(
        f"{format_ts_ms()} local_bind={info['local_bind_ip']}:{info['local_bind_port']} "
        f"socket_family={info['socket_family']}"
    )
    if cri_data_push_ip or cri_data_push_port:
        emit(
            f"{format_ts_ms()} CRI数据推送监听(机器人→本机)={cri_data_push_ip}:{cri_data_push_port} "
            f"【与控制 sendto 目标不同，勿混淆】"
        )
    emit(
        f"{format_ts_ms()} control_frequency={info['control_frequency_hz']:.1f}Hz "
        f"packet_size_bytes={info['packet_size_bytes']} cartesian={info['cartesian_mode']}"
    )
    preview = sender.preview_packets(traj_path)
    if preview:
        emit(f"{format_ts_ms()} first_packet_hex={preview['first_packet_hex']}")
        emit(
            f"{format_ts_ms()} first_packet_decoded: "
            f"{_format_decoded_fields(preview['first_decoded'])}"
        )
        emit(f"{format_ts_ms()} last_packet_hex={preview['last_packet_hex']}")
        emit(
            f"{format_ts_ms()} last_packet_decoded: "
            f"{_format_decoded_fields(preview['last_decoded'])}"
        )


def analyze_trajectory_z(
    traj_path: str | Path,
    *,
    z_draw_mm: float,
    z_safe_mm: float,
    tolerance_mm: float = 5.0,
) -> dict[str, Any]:
    """Z 轴异常分析（不改生成，仅统计）。"""
    path = Path(traj_path)
    threshold = z_safe_mm + tolerance_mm
    high_points: list[tuple[int, str, float]] = []
    line_no = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line_no += 1
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        parts = s.split()
        if len(parts) < 3:
            continue
        z = float(parts[2])
        if z > threshold:
            high_points.append((line_no, s, z))

    stats = trajectory_file_stats(traj_path)
    return {
        "z_draw_mm": z_draw_mm,
        "z_safe_mm": z_safe_mm,
        "z_threshold_mm": threshold,
        "min_z": stats.get("min_z"),
        "max_z": stats.get("max_z"),
        "count_above_threshold": len(high_points),
        "top10_high_z": high_points[:10],
    }


def log_tcp_vs_trajectory_start(
    emit: Callable[[str], None],
    traj_first_point: list[float],
    *,
    tolerance_mm: float = 2.0,
) -> bool:
    """执行前对比 CRI 当前 TCP 与轨迹首点，返回是否基本一致。"""
    rt = RobotRealtimeState.instance()
    if not rt.is_cri_primary():
        emit(f"{format_ts_ms()} 警告: 无 CRI UDP 数据，无法核对当前 TCP 与轨迹首点")
        return False
    cur = rt.current_tcp_pose_mm_deg()
    pos_d = math.sqrt(
        (cur[0] - traj_first_point[0]) ** 2
        + (cur[1] - traj_first_point[1]) ** 2
        + (cur[2] - traj_first_point[2]) ** 2
    )
    orient_d = math.sqrt(
        (cur[3] - traj_first_point[3]) ** 2
        + (cur[4] - traj_first_point[4]) ** 2
        + (cur[5] - traj_first_point[5]) ** 2
    )
    emit(
        f"{format_ts_ms()} 执行前位姿核对: 当前TCP="
        f"X={cur[0]:.2f} Y={cur[1]:.2f} Z={cur[2]:.2f} | 轨迹首点="
        f"X={traj_first_point[0]:.2f} Y={traj_first_point[1]:.2f} Z={traj_first_point[2]:.2f} | "
        f"位置差={pos_d:.2f}mm 姿态差={orient_d:.2f}°"
    )
    ok = pos_d <= tolerance_mm and orient_d <= 3.0
    if not ok:
        emit(
            f"{format_ts_ms()} ⚠ 首点偏差过大: 控制器 startBuffer 未满或偏差大时可能拒收/关节跳变；"
            f"请先「移至起点」或按当前 TCP 重新生成轨迹"
        )
    return ok


def log_trajectory_z_diagnosis(
    emit: Callable[[str], None],
    traj_path: str | Path,
    *,
    z_draw_mm: float,
    z_safe_mm: float,
) -> dict[str, Any]:
    """输出 Z 诊断（项三）。"""
    diag = analyze_trajectory_z(
        traj_path, z_draw_mm=z_draw_mm, z_safe_mm=z_safe_mm,
    )
    emit(f"{format_ts_ms()} —— 轨迹 Z 轴诊断 ——")
    emit(f"{format_ts_ms()} z_draw_mm={z_draw_mm:.3f} z_safe_mm={z_safe_mm:.3f}")
    emit(
        f"{format_ts_ms()} 轨迹 Z 范围: min={diag['min_z']}, max={diag['max_z']} "
        f"(预期主要在 [{z_draw_mm:.1f}, {z_safe_mm:.1f}] 附近)"
    )
    emit(
        f"{format_ts_ms()} Z > z_safe+5mm 的点数: {diag['count_above_threshold']} "
        f"(阈值={diag['z_threshold_mm']:.3f}mm)"
    )
    if diag["max_z"] is not None and diag["max_z"] > diag["z_threshold_mm"]:
        overshoot = diag["max_z"] - z_safe_mm
        emit(
            f"{format_ts_ms()} Z 偏高原因提示: 三次样条在 z_draw↔z_safe 过渡段可能过冲 "
            f"(max_z 超出 z_safe {overshoot:.1f}mm)，非 UDP 层问题"
        )
    for i, (ln, content, z) in enumerate(diag["top10_high_z"], 1):
        emit(f"{format_ts_ms()} 异常高Z #{i} 行{ln} Z={z:.3f}: {content}")
    if not diag["top10_high_z"]:
        emit(f"{format_ts_ms()} 无 Z > z_safe+5mm 的采样点")
    return diag


class _UdpPoseProbe:
    """UDP 发送期间每秒采样机器人状态。"""

    def __init__(self, start_pose: list[float]) -> None:
        self._start = start_pose
        self._last_pose: tuple[float, ...] | None = None
        self._max_dist = 0.0
        self._any_motion = False

    def tick(self, emit: Callable[[str], None], elapsed_s: float) -> None:
        rt = RobotRealtimeState.instance()
        if not rt.is_cri_primary():
            emit(f"{format_ts_ms()} [{elapsed_s:.1f}s] CRI状态无效(无UDP推送数据)")
            return

        pose = rt.current_tcp_pose_mm_deg()
        joints = rt.current_joints_deg()
        dist = math.sqrt(
            (pose[0] - self._start[0]) ** 2
            + (pose[1] - self._start[1]) ** 2
            + (pose[2] - self._start[2]) ** 2
        )
        self._max_dist = max(self._max_dist, dist)
        if dist > 0.05:
            self._any_motion = True

        delta = 0.0
        if self._last_pose is not None:
            delta = math.sqrt(
                (pose[0] - self._last_pose[0]) ** 2
                + (pose[1] - self._last_pose[1]) ** 2
                + (pose[2] - self._last_pose[2]) ** 2
            )
        self._last_pose = pose

        mode = rt.robot_mode()
        state = rt.robot_state()
        err = rt.last_error()
        err_short = err[:80] if err else "无"
        emit(
            f"{format_ts_ms()} [{elapsed_s:.1f}s] TCP="
            f"X={pose[0]:.2f} Y={pose[1]:.2f} Z={pose[2]:.2f} "
            f"Rx={pose[3]:.1f} Ry={pose[4]:.1f} Rz={pose[5]:.1f} | "
            f"关节(deg)={[round(j, 1) for j in joints[:6]]} | "
            f"moving={rt.is_moving()} enabled={rt.is_enabled()} | "
            f"模式={_MODE_NAMES.get(mode, mode)} 状态={_STATE_NAMES.get(state, state)} | "
            f"CRI实时模式={rt.cri_realtime_mode()} CRI错误码={rt.cri_error_code()} "
            f"status2=0x{rt.status2():04X} | "
            f"急停={rt.is_emergency_stop()} 报警={err_short} | "
            f"距轨迹首点={dist:.3f}mm 较上秒Δ={delta:.3f}mm"
        )

    @property
    def max_dist_from_start(self) -> float:
        return self._max_dist

    @property
    def any_motion(self) -> bool:
        return self._any_motion


def log_cri_protocol_reference(emit: Callable[[str], None]) -> None:
    """与 planAPI / cri_packer / write4.0 注释的对照（静态）。"""
    emit(f"{format_ts_ms()} —— CRI 控制包格式对照 ——")
    emit(
        f"{format_ts_ms()} 当前发送: struct {CriMotionSender.CMD_FMT} "
        f"= {CriMotionSender.PACKET_SIZE_BYTES}B; 目标端口 9030; type=1 末端(m+rad)"
    )
    emit(
        f"{format_ts_ms()} cri_packer.py: 同为 <q6dB7B> 64B, mm→m, deg→rad — 与 CriMotionSender 一致"
    )
    emit(
        f"{format_ts_ms()} plan.md 写 70B 为文档笔误; 接收 CRI 推送为 308B(另一方向)"
    )
    emit(
        f"{format_ts_ms()} StartControl.duration 协议范围 [1,16]ms; "
        f"本实现 duration_ms≈1000/Hz (500Hz→2ms)"
    )
    emit(
        f"{format_ts_ms()} 与 send_raw(id:0) 差异: 诊断路径用 send_call 等应答; "
        f"UDP 包体与 write4.0 robot_udp_sender 注释一致"
    )
    emit(
        f"{format_ts_ms()} 常见不动因: 非远程模式、未使能、sendto 非 robot:9030、"
        f"首点与当前位姿偏差>startBuffer、Z 样条过冲导致控制器拒收"
    )
