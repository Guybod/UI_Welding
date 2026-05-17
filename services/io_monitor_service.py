"""IO 监控 — IOManager 轮询与写入（与 planAPI §13 / 运动节点引擎一致）。"""

from __future__ import annotations

from typing import Any, Callable

IO_COUNTS = {
    "DI": 16,
    "DO": 16,
    "AI": 4,
    "AO": 4,
}

DIGITAL_WRITABLE_TYPES = frozenset({"DO"})
ANALOG_WRITABLE_TYPES = frozenset({"AO"})
WRITABLE_TYPES = DIGITAL_WRITABLE_TYPES | ANALOG_WRITABLE_TYPES
READ_TYPES = frozenset({"DI", "DO", "AI", "AO"})


def build_poll_request() -> list[dict[str, Any]]:
    """构造单次 GetIOValue 查询列表。"""
    items: list[dict[str, Any]] = []
    for io_type, count in IO_COUNTS.items():
        for port in range(count):
            items.append({"type": io_type, "port": port})
    return items


def parse_io_values(db: Any) -> dict[tuple[str, int], float | int]:
    """解析 GetIOValue 响应 db 列表为 (type, port) -> value。"""
    out: dict[tuple[str, int], float | int] = {}
    if not isinstance(db, list):
        return out
    for item in db:
        if not isinstance(item, dict):
            continue
        io_type = str(item.get("type", "")).upper()
        if io_type not in READ_TYPES:
            continue
        try:
            port = int(item.get("port", 0))
        except (TypeError, ValueError):
            continue
        val = item.get("value", 0)
        if io_type in ("AI", "AO"):
            try:
                out[(io_type, port)] = float(val)
            except (TypeError, ValueError):
                out[(io_type, port)] = 0.0
        else:
            out[(io_type, port)] = 1 if val else 0
    return out


def is_digital_high(value: float | int, io_type: str) -> bool:
    if io_type in ("AI", "AO"):
        try:
            return float(value) >= 0.5
        except (TypeError, ValueError):
            return False
    return bool(value)


def toggle_digital_value(current: float | int, io_type: str = "DO") -> int:
    """仅用于 DO 高低电平翻转。"""
    return 0 if is_digital_high(current, io_type) else 1


def format_display_value(value: float | int, io_type: str) -> str:
    if io_type in ("AI", "AO"):
        try:
            v = float(value)
            return f"{v:.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return "?"
    return "1" if value else "0"


class IoMonitorClient:
    """通过 ConnectionManager 轮询 / 写 IO。"""

    TY_GET = "IOManager/GetIOValue"
    TY_SET = "IOManager/SetIOValue"

    def __init__(self, connection_manager):
        self._cm = connection_manager

    @property
    def connected(self) -> bool:
        return bool(self._cm and self._cm.is_connected)

    def poll(
        self,
        on_ok: Callable[[dict[tuple[str, int], float | int]], None],
        on_error: Callable[[Exception], None] | None = None,
        *,
        log_traffic: bool = False,
    ) -> None:
        if not self.connected:
            if on_error:
                on_error(Exception("not connected"))
            return

        def _resp(db):
            on_ok(parse_io_values(db))

        self._cm.send_call(
            self.TY_GET,
            build_poll_request(),
            on_response=_resp,
            on_error=on_error or (lambda e: None),
            timeout=3.0,
            log_traffic=log_traffic,
        )

    def set_value(
        self,
        io_type: str,
        port: int,
        value: int | float,
        on_ok: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *,
        log_traffic: bool = True,
    ) -> None:
        if not self.connected:
            if on_error:
                on_error(Exception("not connected"))
            return
        io_type = io_type.upper()
        if io_type not in WRITABLE_TYPES:
            if on_error:
                on_error(Exception(f"not writable: {io_type}"))
            return
        db = {"type": io_type, "port": int(port), "value": value}

        def _resp(_db):
            if on_ok:
                on_ok()

        self._cm.send_call(
            self.TY_SET,
            db,
            on_response=_resp,
            on_error=on_error or (lambda e: None),
            timeout=3.0,
            log_traffic=log_traffic,
        )
