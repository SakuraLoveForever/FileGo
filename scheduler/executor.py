"""
执行器线程 — 从队列中取出任务，执行源×目标全量复制
"""

import queue
import threading
import traceback
from typing import Callable

from config import logger, STATUS_RUNNING
from models.task import Task
from models.task_group import TaskGroup
from services.file_copy import copy_all


class Executor(threading.Thread):
    """后台线程：消费任务队列，执行 M×N 全量复制。"""

    def __init__(self, on_result: Callable[[Task, TaskGroup, bool, str], None]):
        super().__init__(daemon=True, name="FileGo-Executor")
        self._queue: queue.Queue = queue.Queue()
        self._on_result = on_result
        self._stop_event = threading.Event()
        self._running_event = threading.Event()

    def run(self) -> None:
        logger.info("执行器线程已启动")
        while not self._stop_event.is_set():
            try:
                task, group, run_skipped = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if task is None:
                break

            self._running_event.set()
            try:
                self._execute(task, group, run_skipped)
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"执行异常详情:\n{tb}")
                self._on_result(task, group, False, f"异常: {e}")
            finally:
                self._queue.task_done()
                self._running_event.clear()

        logger.info("执行器线程已停止")

    def _execute(self, task: Task, group: TaskGroup, run_skipped: bool) -> None:
        if not run_skipped and not task.enabled:
            return

        combos = task.total_combinations
        logger.info(f"执行: [{task.name}] {len(task.sources)}源×{len(task.dests)}目标 = {combos}次复制")
        self._on_result(task, group, True, STATUS_RUNNING)

        result = copy_all(task.sources, task.dests)

        if result.success:
            logger.info(f"成功: {(task.task_id or "?")[:8]} — {result.message}")
        else:
            logger.error(f"失败: {(task.task_id or "?")[:8]} — {result.message}")

        self._on_result(task, group, result.success, result.message)

    def enqueue(self, task: Task, group: TaskGroup, run_skipped: bool = False) -> None:
        self._queue.put((task, group, run_skipped))

    def stop(self) -> None:
        """停止执行器（非阻塞，安全可在 GUI 线程调用）。

        发送停止信号和哨兵值后立即返回。
        正在运行的任务由 daemon 线程自然终止。
        """
        self._stop_event.set()
        try:
            self._queue.put((None, None, False))  # 哨兵，打破 run() 中的循环
        except Exception:
            pass
