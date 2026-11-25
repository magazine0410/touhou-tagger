"""Per-song genres from TouhouDB, merged into the ``genre`` tag.

TouhouDB song tags in the ``Genres`` category come back in the same
album-tracks request as the per-track titles.  A track gets its own song
genres, or TouhouDB's album genres when the song has none, unioned with
THBWiki's album genres and the file's existing genres.
"""
import tempfile
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401

import touhou_tagger
import thwiki
import touhoudb


def _tag(name, category, count=1):
    return {"count": count, "tag": {"name": name, "categoryName": category}}


ALBUM_RESPONSE = {
    "id": 2628,
    "tags": [
        _tag("electro house", "Genres"),
        _tag("album stream available", "Distribution"),
        _tag("nu-disco", "Genres", count=2),
    ],
    "tracks": [
        {"discNumber": 1, "trackNumber": 1, "name": "One",
         "song": {"id": 11, "name": "One", "tags": [
             _tag("instrumental", "Composition"),
             _tag("electro", "Genres"),
         ]}},
        {"discNumber": 1, "trackNumber": 2, "name": "Two",
         "song": {"id": 12, "name": "Two", "tags": []}},
        {"discNumber": 1, "trackNumber": 3, "name": "Three", "song": None},
        {"discNumber": 2, "trackNumber": 1, "name": "Four",
         "song": {"id": 14, "name": "Four", "tags": [
             _tag("synthpop", "Genres"),
             _tag("electro", "Genres"),
         ]}},
    ],
}


class ClientGenreTests(unittest.TestCase):

    def test_one_request_yields_titles_song_genres_and_album_genres(self):
        client = touhoudb.TouhouDBClient()
        with patch.object(client, "_get",
                          return_value=ALBUM_RESPONSE) as get:
            titles = client.album_track_titles(2628)
            track_genres, album_genres = client.album_genres(2628)
        get.assert_called_once()
        path, params = get.call_args.args
        self.assertEqual(path, "/albums/2628")
        self.assertEqual(params["fields"], "Tracks,Tags")
        self.assertEqual(params["songFields"], "Tags")
        self.assertEqual(titles[(1, 3)], "Three")
        # Only Genres-category tags; songs without any are absent.
        self.assertEqual(track_genres, {
            (1, 1): ["electro"],
            (2, 1): ["synthpop", "electro"],
        })
        self.assertEqual(album_genres, ["electro house", "nu-disco"])

    def test_failed_request_gives_no_genres(self):
        client = touhoudb.TouhouDBClient()
        with patch.object(client, "_get", return_value=None):
            self.assertEqual(client.album_genres(1), ({}, []))


