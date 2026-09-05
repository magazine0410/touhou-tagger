import tempfile
import unittest
from pathlib import Path

from mutagen.id3 import ID3

from tests import _support  # noqa: F401

import tag_io


class TagIoTests(unittest.TestCase):
    def test_mp3_grouping_and_multi_genre_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.mp3"
            path.touch()  # ID3 tags can be tested without shipping audio.
            tag_io.set_grouping(str(path), "Original Theme")
            tag_io.set_genres(str(path), ["Rock", "Electronic"])
            tags = ID3(path)

            self.assertEqual(tag_io.read_grouping(str(path)), "Original Theme")
            self.assertEqual(tags["TIT1"].text, ["Original Theme"])
            self.assertEqual(tags.getall("TCON")[0].text, ["Rock", "Electronic"])

            tag_io.clear_grouping(str(path))
            self.assertIsNone(tag_io.read_grouping(str(path)))

    def test_dry_run_does_not_create_or_modify_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.mp3"
            path.touch()
            tag_io.set_grouping(str(path), "Theme", dry_run=True)
            tag_io.set_genres(str(path), ["Rock"], dry_run=True)

            self.assertIsNone(tag_io.read_grouping(str(path)))
            self.assertEqual(path.read_bytes(), b"")

    def test_cjk_guard_distinguishes_display_and_romanised_text(self):
        self.assertFalse(tag_io._is_latin_script("上海紅茶館"))
        self.assertTrue(tag_io._is_latin_script("Shanghai Teahouse"))

    def test_delete_tag_reports_absence_but_raises_on_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tags.mp3"
            path.touch()
            tag_io._set_tag(str(path), "titlesort", "Kachou Fuugetsu")

            # Nothing to remove is False, not a failure.
            self.assertFalse(tag_io._delete_tag(str(path), "composer"))
            # A write that cannot happen must not look like a clean delete:
            # the Tag Edit tab would report the tag as saved and lock it.
            path.chmod(0o444)
            try:
                with self.assertRaises(Exception):
                    tag_io._delete_tag(str(path), "titlesort")
            finally:
                path.chmod(0o644)
            self.assertEqual(ID3(path)["TSOT"].text, ["Kachou Fuugetsu"])

            self.assertTrue(tag_io._delete_tag(str(path), "titlesort"))
            self.assertNotIn("TSOT", ID3(path))
