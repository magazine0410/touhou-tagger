import csv
import io
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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


# These tests exercise the engine without the optional dictionary or real files.
def _feature(surface, reading, pos="名詞", sub_pos="普通名詞", *,
             lemma=None, pronunciation=None, goshu="和"):
    fields = ["*"] * 29
    fields[0:2] = [pos, sub_pos]
    fields[6:10] = [lemma or reading, surface, surface, pronunciation or reading]
    fields[12] = goshu
    fields[18] = "B1S6SjShS,B1S8SjShS"  # a real quoted-comma UniDic field
    fields[20] = reading
    output = io.StringIO()
    csv.writer(output, lineterminator="").writerow(fields)
    return output.getvalue()


class _FakeMeCab:
    def __init__(self, rows):
        self.rows = rows

    def parseToNode(self, text):
        node = None
        for surface, feature in reversed(self.rows[text]):
            node = SimpleNamespace(surface=surface, feature=feature, next=node,
                                   stat=0 if len(next(csv.reader([feature]))) > 6 else 1)
        return node


class RomanizerEngineTests(unittest.TestCase):
    def setUp(self):
        for name in ("_TITLE_OVERRIDES", "_PHRASE_OVERRIDES", "_LOANWORDS_MAP"):
            context = patch.object(japanese_romanizer, name, {})
            context.start()
            self.addCleanup(context.stop)

    def convert_tokens(self, rows):
        text = "".join(surface for surface, _ in rows)
        with patch.object(japanese_romanizer, "MECAB_AVAILABLE", True), \
                patch.object(japanese_romanizer, "_mecab", _FakeMeCab({text: rows})):
            return japanese_romanizer.to_romaji(text)

    def test_surface_reading_uses_csv_and_preserves_inflection(self):
        feature = _feature("見よう", "ミヨウ", "動詞", lemma="ミル", pronunciation="ミヨー")
        self.assertEqual(japanese_romanizer._get_reading(feature), "ミヨウ")
        feature = _feature("あたし", "アタシ", "代名詞", lemma="ワタシ")
        self.assertEqual(japanese_romanizer._get_reading(feature), "アタシ")

    def test_reading_fallbacks_for_short_or_missing_fields(self):
        fields = ["名詞"] + ["*"] * 16
        fields[6], fields[9] = "ゲンケイ", "ゲンケー"
        self.assertEqual(japanese_romanizer._get_reading(",".join(fields)), "ゲンケー")
        fields[9] = "*"
        self.assertEqual(japanese_romanizer._get_reading(",".join(fields)), "ゲンケイ")
        self.assertIsNone(japanese_romanizer._get_reading("名詞,普通名詞,一般,*,*,*"))

    def test_extended_kana_and_longest_match_in_all_lookaheads(self):
        cases = {
            "クァクィクェクォ": "kwakwikwekwo", "グァ": "gwa",
            "クヮ": "kwa", "スィズィ": "sizi", "フィュ": "fyu",
            "ティュディュ": "tyudyu", "ヴャヴョ": "vyavyo",
            "ヷヸヹヺ": "vavivevo", "ッフィュ": "ffyu",
            "ンイェ": "n'ye", "フィュー": "fyuu", "ｳﾞｧ": "va",
            "か\u3099": "ga", "コンヤク": "kon'yaku", "マッチャ": "matcha",
            "シンブン": "shinbun", "ー": "ー",
        }
        for kana, expected in cases.items():
            with self.subTest(kana=kana):
                self.assertEqual(japanese_romanizer._kana_to_romaji(kana), expected)
        self.assertEqual(japanese_romanizer._geminate_romaji("𠮷"), "𠮷")
        self.assertEqual(japanese_romanizer._geminate_romaji("1"), "1")

    def test_japanese_detection_and_segmentation_share_coverage(self):
        for text in ("ｹﾞﾝｿｳ", "𠮷", "𠀋", "ㇰ", "〇", "々"):
            with self.subTest(text=text):
                self.assertTrue(japanese_romanizer.has_japanese(text))
                self.assertIsNotNone(japanese_romanizer._JP_SEGMENT_RE.fullmatch(text))
        for text in ("Rainbow", "1969", "★"):
            self.assertFalse(japanese_romanizer.has_japanese(text))

    def test_katakana_rewrite_requires_kanji_context(self):
        normalize = japanese_romanizer._normalize_katakana_okurigana
        self.assertEqual(normalize("ハとヘ"), "ハとヘ")
        self.assertEqual(normalize("永イ夜ハ空ヲ歩キ"), "永い夜は空を歩き")
        self.assertEqual(normalize("一ヶ月のメロディー"), "一ヶ月のメロディー")

    def test_syllabic_n_uses_reading_at_a_joined_kanji_boundary(self):
        self.assertEqual(self.convert_tokens([
            ("無限", _feature("無限", "ムゲン")),
            ("遠", _feature("遠", "エン", "接尾辞")),
        ]), "Mugen'en")

    def test_separate_particle_keeps_its_word_boundary_after_n(self):
        self.assertEqual(self.convert_tokens([
            ("ごめん", _feature("ごめん", "ゴメン")),
            ("よ", _feature("よ", "ヨ", "助詞", "終助詞")),
        ]), "Gomen yo")

    def test_small_tsu_joins_adverb_and_particle(self):
        self.assertEqual(self.convert_tokens([
            ("ふっ", _feature("ふっ", "フッ", "副詞")),
            ("と", _feature("と", "ト", "助詞", "格助詞")),
        ]), "Futto")

    def test_gemination_uses_reading_even_when_surface_ends_in_kanji(self):
        self.assertEqual(self.convert_tokens([
            ("六", _feature("六", "ロッ")),
            ("拍", _feature("拍", "パク", "接尾辞")),
        ]), "Roppaku")

    def test_long_mark_separate_from_its_vowel_is_retained(self):
        self.assertEqual(self.convert_tokens([
            ("夢", _feature("夢", "ユメ")),
            ("ーー", _feature("ーー", "*", "補助記号")),
        ]), "Yumeee")

    def test_fallback_uses_shared_kana_rules_and_preserves_unknown_gaps(self):
        converter = SimpleNamespace(convert=lambda text: [
            {"orig": "翻", "kana": "ホン", "hepburn": "hon"},
            {"orig": "訳", "kana": "ヤク", "hepburn": "yaku"},
        ])
        with patch.object(japanese_romanizer, "PYKAKASI_AVAILABLE", True), \
                patch.object(japanese_romanizer, "_kks", converter):
            self.assertEqual(japanese_romanizer._pykakasi_fallback("翻訳"), "hon'yaku")
            self.assertEqual(japanese_romanizer._pykakasi_fallback("𠮷翻訳"), "𠮷hon'yaku")
        with patch.object(japanese_romanizer, "PYKAKASI_AVAILABLE", False):
            self.assertEqual(japanese_romanizer._pykakasi_fallback("𠮷"), "𠮷")
        with patch.object(japanese_romanizer, "PYKAKASI_AVAILABLE", True), \
                patch.object(japanese_romanizer, "_kks", SimpleNamespace(convert=lambda _: [])):
            self.assertEqual(self.convert_tokens([
                ("𠮷", "名詞,普通名詞,一般,*,*,*"),
            ]), "𠮷")

    def test_regular_counter_sound_changes(self):
        cases = {
            (1, "本"): "ippon", (3, "本"): "sanbon", (6, "本"): "roppon",
            (4, "本"): "yonhon", (8, "本"): "happon", (10, "本"): "juppon",
            (100, "本"): "hyappon", (300, "本"): "sanbyappon",
            (1000, "本"): "senbon", (21, "本"): "nijuuippon",
            (1, "匹"): "ippiki", (3, "匹"): "sanbiki", (6, "匹"): "roppiki",
            (1, "杯"): "ippai", (3, "杯"): "sanbai", (6, "杯"): "roppai",
            (1, "個"): "ikko", (6, "個"): "rokko", (8, "個"): "hakko",
            (3, "階"): "sangai", (3, "回"): "sankai",
            (1, "冊"): "issatsu", (6, "冊"): "rokusatsu",
            (1, "人"): "hitori", (2, "人"): "futari", (4, "人"): "yonin",
            (21, "人"): "nijuuichinin", (20, "歳"): "hatachi",
            (4, "月"): "shigatsu", (7, "月"): "shichigatsu", (9, "月"): "kugatsu",
            (1, "ヶ月"): "ikkagetsu", (6, "曲"): "rokkyoku",
        }
        for (number, counter), expected in cases.items():
            with self.subTest(number=number, counter=counter):
                reading = japanese_romanizer._counter_reading(number, counter)
                self.assertEqual(japanese_romanizer._kana_to_romaji(reading), expected)
        self.assertIsNone(japanese_romanizer._counter_reading(13, "月"))

    def test_numeral_parsing_rejects_identifiers_and_malformed_numbers(self):
        for text, expected in (("123", 123), ("二〇二四", 2024), ("二十三", 23),
                               ("三百六十二", 362), ("一万二千", 12000), ("2万", 20000)):
            self.assertEqual(japanese_romanizer._number_value(text), expected)
        for text in ("01", "1.5", "十百", "万億", "x"):
            self.assertIsNone(japanese_romanizer._number_value(text))

    def test_arabic_counter_context_reaches_complete_word(self):
        self.assertEqual(self.convert_tokens([
            ("2人", _feature("2人", "フタリ")),
        ]), "Futari")
        self.assertEqual(self.convert_tokens([
            ("3", "名詞,数詞,*,*,*,*"),
            ("月", _feature("月", "ツキ")),
        ]), "Sangatsu")

    def test_counter_matching_does_not_take_part_of_a_word(self):
        self.assertEqual(self.convert_tokens([
            ("一", _feature("一", "イチ")),
            ("曲線", _feature("曲線", "キョクセン")),
        ]), "Ichi Kyokusen")

    def test_counter_matching_preserves_names_and_ordinals(self):
        self.assertEqual(self.convert_tokens([
            ("千曲", _feature("千曲", "チクマ", sub_pos="固有名詞")),
            ("川", _feature("川", "ガワ", "接尾辞")),
        ]), "Chikumagawa")
        self.assertEqual(self.convert_tokens([
            ("第", _feature("第", "ダイ", "接頭辞")),
            ("一", _feature("一", "イチ")),
            ("人", _feature("人", "ニン", "接尾辞")),
            ("者", _feature("者", "シャ", "接尾辞")),
        ]), "Dai Ichininsha")

    def test_loanword_cannot_consume_a_later_phrase_override(self):
        rows = [(s, _feature(s, s)) for s in "アイウ"]
        with patch.object(japanese_romanizer, "_LOANWORDS_MAP", {"ai": "Loan"}), \
                patch.object(japanese_romanizer, "_PHRASE_OVERRIDES", {("イ", "ウ"): "Reviewed"}):
            self.assertEqual(self.convert_tokens(rows), "A Reviewed")

    def test_counter_cannot_consume_a_later_phrase_override(self):
        rows = [("三", _feature("三", "サン")), ("本", _feature("本", "ホン")),
                ("の", _feature("の", "ノ", "助詞"))]
        with patch.object(japanese_romanizer, "_PHRASE_OVERRIDES", {("本", "の"): "Reviewed"}):
            self.assertEqual(self.convert_tokens(rows), "San Reviewed")

    def test_foreign_lemma_alias_preserves_existing_loanword_keys(self):
        with patch.object(japanese_romanizer, "_LOANWORDS_MAP", {"boyaaju": "Voyage"}):
            self.assertEqual(self.convert_tokens([
                ("ヴォヤージュ", _feature("ヴォヤージュ", "ヴォヤージュ",
                                       lemma="ボヤージュ", goshu="外")),
            ]), "Voyage")


