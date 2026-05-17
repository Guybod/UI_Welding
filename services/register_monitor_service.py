"""寄存器监控 — RegisterManager 轮询与用户自定义寄存器列表。"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Callable

from pathlib import Path

from PySide6.QtCore import QSettings

REGISTER_TYPES = ("bool", "int", "float")
SETTINGS_KEY = "register/monitorDefs"
REGISTER_CARDS_VERSION = "1.0"
REGISTER_CARDS_FILENAME = "register_cards.json"


@dataclass
class RegisterDef:
    reg_id: str
    address: int
    reg_type: str
    label: str = ""

    def __post_init__(self):
        if not self.reg_id:
            self.reg_id = str(uuid.uuid4())[:8]
        self.reg_type = (self.reg_type or "int").lower()
        if self.reg_type not in REGISTER_TYPES:
            self.reg_type = "int"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(obj: dict) -> "RegisterDef":
        return RegisterDef(
            reg_id=obj.get("reg_id", ""),
            address=int(obj.get("address", 0)),
            reg_type=obj.get("reg_type", "int"),
            label=obj.get("label", ""),
        )

    def uses_two_bytes(self) -> bool:
        return self.reg_type in ("int", "float")

    def address_range(self) -> tuple[int, int]:
        return self.address, self.address


def get_projects_dir(projects_dir: Path | None = None) -> Path:
    root = projects_dir or Path(__file__).resolve().parents[1] / "projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def register_cards_path(projects_dir: Path | None = None) -> Path:
    return get_projects_dir(projects_dir) / REGISTER_CARDS_FILENAME


def _defs_from_items(items: list) -> list[RegisterDef]:
    out: list[RegisterDef] = []
    for item in items:
        if isinstance(item, dict):
            out.append(RegisterDef.from_dict(item))
    return out


def _load_from_qsettings(settings: QSettings) -> list[RegisterDef]:
    raw = settings.value(SETTINGS_KEY, "[]")
    if isinstance(raw, list):
        return _defs_from_items(raw)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        items = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        items = []
    return _defs_from_items(items)


def load_register_defs(
    settings: QSettings | None = None,
    projects_dir: Path | None = None,
) -> list[RegisterDef]:
    """从 projects/register_cards.json 加载；若无文件则回退 QSettings 并迁移到文件。"""
    path = register_cards_path(projects_dir)
    if path.is_file():
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            items = obj.get("registers", obj) if isinstance(obj, dict) else obj
            if isinstance(items, list):
                return _defs_from_items(items)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    s = settings or QSettings("Codroid", "RobotUI")
    regs = _load_from_qsettings(s)
    if regs:
        save_register_defs(regs, s, projects_dir)
    return regs


def save_register_defs(
    regs: list[RegisterDef],
    settings: QSettings | None = None,
    projects_dir: Path | None = None,
) -> None:
    """保存到 projects/register_cards.json，并同步 QSettings 备份。"""
    path = register_cards_path(projects_dir)
    payload = {
        "register_cards_version": REGISTER_CARDS_VERSION,
        "registers": [r.to_dict() for r in regs],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    s = settings or QSettings("Codroid", "RobotUI")
    s.setValue(SETTINGS_KEY, json.dumps(payload["registers"], ensure_ascii=False))
    s.sync()


def address_conflict(new: RegisterDef, existing: list[RegisterDef], skip_id: str = "") -> RegisterDef | None:
    """若地址区间重叠则返回冲突项。"""
    a0, a1 = new.address_range()
    for reg in existing:
        if reg.reg_id == skip_id:
            continue
        b0, b1 = reg.address_range()
        if a0 <= b1 and b0 <= a1:
            return reg
    return None


def parse_register_values(db: Any) -> dict[int, Any]:
    out: dict[int, Any] = {}
    if not isinstance(db, list):
        return out
    for item in db:
        if not isinstance(item, dict):
            continue
        try:
            addr = int(item.get("address", 0))
        except (TypeError, ValueError):
            continue
        out[addr] = item.get("value", 0)
    return out


def coerce_value(value: Any, reg_type: str) -> bool | int | float:
    t = reg_type.lower()
    if t == "bool":
        return bool(value) if not isinstance(value, str) else value not in ("", "0", "false", "False")
    if t == "float":
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def format_register_value(value: Any, reg_type: str) -> str:
    t = reg_type.lower()
    if t == "bool":
        return "true" if coerce_value(value, "bool") else "false"
    if t == "float":
        try:
            v = float(value)
            return f"{v:.4f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return "?"
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return "?"


def toggle_bool_value(current: Any) -> int:
    return 0 if coerce_value(current, "bool") else 1


class RegisterMonitorClient:
    TY_GET = "RegisterManager/GetRegisterValue"
    TY_SET = "RegisterManager/SetRegisterValue"

    def __init__(self, connection_manager):
        self._cm = connection_manager

    @property
    def connected(self) -> bool:
        return bool(self._cm and self._cm.is_connected)

    def poll(
        self,
        registers: list[RegisterDef],
        on_ok: Callable[[dict[str, Any]], None],
        on_error: Callable[[Exception], None] | None = None,
        *,
        log_traffic: bool = False,
    ) -> None:
        if not self.connected:
            if on_error:
                on_error(Exception("not connected"))
            return
        if not registers:
            on_ok({})
            return
        addresses = sorted({r.address for r in registers})

        def _resp(db):
            by_addr = parse_register_values(db)
            out: dict[str, Any] = {}
            for reg in registers:
                out[reg.reg_id] = by_addr.get(reg.address, 0)
            on_ok(out)

        self._cm.send_call(
            self.TY_GET,
            addresses,
            on_response=_resp,
            on_error=on_error or (lambda e: None),
            timeout=3.0,
            log_traffic=log_traffic,
        )

    def set_value(
        self,
        reg: RegisterDef,
        value: bool | int | float,
        on_ok: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        *,
        log_traffic: bool = True,
    ) -> None:
        if not self.connected:
            if on_error:
                on_error(Exception("not connected"))
            return
        payload = coerce_value(value, reg.reg_type)
        db = {"address": int(reg.address), "value": payload}

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
