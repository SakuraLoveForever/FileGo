"""
FileGo — 定时文件复制工具
入口点

用法:
    python main.py              # 正常启动
    python main.py --hidden     # 最小化到托盘启动（用于开机自启动）
"""

import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import ctypes

from config import logger, APP_NAME, APP_VERSION
from services.single_instance import try_acquire, notify_existing


def set_dpi_awareness():
    """设置 Windows DPI 感知，避免高 DPI 屏幕模糊。"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION} — 定时文件复制工具"
    )
    parser.add_argument(
        "--hidden", action="store_true",
        help="启动时最小化到系统托盘",
    )
    args = parser.parse_args()

    # Windows DPI 修复
    set_dpi_awareness()

    logger.info(f"{'=' * 50}")
    logger.info(f"{APP_NAME} v{APP_VERSION} 启动")
    logger.info(f"{'=' * 50}")

    # 单实例检查
    is_first, lock_socket = try_acquire()
    if not is_first:
        # 已有实例在运行 — 通知它显示窗口，然后退出
        notify_existing()
        logger.info("已有实例在运行，本实例退出")
        return

    try:
        from app import App

        app = App()
        app.set_lock_socket(lock_socket)
        app.run(start_hidden=args.hidden)
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.exception(f"应用程序异常: {e}")
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "FileGo 错误",
                f"应用程序启动失败:\n\n{e}\n\n请查看日志文件了解详情。"
            )
        except Exception:
            pass
        sys.exit(1)
    finally:
        # 确保锁 socket 关闭
        try:
            lock_socket.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
