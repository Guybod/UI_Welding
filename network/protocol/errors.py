class ProtocolError(Exception):
    """TCP JSON 协议层错误"""
    pass


class RobotError(Exception):
    """机器人返回的 err 字段"""

    def __init__(self, err: dict):
        code = err.get("code", -1) if isinstance(err, dict) else -1
        msg = err.get("msg", str(err)) if isinstance(err, dict) else str(err)
        self.code = code
        self.msg = msg
        super().__init__(f"RobotError[{code}]: {msg}")


class NetworkDisconnectedError(Exception):
    """连接断开 — 用于回调所有 pending 请求"""
    pass
