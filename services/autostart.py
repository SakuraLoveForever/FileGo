"""
Windows 自启动服务 — 通过注册表 Run 键管理
"""

import sys
import winreg

from config import logger, APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _get_app_path() -> str:
    """获取当前应用程序的路径用于注册表。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包的 exe
        return sys.executable
    else:
        # 开发模式 — 使用 pythonw.exe 运行 main.py
        import os
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # 回退到 python.exe
        main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "main.py")
        main_py = os.path.abspath(main_py)
        return f'"{pythonw}" "{main_py}" --hidden'


def is_enabled() -> bool:
    """检查自启动是否已启用。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return bool(value)
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.error(f"检查自启动状态失败: {e}")
        return False


def enable() -> None:
    """启用自启动。"""
    try:
        app_path = _get_app_path()
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, app_path)
        winreg.CloseKey(key)
        logger.info(f"已启用自启动: {app_path}")
    except OSError as e:
        logger.error(f"启用自启动失败: {e}")
        raise


def disable() -> None:
    """禁用自启动。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, APP_NAME)
            logger.info("已禁用自启动")
        except FileNotFoundError:
            pass  # 本来就没有，忽略
        winreg.CloseKey(key)
    except OSError as e:
        logger.error(f"禁用自启动失败: {e}")
        raise
