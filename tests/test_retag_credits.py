"""Offline tests for the credit-repair migration CLI.

The decision logic is pure, so it is tested directly: a credit is repaired
only when it is exactly what the faulty circle mapping would have produced.
"""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import _support  # noqa: F401  (puts source/ on sys.path)

import retag_credits  # noqa: E402
import thwiki  # noqa: E402
from thwiki import ThwikiCookieError  # noqa: E402


def record(path, key, **credits):
    """One track record in the shape collect_current_credits() returns."""
    return {
        "path": path,
        "key": key,
        "credits": {tag: credits.get(tag, "")
                    for tag, _role in retag_credits.CREDIT_ROLES},
    }


class PlanAlbumFixesTests(unittest.TestCase):
    """The repair rule: wiki disagreement AND an exact bug signature."""

    WIKI = {(1, 1): {"arrange": ["Shibayan"], "vocal": ["3L"],
                     "lyric": ["やまざきさやか"]}}
    CIRCLES = {"Shibayan": "ShibayanRecords", "3L": "NJK Record"}

    def plan(self, rec, wiki=None, circles=None):
        return retag_credits.plan_album_fixes(
            [rec],
            self.WIKI if wiki is None else wiki,
            self.CIRCLES if circles is None else circles,
        )

    def test_circle_value_is_repaired(self):
        fixes, counts = self.plan(record(
            "a.flac", (1, 1), arranger="ShibayanRecords", vocalist="NJK Record"))
        self.assertEqual(counts["repaired"], 2)
        self.assertEqual(
            {(f["tag"], f["old"], f["new"]) for f in fixes},
            {("arranger", "ShibayanRecords", "Shibayan"),
             ("vocalist", "NJK Record", "3L")})

    def test_correct_value_is_left_alone(self):
        fixes, counts = self.plan(record(
            "a.flac", (1, 1), arranger="Shibayan", lyricist="やまざきさやか"))
        self.assertEqual(fixes, [])
        self.assertEqual(counts["already correct"], 2)

    def test_unrelated_value_is_left_alone(self):
        # A hand-edited or rip-supplied credit matches neither the wiki nor
        # the bug's output, so the tool must not touch it.
        fixes, counts = self.plan(record(
            "a.flac", (1, 1), arranger="Someone Else"))
        self.assertEqual(fixes, [])
        self.assertEqual(counts["differs (left alone)"], 1)

    def test_empty_credit_is_never_filled(self):
        fixes, counts = self.plan(record("a.flac", (1, 1)))
        self.assertEqual(fixes, [])
        self.assertEqual(counts["empty (left alone)"], 3)

    def test_circle_that_the_wiki_itself_credits_is_kept(self):
        # THBWiki credits some circles as the real arranger (e.g. NJK Record
        # on Crimson Glory Remixies +).  There the bug's output equals the
        # correct value, so the guard must not fire.
        wiki = {(1, 1): {"arrange": ["NJK Record"], "vocal": [], "lyric": []}}
        fixes, counts = self.plan(
            record("a.flac", (1, 1), arranger="NJK Record"), wiki=wiki)
        self.assertEqual(fixes, [])
        self.assertEqual(counts["already correct"], 1)

    def test_partially_mapped_multi_name_credit_is_repaired(self):
        wiki = {(1, 1): {"arrange": ["Shibayan", "kachi"],
                         "vocal": [], "lyric": []}}
        fixes, _counts = self.plan(
            record("a.flac", (1, 1), arranger="ShibayanRecords; kachi"),
            wiki=wiki)
        self.assertEqual([f["new"] for f in fixes], ["Shibayan; kachi"])

    def test_track_absent_from_the_page_is_skipped(self):
        _fixes, counts = self.plan(
            record("a.flac", (2, 9), arranger="ShibayanRecords"))
        self.assertEqual(counts["track not on page"], 1)


class AlbumDiscoveryTests(unittest.TestCase):

    def test_disc_subdirectories_fold_into_their_album(self):
        with tempfile.TemporaryDirectory() as root:
            album = Path(root) / "Some Album"
            (album / "Disc 1").mkdir(parents=True)
            (album / "Disc 2").mkdir()
            (album / "Disc 1" / "a.flac").touch()
            (album / "Disc 2" / "b.flac").touch()
            self.assertEqual(retag_credits.find_album_dirs([root]),
                             [str(album)])

    def test_directory_without_audio_is_not_an_album(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "scans").mkdir()
            (Path(root) / "scans" / "cover.jpg").touch()
            self.assertEqual(retag_credits.find_album_dirs([root]), [])


