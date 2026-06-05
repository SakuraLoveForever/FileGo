"""
调度器线程 — 睡眠轮询，到期时触发任务执行
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Callable, List

from config import logger
from models.task import Task
from models.task_group import TaskGroup


class Scheduler(threading.Thread):
    """后台线程：轮询所有任务，到期时入队执行。"""

    def __init__(
        self,
        groups_provider: Callable[[], List[TaskGroup]],
        executor: "Executor",  # noqa: F821
        config: dict,
    ):
        super().__init__(daemon=True, name="FileGo-Scheduler")
        self._groups_provider = groups_provider
        self._executor = executor
        self._config = config
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._lock = threading.Lock()
        self._on_status: Callable[[str], None] | None = None  # 状态回调

    def set_status_callback(self, cb: Callable[[str], None]) -> None:
        """设置状态栏更新回调。"""
        self._on_status = cb

    def run(self) -> None:
        """主调度循环。"""
        logger.info("调度器线程已启动")
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.exception(f"调度器循环异常: {e}")
                time.sleep(5)

        logger.info("调度器线程已停止")

    def _tick(self) -> None:
        """单次调度循环。"""
        groups = self._groups_provider()
        now = datetime.now()
        next_event_info = ""  # 状态栏显示
        min_next_run = None

        with self._lock:
            for group in groups:
                for task in group.tasks:
                    if not task.enabled:
                        continue

                    # 解析 next_run
                    next_run = None
                    if task.next_run:
                        try:
                            next_run = datetime.fromisoformat(task.next_run)
                        except (ValueError, TypeError):
                            pass

                    # 如果 next_run 为空，根据调度类型计算
                    if next_run is None and task.schedule_type != "manual":
                        next_run = task.compute_next_run(now)
                        if next_run:
                            task.next_run = next_run.isoformat()

                    if next_run is None:
                        continue

                    # 检查是否到期
                    if next_run <= now:
                        logger.debug(f"任务到期: {(task.task_id or "?")[:8]} ({group.name})")
                        self._executor.enqueue(task, group, run_skipped=False)
                        # 计算下次运行时间
                        new_next = task.compute_next_run(now)
                        task.next_run = new_next.isoformat() if new_next else None
                        # 立即检查是否再次到期（间隔可能很短）
                        if new_next and new_next <= now:
                            new_next = None
                        next_run = new_next

                    # 跟踪最近的下次运行
                    if next_run:
                        if min_next_run is None or next_run < min_next_run:
                            min_next_run = next_run
                            if task.schedule_type == "daily":
                                next_event_info = (
                                    f"下次: {next_run.strftime('%m-%d %H:%M')} "
                                    f"({group.name}/{task.source[:20]})"
                                )
                            else:
                                next_event_info = (
                                    f"下次: {next_run.strftime('%H:%M:%S')} "
                                    f"({group.name}/{task.source[:20]})"
                                )

        # 更新状态栏
        if self._on_status:
            if next_event_info:
                self._on_status(next_event_info)
            else:
                self._on_status("无待执行任务")

        # 计算睡眠时间
        poll_interval = self._config.get("poll_interval_seconds", 15)
        sleep_duration = poll_interval

        if min_next_run:
            remaining = (min_next_run - datetime.now()).total_seconds()
            if remaining > 0:
                sleep_duration = min(remaining, poll_interval, 300)  # 上限 5 分钟

        sleep_duration = max(1.0, sleep_duration)  # 至少 1 秒

        # 等待
        self._wake_event.wait(timeout=sleep_duration)
        self._wake_event.clear()

    def wake(self) -> None:
        """立即唤醒调度器（用于手动触发后重新计算）。"""
        self._wake_event.set()

    def stop(self) -> None:
        """停止调度器。"""
        self._stop_event.set()
        self._wake_event.set()  # 唤醒以退出
