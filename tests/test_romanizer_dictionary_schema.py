"""Surface-reading regressions for supported UniDic feature layouts."""
import csv
import importlib
import io
import unittest

from tests import _support  # noqa: F401
import japanese_romanizer as r


# These are dictionary schemas, not title or companion-data overrides.
# UniDic 2.1.2 binary/lite has 26 columns; UniDic 2.2+/3.x has 29.
_COMMON_FIELDS = (
    "pos1 pos2 pos3 pos4 cType cForm lForm lemma orth pron orthBase "
    "pronBase goshu iType iForm fType fForm"
).split()
_SCHEMAS = {
    26: _COMMON_FIELDS + (
        "kana kanaBase form formBase iConType fConType aType aConType aModType"
    ).split(),
    29: _COMMON_FIELDS + (
        "iConType fConType type kana kanaBase form formBase aType aConType "
        "aModType lid lemma_id"
    ).split(),
}


def _feature(size, **values):
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(
        values.get(field, "*") for field in _SCHEMAS[size])
    return output.getvalue()


class DictionarySchemaTests(unittest.TestCase):
    def test_surface_inflection_wins_over_base_form_in_both_layouts(self):
        for size in _SCHEMAS:
            for surface, reading, base in (
                ("忘れ", "ワスレ", "ワスレル"),
                ("走っ", "ハシッ", "ハシル"),
                ("読ん", "ヨン", "ヨム"),
                ("美しかっ", "ウツクシカッ", "ウツクシイ"),
            ):
                with self.subTest(size=size, surface=surface):
                    feature = _feature(
                        size, orth=surface, kana=reading, pron=reading,
                        lForm=base, kanaBase=base, form=reading, formBase=base)
                    self.assertEqual(r._get_reading(feature), reading)

    def test_surface_kana_preserves_volitional_vowel_spelling(self):
        for size in _SCHEMAS:
            with self.subTest(size=size):
                feature = _feature(
                    size, orth="行こう", kana="イコウ", pron="イコー",
                    lForm="イク", kanaBase="イク", form="イコウ", formBase="イク")
                self.assertEqual(r._get_reading(feature), "イコウ")

    def test_quoted_commas_do_not_change_schema_detection(self):
        for size in _SCHEMAS:
            with self.subTest(size=size):
                feature = _feature(
                    size, kana="ミヨウ", pron="ミヨー", lForm="ミル",
                    formBase="ミル", fConType="B1S6SjShS,B1S8SjShS",
                    aConType="動詞%F2@1,形容詞%F4@-2")
                self.assertEqual(r._get_reading(feature), "ミヨウ")

    def test_missing_surface_kana_falls_back_to_surface_pronunciation(self):
        for size in _SCHEMAS:
            for missing in ("*", ""):
                with self.subTest(size=size, missing=missing):
                    feature = _feature(
                        size, kana=missing, pron="イコー", lForm="イク",
                        kanaBase="イク", formBase="イク")
                    self.assertEqual(r._get_reading(feature), "イコー")

    def test_legacy_without_kana_uses_surface_pronunciation(self):
        fields = ["*"] * 17
        fields[6], fields[9] = "ハシル", "ハシッ"
        self.assertEqual(r._get_reading(",".join(fields)), "ハシッ")

    def test_unrecognized_layout_does_not_guess_a_kana_column(self):
        for size in (21, 25, 27, 28, 30):
            with self.subTest(size=size):
                fields = ["*"] * size
                fields[6], fields[9] = "ハシル", "ハシッ"
                fields[17], fields[20] = "C1", "ハシル"
                self.assertEqual(r._get_reading(",".join(fields)), "ハシッ")

    def test_lemma_is_only_used_when_surface_fields_are_missing(self):
        for size in _SCHEMAS:
            with self.subTest(size=size):
                self.assertEqual(r._get_reading(_feature(size, lForm="ヨム")), "ヨム")

    def test_unknown_node_has_no_reading(self):
        self.assertIsNone(r._get_reading("名詞,普通名詞,一般,*,*,*"))
        self.assertIsNone(r._get_reading(""))


class InstalledDictionarySchemaTests(unittest.TestCase):
    def check_dictionary(self, package):
        try:
            mecab = importlib.import_module("MeCab")
            dictionary = importlib.import_module(package)
            tagger = mecab.Tagger(f'-d "{dictionary.DICDIR}"')
        except (ImportError, RuntimeError) as exc:
            self.skipTest(f"{package} dictionary unavailable: {exc}")
        for text, expected_surface, expected_reading in (
            ("忘れ", "忘れ", "ワスレ"),
            ("走った", "走っ", "ハシッ"),
            ("読ん", "読ん", "ヨン"),
            ("美しかった", "美しかっ", "ウツクシカッ"),
            ("行こう", "行こう", "イコウ"),
        ):
            with self.subTest(package=package, text=text):
                node = tagger.parseToNode(text)
                while node is not None and not node.surface:
                    node = node.next
                self.assertIsNotNone(node)
                self.assertEqual(node.surface, expected_surface)
                self.assertEqual(r._get_reading(node.feature), expected_reading)

    def test_full_dictionary_surface_readings(self):
        self.check_dictionary("unidic")

    def test_lite_dictionary_surface_readings(self):
        self.check_dictionary("unidic_lite")


if __name__ == "__main__":
    unittest.main()
