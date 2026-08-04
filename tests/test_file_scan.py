import tempfile
import unittest
from pathlib import Path

from tests import _support  # noqa: F401

import file_scan


class FileScanTests(unittest.TestCase):
    def test_scans_disc_folders_and_ignores_non_audio_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            album = Path(tmp)
            disc_one = album / "Disc 1"
            disc_two = album / "CD02 - Bonus"
            disc_one.mkdir()
            disc_two.mkdir()
            (disc_one / "01 - First.flac").touch()
            (disc_two / "02 - Second.OPUS").touch()
            (album / "notes.txt").touch()

            tracks = file_scan.scan_music_files(str(album))

        self.assertEqual(
            [(t["disc"], t["number"], t["filename"]) for t in tracks],
            [(1, 1, "01 - First.flac"), (2, 2, "02 - Second.OPUS")],
        )

    def test_slug_fallback_removes_optional_layout_decoration(self):
        with tempfile.TemporaryDirectory() as tmp:
            album = Path(tmp) / "2022.08.14_[EUCD-0022]_Album Name_[C100]"
            album.mkdir()

            self.assertEqual(file_scan.guess_album_slug(str(album)), "Album_Name")

    def test_artist_container_expands_even_without_artist_brackets(self):
        with tempfile.TemporaryDirectory() as tmp:
            artist = Path(tmp) / "ShibayanRecords"
            album_a = artist / "Album A"
            album_b = artist / "Album B"
            album_a.mkdir(parents=True)
            album_b.mkdir()
            (album_a / "01.mp3").touch()
            (album_b / "01.flac").touch()

            found = file_scan._expand_to_album_dirs(str(artist))

        self.assertEqual(found, [str(album_a), str(album_b)])

