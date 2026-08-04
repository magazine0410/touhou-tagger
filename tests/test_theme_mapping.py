import unittest

from tests import _support  # noqa: F401

import theme_mapping


class ThemeMappingTests(unittest.TestCase):
    def test_translation_normalizes_wiki_typography(self):
        mapping = {"永夜抄 ～ Eastern Night": "Eternal Night Vignette"}
        data = {
            "mapping": mapping,
            "normalized_keys": {
                theme_mapping._normalize_for_mapping("永夜抄 ～ Eastern Night"):
                "永夜抄 ～ Eastern Night",
            },
        }
        tracks = [{"original_titles": ["永夜抄　～ Eastern Night."]}]

        theme_mapping.translate_titles(tracks, data)

        self.assertEqual(tracks[0]["original_titles"], ["Eternal Night Vignette"])

    def test_variant_inherits_original_titles(self):
        tracks = [
            {"title": "Song Name", "original_titles": ["Original Theme"]},
            {"title": "Song Name (Instrumental)", "original_titles": []},
            {"title": "Unrelated Song", "original_titles": []},
        ]

        theme_mapping._inherit_instrumental_titles(tracks)

        self.assertEqual(tracks[1]["original_titles"], ["Original Theme"])
        self.assertEqual(tracks[2]["original_titles"], [])

