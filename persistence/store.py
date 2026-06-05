"""
JSON 持久化存储 — 原子写入、损坏恢复
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from config import logger, DATA_DIR, TASKS_FILE, CONFIG_FILE, DEFAULT_CONFIG, DEFAULT_TASKS
from models.task_group import TaskGroup


class Store:
    """任务和配置的 JSON 持久化存储。"""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ---- 任务组 ----

    def load_groups(self) -> List[TaskGroup]:
        """加载所有任务组。如果文件损坏，恢复备份或返回默认值。"""
        data = self._load_json(TASKS_FILE, DEFAULT_TASKS)
        groups = []
        for g in data.get("groups", []):
            try:
                groups.append(TaskGroup.from_dict(g))
            except Exception as e:
                logger.error(f"加载任务组失败: {e}")
        return groups

    def save_groups(self, groups: List[TaskGroup]) -> None:
        """保存所有任务组（原子写入）。"""
        data = {
            "schema_version": 1,
            "groups": [g.to_dict() for g in groups],
        }
        self._save_json(TASKS_FILE, data)

    # ---- 配置 ----

    def load_config(self) -> dict:
        """加载配置，合并默认值。"""
        saved = self._load_json(CONFIG_FILE, {})
        config = DEFAULT_CONFIG.copy()
        config.update(saved)
        return config

    def save_config(self, config: dict) -> None:
        """保存配置。"""
        self._save_json(CONFIG_FILE, config)

    # ---- 内部方法 ----

    def _load_json(self, path: Path, default: dict) -> dict:
        """安全加载 JSON 文件。"""
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载 JSON 失败 ({path}): {e}")
            # 备份损坏的文件
            bak = path.with_suffix(path.suffix + ".bak")
            try:
                shutil.copy2(path, bak)
                logger.warning(f"已备份损坏文件到 {bak}")
            except OSError:
                pass
            return default

    def _save_json(self, path: Path, data: dict) -> None:
        """原子写入 JSON：先写 .tmp，再重命名。"""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)  # Windows 上是原子操作
        except OSError as e:
            logger.error(f"保存 JSON 失败 ({path}): {e}")
            raise
