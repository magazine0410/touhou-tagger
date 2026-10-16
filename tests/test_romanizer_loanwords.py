"""Dictionary spelling restoration, independent of companion-data entries."""
import csv
from dataclasses import replace
import io
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401
from tests.test_japanese_romanizer import _FakeMeCab, _feature
import japanese_romanizer as r


class LoanwordMetadataTests(unittest.TestCase):
    def test_token_retains_etymon_separately_from_lemma_reading(self):
        parts = next(csv.reader([_feature('モザイク', 'モザイク', goshu='外')]))
        parts[7] = 'モザイク-mosaic'
        stream = io.StringIO()
        csv.writer(stream).writerow(parts)
        with patch.object(r, '_mecab', _FakeMeCab({
                'モザイク': [('モザイク', stream.getvalue().strip())]})):
            token, = r._read_tokens('モザイク')
        self.assertEqual(token.lemma, 'モザイク-mosaic')
        self.assertEqual(token.lemma_reading, 'モザイク')
        self.assertEqual(token.reading, 'モザイク')

    def test_ineligible_metadata_never_reaches_spelling_lookup(self):
        token = r._Token('モザイク', 'モザイク', 'モザイク', '名詞',
                         '普通名詞', '外', 'モザイク', 0, 4,
                         lemma='モザイク-mosaic')
        for changes in ({'unknown': True}, {'goshu': '固'}, {'goshu': '和'},
                        {'pos': '動詞'}, {'conjugation_form': '連用形-一般'},
                        {'surface': 'モザイグ'}, {'lemma': ''},
                        {'lemma': 'モザイク-mosaic（図柄）'},
                        {'lemma': 'モザイク-two words'}, {'lemma': 'モザイク-d\'Or'}):
            with self.subTest(changes=changes), patch.object(r, '_mecab') as mecab:
                self.assertEqual(r._dictionary_loanwords(
                    'モザイク', [replace(token, **changes)]), {})
                mecab.parse.assert_not_called()


@unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
class LoanwordIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Even tests exercising replacement precedence use only synthetic
        # entries; no expectation relies on the companion data file.
        self.addCleanup(patch.stopall)
        patch.multiple(r, _TITLE_OVERRIDES={}, _TITLE_SPELLING_ALIASES={},
                       _PHRASE_OVERRIDES={}, _LOANWORDS_MAP={}).start()

    def test_complete_dictionary_supported_segments(self):
        for source, expected in {
                'シークレットシスターコンプレックス': 'Secret Sister Complex',
                'シークレット・シスター・コンプレックス': 'Secret Sister Complex',
                'モザイクディスコ': 'Mosaic Disco',
                'ローズマリー': 'Rosemary',
                'リグレッション メモリー': 'Regression Memory',
                'パーフェクト': 'Perfect',
                'コミュニケーション': 'Communication',
                'ﾛｰｽﾞﾏﾘｰ': 'Rosemary',
                '「ローズマリー」Live': '「Rosemary」Live',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_uncertain_katakana_runs_and_hiragana_keep_written_readings(self):
        for source in ('ハートフルスマイル', 'アマテラスカイ', 'ぱーふぇくと'):
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False),
                                 r.to_romaji(source, use_overrides=False,
                                 restore_loanwords=False))

    def test_complete_katakana_words_in_mixed_titles(self):
        # Japanese grammar provides an explicit boundary; an English token
        # is still not recovered from the middle of a rejected katakana run.
        for source, expected in {
                '風神パパラッチ': 'Fuujin Paparazzi',
                '夜のスター': 'Yoru no Star',
                'チルノのパーフェクトさんすう教室': 'Chiruno no Perfect Sansuu Kyoushitsu',
                'ツナガル': 'Tsunagaru',
                'マカブル': 'Maka Buru',
                'ディスアスター': 'Disu Asutaa',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_shortened_plural_and_variant_forms_are_not_expanded(self):
        for source, expected in {
                'アニメ': 'Anime', 'テレビ': 'Terebi', 'コンビニ': 'Konbini',
                'ハーツ': 'Haatsu', 'シスターズ': 'Shisutaazu',
                'パルフェ': 'Parufe', 'ヴォヤージュ': 'Voyaaju',
                'フランドール': 'Furan Dooru',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_competing_etymons_decline_entire_segment(self):
        # Exact-span dictionary alternatives must be considered even if they
        # precede the best node in its bnext list, or contain a sense label.
        for source, expected in {
                'シック': 'Shikku', 'フライ': 'Furai', 'フォー': 'Foo',
                'パン': 'Pan', 'ユーフォー': 'Yuu Foo',
                'シックシスター': 'Shikku Shisutaa',
                'シスター・シック': 'Shisutaa Shikku',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_phonetic_option_is_local_and_reaches_fragments(self):
        self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False,
                                     restore_loanwords=False), 'Roozumarii')
        self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False), 'Rosemary')
        with patch.object(r, '_TITLE_OVERRIDES', {'夜': 'Night'}):
            self.assertEqual(r.to_romaji('夜 (ローズマリー)', restore_loanwords=False),
                             'Night (Roozumarii)')
            self.assertEqual(r.to_romaji('夜 (ローズマリー)'), 'Night (Rosemary)')
        with patch.object(r, '_TITLE_SPELLING_ALIASES', {'想い': 'ローズマリー'}):
            self.assertEqual(r.to_romaji('想い', restore_loanwords=False), 'Roozumarii')
            self.assertEqual(r.to_romaji('想い'), 'Rosemary')

    def test_reviewed_spellings_have_priority(self):
        with patch.object(r, '_LOANWORDS_MAP', {'roozumarii': 'Reviewed'}):
            self.assertEqual(r.to_romaji('ローズマリー'), 'Reviewed')
            self.assertEqual(r.to_romaji('ローズマリー', restore_loanwords=False), 'Reviewed')
            self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False), 'Rosemary')
        with patch.object(r, '_PHRASE_OVERRIDES', {('モザイク', 'ディスコ'): 'Reviewed'}):
            self.assertEqual(r.to_romaji('モザイクディスコ'), 'Reviewed')
            self.assertEqual(r.to_romaji('モザイクディスコ', use_overrides=False), 'Mosaic Disco')

    def test_lattice_failure_falls_back_to_phonetic_output(self):
        for error in (AttributeError, TypeError, RuntimeError):
            with self.subTest(error=error), patch.object(r.MeCab, 'Lattice', side_effect=error):
                self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False), 'Roozumarii')
        with patch.object(r, '_mecab', wraps=r._mecab) as mecab:
            mecab.parse.return_value = False
            self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False), 'Roozumarii')

    def test_empty_lattice_is_not_evidence_for_restoration(self):
        with patch.object(r.MeCab, 'Lattice') as lattice, \
                patch.object(r, '_mecab', wraps=r._mecab) as mecab:
            mecab.parse.return_value = True
            lattice.return_value.begin_nodes.return_value = None
            self.assertEqual(r.to_romaji('ローズマリー', use_overrides=False), 'Roozumarii')
