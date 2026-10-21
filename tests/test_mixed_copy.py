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
        task = Task(sources=["folder", "file.txt"],
                    source_modes=[BACKUP_FOLDER, BACKUP_FILE])
        restored = Task.from_dict(json.loads(json.dumps(task.to_dict())))
        self.assertEqual(restored.source_modes, [BACKUP_FOLDER, BACKUP_FILE])
        self.assertEqual(restored.mode_label, "混合复制")

    def test_invalid_type_fails_without_copying(self):
        result = copy_all(["source"], ["dest"], ["invalid"])
        self.assertFalse(result.success)
        self.assertEqual(result.files_copied, 0)

    def test_executor_copies_mixed_sources_to_every_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "source"
            (folder / "nested").mkdir(parents=True)
            (folder / "nested" / "child.txt").write_text("child")
            single = root / "single.txt"
            single.write_text("single")
            dests = [root / "dest1", root / "dest2"]
            for dest in dests:
                dest.mkdir()
                (dest / "keep.txt").write_text("keep")
            task = Task(sources=["", str(folder), str(single)],
                        dests=[str(d) for d in dests],
                        source_modes=[BACKUP_FILE, BACKUP_FOLDER, BACKUP_FILE])
            task = Task.from_dict(json.loads(json.dumps(task.to_dict())))
            results = []
            Executor(lambda *args: results.append(args))._execute(task, None, False)
            self.assertTrue(results[-1][2], results[-1][3])
            self.assertIn("4", results[-1][3])
            for dest in dests:
                self.assertEqual((dest / "nested" / "child.txt").read_text(), "child")
                self.assertEqual((dest / "single.txt").read_text(), "single")
                self.assertEqual((dest / "keep.txt").read_text(), "keep")

    def test_dialog_add_remove_change_and_save_types(self):
        import ttkbootstrap as ttk
        from ui.dialogs import TaskEditDialog, BACKUP_MODE_LABELS

        root = ttk.Window()
        root.withdraw()
        try:
            original = Task(sources=["old-folder", "file.txt"], dests=["dest"],
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
            editor._remove_row(editor._rows[0], editor._paths[0])
            editor._add_btn.invoke()
            editor._mode_vars[1].set(BACKUP_MODE_LABELS[BACKUP_FOLDER])
            with patch("ui.dialogs.filedialog.askdirectory", return_value="new-folder"):
                editor._browse(editor._paths[1], editor._mode_vars[1])
            dialog._on_save()
            self.assertEqual(dialog.result.sources, ["picked.txt", "new-folder"])
            self.assertEqual(dialog.result.source_modes, [BACKUP_FILE, BACKUP_FOLDER])
            self.assertEqual(dialog.result.task_id, original.task_id)
            with patch.object(TaskEditDialog, "wait_window"):
                reopened = TaskEditDialog(root, dialog.result)
            self.assertEqual(reopened._src_editor.get_modes(), [BACKUP_FILE, BACKUP_FOLDER])
            reopened.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()

