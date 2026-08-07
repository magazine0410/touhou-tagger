import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _support  # noqa: F401

import theme_mapping
import translate_groupings


class TranslateGroupingsTests(unittest.TestCase):
    def setUp(self):
        self.mapping = theme_mapping.load_theme_mapping(None)
        self.assertIsNotNone(self.mapping)

    def test_translates_problem_variants_inside_multi_theme_value(self):
        old = (
            "Lotus Love; 二色蓮花蝶　～ Red and White; "
            "眠れる恐怖　～Sleeping Terror"
        )

        new, applied, untranslated = (
            translate_groupings.translate_grouping_value(old, self.mapping)
        )

        self.assertEqual(
            new,
            "Lotus Love; Dichromatic Lotus Butterfly ~ Red and White; "
            "Sleeping Terror",
        )
        self.assertEqual(len(applied), 2)
        self.assertEqual(untranslated, [])

    def test_translates_new_official_and_fanmade_aliases(self):
        old = (
            "遥か３８万キロのボヤージュ; "
            "幽夢　～ Inanimate Dream（未使用バージョン）; "
            "河童様の云う通り ～ One-way Accelerator"
        )

        new, applied, untranslated = (
            translate_groupings.translate_grouping_value(old, self.mapping)
        )

        self.assertEqual(
            new,
            "Faraway Voyage of 380,000 Kilometers; "
            "Faint Dream ~ Inanimate Dream (Unused Version); "
            "The Kappa Way as Said ~ One-way Accelerator",
        )
        self.assertEqual(len(applied), 3)
        self.assertEqual(untranslated, [])

    def test_translates_named_lenen_and_seihou_sections(self):
        old = (
            "キリングスペリオル ～ Giant killing; "
            "超越时空之翼 ～ M theory; はじまりの前に"
        )

        new, applied, untranslated = (
            translate_groupings.translate_grouping_value(old, self.mapping)
        )

        self.assertEqual(
            new,
            "Killing Superior ~ Giant killing; "
            "Wings That Transcend Spacetime ~ M theory; "
            "Before the Beginning",
        )
        self.assertEqual(len(applied), 3)
        self.assertEqual(untranslated, [])

    def test_unmatched_manual_value_is_preserved_exactly(self):
        old = "  手作りのテーマ  "

        new, applied, untranslated = (
            translate_groupings.translate_grouping_value(old, self.mapping)
        )

        self.assertEqual(new, old)
        self.assertEqual(applied, [])
        self.assertEqual(untranslated, ["手作りのテーマ"])

    def test_dry_run_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "track.flac"
            audio.touch()
            with mock.patch.object(
                translate_groupings, "read_grouping",
                return_value="眠れる恐怖　～Sleeping Terror",
            ), mock.patch.object(
                translate_groupings, "set_grouping",
            ) as write:
                summary = translate_groupings.process_paths(
                    [tmp], mapping_data=self.mapping, dry_run=True,
                )

        write.assert_not_called()
        self.assertEqual(summary["changed_files"], 1)
        self.assertEqual(summary["written"], 0)

    def test_stats_cache_dry_run_trusts_fresh_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "track.flac"
            audio.touch()
            cache_path = Path(tmp) / "stats_cache.json"
            cache_path.write_text(json.dumps({
                str(audio): [
                    audio.stat().st_mtime_ns,
                    "眠れる恐怖　～Sleeping Terror",
                    [], [], None, None, None, None, [],
                ],
            }), encoding="utf-8")
            with mock.patch.object(
                translate_groupings, "read_grouping",
            ) as read, mock.patch.object(
                translate_groupings, "set_grouping",
            ) as write:
                summary = translate_groupings.process_stats_cache(
                    [tmp], mapping_data=self.mapping,
                    cache_path=str(cache_path), dry_run=True,
                )

        read.assert_not_called()
        write.assert_not_called()
        self.assertEqual(summary["cache_candidates"], 1)
        self.assertEqual(summary["stale_candidates"], 0)
        self.assertEqual(summary["changed_files"], 1)

    def test_stats_cache_rereads_stale_candidate_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "track.flac"
            audio.touch()
            cache_path = Path(tmp) / "stats_cache.json"
            cache_path.write_text(json.dumps({
                str(audio): [
                    0, "眠れる恐怖　～Sleeping Terror",
                    [], [], None, None, None, None, [],
                ],
            }), encoding="utf-8")
            with mock.patch.object(
                translate_groupings, "read_grouping",
                return_value="二色蓮花蝶　～ Red and White",
            ) as read, mock.patch.object(
                translate_groupings, "set_grouping",
            ) as write:
                summary = translate_groupings.process_stats_cache(
                    [tmp], mapping_data=self.mapping,
                    cache_path=str(cache_path), dry_run=False,
                )

        read.assert_called_once_with(str(audio))
        write.assert_called_once_with(
            str(audio), "Dichromatic Lotus Butterfly ~ Red and White",
            dry_run=False,
        )
        self.assertEqual(summary["stale_candidates"], 1)
        self.assertEqual(summary["written"], 1)

    def test_stats_cache_filters_records_to_requested_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inside = root / "artist" / "inside.flac"
            outside = root / "other" / "outside.flac"
            inside.parent.mkdir()
            outside.parent.mkdir()
            inside.touch()
            outside.touch()
            cache_path = root / "stats_cache.json"
            record = lambda path: [
                path.stat().st_mtime_ns,
                "眠れる恐怖　～Sleeping Terror",
                [], [], None, None, None, None, [],
            ]
            cache_path.write_text(json.dumps({
                str(inside): record(inside),
                str(outside): record(outside),
            }), encoding="utf-8")

            summary = translate_groupings.process_stats_cache(
                [str(inside.parent)], mapping_data=self.mapping,
                cache_path=str(cache_path), dry_run=True,
            )

        self.assertEqual(summary["scanned"], 1)
        self.assertEqual(summary["changed_files"], 1)


if __name__ == "__main__":
    unittest.main()
