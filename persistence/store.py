"""
JSON 持久化存储 — 原子写入、轮转备份、损坏恢复
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from config import logger, DATA_DIR, TASKS_FILE, CONFIG_FILE, DEFAULT_CONFIG, DEFAULT_TASKS
from models.task_group import TaskGroup

# 轮转备份数量（保留最近 N 个版本）
MAX_BACKUPS = 5


class Store:
    """任务和配置的 JSON 持久化存储。"""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._recovery_messages: List[str] = []

    @property
    def recovery_messages(self) -> List[str]:
        """返回数据恢复相关的警告消息，调用后清空。"""
        msgs = self._recovery_messages.copy()
        self._recovery_messages.clear()
        return msgs

    # ---- 任务组 ----

    def load_groups(self) -> List[TaskGroup]:
        """加载所有任务组。如果文件损坏，从备份恢复或返回默认值。"""
        data = self._load_json(TASKS_FILE, DEFAULT_TASKS)
        groups = []
        for g in data.get("groups", []):
            try:
                groups.append(TaskGroup.from_dict(g))
            except Exception as e:
                logger.error(f"加载任务组失败: {e}")
        return groups

    def save_groups(self, groups: List[TaskGroup]) -> None:
        """保存所有任务组（原子写入 + 轮转备份）。"""
        data = {
            "schema_version": 1,
            "groups": [g.to_dict() for g in groups],
        }
        self._save_json(TASKS_FILE, data)

    # ---- 配置 ----

    def load_config(self) -> dict:
        """加载配置，合并默认值。如果文件损坏，从备份恢复。"""
        saved = self._load_json(CONFIG_FILE, {})
        config = DEFAULT_CONFIG.copy()
        config.update(saved)
        return config

    def save_config(self, config: dict) -> None:
        """保存配置（原子写入 + 轮转备份）。"""
        self._save_json(CONFIG_FILE, config)

    # ---- 内部方法 ----

    def _load_json(self, path: Path, default: dict) -> dict:
        """安全加载 JSON 文件。

        加载顺序：主文件 → 轮转备份(.1.bak ~ .N.bak) → 旧格式备份(.bak) → 默认值。
        如果从备份恢复，会记录到 recovery_messages 中。
        """
        # 1. 尝试加载主文件
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"加载 JSON 失败 ({path}): {e}")
                # 备份损坏的主文件
                self._backup_corrupted(path)

        # 2. 尝试从轮转备份恢复（从最新到最旧）
        for i in range(1, MAX_BACKUPS + 1):
            bak = Path(str(path) + f".{i}.bak")
            if bak.exists():
                try:
                    with open(bak, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    logger.warning(f"✅ 已从轮转备份恢复: {bak.name}")
                    self._recovery_messages.append(
                        f"数据文件 {path.name} 已从备份 ({bak.name}) 恢复。\n"
                        f"备份时间: {datetime.fromtimestamp(bak.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    # 恢复成功后，立即写回主文件
                    self._write_atomic(path, data)
                    return data
                except (json.JSONDecodeError, OSError) as e:
                    logger.error(f"轮转备份也损坏 ({bak}): {e}")

        # 3. 尝试旧格式 .bak 备份（兼容旧版本）
        old_bak = path.with_suffix(path.suffix + ".bak")
        if old_bak.exists():
            try:
                with open(old_bak, "r", encoding="utf-8") as f:
                    data = json.load(f)
                logger.warning(f"✅ 已从旧备份恢复: {old_bak.name}")
                self._recovery_messages.append(
                    f"数据文件 {path.name} 已从旧备份 ({old_bak.name}) 恢复。"
                )
                self._write_atomic(path, data)
                return data
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"旧备份也损坏 ({old_bak}): {e}")

        # 4. 所有尝试都失败，返回默认值
        logger.error(f"⚠️ 所有恢复尝试均失败，使用默认值: {path.name}")
        self._recovery_messages.append(
            f"⚠️ 数据文件 {path.name} 无法恢复，已使用默认配置。\n"
            f"旧数据备份存放在: {path.parent}"
        )
        return default

    def _save_json(self, path: Path, data: dict) -> None:
        """原子写入 JSON（先轮转备份，再写 .tmp，最后原子重命名）。"""
        # 写入前先创建快照（轮转备份）
        if path.exists() and path.stat().st_size > 0:
            self._rotate_backups(path)

        self._write_atomic(path, data)

    def _write_atomic(self, path: Path, data: dict) -> None:
        """原子写入：先写 .tmp，再重命名。"""
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp.replace(path)  # Windows 上是原子操作
        except OSError as e:
            logger.error(f"保存 JSON 失败 ({path}): {e}")
            raise

    def _rotate_backups(self, path: Path) -> None:
        """轮转备份：将当前文件快照保存到 .1.bak，旧的依次后移。

        .1.bak → .2.bak → ... → .N.bak → 删除
        最新的备份总是 .1.bak。
        """
        # 删除最旧的备份
        oldest = Path(str(path) + f".{MAX_BACKUPS}.bak")
        if oldest.exists():
            try:
                oldest.unlink()
            except OSError as e:
                logger.debug(f"删除旧备份失败 ({oldest}): {e}")

        # 依次后移：.4.bak → .5.bak, ..., .1.bak → .2.bak
        for i in range(MAX_BACKUPS - 1, 0, -1):
            old = Path(str(path) + f".{i}.bak")
            if old.exists():
                try:
                    old.replace(Path(str(path) + f".{i + 1}.bak"))
                except OSError as e:
                    logger.debug(f"轮转备份失败 ({old}): {e}")

        # 将当前文件复制为 .1.bak
        try:
            shutil.copy2(path, Path(str(path) + ".1.bak"))
        except OSError as e:
            logger.error(f"创建备份快照失败 ({path}): {e}")

    def _backup_corrupted(self, path: Path) -> None:
        """备份损坏的主文件（带时间戳），避免覆盖有用的轮转备份。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        corrupted = Path(str(path) + f".corrupted_{ts}.bak")
        try:
            shutil.copy2(path, corrupted)
            logger.warning(f"已备份损坏文件到 {corrupted.name}")
        except OSError:
            pass
