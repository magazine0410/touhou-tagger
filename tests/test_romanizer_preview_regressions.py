"""Failures found in the library preview, including conservative counterexamples."""
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401
import japanese_romanizer as r


@unittest.skipUnless(r.MECAB_AVAILABLE, "MeCab/UniDic required")
class PreviewEngineTests(unittest.TestCase):
    def setUp(self):
        context = patch.multiple(r, _TITLE_OVERRIDES={}, _TITLE_SPELLING_ALIASES={},
                                 _PHRASE_OVERRIDES={}, _LOANWORDS_MAP={})
        context.start()
        self.addCleanup(context.stop)

    def test_kana_and_classical_repairs_without_data(self):
        for title, expected in {
            "こんにちは世界": "Konnichiwa Sekai",
            "妖しき夜からこんばんは": "Ayashiki Yoru kara Konbanwa",
            "こころのうた": "Kokoro no Uta",
            "みょん": "Myon", "おでんぱ": "Odenpa",
            "みょんのうた": "Myon no Uta",
            "鮮烈のみょん": "Senretsu no Myon", "みょんでポン": "Myon de Pon",
            "みょ～んみょんみょん": "Myo~N Myon Myon",
            "9秒で聴くおでんぱ": "9 Byou de Kiku Odenpa",
            "ずっと君と": "Zutto Kimi to",
            "らいぶらりあん": "Raiburarian",
            "幼き末裔": "Osanaki Matsuei", "白き花": "Shiroki Hana",
            "若き血": "Wakaki Chi", "強き者": "Tsuyoki Mono",
            "小さきもの": "Chiisaki Mono",
            "永遠に幼き紅色に染めて": "Eien ni Osanaki Koushoku ni Somete",
            "古きにゃんにゃんしぇん": "Furuki nyannyanshen",
            "白きつね": "Shiro Kitsune", "焼き魚": "Yakizakana",
            "君は誰": "Kimi wa Dare", "一ヶ月": "Ikkagetsu",
            "ありがとうございます": "Arigatou Gozaimasu",
            "夜空に舞い喰らうもの": "Yozora ni Mai Kurau Mono",
            "また3時にお会いしましょう": "Mata 3 Ji ni Oai Shimashou",
            "コイはふぃっしんぐ": "Koi wa Fisshingu",
            "みしゃくじ": "Mishakuji", "とおりゃんせ": "Tooryanse",
            "ぱちゅみりん": "Pachumirin", "こいいろ きゃらせれ": "Koi Iro Kyarasere",
            "きゅーと": "Kyuuto", "ぱーとちゅー": "Paato Chuu",
            "八雲家のお約束条項ぱーとちゅー": "Yakumoke no Oyakusoku Joukou Paato Chuu",
            "キャンプ場": "Kyanpujou", "メタルっぽい何か": "Metaruppoi Nan ka",
        }.items():
            with self.subTest(title=title):
                self.assertEqual(r.to_romaji(title, use_overrides=False), expected)

    def test_long_vowel_prefix_and_lexical_small_ke_keep_dictionary_context(self):
        # The title's intended English spelling requires a reviewed entry;
        # this specifically tests the cross-token vowel repair without it.
        result = r.to_romaji("は～りぃすたーふぃっしゅ", use_overrides=False)
        self.assertIn("sutaafisshu", result.replace(" ", "").lower())
        self.assertFalse(r._has_unresolved_output(result, "は～りぃすたーふぃっしゅ"))
        title = "少女幻想ヶ原を往く"
        self.assertEqual(r.to_romaji(title, use_overrides=False), "Shoujo Gensou Ga Hara o Iku")
        self.assertFalse(r._has_unresolved_output(r.to_romaji(title), title))
        # Unattached vowel marks are still unresolved; no invented vowel.
        self.assertTrue(r._has_unresolved_output(r.to_romaji("ー"), "ー"))
        ambiguous = "子守唄ーユカウラー"
        self.assertTrue(r._has_unresolved_output(r.to_romaji(ambiguous), ambiguous))

    def test_existing_phrases_survive_dictionary_tokenization(self):
        with patch.object(r, "_PHRASE_OVERRIDES", {
            ("白", "玉", "楼"): "Hakugyokurou",
            ("命", "蓮", "寺"): "Myourenji",
            ("前", "退", "後", "進"): "Zentaikoushin",
            ("てゐ",): "Tewi",
        }):
            for title, expected in {
                "白玉楼であまあまお勤め": "Hakugyokurou de Amaama Otsutome",
                "命蓮寺にお邪魔して": "Myourenji ni Ojama Shite",
                "前退後進": "Zentaikoushin", "えいえんてゐ": "Eien Tewi",
            }.items():
                with self.subTest(title=title):
                    self.assertEqual(r.to_romaji(title), expected)
            for title in ("白・玉楼", "白 玉楼"):
                self.assertNotIn("Hakugyokurou", r.to_romaji(title, use_overrides=False))
            # The prefix rule now joins 白 to 玉楼 on its own; the reviewed
            # phrase still decides the spelling where the two differ.
            self.assertEqual(r.to_romaji("白玉楼", use_overrides=False), "Hakugyokurou")
            self.assertNotIn("Hakugyokurou", r.to_romaji("白・玉楼"))
            self.assertNotIn("Tewi", r.to_romaji("見てゐる"))

    def test_loanword_lookup_preserves_plural_and_variant_forms(self):
        entries = {"shisutaa": "Sister", "dooru": "Doll", "gaaru": "Girl",
                   "suiito": "Sweet", "tsuaa": "Tour", "naito": "Night",
                   "merankorii": "Melancholy", "booyaju": "Voyage"}
        with patch.object(r, "_LOANWORDS_MAP", entries):
            for title, expected in {
                "シスターズ": "Sisters", "ドールズ": "Dolls", "ガールズ": "Girls",
                "スイーツ": "Sweets", "ツアーズ": "Tours", "ナイツ": "Nights",
                "メランコリア": "Merankoria", "ナイト": "Night",
            }.items():
                with self.subTest(title=title):
                    self.assertEqual(r.to_romaji(title, restore_loanwords=False), expected)
        self.assertEqual(r._written_loanword_form("ヴォヤージュ", "ボヤージュ", "Voyage"), "Voyage")
        self.assertIsNone(r._written_loanword_form("メランコリア", "メランコリー", "Melancholy"))

    def test_reviewed_long_words_can_cross_spurious_particles(self):
        with patch.object(r, "_LOANWORDS_MAP", {"runasa": "Lunasa", "runatikku": "Lunatic",
                                               "runa": "Lunar", "doreddofuru": "Dreadful"}):
            self.assertEqual(r.to_romaji("ルナサ・ソロライブ"), "Lunasa Soro Raibu")
            self.assertIn("Lunatic", r.to_romaji("ゐなばるなてぃっく"))
            self.assertEqual(r.to_romaji("ドレッドフルエンジェル"), "Dreadful Angel")
        with patch.object(r, "_LOANWORDS_MAP", {"rin": "Rin"}):
            self.assertEqual(r.to_romaji("リンゲージ"), "Rin Geeji")

    def test_automatic_recovery_declines_bad_boundaries_and_etymons(self):
        for title, rejected in {
            "ファントムセイバー": "Say", "ツナガル": "Tuna",
            "スリープレスエスケープ": "Three", "マカブル": "Bull",
            "ワンモアチャンス": "Moi", "ディスアスター": "This",
            "フラジール・エゴ": "Flagyl", "マレイン": "Maleic",
        }.items():
            with self.subTest(title=title):
                self.assertNotIn(rejected, r.to_romaji(title, use_overrides=False))
        self.assertEqual(r.to_romaji("夜のスター", use_overrides=False), "Yoru no Star")
        self.assertEqual(r.to_romaji("ツナガル", use_overrides=False), "Tsunagaru")
        self.assertNotIn("Can", r.to_romaji("ゆるキャン△", use_overrides=False))
        self.assertEqual(r.to_romaji("キャン", use_overrides=False), "Kyan")
        self.assertEqual(r.to_romaji("ナイトラウンシジ", use_overrides=False), "Naitoraunshiji")
        self.assertEqual(r.to_romaji("ナイトネスブライトネス", use_overrides=False), "Naitonesuburaitonesu")

    def test_decorative_marks_do_not_disable_the_cjk_guard(self):
        for title in ("(ﾟ⊿ﾟ)", "Help me, ERINNNNNN!! o彡ﾟ", "夜(ﾟ⊿ﾟ)"):
            with self.subTest(title=title):
                result = r.to_romaji(title, use_overrides=False)
                self.assertFalse(r._has_unresolved_output(result, title))
                self.assertNotIn("San", result)
        for title in ("aﾟ", "(未知字゚)", "ー"):
            self.assertTrue(r._has_unresolved_output(title, title))


