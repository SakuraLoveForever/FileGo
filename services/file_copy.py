"""
文件复制服务 — 每个源 → 每个目标全量复制
"""

import glob
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config import logger


@dataclass
class CopyResult:
    success: bool
    message: str = ""
    files_copied: int = 0
    files_failed: int = 0


def _has_wildcard(path: str) -> bool:
    return "*" in path or "?" in path


def _is_directory_path(path: str) -> bool:
    """智能判断路径是否为目录。"""
    if path.endswith(("\\", "/")):
        return True
    p = Path(path)
    if p.exists():
        return p.is_dir()
    # 路径不存在：如果没有文件后缀名，视为目录
    suffix = p.suffix
    if not suffix:
        return True
    return False


def _ensure_dir(path: str):
    """安全创建目录：如果路径是已存在的文件则先删除。"""
    import time
    if os.path.isfile(path):
        try:
            os.remove(path)
            time.sleep(0.1)
        except OSError:
            pass
    os.makedirs(path, exist_ok=True)
    time.sleep(0.05)  # Windows 目录创建后短暂等待


def _copy_with_retry(src: str, dst: str, retries: int = 3) -> None:
    """手动读写文件复制，避免 shutil.copy2 元数据复制触发 Windows 文件锁。"""
    import time
    last_err = None
    for attempt in range(retries):
        try:
            # 手动分块复制，不复制元数据
            with open(src, "rb") as fsrc:
                with open(dst, "wb") as fdst:
                    while True:
                        chunk = fsrc.read(8 * 1024 * 1024)  # 8MB 块
                        if not chunk:
                            break
                        fdst.write(chunk)
            # 尝试复制修改时间（失败不影响）
            try:
                st = os.stat(src)
                os.utime(dst, (st.st_atime, st.st_mtime))
            except OSError:
                pass
            return
        except OSError as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
            else:
                # 最后一次尝试：清理可能损坏的目标文件
                try:
                    if os.path.exists(dst):
                        os.remove(dst)
                except OSError:
                    pass
    raise last_err


def _count_files(path: str) -> int:
    """递归统计目录中的文件数。"""
    p = Path(path)
    if p.is_file():
        return 1
    if p.is_dir():
        return sum(1 for _ in p.rglob("*") if _.is_file())
    return 0


def copy_single(src: str, dst: str) -> CopyResult:
    """复制单个源到目标。"""
    if not src.strip():
        return CopyResult(success=False, message="源路径为空")
    if not dst.strip():
        return CopyResult(success=False, message="目标路径为空")

    src = os.path.expandvars(src)
    dst = os.path.expandvars(dst)
    dst_is_dir = _is_directory_path(dst)
    copied = 0
    failed = 0
    errors = []

    try:
        if _has_wildcard(src):
            matches = glob.glob(src)
            if not matches:
                return CopyResult(success=False, message=f"无匹配: {os.path.basename(src)}")
            if dst_is_dir:
                _ensure_dir(dst)
            for match in matches:
                if os.path.isfile(match):
                    try:
                        dest_path = os.path.join(dst, os.path.basename(match)) if dst_is_dir else dst
                        _ensure_dir(os.path.dirname(dest_path) or ".")
                        shutil.copy2(match, dest_path)
                        copied += 1
                    except (PermissionError, OSError) as e:
                        failed += 1
                        errors.append(f"{os.path.basename(match)}: {e}")
        else:
            if not os.path.exists(src):
                return CopyResult(success=False, message=f"源不存在: {os.path.basename(src)}")

            if os.path.isdir(src):
                if os.path.exists(dst) and not dst_is_dir:
                    return CopyResult(success=False, message=f"目标非目录: {dst}")
                dest_dir = os.path.join(dst, os.path.basename(src)) if (os.path.exists(dst) and dst_is_dir) else dst
                try:
                    if os.path.exists(dest_dir):
                        shutil.rmtree(dest_dir)
                    shutil.copytree(src, dest_dir)
                    copied = _count_files(dest_dir)
                    logger.info(f"已复制目录: {os.path.basename(src)} -> {dest_dir} ({copied} 文件)")
                except (PermissionError, OSError) as e:
                    return CopyResult(success=False, message=f"目录复制失败: {e}")
            else:
                # 单文件复制
                if dst_is_dir:
                    # 目标是目录 → 保留源文件名
                    dest_path = os.path.join(dst, os.path.basename(src))
                elif os.path.isdir(dst):
                    # 目标已存在且是目录 → 保留源文件名
                    dest_path = os.path.join(dst, os.path.basename(src))
                else:
                    # 目标是不存在的文件路径 → 直接用
                    dest_path = dst
                _ensure_dir(os.path.dirname(dest_path) or ".")
                if os.path.isfile(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                try:
                    _copy_with_retry(src, dest_path)
                    copied = 1
                    logger.info(f"已复制: {os.path.basename(src)} -> {dest_path}")
                except OSError as e:
                    return CopyResult(success=False, message=f"复制失败: {e}")

    except Exception as e:
        logger.exception(f"复制异常: {src}")
        return CopyResult(success=False, message=f"异常: {e}")

    if failed > 0:
        msg = f"{copied} 成功, {failed} 失败"
        if errors:
            msg += f" ({'; '.join(errors[:2])})"
        return CopyResult(success=False, message=msg, files_copied=copied, files_failed=failed)

    return CopyResult(success=True, message=f"{copied} 个文件", files_copied=copied)


def copy_all(sources: List[str], dests: List[str]) -> CopyResult:
    """
    每个源复制到每个目标（M × N 全量复制）。
    返回汇总结果。
    """
    if sources is None:
        sources = []
    if dests is None:
        dests = []

    valid_sources = [s.strip() for s in sources if isinstance(s, str) and s.strip()]
    valid_dests = [d.strip() for d in dests if isinstance(d, str) and d.strip()]

    if not valid_sources:
        return CopyResult(success=False, message="无有效源路径")
    if not valid_dests:
        return CopyResult(success=False, message="无有效目标路径")

    total_copied = 0
    total_failed = 0
    pair_errors = []

    for src in valid_sources:
        for dst in valid_dests:
            r = copy_single(src, dst)
            total_copied += r.files_copied
            total_failed += r.files_failed
            if not r.success:
                src_name = os.path.basename(src)
                dst_name = os.path.basename(dst) if not _is_directory_path(dst) else dst
                pair_errors.append(f"{src_name}→{dst_name}: {r.message}")

    total_pairs = len(valid_sources) * len(valid_dests)

    if total_failed == 0 and len(pair_errors) == 0:
        return CopyResult(
            success=True,
            message=f"全部成功: {total_copied} 个文件 ({total_pairs} 组复制)",
            files_copied=total_copied,
        )
    elif total_copied > 0:
        return CopyResult(
            success=False,
            message=f"{total_copied} 成功, {total_failed} 失败 — {'; '.join(pair_errors[:3])}",
            files_copied=total_copied,
            files_failed=total_failed,
        )
    else:
        return CopyResult(
            success=False,
            message=f"全部失败 ({total_pairs} 组) — {'; '.join(pair_errors[:3])}",
            files_failed=total_failed,
        )
