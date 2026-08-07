import json
import unittest
from pathlib import Path

from tests import _support  # noqa: F401

import theme_mapping


class ThemeMappingTests(unittest.TestCase):
    def test_named_project_sections_are_separate_and_loaded_for_lookup(self):
        mapping_path = Path(theme_mapping.__file__).with_name(
            "touhou_theme_mapping.json"
        )
        raw = json.loads(mapping_path.read_text(encoding="utf-8"))

        self.assertNotIn("秋霜玉　～ Clockworks", raw["mapping"])
        self.assertEqual(len(raw["sections"]["lenen"]["mapping"]), 126)
        self.assertEqual(len(raw["sections"]["seihou"]["mapping"]), 64)

        loaded = theme_mapping.load_theme_mapping(str(mapping_path))
        expected = {
            "キリングスペリオル ～ Giant killing":
                "Killing Superior ~ Giant killing",
            "超越时空之翼 ～ M theory":
                "Wings That Transcend Spacetime ~ M theory",
            "秋霜玉　～ Clockworks": "Autumn Frost Orb ~ Clockworks",
            "はじまりの前に": "Before the Beginning",
        }
        for source, english in expected.items():
            with self.subTest(source=source):
                self.assertEqual(
                    theme_mapping.translate_title(source, loaded), english,
                )

    def test_reviewed_source_variants_translate_to_english(self):
        mapping = theme_mapping.load_theme_mapping(None)
        expected = {
            "遥か３８万キロのボヤージュ":
                "Faraway Voyage of 380,000 Kilometers",
            "ロマンチック逃飛行": "Romantic Escape Flight",
            "夜の鳩山を飛ぶ -Power MIX":
                "Fly above Hatoyama at night - Power MIX",
            "東方萃夢想（Arrange）":
                "Eastern Forgathering Dream (Arrange)",
            "ハーセルヴズ": "Herselves",
            "今宵は飄逸なエゴイスト　～ Egoistic Flowers.":
                "Tonight Stars an Easygoing Egoist ~ Egoistic Flowers.",
            "月まで届け不死の煙":
                "Reach for the Moon, Immortal Smoke",
            "君はあの影を見たか": "Did You See that Shadow?",
            "幽夢　～ Inanimate Dream（未使用バージョン）":
                "Faint Dream ~ Inanimate Dream (Unused Version)",
            "河童様の云う通り ～ One-way Accelerator":
                "The Kappa Way as Said ~ One-way Accelerator",
        }

        self.assertIsNotNone(mapping)
        for source, english in expected.items():
            with self.subTest(source=source):
                self.assertEqual(
                    theme_mapping.translate_title(source, mapping), english,
                )

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

    def test_translation_normalizes_case_and_tilde_spacing(self):
        mapping = {
            "二色蓮花蝶 ～ Red And White":
                "Dichromatic Lotus Butterfly ~ Red and White",
            "眠れる恐怖　～ Sleeping Terror": "Sleeping Terror",
        }
        data = {
            "mapping": mapping,
            "normalized_keys": {
                theme_mapping._normalize_for_mapping(key): key
                for key in mapping
            },
        }
        tracks = [{"original_titles": [
            "二色蓮花蝶　～ Red and White",
            "眠れる恐怖　～Sleeping Terror",
        ]}]

        theme_mapping.translate_titles(tracks, data)

        self.assertEqual(tracks[0]["original_titles"], [
            "Dichromatic Lotus Butterfly ~ Red and White",
            "Sleeping Terror",
        ])

    def test_variant_inherits_original_titles(self):
        tracks = [
            {"title": "Song Name", "original_titles": ["Original Theme"]},
            {"title": "Song Name (Instrumental)", "original_titles": []},
            {"title": "Unrelated Song", "original_titles": []},
        ]

        theme_mapping._inherit_instrumental_titles(tracks)

        self.assertEqual(tracks[1]["original_titles"], ["Original Theme"])
        self.assertEqual(tracks[2]["original_titles"], [])
