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
    def test_investigated_japanese_titles_convert_and_pass_language_guard(self):
        cases = {
            "蔷薇": "Bara",
            "炼沙回廊": "Rensa Kairou",
            "牢狱STRIP": "Rougoku STRIP",
            "浪漫纪行": "Roman Kikou",
            "百花缭乱": "Hyakka Ryouran",
            "幽灵乐团 · 幽雅に咲かせ、墨染の桜":
                "Yuurei Gakudan · Yuuga ni Sakase、Sumizome no Sakura",
            "大神神话传": "Oomiwa Shinwaden",
            "沉泥": "Chindei",
            "轮廻": "Rinne",
            "燋燄誓契": "Shouen Seikitsu",
        }
        for title, expected in cases.items():
            for suffix in ("", " [Instrumental]"):
                with self.subTest(title=title, suffix=suffix):
                    self.assertEqual(japanese_romanizer.to_romaji(title + suffix),
                                     expected + suffix)
                    self.assertIsNone(japanese_romanizer._language_skip_reason(title + suffix))
        self.assertEqual(japanese_romanizer.to_romaji("煉沙回廊"), "Rensa Kairou")

        # The live event spelling is supported; its intended pronunciation
        # remains unverified, so test alias normalization without blessing
        # the dictionary's current reading of that proper name.
        live = "瑠璃色幻想鄉(Live at東方艷騷会Vol.3)"
        canonical = "瑠璃色幻想郷(Live at 東方艶騒会Vol.3)"
        self.assertEqual(japanese_romanizer.to_romaji(live),
                         japanese_romanizer.to_romaji(canonical))
        self.assertIsNone(japanese_romanizer._language_skip_reason(live))
        self.assertFalse(japanese_romanizer._has_unresolved_output(
            japanese_romanizer.to_romaji(live), live))

    def test_default_japanese_retains_explicit_chinese_exclusions(self):
        for title in ("明鏡止水", "東京", "清明", "棱彩", "夜の歌 (月下独舞)"):
            self.assertIsNone(japanese_romanizer._language_skip_reason(title))
        for title in ("背水一战", "我亲爱傀儡", "蔷薇 (你好)"):
            self.assertEqual(japanese_romanizer._language_skip_reason(title), "skip_non_japanese")
        self.assertEqual(japanese_romanizer._language_skip_reason(
            "兽之道的清晨", "/music/Mystia's Izakaya/OST1/song.flac"), "skip_non_japanese")
        self.assertIsNone(japanese_romanizer._language_skip_reason(
            "明鏡止水", "/music/Mystia's Izakaya remix/song.flac"))

    def test_embedded_titles_and_spelling_aliases(self):
        cases = {
            "花畑のエリカ (原曲：少女绮想曲 ～ Dream Battle)": "Shoujo Kisoukyoku",
            "reverberate (原曲：ヴワル魔法図书馆)": "Voile Mahou Toshokan",
            "幻想乡の二ッ岩": "Gensokyo no Futatsuiwa",
            "鎮座する瑰意琦行": "Chinza Suru Kaiikikou",
            "信仰は儚き人间の为に": "Shinkou wa Hakanaki Ningen no Tame ni",
            "雩 - 春の訪れと共に稲妻が鳴り響く": "Amahiki - Haru no Otozure",
        }
        for title, fragment in cases.items():
            with self.subTest(title=title):
                self.assertIn(fragment, japanese_romanizer.to_romaji(title))
                self.assertIsNone(japanese_romanizer._language_skip_reason(title))
        value = japanese_romanizer.to_romaji("Mix (少女绮想曲) + 二色莲花蝶")
        self.assertEqual(value, "Mix (Shoujo Kisoukyoku) + Nishiki Rengechou")

    def test_title_matches_require_boundaries_and_prefer_longest(self):
        with patch.object(japanese_romanizer, "_TITLE_OVERRIDES", {
                "少女": "SHORT", "少女绮想曲": "LONG"}):
            self.assertEqual(japanese_romanizer.to_romaji("(少女绮想曲)"), "(LONG)")
            for title in ("新少女绮想曲", "少女绮想曲Extra", "X少女绮想曲", "少女绮想曲集"):
                with self.subTest(title=title):
                    self.assertNotIn("LONG", japanese_romanizer.to_romaji(title))
        self.assertIn("欢迎", japanese_romanizer.to_romaji("欢迎光临夜雀食堂"))
        self.assertIn("橤", japanese_romanizer.to_romaji("橤の想い"))

    def test_masking_circles_survive_conversion_and_guard(self):
        for title in ("疵とマントと〇〇心", "宇〇刑事シャ〇パン神社", "マジ〇チ青森產トマト出荷"):
            with self.subTest(title=title):
                output = japanese_romanizer.to_romaji(title)
                self.assertEqual(output.count("〇"), title.count("〇"))
                self.assertNotIn("Rei", output)
                self.assertFalse(japanese_romanizer._has_unresolved_output(output, title))
        for title in ("〇", "二〇二四年", "〇人", "第〇話", "１２〇年"):
            with self.subTest(title=title):
                self.assertEqual(list(japanese_romanizer._masking_circle_spans(title)), [])
                self.assertTrue(japanese_romanizer._has_unresolved_output("Year 〇", title))

    def test_theme_spelling_aliases_preserve_subtitles(self):
        for bases, expected, suffix in (
            (("少女綺想曲", "少女绮想曲"), "Shoujo Kisoukyoku", " ～ Capriccio · Dream Battle"),
            (("二色蓮花蝶", "二色莲花蝶"), "Nishiki Rengechou", " ～ Ancients · Red and White"),
            (("有頂天変", "有顶天变"), "Uchoutenpen", " ～ Wonderful Heaven"),
        ):
            for base in bases:
                with self.subTest(base=base):
                    self.assertEqual(japanese_romanizer.to_romaji(base), expected)
                    self.assertEqual(japanese_romanizer.to_romaji(base + suffix),
                                     expected + suffix.replace("～", "~"))
                    self.assertEqual(japanese_romanizer.to_romaji(base + " [Instrumental]"),
                                     expected + " [Instrumental]")

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
class RomanizerWriteGuardTests(unittest.TestCase):
    def test_release_exclusion_is_limited_to_recorded_title_and_release(self):
        circle = "[鸽屋谷]"
        album = "2022.10.03 回忆京都 [深圳TH4]"
        root = f"/music/{circle}/{album}"
        for path in (root + "/song.flac", root + "/Disc 2/song.flac"):
            with self.subTest(path=path):
                self.assertEqual(japanese_romanizer._language_skip_reason(
                    "神隐", path), "skip_non_japanese")
                self.assertIsNone(japanese_romanizer._language_skip_reason(
                    "神隠しの夜", path))
        for path in (None, "/music/other/song.flac",
                     f"/music/other/{album}/song.flac",
                     f"/music/{circle}/{album} remix/song.flac",
                     f"/music/{circle}/unrelated/{album}/song.flac",
                     root + ".flac"):
            with self.subTest(path=path):
                self.assertIsNone(japanese_romanizer._language_skip_reason("神隐", path))
        self.assertIsNone(japanese_romanizer._language_skip_reason("神隐 remix", root + "/song.flac"))

    def test_release_exclusion_normalizes_width_and_directory_case(self):
        # Select a real reviewed entry with an ASCII directory label and
        # fullwidth punctuation, to exercise normalization on both sides.
        path = "/music/[SORRICOP]/2025.07.19 [SRCP-03] 须臾的悖论 ~ Immortal Dialectics ~/Disc 1/song.flac"
        self.assertEqual(japanese_romanizer._language_skip_reason(
            "月难!心跳加速是病啊", path.lower()), "skip_non_japanese")
        self.assertIsNone(japanese_romanizer._language_skip_reason(
            "マニック☆スパーク", path))
        self.assertIsNone(japanese_romanizer._language_skip_reason(
            "無舟海（Japanese ver.）", path))

    def test_release_exclusion_prevents_even_forced_writes(self):
        path = "/music/[鸽屋谷]/2022.10.03 回忆京都 [深圳TH4]/Disc 1/song.flac"
        for existing in (None, "Kami"):
            for dry_run in (False, True):
                with self.subTest(existing=existing, dry_run=dry_run), \
                        patch.object(japanese_romanizer, "is_ready", return_value=True), \
                        patch.object(japanese_romanizer, "read_title", return_value="神隐"), \
                        patch.object(japanese_romanizer, "read_titlesort", return_value=existing), \
                        patch.object(japanese_romanizer, "to_romaji") as convert, \
                        patch.object(japanese_romanizer, "set_titlesort") as write:
                    result = japanese_romanizer.romanize_file(
                        path, force_titlesort=True, dry_run=dry_run)
                    self.assertEqual(result["status"], "skip_non_japanese")
                    self.assertEqual(result["titlesort_old"], existing)
                    self.assertIsNone(result["titlesort_new"])
                    convert.assert_not_called()
                    write.assert_not_called()

    def test_chinese_titles_do_not_reach_conversion_or_writer(self):
        for title, status in (
            ("欢迎光临夜雀食堂！", "skip_non_japanese"),
            ("我亲爱傀儡", "skip_non_japanese"),
            ("你好!カンフー娘", "skip_non_japanese"),
            ("夜の歌 (交响管乐)", "skip_non_japanese"),
            ("夜の歌 - 欢迎光临", "skip_non_japanese"),
        ):
            for existing in (None, "Previous sort"):
                with self.subTest(title=title, existing=existing), \
                        patch.object(japanese_romanizer, "is_ready", return_value=True), \
                        patch.object(japanese_romanizer, "read_title", return_value=title), \
                        patch.object(japanese_romanizer, "read_titlesort", return_value=existing), \
                        patch.object(japanese_romanizer, "to_romaji") as convert, \
                        patch.object(japanese_romanizer, "set_titlesort") as write:
                    result = japanese_romanizer.romanize_file("test.flac", force_titlesort=True)
                    self.assertEqual(result["status"], status)
                    self.assertEqual(result["titlesort_old"], existing)
                    self.assertIsNone(result["titlesort_new"])
                    convert.assert_not_called()
                    write.assert_not_called()

    def test_directory_exclusion_prevents_conversion_and_writes(self):
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
                patch.object(japanese_romanizer, "read_title", return_value="兽之道的清晨"), \
                patch.object(japanese_romanizer, "read_titlesort", return_value="Old"), \
                patch.object(japanese_romanizer, "to_romaji") as convert, \
                patch.object(japanese_romanizer, "set_titlesort") as write:
            result = japanese_romanizer.romanize_file(
                "/music/Mystia's Izakaya/OST1/song.flac", force_titlesort=True)
            self.assertEqual(result["status"], "skip_non_japanese")
            convert.assert_not_called()
            write.assert_not_called()

    def test_unreviewed_han_title_can_be_written_as_japanese(self):
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
                patch.object(japanese_romanizer, "read_title", return_value="明鏡止水"), \
                patch.object(japanese_romanizer, "read_titlesort", return_value="Old"), \
                patch.object(japanese_romanizer, "to_romaji", return_value="Meikyou Shisui"), \
                patch.object(japanese_romanizer, "set_titlesort") as write:
            result = japanese_romanizer.romanize_file("song.flac", force_titlesort=True)
            self.assertEqual(result["status"], "overwritten")
            write.assert_called_once_with("song.flac", "Meikyou Shisui", dry_run=False)

    def test_reviewed_han_titles_can_still_be_written(self):
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
                patch.object(japanese_romanizer, "read_title", return_value="少女绮想曲"), \
                patch.object(japanese_romanizer, "read_titlesort", return_value="Old"), \
                patch.object(japanese_romanizer, "set_titlesort") as write:
            result = japanese_romanizer.romanize_file("test.flac", force_titlesort=True)
            self.assertEqual(result["status"], "overwritten")
            write.assert_called_once_with("test.flac", "Shoujo Kisoukyoku", dry_run=False)

    def test_incomplete_results_never_reach_writer(self):
        for incomplete in ("Shoujo 绮想 Kyoku", "Unknown 𠮷", "Song カナ", "", "  "):
            for existing in (None, "Existing sort", incomplete):
                for dry_run in (False, True):
                    with self.subTest(incomplete=incomplete, existing=existing, dry_run=dry_run), \
                            patch.object(japanese_romanizer, "is_ready", return_value=True), \
                            patch.object(japanese_romanizer, "read_title", return_value="曲の夢"), \
                            patch.object(japanese_romanizer, "read_titlesort", return_value=existing), \
                            patch.object(japanese_romanizer, "to_romaji", return_value=incomplete), \
                            patch.object(japanese_romanizer, "set_titlesort") as writer:
                        result = japanese_romanizer.romanize_file(
                            "test.flac", force_titlesort=True, dry_run=dry_run)
                        self.assertEqual(result["status"], "skip_unresolved")
                        self.assertEqual(result["titlesort_new"], incomplete)
                        self.assertEqual(result["titlesort_old"], existing)
                        writer.assert_not_called()

    def test_unresolved_batch_result_is_logged_and_counted_as_skipped(self):
        messages = []
        with patch.object(japanese_romanizer, "is_ready", return_value=True), \
                patch.object(japanese_romanizer, "romanize_file", return_value={
                    "status": "skip_unresolved", "title": "曲", "titlesort_new": "绮想",
                }):
            result = japanese_romanizer.romanize_files(
                [{"path": "test.flac"}], log=messages.append)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(any("[UNRESOLVED]" in line for line in messages))