class ResumeTests(unittest.TestCase):
    """An expired THBWiki session must stop the batch, not lose the work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = os.path.join(self.tmp.name, "state.json")
        for name in ("Album A", "Album B"):
            d = Path(self.tmp.name) / name
            d.mkdir()
            (d / "track.flac").touch()

    def run_batch(self, side_effect, no_wait=False):
        with patch.object(retag_credits, "process_album",
                          side_effect=side_effect), \
             patch.object(retag_credits, "reviewed_slugs", return_value={}):
            return retag_credits.run(
                [self.tmp.name], apply=False, limit=None, delay=0,
                reviewed_only=False, state_file=self.state, verbose=False,
                no_wait=no_wait)

    def test_cookie_error_stops_the_batch_and_checkpoints_the_rest(self):
        calls = []

        def side_effect(album_dir, **kwargs):
            calls.append(album_dir)
            if len(calls) == 1:
                return {"result": "checked", "repaired": 0}
            raise ThwikiCookieError("cookie expired")

        summary = self.run_batch(side_effect)
        self.assertEqual(len(calls), 2)
        self.assertIn("cookie expired", summary["stopped"])

        with open(self.state, encoding="utf-8") as f:
            done = json.load(f)["done"]
        self.assertEqual(len(done), 1)          # only the finished album
        self.assertNotIn(calls[1], done)        # the album that raised

        # Re-running picks up exactly where it stopped: the finished album is
        # not re-fetched, the one that raised is retried.
        retried = []

        def retry(album_dir, **kwargs):
            retried.append(album_dir)
            return {"result": "checked", "repaired": 0}

        self.run_batch(retry)
        self.assertEqual(retried, [calls[1]])

    def test_dry_run_checkpoint_does_not_block_a_later_apply(self):
        seen = []

        def side_effect(album_dir, **kwargs):
            seen.append(album_dir)
            return {"result": "checked", "repaired": 0}

        def batch(apply):
            with patch.object(retag_credits, "process_album",
                              side_effect=side_effect), \
                 patch.object(retag_credits, "reviewed_slugs",
                              return_value={}):
                return retag_credits.run(
                    [self.tmp.name], apply=apply, limit=None, delay=0,
                    reviewed_only=False, state_file=self.state, verbose=False)

        batch(apply=False)                  # dry run over both albums
        self.assertEqual(len(seen), 2)
        seen.clear()

        batch(apply=False)                  # a second dry run resumes
        self.assertEqual(seen, [])
        seen.clear()

        batch(apply=True)                   # --apply must still do the work
        self.assertEqual(len(seen), 2)
        seen.clear()

        batch(apply=True)                   # and only then is it done
        self.assertEqual(seen, [])

    def test_no_wait_stops_on_an_expired_session(self):
        calls = []

        def side_effect(album_dir, **kwargs):
            calls.append(album_dir)
            raise ThwikiCookieError("cookie expired")

        with patch.object(retag_credits, "can_wait", return_value=False), \
             patch.object(retag_credits, "wait_for_new_cookie") as prompt:
            summary = self.run_batch(side_effect, no_wait=True)
        prompt.assert_not_called()
        self.assertEqual(len(calls), 1)         # stopped on the first album
        self.assertIn("cookie expired", summary["stopped"])

    def test_waiting_retries_the_same_album_and_carries_on(self):
        calls = []

        def side_effect(album_dir, **kwargs):
            calls.append(album_dir)
            # The first album fails once, then succeeds on the retry.
            if len(calls) == 1:
                raise ThwikiCookieError("cookie expired")
            return {"result": "checked", "repaired": 0}

        with patch.object(retag_credits, "can_wait", return_value=True), \
             patch.object(retag_credits, "wait_for_new_cookie",
                          return_value=True) as prompt:
            summary = self.run_batch(side_effect)

        prompt.assert_called_once()
        # album A (fails), album A again (succeeds), album B.
        self.assertEqual(calls, [calls[0], calls[0], calls[2]])
        self.assertIsNone(summary["stopped"])
        self.assertEqual(summary["totals"]["checked"], 2)

    def test_declining_the_prompt_stops_without_consuming_the_album(self):
        calls = []

        def side_effect(album_dir, **kwargs):
            calls.append(album_dir)
            raise ThwikiCookieError("cookie expired")

        with patch.object(retag_credits, "can_wait", return_value=True), \
             patch.object(retag_credits, "wait_for_new_cookie",
                          return_value=False):
            summary = self.run_batch(side_effect)

        self.assertEqual(summary["stopped"], "stopped at the session prompt")
        # Nothing completed, so the album is still pending on the next run.
        # (The checkpoint file may not even exist yet — load_state copes.)
        self.assertEqual(retag_credits.load_state(self.state)["done"], {})

    def test_repeated_expiries_on_one_album_give_up(self):
        calls = []

        def side_effect(album_dir, **kwargs):
            calls.append(album_dir)
            raise ThwikiCookieError("cookie expired")

        with patch.object(retag_credits, "can_wait", return_value=True), \
             patch.object(retag_credits, "wait_for_new_cookie",
                          return_value=True):
            summary = self.run_batch(side_effect)

        # Bounded, so an always-failing session cannot loop forever.
        self.assertEqual(len(calls), retag_credits._MAX_CONSECUTIVE_EXPIRIES)
        self.assertIn("times in a row", summary["stopped"])

    def test_a_pipe_never_waits(self):
        # Without a terminal the prompt would block forever.
        with patch.object(retag_credits.sys, "stdin", io.StringIO()):
            self.assertFalse(retag_credits.can_wait(False))

    def test_one_album_error_does_not_stop_the_batch(self):
        def side_effect(album_dir, **kwargs):
            if album_dir.endswith("Album A"):
                raise ValueError("bad page")
            return {"result": "checked", "repaired": 0}

        summary = self.run_batch(side_effect)
        self.assertIsNone(summary["stopped"])
        self.assertEqual(summary["totals"]["error: ValueError"], 1)


class StaffCircleParserTests(unittest.TestCase):

    def test_circles_come_from_the_second_column(self):
        from bs4 import BeautifulSoup
        html = """
        <div class="stafflist-wrapper"><table class="stafflist">
          <tr><td>隣人</td><td>ZYTOKINE</td><td>Tr.2</td></tr>
          <tr><td>kachi</td><td></td><td>Tr.1</td></tr>
        </table></div>
        """
        circles = thwiki.parse_thwiki_staff_circles(
            BeautifulSoup(html, "html.parser"))
        self.assertEqual(circles, {"隣人": "ZYTOKINE"})


class FakeRomanizer:
    """Stand-in for TouhouDBClient.romanize with no network."""

    def __init__(self, table):
        self.table = table
        self.queries = []

    def romanize(self, name):
        self.queries.append(name)
        return self.table.get(name)


class RomanizeTests(unittest.TestCase):
    """--romanize is a second, separately-counted operation."""

    WIKI = {(1, 1): {"arrange": ["すみじゅん"], "vocal": ["水瀬ましろ"],
                     "lyric": ["アサヒ"]}}
    CIRCLES = {"すみじゅん": "Halozy", "水瀬ましろ": "Amorevole"}
    TABLE = {"水瀬ましろ": "Minase Mashiro", "アサヒ": "Asahi"}

    def plan(self, rec, client):
        return retag_credits.plan_album_fixes(
            [rec], self.WIKI, self.CIRCLES, tdb_client=client)

    def test_japanese_credit_is_romanized_and_counted_apart(self):
        client = FakeRomanizer(self.TABLE)
        fixes, counts = self.plan(
            record("a.flac", (1, 1), vocalist="水瀬ましろ"), client)
        self.assertEqual(counts["romanized"], 1)
        self.assertEqual(counts["repaired"], 0)
        self.assertEqual(fixes[0]["new"], "Minase Mashiro")
        self.assertEqual(fixes[0]["kind"], "romanized")

    def test_damaged_credit_is_repaired_straight_to_the_romanized_form(self):
        client = FakeRomanizer(self.TABLE)
        fixes, counts = self.plan(
            record("a.flac", (1, 1), vocalist="Amorevole"), client)
        self.assertEqual(counts["repaired"], 1)
        self.assertEqual(counts["romanized"], 0)
        self.assertEqual(fixes[0]["new"], "Minase Mashiro")

    def test_name_without_a_touhoudb_entry_keeps_its_japanese_form(self):
        client = FakeRomanizer(self.TABLE)
        fixes, counts = self.plan(
            record("a.flac", (1, 1), arranger="Halozy"), client)
        # Repaired (it was the circle), but すみじゅん has no romanization.
        self.assertEqual(counts["repaired"], 1)
        self.assertEqual(fixes[0]["new"], "すみじゅん")

    def test_already_romanized_credit_is_left_alone(self):
        client = FakeRomanizer(self.TABLE)
        fixes, counts = self.plan(
            record("a.flac", (1, 1), lyricist="Asahi"), client)
        self.assertEqual(fixes, [])
        self.assertEqual(counts["already correct"], 1)

    def test_without_a_client_japanese_credits_are_untouched(self):
        fixes, counts = retag_credits.plan_album_fixes(
            [record("a.flac", (1, 1), vocalist="水瀬ましろ")],
            self.WIKI, self.CIRCLES, tdb_client=None)
        self.assertEqual(fixes, [])
        self.assertEqual(counts["already correct"], 1)

    def test_latin_names_are_never_queried(self):
        client = FakeRomanizer(self.TABLE)
        retag_credits.romanize_names(["3L", "Nhato"], client)
        self.assertEqual(client.queries, [])


class NameCacheTests(unittest.TestCase):
    """The romanization cache must survive a resume without going bad."""

    def test_roundtrip_including_negative_entries(self):
        from touhoudb import TouhouDBClient
        client = TouhouDBClient()
        loaded = client.load_name_cache(
            {"アサヒ": "Asahi", "すみじゅん": None})
        self.assertEqual(loaded, 2)
        # Cached values are returned without a request.
        self.assertEqual(client.romanize("アサヒ"), "Asahi")
        self.assertIsNone(client.romanize("すみじゅん"))
        self.assertEqual(client.export_name_cache()["アサヒ"], "Asahi")

    def test_corrupt_entries_are_rejected(self):
        from touhoudb import TouhouDBClient
        client = TouhouDBClient()
        # A CJK "romanization" and a non-string key are not usable.
        loaded = client.load_name_cache({"アサヒ": "朝日", 3: "x", "": "y"})
        self.assertEqual(loaded, 0)
        self.assertEqual(client.export_name_cache(), {})


if __name__ == "__main__":
    unittest.main()
