# FileGo

**FileGo** 是一款 Windows 桌面定时文件复制工具。它允许你定义多个任务组，每个任务组包含若干复制任务，按照设定的时间计划（间隔 / 每日定时 / 手动）将多个源文件或文件夹复制到多个目标路径。

## 功能特性

- **多源到多目标复制** — 每个任务支持 M×N 的源→目标映射，所有源都会复制到所有目标
- **通配符支持** — 源路径支持 `*` 和 `?` 通配符匹配
- **三种调度模式**
  - **间隔模式** — 每隔 N 分钟执行一次（1–1440 分钟）
  - **每日模式** — 在指定时间（HH:MM）执行
  - **手动模式** — 仅手动触发执行
- **任务分组** — 将任务按类别组织到不同分组中
- **系统托盘** — 最小化到系统托盘，后台静默运行
- **开机自启** — 支持注册到 Windows 启动项
- **单实例运行** — 防止重复启动，再次启动会激活已有窗口
- **复制重试** — 文件复制失败时自动重试（最多 3 次，带退避延迟）
- **大文件分块复制** — 8 MB 分块读写，避免大文件复制时的元数据锁问题
- **数据持久化** — 配置和任务数据保存为 JSON 文件（原子写入，损坏自动恢复）
- **日志记录** — 运行日志写入 `%USERPROFILE%\.filego\filego.log`
- **现代 UI** — 基于 ttkbootstrap "flatly" 主题的美观界面

## 运行环境

- **操作系统：** Windows
- **Python：** 3.12+

## 快速开始

### 从源码运行

```bash
# 克隆仓库
git clone <repo-url> FileGo
cd FileGo

# 安装依赖
pip install -r requirements.txt

# 启动程序
python main.py

# 以隐藏模式启动（最小化到托盘，适用于开机自启）
python main.py --hidden
```

### 使用预构建的可执行文件

直接运行 `dist/FileGo.exe`（约 19 MB 的独立可执行文件）。

## 依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| [ttkbootstrap](https://github.com/israel-dryer/ttkbootstrap) | >=1.10.0 | 现代化 tkinter 主题控件 |
| [pystray](https://github.com/moses-palmer/pystray) | >=0.19.0 | 系统托盘图标 |
| [Pillow](https://python-pillow.org/) | >=10.0.0 | 托盘图标图像处理 |

## 项目结构

```
FileGo/
├── main.py                  # 入口（DPI 设置、单实例锁、启动 App）
├── app.py                   # 应用根对象（串联所有组件）
├── config.py                # 常量、路径、日志、默认配置
├── FileGo-debug.spec        # PyInstaller 打包配置
├── requirements.txt         # Python 依赖
│
├── models/
│   ├── task.py              # Task 数据类
│   └── task_group.py        # TaskGroup 数据类
│
├── persistence/
│   └── store.py             # JSON 文件持久化（原子写入、损坏恢复）
│
├── scheduler/
│   ├── engine.py            # 调度引擎（后台线程，轮询到期任务）
│   └── executor.py          # 执行器（后台线程，消费任务队列执行复制）
│
├── services/
│   ├── file_copy.py         # 核心复制逻辑（M×N 复制、通配符、重试）
│   ├── single_instance.py   # 单实例锁（localhost socket）
│   └── autostart.py         # Windows 注册表开机自启管理
│
├── ui/
│   ├── main_window.py       # 主窗口（ttkbootstrap、标签页、状态栏）
│   ├── tray.py              # 系统托盘图标和菜单
│   ├── dialogs.py           # 任务编辑、分组编辑、设置对话框
│   ├── group_panel.py       # 分组面板（可滚动的任务卡片列表 + 日志）
│   ├── task_row.py          # 单个任务卡片控件
│   └── icons.py             # Base64 编码的托盘图标
│
└── resources/
    └── icon.ico             # 应用图标
```

## 构建

使用 PyInstaller 打包为独立可执行文件：

```bash
pyinstaller FileGo-debug.spec
```

构建产物输出到 `dist/` 目录。

## 数据存储

所有数据存储在 `%USERPROFILE%\.filego\` 目录下：

| 文件 | 说明 |
|------|------|
| `tasks.json` | 任务组和任务数据 |
| `config.json` | 应用配置 |
| `filego.log` | 运行日志 |

## 许可证

MIT License
