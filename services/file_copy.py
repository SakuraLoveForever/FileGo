"""
文件复制服务 — 每个源 → 每个目标全量复制
"""

import glob
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

from config import logger, BACKUP_FILE, BACKUP_FOLDER


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
    """创建目录；遇到同名文件时保留文件并报错。"""
    os.makedirs(path, exist_ok=True)


def _same_file(src: str, dst: str) -> bool:
    """识别同一路径及指向同一文件的硬链接、符号链接。"""
    try:
        return os.path.samefile(src, dst)
    except OSError:
        return os.path.normcase(os.path.realpath(src)) == os.path.normcase(os.path.realpath(dst))


def _directories_overlap(src: str, dst: str) -> bool:
    src = os.path.normcase(os.path.realpath(src))
    dst = os.path.normcase(os.path.realpath(dst))
    try:
        return os.path.commonpath([src, dst]) in (src, dst)
    except ValueError:  # 不同盘符
        return False


def _copy_with_retry(src: str, dst: str, retries: int = 3) -> None:
    """写入同目录临时文件，成功后替换目标；失败时保留原有内容。"""
    import time
    if _same_file(src, dst):
        return
    last_err = None
    for attempt in range(retries):
        temp_path = None
        try:
            with open(src, "rb") as fsrc, tempfile.NamedTemporaryFile(
                dir=os.path.dirname(os.path.abspath(dst)), prefix=".filego-", suffix=".tmp",
                delete=False,
            ) as fdst:
                temp_path = fdst.name
                shutil.copyfileobj(fsrc, fdst, length=8 * 1024 * 1024)
            # 尝试复制修改时间（失败不影响）
            try:
                st = os.stat(src)
                os.utime(temp_path, (st.st_atime, st.st_mtime))
            except OSError:
                pass
            os.replace(temp_path, dst)
            return
        except OSError as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning(f"临时文件清理失败: {temp_path}: {e}")
    raise last_err


def _count_files(path: str) -> int:
    """递归统计目录中的文件数。"""
    p = Path(path)
    if p.is_file():
        return 1
    if p.is_dir():
        return sum(1 for _ in p.rglob("*") if _.is_file())
    return 0


def _file_unchanged(src: str, dst: str) -> bool:
    """只有实际内容相同才跳过，不能仅凭大小和修改时间判断。"""
    try:
        if _same_file(src, dst):
            return True
        if os.path.getsize(src) != os.path.getsize(dst):
            return False
        with open(src, "rb") as source, open(dst, "rb") as dest:
            while True:
                chunk = source.read(8 * 1024 * 1024)
                if chunk != dest.read(8 * 1024 * 1024):
                    return False
                if not chunk:
                    return True
    except OSError:
        return False


def _sync_dir(src_dir: str, dst_dir: str) -> tuple:
    """
    把源目录整棵树同步到目标目录（非破坏性合并）：
    - 新增/变更的文件会被复制；
    - 目标中已有的其他内容保留，不删除。
    返回 (已复制数, 失败数, 错误列表)。
    """
    if _same_file(src_dir, dst_dir):
        return 0, 0, []
    if _directories_overlap(src_dir, dst_dir):
        return 0, 1, ["源目录与目标目录不能互相包含"]
    copied = 0
    failed = 0
    errors = []
    try:
        os.makedirs(dst_dir, exist_ok=True)
    except OSError as e:
        return 0, 1, [f"无法创建目标目录 {dst_dir}: {e}"]

    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        try:
            os.makedirs(target_root, exist_ok=True)
        except OSError as e:
            failed += 1
            errors.append(f"{rel or '.':<30} {e}")
            continue
        for name in files:
            s = os.path.join(root, name)
            d = os.path.join(target_root, name)
            try:
                if _file_unchanged(s, d):
                    continue
                _copy_with_retry(s, d)
                copied += 1
            except OSError as e:
                failed += 1
                errors.append(f"{os.path.relpath(s, src_dir)}: {e}")
    return copied, failed, errors


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
                        if _same_file(match, dest_path):
                            continue
                        _ensure_dir(os.path.dirname(dest_path) or ".")
                        _copy_with_retry(match, dest_path)
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
                if _same_file(src, dest_dir):
                    return CopyResult(success=True, message="源与目标为同一目录，已跳过")
                if _directories_overlap(src, dest_dir):
                    return CopyResult(success=False, message="源目录与目标目录不能互相包含", files_failed=1)
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
                if _same_file(src, dest_path):
                    return CopyResult(success=True, message="源与目标为同一文件，已跳过")
                _ensure_dir(os.path.dirname(dest_path) or ".")
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


