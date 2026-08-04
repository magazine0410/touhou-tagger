import unittest

from tests import _support  # noqa: F401

import japanese_romanizer


@unittest.skipUnless(
    japanese_romanizer.MECAB_AVAILABLE,
    "MeCab/UniDic is required for romanizer output tests",
)
class JapaneseRomanizerTests(unittest.TestCase):
    def test_title_override_applies_before_common_suffixes(self):
        base = "緋色月下、狂咲ノ絶"
        expected_base = "Hiiro Gekka, Kyoushou no Zetsu"

        self.assertEqual(japanese_romanizer.to_romaji(base), expected_base)
        self.assertEqual(
            japanese_romanizer.to_romaji(base + " [Instrumental]"),
            expected_base + " [Instrumental]",
        )
        self.assertEqual(
            japanese_romanizer.to_romaji(base + " (インスト)"),
            expected_base + " ( Insuto )",
        )
        self.assertEqual(
            japanese_romanizer.to_romaji(base + "-Radio Edit"),
            expected_base + "-Radio Edit",
        )

    def test_title_override_does_not_match_alphanumeric_continuation(self):
        base = "緋色月下、狂咲ノ絶"
        result = japanese_romanizer.to_romaji(base + "Extra")

        self.assertNotEqual(result, "Hiiro Gekka, Kyoushou no ZetsuExtra")
