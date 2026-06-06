"""
主窗口 — ttkbootstrap 现代主题，Notebook 标签页管理多任务组
"""

import tkinter as tk
from tkinter import messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import List

from config import logger, APP_NAME, APP_VERSION
from models.task import Task
from models.task_group import TaskGroup
from ui.group_panel import GroupPanel
from ui.dialogs import GroupEditDialog, SettingsDialog

try:
    from ui.tray import TrayIcon
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


class MainWindow:
    """应用程序主窗口 — ttkbootstrap 现代主题。"""

    def __init__(self, app: "App"):  # noqa: F821
        self.app = app

        # 使用 ttkbootstrap Window（带现代主题）
        self.root = ttk.Window(
            title=f"{APP_NAME} v{APP_VERSION}",
            themename="flatly",  # 现代扁平主题
            size=(1050, 720),
            iconphoto=None,
        )

        # 窗口居中
        self._center_window(1050, 720)

        # 面板缓存
        self._panels: dict[str, GroupPanel] = {}
        self._notebook: ttk.Notebook | None = None
        self._status_var = tk.StringVar(value="就绪")
        self._welcome_frame = None

        # 关闭行为
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 绑定托盘线程安全虚拟事件（event_generate 是 tkinter 唯一线程安全的方法）
        self.root.bind("<<TrayShow>>", lambda e: self.restore_from_tray())
        self.root.bind("<<TrayRunAll>>", lambda e: self._on_run_all())
        self.root.bind("<<TrayExit>>", lambda e: self.app.shutdown())

        self._build()
        self.refresh_all()
        self._schedule_refresh()
        self._schedule_autosave()
        self._hook_shutdown()

    def _center_window(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build(self):
        """构建主窗口 UI。"""
        # ---- 标题栏 ----
        title_bar = ttk.Frame(self.root, padding=(15, 10, 15, 8))
        title_bar.pack(fill=X)

        title_frame = ttk.Frame(title_bar)
        title_frame.pack(side=LEFT)
        ttk.Label(title_frame, text="📁 FileGo",
                  font=("", 16, "bold"), bootstyle="primary").pack(side=LEFT)
        ttk.Label(title_frame, text="  定时文件同步工具",
                  font=("", 9), bootstyle="secondary").pack(side=LEFT)

        # 右侧操作按钮
        actions = ttk.Frame(title_bar)
        actions.pack(side=RIGHT)

        ttk.Button(actions, text="▶ 运行全部", bootstyle="success",
                   command=self._on_run_all).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="＋ 新建组", bootstyle="primary-outline",
                   command=self._on_add_group).pack(side=LEFT, padx=3)
        ttk.Button(actions, text="⚙ 设置", bootstyle="secondary-outline",
                   command=self._on_settings).pack(side=LEFT, padx=3)

        ttk.Separator(self.root, bootstyle="default").pack(fill=X)

        # ---- Notebook 标签页 ----
        self._notebook = ttk.Notebook(self.root, bootstyle="primary")
        self._notebook.pack(fill=BOTH, expand=True, padx=8, pady=(5, 0))

        # 欢迎页（无任务组时显示）
        self._welcome_frame = ttk.Frame(self._notebook)
        self._build_welcome()

        # ---- 状态栏 ----
        ttk.Separator(self.root, bootstyle="default").pack(fill=X, pady=(5, 0))
        status_bar = ttk.Frame(self.root, padding=(12, 5))
        status_bar.pack(fill=X)

        ttk.Label(status_bar, textvariable=self._status_var,
                  bootstyle="secondary", font=("", 8)).pack(side=LEFT)
        ttk.Label(status_bar, text=f"v{APP_VERSION} | 数据: %USERPROFILE%\\.filego\\",
                  bootstyle="secondary", font=("", 7)).pack(side=RIGHT)

    def _build_welcome(self):
        """构建欢迎页（无任务组时显示）。"""
        for w in self._welcome_frame.winfo_children():
            w.destroy()

        inner = ttk.Frame(self._welcome_frame, padding=60)
        inner.pack(expand=True)

        ttk.Label(inner, text="📁", font=("", 48)).pack()
        ttk.Label(inner, text="欢迎使用 FileGo", font=("", 18, "bold"),
                  bootstyle="primary").pack(pady=(10, 5))
        ttk.Label(inner, text="定时文件复制与同步工具",
                  font=("", 10), bootstyle="secondary").pack()
        ttk.Label(inner, text="支持多源到多目标文件配对 · 间隔/每日/手动触发 · 系统托盘后台运行",
                  font=("", 8), bootstyle="secondary").pack(pady=(5, 20))

        btns = ttk.Frame(inner)
        btns.pack()
        ttk.Button(btns, text="＋ 创建第一个任务组", bootstyle="success",
                   command=self._on_add_group).pack(side=LEFT, padx=5)
        ttk.Button(btns, text="⚙ 设置", bootstyle="primary-outline",
                   command=self._on_settings).pack(side=LEFT, padx=5)

    def _add_group_tab(self, group: TaskGroup):
        """为任务组添加一个标签页。"""
        # 首次添加组时移除欢迎页
        if self._welcome_frame:
            try:
                self._notebook.forget(self._welcome_frame)
            except Exception:
                pass
            self._welcome_frame = None

        callbacks = {
            "on_add": lambda t: self._on_add_task(group, t),
            "on_run_all": lambda g=group: self._on_run_group(g),
            "on_run": lambda t, g=group: self._on_run_task(g, t),
            "on_edit": lambda t, g=group: self._on_edit_task(g, t),
            "on_delete": lambda t, g=group: self._on_delete_task(g, t),
            "on_toggle": lambda t, g=group: self._on_toggle_task(g, t),
        }

        panel = GroupPanel(self._notebook, group, callbacks)
        self._panels[group.group_id] = panel
        self._notebook.add(panel, text=f"  {group.name}  ")

        self._setup_tab_menu(panel, group)
        return panel

    def _setup_tab_menu(self, panel: GroupPanel, group: TaskGroup):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="重命名组...",
                         command=lambda g=group: self._on_rename_group(g))
        menu.add_command(label="删除组",
                         command=lambda g=group: self._on_delete_group(g))

        def on_right_click(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        panel.bind("<Button-3>", on_right_click)
        for child in panel.winfo_children():
            child.bind("<Button-3>", on_right_click)

    def refresh_all(self):
        """重新加载所有内容。"""
        for panel in self._panels.values():
            panel.destroy()
        self._panels.clear()

        for tab in self._notebook.tabs():
            self._notebook.forget(tab)

        if not self.app.groups:
            self._welcome_frame = ttk.Frame(self._notebook)
            self._build_welcome()
            self._notebook.add(self._welcome_frame, text="  FileGo  ")
        else:
            self._welcome_frame = None
            for group in self.app.groups:
                self._add_group_tab(group)

        for panel in self._panels.values():
            panel.refresh()

    def _schedule_refresh(self):
        try:
            for panel in self._panels.values():
                for task in panel.group.tasks:
                    panel.update_task_row(task)
        except Exception:
            pass
        self.root.after(30000, self._schedule_refresh)

    def _schedule_autosave(self):
        """定期自动保存（30秒间隔），防止意外退出丢数据。"""
        try:
            self.app.save_state()
        except Exception:
            pass
        self.root.after(30000, self._schedule_autosave)

    def _hook_shutdown(self):
        """拦截 Windows 关机/注销消息，提前保存数据。

        使用 Window 子类化（Subclassing）拦截 WM_QUERYENDSESSION
        和 WM_ENDSESSION 消息，确保在系统关机前保存数据。
        """
        try:
            import ctypes
            from ctypes import wintypes

            WM_QUERYENDSESSION = 0x0011
            WM_ENDSESSION = 0x0016
            GWLP_WNDPROC = -4

            # wintypes 没有 LRESULT，用 LPARAM 替代（都是 LONG_PTR）
            LRESULT = wintypes.LPARAM

            # 获取 tk 顶层窗口句柄
            hwnd = self.root.winfo_id()

            # 定义窗口过程函数类型（使用 wintypes 确保 64 位兼容）
            WNDPROC = ctypes.WINFUNCTYPE(
                LRESULT,
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            )

            # 设置 SetWindowLongPtrW 参数类型
            user32 = ctypes.windll.user32
            user32.SetWindowLongPtrW.argtypes = [
                wintypes.HWND, ctypes.c_int, wintypes.LONG_PTR,
            ]
            user32.SetWindowLongPtrW.restype = wintypes.LONG_PTR
            user32.GetWindowLongPtrW.argtypes = [
                wintypes.HWND, ctypes.c_int,
            ]
            user32.GetWindowLongPtrW.restype = wintypes.LONG_PTR

            # 保存原始窗口过程
            old_proc_addr = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
            self._old_wnd_proc = WNDPROC(old_proc_addr)

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == WM_QUERYENDSESSION:
                    try:
                        self.app.save_state()
                        self.app.store.save_config(self.app.config)
                        logger.info("WM_QUERYENDSESSION: 数据已保存，允许关机")
                    except Exception as e:
                        logger.error(f"关机保存失败: {e}")
                    return 1  # TRUE → 允许关机

                elif msg == WM_ENDSESSION:
                    if wparam:  # 真正关机
                        try:
                            self.app.save_state()
                            self.app.store.save_config(self.app.config)
                            logger.info("WM_ENDSESSION: 最终数据已保存")
                        except Exception as e:
                            logger.error(f"关机最终保存失败: {e}")

                # 转发到原始窗口过程
                return self._old_wnd_proc(hwnd, msg, wparam, lparam)

            # 子类化窗口
            self._new_wnd_proc = WNDPROC(wnd_proc)
            new_proc_addr = ctypes.cast(self._new_wnd_proc, wintypes.LONG_PTR).value
            user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, new_proc_addr)
            logger.info("已注册 Windows 关机钩子")

        except Exception as e:
            logger.warning(f"注册关机钩子失败 (非关键): {e}")

    # ---- 任务操作 ----

    def _on_add_task(self, group: TaskGroup, task: Task):
        group.add_task(task)
        self.app.save_state()
        self._panels[group.group_id].refresh()
        self._panels[group.group_id].add_log(f"已添加任务 [{task.name}]: {task.total_combinations} 次复制")

    def _on_edit_task(self, group: TaskGroup, updated_task: Task):
        for i, t in enumerate(group.tasks):
            if t.task_id == updated_task.task_id:
                group.tasks[i] = updated_task
                break
        self.app.save_state()
        self._panels[group.group_id].refresh()
        self._panels[group.group_id].add_log(f"已更新任务 [{updated_task.name}]")

    def _on_delete_task(self, group: TaskGroup, task: Task):
        group.remove_task(task.task_id)
        self.app.save_state()
        self._panels[group.group_id].refresh()
        self._panels[group.group_id].add_log(f"已删除任务 [{task.name}]")

    def _on_toggle_task(self, group: TaskGroup, task: Task):
        task.enabled = not task.enabled
        self.app.save_state()
        self._panels[group.group_id].update_task_row(task)

    def _on_run_task(self, group: TaskGroup, task: Task):
        self.app.executor.enqueue(task, group, run_skipped=True)
        task.last_status = "running"
        self._panels[group.group_id].update_task_row(task)
        self._panels[group.group_id].add_log(f"▶ 手动执行: [{task.name}] ({task.total_combinations} 次复制)")
        self._set_status(f"正在运行: {task.name}...")

    def _on_run_group(self, group: TaskGroup):
        count = 0
        for task in group.tasks:
            if task.enabled:
                self.app.executor.enqueue(task, group, run_skipped=True)
                task.last_status = "running"
                self._panels[group.group_id].update_task_row(task)
                count += 1
        self._panels[group.group_id].add_log(f"▶ 运行全部: {count} 个任务")
        self._set_status(f"已加入 {count} 个任务到执行队列")

    def _on_run_all(self):
        total = 0
        for group in self.app.groups:
            for task in group.tasks:
                if task.enabled:
                    self.app.executor.enqueue(task, group, run_skipped=True)
                    task.last_status = "running"
                    if group.group_id in self._panels:
                        self._panels[group.group_id].update_task_row(task)
                    total += 1
        self._set_status(f"已加入 {total} 个任务到执行队列")

    # ---- 组操作 ----

    def _on_add_group(self):
        dialog = GroupEditDialog(self.root)
        if dialog.result:
            group = TaskGroup(name=dialog.result)
            self.app.groups.append(group)
            self.app.save_state()
            panel = self._add_group_tab(group)
            panel.refresh()
            self._notebook.select(len(self._notebook.tabs()) - 1)
            self._set_status(f"已创建组: {group.name}")

    def _on_rename_group(self, group: TaskGroup):
        dialog = GroupEditDialog(self.root, group)
        if dialog.result:
            old_name = group.name
            group.name = dialog.result
            self.app.save_state()
            for i, g in enumerate(self.app.groups):
                if g.group_id == group.group_id:
                    self._notebook.tab(i, text=f"  {group.name}  ")
                    break
            self._set_status(f"已重命名: {old_name} → {group.name}")

    def _on_delete_group(self, group: TaskGroup):
        if not messagebox.askyesno("确认删除",
                                   f"确定要删除组 [{group.name}] 及其所有 {len(group.tasks)} 个任务吗？\n\n此操作不可撤销。"):
            return
        self.app.groups = [g for g in self.app.groups if g.group_id != group.group_id]
        self.app.save_state()
        self.refresh_all()
        self._set_status(f"已删除组: {group.name}")

    # ---- 设置 ----

    def _on_settings(self):
        def on_save(config):
            self.app.config.update(config)
            self.app.save_config()
            self._set_status("设置已保存")

        SettingsDialog(self.root, self.app.config, on_save)

    # ---- 窗口管理 ----

    def _on_close(self):
        self.app.save_state()  # 立即保存
        if self.app.config.get("close_to_tray", True) and HAS_TRAY:
            self.root.withdraw()
            self.app.show_tray()  # 窗口隐藏后显示托盘图标
            self._set_status("已最小化到系统托盘")
        else:
            self._on_exit()

    def _on_exit(self):
        if messagebox.askyesno("退出 FileGo", "确定要退出吗？\n\n计划任务将停止运行。"):
            self.app.shutdown()

    # ---- 回调 ----

    def on_task_result(self, task: Task, group: TaskGroup, success: bool, message: str):
        try:
            if group is None or task is None:
                return
            panel = self._panels.get(group.group_id)
            if panel:
                icon = "✓" if success else "✗"
                panel.add_log(f"{icon} [{task.name}]: {message}")
                panel.update_task_row(task)
        except Exception as e:
            import traceback
            logger.error(f"on_task_result UI异常:\n{traceback.format_exc()}")

        if success and self.app.config.get("notify_on_success", False):
            self._notify("复制成功", f"{task.name}: {message}")
        elif not success and self.app.config.get("notify_on_failure", True):
            self._notify("复制失败", f"{task.name}: {message}")

        self._set_status(message)

    def _notify(self, title: str, message: str):
        if HAS_TRAY and self.app.tray_icon:
            self.app.tray_icon.show_notification(title, message)

    def _set_status(self, text: str):
        self._status_var.set(text)

    def restore_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.app.hide_tray()  # 窗口恢复后隐藏托盘图标
        self._set_status("窗口已恢复")

    def show(self, start_hidden: bool = False):
        # 检查是否有数据恢复消息需要展示
        recovery_msgs = self.app.get_recovery_messages()
        if recovery_msgs:
            def _show_recovery():
                for msg in recovery_msgs:
                    messagebox.showwarning("FileGo — 数据恢复通知", msg)
            self.root.after(500, _show_recovery)

        if start_hidden or (self.app.config.get("minimize_to_tray", False) and HAS_TRAY):
            self.root.withdraw()
            self.app.show_tray()  # 窗口启动隐藏 → 显示托盘图标
        else:
            self.root.deiconify()
        self.root.mainloop()

    def destroy(self):
        """销毁窗口并退出主循环。"""
        try:
            self.root.quit()     # 先退出 mainloop
        except Exception:
            pass
        try:
            self.root.destroy()  # 再销毁窗口
        except Exception:
            pass
