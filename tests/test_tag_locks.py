import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests import _support  # noqa: F401

import availability
import config_backup
import japanese_romanizer
import tag_locks
import touhou_tagger


class _LockStoreCase(unittest.TestCase):
    """Runs each test against a throwaway tag_locks.json."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.config_dir = Path(self._tmp.name)
        self.locks_path = self.config_dir / "tag_locks.json"
        # _CONFIG_PATH is computed at import time, so patching config_path()
        # alone would leave the reads and writes pointed at the real file.
        patcher = patch.object(tag_locks, "_CONFIG_PATH", str(self.locks_path))
        patcher.start()
        self.addCleanup(patcher.stop)
        dir_patcher = patch.object(
            availability, "app_config_dir", return_value=str(self.config_dir)
        )
        dir_patcher.start()
        self.addCleanup(dir_patcher.stop)
        tag_locks.reload()
        self.addCleanup(tag_locks.reload)


class TagLockStoreTests(_LockStoreCase):
    def test_round_trip_through_disk(self):
        self.assertEqual(tag_locks.locked_tags("/music/a.flac"), frozenset())
        self.assertTrue(tag_locks.set_lock("/music/a.flac", "grouping", True))
        self.assertTrue(tag_locks.set_lock("/music/a.flac", "album", True))
        self.assertFalse(tag_locks.set_lock("/music/a.flac", "album", True))

        tag_locks.reload()
        self.assertEqual(
            tag_locks.locked_tags("/music/a.flac"),
            frozenset({"album", "grouping"}),
        )
        self.assertTrue(tag_locks.is_locked("/music/a.flac", "grouping"))
        self.assertFalse(tag_locks.is_locked("/music/a.flac", "title"))
        self.assertEqual(tag_locks.locked_files(), ["/music/a.flac"])

    def test_unlocking_the_last_tag_drops_the_entry(self):
        tag_locks.set_lock("/music/a.flac", "grouping", True)
        self.assertTrue(tag_locks.set_lock("/music/a.flac", "grouping", False))
        self.assertFalse(
            tag_locks.set_lock("/music/a.flac", "grouping", False))
        self.assertEqual(tag_locks.locked_files(), [])
        saved = json.loads(self.locks_path.read_text(encoding="utf-8"))
        self.assertEqual(saved, {"locks": {}})

    def test_bulk_set_locks_writes_once(self):
        pairs = [("/music/a.flac", "title"), ("/music/b.flac", "title")]
        with patch.object(tag_locks, "_save") as saver:
            self.assertTrue(tag_locks.set_locks(pairs, True))
            saver.assert_called_once()
        self.assertTrue(tag_locks.is_locked("/music/b.flac", "title"))

    def test_paths_normalise_to_one_key(self):
        tag_locks.set_lock("/music/album/a.flac", "grouping", True)
        for variant in (
            "/music/album/a.flac",
            "/music/album//a.flac",
            "/music/album/../album/a.flac",
        ):
            self.assertTrue(
                tag_locks.is_locked(variant, "grouping"), variant
            )

    def test_clear_file_removes_every_lock(self):
        tag_locks.set_locks(
            [("/music/a.flac", "album"), ("/music/a.flac", "title")], True
        )
        self.assertTrue(tag_locks.clear_file("/music/a.flac"))
        self.assertFalse(tag_locks.clear_file("/music/a.flac"))
        self.assertEqual(tag_locks.locked_tags("/music/a.flac"), frozenset())

    def test_corrupt_or_alien_json_degrades_to_empty(self):
        for payload in ("{ not json", '["a list"]', '{"locks": 5}'):
            self.locks_path.write_text(payload, encoding="utf-8")
            tag_locks.reload()
            self.assertEqual(tag_locks.locked_files(), [], payload)

    def test_unknown_tag_names_survive_a_round_trip(self):
        # Names are never validated against a vocabulary, so a tag added in a
        # later release is preserved rather than silently dropped.
        tag_locks.set_lock("/music/a.flac", "somefuturetag", True)
        tag_locks.reload()
        self.assertTrue(tag_locks.is_locked("/music/a.flac", "somefuturetag"))

    def test_blank_tag_names_are_ignored(self):
        self.assertFalse(tag_locks.set_lock("/music/a.flac", "   ", True))
        self.assertEqual(tag_locks.locked_files(), [])

    def test_locks_survive_a_config_backup_round_trip(self):
        tag_locks.set_locks(
            [("/music/a.flac", "grouping"), ("/music/a.flac", "album"),
             ("/music/b.flac", "title")],
            True,
        )
        backup = self.config_dir / "backup.json"
        config_backup.export_file(str(backup))

        tag_locks.set_lock("/music/a.flac", "grouping", False)
        tag_locks.set_lock("/music/c.flac", "year", True)

        config_backup.import_file(str(backup))
        tag_locks.reload()
        self.assertEqual(
            tag_locks.locked_tags("/music/a.flac"),
            frozenset({"album", "grouping"}),
        )
        # Import replaces the store wholesale, as documented.
        self.assertEqual(tag_locks.locked_tags("/music/c.flac"), frozenset())

    def test_prune_missing_keeps_entries_on_an_absent_parent(self):
        present = self.config_dir / "present.flac"
        present.write_text("", encoding="utf-8")
        gone = self.config_dir / "gone.flac"
        unmounted = "/mnt/not-mounted-here/album/track.flac"

        tag_locks.set_locks(
            [(str(present), "album"), (str(gone), "album"),
             (unmounted, "album")],
            True,
        )
        self.assertEqual(tag_locks.prune_missing(), 1)

        self.assertTrue(tag_locks.is_locked(str(present), "album"))
        self.assertFalse(tag_locks.is_locked(str(gone), "album"))
        # The unmounted drive's locks are the record of hand work; losing them
        # because a mount was absent would be unrecoverable.
        self.assertTrue(tag_locks.is_locked(unmounted, "album"))
        self.assertFalse(os.path.isdir(os.path.dirname(unmounted)))


TRACK = "/music/album/01 Song.flac"

LOCAL_FILES = [{
    "path": TRACK,
    "filename": "01 Song.flac",
    "disc": 1,
    "number": 1,
    "title": "Song",
}]


class LockedTagWritePolicyTests(_LockStoreCase):
    """A lock beats every wiki write policy, including the two that
    otherwise overwrite unconditionally."""

    def make_plan(self, tmp, **kwargs):
        opts = dict(
            wiki_album="Some_Album",
            music_dir=tmp,
            dry_run=False,
            romanize=False,
            force_titlesort=False,
            force_credits=False,
            fetch_metadata=True,
            fetch_credits=True,
            use_touhoudb=False,
            touhoudb_add_missing=False,
            selected_tags=("grouping", "album", "arranger", "vocalist",
                           "artist", "artistsort"),
            wiki_tracks=[{
                "number": 1, "disc": 1, "title": "Song",
                "original_titles": ["Bad Apple!!"],
                "arrangers": ["Shibayan"],
                "vocalists": ["3L"],
                "lyricists": [],
                "arrangers_jp": ["シバヤン"],
                "vocalists_jp": ["3L"],
            }],
            album_info={"album": "Correct Album Title"},
            source_used="THBWiki",
        )
        opts.update(kwargs)
        return touhou_tagger.AlbumPlan(**opts)

    def run_tagging(self, *, existing=None, **plan_kwargs):
        """Tag one track with mocked tag I/O; return every write attempted."""
        existing = existing or {}
        writes = []
        groupings = []

        with tempfile.TemporaryDirectory() as tmp:
            plan = self.make_plan(tmp, **plan_kwargs)
            with patch.object(touhou_tagger, "scan_music_files",
                              return_value=LOCAL_FILES), \
                 patch.object(touhou_tagger, "_get_existing_tag",
                              side_effect=lambda _p, t: existing.get(t)), \
                 patch.object(touhou_tagger, "_set_tag",
                              side_effect=lambda _p, t, v, dry_run=False:
                              writes.append((t, v))), \
                 patch.object(touhou_tagger, "read_grouping",
                              side_effect=lambda _p:
                              existing.get("grouping")), \
                 patch.object(touhou_tagger, "set_grouping",
                              side_effect=lambda _p, v, dry_run=False:
                              groupings.append(("set", v))), \
                 patch.object(touhou_tagger, "clear_grouping",
                              side_effect=lambda _p, dry_run=False:
                              groupings.append(("clear", None))):
                result = touhou_tagger.tag_album_from_plan(plan)
        return writes, groupings, result

    def test_a_locked_album_survives_the_always_overwrite_policy(self):
        # `album` normally overwrites on mismatch — the wiki is authoritative.
        writes, _g, result = self.run_tagging(
            existing={"album": "My Preferred Title"})
        self.assertIn(("album", "Correct Album Title"), writes)

        tag_locks.set_lock(TRACK, "album", True)
        writes, _g, result = self.run_tagging(
            existing={"album": "My Preferred Title"})
        self.assertNotIn("album", [tag for tag, _ in writes])
        self.assertEqual(result["locked_skipped"], 1)

    def test_a_locked_credit_survives_force_credits(self):
        writes, _g, _r = self.run_tagging(
            force_credits=True,
            existing={"arranger": "Hand Written", "vocalist": "Hand Written"})
        self.assertEqual(sorted(t for t, _ in writes if t in
                                ("arranger", "vocalist")),
                         ["arranger", "vocalist"])

        tag_locks.set_lock(TRACK, "arranger", True)
        writes, _g, result = self.run_tagging(
            force_credits=True,
            existing={"arranger": "Hand Written", "vocalist": "Hand Written"})
        self.assertNotIn("arranger", [tag for tag, _ in writes])
        self.assertIn(("vocalist", "3L"), writes)
        self.assertEqual(result["locked_skipped"], 1)

    def test_a_locked_grouping_is_neither_set_nor_cleared(self):
        # grouping goes through set_grouping/clear_grouping, not _set_tag, and
        # is written unconditionally — so it needs its own coverage.
        _w, groupings, _r = self.run_tagging()
        self.assertEqual(groupings, [("set", "Bad Apple!!")])

        tag_locks.set_lock(TRACK, "grouping", True)
        _w, groupings, _r = self.run_tagging(existing={"grouping": "Mine"})
        self.assertEqual(groupings, [])

        # ...and an original composition must not clear a locked grouping.
        plan_tracks = [{
            "number": 1, "disc": 1, "title": "Song", "original_titles": [],
            "arrangers": [], "vocalists": [], "lyricists": [],
        }]
        _w, groupings, _r = self.run_tagging(
            wiki_tracks=plan_tracks, existing={"grouping": "Mine"})
        self.assertEqual(groupings, [])

    def test_locked_artist_tags_skip_the_rate_limited_touhoudb_lookup(self):
        # The artist block is gated on the same tag set, so locking both tags
        # avoids a per-track TouhouDB request, not just a write.
        client = MagicMock()
        client.track_extra_artists.return_value = []
        client.romanize.return_value = None
        kwargs = dict(use_touhoudb=True, touhoudb_add_missing=True,
                      tdb_client=client, tdb_album_id=42)

        self.run_tagging(**kwargs)
        self.assertEqual(client.track_extra_artists.call_count, 1)

        client.track_extra_artists.reset_mock()
        tag_locks.set_locks(
            [(TRACK, "artist"), (TRACK, "artistsort")], True)
        _w, _g, result = self.run_tagging(**kwargs)
        client.track_extra_artists.assert_not_called()
        self.assertEqual(result["locked_skipped"], 2)

    def test_locked_tags_appear_in_tag_changes_with_wiki_values(self):
        """Locked tags that *differ* from the wiki value are reported in
        tag_changes with ``"locked": True`` so the summary shows them."""
        tag_locks.set_lock(TRACK, "grouping", True)
        tag_locks.set_lock(TRACK, "album", True)
        _w, _g, result = self.run_tagging(
            existing={"grouping": "Old Theme", "album": "Old Title"})
        locked_changes = [
            ch for ch in result["tag_changes"] if ch.get("locked")
        ]
        tags_reported = {ch["tag"] for ch in locked_changes}
        self.assertIn("grouping", tags_reported)
        self.assertIn("album", tags_reported)
        # The "new" value is what the wiki would have written.
        for ch in locked_changes:
            if ch["tag"] == "grouping":
                self.assertEqual(ch["new"], "Bad Apple!!")
                self.assertEqual(ch["old"], "Old Theme")
            elif ch["tag"] == "album":
                self.assertEqual(ch["new"], "Correct Album Title")
                self.assertEqual(ch["old"], "Old Title")

    def test_locked_tag_not_reported_when_wiki_agrees(self):
        """A lock whose on-disk value already matches the wiki produces
        no locked change entry — it is a no-op, not interesting."""
        tag_locks.set_lock(TRACK, "album", True)
        _w, _g, result = self.run_tagging(
            existing={"album": "Correct Album Title"})
        locked_changes = [
            ch for ch in result["tag_changes"] if ch.get("locked")
        ]
        album_locked = [ch for ch in locked_changes if ch["tag"] == "album"]
        self.assertEqual(album_locked, [])

    def test_an_unlocked_run_is_unchanged(self):
        writes, groupings, result = self.run_tagging()
        self.assertEqual(result["locked_skipped"], 0)
        self.assertEqual(groupings, [("set", "Bad Apple!!")])
        self.assertIn(("album", "Correct Album Title"), writes)

    def test_locked_comparison_respects_other_skip_policies(self):
        tags = ("date", "year", "catalognumber", "arranger", "albumartistsort")
        tag_locks.set_locks([(TRACK, tag) for tag in tags], True)
        _w, _g, result = self.run_tagging(
            selected_tags=tags,
            existing=dict(date="2000", year="2000", catalognumber="OLD",
                          arranger="Manual", albumartistsort="Manual Circle"),
            album_info=dict(date="2020-01-01", catalog_numbers=["NEW"],
                            album_artists=["Other Circle"]),
        )
        self.assertEqual(result["tag_changes"], [])
        self.assertEqual(result["locked_skipped"], len(tags))

    def test_locked_credit_preview_requires_force_for_existing_credit(self):
        tag_locks.set_lock(TRACK, "arranger", True)
        writes, _g, result = self.run_tagging(
            selected_tags=("arranger",), force_credits=True,
            existing={"arranger": "Manual"})
        self.assertEqual(writes, [])
        self.assertEqual(result["tag_changes"], [dict(
            filename=LOCAL_FILES[0]["filename"], path=TRACK, tag="arranger",
            old="Manual", new="Shibayan", locked=True)])

    def test_locked_grouping_clear_is_reported_but_not_written(self):
        tag_locks.set_lock(TRACK, "grouping", True)
        tracks = [dict(number=1, disc=1, title="Song", original_titles=[])]
        _w, groupings, result = self.run_tagging(
            selected_tags=("grouping",), wiki_tracks=tracks,
            existing={"grouping": "Manual"})
        self.assertEqual(groupings, [])
        self.assertEqual(result["tag_changes"][0]["new"], None)
        self.assertTrue(result["tag_changes"][0]["locked"])
        _w, _g, empty_result = self.run_tagging(
            selected_tags=("grouping",), wiki_tracks=tracks)
        self.assertEqual(empty_result["tag_changes"], [])

    def test_locked_album_sort_preview_uses_prewrite_display_value(self):
        tag_locks.set_lock(TRACK, "albumartistsort", True)
        _w, _g, result = self.run_tagging(
            selected_tags=("albumartist", "albumartistsort"),
            existing={"albumartist": "Existing Latin"},
            album_info={"album_artists": ["森羅万象"]})
        change = next(ch for ch in result["tag_changes"] if ch.get("locked"))
        self.assertEqual(change["new"], "Existing Latin")

    def test_locked_titlesort_preview_is_always_dry_run(self):
        tag_locks.set_lock(TRACK, "titlesort", True)
        with patch.object(touhou_tagger, "ROMANIZER_AVAILABLE", True), \
             patch.object(touhou_tagger.japanese_romanizer, "romanize_file",
                          return_value=dict(status="overwritten",
                                            titlesort_old="Old", titlesort_new="New")) as rm:
            writes, _g, result = self.run_tagging(
                selected_tags=("titlesort",), romanize=True,
                force_titlesort=True, existing={"titlesort": "Old"})
        self.assertEqual(writes, [])
        self.assertTrue(rm.call_args.kwargs["dry_run"])
        self.assertTrue(result["tag_changes"][0]["locked"])
        self.assertEqual(result["tag_changes"][0]["new"], "New")
        self.assertEqual(result["overwritten"], 0)

    def test_empty_locked_artist_preview_uses_available_credits(self):
        tag_locks.set_locks([(TRACK, "artist"), (TRACK, "artistsort")], True)
        writes, _g, result = self.run_tagging(
            selected_tags=("artist", "artistsort"), use_touhoudb=True,
            staff_name_map={"シバヤン": "Shibayan"})
        self.assertEqual(writes, [])
        self.assertEqual({ch["tag"]: ch["new"] for ch in result["tag_changes"]},
                         {"artist": "シバヤン; 3L", "artistsort": "Shibayan; 3L"})
        self.assertTrue(all(ch["locked"] for ch in result["tag_changes"]))


class RomaniserLockPredicateTests(unittest.TestCase):
    """The romaniser takes locks by injection so its CLI stays lock-free."""

    FILES = [{"path": TRACK, "filename": "01 Song.flac",
              "disc": 1, "number": 1}]

    def test_a_locked_file_is_never_romanised_and_counts_as_skipped(self):
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
             patch.object(japanese_romanizer, "romanize_file") as rf:
            summary = japanese_romanizer.romanize_files(
                self.FILES, log=lambda _m: None,
                is_locked=lambda _p: True,
            )
        rf.assert_not_called()
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["romanized"], 0)

    def test_the_default_is_no_predicate_at_all(self):
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
             patch.object(japanese_romanizer, "romanize_file",
                          return_value={"status": "skip_no_japanese",
                                        "title": "Song"}) as rf:
            summary = japanese_romanizer.romanize_files(
                self.FILES, log=lambda _m: None)
        rf.assert_called_once()
        self.assertEqual(summary["skipped"], 1)


if __name__ == "__main__":
    unittest.main()
