"""
TaskGroup 数据模型 — 命名的任务列表
"""

import uuid
from dataclasses import dataclass, field
from typing import List
from .task import Task


@dataclass
class TaskGroup:
    """命名的任务组。"""
    name: str
    group_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    tasks: List[Task] = field(default_factory=list)

    @staticmethod
    def from_dict(d: dict) -> "TaskGroup":
        """从字典反序列化。"""
        tasks = [Task.from_dict(t) for t in d.get("tasks", [])]
        return TaskGroup(
            group_id=d.get("group_id") or uuid.uuid4().hex[:12],
            name=d.get("name", "未命名组"),
            tasks=tasks,
        )

    def to_dict(self) -> dict:
        """序列化为字典。"""
        return {
            "group_id": self.group_id,
            "name": self.name,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    def get_enabled_tasks(self) -> List[Task]:
        """获取所有已启用且有效的任务。"""
        return [t for t in self.tasks if t.enabled and t.is_valid()]

    def get_task_by_id(self, task_id: str) -> Task | None:
        """按 ID 查找任务。"""
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def add_task(self, task: Task) -> None:
        """添加任务。"""
        self.tasks.append(task)

    def remove_task(self, task_id: str) -> bool:
        """按 ID 删除任务，返回是否成功。"""
        for i, t in enumerate(self.tasks):
            if t.task_id == task_id:
                self.tasks.pop(i)
                return True
        return False

    def __repr__(self) -> str:
        return f"TaskGroup({self.name!r}, {len(self.tasks)} tasks)"
