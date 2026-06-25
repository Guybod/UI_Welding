#!/usr/bin/env python3
"""伪机器人服务器 — 接收 TCP 消息并打印，用于离线调试 UI。

默认端口 9001，匹配 TcpAdapter 默认端口。
每行一条 JSON 消息，以 \n 分隔。
"""

import json
import socket
import sys
import threading


def handle_client(conn: socket.socket, addr: tuple):
    """处理单个客户端连接。"""
    peer = f"{addr[0]}:{addr[1]}"
    print(f"[连接] {peer}")
    buf = b""
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                    ty = msg.get("ty", "?")
                    print(f"[接收] {peer} → {ty}")
                    print(f"        {json.dumps(msg, ensure_ascii=False)}")
                except json.JSONDecodeError:
                    print(f"[原始] {peer} → {line.decode('utf-8', errors='replace')}")
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        print(f"[断开] {peer}")
        conn.close()


def main(host: str = "0.0.0.0", port: int = 9001):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"伪机器人服务器启动: {host}:{port}")
    print("等待 UI 连接...\n")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n服务器关闭")
    finally:
        server.close()


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9001
    main(host, port)
