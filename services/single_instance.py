"""
单实例锁 — 使用 localhost socket 确保只有一个实例运行
第二个实例启动时会通知已有实例显示窗口，然后退出
"""

import socket
import threading

from config import logger

LOCK_PORT = 65432
LOCK_HOST = "127.0.0.1"


def try_acquire() -> tuple[bool, socket.socket | None]:
    """
    尝试获取单实例锁。
    返回 (is_first, server_socket)。
    - is_first=True: 这是第一个实例，server_socket 是已绑定的监听 socket
    - is_first=False: 已有实例运行，server_socket 为 None
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Windows 上用 SO_EXCLUSIVEADDRUSE 阻止端口被重用
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    except (AttributeError, OSError):
        pass  # 非 Windows 或不支持，用默认行为（通常就是独占）
    sock.settimeout(0.5)

    try:
        sock.bind((LOCK_HOST, LOCK_PORT))
        sock.listen(1)
        logger.info("单实例锁已获取")
        return True, sock
    except OSError:
        sock.close()
        logger.info("检测到已有实例，通知其显示窗口")
        return False, None


def notify_existing():
    """通知已有实例显示窗口。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect((LOCK_HOST, LOCK_PORT))
        sock.sendall(b"show")
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def start_listener(server_sock: socket.socket, on_show):
    """
    在后台线程中监听来自新实例的通知。
    on_show: 当收到 "show" 命令时调用的回调函数。
    """
    def listen():
        while True:
            try:
                conn, _ = server_sock.accept()
                data = conn.recv(4)
                conn.close()
                if data == b"show":
                    logger.info("收到显示窗口请求")
                    if on_show:
                        on_show()
            except OSError:
                break
            except Exception:
                pass

    thread = threading.Thread(target=listen, daemon=True, name="FileGo-LockListener")
    thread.start()
    return thread
