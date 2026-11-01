"""
TaskRow — 单个任务在列表中的显示行（ttkbootstrap 美化版）
"""

import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.tooltip import ToolTip

from config import (
    SCHEDULE_INTERVAL,
    SCHEDULE_DAILY,
    SCHEDULE_MANUAL,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    BACKUP_FOLDER,
)
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
        self._displayed_paths = None
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

        # 每组复制关系分为来源、目标两行，路径可横向滚动和复制。
        self._paths_frame = ttk.Frame(self)
        self._paths_frame.pack(fill=X, padx=(22, 0), pady=(6, 0))
        self._paths_frame.columnconfigure(1, weight=1)

        # 信息行：调度信息 + 上次运行 + 下次运行
        info = ttk.Frame(self)
        info.pack(fill=X, pady=(5, 0))

        if self.task.schedule_type == SCHEDULE_INTERVAL:
            sched_text = f"⏱ 每 {self.task.schedule_value} 分钟"
        elif self.task.schedule_type == SCHEDULE_DAILY:
            sched_text = f"🕐 每日 {self.task.schedule_value}"
        else:
            sched_text = "👆 仅手动"

        if BACKUP_FOLDER in self.task.source_modes:
            ttk.Label(info, text=self.task.mode_label, bootstyle="info", font=("", 8)).pack(
                side=LEFT, padx=(22, 5))

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

        # 源 → 目标 配对摘要
        srcs = task.sources if isinstance(task.sources, list) else []
        dsts = task.dests if isinstance(task.dests, list) else []
        sc = len([s for s in srcs if isinstance(s, str) and s.strip()])
        dc = len([d for d in dsts if isinstance(d, str) and d.strip()])
        if task.pair_count == 0:
            self._pair_info_var.set("未配置")
        elif sc != dc:
            self._pair_info_var.set(f"⚠ {sc}源 ≠ {dc}目标，需按序号配对")
        else:
            self._pair_info_var.set(f"🔗 {task.pair_count} 组 1对1 复制")

        paths = (tuple(srcs), tuple(dsts))
        if paths != self._displayed_paths:
            self._displayed_paths = paths
            for widget in self._paths_frame.winfo_children():
                widget.destroy()
            for i in range(max(len(srcs), len(dsts))):
                source = srcs[i] if i < len(srcs) else ""
                dest = dsts[i] if i < len(dsts) else ""
                if not source.strip() and not dest.strip():
                    continue
                for offset, (label, path) in enumerate((("来源", source), ("目标", dest))):
                    row = i * 2 + offset
                    pady = (6 if i and offset == 0 else 1, 1)
                    ttk.Label(self._paths_frame, text=f"#{i + 1} {label}",
                              bootstyle="secondary", font=("", 9)).grid(
                        row=row, column=0, sticky=W, padx=(0, 8), pady=pady)
                    entry = ttk.Entry(self._paths_frame, width=1, font=("", 9))
                    entry.insert(0, path or "未配置")
                    entry.configure(state="readonly")
                    entry.grid(row=row, column=1, sticky=EW, pady=pady)
                    ToolTip(entry, text=path or "未配置")
                    button = ttk.Button(
                        self._paths_frame, text="打开", width=4,
                        bootstyle="secondary-outline", padding=(4, 1),
                        state=NORMAL if path.strip() else DISABLED,
                        command=lambda p=path: self._open_location(p))
                    button.grid(row=row, column=2, padx=(6, 0), pady=pady)
                    ToolTip(button, text="在文件资源管理器中打开位置")

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

    def _open_location(self, path: str):
        """文件选中定位，文件夹直接打开；通配符定位到所在文件夹。"""
        try:
            location = Path(os.path.abspath(path))
            if "*" in path or "?" in path:
                while "*" in str(location) or "?" in str(location):
                    location = location.parent
            if location.is_dir():
                os.startfile(str(location))
            elif location.is_file():
                subprocess.Popen(["explorer.exe", f"/select,{location}"])
            else:
                messagebox.showwarning("无法打开位置", f"路径不存在：\n{path}", parent=self)
        except OSError as exc:
            messagebox.showwarning("无法打开位置", str(exc), parent=self)

    def _on_toggle(self):
        self._callbacks.get("on_toggle", lambda t: None)(self.task)

    def _on_run(self):
        self._callbacks.get("on_run", lambda t: None)(self.task)

    def _on_edit(self):
        self._callbacks.get("on_edit", lambda t: None)(self.task)

    def _on_delete(self):
        pairs_info = f"{self.task.pair_count} 组 1对1 复制" if self.task.pair_count > 0 else "无文件"
        if messagebox.askyesno("确认删除",
                               f"确定要删除任务 [{self.task.name}] 吗？\n\n{pairs_info}\n\n此操作不可撤销。"):
            self._callbacks.get("on_delete", lambda t: None)(self.task)
