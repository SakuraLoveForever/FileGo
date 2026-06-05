"""
FileGo — 全局常量、路径和日志配置
"""

import os
import logging
from pathlib import Path

APP_NAME = "FileGo"
APP_VERSION = "1.0.0"

# 数据目录：%USERPROFILE%\.filego
DATA_DIR = Path(os.path.expanduser("~")) / ".filego"
TASKS_FILE = DATA_DIR / "tasks.json"
CONFIG_FILE = DATA_DIR / "config.json"
LOG_FILE = DATA_DIR / "filego.log"

# 日志格式
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 默认配置
DEFAULT_CONFIG = {
    "schema_version": 1,
    "poll_interval_seconds": 15,
    "autostart_enabled": False,
    "minimize_to_tray": False,
    "close_to_tray": True,
    "window_geometry": "950x650+100+100",
    "notify_on_success": False,
    "notify_on_failure": True,
    "max_log_lines_per_group": 500,
}

# 默认任务组（首次运行）
DEFAULT_TASKS = {
    "schema_version": 1,
    "groups": [],
}

# 调度类型
SCHEDULE_INTERVAL = "interval"  # 每 N 分钟
SCHEDULE_DAILY = "daily"        # 每日定时
SCHEDULE_MANUAL = "manual"      # 仅手动

SCHEDULE_TYPES = [SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_MANUAL]

# 任务状态
STATUS_IDLE = "idle"
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_RUNNING = "running"


def setup_logging():
    """初始化日志系统。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)

    # 文件处理器
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(fh)

    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    logger.addHandler(ch)

    return logger


logger = setup_logging()
