"""
系统托盘图标 — 最小化到托盘、托盘菜单
"""

import base64
import threading
from io import BytesIO
from typing import Callable

from PIL import Image

from config import logger, APP_NAME
from ui.icons import APP_ICON_BASE64


class TrayIcon:
    """系统托盘图标管理器。"""

    def __init__(self):
        self._icon = None
        self._running = False
        self._callbacks: dict[str, Callable] = {}

    def set_callbacks(self, callbacks: dict[str, Callable]):
        """
        设置回调：
        - on_show: 恢复窗口
        - on_run_all: 运行全部任务
        - on_exit: 退出应用
        """
        self._callbacks = callbacks

    def setup(self):
        """在后台线程中创建并运行系统托盘图标。"""
        if self._running:
            return

        self._running = True
        thread = threading.Thread(target=self._run, daemon=True, name="FileGo-Tray")
        thread.start()

    def _run(self):
        """托盘图标主循环（在单独线程中运行）。"""
        try:
            import pystray

            # 解码图标
            icon_data = base64.b64decode(APP_ICON_BASE64)
            image = Image.open(BytesIO(icon_data))

            # 创建菜单
            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._on_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("▶ 运行全部任务", self._on_run_all),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._on_exit),
            )

            self._icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
            logger.info("系统托盘已启动")
            self._icon.run()
        except Exception as e:
            logger.error(f"系统托盘启动失败: {e}")
            self._running = False

    def _on_show(self, icon=None, item=None):
        cb = self._callbacks.get("on_show")
        if cb:
            cb()

    def _on_run_all(self, icon=None, item=None):
        cb = self._callbacks.get("on_run_all")
        if cb:
            cb()

    def _on_exit(self, icon=None, item=None):
        cb = self._callbacks.get("on_exit")
        if cb:
            cb()

    def show_notification(self, title: str, message: str):
        """显示气泡通知。"""
        if self._icon and self._running:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass  # 通知失败不影响主功能

    def stop(self):
        """停止托盘图标。"""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
                logger.info("系统托盘已停止")
            except Exception:
                pass
