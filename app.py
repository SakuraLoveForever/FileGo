"""
App — 应用程序根对象，连接所有组件并管理生命周期
"""

import socket
import threading
from datetime import datetime
from typing import List

from config import logger, STATUS_SUCCESS
from models.task import Task
from models.task_group import TaskGroup
from persistence.store import Store
from scheduler.engine import Scheduler
from scheduler.executor import Executor
from services.single_instance import start_listener
from ui.main_window import MainWindow

try:
    from ui.tray import TrayIcon
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


class App:
    """FileGo 应用程序根对象。"""

    def __init__(self):
        self.store = Store()
        self.groups: List[TaskGroup] = []
        self.config: dict = {}

        # 线程组件
        self.executor: Executor | None = None
        self.scheduler: Scheduler | None = None
        self.tray_icon: TrayIcon | None = None

        # UI
        self.main_window: MainWindow | None = None

        # 线程安全锁
        self._groups_lock = threading.Lock()

        # 单实例锁
        self._lock_socket: socket.socket | None = None
        self._lock_thread = None

        # 加载数据
        self._load_data()

    def _load_data(self):
        """加载任务和配置。"""
        logger.info("加载数据...")
        self.config = self.store.load_config()
        self.groups = self.store.load_groups()
        logger.info(f"已加载 {len(self.groups)} 个组, 配置={len(self.config)} 项")

        # 初始化所有任务的 next_run
        now = datetime.now()
        for group in self.groups:
            for task in group.tasks:
                if task.enabled and task.next_run is None:
                    next_run = task.compute_next_run(now)
                    if next_run:
                        task.next_run = next_run.isoformat()
                        logger.debug(
                            f"初始化 next_run: {(task.task_id or '?')[:8]} → {task.next_run}"
                        )

        # 保存初始化的 next_run
        self.save_state()

    def set_lock_socket(self, sock: socket.socket):
        """设置单实例锁 socket 并启动监听。"""
        self._lock_socket = sock

    def run(self, start_hidden: bool = False):
        """启动应用程序。"""
        logger.info("FileGo 启动中...")

        # 创建执行器
        self.executor = Executor(on_result=self._on_task_result)
        self.executor.start()

        # 创建调度器
        self.scheduler = Scheduler(
            groups_provider=self._get_groups_snapshot,
            executor=self.executor,
            config=self.config,
        )
        self.scheduler.start()

        # 创建主窗口
        self.main_window = MainWindow(self)

        # 设置调度器状态回调
        self.scheduler.set_status_callback(self.main_window._set_status)

        # 单实例锁监听（收到新实例时显示窗口）
        if self._lock_socket:
            self._lock_thread = start_listener(
                self._lock_socket,
                on_show=lambda: self.main_window.root.after(
                    0, self.main_window.restore_from_tray
                ),
            )

        # 系统托盘
        if HAS_TRAY:
            self._setup_tray()

        # 显示窗口并进入事件循环
        self.main_window.show(start_hidden=start_hidden)

    def _setup_tray(self):
        """初始化系统托盘。"""
        self.tray_icon = TrayIcon()
        self.tray_icon.set_callbacks({
            "on_show": self.main_window.restore_from_tray,
            "on_run_all": self.main_window._on_run_all,
            "on_exit": self.shutdown,
        })
        self.tray_icon.setup()

    def _get_groups_snapshot(self) -> List[TaskGroup]:
        """获取任务组的快照（线程安全）。"""
        with self._groups_lock:
            return list(self.groups)

    def _on_task_result(self, task: Task, group: TaskGroup, success: bool, message: str):
        """任务执行结果回调。"""
        try:
            self._do_on_task_result(task, group, success, message)
        except Exception as e:
            import traceback
            logger.error(f"_on_task_result 异常:\n{traceback.format_exc()}")

    def _do_on_task_result(self, task: Task, group: TaskGroup, success: bool, message: str):
        with self._groups_lock:
            now = datetime.now()

            if message == "running":
                # 正在运行
                task.last_status = "running"
            else:
                task.last_run = now.isoformat()
                task.last_status = STATUS_SUCCESS if success else f"error: {message}"

                # 计算下次运行
                next_run = task.compute_next_run(now)
                task.next_run = next_run.isoformat() if next_run else None

            # 保存状态
            try:
                self.store.save_groups(self.groups)
            except OSError as e:
                logger.error(f"保存任务状态失败: {e}")

        # 通知 UI（在 GUI 线程中）
        if self.main_window and self.main_window.root:
            self.main_window.root.after(
                0, self.main_window.on_task_result, task, group, success, message
            )

    def save_state(self):
        """保存当前状态（任务 + 配置）。"""
        with self._groups_lock:
            try:
                self.store.save_groups(self.groups)
            except OSError as e:
                logger.error(f"保存任务失败: {e}")

    def save_config(self):
        """保存配置。"""
        try:
            self.store.save_config(self.config)
        except OSError as e:
            logger.error(f"保存配置失败: {e}")

    def shutdown(self):
        """安全关闭应用程序。"""
        logger.info("FileGo 正在关闭...")

        # 1. 停止调度器
        if self.scheduler:
            logger.info("停止调度器...")
            self.scheduler.stop()

        # 2. 停止执行器
        if self.executor:
            logger.info("停止执行器...")
            self.executor.stop()

        # 3. 保存最终状态
        with self._groups_lock:
            try:
                self.store.save_groups(self.groups)
                logger.info("已保存最终状态")
            except OSError as e:
                logger.error(f"保存最终状态失败: {e}")

        # 4. 停止托盘
        if self.tray_icon:
            self.tray_icon.stop()

        # 5. 关闭单实例锁
        if self._lock_socket:
            try:
                self._lock_socket.close()
            except Exception:
                pass

        # 6. 销毁 UI
        if self.main_window:
            self.main_window.destroy()

        logger.info("FileGo 已关闭")
