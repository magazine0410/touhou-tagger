import unittest

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
