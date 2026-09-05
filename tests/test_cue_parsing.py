import os
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401

import cue_split


class CueParsingTests(unittest.TestCase):
    def test_parse_single_image_cue_prefers_index_01_and_defaults_titles(self):
        cue = '''TITLE "Album"
PERFORMER "Circle"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "First"
    PERFORMER "Singer"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    INDEX 00 03:00:00
    INDEX 01 03:02:00
'''

        tracks, album, performer, starts, file_count = cue_split._parse_cue(cue)

        self.assertEqual(album, "Album")
        self.assertEqual(performer, "Circle")
        self.assertEqual(tracks, [(1, "First", "Singer"), (2, "Track 02", "")])
        self.assertEqual(starts, [0.0, 182.0])
        self.assertEqual(file_count, 1)

    def test_parse_multi_file_cue_marks_it_as_unsuitable_for_image_splitting(self):
        cue = '''FILE "01.flac" WAVE
  TRACK 01 AUDIO
    INDEX 01 00:00:00
FILE "02.flac" WAVE
  TRACK 02 AUDIO
    INDEX 01 00:00:00
'''

        _, _, _, _, file_count = cue_split._parse_cue(cue)

        self.assertEqual(file_count, 2)

    def test_cp932_cue_is_decoded_without_mojibake(self):
        text, encoding = cue_split._decode_cue_bytes('TITLE "上海紅茶館"'.encode("cp932"))

        self.assertEqual(text, 'TITLE "上海紅茶館"')
        self.assertIn(encoding.lower(), {"cp932", "shift_jis"})


class CuePreflightTests(unittest.TestCase):
    def _source(self, tmp, starts):
        image = os.path.join(tmp, "album.flac")
        open(image, "wb").close()
        return cue_split.CueSource(
            image_path=image, music_dir=tmp, source_kind="external",
            encoding="utf-8",
            tracks=[(1, "First", ""), (2, "Second", "")],
            starts=starts, file_count=1, album="Album", cue_text="x",
        )

    def test_breakpoint_past_the_end_of_the_image_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(tmp, [0.0, 300.0])
            with patch.object(cue_split, "_flac_duration", return_value=120.0):
                failure, starts = cue_split._check_source(source)

            # An empty track still decodes cleanly, so a split accepted here
            # would verify fine and could trash the original image.
            self.assertIsNotNone(failure)
            self.assertEqual(failure.reason, "breakpoints_past_end")
            self.assertEqual(starts, [])

    def test_breakpoints_inside_the_image_pass_the_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(tmp, [0.0, 60.0])
            with patch.object(cue_split, "_flac_duration", return_value=120.0):
                failure, starts = cue_split._check_source(source)

            self.assertIsNone(failure)
            self.assertEqual(starts, [0.0, 60.0])

    def test_free_path_never_reuses_an_existing_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            wanted = os.path.join(tmp, "01 - Song.flac")
            self.assertEqual(cue_split._free_path(wanted), wanted)

            open(wanted, "wb").close()
            first = cue_split._free_path(wanted)
            self.assertEqual(first, os.path.join(tmp, "01 - Song_split.flac"))

            # A second collision must not land back on the first fallback.
            open(first, "wb").close()
            second = cue_split._free_path(wanted)
            self.assertEqual(second, os.path.join(tmp, "01 - Song_split2.flac"))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("flac"),
                     "FFmpeg and FLAC are required for split verification")
class CueAudioVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        image = os.path.join(self.temp.name, "image.flac")
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=stereo", "-t", "2", "-c:a", "flac", image,
        ], check=True, capture_output=True)
        self.source = cue_split.CueSource(
            image_path=image, music_dir=self.temp.name,
            source_kind="external", encoding="utf-8",
            tracks=[(1, "First", ""), (2, "Second", "")], starts=[0, 1],
        )

    def test_nonempty_short_tracks_survive_split_verification(self):
        for breakpoint in (0.25, 1.5, 1.75):
            with self.subTest(breakpoint=breakpoint):
                self.source.starts = [0, breakpoint]
                result = cue_split.split_album(
                    self.source, original_policy="keep", log=lambda _: None)
                self.assertTrue(result.ok, result.message)
                self.assertEqual(len(result.created), 2)
                for path, duration in zip(result.created,
                                          (breakpoint, 2 - breakpoint)):
                    self.assertAlmostEqual(cue_split._flac_duration(path),
                                           duration, places=5)

    def test_breakpoints_at_or_beyond_eof_leave_original_untouched(self):
        for breakpoint in (2, 5):
            with self.subTest(breakpoint=breakpoint):
                self.source.starts = [0, breakpoint]
                with patch.object(cue_split, "_trash") as trash:
                    result = cue_split.split_album(self.source, log=lambda _: None)
                self.assertFalse(result.ok)
                self.assertEqual(result.reason, "breakpoints_past_end")
                trash.assert_not_called()
                self.assertTrue(os.path.isfile(self.source.image_path))

    def test_empty_output_is_rejected_even_when_source_duration_is_unknown(self):
        self.source.starts = [0, 5]
        read_duration = cue_split._flac_duration
        with patch.object(cue_split, "_flac_duration", side_effect=lambda path:
                          0 if path == self.source.image_path else read_duration(path)), \
                patch.object(cue_split, "_trash") as trash:
            result = cue_split.split_album(self.source, log=lambda _: None)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "empty_track")
        trash.assert_not_called()
        self.assertTrue(os.path.isfile(self.source.image_path))