def _feature(surface, reading, pos="名詞", sub_pos="普通名詞", *,
             lemma=None, pronunciation=None, goshu="和", conjugation="*"):
    fields = ["*"] * 29
    fields[0:2] = [pos, sub_pos]
    fields[5] = conjugation
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

    def explanatory_rows(self):
        return [
            ("な", _feature("な", "ナ", "助動詞", lemma="ダ", conjugation="連体形-一般")),
            ("ん", _feature("ん", "ン", "助詞", "準体助詞", lemma="ノ")),
            ("だ", _feature("だ", "ダ", "助動詞", lemma="ダ")),
        ]

    def test_explanatory_nanda_joins_but_final_particle_stays_separate(self):
        self.assertEqual(self.convert_tokens(self.explanatory_rows()), "Nanda")
        self.assertEqual(self.convert_tokens([
            ("日", _feature("日", "ヒ")), *self.explanatory_rows(),
            ("よ", _feature("よ", "ヨ", "助詞", "終助詞")),
        ]), "Hi Nanda yo")

    def test_explanatory_nanda_requires_grammatical_evidence(self):
        for index, feature in (
            (0, _feature("な", "ナ", "名詞", lemma="ダ", conjugation="連体形-一般")),
            (0, _feature("な", "ナ", "助動詞", lemma="ダ")),
            (1, _feature("ん", "ン", "助詞", "終助詞", lemma="ノ")),
            (1, _feature("ん", "ン", "助詞", "準体助詞", lemma="ン")),
            (2, _feature("だ", "ダ", "名詞")),
        ):
            rows = self.explanatory_rows()
            rows[index] = (rows[index][0], feature)
            with self.subTest(index=index, feature=feature):
                self.assertNotIn("Nanda", self.convert_tokens(rows))
        rows = self.explanatory_rows()
        rows[1] = ("の", _feature("の", "ノ", "助詞", "準体助詞"))
        self.assertEqual(self.convert_tokens(rows), "Na no Da")

    def test_explanatory_nanda_preserves_gaps_and_reviewed_replacements(self):
        for boundary in (1, 2):
            for gap in (" ", "\t", "　", "・"):
                rows = self.explanatory_rows()
                rows.insert(boundary, (gap, _feature(gap, gap, "補助記号")))
                text = "".join(surface for surface, _ in rows)
                if gap != "・":
                    rows.pop(boundary)  # MeCab omits whitespace nodes.
                with self.subTest(boundary=boundary, gap=gap), patch.object(
                        japanese_romanizer, "_mecab", _FakeMeCab({text: rows})):
                    self.assertEqual(japanese_romanizer._japanese_segment_to_romaji(
                        text, first_in_title=True), "Na n Da")
        for phrase, expected in (
            (("な", "ん"), "Reviewed Da"),
            (("ん", "だ"), "Na Reviewed"),
            (("な", "ん", "だ"), "Reviewed"),
        ):
            with self.subTest(phrase=phrase), patch.object(
                    japanese_romanizer, "_PHRASE_OVERRIDES", {phrase: "Reviewed"}):
                self.assertEqual(self.convert_tokens(self.explanatory_rows()), expected)
        with patch.object(japanese_romanizer, "_LOANWORDS_MAP", {"da": "Reviewed"}):
            self.assertEqual(self.convert_tokens(self.explanatory_rows()), "Na n Reviewed")

    def test_classical_ki_joins_an_identified_adjective_stem(self):
        # The observed parse labels き as a noun in the title and as a verb
        # when 儚き stands alone; neither classification should block repair.
        for conjugation in ("語幹", "語幹-一般"):
            for ending_pos in ("名詞", "動詞"):
                with self.subTest(conjugation=conjugation, ending_pos=ending_pos):
                    self.assertEqual(self.convert_tokens([
                        ("儚", _feature("儚", "ハカナ", "形容詞", conjugation=conjugation)),
                        ("き", _feature("き", "キ", ending_pos)),
                    ]), "Hakanaki")

    def test_classical_ki_requires_adjective_and_stem_metadata(self):
        for surface, reading, pos, conjugation, expected in (
            ("美しい", "ウツクシイ", "形容詞", "連体形-一般", "Utsukushii Ki"),
            ("儚", "ハカナ", "形容詞", "*", "Hakana Ki"),
            ("儚", "ハカナ", "名詞", "語幹-一般", "Hakana Ki"),
        ):
            with self.subTest(surface=surface, pos=pos, conjugation=conjugation):
                self.assertEqual(self.convert_tokens([
                    (surface, _feature(surface, reading, pos, conjugation=conjugation)),
                    ("き", _feature("き", "キ")),
                ]), expected)

    def test_classical_ki_requires_exact_original_hiragana(self):
        stem = ("儚", _feature("儚", "ハカナ", "形容詞", conjugation="語幹-一般"))
        for surface, reading, expected in (
            ("木", "キ", "Hakana Ki"), ("期", "キ", "Hakana Ki"),
            ("きり", "キリ", "Hakana Kiri"),
        ):
            with self.subTest(surface=surface):
                self.assertEqual(self.convert_tokens([
                    stem, (surface, _feature(surface, reading)),
                ]), expected)
        # The existing stylistic normalizer changes 儚キ to 儚き for analysis.
        # The repair must still inspect the original text and refuse to join.
        rows = [stem, ("き", _feature("き", "キ"))]
        with patch.object(japanese_romanizer, "MECAB_AVAILABLE", True), \
                patch.object(japanese_romanizer, "_mecab", _FakeMeCab({"儚き": rows})):
            self.assertEqual(japanese_romanizer.to_romaji("儚キ"), "Hakana Ki")

    def test_classical_ki_cannot_cross_whitespace_or_removed_separator(self):
        stem = ("儚", _feature("儚", "ハカナ", "形容詞", conjugation="語幹-一般"))
        ending = ("き", _feature("き", "キ"))
        for gap in (" ", "\t", "　", "・"):
            text = "儚" + gap + "き"
            rows = [stem, ending]
            if gap == "・":
                rows.insert(1, (gap, _feature(gap, gap, "補助記号")))
            with self.subTest(gap=gap), \
                    patch.object(japanese_romanizer, "_mecab", _FakeMeCab({text: rows})):
                self.assertEqual(japanese_romanizer._japanese_segment_to_romaji(
                    text, first_in_title=True), "Hakana Ki")

    def test_classical_ki_preserves_phrase_replacements_on_either_side(self):
        stem = ("儚", _feature("儚", "ハカナ", "形容詞", conjugation="語幹-一般"))
        ending = ("き", _feature("き", "キ"))
        dream = ("夢", _feature("夢", "ユメ"))
        for rows, phrase, replacement, expected in (
            ([dream, stem, ending], ("夢", "儚"), "Reviewed", "Reviewed Ki"),
            ([stem, ending, dream], ("き", "夢"), "Reviewed", "Hakana Reviewed"),
            ([stem, ending], ("儚", "き"), "Keep Space", "Keep Space"),
        ):
            with self.subTest(phrase=phrase), patch.object(
                    japanese_romanizer, "_PHRASE_OVERRIDES", {phrase: replacement}):
                self.assertEqual(self.convert_tokens(rows), expected)

    def test_classical_ki_also_preserves_single_token_replacements(self):
        rows = [("儚", _feature("儚", "ハカナ", "形容詞", conjugation="語幹-一般")),
                ("き", _feature("き", "キ"))]
        for mapping, expected in (({"hakana": "Reviewed"}, "Reviewed Ki"),
                                  ({"ki": "Reviewed"}, "Hakana Reviewed")):
            with self.subTest(mapping=mapping), patch.object(
                    japanese_romanizer, "_LOANWORDS_MAP", mapping):
                self.assertEqual(self.convert_tokens(rows), expected)

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

    def test_explanatory_nanda_in_song_title(self):
        cases = {
            "きっと今日は休憩の日なんだよ": "Kitto Kyou wa Kyuukei no Hi Nanda yo",
            "夢なんだね": "Yume Nanda ne",
            "ごめんよ": "Gomen yo",
            "夢なのだよ": "Yume Na no Da yo",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(japanese_romanizer.to_romaji(title), expected)

    def test_classical_adjective_in_touhou_title_and_remix_fragments(self):
        cases = {
            "信仰は儚き人間の為に": "Shinkou wa Hakanaki Ningen no Tame ni",
            "儚き": "Hakanaki", "儚き夢": "Hakanaki Yume",
            "儚き人間": "Hakanaki Ningen", "儚い": "Hakanai",
            "美しき": "Utsukushiki", "古き": "Furuki",
            "美しい木": "Utsukushii Ki", "美しいき": "Utsukushii Ki",
            "儚 き": "Hakana Ki", "儚・き": "Hakana Ki", "儚キ": "Hakana Ki",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(japanese_romanizer.to_romaji(title), expected)
        for separator in ("、", "「", "(", "\n"):
            with self.subTest(separator=separator):
                result = japanese_romanizer.to_romaji("儚" + separator + "き")
                self.assertIn(separator, result)
                self.assertNotIn("Hakanaki", result)

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
