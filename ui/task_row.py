"""
TaskRow — 单个任务在列表中的显示行（ttkbootstrap 美化版）
"""

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config import SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_MANUAL, STATUS_RUNNING, STATUS_SUCCESS
from models.task import Task


class TaskRow(ttk.Frame):
    """任务列表中的单行卡片控件。"""

    STATUS_MAP = {
        "idle": "secondary",
        "success": "success",
        "running": "info",
    }

    def __init__(self, parent, task: Task, callbacks: dict):
        super().__init__(parent, padding=8)
        self.task = task
        self._callbacks = callbacks

        self._enabled_var = tk.BooleanVar(value=task.enabled)
        self._status_var = tk.StringVar()
        self._next_run_var = tk.StringVar()
        self._pair_info_var = tk.StringVar()
        self._build()

    def _build(self):
        """构建卡片式行 UI。"""
        # 主行：启用 + 名称 + 配对信息 + 状态 + 按钮
        main = ttk.Frame(self)
        main.pack(fill=X)
        main.columnconfigure(2, weight=1)

        # 启用开关
        ttk.Checkbutton(main, variable=self._enabled_var,
                        command=self._on_toggle, bootstyle="primary-round-toggle").grid(
            row=0, column=0, padx=(0, 8))

        # 任务名称
        name_lbl = ttk.Label(main, text=self.task.name, font=("", 10, "bold"))
        name_lbl.grid(row=0, column=1, sticky=W, padx=(0, 10))

        # 配对信息
        ttk.Label(main, textvariable=self._pair_info_var,
                  bootstyle="secondary", font=("", 8)).grid(
            row=0, column=2, sticky=W)

        # 状态
        status_frame = ttk.Frame(main)
        status_frame.grid(row=0, column=3, padx=5)

        self._status_badge = ttk.Label(status_frame, textvariable=self._status_var,
                                       font=("", 8), padding=(8, 2))
        self._status_badge.pack()

        # 按钮组
        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=0, column=4)

        ttk.Button(btn_frame, text="▶ 运行", bootstyle="success-outline",
                   command=self._on_run, width=7).pack(side=LEFT, padx=2)
        ttk.Button(btn_frame, text="编辑", bootstyle="primary-outline",
                   command=self._on_edit, width=5).pack(side=LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", bootstyle="danger-outline",
                   command=self._on_delete, width=5).pack(side=LEFT, padx=2)

        # 信息行：调度信息 + 上次运行 + 下次运行
        info = ttk.Frame(self)
        info.pack(fill=X, pady=(5, 0))

        if self.task.schedule_type == SCHEDULE_INTERVAL:
            sched_text = f"⏱ 每 {self.task.schedule_value} 分钟"
        elif self.task.schedule_type == SCHEDULE_DAILY:
            sched_text = f"🕐 每日 {self.task.schedule_value}"
        else:
            sched_text = "👆 仅手动"

        ttk.Label(info, text=sched_text, bootstyle="secondary", font=("", 8)).pack(
            side=LEFT, padx=(22, 15))

        if self.task.last_run:
            last_text = f"上次: {self.task.last_run[:16].replace('T', ' ')} "
            if self.task.last_status.startswith("success"):
                last_text += "✓"
                ttk.Label(info, text=last_text, bootstyle="success",
                          font=("", 8)).pack(side=LEFT, padx=5)
            elif self.task.last_status.startswith("error"):
                last_text += "✗"
                ttk.Label(info, text=last_text, bootstyle="danger",
                          font=("", 8)).pack(side=LEFT, padx=5)
            else:
                ttk.Label(info, text=last_text, bootstyle="secondary",
                          font=("", 8)).pack(side=LEFT, padx=5)

        ttk.Label(info, textvariable=self._next_run_var,
                  bootstyle="secondary", font=("", 8)).pack(side=RIGHT, padx=5)

        self.update_display(self.task)

    def update_display(self, task: Task):
        """根据最新任务数据更新显示。"""
        self.task = task
        self._enabled_var.set(task.enabled)

        # 源×目标 摘要
        srcs = task.sources if isinstance(task.sources, list) else []
        dsts = task.dests if isinstance(task.dests, list) else []
        sc = len([s for s in srcs if isinstance(s, str) and s.strip()])
        dc = len([d for d in dsts if isinstance(d, str) and d.strip()])
        if sc == 1 and dc == 1 and srcs:
            s = srcs[0] if srcs[0] else ""
            src = s if len(s) <= 30 else "..." + s[-27:]
            self._pair_info_var.set(f"📄 {src}")
        elif sc == 0 or dc == 0:
            self._pair_info_var.set("未配置")
        else:
            self._pair_info_var.set(f"📦 {sc}源 × {dc}目标 = {sc*dc}次复制")

        # 状态标签
        status = task.last_status
        if status == STATUS_RUNNING:
            self._status_var.set("⏳ 运行中")
            self._status_badge.configure(bootstyle="info")
        elif status == "idle":
            self._status_var.set("— 空闲")
            self._status_badge.configure(bootstyle="secondary")
        elif status.startswith("success"):
            self._status_var.set("✓ 成功")
            self._status_badge.configure(bootstyle="success")
        elif status.startswith("error"):
            self._status_var.set("✗ 失败")
            self._status_badge.configure(bootstyle="danger")
        else:
            self._status_var.set(status)
            self._status_badge.configure(bootstyle="secondary")

        # 下次运行
        if task.next_run:
            try:
                from datetime import datetime
                nr = datetime.fromisoformat(task.next_run)
                self._next_run_var.set(f"下次: {nr.strftime('%m-%d %H:%M')}")
            except (ValueError, TypeError):
                self._next_run_var.set("")
        else:
            if task.schedule_type == SCHEDULE_MANUAL:
                self._next_run_var.set("手动触发")
            elif not task.enabled:
                self._next_run_var.set("已禁用")
            else:
                self._next_run_var.set("等待调度...")

    def _on_toggle(self):
        self._callbacks.get("on_toggle", lambda t: None)(self.task)

    def _on_run(self):
        self._callbacks.get("on_run", lambda t: None)(self.task)

    def _on_edit(self):
        self._callbacks.get("on_edit", lambda t: None)(self.task)

    def _on_delete(self):
        pairs_info = f"{self.task.total_combinations} 次复制" if self.task.total_combinations > 0 else "无文件"
        if messagebox.askyesno("确认删除",
                               f"确定要删除任务 [{self.task.name}] 吗？\n\n{pairs_info}\n\n此操作不可撤销。"):
            self._callbacks.get("on_delete", lambda t: None)(self.task)