class FormatGenreNameTests(unittest.TestCase):

    def test_only_lowercase_words_are_capitalised(self):
        for raw, expected in (
            ("electro house", "Electro House"),
            ("post-rock", "Post-Rock"),
            ("drum and bass", "Drum and Bass"),
            ("nu-disco", "Nu-Disco"),
            ("EDM", "EDM"),
            ("IDM", "IDM"),
            ("J-POP", "J-POP"),
            ("Irish folk", "Irish Folk"),
            ("the 8-bit", "The 8-Bit"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(touhoudb.format_genre_name(raw), expected)

    def test_tagger_translates_then_formats_and_dedups(self):
        with patch.dict(thwiki.GENRE_TRANSLATIONS,
                        {"テスト": "Test Genre"}):
            out = touhou_tagger._format_tdb_genres(
                ["テスト", "electro", "electro"])
        self.assertEqual(out, ["Test Genre", "Electro"])

    def test_japanese_touhoudb_denpa_tag_is_translated(self):
        self.assertEqual(touhou_tagger._format_tdb_genres(["電波ソング"]),
                         ["Denpa"])


LOCAL_FILES = [
    {"path": "/nonexistent/01 One.flac", "filename": "01 One.flac",
     "disc": 1, "number": 1, "title": "One"},
    {"path": "/nonexistent/02 Two.flac", "filename": "02 Two.flac",
     "disc": 1, "number": 2, "title": "Two"},
]


def make_plan(tmp, *, wiki_genres, track_genres, album_genres):
    return touhou_tagger.AlbumPlan(
        wiki_album="Some_Album",
        music_dir=tmp,
        dry_run=False,
        romanize=False,
        force_titlesort=False,
        force_credits=False,
        fetch_metadata=True,
        fetch_credits=False,
        use_touhoudb=True,
        touhoudb_add_missing=False,
        selected_tags=("genre",),
        wiki_tracks=[
            {"number": 1, "disc": 1, "title": "One", "original_titles": [],
             "arrangers": [], "vocalists": [], "lyricists": []},
            {"number": 2, "disc": 1, "title": "Two", "original_titles": [],
             "arrangers": [], "vocalists": [], "lyricists": []},
        ],
        source_used="THBWiki",
        album_info={"genres": wiki_genres},
        tdb_track_genres=track_genres,
        tdb_album_genres=album_genres,
    )


class TagPhaseGenreTests(unittest.TestCase):

    def run_tagging(self, *, wiki_genres, track_genres, album_genres,
                    existing=None):
        existing = existing or {}
        writes = {}

        def fake_set(path, values, dry_run=False):
            writes[path] = list(values)

        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(tmp, wiki_genres=wiki_genres,
                             track_genres=track_genres,
                             album_genres=album_genres)
            with patch.object(touhou_tagger, "scan_music_files",
                              return_value=LOCAL_FILES), \
                 patch.object(touhou_tagger, "read_genres",
                              side_effect=lambda p: list(existing.get(p, []))), \
                 patch.object(touhou_tagger, "set_genres",
                              side_effect=fake_set):
                touhou_tagger.tag_album_from_plan(plan)
        return writes

    def test_song_genres_and_album_fallback(self):
        writes = self.run_tagging(
            wiki_genres=["Electronic"],
            track_genres={(1, 1): ["Electro", "Nu-Disco"]},
            album_genres=["Electro House"],
        )
        self.assertEqual(writes, {
            "/nonexistent/01 One.flac": ["Electronic", "Electro", "Nu-Disco"],
            "/nonexistent/02 Two.flac": ["Electronic", "Electro House"],
        })

    def test_touhoudb_genres_are_written_without_a_thbwiki_genre(self):
        writes = self.run_tagging(
            wiki_genres=[],
            track_genres={(1, 2): ["Synthpop"]},
            album_genres=[],
        )
        self.assertEqual(writes, {"/nonexistent/02 Two.flac": ["Synthpop"]})

    def test_existing_genres_are_kept_and_a_rerun_writes_nothing(self):
        writes = self.run_tagging(
            wiki_genres=["Electronic"],
            track_genres={(1, 1): ["electro"]},
            album_genres=[],
            existing={
                "/nonexistent/01 One.flac": ["Indie", "Electronic", "Electro"],
                "/nonexistent/02 Two.flac": ["Electronic"],
            },
        )
        self.assertEqual(writes, {})


class DiscFallbackTests(unittest.TestCase):

    def run_two_disc(self, tdb_titles):
        local = [
            {"path": "/nonexistent/d1/01.flac", "filename": "01.flac",
             "disc": 1, "number": 1, "title": "One"},
            {"path": "/nonexistent/d2/01.flac", "filename": "01.flac",
             "disc": 2, "number": 1, "title": "Four"},
        ]
        writes = {}
        with tempfile.TemporaryDirectory() as tmp:
            plan = make_plan(tmp, wiki_genres=[],
                             track_genres={(1, 1): ["Electro"]},
                             album_genres=["Electro House"])
            plan.wiki_tracks = [
                {"number": 1, "disc": 1, "title": "One",
                 "original_titles": [], "arrangers": [], "vocalists": [],
                 "lyricists": []},
                {"number": 1, "disc": 2, "title": "Four",
                 "original_titles": [], "arrangers": [], "vocalists": [],
                 "lyricists": []},
            ]
            plan.tdb_track_titles = tdb_titles
            with patch.object(touhou_tagger, "scan_music_files",
                              return_value=local), \
                 patch.object(touhou_tagger, "read_genres", return_value=[]), \
                 patch.object(touhou_tagger, "set_genres",
                              side_effect=lambda p, v, dry_run=False:
                              writes.__setitem__(p, list(v))):
                touhou_tagger.tag_album_from_plan(plan)
        return writes["/nonexistent/d2/01.flac"]

    def test_untagged_disc_2_song_gets_album_genres_not_disc_1_genres(self):
        # TouhouDB lists both discs; disc 2 track 1 simply has no genres.
        got = self.run_two_disc({(1, 1): "One", (2, 1): "Four"})
        self.assertEqual(got, ["Electro House"])

    def test_single_disc_tdb_entry_falls_back_to_disc_1(self):
        # TouhouDB numbers every track on disc 1.
        got = self.run_two_disc({(1, 1): "One"})
        self.assertEqual(got, ["Electro"])


class FetchPhaseGenreTests(unittest.TestCase):

    def test_plan_carries_formatted_song_and_album_genres(self):
        from bs4 import BeautifulSoup
        html = """
        <table class="wikitable musicTable">
          <tr><td class="infoA"><b>01</b></td>
              <td class="text">One</td><td class="infoB">03:00</td></tr>
          <tr><td class="infoA"><b>02</b></td>
              <td class="text">Two</td><td class="infoB">03:00</td></tr>
        </table>
        """
        soup = BeautifulSoup(html, "html.parser")
        with tempfile.TemporaryDirectory() as music_dir, \
             patch.object(touhou_tagger, "english_wiki_available",
                          return_value=False), \
             patch.object(touhou_tagger, "fetch_thwiki_tracks",
                          return_value=[]), \
             patch.object(touhou_tagger, "_fetch_thwiki_page_html",
                          return_value=soup), \
             patch.object(touhoudb.TouhouDBClient, "find_album",
                          return_value={"id": 2628, "name": "Album"}), \
             patch.object(touhoudb.TouhouDBClient, "_get",
                          return_value=ALBUM_RESPONSE):
            plan = touhou_tagger.fetch_album_plan(
                "Some_Album", music_dir, use_touhoudb=True,
                selected_tags=("genre",), fetch_credits=False,
            )
        self.assertIsNone(plan.error)
        self.assertTrue(plan.use_touhoudb)
        self.assertEqual(plan.tdb_track_genres, {
            (1, 1): ["Electro"],
            (2, 1): ["Synthpop", "Electro"],
        })
        self.assertEqual(plan.tdb_album_genres, ["Electro House", "Nu-Disco"])


class TouhouDBGenreGateTests(unittest.TestCase):

    def test_a_genre_only_selection_keeps_touhoudb_when_metadata_is_fetched(self):
        for fetch_metadata, expected in ((True, True), (False, False)):
            with self.subTest(fetch_metadata=fetch_metadata):
                plan = touhou_tagger.fetch_album_plan(
                    "Example_Album", "/no/such/directory",
                    use_touhoudb=True, selected_tags=("genre",),
                    fetch_metadata=fetch_metadata,
                )
                self.assertEqual(plan.error, "directory not found")
                self.assertEqual(plan.use_touhoudb, expected)


if __name__ == "__main__":
    unittest.main()