@unittest.skipUnless(r.MECAB_AVAILABLE, "MeCab/UniDic required")
class ReviewedPreviewDataTests(unittest.TestCase):
    def test_names_and_lexical_exceptions_remain_in_the_data_layer(self):
        for title, expected in {
            "月時計": "Tsukidokei", "咲夜": "Sakuya", "妹紅": "Mokou",
            "射命丸": "Shameimaru", "幽香": "Yuuka", "小傘": "Kogasa",
            "射命丸文": "Shameimaru Aya", "射命丸　文": "Shameimaru Aya",
            "射命丸 文のテーマ": "Shameimaru Aya no Theme",
            "今日も今日とてみょんな道": "Kyou mo Kyou tote Myonna Michi",
            "魂魄妖夢": "Konpaku Youmu", "幽谷響子": "Kasodani Kyouko",
            "紅魔館": "Koumakan", "てゐ": "Tewi",
            "らくえんおうた": "Rakuen no Uta", "らくえんのうた": "Rakuen no Uta",
            "ファントムセイバー01_00": "Phantom Saber 01_00",
            "パラレルパレット -off vocal-": "Parallel Palette -off vocal-",
            "ラストジャッジメント": "Last Judgment",
            "トッププレデター": "Top Predator",
            "スリープレスエスケープ": "Sleepless Escape",
            "ハングライダー": "Hang Glider",
            "Melody (サリー acoustic cover)": "Melody (Sally acoustic cover)",
            "スカル キャット -Brave or Death-": "Skull Cat -Brave or Death-",
            "[クロノ・トリガー]BC12000": "[Chrono Trigger]BC12000",
            "は～りぃすたーふぃっしゅ": "Hurry, Starfish",
        }.items():
            with self.subTest(title=title):
                self.assertEqual(r.to_romaji(title), expected)
        self.assertNotEqual(r.to_romaji("らくえんおうた", use_overrides=False), "Rakuen no Uta")
