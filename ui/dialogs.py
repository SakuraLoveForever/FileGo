"""
对话框 — 任务编辑（源列表 × 目标列表）、组编辑、设置
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Optional, List

from config import SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_MANUAL
from models.task import Task
from models.task_group import TaskGroup


class PathListEditor(ttk.Labelframe):
    """可编辑的路径列表 — 带添加/删除按钮的路径条目集合。"""

    def __init__(self, parent, title: str, paths: List[str], browse_dir: bool = False, **kw):
        super().__init__(parent, text=title, padding=8, **kw)
        self._paths: List[tk.StringVar] = []
        self._rows: List[ttk.Frame] = []
        self._browse_dir = browse_dir
        self._container = ttk.Frame(self)
        self._container.pack(fill=X)

        # 初始化行
        for p in paths:
            self._add_row(p)

        # 如果没有行，至少加一行
        if not self._paths:
            self._add_row("")

        # 添加按钮
        ttk.Button(self, text=f"＋ 添加{title}", bootstyle="success-outline",
                   command=lambda: self._add_row("")).pack(anchor=W, pady=(8, 0))

    def _add_row(self, value: str):
        var = tk.StringVar(value=value)
        self._paths.append(var)
        idx = len(self._paths) - 1

        row = ttk.Frame(self._container)
        row.pack(fill=X, pady=2)

        ttk.Label(row, text=f"#{idx + 1}", font=("", 8, "bold"),
                  bootstyle="secondary", width=3).pack(side=LEFT, padx=(0, 5))
        ttk.Entry(row, textvariable=var, width=50).pack(side=LEFT, fill=X, expand=True, padx=(0, 3))
        ttk.Button(row, text="📂", width=3, bootstyle="outline-secondary",
                   command=lambda v=var: self._browse(v)).pack(side=LEFT, padx=(0, 3))
        ttk.Button(row, text="✕", width=3, bootstyle="danger-outline",
                   command=lambda r=row, v=var: self._remove_row(r, v)).pack(side=LEFT)

        self._rows.append(row)

    def _remove_row(self, row: ttk.Frame, var: tk.StringVar):
        if len(self._paths) <= 1:
            messagebox.showwarning("提示", "至少保留一个路径", parent=self.winfo_toplevel())
            return
        idx = self._paths.index(var)
        self._paths.pop(idx)
        row.destroy()
        self._rows.remove(row)
        self._renumber()

    def _renumber(self):
        for i, row in enumerate(self._rows):
            for child in row.winfo_children():
                if isinstance(child, ttk.Label) and child.cget("text").startswith("#"):
                    child.configure(text=f"#{i + 1}")
                    break

    def _browse(self, var: tk.StringVar):
        if self._browse_dir:
            path = filedialog.askdirectory(title="选择目录")
        else:
            path = filedialog.askopenfilename(title="选择文件")
            if not path:
                path = filedialog.askdirectory(title="选择目录")
        if path:
            var.set(path)

    def get_paths(self) -> List[str]:
        return [v.get().strip() for v in self._paths]


class TaskEditDialog(tk.Toplevel):
    """添加/编辑任务 — 源列表 × 目标列表，全量复制。"""

    def __init__(self, parent, task: Optional[Task] = None):
        super().__init__(parent)
        self.title("编辑任务" if task else "新建任务")
        self.resizable(True, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[Task] = None
        self._editing = task

        self._name_var = tk.StringVar(value=task.name if task else "")
        self._enabled_var = tk.BooleanVar(value=task.enabled if task else True)
        self._type_var = tk.StringVar(value=task.schedule_type if task else SCHEDULE_INTERVAL)

        # 解析 HH:MM 为分离的小时/分钟
        if task and task.schedule_type == SCHEDULE_DAILY:
            try:
                h, m = task.schedule_value.split(":")
                self._hour_var = tk.IntVar(value=int(h))
                self._min_var = tk.IntVar(value=int(m))
            except (ValueError, TypeError):
                self._hour_var = tk.IntVar(value=0)
                self._min_var = tk.IntVar(value=0)
        else:
            self._hour_var = tk.IntVar(value=0)
            self._min_var = tk.IntVar(value=0)

        # interval 值
        int_val = "60"
        if task and task.schedule_type == SCHEDULE_INTERVAL:
            int_val = task.schedule_value
        self._interval_var = tk.StringVar(value=int_val)

        self._src_editor = None
        self._dst_editor = None
        self._value_frame = None  # 动态切换的容器

        self._build(task)
        self._on_type_change()

        self.update_idletasks()
        self._center()
        self.wait_window()

    def _center(self):
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self, task: Optional[Task]):
        outer = ttk.Frame(self, padding=20)
        outer.pack(fill=BOTH, expand=True)

        # ── 任务名称 ──
        ttk.Label(outer, text="任务名称", font=("", 9, "bold"), bootstyle="primary").pack(anchor=W)
        ttk.Entry(outer, textvariable=self._name_var,
                  font=("", 10), width=40).pack(fill=X, pady=(3, 12))

        # ── 源路径 + 目标路径 并排 ──
        columns = ttk.Frame(outer)
        columns.pack(fill=X)

        # 左列：源路径
        src_col = ttk.Frame(columns)
        src_col.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 5))

        src_paths = task.sources if task else [""]
        self._src_editor = PathListEditor(src_col, "📄 源路径", src_paths,
                                          browse_dir=False, bootstyle="default")
        self._src_editor.pack(fill=X)

        # 中间：× 符号
        mid = ttk.Frame(columns, width=40)
        mid.pack(side=LEFT, fill=Y)
        mid.pack_propagate(False)
        ttk.Label(mid, text="", font=("", 4)).pack()
        ttk.Label(mid, text="×", font=("", 16, "bold"), bootstyle="info").pack(expand=True)

        # 右列：目标路径
        dst_col = ttk.Frame(columns)
        dst_col.pack(side=LEFT, fill=BOTH, expand=True, padx=(5, 0))

        dst_paths = task.dests if task else [""]
        self._dst_editor = PathListEditor(dst_col, "📁 目标路径", dst_paths,
                                          browse_dir=True, bootstyle="default")
        self._dst_editor.pack(fill=X)

        # ── 说明 ──
        ttk.Label(outer, text="每个源路径都会分别复制到所有目标路径",
                  bootstyle="secondary", font=("", 8, "italic")).pack(pady=(5, 10))

        ttk.Separator(outer, bootstyle="default").pack(fill=X, pady=5)

        # ── 调度设置 ──
        sched_frame = ttk.Labelframe(outer, text="调度设置", padding=10, bootstyle="default")
        sched_frame.pack(fill=X, pady=(5, 10))

        # 类型选择行
        type_row = ttk.Frame(sched_frame)
        type_row.pack(fill=X)

        ttk.Label(type_row, text="类型:", width=8).pack(side=LEFT)
        ttk.Combobox(type_row, textvariable=self._type_var, width=12, state="readonly",
                     values=[SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_MANUAL],
                     bootstyle="primary").pack(side=LEFT, padx=(5, 10))

        ttk.Label(type_row, text="值:", width=3).pack(side=LEFT, padx=(0, 5))

        # 动态值容器 — 根据类型切换不同控件
        self._value_frame = ttk.Frame(type_row)
        self._value_frame.pack(side=LEFT)

        # ---- interval 控件 (默认显示) ----
        self._interval_box = ttk.Frame(self._value_frame)
        self._int_spin = ttk.Spinbox(self._interval_box, textvariable=self._interval_var,
                                     from_=1, to=1440, increment=5, width=6, bootstyle="primary")
        self._int_spin.pack(side=LEFT)
        ttk.Label(self._interval_box, text=" 分钟", bootstyle="secondary").pack(side=LEFT)

        # ---- daily 控件 ----
        self._daily_box = ttk.Frame(self._value_frame)
        ttk.Label(self._daily_box, text="每天  ").pack(side=LEFT)
        self._hour_spin = ttk.Spinbox(self._daily_box, textvariable=self._hour_var,
                                      from_=0, to=23, increment=1, width=3, bootstyle="primary")
        self._hour_spin.pack(side=LEFT)
        ttk.Label(self._daily_box, text=" : ", font=("", 10, "bold")).pack(side=LEFT)
        self._min_spin = ttk.Spinbox(self._daily_box, textvariable=self._min_var,
                                     from_=0, to=59, increment=1, width=3, bootstyle="primary")
        self._min_spin.pack(side=LEFT)
        ttk.Label(self._daily_box, text="  时:分", bootstyle="secondary").pack(side=LEFT)

        # ---- manual 控件 ----
        self._manual_box = ttk.Frame(self._value_frame)
        ttk.Label(self._manual_box, text="(仅手动触发)", bootstyle="secondary").pack(side=LEFT)

        self._type_var.trace_add("write", lambda *a: self._on_type_change())

        ttk.Checkbutton(sched_frame, text="启用此任务",
                        variable=self._enabled_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=(8, 0))

        # ── 上次状态 ──
        if task and task.last_run:
            ttk.Separator(outer, bootstyle="default").pack(fill=X, pady=5)
            info = f"上次运行: {task.last_run[:19].replace('T', ' ')}    状态: {task.last_status}"
            ttk.Label(outer, text=info, bootstyle="secondary", font=("", 8)).pack(anchor=W)

        # ── 按钮 ──
        ttk.Separator(outer, bootstyle="default").pack(fill=X, pady=10)
        btns = ttk.Frame(outer)
        btns.pack(fill=X)
        ttk.Button(btns, text="取消", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btns, text="保存", bootstyle="primary", command=self._on_save).pack(side=RIGHT)

    def _on_type_change(self):
        st = self._type_var.get()
        # 隐藏所有
        for box in [self._interval_box, self._daily_box, self._manual_box]:
            box.pack_forget()

        if st == SCHEDULE_INTERVAL:
            self._interval_box.pack(side=LEFT)
        elif st == SCHEDULE_DAILY:
            self._daily_box.pack(side=LEFT)
        else:
            self._manual_box.pack(side=LEFT)

    def _on_save(self):
        # 根据类型获取调度值
        st = self._type_var.get()
        if st == SCHEDULE_INTERVAL:
            schedule_value = self._interval_var.get().strip()
        elif st == SCHEDULE_DAILY:
            schedule_value = f"{self._hour_var.get():02d}:{self._min_var.get():02d}"
        else:
            schedule_value = ""

        sources = self._src_editor.get_paths()
        dests = self._dst_editor.get_paths()

        task = Task(
            task_id=self._editing.task_id if self._editing else None,
            name=self._name_var.get().strip() or "新任务",
            sources=sources,
            dests=dests,
            enabled=self._enabled_var.get(),
            schedule_type=st,
            schedule_value=schedule_value,
            last_run=self._editing.last_run if self._editing else None,
            last_status=self._editing.last_status if self._editing else "idle",
            next_run=self._editing.next_run if self._editing else None,
        )

        errors = task.validate()
        if errors:
            messagebox.showwarning("验证失败", "\n".join(errors), parent=self)
            return

        self.result = task
        self.destroy()


class GroupEditDialog(tk.Toplevel):
    """添加/编辑任务组。"""

    def __init__(self, parent, group: Optional[TaskGroup] = None):
        super().__init__(parent)
        self.title("编辑组" if group else "新建组")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[str] = None
        self._name_var = tk.StringVar(value=group.name if group else "")
        self._build()
        self._center()
        self.wait_window()

    def _center(self):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        frame = ttk.Frame(self, padding=25)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="组名:", font=("", 10, "bold")).grid(row=0, column=0, sticky=W)
        entry = ttk.Entry(frame, textvariable=self._name_var, width=30, font=("", 10))
        entry.grid(row=0, column=1, sticky=EW, padx=(15, 0))
        entry.focus_set()

        btns = ttk.Frame(frame)
        btns.grid(row=1, column=0, columnspan=2, sticky=E, pady=(20, 0))
        ttk.Button(btns, text="取消", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btns, text="确定", bootstyle="primary", command=self._on_ok).pack(side=RIGHT)
        frame.columnconfigure(1, weight=1)

    def _on_ok(self):
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("验证失败", "组名不能为空", parent=self)
            return
        self.result = name
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """设置对话框。"""

    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("设置")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._config = config.copy()
        self._on_save = on_save

        self._poll_var = tk.IntVar(value=config.get("poll_interval_seconds", 15))
        self._close_tray_var = tk.BooleanVar(value=config.get("close_to_tray", True))
        self._minimize_tray_var = tk.BooleanVar(value=config.get("minimize_to_tray", False))
        self._notify_success_var = tk.BooleanVar(value=config.get("notify_on_success", False))
        self._notify_failure_var = tk.BooleanVar(value=config.get("notify_on_failure", True))

        from services.autostart import is_enabled as check_autostart
        self._autostart_var = tk.BooleanVar(value=check_autostart())

        self._build()
        self._center()
        self.wait_window()

    def _center(self):
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_rootx()
        py = self.master.winfo_rooty()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        frame = ttk.Frame(self, padding=25)
        frame.pack(fill=BOTH, expand=True)

        ttk.Label(frame, text="调度器", font=("", 10, "bold"), bootstyle="primary").pack(anchor=W)
        sf = ttk.Frame(frame)
        sf.pack(fill=X, pady=(5, 10))
        ttk.Label(sf, text="轮询间隔(秒):").pack(side=LEFT)
        ttk.Spinbox(sf, textvariable=self._poll_var, from_=5, to=3600,
                    width=8, bootstyle="primary").pack(side=LEFT, padx=(10, 0))

        ttk.Separator(frame, bootstyle="default").pack(fill=X, pady=5)

        ttk.Label(frame, text="行为", font=("", 10, "bold"), bootstyle="primary").pack(anchor=W)
        opts = ttk.Frame(frame)
        opts.pack(fill=X, pady=(5, 10))
        ttk.Checkbutton(opts, text="关闭窗口时最小化到系统托盘",
                        variable=self._close_tray_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=2)
        ttk.Checkbutton(opts, text="启动时最小化到系统托盘",
                        variable=self._minimize_tray_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=2)
        ttk.Checkbutton(opts, text="开机自启动（随 Windows 启动）",
                        variable=self._autostart_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=2)

        ttk.Separator(frame, bootstyle="default").pack(fill=X, pady=5)

        ttk.Label(frame, text="通知", font=("", 10, "bold"), bootstyle="primary").pack(anchor=W)
        nf = ttk.Frame(frame)
        nf.pack(fill=X, pady=(5, 10))
        ttk.Checkbutton(nf, text="复制成功时通知",
                        variable=self._notify_success_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=2)
        ttk.Checkbutton(nf, text="复制失败时通知",
                        variable=self._notify_failure_var,
                        bootstyle="primary-round-toggle").pack(anchor=W, pady=2)

        ttk.Separator(frame, bootstyle="default").pack(fill=X, pady=10)

        btns = ttk.Frame(frame)
        btns.pack(fill=X)
        ttk.Button(btns, text="取消", bootstyle="secondary", command=self.destroy).pack(side=RIGHT, padx=(5, 0))
        ttk.Button(btns, text="保存", bootstyle="primary", command=self._on_save_clicked).pack(side=RIGHT)

    def _on_save_clicked(self):
        self._config["poll_interval_seconds"] = self._poll_var.get()
        self._config["close_to_tray"] = self._close_tray_var.get()
        self._config["minimize_to_tray"] = self._minimize_tray_var.get()
        self._config["notify_on_success"] = self._notify_success_var.get()
        self._config["notify_on_failure"] = self._notify_failure_var.get()
        self._config["autostart_enabled"] = self._autostart_var.get()

        from services.autostart import enable as enable_autostart, disable as disable_autostart
        try:
            if self._autostart_var.get():
                enable_autostart()
            else:
                disable_autostart()
        except OSError as e:
            messagebox.showwarning("自启动设置失败", str(e), parent=self)

        self._on_save(self._config)
        self.destroy()
