import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import _support  # noqa: F401

import availability
import config_backup
import preferences
import tag_selection
import touhou_tagger


class TagSelectionTests(unittest.TestCase):
    def test_normalization_and_log_format_are_stable(self):
        self.assertEqual(
            tag_selection.normalize_selected_tags(["year", "grouping", "year"]),
            ("grouping", "year"),
        )
        self.assertEqual(tag_selection.normalize_selected_tags({"unknown"}), ())
        self.assertEqual(tag_selection.normalize_selected_tags({"grouping": True}), ())
        self.assertEqual(
            tag_selection.format_tag_selection(["titlesort", "grouping"]),
            "Tag selection: grouping, titlesort",
        )

    def test_fetch_requirements_follow_selected_outputs(self):
        self.assertEqual(
            touhou_tagger._tag_selection_fetch_options(
                ("grouping",), fetch_metadata=True, fetch_credits=True,
                use_touhoudb=False,
            ),
            {
                "fetch_metadata": False,
                "fetch_credits": False,
                "fetch_staff_names": False,
            },
        )
        self.assertEqual(
            touhou_tagger._tag_selection_fetch_options(
                ("albumartistsort",), fetch_metadata=True, fetch_credits=True,
                use_touhoudb=False,
            ),
            {
                "fetch_metadata": True,
                "fetch_credits": False,
                "fetch_staff_names": True,
            },
        )
        self.assertEqual(
            touhou_tagger._tag_selection_fetch_options(
                ("artistsort",), fetch_metadata=True, fetch_credits=True,
                use_touhoudb=True,
            ),
            {
                "fetch_metadata": False,
                "fetch_credits": True,
                "fetch_staff_names": True,
            },
        )

    def test_preferences_default_validate_and_backup_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            prefs_path = config_dir / "preferences.json"
            with patch.object(availability, "app_config_dir", return_value=tmp), patch.object(
                preferences, "config_path", return_value=str(prefs_path)
            ):
                self.assertEqual(preferences.wiki_tag_selection(), tag_selection.WIKI_TAGS)
                self.assertTrue(preferences.save({
                    "wiki_tag_selection": ["titlesort", "grouping", "unknown"],
                }))
                self.assertEqual(
                    preferences.wiki_tag_selection(), ("grouping", "titlesort")
                )

                payload = config_backup.build_payload()
                self.assertEqual(
                    payload["preferences"]["wiki_tag_selection"],
                    ["grouping", "titlesort"],
                )
                backup = config_dir / "backup.json"
                config_backup.export_file(str(backup))
                self.assertTrue(preferences.save({
                    "wiki_tag_selection": ["year"],
                }))
                config_backup.import_file(str(backup))
                self.assertEqual(
                    preferences.wiki_tag_selection(), ("grouping", "titlesort")
                )

                prefs_path.write_text(
                    json.dumps({"wiki_tag_selection": []}), encoding="utf-8"
                )
                self.assertEqual(preferences.wiki_tag_selection(), tag_selection.WIKI_TAGS)

    @staticmethod
    def _plan(*, selected_tags, wiki_track, album_info=None, fetch_metadata=False):
        return touhou_tagger.AlbumPlan(
            wiki_album="Example_Album",
            music_dir="/music/example",
            dry_run=False,
            romanize=False,
            force_titlesort=False,
            force_credits=False,
            fetch_metadata=fetch_metadata,
            fetch_credits=False,
            use_touhoudb=False,
            touhoudb_add_missing=False,
            selected_tags=selected_tags,
            wiki_tracks=[wiki_track],
            source_used="THBWiki",
            album_info=album_info or {},
        )

    @staticmethod
    def _local_file():
        return {
            "filename": "01 - Song.flac",
            "path": "/music/example/01 - Song.flac",
            "disc": 1,
            "number": 1,
            "title": "Song",
        }

    @staticmethod
    def _wiki_track(original_titles):
        return {
            "disc": 1,
            "number": 1,
            "title": "Song",
            "original_titles": original_titles,
            "arrangers": ["Arranger"],
            "vocalists": [],
            "lyricists": [],
        }

    def test_grouping_only_does_not_write_other_tag_groups(self):
        plan = self._plan(
            selected_tags=("grouping",),
            wiki_track=self._wiki_track(["Theme"]),
        )
        with patch.object(touhou_tagger, "scan_music_files", return_value=[self._local_file()]), patch.object(
            touhou_tagger, "read_grouping", return_value=None
        ), patch.object(touhou_tagger, "set_grouping") as set_grouping, patch.object(
            touhou_tagger, "_set_tag"
        ) as set_tag, patch.object(touhou_tagger, "set_genres") as set_genres:
            touhou_tagger.tag_album_from_plan(plan)

        set_grouping.assert_called_once_with(
            "/music/example/01 - Song.flac", "Theme", dry_run=False
        )
        set_tag.assert_not_called()
        set_genres.assert_not_called()

    def test_deselected_grouping_never_reads_or_clears_it(self):
        plan = self._plan(
            selected_tags=("album",),
            wiki_track=self._wiki_track([]),
            album_info={"album": "Fetched Album"},
            fetch_metadata=True,
        )
        with patch.object(touhou_tagger, "scan_music_files", return_value=[self._local_file()]), patch.object(
            touhou_tagger, "read_grouping"
        ) as read_grouping, patch.object(
            touhou_tagger, "clear_grouping"
        ) as clear_grouping, patch.object(touhou_tagger, "_set_tag") as set_tag:
            touhou_tagger.tag_album_from_plan(plan)

        read_grouping.assert_not_called()
        clear_grouping.assert_not_called()
        set_tag.assert_called_once_with(
            "/music/example/01 - Song.flac", "album", "Fetched Album",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