def copy_folder_single(src: str, dst: str) -> CopyResult:
    """
    文件夹整体备份：把源文件夹的整个内容同步到目标文件夹。
    新增的文件会在下一次运行时一并备份；目标中已有的文件保留。
    """
    if not src.strip():
        return CopyResult(success=False, message="源路径为空")
    if not dst.strip():
        return CopyResult(success=False, message="目标路径为空")

    src = os.path.expandvars(src)
    dst = os.path.expandvars(dst)
    dst_is_dir = _is_directory_path(dst)

    try:
        if not os.path.exists(src):
            return CopyResult(success=False, message=f"源不存在: {os.path.basename(src)}")

        if os.path.isdir(src):
            if os.path.exists(dst) and not dst_is_dir:
                return CopyResult(success=False, message=f"目标非目录: {dst}")
            copied, failed, errors = _sync_dir(src, dst)
        else:
            # 源是单个文件时直接放入目标文件夹（宽容处理）
            if not dst_is_dir:
                return CopyResult(success=False, message=f"整体备份目标必须是文件夹: {dst}")
            _ensure_dir(dst)
            dest_path = os.path.join(dst, os.path.basename(src))
            copied = 0
            failed = 0
            errors = []
            try:
                if not _file_unchanged(src, dest_path):
                    _copy_with_retry(src, dest_path)
                    copied = 1
            except OSError as e:
                failed = 1
                errors.append(f"{os.path.basename(src)}: {e}")

    except Exception as e:
        logger.exception(f"整体备份异常: {src}")
        return CopyResult(success=False, message=f"异常: {e}")

    if failed > 0:
        msg = f"整体备份: {copied} 复制, {failed} 失败"
        if errors:
            msg += f" ({'; '.join(errors[:2])})"
        return CopyResult(success=False, message=msg, files_copied=copied, files_failed=failed)

    return CopyResult(success=True, message=f"整体备份完成: {copied} 个文件", files_copied=copied)


def copy_all(sources: List[str], dests: List[str], source_modes: List[str] = None) -> CopyResult:
    """
    每个源复制到每个目标（M × N 全量复制）。
    source_modes 与 sources 一一对应；省略时沿用文件复制行为。
    返回汇总结果。
    """
    if sources is None:
        sources = []
    if dests is None:
        dests = []

    modes = source_modes if source_modes is not None else [BACKUP_FILE] * len(sources)
    if len(modes) != len(sources) or any(m not in (BACKUP_FILE, BACKUP_FOLDER) for m in modes):
        return CopyResult(success=False, message="源路径的复制类型无效")
    valid_sources = [(s.strip(), mode) for s, mode in zip(sources, modes)
                     if isinstance(s, str) and s.strip()]
    valid_dests = [d.strip() for d in dests if isinstance(d, str) and d.strip()]

    if not valid_sources:
        return CopyResult(success=False, message="无有效源路径")
    if not valid_dests:
        return CopyResult(success=False, message="无有效目标路径")

    total_copied = 0
    total_failed = 0
    pair_errors = []

    for src, mode in valid_sources:
        for dst in valid_dests:
            r = copy_folder_single(src, dst) if mode == BACKUP_FOLDER else copy_single(src, dst)
            total_copied += r.files_copied
            total_failed += r.files_failed if r.success else max(1, r.files_failed)
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


def copy_folder_all(sources: List[str], dests: List[str]) -> CopyResult:
    """
    每个源文件夹整体备份到每个目标文件夹（M×N）。
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
            r = copy_folder_single(src, dst)
            total_copied += r.files_copied
            total_failed += r.files_failed if r.success else max(1, r.files_failed)
            if not r.success:
                src_name = os.path.basename(src)
                dst_name = os.path.basename(dst) if not _is_directory_path(dst) else dst
                pair_errors.append(f"{src_name}→{dst_name}: {r.message}")

    total_pairs = len(valid_sources) * len(valid_dests)

    if total_failed == 0 and len(pair_errors) == 0:
        return CopyResult(
            success=True,
            message=f"全部成功: {total_copied} 个文件 ({total_pairs} 组备份)",
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
