import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import BACKUP_FILE, BACKUP_FOLDER
from models.task import Task
from scheduler.executor import Executor
from services.file_copy import copy_all


class MixedCopyTests(unittest.TestCase):
    def test_legacy_mode_applies_to_each_source(self):
        task = Task.from_dict({"sources": ["a", "b"], "backup_mode": BACKUP_FOLDER})
        self.assertEqual(task.source_modes, [BACKUP_FOLDER, BACKUP_FOLDER])

    def test_mixed_types_survive_json(self):
        task = Task(sources=["folder", "file.txt"], dests=["d1", "d2"],
                    source_modes=[BACKUP_FOLDER, BACKUP_FILE])
        restored = Task.from_dict(json.loads(json.dumps(task.to_dict())))
        self.assertEqual(restored.source_modes, [BACKUP_FOLDER, BACKUP_FILE])
        self.assertEqual(restored.mode_label, "混合复制")
        self.assertEqual(restored.pair_count, 2)

    def test_invalid_type_fails_without_copying(self):
        result = copy_all(["source"], ["dest"], ["invalid"])
        self.assertFalse(result.success)
        self.assertEqual(result.files_copied, 0)

    def test_unequal_source_and_destination_counts_are_rejected(self):
        task = Task(sources=["a", "b"], dests=["d1"])
        self.assertFalse(task.is_valid())
        self.assertTrue(any("数量必须一致" in e for e in task.validate()), task.validate())

        result = copy_all(["a"], ["d1", "d2"])
        self.assertFalse(result.success)
        self.assertIn("数量不一致", result.message)

    def test_half_filled_pair_is_rejected(self):
        task = Task(sources=["a", ""], dests=["dest1", "d2"])
        errors = task.validate()
        self.assertTrue(any("第 2 组" in e for e in errors), errors)

        result = copy_all(["a", ""], ["dest1", "d2"])
        self.assertFalse(result.success)
        self.assertIn("第 2 组", result.message)

    def test_blank_pairs_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "note.txt"
            source.write_text("note")
            dest = root / "dest"
            dest.mkdir()
            task = Task(sources=["", str(source)], dests=["", str(dest)])
            self.assertEqual(task.pair_count, 1)
            self.assertTrue(task.is_valid(), task.validate())
            result = copy_all(task.sources, task.dests, task.source_modes)
            self.assertTrue(result.success, result.message)
            self.assertEqual((dest / "note.txt").read_text(), "note")

    def test_executor_copies_each_source_to_its_paired_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "source"
            (folder / "nested").mkdir(parents=True)
            (folder / "nested" / "child.txt").write_text("child")
            single = root / "single.txt"
            single.write_text("single")
            dest1 = root / "dest1"
            dest2 = root / "dest2"
            for dest in (dest1, dest2):
                dest.mkdir()
                (dest / "keep.txt").write_text("keep")
            # 源 #1（整体备份）→ 目标 #1；源 #2（单文件）→ 目标 #2
            task = Task(sources=[str(folder), str(single)],
                        dests=[str(dest1), str(dest2)],
                        source_modes=[BACKUP_FOLDER, BACKUP_FILE])
            task = Task.from_dict(json.loads(json.dumps(task.to_dict())))
            results = []
            Executor(lambda *args: results.append(args))._execute(task, None, False)
            self.assertTrue(results[-1][2], results[-1][3])
            self.assertIn("2 组", results[-1][3])
            # 目标 #1 只收到文件夹内容
            self.assertEqual((dest1 / "nested" / "child.txt").read_text(), "child")
            self.assertEqual((dest1 / "keep.txt").read_text(), "keep")
            self.assertFalse((dest1 / "single.txt").exists())
            # 目标 #2 只收到单文件
            self.assertEqual((dest2 / "single.txt").read_text(), "single")
            self.assertEqual((dest2 / "keep.txt").read_text(), "keep")
            self.assertFalse((dest2 / "nested").exists())

    def test_dialog_add_remove_change_and_save_types(self):
        import ttkbootstrap as ttk
        from ui.dialogs import TaskEditDialog, BACKUP_MODE_LABELS

        root = ttk.Window()
        root.withdraw()
        try:
            original = Task(sources=["old-folder", "file.txt"],
                            dests=["dest1", "dest2"],
                            backup_mode=BACKUP_FOLDER, last_run="2026-10-21T14:10:52",
                            last_status="error: " + "long/path/" * 200)
            with patch.object(TaskEditDialog, "wait_window"):
                dialog = TaskEditDialog(root, original)
            root.update_idletasks()
            from ttkbootstrap.utility import scale_size
            self.assertLessEqual(dialog.winfo_reqwidth(), scale_size(root, 680))
            self.assertLessEqual(dialog.winfo_reqheight(), scale_size(root, 650))
            editor = dialog._src_editor
            self.assertEqual(editor.get_modes(), [BACKUP_FOLDER, BACKUP_FOLDER])
            editor._mode_vars[1].set(BACKUP_MODE_LABELS[BACKUP_FILE])
            with patch("ui.dialogs.filedialog.askopenfilename", return_value="picked.txt"):
                editor._browse(editor._paths[1], editor._mode_vars[1])
            # 删除源 #1 时，目标 #1 同步删除，保持按序号配对
            editor._remove_row(editor._rows[0], editor._paths[0])
            self.assertEqual(dialog._dst_editor.get_paths(), ["dest2"])
            # 添加一组：源和目标各加一行
            editor._add_btn.invoke()
            self.assertEqual(editor.row_count, 2)
            self.assertEqual(dialog._dst_editor.row_count, 2)
            editor._mode_vars[1].set(BACKUP_MODE_LABELS[BACKUP_FOLDER])
            with patch("ui.dialogs.filedialog.askdirectory", return_value="new-folder"):
                editor._browse(editor._paths[1], editor._mode_vars[1])
            with patch("ui.dialogs.filedialog.askdirectory", return_value="new-dest"):
                dialog._dst_editor._browse(dialog._dst_editor._paths[1])
            dialog._on_save()
            self.assertIsNotNone(dialog.result)
            self.assertEqual(dialog.result.sources, ["picked.txt", "new-folder"])
            self.assertEqual(dialog.result.dests, ["dest2", "new-dest"])
            self.assertEqual(dialog.result.source_modes, [BACKUP_FILE, BACKUP_FOLDER])
            self.assertEqual(dialog.result.task_id, original.task_id)
            with patch.object(TaskEditDialog, "wait_window"):
                reopened = TaskEditDialog(root, dialog.result)
            self.assertEqual(reopened._src_editor.get_modes(), [BACKUP_FILE, BACKUP_FOLDER])
            self.assertEqual(reopened._dst_editor.get_paths(), ["dest2", "new-dest"])
            reopened.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()