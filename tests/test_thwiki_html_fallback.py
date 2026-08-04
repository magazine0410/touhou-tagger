import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

SOURCE_DIR = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

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


if __name__ == "__main__":
    unittest.main()
