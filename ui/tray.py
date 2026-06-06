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
    """系统托盘图标管理器。

    图标默认隐藏，仅在窗口最小化到托盘时显示。
    """

    def __init__(self):
        self._icon = None
        self._running = False
        self._callbacks: dict[str, Callable] = {}
        self._pending_visible = False  # 图标创建前的可见性请求

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
            from pystray._util import win32 as _win32_util

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
            # 不在这里设置 visible — pystray.run() 内部的 setup 线程会覆盖。
            # 改用 run(setup=...) 来控制初始可见性。

            # ---- 补丁: 修复 Windows 托盘右键菜单不弹出 ----
            # pystray 的 _on_notify 只处理 WM_RBUTTONUP (0x0205)，
            # 但某些 Windows 10/11 版本发送的是 WM_RBUTTONDOWN (0x0204)。
            # 补丁：将 WM_RBUTTONDOWN 映射为 WM_RBUTTONUP，统一触发菜单。
            _msg_id = _win32_util.WM_NOTIFY
            _original_handler = self._icon._message_handlers[_msg_id]

            def _patched_notify(wparam, lparam):
                # WM_RBUTTONDOWN (0x0204) → WM_RBUTTONUP (0x0205)
                if lparam == 0x0204:
                    lparam = 0x0205
                # WM_LBUTTONDOWN (0x0201) → WM_LBUTTONUP (0x0202)
                if lparam == 0x0201:
                    lparam = 0x0202
                return _original_handler(wparam, lparam)

            self._icon._message_handlers[_msg_id] = _patched_notify
            # ---- 补丁结束 ----

            # 通过 setup 回调控制初始可见性（避免 pystray 默认设为可见）
            def _setup_visibility(icon):
                icon.visible = self._pending_visible

            logger.info("系统托盘已启动")
            self._icon.run(setup=_setup_visibility)
        except Exception as e:
            logger.error(f"系统托盘启动失败: {e}")
            self._running = False

    def _on_show(self, icon=None, item=None):
        logger.info("托盘: 显示窗口")
        cb = self._callbacks.get("on_show")
        if cb:
            cb()

    def _on_run_all(self, icon=None, item=None):
        logger.info("托盘: 运行全部任务")
        cb = self._callbacks.get("on_run_all")
        if cb:
            cb()

    def _on_exit(self, icon=None, item=None):
        logger.info("托盘: 退出请求")
        cb = self._callbacks.get("on_exit")
        if cb:
            cb()
        else:
            logger.error("托盘退出回调未设置!")

    def show_notification(self, title: str, message: str):
        """显示气泡通知。"""
        if self._icon and self._running:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass  # 通知失败不影响主功能

    def show_icon(self):
        """显示托盘图标（线程安全）。"""
        self._pending_visible = True  # 始终同步，防止 setup 线程覆盖
        if self._icon:
            try:
                self._icon.visible = True
            except Exception:
                pass

    def hide_icon(self):
        """隐藏托盘图标（线程安全）。"""
        self._pending_visible = False  # 始终同步，防止 setup 线程覆盖
        if self._icon:
            try:
                self._icon.visible = False
            except Exception:
                pass

    def stop(self):
        """停止托盘图标。"""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
                logger.info("系统托盘已停止")
            except Exception:
                pass
