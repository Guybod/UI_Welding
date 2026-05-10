import json

from network.protocol.errors import ProtocolError


class JsonStreamParser:
    """从无分隔符TCP流中切分出完整JSON对象

    TCP 是流式协议, 一个坏字节可能导致后续 JSON 结构被悄悄改坏,
    因此 UTF-8 解码失败必须清缓冲, 不能 errors="ignore"。
    """

    def __init__(self):
        self._buffer: str = ""

    def feed(self, data: bytes) -> list[dict]:
        try:
            self._buffer += data.decode("utf-8")
        except UnicodeDecodeError:
            self._buffer = ""
            raise ProtocolError("TCP JSON UTF-8 decode failed, buffer cleared")

        results = []
        decoder = json.JSONDecoder()
        while self._buffer:
            self._buffer = self._buffer.lstrip()
            if not self._buffer:
                break
            try:
                obj, end = decoder.raw_decode(self._buffer)
                results.append(obj)
                self._buffer = self._buffer[end:]
            except json.JSONDecodeError:
                break

        return results

    def reset(self):
        self._buffer = ""
