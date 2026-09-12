import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

import file_scan


class FileScanTests(unittest.TestCase):
    def test_track_tags_sort_numerically_even_when_filenames_disagree(self):
        tags = {"(10).flac": "10/183", "(100).flac": "100",
                "(11).flac": "11", "99.flac": "2", "(09).flac": "9"}
        with tempfile.TemporaryDirectory() as tmp:
            for name in tags:
                (Path(tmp) / name).touch()
            with patch.object(file_scan.mutagen, "File", side_effect=lambda path, **kw:
                              {"tracknumber": [tags[Path(path).name]]}):
                tracks = file_scan.scan_music_files(tmp)
        self.assertEqual([t["number"] for t in tracks], [2, 9, 10, 11, 100])
        self.assertEqual(tracks[0]["filename"], "99.flac")

    def test_numeric_discs_and_filename_fallbacks(self):
        names = ["unknown-z.flac", "100.flac", "11.flac", "2-b.flac",
                 "unknown-a.flac", "2-a.flac", "10.flac"]
        with tempfile.TemporaryDirectory() as tmp:
            for disc in ("Disc 10", "Disc 2"):
                folder = Path(tmp) / disc
                folder.mkdir()
                for name in names:
                    (folder / name).touch()
            with patch.object(file_scan.mutagen, "File", return_value=None):
                tracks = file_scan.scan_music_files(tmp)
        expected_names = ["2-a.flac", "2-b.flac", "10.flac", "11.flac",
                          "100.flac", "unknown-a.flac", "unknown-z.flac"]
        self.assertEqual([(t["disc"], t["filename"]) for t in tracks],
                         [(disc, name) for disc in (2, 10) for name in expected_names])

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


    def test_a_file_in_a_disc_folder_resolves_to_its_album(self):
        # Dropping one track of a multi-disc set must queue the album, not the
        # disc folder: scanning "Disc 2" alone would renumber it as disc 1.
        with tempfile.TemporaryDirectory() as tmp:
            album = Path(tmp) / "Two Disc Album"
            for disc in ("Disc 1", "CD2", "disk 3"):
                (album / disc).mkdir(parents=True)
            for disc in ("Disc 1", "CD2", "disk 3"):
                track = album / disc / "01.flac"
                track.touch()
                self.assertEqual(
                    file_scan.album_dir_for_file(str(track)), str(album), disc
                )

    def test_a_file_in_a_plain_album_folder_resolves_to_that_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            album = Path(tmp) / "Flat Album"
            album.mkdir()
            track = album / "01.flac"
            track.touch()
            self.assertEqual(
                file_scan.album_dir_for_file(str(track)), str(album)
            )
            # A folder that merely starts with a digit is not a disc folder.
            other = Path(tmp) / "2022 Album"
            other.mkdir()
            track = other / "01.flac"
            track.touch()
            self.assertEqual(
                file_scan.album_dir_for_file(str(track)), str(other)
            )
