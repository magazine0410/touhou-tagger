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
    def test_locked_changes_compose_with_tag_filter(self):
        script = textwrap.dedent('''
            import logging
            from unittest.mock import patch
            from PyQt5 import QtCore, QtWidgets
            import gui

            def exercise(app):
                window = next(w for w in app.topLevelWidgets()
                              if hasattr(w, "_wiki_tab"))
                wiki = window._wiki_tab
                def change(path, tag, locked=False, new="Wiki"):
                    return dict(path=path, filename="01 Song.flac", tag=tag,
                                old="Current", new=new, locked=locked)
                wiki._results = [dict(
                    album="Album", music_dir="/album", source="THBWiki",
                    tagged=0, skipped=0, errors=0, error=None, locked_skipped=4,
                    tag_changes=[
                        change("/album/Disc 1/01 Song.flac", "grouping", True),
                        change("/album/Disc 1/01 Song.flac", "album", True),
                        change("/album/Disc 2/01 Song.flac", "grouping", True, None),
                        change("/album/Disc 3/01 Song.flac", "grouping"),
                    ], date_mismatch=("2000", "2001")), dict(
                    album="Other", music_dir="/other", source="THBWiki",
                    tagged=0, skipped=0, errors=0, error=None,
                    tag_changes=[change("/other/01 Song.flac", "album")])]
                widget = wiki._build_changes_tree()
                tree = widget.findChild(QtWidgets.QTreeWidget)
                checkboxes = {c.text(): c for c in widget.findChildren(QtWidgets.QCheckBox)}
                locked = checkboxes["🔒 Only locked"]
                disc = checkboxes["⚠ Only discrepancies"]
                grouping = checkboxes["grouping"]
                def visible_leaves():
                    leaves = []
                    def visit(item):
                        if item.isHidden():
                            return
                        if not item.childCount():
                            leaves.append(item)
                        for i in range(item.childCount()):
                            visit(item.child(i))
                    for i in range(tree.topLevelItemCount()):
                        visit(tree.topLevelItem(i))
                    return leaves
                assert len(visible_leaves()) == 6
                locked.setChecked(True)
                assert grouping.isEnabled()
                assert len(visible_leaves()) == 3
                grouping.setChecked(True)
                leaves = visible_leaves()
                assert len(leaves) == 2
                assert all(c.text(0) == "🔒 grouping" for c in leaves)
                assert leaves[0].parent() != leaves[1].parent()
                assert leaves[1].text(2) == "(would clear)"
                assert tree.topLevelItem(1).isHidden()
                checkboxes["album"].setChecked(True)
                assert len(visible_leaves()) == 3
                checkboxes["album"].setChecked(False)
                locked.setChecked(False)
                assert len(visible_leaves()) == 3
                disc.setChecked(True)
                assert len(visible_leaves()) == 1
                assert not grouping.isEnabled()
                locked.setChecked(True)
                assert not disc.isChecked()
                assert grouping.isEnabled()
                assert len(visible_leaves()) == 2
                disc.setChecked(True)
                assert not locked.isChecked()
                disc.setChecked(False)
                grouping.setChecked(False)
                assert len(visible_leaves()) == 6
                wiki._jobs = [("Album", "/album"), ("Other", "/other")]
                with patch.object(wiki, "_show_summary_dialog") as summary:
                    wiki._on_all_done()
                text = summary.call_args.args[0]
                assert "Locks prevented 3 tag change(s) across 2 track(s)" in text, text
                assert "4 tag(s) left untouched" in text, text
                return 0

            with patch.object(gui, "_setup_gui_logging", return_value=(
                logging.getLogger("gui-test"), None
            )), patch.object(gui, "_refresh_auth_cookie", return_value=False), \\
                    patch.object(QtWidgets.QApplication, "exec_", exercise):
                gui.gui_main()
        ''')
        self._run_gui_script(script)

    def test_numeric_track_order_in_both_tabs_and_after_refresh(self):
        script = textwrap.dedent('''
            import logging
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from PyQt5 import QtCore, QtWidgets
            import gui

            def exercise(app):
                window = next(w for w in app.topLevelWidgets()
                              if hasattr(w, "_wiki_tab"))
                wiki = window._wiki_tab
                editor = window._tag_edit_tab
                wiki._skip_done_cb.setChecked(False)
                wiki._skip_genre_cb.setChecked(False)
                with tempfile.TemporaryDirectory() as tmp:
                    album = Path(tmp) / "B album"
                    for disc in (2, 10):
                        folder = album / f"Disc {disc}"
                        folder.mkdir(parents=True)
                        for name in ("10", "100", "11", "99", "unknown"):
                            (folder / f"{name}.flac").touch()
                    # Empty audio fixtures exercise filename number fallback;
                    # all GUI reads stay within the temporary album.
                    wiki._add_directory(str(album))
                    other = Path(tmp) / "A album"
                    other.mkdir()
                    wiki._add_directory(str(other))
                    tree = wiki._tree
                    tree.sortItems(0, QtCore.Qt.AscendingOrder)
                    assert tree.topLevelItem(0).text(0) == str(other)
                    item = tree.topLevelItem(1)
                    expected = [f"{d}-{n}. {filename}.flac"
                                for d in (2, 10)
                                for n, filename in (("10", "10"), ("11", "11"),
                                                    ("99", "99"), ("100", "100"),
                                                    ("??", "unknown"))]
                    def labels():
                        return [item.child(i).text(0) for i in range(item.childCount())]
                    assert labels() == expected, labels()
                    tree.sortItems(0, QtCore.Qt.DescendingOrder)
                    assert labels() == expected[::-1], labels()
                    wiki._refresh_grouping_for_dirs({str(album)})
                    assert labels() == expected[::-1], labels()
                    tree.sortItems(0, QtCore.Qt.AscendingOrder)
                    assert labels() == expected, labels()
                    for i in range(item.childCount()):
                        item.child(i).setText(3, f"{item.childCount() - i:02d}")
                    tree.sortItems(3, QtCore.Qt.AscendingOrder)
                    groupings = [item.child(i).text(3) for i in range(item.childCount())]
                    assert groupings == sorted(groupings), groupings

                    # A partial file drop followed by the whole album must
                    # insert missing tracks in numeric order without duplicates.
                    with patch.object(gui, "read_all_tags", return_value={}):
                        editor._add_tracks(str(album), wanted={
                            str(album / "Disc 2" / "100.flac")})
                        editor._add_tracks(str(album))
                    numbers = [editor._table.item(row, 0).text()
                               for row in range(1, editor._table.rowCount())]
                    assert numbers == [label.split(". ")[0] for label in expected], numbers
                    assert not editor._dirty
                return 0

            with patch.object(gui, "_setup_gui_logging", return_value=(
                logging.getLogger("gui-test"), None
            )), patch.object(gui, "_refresh_auth_cookie", return_value=False), \\
                    patch.object(QtWidgets.QApplication, "exec_", exercise):
                gui.gui_main()
        ''')
        self._run_gui_script(script)

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
        self._run_gui_script(script)

    def _run_gui_script(self, script):
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
