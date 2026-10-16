"""Engine regressions: expected readings here require no companion overrides."""
import csv
from dataclasses import replace
import io
import os
import shlex
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import _support  # noqa: F401
from tests.test_japanese_romanizer import _FakeMeCab, _feature
import japanese_romanizer as r


class KanaPhoneticTests(unittest.TestCase):
    def test_iteration_marks_expand_with_script_and_voicing(self):
        for source, expected in {
            'いすゞ': 'isuzu', 'さゝやき': 'sasayaki', 'つゞく': 'tsuzuku',
            'サヽ': 'sasa', 'スヾ': 'suzu', 'がゝ': 'gaka', 'ガヾ': 'gaga',
            'くゝゝ': 'kukuku', 'はゞ': 'haba', 'ぱゝ': 'paha',
            'あゝ': 'aa', 'いすゝ\u3099': 'isuzu',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r._kana_to_romaji(source), expected)

    def test_invalid_iteration_marks_remain_unresolved(self):
        for source in ('ゝ', 'ゞ', 'ヽ', 'ヾ', 'あゞ', 'アヾ', 'アゝ', 'あヽ',
                       'っゝ', 'ゃゝ', 'ーゝ', '星ゝ', 'か・ゞ'):
            with self.subTest(source=source):
                self.assertTrue(r.has_japanese(r._kana_to_romaji(source)))

    def test_mora_crosses_dictionary_boundary_but_not_separator(self):
        for text, rows, expected in (
            ('まじょ', [('まじ', _feature('まじ', 'マジ')),
                        ('ょ', _feature('ょ', 'ョ', '助詞'))], 'Majo'),
            ('フィュ', [('フィ', _feature('フィ', 'フィ')),
                        ('ュ', _feature('ュ', 'ュ'))], 'Fyu'),
            ('まじ・ょ', [('まじ', _feature('まじ', 'マジ')),
                         ('・', _feature('・', '・')),
                         ('ょ', _feature('ょ', 'ョ', '助詞'))], 'Maji yo'),
            ('字ょ', [('字', _feature('字', 'ジ')),
                     ('ょ', _feature('ょ', 'ョ', '助詞'))], 'Ji yo'),
        ):
            with self.subTest(text=text), patch.object(r, '_mecab', _FakeMeCab({text: rows})):
                self.assertEqual(r._japanese_segment_to_romaji(
                    text, first_in_title=True, use_overrides=False), expected)


@unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
class BaseEngineIntegrationTests(unittest.TestCase):
    def test_no_data_mode_is_local_and_bypasses_all_replacement_tiers(self):
        replacements = {'_TITLE_OVERRIDES': {'夜': 'TITLE'},
                        '_TITLE_SPELLING_ALIASES': {'星': '朝'},
                        '_PHRASE_OVERRIDES': {('猫', 'の'): 'PHRASE'},
                        '_LOANWORDS_MAP': {'neko': 'LOAN'}}
        with patch.multiple(r, **replacements):
            self.assertEqual(r.to_romaji('夜'), 'TITLE')
            self.assertEqual(r.to_romaji('星'), 'Asa')
            self.assertEqual(r.to_romaji('猫の夜'), 'PHRASE Yoru')
            self.assertEqual(r.to_romaji('ネコ'), 'LOAN')
            for source, expected in {'夜': 'Yoru', '星': 'Hoshi',
                                     '猫の夜': 'Neko no Yoru', 'ネコ': 'Neko'}.items():
                with self.subTest(source=source):
                    self.assertEqual(r.to_romaji(source, use_overrides=False), expected)
            self.assertEqual(r.to_romaji('夜'), 'TITLE')
            self.assertEqual(r.to_romaji('ネコ'), 'LOAN')

    def test_iteration_and_split_mora_in_real_dictionary(self):
        for source, expected in {'いすゞ': 'Isuzu', 'さゝやき': 'Sasayaki',
                                 'かゞ': 'Kaga', 'がゝ': 'Gaka', 'ぱゞ': 'Paba',
                                 'くゝゝ': 'Kukuku', 'はゝゞ': 'Hahaba',
                                 'まじょぱら': 'Majo Para',
                                 '門番少女ちゅうかなめいりん': 'Monban Shoujo Chuukanameirin'}.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_morphological_word_boundaries(self):
        cases = {
            'ここにいますから': 'Koko ni Imasu kara',
            'だから': 'Dakara', '夢だから': 'Yume Dakara', '行ったから': 'Itta kara',
            '笑うけど': 'Warau kedo', '食べながら': 'Tabe nagara',
            '泣いても': 'Naite mo', '帰れば': 'Kaereba',
            '待って': 'Matte', '泳いで': 'Oyoide',
            '行かなくちゃ': 'Ikanakucha', '食べちゃ': 'Tabecha', '死んじゃ': 'Shinja',
            'おじょうさまDAYS': 'Ojousama DAYS',
            'お祓い': 'Oharai', 'ご褒美': 'Gohoubi',
            'お別れ': 'Owakare', 'お 別れ': 'O Wakare',
            'お・別れ': 'O Wakare', '新世界': 'Shinsekai', '第一人者': 'Dai Ichininsha',
            '静かな夜': 'Shizuka na Yoru', '静かに': 'Shizuka ni',
            '大好きな君': 'Daisuki na Kimi', '夢だった': 'Yume Datta',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_honorific_prefix_preserves_reviewed_replacement_case(self):
        with patch.object(r, '_LOANWORDS_MAP', {'keeki': 'Reviewed'}):
            self.assertEqual(r.to_romaji('おケーキ'), 'O Reviewed')

    def test_fragmented_classical_adjectives_use_dictionary_evidence(self):
        cases = {
            '懐かしき東方の血': 'Natsukashiki Touhou no Chi',
            '優しき夢': 'Yasashiki Yume',
            '優しき夢と懐かしき夜': 'Yasashiki Yume to Natsukashiki Yoru',
            '儚き人間': 'Hakanaki Ningen', '美しき夜': 'Utsukushiki Yoru',
            '好き': 'Suki', '大好き': 'Daisuki', 'ときめき': 'Tokimeki',
            '焼き魚': 'Yakizakana', '懐かし・き': 'Natsukashi Ki',
            '懐かしキ': 'Natsukashi Ki', '懐かし き': 'Natsukashi Ki',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_classical_reanalysis_does_not_consume_reviewed_phrase(self):
        with patch.object(r, '_PHRASE_OVERRIDES', {('懐', 'か', 'しき'): 'Reviewed'}):
            self.assertEqual(r.to_romaji('懐かしき東方の血'), 'Reviewed Touhou no Chi')
            self.assertEqual(r.to_romaji('懐かしき東方の血', use_overrides=False),
                             'Natsukashiki Touhou no Chi')

    def test_delimiters_and_mixed_script_boundaries(self):
        cases = {
            '夜!': 'Yoru!', '月。': 'Tsuki。', '(夜)': '(Yoru)',
            '「夜」': '「Yoru」', '夜!夢': 'Yoru!Yume',
            '夜AD夢': 'Yoru AD Yume', '夜とADの夢': 'Yoru to AD no Yume',
            'A(夜)B': 'A(Yoru)B', '夜、夢。': 'Yoru、Yume。',
            '夜 [Live]': 'Yoru [Live]', '夜 ( 夢 )': 'Yoru ( Yume )',
            'A  B': 'A B', '夜\n夢': 'Yoru\nYume',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_hour_and_ordinal_counter_morphology(self):
        for source, expected in {
            '8番目の路地': 'Hachibanme no Roji',
            '十二時間睡眠': 'Juunijikan Suimin',
            '4時間': 'Yojikan', '9時間': 'Kujikan',
            '24時間': 'Nijuuyojikan', '十九時間': 'Juukujikan',
            '四番目': 'Yonbanme', '三番': 'Sanban',
            '01番': '01 Ban', '1.5時間': '1.5 Jikan',
            'R2番': 'R2 Ban', '3番組': '3 Bangumi',
        }.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)

    def test_classical_reanalysis_preserves_loanwords(self):
        # A reviewed katakana neighbour survives the reanalysis.  A native
        # word's reading (懐/フトコロ, 東方/トウホウ) is no longer a loanword
        # match, so it neither vetoes the repair nor takes a spelling.
        with patch.object(r, '_LOANWORDS_MAP', {'merodi': 'Reviewed'}):
            self.assertEqual(r.to_romaji('懐かしきメロディ'), 'Natsukashiki Reviewed')
        with patch.object(r, '_LOANWORDS_MAP', {'futokoro': 'Reviewed', 'touhou': 'Reviewed'}):
            self.assertEqual(r.to_romaji('懐かしき東方の血'), 'Natsukashiki Touhou no Chi')

    def test_split_mora_preserves_following_reviewed_word(self):
        rows = [('まじ', _feature('まじ', 'マジ')),
                ('ょ', _feature('ょ', 'ョ'))]
        with patch.object(r, '_mecab', _FakeMeCab({'まじょ': rows})), \
                patch.object(r, '_LOANWORDS_MAP', {'yo': 'Reviewed'}):
            self.assertEqual(r.to_romaji('まじょ'), 'Maji Reviewed')
            self.assertEqual(r.to_romaji('まじょ', use_overrides=False), 'Majo')

    def test_classical_reanalysis_rejects_changed_neighbor(self):
        old = [('懐', _feature('懐', 'フトコロ')),
               ('か', _feature('か', 'カ', '助詞')),
               ('しき', _feature('しき', 'シキ', '助詞')),
               ('風', _feature('風', 'フウ', '接尾辞'))]
        new = [('懐かしい', _feature('懐かしい', 'ナツカシイ', '形容詞')),
               ('風', _feature('風', 'カゼ'))]
        with patch.object(r, '_mecab', _FakeMeCab({'懐かしき風': old, '懐かしい風': new})):
            self.assertEqual(r.to_romaji('懐かしき風', use_overrides=False), 'Futokoro ka shikifuu')


    def test_review_fixes_with_the_real_dictionary(self):
        loanwords = {'heru': 'Hell', 'kiro': 'Kilo', 'kooru': 'Call', 'runa': 'Lunar',
                     'arisu': 'Alice', 'rin': 'Rin', 'hekaatia': 'Hecatia',
                     'rapisurazuri': 'Lapislazuli', 'intu・bakkudoa': 'Into Backdoor',
                     'shanhai': 'Shanghai', 'majikaru': 'Magical', 'nue': 'Nue',
                     'rein': 'Rain', 'terasu': 'Terrace', 'saron': 'Salon'}
        cases = {
            '減る': 'Heru', '帰路': 'Kiro', '凍る': 'Kooru', '瑠奈': 'Runa',
            '有栖': 'Arisu', '三輪車': 'Sanrinsha', '六輪': 'Rokurin',
            '照らす': 'Terasu', 'レ淫': 'Re In', 'お燐': 'Orin',
            'ヘル': 'Hell', 'アリス': 'Alice', 'ルナ': 'Lunar',
            'ありす': 'Alice', 'まじかる': 'Magical', 'ぬえ': 'Nue',
            'るーずれいん': 'Ruuzu Rain', '上海': 'Shanghai',
            'ヘカーティア・ラピスラズリ': 'Hecatia Lapislazuli',
            'イントゥ・バックドア': 'Into Backdoor',
            'サロン・ド・アノニマス': 'Salon Do Anonimasu',
            '雲居一輪': 'Ungo Ichirin', '十輪': 'Juurin', '一本': 'Ippon',
            '3分間': '3 Funkan', '3つ': 'Mittsu', '三つ': 'Mittsu',
            '3つ目': 'Mittsume', '10つ': '10 Tsu', '3秒': '3 Byou',
        }
        with patch.multiple(r, _TITLE_OVERRIDES={}, _TITLE_SPELLING_ALIASES={},
                            _PHRASE_OVERRIDES={}, _LOANWORDS_MAP=loanwords):
            for source, expected in cases.items():
                with self.subTest(source=source):
                    self.assertEqual(r.to_romaji(source), expected)
        for source, expected in {'ヘカーティア・ラピスラズリ': 'Hekaatia Rapisurazuri',
                                 '雲居一輪': 'Ungo Ichirin', '3分間': '3 Funkan'}.items():
            with self.subTest(source=source):
                self.assertEqual(r.to_romaji(source, use_overrides=False), expected)


def _place_name(surface, reading):
    """A 固有名詞/地名 feature; _feature leaves the third level at '*'."""
    fields = next(csv.reader([_feature(surface, reading, '名詞', '固有名詞', goshu='固')]))
    fields[2] = '地名'
    output = io.StringIO()
    csv.writer(output, lineterminator='').writerow(fields)
    return output.getvalue()


class ReviewFixTests(unittest.TestCase):
    """2026-10 engine review fixes, checked against hand-built dictionary rows."""

    def setUp(self):
        for name in ('_TITLE_OVERRIDES', '_PHRASE_OVERRIDES', '_LOANWORDS_MAP'):
            context = patch.object(r, name, {})
            context.start()
            self.addCleanup(context.stop)

    def convert(self, rows, loanwords=None, **kwargs):
        text = ''.join(surface for surface, _ in rows)
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab({text: rows})), \
                patch.object(r, '_LOANWORDS_MAP', loanwords or {}):
            return r.to_romaji(text, **kwargs)

    def test_native_readings_do_not_take_loanword_spellings(self):
        loanwords = {'heru': 'Hell', 'kiro': 'Kilo', 'runa': 'Lunar', 'tabako': 'Tobacco',
                     'shanhai': 'Shanghai', 'majikaru': 'Magical'}
        cases = [
            ([('減る', _feature('減る', 'ヘル', '動詞', '一般'))], 'Heru'),
            ([('帰路', _feature('帰路', 'キロ', goshu='漢'))], 'Kiro'),
            ([('瑠奈', _feature('瑠奈', 'ルナ', '名詞', '固有名詞', goshu='固'))], 'Runa'),
            # Kana spellings of any origin, dictionary-marked foreign words
            # and place names keep their reviewed spellings.
            ([('ヘル', _feature('ヘル', 'ヘル', goshu='外'))], 'Hell'),
            ([('ルナ', _feature('ルナ', 'ルナ', '名詞', '固有名詞', goshu='固'))], 'Lunar'),
            ([('まじかる', _feature('まじかる', 'マジカル', '助動詞', '*'))], 'Magical'),
            ([('煙草', _feature('煙草', 'タバコ', goshu='外'))], 'Tobacco'),
            ([('上海', _place_name('上海', 'シャンハイ'))], 'Shanghai'),
        ]
        for rows, expected in cases:
            with self.subTest(text=rows[0][0]):
                self.assertEqual(self.convert(rows, loanwords), expected)

    def test_kana_spellings_match_whatever_the_dictionary_calls_them(self):
        token = r._Token('ファンタジー', 'ふぁんたじー', 'ファンタジー', '名詞', '普通名詞',
                         '外', 'ファンタジー', 0, 6)
        with patch.object(r, '_LOANWORDS_MAP', {'fantajii': 'Fantasy'}):
            self.assertEqual(r._loanword_match([token]), 'Fantasy')
            self.assertEqual(r._loanword_match([replace(token, surface='ふぁんたじー',
                                                        goshu='和')]), 'Fantasy')
        name = r._Token('瑠奈', '瑠奈', 'ルナ', '名詞', '固有名詞', '固', 'ルナ', 0, 2,
                        pos3='人名')
        with patch.object(r, '_LOANWORDS_MAP', {'runa': 'Lunar'}):
            self.assertIsNone(r._loanword_match([name]))
            self.assertEqual(r._loanword_match([replace(name, pos3='地名')]), 'Lunar')

    def test_short_keys_apply_to_kana_runs_but_not_across_kanji(self):
        kana = [('ぬ', _feature('ぬ', 'ヌ', '助動詞', '*')),
                ('え', _feature('え', 'エ', '感動詞', 'フィラー'))]
        self.assertEqual(self.convert(kana, {'nue': 'Nue'}), 'Nue')
        mixed = [('レ', _feature('レ', 'レ')), ('淫', _feature('淫', 'イン', goshu='漢'))]
        self.assertEqual(self.convert(mixed, {'rein': 'Rain'}), 'Re In')
        long = [('東方', _feature('東方', 'トウホウ', goshu='漢')),
                ('紅魔郷', _feature('紅魔郷', 'コウマキョウ', goshu='漢'))]
        self.assertEqual(self.convert(long, {'touhoukoumakyou': 'Reviewed'}), 'Reviewed')

    def test_suffix_replacement_never_leaves_a_capital_mid_word(self):
        rows = [('三', _feature('三', 'サン', '名詞', '数詞', goshu='漢')),
                ('輪', _feature('輪', 'リン', '接尾辞', '名詞的', goshu='漢')),
                ('車', _feature('車', 'シャ', '接尾辞', '名詞的', goshu='漢'))]
        self.assertEqual(self.convert(rows, {'rin': 'Rin'}), 'Sanrinsha')
        rows = [('リアル', _feature('リアル', 'リアル', goshu='外')),
                ('イズム', _feature('イズム', 'イズム', '接尾辞', '名詞的', goshu='外'))]
        self.assertEqual(self.convert(rows, {'riaru': 'Real', 'izumu': 'Ism'}), 'Realism')
        self.assertEqual(self.convert(rows, {'riaru': 'Real', 'izumu': 'ISM'}), 'RealISM')

    def test_foreign_marked_word_still_vetoes_classical_reanalysis(self):
        old = [('懐', _feature('懐', 'フトコロ', goshu='外')),
               ('か', _feature('か', 'カ', '助詞')),
               ('しき', _feature('しき', 'シキ', '助詞')),
               ('夜', _feature('夜', 'ヨル'))]
        new = [('懐かしい', _feature('懐かしい', 'ナツカシイ', '形容詞', '一般')),
               ('夜', _feature('夜', 'ヨル'))]
        with patch.object(r, '_mecab', _FakeMeCab({'懐かしき夜': old, '懐かしい夜': new})):
            with patch.object(r, '_LOANWORDS_MAP', {'futokoro': 'Reviewed'}):
                self.assertEqual(r.to_romaji('懐かしき夜'), 'Reviewed ka shiki Yoru')
            self.assertEqual(r.to_romaji('懐かしき夜'), 'Natsukashiki Yoru')

    def test_unknown_katakana_run_splits_at_the_middle_dot(self):
        rows = [('ヘカーティア・ラピスラズリ', '名詞,普通名詞,一般,*,*,*')]
        self.assertEqual(self.convert(rows), 'Hekaatia Rapisurazuri')
        self.assertEqual(self.convert(rows, {'hekaatia': 'Hecatia',
                                             'rapisurazuri': 'Lapislazuli'}),
                         'Hecatia Lapislazuli')
        for key in ('hekaatia・rapisurazuri', 'hekaatiarapisurazuri'):
            with self.subTest(key=key):
                self.assertEqual(self.convert(rows, {key: 'Whole'}), 'Whole')
        self.assertEqual(self.convert([('・・ラピス', '名詞,普通名詞,一般,*,*,*')]), 'Rapisu')

    def test_unknown_name_across_a_dot_does_not_block_a_known_neighbour(self):
        salon = _feature('サロン', 'サロン', goshu='外', lemma='サロン')
        rows = [('サロン', salon.replace(',サロン,サロン,', ',サロン-salon,サロン,', 1)),
                ('・', _feature('・', '・', '補助記号', '一般', goshu='記号')),
                ('ド・アノニマス', '名詞,普通名詞,一般,*,*,*')]
        self.assertEqual(self.convert(rows, {'saron': 'Salon'}), 'Salon Do Anonimasu')

    def test_leftover_middle_dot_counts_as_unresolved(self):
        title = 'ヘカーティア・ラピスラズリ'
        self.assertTrue(r._has_unresolved_output('Hekaatia・rapisurazuri', title))
        self.assertFalse(r._has_unresolved_output('Hecatia Lapislazuli', title))
        self.assertFalse(r._has_unresolved_output('Yoru (・ω・)', '夜 (・ω・)'))

    def test_numeral_allomorph_uses_lemma_reading_where_sokuon_cannot_apply(self):
        ichi = ('一', _feature('一', 'イッ', '名詞', '数詞', lemma='イチ', goshu='漢'))
        cases = [
            ([('雲居', _feature('雲居', 'ウンゴ', '名詞', '固有名詞', goshu='固')), ichi,
              ('輪', _feature('輪', 'リン', '接尾辞', '名詞的', goshu='漢'))], 'Ungo Ichirin'),
            ([('十', _feature('十', 'ジッ', '名詞', '数詞', lemma='ジュウ', goshu='漢')),
              ('輪', _feature('輪', 'リン', '接尾辞', '名詞的', goshu='漢'))], 'Juurin'),
            ([ichi, ('体', _feature('体', 'タイ', '接尾辞', '名詞的', goshu='漢'))], 'Ittai'),
            ([ichi, ('遍', _feature('遍', 'ペン', '接尾辞', '名詞的', goshu='漢'))], 'Ippen'),
            ([ichi, ('斉', _feature('斉', 'セイ', '接尾辞', '名詞的', goshu='漢'))], 'Issei'),
            ([ichi], 'Ichi'),
            # Only numerals are repaired; a verb's っ-stem is correct as is.
            ([('行っ', _feature('行っ', 'イッ', '動詞', '一般', lemma='イク',
                              conjugation='連用形-促音便')),
              ('た', _feature('た', 'タ', '助動詞', '*', lemma='タ'))], 'Itta'),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)

    def test_counter_after_digits_is_its_own_word_in_base_reading(self):
        def digits(value):
            return value, '名詞,数詞,*,*,*,*'
        tsu = ('つ', _feature('つ', 'ツ', '接尾辞', '名詞的'))
        cases = [
            ([digits('3'), ('分間', _feature('分間', 'プンカン', lemma='フンカン', goshu='漢'))],
             '3 Funkan'),
            ([digits('3'), ('分', _feature('分', 'プン', lemma='フン', goshu='漢'))], '3 Fun'),
            ([digits('3'), tsu], 'Mittsu'),
            ([digits('10'), tsu], '10 Tsu'),
            ([digits('3'), ('日', _feature('日', 'カ', '接尾辞', '名詞的'))], '3 Ka'),
            ([digits('3'), ('本', _feature('本', 'ポン', '接尾辞', '名詞的', lemma='ホン',
                                        goshu='漢'))], 'Sanbon'),
            ([digits('3'), tsu, ('目', _feature('目', 'メ', '接尾辞', '名詞的'))], 'Mittsume'),
            ([('三', _feature('三', 'ミッ', '名詞', '数詞', lemma='ミ')), tsu], 'Mittsu'),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)
        self.assertEqual([r._counter_reading(n, 'つ') for n in range(1, 10)],
                         ['ヒトツ', 'フタツ', 'ミッツ', 'ヨッツ', 'イツツ',
                          'ムッツ', 'ナナツ', 'ヤッツ', 'ココノツ'])
        self.assertIsNone(r._counter_reading(10, 'つ'))


class TaggerLoadingTests(unittest.TestCase):
    """Dictionary selection runs without MeCab: a fake records the options."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='dic with space ')
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.full = os.path.join(self.root, 'full dic')
        self.lite = os.path.join(self.root, 'lite dic')
        for path in (self.full, self.lite):
            os.makedirs(path)
            with open(os.path.join(path, 'mecabrc'), 'w', encoding='utf-8') as handle:
                handle.write('\n')
        self.calls = []

    def fake_mecab(self, broken=()):
        calls = self.calls

        class Tagger:
            def __init__(self, options):
                calls.append(options)
                self.args = shlex.split(options)
                if any(path in self.args for path in broken):
                    raise RuntimeError('Failed initializing MeCab')
        return SimpleNamespace(Tagger=Tagger)

    def modules(self):
        return patch.dict(sys.modules, {'unidic': SimpleNamespace(DICDIR=self.full),
                                        'unidic_lite': SimpleNamespace(DICDIR=self.lite)})

    def test_dictionary_path_with_a_space_stays_one_argument(self):
        with self.modules():
            tagger, name = r._load_tagger(self.fake_mecab())
        self.assertEqual(name, 'unidic')
        self.assertEqual(tagger.args, ['-r', os.path.join(self.full, 'mecabrc'),
                                       '-d', self.full])
        self.assertNotIn(self.full, self.calls[0].split('"')[::2])

    def test_lite_fallback_when_the_full_dictionary_fails(self):
        with self.modules():
            tagger, name = r._load_tagger(self.fake_mecab(broken=(self.full,)))
        self.assertEqual(name, 'unidic_lite')
        self.assertEqual(tagger.args[-1], self.lite)
        self.assertEqual(len(self.calls), 2)

    def test_undownloaded_full_dictionary_skips_to_lite(self):
        shutil.rmtree(self.full)
        with self.modules():
            tagger, name = r._load_tagger(self.fake_mecab())
        self.assertEqual(name, 'unidic_lite')
        self.assertEqual(len(self.calls), 1)

    def test_uninstalled_full_package_skips_to_lite(self):
        with patch.dict(sys.modules, {'unidic': None,
                                      'unidic_lite': SimpleNamespace(DICDIR=self.lite)}):
            tagger, name = r._load_tagger(self.fake_mecab())
        self.assertEqual(name, 'unidic_lite')

    def test_every_failure_is_named(self):
        with self.modules(), self.assertRaises(RuntimeError) as context:
            r._load_tagger(self.fake_mecab(broken=(self.full, self.lite)))
        self.assertIn('unidic: Failed initializing MeCab', str(context.exception))
        self.assertIn('unidic_lite: Failed initializing MeCab', str(context.exception))


def _name_feature(surface, reading, kind='姓'):
    """A UniDic person-name row (pos3 人名) built from the shared helper."""
    fields = next(csv.reader([_feature(surface, reading, '名詞', '固有名詞', goshu='固')]))
    fields[2:4] = ['人名', kind]
    output = io.StringIO()
    csv.writer(output, lineterminator='').writerow(fields)
    return output.getvalue()


class CompoundJoinTests(unittest.TestCase):
    """Item 7 of the 2026-10 review: prefixes and rendaku join their compound."""

    def setUp(self):
        for name in ('_TITLE_OVERRIDES', '_PHRASE_OVERRIDES', '_LOANWORDS_MAP'):
            context = patch.object(r, name, {})
            context.start()
            self.addCleanup(context.stop)

    def convert(self, rows):
        text = ''.join(surface for surface, _ in rows)
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab({text: rows})):
            return r.to_romaji(text)

    def test_prefix_joins_the_word_it_modifies(self):
        cases = [
            ([('大', _feature('大', 'ダイ', '接頭辞', '*', goshu='漢')),
              ('妖精', _feature('妖精', 'ヨウセイ', goshu='漢'))], 'Daiyousei'),
            ([('無', _feature('無', 'ム', '接頭辞', '*', goshu='漢')),
              ('条件', _feature('条件', 'ジョウケン', goshu='漢'))], 'Mujouken'),
            ([('超', _feature('超', 'チョウ', '接頭辞', '*', goshu='漢')),
              ('新星', _feature('新星', 'シンセイ', goshu='漢')),
              ('世界', _feature('世界', 'セカイ', goshu='漢'))], 'Choushinsei Sekai'),
            # The syllabic-n apostrophe still applies inside the joined word.
            ([('現', _feature('現', 'ゲン', '接頭辞', '*', goshu='漢')),
              ('夢', _feature('夢', 'ユメ'))], "Gen'yume"),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)

    def test_prefix_keeps_numerals_digits_and_lone_kana_apart(self):
        cases = [
            ([('第', _feature('第', 'ダイ', '接頭辞', '*', goshu='漢')),
              ('8', '名詞,数詞,*,*,*,*'),
              ('番', _feature('番', 'バン', '接尾辞', '名詞的', goshu='漢'))], 'Dai 8 Ban'),
            ([('第', _feature('第', 'ダイ', '接頭辞', '*', goshu='漢')),
              ('二', _feature('二', 'ニ', '名詞', '数詞', goshu='漢')),
              ('楽章', _feature('楽章', 'ガクショウ', goshu='漢'))], 'Dai Ni Gakushou'),
            # A lone kana after a prefix is more likely a broken name than
            # its stem (新ちゆり).
            ([('新', _feature('新', 'シン', '接頭辞', '*', goshu='漢')),
              ('ち', _feature('ち', 'チ')),
              ('ゆり', _feature('ゆり', 'ユリ'))], 'Shin Chi Yuri'),
            ([('新', _feature('新', 'シン', '接頭辞', '*', goshu='漢')),
              ('鄉', '名詞,普通名詞,*,*,*,*')], 'Shin 鄉'),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)

    def test_rendaku_marks_a_compound(self):
        cases = [
            ([('無縁', _feature('無縁', 'ムエン', '形状詞', '一般', goshu='漢')),
              ('塚', _feature('塚', 'ヅカ', lemma='ツカ'))], 'Muenzuka'),
            ([('三途', _feature('三途', 'サンズ', goshu='漢')),
              ('川', _feature('川', 'ガワ', lemma='カワ'))], 'Sanzugawa'),
            ([('ほたる', _feature('ほたる', 'ホタル')),
              ('囃子', _feature('囃子', 'バヤシ', lemma='ハヤシ'))], 'Hotarubayashi'),
            ([('水', _feature('水', 'ミズ')),
              ('不足', _feature('不足', 'ブソク', goshu='漢', lemma='フソク'))], 'Mizubusoku'),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)

    def test_voicing_that_is_not_rendaku_does_not_join(self):
        cases = [
            # A lemma that is voiced in its own right is no evidence.
            ([('夢', _feature('夢', 'ユメ')),
              ('現', _feature('現', 'ゲン', goshu='漢'))], 'Yume Gen'),
            # A different lemma with a voiced first kana is not a reading of
            # the same word.
            ([('夢', _feature('夢', 'ユメ')),
              ('像', _feature('像', 'ゾウ', goshu='漢', lemma='ソウゾウ'))], 'Yume Zou'),
            # Only nominal elements bind; a particle boundary stays.
            ([('無縁', _feature('無縁', 'ムエン', '形状詞', '一般', goshu='漢')),
              ('の', _feature('の', 'ノ', '助詞', '格助詞')),
              ('塚', _feature('塚', 'ヅカ', lemma='ツカ'))], 'Muen no Zuka'),
        ]
        for rows, expected in cases:
            with self.subTest(text=''.join(s for s, _ in rows)):
                self.assertEqual(self.convert(rows), expected)
        token = r._Token('塚', '塚', 'ヅカ', '名詞', '普通名詞', '和', 'ツカ', 0, 1)
        self.assertTrue(r._rendaku_bound(token))
        self.assertFalse(r._rendaku_bound(replace(token, reading='ヅカイ')))
        self.assertFalse(r._rendaku_bound(replace(token, reading='', lemma_reading='')))


class SurnameReadingTests(unittest.TestCase):
    """Item 5 of the 2026-10 review, limited to the 東方 pattern."""

    def test_fake_tagger_without_a_lattice_keeps_the_path_reading(self):
        rows = [('東方', _name_feature('東方', 'トウボウ')),
                ('翠', _feature('翠', 'ミドリ')),
                ('夢想', _feature('夢想', 'ムソウ', goshu='漢'))]
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab({'東方翠夢想': rows})), \
                patch.multiple(r, _TITLE_OVERRIDES={}, _PHRASE_OVERRIDES={}, _LOANWORDS_MAP={}):
            self.assertEqual(r.to_romaji('東方翠夢想'), 'Toubou Midori Musou')

    @unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
    def test_touhou_reads_as_the_noun_without_overrides(self):
        for title in ('東方翠夢想', '東方萃夢創', '東方永夜抄', '東方千年紀'):
            with self.subTest(title=title):
                self.assertTrue(r.to_romaji(title, use_overrides=False).startswith('Touhou '))

    @unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
    def test_names_that_are_the_frequent_word_keep_their_reading(self):
        cases = {'西行桜': 'Saigyou Sakura', '望月の夢路': 'Mochizuki no Yumeji',
                 '千秋恋歌': 'Chiaki Renka', '山中湖': 'Yamanakako'}
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(r.to_romaji(title, use_overrides=False), expected)

    @unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
    def test_cost_margin_is_what_protects_ambiguous_surnames(self):
        title = '涼風爽夏'
        self.assertTrue(r.to_romaji(title, use_overrides=False).startswith('Suzukaze'))
        with patch.object(r, '_COMMON_NOUN_COST_MARGIN', 0):
            self.assertTrue(r.to_romaji(title, use_overrides=False).startswith('Ryoufuu'))


class ExplainTests(unittest.TestCase):
    """Item 11 of the 2026-10 review: per-word sources and review reasons."""

    def setUp(self):
        for name in ('_TITLE_OVERRIDES', '_PHRASE_OVERRIDES', '_LOANWORDS_MAP'):
            context = patch.object(r, name, {})
            context.start()
            self.addCleanup(context.stop)

    def explain(self, rows, loanwords=None, text=None):
        text = text or ''.join(surface for surface, _ in rows)
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab({text: rows})), \
                patch.object(r, '_LOANWORDS_MAP', loanwords or {}):
            return r.explain_romaji(text)

    def test_sources_flags_and_reasons(self):
        rows = [('夢', _feature('夢', 'ユメ')),
                ('鄉', '名詞,普通名詞,*,*,*,*'),
                ('の', _feature('の', 'ノ', '助詞', '格助詞')),
                ('セプテット', _feature('セプテット', 'セプテット', goshu='外'))]
        explained = self.explain(rows, {'seputetto': 'Septette'})
        self.assertEqual(explained['romaji'], 'Yume 鄉 no Septette')
        self.assertEqual([w['source'] for w in explained['words']],
                         ['dictionary', 'dictionary', 'dictionary', 'loanword'])
        self.assertEqual([w['written'] for w in explained['words']], ['夢', '鄉', 'の', 'セプテット'])
        self.assertEqual(explained['words'][1]['flags'], ['guessed'])
        self.assertEqual(explained['words'][3]['romaji'], 'Septette')
        self.assertEqual(explained['review'], ['reading of 鄉 guessed outside the dictionary'])

    def test_kana_outside_the_dictionary_is_noted_but_not_reviewed(self):
        rows = [('オンバシラテクノ', '名詞,普通名詞,*,*,*,*')]
        explained = self.explain(rows)
        self.assertEqual(explained['words'][0]['flags'], ['unknown'])
        self.assertEqual(explained['review'], [])
        # Track numbers and other non-Japanese unknowns carry no flag at all.
        rows = [('01', '名詞,数詞,*,*,*,*'), ('幕', _feature('幕', 'マク', goshu='漢'))]
        self.assertEqual([w['flags'] for w in self.explain(rows)['words']], [[], []])

    def test_kanji_by_kanji_runs_are_flagged_but_numerals_are_not(self):
        rows = [('比', _feature('比', 'ヒ', goshu='漢')),
                ('那', _feature('那', 'アノ', '連体詞', '*')),
                ('名', _feature('名', 'メイ', goshu='漢')),
                ('居', _feature('居', 'キョ', goshu='漢')),
                ('天子', _feature('天子', 'テンシ', goshu='漢'))]
        explained = self.explain(rows)
        self.assertEqual([w['flags'] for w in explained['words']],
                         [['fragments']] * 4 + [[]])
        self.assertEqual(explained['review'], ['比那名居 read kanji by kanji (Hi Ano Mei Kyo)'])
        rows = [('明治', _feature('明治', 'メイジ', goshu='漢')),
                ('十', _feature('十', 'ジュウ', '名詞', '数詞', goshu='漢')),
                ('七', _feature('七', 'シチ', '名詞', '数詞', goshu='漢')),
                ('年', _feature('年', 'ネン', '接尾辞', '名詞的', goshu='漢'))]
        self.assertEqual(self.explain(rows)['review'], [])
        # Two lone kanji are an ordinary compound split, not a run.
        rows = [('紅', _feature('紅', 'クレナイ')), ('霧', _feature('霧', 'キリ')),
                ('異変', _feature('異変', 'イヘン', goshu='漢'))]
        self.assertEqual(self.explain(rows)['review'], [])

    def test_reviewed_text_is_trusted(self):
        rows = [('比', _feature('比', 'ヒ', goshu='漢')),
                ('那', _feature('那', 'アノ', '連体詞', '*')),
                ('名居', _feature('名居', 'メイキョ', goshu='漢'))]
        with patch.object(r, '_TITLE_OVERRIDES', {'比那名居': 'Hinanawi'}):
            explained = self.explain(rows)
        self.assertEqual(explained['romaji'], 'Hinanawi')
        self.assertEqual(explained['words'], [{'written': '比那名居', 'romaji': 'Hinanawi',
                                               'reading': '', 'source': 'title', 'flags': []}])
        self.assertEqual(explained['review'], [])

    def test_romanize_file_and_logs_carry_the_review(self):
        rows = [('比', _feature('比', 'ヒ', goshu='漢')),
                ('那', _feature('那', 'アノ', '連体詞', '*')),
                ('名', _feature('名', 'メイ', goshu='漢')),
                ('居', _feature('居', 'キョ', goshu='漢'))]
        writes = []
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab({'比那名居': rows})), \
                patch.object(r, 'read_title', return_value='比那名居'), \
                patch.object(r, 'read_titlesort', return_value=None), \
                patch.object(r, 'set_titlesort', side_effect=lambda *a, **k: writes.append(a)):
            result = r.romanize_file('/x/01.flac')
            self.assertEqual(result['status'], 'romanized')
            self.assertEqual(result['review'], ['比那名居 read kanji by kanji (Hi Ano Mei Kyo)'])
            lines = []
            summary = r.romanize_files([{'path': '/x/01.flac', 'filename': '01.flac',
                                         'disc': 1, 'number': 1}], log=lines.append)
        self.assertEqual(summary['romanized'], 1)
        self.assertEqual(summary['review'], 1)
        self.assertTrue(any('review: 比那名居 read kanji by kanji' in line for line in lines))
        self.assertEqual(len(writes), 2)

    def test_real_dictionary_examples(self):
        # Also run unpatched by ExplainIntegrationTests; here the reviewed
        # tables are blank, so 西行寺 is only exempt when its loanword exists.
        if not r.MECAB_AVAILABLE:
            self.skipTest('MeCab/UniDic required')
        if r._LOANWORDS_MAP:
            self.assertEqual(r.explain_romaji('西行寺幽々子')['review'], [])
        self.assertEqual(r.explain_romaji('3つの願い')['words'][0]['source'], 'counter')
        self.assertTrue(r.explain_romaji('蓮の華')['review'][0].startswith("蓮 read as a person's name"))
        self.assertEqual(r.explain_romaji('比那名居天子')['review'],
                         ['比那名居 read kanji by kanji (Hi Ano Mei Kyo)'])
        self.assertEqual(r.explain_romaji('幻想龘')['review'],
                         ['reading of 龘 guessed outside the dictionary'])
        # The 東方 substitution clears the name flag it resolved.
        first = r.explain_romaji('東方千年紀', use_overrides=False)['words'][0]
        self.assertEqual((first['written'], first['romaji'], first['flags']), ('東方', 'Touhou', []))


@unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
class ExplainIntegrationTests(unittest.TestCase):
    """explain_romaji with the real dictionary and the shipped tables."""

    def test_real_dictionary_examples(self):
        ExplainTests.test_real_dictionary_examples(self)


class VariantKanjiTests(unittest.TestCase):
    """Item 6 of the 2026-10 review: old-form kanji analyzed through modern forms."""

    def setUp(self):
        for name in ('_TITLE_OVERRIDES', '_PHRASE_OVERRIDES', '_LOANWORDS_MAP'):
            context = patch.object(r, name, {})
            context.start()
            self.addCleanup(context.stop)

    def convert(self, rows_by_text):
        text = next(iter(rows_by_text))
        with patch.object(r, 'MECAB_AVAILABLE', True), \
                patch.object(r, '_mecab', _FakeMeCab(rows_by_text)):
            return r.to_romaji(text)

    def test_mapping_is_one_to_one_and_leaves_ryuu_alone(self):
        self.assertEqual(len(r._KANJI_VARIANT_PAIRS) % 2, 0)
        self.assertNotIn(ord('龍'), r._KANJI_VARIANTS)
        self.assertNotIn(ord('蔷'), r._KANJI_VARIANTS)
        self.assertEqual('戀體鄉'.translate(r._KANJI_VARIANTS), '恋体郷')
        for old, new in r._KANJI_VARIANTS.items():
            self.assertEqual(len(new), 1, chr(old))

    def test_modern_form_is_used_when_it_resolves_an_unknown(self):
        rows = {'戀': [('戀', '名詞,普通名詞,*,*,*,*')],
                '恋': [('恋', _feature('恋', 'コイ'))]}
        self.assertEqual(self.convert(rows), 'Koi')

    def test_modern_form_is_used_when_it_parses_into_fewer_words(self):
        rows = {'天體': [('天', _feature('天', 'テン', goshu='漢')),
                       ('體', _feature('體', 'テイ', goshu='漢'))],
                '天体': [('天体', _feature('天体', 'テンタイ', goshu='漢'))]}
        self.assertEqual(self.convert(rows), 'Tentai')

    def test_old_form_is_kept_when_the_parse_does_not_improve(self):
        rows = {'櫻花': [('櫻', _feature('櫻', 'サクラ')), ('花', _feature('花', 'ハナ'))],
                '桜花': [('桜', _feature('桜', 'サクラ')), ('花', _feature('花', 'ハナ'))]}
        self.assertEqual(self.convert(rows), 'Sakura Hana')
        rows = {'醉月': [('醉月', _feature('醉月', 'スイゲツ', goshu='漢'))],
                '酔月': [('酔', _feature('酔', 'ヨイ')), ('月', _feature('月', 'ツキ'))]}
        self.assertEqual(self.convert(rows), 'Suigetsu')

    @unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
    def test_real_dictionary_examples(self):
        cases = {'天體觀測': 'Tentai Kansoku', '亂れ咲き': 'Midaresaki', '神祕': 'Shinpi',
                 '幻想鄉': 'Gensoukyou', '眞紅': 'Shinku', '蓬莱傳説': 'Hourai Densetsu',
                 # the gate keeps a known old-form word's own split
                 '櫻月夜': 'Sakura Tsukiyo', '蒼龍': 'Souryuu',
                 '戀獄タランテラ': 'Ren Goku Tarantera'}
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(r.to_romaji(title, use_overrides=False), expected)
        self.assertFalse(r._has_unresolved_output(r.to_romaji('幻想鄉'), '幻想鄉'))


class DashMarkTests(unittest.TestCase):
    """Item 10 of the 2026-10 review: a ー that can only be a dash."""

    def test_dash_positions(self):
        cases = {
            '夢 ー終焉ー': '夢 -終焉-', 'ー終焉ー': '-終焉-', '夢ー終焉ー': '夢-終焉-',
            '鋼琴符 ー 双鬼': '鋼琴符 - 双鬼', '-雷音ーBEAT': '-雷音-BEAT', '昴ーsubaru-': '昴-subaru-',
            '空の境界The Horizonー': '空の境界The Horizon-',
            # long vowels and lengthening are untouched
            'スーパー図書館': 'スーパー図書館', 'セーラー服': 'セーラー服', 'らーめん': 'らーめん',
            '夢ーー': '夢ーー', 'ああー': 'ああー', '限界突破ー！！': '限界突破ー！！',
            # kanji + ー + kana stays ambiguous
            '子守唄ーユカウラー': '子守唄ーユカウラー',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(r._dash_long_vowel_marks(text), expected)

    @unittest.skipUnless(r.MECAB_AVAILABLE, 'MeCab/UniDic required')
    def test_real_dictionary_examples(self):
        cases = {'夢 ー終焉ー': 'Yume -Shuuen-', 'ー終焉ー': '-Shuuen-',
                 '鋼琴符 ー 双鬼': 'Koukinfu - Souoni', '夢ーー': 'Yumeee',
                 '宇宙最後まで限界突破ー！！': 'Uchuu Saigo made Genkai Toppaa!!'}
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(r.to_romaji(title, use_overrides=False), expected)
                self.assertFalse(r._has_unresolved_output(r.to_romaji(title), title))
        ambiguous = '子守唄ーユカウラー'
        self.assertTrue(r._has_unresolved_output(r.to_romaji(ambiguous), ambiguous))