@unittest.skipUnless(japanese_romanizer.MECAB_AVAILABLE, "MeCab/UniDic required")
class RomanizerDictionaryIntegrationTests(unittest.TestCase):
    def setUp(self):
        for name in ("_TITLE_OVERRIDES", "_PHRASE_OVERRIDES", "_LOANWORDS_MAP"):
            context = patch.object(japanese_romanizer, name, {})
            context.start()
            self.addCleanup(context.stop)

    def test_written_forms_and_verb_inflections(self):
        cases = {
            "あたしの歌": "Atashi no Uta", "あんたの夢": "Anta no Yume",
            "やっぱり": "Yappari", "見よう": "Miyou", "行こう": "Ikou",
            "思って": "Omotte", "待っちゃう": "Matchau", "夢だった": "Yume Datta",
            "神々": "Kamigami", "星空": "Hoshizora",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(japanese_romanizer.to_romaji(title), expected)

    def test_stylized_kana_preserves_words_particles_and_long_vowels(self):
        cases = {
            "ハとヘ": "Ha to He", "ア": "A", "ハ": "Ha",
            "永イ夜ハ空ヲ歩キ": "Nagai Yoru wa Sora o Aruki",
            "きょーは": "Kyoo wa", "ぱーてぃーは": "Paatii wa",
            "あのぱーてぃーは": "Ano Paatii wa", "ありがとーね": "Arigatoo ne",
            "ずーっと": "Zuutto", "うれしーな": "Ureshii na", "にーとです": "Niito Desu",
            "ふぃーばー": "Fiibaa", "ふっと": "Futto", "ごめんよ": "Gomen yo",
            "無限遠": "Mugen'en", "夢ーー": "Yumeee",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(japanese_romanizer.to_romaji(title), expected)

    def test_numeric_expressions_and_latin_identifiers(self):
        cases = {
            "2人の夜": "Futari no Yoru", "3人の夜": "Sannin no Yoru",
            "3月の夢": "Sangatsu no Yume", "一本": "Ippon", "三本": "Sanbon",
            "六本": "Roppon", "三匹": "Sanbiki", "三階": "Sangai",
            "LOVE1969": "LOVE1969", "R2-D2の夢": "R2-D2 no Yume",
            "恋2024ver": "Koi 2024ver", "1969": "1969", "1.5本": "1.5 Hon",
            "60年目の東方裁判": "60 Nenme no Touhou Saiban",
            "千曲": "Chikuma", "第一人者": "Dai Ichininsha",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(japanese_romanizer.to_romaji(title), expected)

    def test_extended_and_halfwidth_kana(self):
        for title, expected in (("クァルテット", "Kwarutetto"),
                                ("フィュージョン", "Fyuujon"), ("ｹﾞﾝｿｳ", "Gensou")):
            self.assertEqual(japanese_romanizer.to_romaji(title), expected)
