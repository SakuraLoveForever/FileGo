import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.file_copy import copy_all, copy_single, copy_folder_single, _copy_with_retry


class CopySafetyTests(unittest.TestCase):
    def test_self_copy_is_skipped_and_next_pair_still_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            source.write_bytes(b"original")
            result = copy_all([str(source), str(source)],
                              [str(root), str(root / "backup")])
            self.assertTrue(result.success, result.message)
            self.assertEqual(source.read_bytes(), b"original")
            self.assertEqual((root / "backup" / "note.txt").read_bytes(), b"original")
            self.assertEqual(result.files_copied, 1)

    def test_same_filename_with_different_contents_is_overwritten_in_each_mode(self):
        for mode in ("file", "folder", "wildcard"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source_dir = root / "source"
                dest_dir = root / "dest"
                source_dir.mkdir()
                dest_dir.mkdir()
                source = source_dir / "note.txt"
                dest = dest_dir / "note.txt"
                source.write_bytes(b"new contents")
                dest.write_bytes(b"old contents")
                # 大小、时间相同也不能当作内容相同。
                os.utime(source, (1700000000, 1700000000))
                os.utime(dest, (1700000000, 1700000000))
                (dest_dir / "keep.txt").write_bytes(b"keep")
                if mode == "folder":
                    result = copy_folder_single(str(source_dir), str(dest_dir))
                else:
                    src = str(source_dir / "*.txt") if mode == "wildcard" else str(source)
                    result = copy_single(src, str(dest_dir))
                self.assertTrue(result.success, result.message)
                self.assertEqual(dest.read_bytes(), b"new contents")
                self.assertEqual(source.read_bytes(), b"new contents")
                self.assertEqual((dest_dir / "keep.txt").read_bytes(), b"keep")

    def test_failed_replacement_preserves_source_and_old_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            dest = root / "dest.txt"
            source.write_bytes(b"new")
            dest.write_bytes(b"old")
            with patch("services.file_copy.os.replace", side_effect=PermissionError("locked")):
                with self.assertRaises(OSError):
                    _copy_with_retry(str(source), str(dest), retries=1)
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(dest.read_bytes(), b"old")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["dest.txt", "source.txt"])
            with patch("services.file_copy.os.replace", side_effect=PermissionError("locked")), \
                    patch("time.sleep"):
                result = copy_single(str(source), str(dest))
            self.assertFalse(result.success)
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(dest.read_bytes(), b"old")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["dest.txt", "source.txt"])

    def test_interrupted_write_keeps_old_destination(self):
        def interrupted(source, dest, **kwargs):
            dest.write(b"partial")
            raise OSError("disk full")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            dest = root / "dest.txt"
            source.write_bytes(b"new")
            dest.write_bytes(b"old")
            with patch("services.file_copy.shutil.copyfileobj", side_effect=interrupted), \
                    patch("time.sleep"):
                result = copy_single(str(source), str(dest))
            self.assertFalse(result.success)
            self.assertEqual(source.read_bytes(), b"new")
            self.assertEqual(dest.read_bytes(), b"old")
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["dest.txt", "source.txt"])

    def test_wildcard_self_copy_preserves_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            source.write_bytes(b"keep")
            result = copy_single(str(root / "*.txt"), tmp)
            self.assertTrue(result.success, result.message)
            self.assertEqual(source.read_bytes(), b"keep")
            self.assertEqual(result.files_copied, 0)

    def test_file_is_not_deleted_to_make_destination_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            dest = root / "dest.txt"
            source.write_bytes(b"source")
            dest.write_bytes(b"keep")
            with self.assertLogs("FileGo", level="ERROR"):
                result = copy_single(str(source), str(dest) + os.sep)
            self.assertFalse(result.success)
            self.assertEqual(source.read_bytes(), b"source")
            self.assertEqual(dest.read_bytes(), b"keep")

    def test_hardlink_to_source_is_skipped_without_changing_either_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.txt"
            dest = root / "alias.txt"
            source.write_bytes(b"keep")
            os.link(source, dest)
            result = copy_single(str(source), str(dest))
            self.assertTrue(result.success, result.message)
            self.assertEqual(source.read_bytes(), b"keep")
            self.assertTrue(os.path.samefile(source, dest))
            self.assertEqual(result.files_copied, 0)

    def test_directory_copy_to_itself_preserves_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            (source / "note.txt").write_bytes(b"keep")
            result = copy_single(str(source), tmp)
            self.assertTrue(result.success, result.message)
            self.assertEqual((source / "note.txt").read_bytes(), b"keep")

    def test_overlapping_directories_are_rejected_before_writing(self):
        for copier in (copy_single, copy_folder_single):
            with self.subTest(mode=copier.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source"
                source.mkdir()
                (source / "note.txt").write_bytes(b"keep")
                result = copier(str(source), str(source / "nested"))
                self.assertFalse(result.success)
                self.assertEqual((source / "note.txt").read_bytes(), b"keep")
                self.assertFalse((source / "nested").exists())

    def test_missing_source_counts_as_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            source.write_bytes(b"good")
            result = copy_all([str(source), str(root / "missing.txt")],
                              [str(root / "backup"), str(root / "backup2")])
            self.assertFalse(result.success)
            self.assertEqual(result.files_copied, 1)
            self.assertEqual(result.files_failed, 1)


if __name__ == "__main__":
    unittest.main()
