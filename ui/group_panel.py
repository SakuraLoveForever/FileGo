"""
GroupPanel — 单个任务组的可滚动面板（ttkbootstrap 美化版）
"""

import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Callable

from models.task import Task
from models.task_group import TaskGroup
from ui.dialogs import TaskEditDialog
from ui.task_row import TaskRow


class GroupPanel(ttk.Frame):
    """任务组面板：任务卡片列表 + 日志。"""

    def __init__(self, parent, group: TaskGroup, callbacks: dict):
        super().__init__(parent)
        self.group = group
        self._callbacks = callbacks
        self._task_rows: dict[str, TaskRow] = {}
        self._build()

    def _build(self):
        """构建面板 UI。"""
        # 顶部工具栏
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill=X)

        ttk.Button(toolbar, text="＋ 添加任务", bootstyle="success",
                   command=self._on_add_task).pack(side=LEFT)
        ttk.Button(toolbar, text="▶ 运行全部", bootstyle="primary-outline",
                   command=self._on_run_all).pack(side=LEFT, padx=(8, 0))

        self._count_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self._count_var,
                  bootstyle="secondary", font=("", 9)).pack(side=RIGHT, padx=5)

        ttk.Separator(self, bootstyle="default").pack(fill=X, padx=5)

        # 可滚动任务列表
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=BOTH, expand=True, padx=5, pady=2)

        self._canvas = tk.Canvas(canvas_frame, highlightthickness=0,
                                 bg=self._get_bg_color())
        scrollbar = ttk.Scrollbar(canvas_frame, orient=VERTICAL,
                                  command=self._canvas.yview, bootstyle="round")
        self._scroll_frame = ttk.Frame(self._canvas)

        self._scroll_frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor=NW)

        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side=RIGHT, fill=Y)

        self._canvas.bind("<Configure>", self._on_canvas_resize)
        # 鼠标滚轮支持
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))

        # 日志区域
        ttk.Separator(self, bootstyle="default").pack(fill=X, padx=5)
        log_frame = ttk.Labelframe(self, text=" 运行日志 ", padding=5, bootstyle="default")
        log_frame.pack(fill=BOTH, padx=5, pady=(2, 5), expand=False)

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill=BOTH, expand=True)

        self._log_text = tk.Text(log_inner, height=5, state=DISABLED,
                                 font=("Consolas", 8), wrap=WORD,
                                 bg="#1e1e1e", fg="#d4d4d4",
                                 insertbackground="white",
                                 relief=FLAT, borderwidth=0)
        self._log_text.pack(side=LEFT, fill=BOTH, expand=True)

    def _get_bg_color(self):
        """获取当前主题的背景色。"""
        try:
            return self.master.master.style.colors.get("bg", "#f5f5f5")
        except Exception:
            return "#f5f5f5"

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh(self):
        """重建任务行列表。"""
        for row in self._task_rows.values():
            row.destroy()
        self._task_rows.clear()

        row_callbacks = {
            "on_run": self._on_run_task,
            "on_edit": self._on_edit_task,
            "on_delete": self._on_delete_task,
            "on_toggle": self._on_toggle_task,
        }

        for task in self.group.tasks:
            row = TaskRow(self._scroll_frame, task, row_callbacks)
            row.pack(fill=X, padx=3, pady=2)
            self._task_rows[task.task_id] = row

        self._update_count()

    def _update_count(self):
        enabled = len(self.group.get_enabled_tasks())
        total = len(self.group.tasks)
        self._count_var.set(f"{enabled}/{total} 个已启用")

    def update_task_row(self, task: Task):
        if task.task_id in self._task_rows:
            self._task_rows[task.task_id].update_display(task)

    def add_log(self, message: str):
        self._log_text.config(state=NORMAL)
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.insert(END, f"[{ts}] {message}\n")
        lines = int(self._log_text.index("end-1c").split(".")[0])
        if lines > 500:
            self._log_text.delete("1.0", f"{lines - 500}.0")
        self._log_text.see(END)
        self._log_text.config(state=DISABLED)

    # ---- 回调 ----

    def _on_add_task(self):
        dialog = TaskEditDialog(self.winfo_toplevel())
        if dialog.result:
            self._callbacks.get("on_add", lambda t: None)(dialog.result)

    def _on_run_all(self):
        self._callbacks.get("on_run_all", lambda: None)()

    def _on_run_task(self, task: Task):
        self._callbacks.get("on_run", lambda t: None)(task)

    def _on_edit_task(self, task: Task):
        dialog = TaskEditDialog(self.winfo_toplevel(), task)
        if dialog.result:
            self._callbacks.get("on_edit", lambda t: None)(dialog.result)

    def _on_delete_task(self, task: Task):
        self._callbacks.get("on_delete", lambda t: None)(task)

    def _on_toggle_task(self, task: Task):
        self._callbacks.get("on_toggle", lambda t: None)(task)
