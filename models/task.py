"""
Task 数据模型 — 多个源 × 多个目标，全量复制
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

from config import SCHEDULE_INTERVAL, SCHEDULE_DAILY, SCHEDULE_MANUAL, SCHEDULE_TYPES


@dataclass
class Task:
    """文件复制任务 — sources 中每个路径都复制到 dests 中每个路径。"""
    name: str = "新任务"
    sources: List[str] = field(default_factory=lambda: [""])
    dests: List[str] = field(default_factory=lambda: [""])
    enabled: bool = True
    schedule_type: str = SCHEDULE_INTERVAL
    schedule_value: str = "60"
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    last_run: Optional[str] = None
    last_status: str = "idle"
    next_run: Optional[str] = None

    def __post_init__(self):
        """确保 sources 和 dests 始终是列表。"""
        if self.sources is None:
            object.__setattr__(self, 'sources', [""])
        if self.dests is None:
            object.__setattr__(self, 'dests', [""])
        # 过滤 None 值
        self.sources = [s if isinstance(s, str) else "" for s in self.sources]
        self.dests = [d if isinstance(d, str) else "" for d in self.dests]

    @property
    def total_combinations(self) -> int:
        """源 × 目标 的总复制组合数。"""
        return len([s for s in self.sources if s.strip()]) * len([d for d in self.dests if d.strip()])

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
            "last_run": self.last_run,
            "last_status": self.last_status,
            "next_run": self.next_run,
        }

    def validate(self) -> list[str]:
        errors = []
        if not self.name.strip():
            errors.append("任务名称不能为空")

        valid_sources = [s for s in self.sources if s.strip()]
        valid_dests = [d for d in self.dests if d.strip()]

        if not valid_sources:
            errors.append("至少需要一个源路径")
        if not valid_dests:
            errors.append("至少需要一个目标路径")

        for i, s in enumerate(self.sources):
            if s.strip() and not s.strip():
                errors.append(f"源 #{i+1} 不能为空")
        for i, d in enumerate(self.dests):
            if d.strip() and not d.strip():
                errors.append(f"目标 #{i+1} 不能为空")

        if self.schedule_type not in SCHEDULE_TYPES:
            errors.append(f"无效的调度类型: {self.schedule_type}")
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
        if sc == 0 or dc == 0:
            return "未配置"
        if sc == 1 and dc == 1:
            s = self.sources[0]
            return s if len(s) <= 40 else "..." + s[-37:]
        return f"{sc} 个源 × {dc} 个目标 = {sc * dc} 次复制"

    def __repr__(self) -> str:
        return f"Task({self.name!r}, {len(self.sources)}src×{len(self.dests)}dst)"
