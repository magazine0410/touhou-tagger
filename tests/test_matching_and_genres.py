import unittest

from tests import _support  # noqa: F401

import touhou_tagger


class MatchingAndGenreTests(unittest.TestCase):
    def test_filename_title_and_number_choose_the_correct_wiki_track(self):
        wiki = [
            {"disc": 1, "number": 1, "title": "First Song"},
            {"disc": 1, "number": 2, "title": "Second Song"},
        ]
        local = [
            {"disc": 1, "number": 2, "filename": "02 - Second Song.flac", "title": None},
            {"disc": 1, "number": 1, "filename": "(01) [Circle] First Song.flac", "title": None},
        ]

        pairs = touhou_tagger.match_tracks(wiki, local)

        self.assertEqual([track[1]["number"] for track in pairs], [2, 1])

    def test_comparison_accepts_reordered_tracks_when_titles_match(self):
        wiki = [
            {"disc": 1, "number": 1, "title": "First Song"},
            {"disc": 1, "number": 2, "title": "Second Song"},
        ]
        local = [
            {"disc": 1, "number": 1, "filename": "01 - Second Song.flac", "title": None,
             "path": "second.flac"},
            {"disc": 1, "number": 2, "filename": "02 - First Song.flac", "title": None,
             "path": "first.flac"},
        ]

        report = touhou_tagger.compare_tracklists(wiki, local)

        self.assertFalse(report["severe"])
        self.assertEqual(report["match_rate"], 1.0)
        self.assertEqual(report["discrepancies"], [])

    def test_comparison_reports_a_genuinely_wrong_title(self):
        wiki = [{"disc": 1, "number": 1, "title": "First Song"}]
        local = [{"disc": 1, "number": 1, "filename": "01 - Unrelated.flac",
                  "title": None, "path": "unrelated.flac"}]

        report = touhou_tagger.compare_tracklists(wiki, local)

        self.assertTrue(report["severe"])
        self.assertEqual(report["discrepancies"][0]["kind"], "title_mismatch")

    def test_genre_merge_translates_deduplicates_and_keeps_existing_order(self):
        merged = touhou_tagger._merge_genres(
            ["独立音乐", "Rock", "rock", "Personal genre"],
            ["Indie", "Electronic", "PERSONAL GENRE"],
        )

        self.assertEqual(merged, ["Indie", "Rock", "Personal genre", "Electronic"])
