import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ttkbootstrap as ttk

from models.task import Task
from ui.task_row import TaskRow


class TaskPathTests(unittest.TestCase):
    def test_each_pair_has_two_path_rows_with_matching_open_buttons(self):
        # ttkbootstrap caches its Style across the other GUI test's destroyed root.
        style_patch = patch.object(ttk.Style, "instance", None)
        style_patch.start()
        self.addCleanup(style_patch.stop)
        root = ttk.Window()
        root.withdraw()
        self.addCleanup(root.destroy)
        task = Task(sources=["source one.txt", "source two"], dests=["dest one", "dest two"])
        row = TaskRow(root, task, {})
        with patch.object(row, "_open_location") as open_location:
            entries = [w for w in row._paths_frame.winfo_children() if isinstance(w, ttk.Entry)]
            buttons = [w for w in row._paths_frame.winfo_children() if isinstance(w, ttk.Button)]
            self.assertEqual([w.get() for w in entries],
                             ["source one.txt", "dest one", "source two", "dest two"])
            for button, entry in zip(buttons, entries):
                self.assertEqual(button.grid_info()["row"], entry.grid_info()["row"])
                button.invoke()
            self.assertEqual([call.args[0] for call in open_location.call_args_list],
                             [w.get() for w in entries])
        task.dests[0] = "changed destination"
        row.update_display(task)
        entries = [w for w in row._paths_frame.winfo_children() if isinstance(w, ttk.Entry)]
        self.assertEqual(entries[1].get(), "changed destination")

    def test_open_directory_select_file_and_report_missing_path(self):
        with tempfile.TemporaryDirectory(prefix="FileGo 路径 ") as tmp:
            folder = Path(tmp).resolve()
            file = folder / "中文 file.txt"
            file.write_text("test")
            with patch("ui.task_row.os.startfile") as startfile, \
                    patch("ui.task_row.subprocess.Popen") as popen, \
                    patch("ui.task_row.messagebox.showwarning") as warning:
                TaskRow._open_location(None, str(folder))
                startfile.assert_called_once_with(str(folder))
                TaskRow._open_location(None, str(file))
                popen.assert_called_once_with(["explorer.exe", f"/select,{file}"])
                TaskRow._open_location(None, str(folder / "missing"))
                warning.assert_called_once()
                self.assertEqual(startfile.call_count, 1)
                self.assertEqual(popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
