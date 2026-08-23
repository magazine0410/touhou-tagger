"""The "Force overwrite staff tags" policy for credit tags.

Credits are skip-if-present by default, which means a re-run cannot correct a
credit an earlier release wrote.  ``force_credits`` makes the wiki
authoritative instead, while still leaving a credit the wiki already agrees
with untouched.
"""
import tempfile
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401

import tag_selection
import touhou_tagger


def make_plan(tmp, *, force_credits):
    return touhou_tagger.AlbumPlan(
        wiki_album="Some_Album",
        music_dir=tmp,
        dry_run=False,
        romanize=False,
        force_titlesort=False,
        force_credits=force_credits,
        fetch_metadata=False,
        fetch_credits=True,
        use_touhoudb=False,
        touhoudb_add_missing=False,
        selected_tags=("arranger", "vocalist", "lyricist"),
        wiki_tracks=[{
            "number": 1, "disc": 1, "title": "Song",
            "original_titles": [],
            "arrangers": ["Shibayan"],
            "vocalists": ["3L"],
            "lyricists": [],
        }],
        source_used="THBWiki",
    )


LOCAL_FILES = [{
    "path": "/nonexistent/01 Song.flac",
    "filename": "01 Song.flac",
    "disc": 1,
    "number": 1,
    "title": "Song",
}]


class ForceCreditsTests(unittest.TestCase):

    def run_tagging(self, *, force_credits, existing):
        """Tag one track with mocked tag I/O; return the writes attempted."""
        writes = []

        def fake_get(_path, tag_name):
            return existing.get(tag_name)

        def fake_set(_path, tag_name, value, dry_run=False):
            writes.append((tag_name, value))

        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(tmp, force_credits=force_credits)
            with patch.object(touhou_tagger, "scan_music_files",
                              return_value=LOCAL_FILES), \
                 patch.object(touhou_tagger, "_get_existing_tag",
                              side_effect=fake_get), \
                 patch.object(touhou_tagger, "_set_tag",
                              side_effect=fake_set):
                result = touhou_tagger.tag_album_from_plan(plan)
        return writes, result

    def test_existing_credits_are_preserved_by_default(self):
        writes, result = self.run_tagging(
            force_credits=False,
            existing={"arranger": "ShibayanRecords", "vocalist": "NJK Record"})
        self.assertEqual(writes, [])
        self.assertEqual(result["cred_skipped"], 2)

    def test_force_overwrites_a_wrong_credit(self):
        writes, result = self.run_tagging(
            force_credits=True,
            existing={"arranger": "ShibayanRecords", "vocalist": "NJK Record"})
        self.assertEqual(sorted(writes),
                         [("arranger", "Shibayan"), ("vocalist", "3L")])
        self.assertEqual(result["cred_wrote"], 2)

    def test_force_leaves_a_credit_the_wiki_agrees_with(self):
        # Forcing must not churn files or fill the log with no-op writes.
        writes, result = self.run_tagging(
            force_credits=True,
            existing={"arranger": "Shibayan", "vocalist": "3L"})
        self.assertEqual(writes, [])
        self.assertEqual(result["cred_skipped"], 2)

    def test_force_still_fills_an_empty_credit(self):
        writes, _result = self.run_tagging(force_credits=True, existing={})
        self.assertEqual(sorted(writes),
                         [("arranger", "Shibayan"), ("vocalist", "3L")])

    def test_a_role_the_wiki_does_not_credit_is_never_written(self):
        # The wiki has no lyricist for this track; forcing must not clear the
        # file's own value.
        writes, _result = self.run_tagging(
            force_credits=True, existing={"lyricist": "Someone"})
        self.assertNotIn("lyricist", [tag for tag, _ in writes])


class ForceCreditsPlumbingTests(unittest.TestCase):

    def test_default_is_off_everywhere(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = touhou_tagger.AlbumPlan(
                wiki_album="A", music_dir=tmp, dry_run=True, romanize=False,
                force_titlesort=False, force_credits=False,
                fetch_metadata=False, fetch_credits=False,
                use_touhoudb=False, touhoudb_add_missing=False,
            )
            self.assertFalse(plan.force_credits)

    def test_the_gui_toggle_and_the_write_policy_share_one_tag_set(self):
        # The GUI greys the toggle out using tag_selection.STAFF_TAGS while the
        # write loop skips unselected roles using the same set.  A second copy
        # would let the two drift apart.
        self.assertEqual(tag_selection.STAFF_TAGS,
                         frozenset({"arranger", "vocalist", "lyricist"}))
        self.assertIs(touhou_tagger._CREDIT_TAGS, tag_selection.STAFF_TAGS)
        self.assertTrue(tag_selection.STAFF_TAGS <= tag_selection.WIKI_TAG_SET)

    def test_process_album_forwards_the_flag_into_the_plan(self):
        captured = {}

        def fake_fetch(_album, _dir, **kwargs):
            captured.update(kwargs)
            return touhou_tagger.AlbumPlan(
                wiki_album="A", music_dir="d", dry_run=True, romanize=False,
                force_titlesort=False, force_credits=False,
                fetch_metadata=False, fetch_credits=False,
                use_touhoudb=False, touhoudb_add_missing=False,
                error="no music files found",
            )

        with patch.object(touhou_tagger, "fetch_album_plan",
                          side_effect=fake_fetch):
            touhou_tagger.process_album("A", "d", force_credits=True)
        self.assertTrue(captured["force_credits"])


if __name__ == "__main__":
    unittest.main()
