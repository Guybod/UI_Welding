import os
import sys
import logging
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "log")
MAX_BYTES = 1_048_576  # 1MB


class _RotatingFileHandler(logging.Handler):
    """追加写, 超过 1MB 自动切: xxx.txt → xxx_2.txt → xxx_3.txt。每次启动写分割线"""

    def __init__(self, max_bytes: int = MAX_BYTES):
        super().__init__()
        self._max = max_bytes
        self._path = ""
        self._index = 0
        self._stream = None
        self._open_existing_or_new()

    def _open_existing_or_new(self):
        if self._stream:
            self._stream.close()

        os.makedirs(LOG_DIR, exist_ok=True)
        today = datetime.now().strftime("%Y%m%d")
        base = os.path.join(LOG_DIR, today)

        # 找今天的最后一个文件
        self._index = 0
        while True:
            self._path = f"{base}.txt" if self._index == 0 else f"{base}_{self._index}.txt"
            if not os.path.exists(self._path):
                break
            if os.path.getsize(self._path) < self._max:
                break
            self._index += 1

        self._stream = open(self._path, "a", encoding="utf-8")
        # 启动分割线
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._stream.write(f"\n{'='*40} {now} {'='*40}\n")
        self._stream.flush()

    def emit(self, record):
        try:
            msg = self.format(record) + "\n"
            if self._stream.tell() + len(msg.encode("utf-8")) >= self._max:
                self._index += 1
                self._path = self._path.replace(
                    f"_{self._index - 1}.txt" if self._index > 1 else ".txt",
                    f"_{self._index}.txt" if self._index > 0 else "_1.txt"
                )
                if self._index == 1:
                    base = os.path.join(LOG_DIR, datetime.now().strftime("%Y%m%d"))
                    self._path = f"{base}_1.txt"
                else:
                    base = self._path.rsplit("_", 1)[0]
                    self._path = f"{base}_{self._index}.txt"
                if self._stream:
                    self._stream.close()
                self._stream = open(self._path, "a", encoding="utf-8")
            self._stream.write(msg)
            self._stream.flush()
        except Exception:
            pass

    def close(self):
        if self._stream:
            self._stream.close()
        super().close()


class _ColoredFormatter(logging.Formatter):
    GREY = "\x1b[38;20m"
    CYAN = "\x1b[36;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    RESET = "\x1b[0m"

    COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: CYAN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.GREY)
        return f"{color}{super().format(record)}{self.RESET}"


def setup_logger(name: str = "codroid") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    tf = "[%(asctime)s.%(msecs)03d] %(message)s"
    df = "%H:%M:%S"

    # 控制台: 只显示警告和错误, 收发日志去文件看
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(_ColoredFormatter(tf, datefmt=df))
    logger.addHandler(ch)

    # 文件
    fh = _RotatingFileHandler()
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(tf, datefmt=df))
    logger.addHandler(fh)

    return logger


log = setup_logger()
