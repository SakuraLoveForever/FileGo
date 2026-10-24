"""
Task 数据模型 — 多组「源 → 目标」按序号 1 对 1 配对复制
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

from config import (
    SCHEDULE_INTERVAL,
    SCHEDULE_DAILY,
    SCHEDULE_MANUAL,
    SCHEDULE_TYPES,
    BACKUP_FILE,
    BACKUP_FOLDER,
    BACKUP_MODES,
)


@dataclass
class Task:
    """源与目标按序号一一对应：源 #1 → 目标 #1、源 #2 → 目标 #2。"""
    name: str = "新任务"
    sources: List[str] = field(default_factory=lambda: [""])
    dests: List[str] = field(default_factory=lambda: [""])
    enabled: bool = True
    schedule_type: str = SCHEDULE_INTERVAL
    schedule_value: str = "60"
    backup_mode: str = BACKUP_FILE
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_run: Optional[str] = None
    last_status: str = "idle"
    next_run: Optional[str] = None
    source_modes: List[str] = field(default_factory=list)

    def __post_init__(self):
        """确保 sources 和 dests 始终是列表。"""
        if self.sources is None:
            object.__setattr__(self, 'sources', [""])
        if self.dests is None:
            object.__setattr__(self, 'dests', [""])
        # 规范化备份模式
        if self.backup_mode not in BACKUP_MODES:
            object.__setattr__(self, 'backup_mode', BACKUP_FILE)
        # 过滤 None 值
        self.sources = [s if isinstance(s, str) else "" for s in self.sources]
        self.dests = [d if isinstance(d, str) else "" for d in self.dests]
        modes = self.source_modes or []
        self.source_modes = [
            modes[i] if i < len(modes) else self.backup_mode
            for i in range(len(self.sources))
        ]

    @property
    def mode_label(self) -> str:
        """备份模式的中文标签。"""
        modes = {mode for source, mode in zip(self.sources, self.source_modes) if source.strip()}
        if len(modes) > 1:
            return "混合复制"
        return "整体备份(文件夹)" if modes == {BACKUP_FOLDER} else "文件复制"

    @property
    def pair_count(self) -> int:
        """按序号配成的完整组数（该序号下源和目标都填写了）。"""
        return sum(1 for src, dst in zip(self.sources, self.dests)
                   if src.strip() and dst.strip())

    @staticmethod
    def from_dict(d: dict) -> "Task":
        sources = d.get("sources", [])
        dests = d.get("dests", [])

        # 向后兼容旧版格式
        if not sources and not dests:
            # 新版 pairs 格式
            if "pairs" in d:
                sources = [p.get("source", "") for p in d.get("pairs", [])]
                dests = [p.get("dest", "") for p in d.get("pairs", [])]
            # 旧版单文件格式
            elif "source" in d:
                sources = [d.get("source", "")]
                dests = [d.get("dest", "")]

        return Task(
            task_id=d.get("task_id") or uuid.uuid4().hex[:12],
            name=d.get("name", "新任务"),
            sources=sources if sources else [""],
            dests=dests if dests else [""],
            enabled=d.get("enabled", True),
            schedule_type=d.get("schedule_type", SCHEDULE_INTERVAL),
            schedule_value=d.get("schedule_value", "60"),
            backup_mode=d.get("backup_mode", BACKUP_FILE),
            source_modes=d.get("source_modes", []),
            last_run=d.get("last_run"),
            last_status=d.get("last_status", "idle"),
            next_run=d.get("next_run"),
        )

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "sources": self.sources,
            "dests": self.dests,
            "enabled": self.enabled,
            "schedule_type": self.schedule_type,
            "schedule_value": self.schedule_value,
            "backup_mode": self.backup_mode,
            "source_modes": self.source_modes,
            "last_run": self.last_run,
            "last_status": self.last_status,
            "next_run": self.next_run,
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.name.strip():
            errors.append("任务名称不能为空")

        # 1 对 1 配对：两侧数量必须一致，且同一序号要么都填、要么都空
        if len(self.sources) != len(self.dests):
            errors.append(
                f"源路径（{len(self.sources)} 条）与目标路径（{len(self.dests)} 条）"
                "数量必须一致，才能按序号 1 对 1 配对"
            )
        else:
            for i, (src, dst) in enumerate(zip(self.sources, self.dests)):
                if bool(src.strip()) != bool(dst.strip()):
                    errors.append(f"第 {i + 1} 组「源 → 目标」必须同时填写或同时留空")
        if self.pair_count == 0:
            errors.append("至少需要一组「源 → 目标」配对")

        if self.schedule_type not in SCHEDULE_TYPES:
            errors.append(f"无效的调度类型: {self.schedule_type}")
        if self.backup_mode not in BACKUP_MODES:
            errors.append(f"无效的备份模式: {self.backup_mode}")
        if len(self.source_modes) != len(self.sources):
            errors.append("源路径与复制类型数量不一致")
        for i, mode in enumerate(self.source_modes):
            if mode not in BACKUP_MODES:
                errors.append(f"源 #{i+1} 的复制类型无效: {mode}")
        if self.schedule_type == SCHEDULE_INTERVAL:
            try:
                val = int(self.schedule_value)
                if val <= 0:
                    errors.append("间隔分钟数必须大于 0")
            except (ValueError, TypeError):
                errors.append("间隔分钟数必须是有效的整数")
        elif self.schedule_type == SCHEDULE_DAILY:
            try:
                parts = self.schedule_value.split(":")
                if len(parts) != 2:
                    raise ValueError
                h, m = int(parts[0]), int(parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError
            except (ValueError, TypeError):
                errors.append("每日时间格式必须为 HH:MM (如 02:30)")
        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def compute_next_run(self, now: datetime) -> Optional[datetime]:
        if not self.enabled or self.schedule_type == SCHEDULE_MANUAL:
            return None

        if self.schedule_type == SCHEDULE_INTERVAL:
            base = now
            if self.last_run:
                try:
                    base = datetime.fromisoformat(self.last_run)
                except (ValueError, TypeError):
                    pass
            minutes = int(self.schedule_value)
            return base + timedelta(minutes=minutes)

        elif self.schedule_type == SCHEDULE_DAILY:
            try:
                h, m = map(int, self.schedule_value.split(":"))
            except (ValueError, AttributeError):
                return None
            next_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if next_dt <= now:
                next_dt += timedelta(days=1)
            return next_dt

        return None

    @property
    def summary(self) -> str:
        """列表显示的简短摘要。"""
        sc = len([s for s in self.sources if s.strip()])
        dc = len([d for d in self.dests if d.strip()])
        pairs = self.pair_count
        if pairs == 0:
            return "未配置"
        if len(self.sources) == 1 and len(self.dests) == 1:
            s = self.sources[0]
            return s if len(s) <= 40 else "..." + s[-37:]
        if sc != dc:
            return f"{sc} 个源 ≠ {dc} 个目标（需按序号配对）"
        return f"{pairs} 组 1 对 1 复制"

    def __repr__(self) -> str:
        return f"Task({self.name!r}, {self.pair_count} 组 1对1)"
