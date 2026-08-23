import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

import tag_io  # noqa: E402
import thwiki  # noqa: E402
import touhou_tagger  # noqa: E402


TRACKLIST_HTML = """
<table class="wikitable musicTable">
  <tr>
    <td class="infoA"><b>01</b></td>
    <td class="text">First Song</td>
    <td class="infoB">03:35</td>
  </tr>
  <tr>
    <td class="label">Arrange</td>
    <td class="text"><a>AIKA</a></td>
  </tr>
  <tr>
    <td class="label">Original Title</td>
    <td class="text"><div class="ogmusic"><a>おてんば恋娘</a></div></td>
  </tr>
  <tr>
    <td class="infoA"><b>02</b></td>
    <td class="text">Second Song</td>
    <td class="infoB">02:00</td>
  </tr>
  <tr>
    <td class="label">Original Title</td>
    <td class="text"><div class="ogmusic">Bad Apple!!</div></td>
  </tr>
</table>
"""


class ThwikiHtmlFallbackTests(unittest.TestCase):
    def test_rendered_tracklist_builds_complete_records(self):
        soup = BeautifulSoup(TRACKLIST_HTML, "html.parser")

        tracks = thwiki._parse_thwiki_html_tracklist(soup)

        self.assertEqual(
            tracks,
            [
                {
                    "number": 1,
                    "disc": 1,
                    "title": "First Song",
                    "original_titles": ["おてんば恋娘"],
                    "arrangers": ["AIKA"],
                    "vocalists": [],
                    "lyricists": [],
                },
                {
                    "number": 2,
                    "disc": 1,
                    "title": "Second Song",
                    "original_titles": ["Bad Apple!!"],
                    "arrangers": [],
                    "vocalists": [],
                    "lyricists": [],
                },
            ],
        )

    def test_fetch_plan_uses_html_when_asktrack_is_empty(self):
        soup = BeautifulSoup(TRACKLIST_HTML, "html.parser")
        with tempfile.TemporaryDirectory() as music_dir:
            with patch.object(
                touhou_tagger, "english_wiki_available", return_value=False
            ), patch.object(
                touhou_tagger, "fetch_thwiki_tracks", return_value=[]
            ), patch.object(
                touhou_tagger, "_fetch_thwiki_page_html", return_value=soup
            ):
                plan = touhou_tagger.fetch_album_plan(
                    "Unindexed_Album",
                    music_dir,
                    fetch_metadata=False,
                    fetch_credits=False,
                )

        self.assertIsNone(plan.error)
        self.assertEqual(plan.source_used, "THBWiki")
        self.assertEqual([t["title"] for t in plan.wiki_tracks], [
            "First Song", "Second Song",
        ])


# A Staff section as THBWiki actually renders it: the stafflist's second
# column is the artist's circle (所属社团), not a romanization.  The <dd>
# entry is a genuine piped-link romanization; the red link next to it is the
# junk the old title=-based rule used to collect.
STAFF_HTML = """
<p><b>Arrangement</b></p>
<div class="stafflist-wrapper">
  <table class="stafflist">
    <tr>
      <td><a title="隣人">隣人</a></td>
      <td><a title="ZYTOKINE">ZYTOKINE</a></td>
      <td>Tr.2/12</td>
    </tr>
    <tr>
      <td><a title="Shibayan">Shibayan</a></td>
      <td><a title="ShibayanRecords">ShibayanRecords</a></td>
      <td>Tr.6</td>
    </tr>
  </table>
</div>
<p><b>Vocal</b></p>
<div class="stafflist-wrapper">
  <table class="stafflist">
    <tr>
      <td><a title="3L">3L</a></td>
      <td><a title="NJK Record">NJK Record</a></td>
      <td>Tr.2-12</td>
    </tr>
  </table>
</div>
<dl>
  <dt>Guitar</dt>
  <dd>
    <a title="綾倉盟">Ayakura Mei</a>
    <a class="new" title="duca（页面不存在）">duca</a>
  </dd>
</dl>
"""


class StaffNameMappingTests(unittest.TestCase):
    """The Staff section's stafflist column 2 is a circle, not a romanization."""

    def setUp(self):
        self.soup = BeautifulSoup(STAFF_HTML, "html.parser")
        self.name_map = thwiki.parse_thwiki_staff_names(self.soup)

    def test_circle_column_is_not_used_as_a_romanization(self):
        for artist in ("隣人", "Shibayan", "3L"):
            self.assertNotIn(artist, self.name_map)

    def test_piped_dd_link_supplies_a_romanization(self):
        self.assertEqual(self.name_map.get("綾倉盟"), "Ayakura Mei")

    def test_red_link_titles_are_dropped(self):
        self.assertNotIn("duca（页面不存在）",
                         self.name_map)
        self.assertNotIn("duca", self.name_map)

    def test_album_staff_still_reads_the_artist_column(self):
        staff = thwiki.parse_thwiki_album_staff(self.soup)
        self.assertEqual(staff["arrangement"], ["隣人", "Shibayan"])
        self.assertEqual(staff["vocal"], ["3L"])

    def test_latin_credits_are_never_rewritten_by_the_map(self):
        # Defence in depth: even a bad mapping must not touch a Latin credit.
        bad_map = {"Shibayan": "ShibayanRecords", "隣人": "ZYTOKINE"}
        self.assertEqual(
            tag_io._romanize_credit_names(["Shibayan"], bad_map), ["Shibayan"])


if __name__ == "__main__":
    unittest.main()
