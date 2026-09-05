"""Exercise GUI lifecycle and summary behavior with isolated user settings."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


@unittest.skipUnless(importlib.util.find_spec("PyQt5"), "PyQt5 is optional")
class GuiRegressionTests(unittest.TestCase):
    def test_cancelled_shutdown_and_partial_romanisation(self):
        # QApplication and the nested GUI classes live in their own process;
        # none of the user's settings, cookies or running windows are touched.
        script = textwrap.dedent('''
            import logging
            import threading
            from unittest.mock import patch
            from PyQt5 import QtCore, QtGui, QtWidgets
            import gui

            def exercise(app):
                window = next(w for w in app.topLevelWidgets()
                              if hasattr(w, "_wiki_tab"))
                wiki = window._wiki_tab
                romanise = window._romanize_tab

                class Worker(QtCore.QThread):
                    def __init__(self):
                        super().__init__()
                        self.stop = threading.Event()

                    def run(self):
                        self.stop.wait(5)

                    def request_cancel(self):
                        self.stop.set()

                # Stop the worker, then decline to discard unsaved edits.
                worker = Worker()
                wiki._worker = worker
                window._tag_edit_tab._dirty.add(("pending.flac", "title"))
                worker.start()
                with patch.object(QtWidgets.QMessageBox, "warning", side_effect=[
                    QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Cancel,
                ]):
                    event = QtGui.QCloseEvent()
                    window.closeEvent(event)
                assert not event.isAccepted()
                assert not worker.isRunning()
                assert not wiki._shutting_down
                # A subsequent completion must display its summary again.
                with patch.object(wiki, "_show_summary_dialog") as summary:
                    wiki._on_all_done()
                summary.assert_called_once()
                window._tag_edit_tab._dirty.clear()

                def result(name, errors=0, error=None):
                    return dict(album=name, errors=errors, error=error,
                                romanized=0, overwritten=0, skipped=0, no_title=0)

                romanise._results = [result("Good"), result("Partial", errors=1),
                                     result("Failed", error="directory missing")]
                romanise._dirs = ["Good", "Partial", "Failed"]
                romanise._auto_clear_cb.setChecked(True)
                romanise._table.setRowCount(3)
                for row, name in enumerate(romanise._dirs):
                    romanise._table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
                with patch.object(romanise, "_show_summary_dialog") as summary:
                    romanise._on_all_done()
                summary.assert_called_once()
                text = summary.call_args.args[0]
                assert "Successfully processed 1 album(s)" in text, text
                assert "✓ Good" in text, text
                assert "✓ Partial" not in text, text
                assert "Finished with write errors" in text, text
                assert "⚠ Partial" in text, text
                assert "Failed to process 1 album(s)" in text, text
                remaining = [romanise._table.item(row, 0).text()
                             for row in range(romanise._table.rowCount())]
                assert remaining == ["Partial", "Failed"], remaining
                return 0

            with patch.object(gui, "_setup_gui_logging", return_value=(
                logging.getLogger("gui-test"), None
            )), patch.object(gui, "_refresh_auth_cookie", return_value=False), \\
                    patch.object(gui, "ROMANIZER_AVAILABLE", True), \\
                    patch.object(QtWidgets.QApplication, "exec_", exercise):
                gui.gui_main()
        ''')
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                       TOUHOU_TAGGER_CONFIG_DIR=tmp,
                       TOUHOU_TAGGER_LOG_DIR=tmp, THWIKI_COOKIE_AUTO="0",
                       PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
                       PYTHONPATH=str(Path(__file__).resolve().parents[1] / "source"))
            completed = subprocess.run(
                [sys.executable, "-c", script], env=env,
                capture_output=True, text=True, encoding="utf-8", timeout=30,
            )
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)
