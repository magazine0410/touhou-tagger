#!/usr/bin/env python3
"""
japanese_romanizer.py — Romanise Japanese song titles to the `titlesort`
tag of music files.

Adapted from an earlier Japanese title-to-romaji implementation.  Uses MeCab
and UniDic for word segmentation and a built-in
Hepburn katakana table for romanisation.  Optionally falls back to
pykakasi for rare kanji that UniDic can't read.

Designed to:
  * be run standalone from the command line,
  * be imported by ``touhou_tagger.py`` so its GUI/CLI can auto-romanise
    titles in the same pass that writes ``grouping`` from a wiki source.

By default, the romaniser will NOT overwrite an existing ``titlesort``
tag — it shows what is currently there and what would be written, and
skips.  Pass ``--force-titlesort`` (CLI) or tick "Force overwrite" (GUI)
to replace existing values.

Dependencies (required):
    pip install --user mecab-python3 unidic mutagen
    python -m unidic download
    # MeCab itself comes from your OS package manager, e.g.:
    sudo dnf install mecab mecab-devel      # Fedora
    sudo apt install mecab libmecab-dev     # Debian/Ubuntu
    yay -S mecab                            # Arch (AUR)

Optional (recommended for better kanji coverage):
    pip install --user pykakasi

Companion data file (kept separate so the loanword / phrase / title
override tables don't clutter this script):
    japanese_romanizer_data.py
For backwards compatibility this script also accepts the legacy data-module
name ``japanese_title_to_romaji_data.py``.

Usage:
    # Romanise all music files in one or more album folders:
    python source/japanese_romanizer.py "path/to/Album1" "path/to/Album2"

    # Dry run (don't write, just show what would happen):
    python source/japanese_romanizer.py "path/to/Album1" --dry-run

    # Overwrite existing titlesort tags:
    python source/japanese_romanizer.py "path/to/Album1" --force-titlesort
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import os
import re
import sys
import unicodedata

import mutagen
from mutagen.id3 import ID3, TSOT, ID3NoHeaderError
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus

__all__ = [
    # Public API
    "is_ready",
    "get_install_hint",
    "has_japanese",
    "to_romaji",
    # Tag I/O
    "read_title",
    "read_titlesort",
    "set_titlesort",
    # Per-file / per-album processing
    "romanize_file",
    "romanize_files",
    "process_album_romanize",
    # File scanning (re-exported so touhou_tagger.py can share if it wants)
    "SUPPORTED_EXTENSIONS",
]

# ---------------------------------------------------------------------------
# Optional dependency probing
# ---------------------------------------------------------------------------
_MECAB_IMPORT_ERROR: str | None = None
try:
    import MeCab  # type: ignore
    import unidic  # type: ignore
    _mecab = MeCab.Tagger(f"-d {unidic.DICDIR}")
    MECAB_AVAILABLE = True
except Exception as _exc:  # ImportError, RuntimeError, etc.
    MECAB_AVAILABLE = False
    _mecab = None
    _MECAB_IMPORT_ERROR = str(_exc)

try:
    import pykakasi  # type: ignore
    _kks = pykakasi.kakasi()
    PYKAKASI_AVAILABLE = True
except Exception:
    PYKAKASI_AVAILABLE = False
    _kks = None

# ---------------------------------------------------------------------------
# Shared data (loanwords, phrase overrides, title overrides)
# ---------------------------------------------------------------------------
# Try the new module name first, then fall back to the legacy filename so
# existing setups keep working without renaming.
_DATA_LOAD_ERROR: str | None = None
try:
    from japanese_romanizer_data import (  # type: ignore
        _LOANWORDS, _TITLE_OVERRIDES, _PHRASE_OVERRIDES,
    )
except (ImportError, SyntaxError):
    try:
        from japanese_title_to_romaji_data import (  # type: ignore
            _LOANWORDS, _TITLE_OVERRIDES, _PHRASE_OVERRIDES,
        )
    except (ImportError, SyntaxError) as exc:
        _DATA_LOAD_ERROR = str(exc)
        _LOANWORDS: dict[str, str] = {}
        _TITLE_OVERRIDES: dict[str, str] = {}
        _PHRASE_OVERRIDES: dict[tuple, str] = {}

_LOANWORDS_MAP = {k.strip(): v for k, v in _LOANWORDS.items()}

# Optional in older companion data files.
try:
    from japanese_romanizer_data import _TITLE_SPELLING_ALIASES
except (ImportError, SyntaxError):
    _TITLE_SPELLING_ALIASES = {}

# Explicit exclusions are independent of spelling aliases.
try:
    from japanese_romanizer_data import _NON_JAPANESE_DIRECTORIES, _NON_JAPANESE_TITLES
except (ImportError, SyntaxError):
    _NON_JAPANESE_DIRECTORIES = set()
    _NON_JAPANESE_TITLES = set()

# Mixed-language releases need exclusions scoped to both release and title.
# Keep this optional independently, for compatibility with older data files.
try:
    from japanese_romanizer_data import _NON_JAPANESE_RELEASE_TITLES
except (ImportError, SyntaxError):
    _NON_JAPANESE_RELEASE_TITLES = {}

_NON_JAPANESE_RELEASE_TITLES_MAP = {
    tuple(unicodedata.normalize("NFKC", part).casefold() for part in release):
        frozenset(unicodedata.normalize("NFKC", title) for title in titles)
    for release, titles in _NON_JAPANESE_RELEASE_TITLES.items()
}

# ---------------------------------------------------------------------------
# Constants used by the file-scanning helpers
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".ogg", ".m4a", ".opus"}
DISC_DIR_RE = re.compile(r"(?i)^disc\s*(\d+)$")

# ---------------------------------------------------------------------------
# Public readiness API (used by touhou_tagger.py to decide whether to
# show the Romanization tab and to enable auto-romanisation.)
# ---------------------------------------------------------------------------
def is_ready() -> bool:
    """True when MeCab + UniDic are importable.  pykakasi is optional."""
    return MECAB_AVAILABLE


def get_install_hint() -> str:
    """Human-readable hint about how to enable the romaniser, for use
    in tooltips / status bars when ``is_ready()`` is False."""
    if MECAB_AVAILABLE:
        if not PYKAKASI_AVAILABLE:
            return (
                "Romaniser ready.  (Optional: pip install --user pykakasi "
                "for better rare-kanji coverage.)"
            )
        return "Romaniser ready."
    return (
        "Romaniser disabled — MeCab / UniDic not importable.\n"
        "Install the MeCab library with your OS package manager, then the\n"
        "Python bindings and dictionary:\n"
        "    Fedora:        sudo dnf install mecab mecab-devel\n"
        "    Debian/Ubuntu: sudo apt install mecab libmecab-dev\n"
        "    Arch (AUR):    yay -S mecab\n"
        "    macOS (brew):  brew install mecab\n"
        "    pip install --user mecab-python3 unidic mutagen\n"
        "    python -m unidic download\n"
        f"Last import error: {_MECAB_IMPORT_ERROR}"
    )

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------
# Share coverage between detection, segmentation and the reading fallback.
# The supplementary ranges include rare name characters such as 𠮷.
_KANJI_CHARS = (
    r'\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF'
    r'\U00020000-\U0002FA1F\U00030000-\U0003347F'
    r'\u3005-\u3007\u303B'
)
_KANA_CHARS = (
    r'\u3041-\u3096\u3099-\u309F\u30A1-\u30FA\u30FC-\u30FF'
    r'\u31F0-\u31FF\uFF66-\uFF9F\U0001B000-\U0001B16F'
)
_JP_CHARS = _KANJI_CHARS + _KANA_CHARS
_JP_RE = re.compile(f'[{_JP_CHARS}]')
_KANJI_RE = re.compile(f'[{_KANJI_CHARS}]')
_KANA_ONLY_RE = re.compile(f'[{_KANA_CHARS}]+\\Z')


def has_japanese(text: str) -> bool:
    """True if the text contains any hiragana, katakana, kanji, or 々."""
    return bool(_JP_RE.search(text))


def _get_reading(feature: str) -> str | None:
    """Read the surface kana, preserving contractions and inflections.

    UniDic 2.2+/3.x: kana=20, pron=9, lForm=6.  Features such as
    fConType contain quoted commas, so splitting on ',' shifts kana's index.
    Older dictionaries without kana can still supply surface pronunciation;
    the lemma reading is only a last resort.
    """
    parts = next(csv.reader([feature]))
    for index in (20, 9, 6):
        if len(parts) > index and parts[index] not in ("*", ""):
            return parts[index]
    return None

# ---------------------------------------------------------------------------
# Katakana okurigana normalisation
# ---------------------------------------------------------------------------
# Exempt ヶ (U+30F6) and ヵ (U+30F5) — these function as grammatical
# particles (ka/ga/ko) in counter expressions and place names (e.g.
# 一ヶ月, 関ヶ原) and should not be converted to hiragana.
_KATAKANA_OKURIGANA_EXEMPT = frozenset({"ヶ", "ヵ"})


def _is_katakana_adjacent(ch: str) -> bool:
    """Return True if `ch` is a katakana letter or long vowel mark (ー),
    i.e. a character that would form part of a katakana word run."""
    cp = ord(ch)
    return (0x30A1 <= cp <= 0x30F6) or cp == 0x30FC  # ァ-ヶ or ー


def _normalize_katakana_okurigana(text: str) -> str:
    """Convert isolated katakana following kanji back to hiragana.

    Song titles sometimes use katakana for okurigana or particles as a
    stylistic choice (e.g. 永イ夜ハ空ヲ歩キ instead of 永い夜は空を歩き).
    MeCab expects hiragana okurigana and cannot correctly tokenise these
    titles.  This function detects katakana characters that are *not*
    adjacent to other katakana and immediately follow kanji.  Standalone
    kana names (ハとヘ) and foreign-word runs retain their original spelling.

    ヶ and ヵ are exempted because they appear as single katakana between
    kanji in standard orthography (e.g. 一ヶ月, 関ヶ原).
    """
    result = list(text)
    for i, ch in enumerate(result):
        cp = ord(ch)
        # Only consider convertible katakana (ァ-ヶ, U+30A1-U+30F6)
        if not (0x30A1 <= cp <= 0x30F6):
            continue
        if ch in _KATAKANA_OKURIGANA_EXEMPT:
            continue
        prev_kata = i > 0 and _is_katakana_adjacent(result[i - 1])
        next_kata = (
            i + 1 < len(result) and _is_katakana_adjacent(result[i + 1])
        )
        follows_kanji = i > 0 and bool(_KANJI_RE.fullmatch(text[i - 1]))
        if follows_kanji and not prev_kata and not next_kata:
            result[i] = chr(cp - 0x60)  # katakana → hiragana offset
    return "".join(result)

# ---------------------------------------------------------------------------
# Hiragana long-vowel-mark normalisation
# ---------------------------------------------------------------------------
_HIRAGANA_LONG_VOWEL_RE = re.compile(
    r'[\u3041-\u3096ー]*ー[\u3041-\u3096ー]*'
)


def _normalize_hiragana_long_vowels(text: str) -> str:
    """Choose a less fragmented analysis without changing the output spelling.

    ー also occurs in native words and beside particles.  Try ordinary vowel
    spellings and dictionary-confirmed foreign-word spans, rather than turning
    an entire hiragana sentence into katakana.  All alternatives have the same
    length; the tokenizer can recover the original kana for the final reading.
    Work is bounded for unusually long runs, and ties retain the original.
    """
    def normalize_run(match: re.Match[str]) -> str:
        run = match.group()
        if len(run) > 64 or not any("ぁ" <= ch <= "ゖ" for ch in run):
            return run
        cache: dict[str, list[_Token]] = {}

        def analyze(candidate: str) -> list[_Token]:
            if candidate not in cache:
                cache[candidate] = _read_tokens(candidate)
            return cache[candidate]

        def score(candidate: str) -> tuple[int, int, int]:
            tokens = analyze(candidate)
            broken = sum(len(t.surface) for t in tokens if t.unknown or
                         all(ch in "ーぁぃぅぇぉゃゅょ" for ch in t.surface))
            return broken, len(tokens), sum(a != b for a, b in zip(run, candidate))

        def expand(candidate: str, alternate: bool) -> str:
            out = []
            for i, ch in enumerate(candidate):
                if ch == "ー" and i and ("ぁ" <= candidate[i - 1] <= "ゖ"
                                         or candidate[i - 1] == "ー"):
                    previous = _kana_to_romaji(candidate[:i])
                    vowel = previous[-1:] if previous else ""
                    choices = {"a": "あ", "i": "い", "u": "う",
                               "e": "え" if alternate else "い",
                               "o": "お" if alternate else "う"}
                    ch = choices.get(vowel, ch)
                out.append(ch)
            return "".join(out)

        original_tokens = analyze(run)
        if len(original_tokens) == 1 and not original_tokens[0].unknown:
            return run
        candidates = [run, expand(run, False), expand(run, True)]

        # MeCab can mark パーティーハ as one unknown word.  Check spans at
        # the original token boundaries so パーティー can be recognized while
        # は remains a particle.  Only a single known foreign word qualifies.
        starts = {0, *(t.start for t in original_tokens)}
        ends = {len(run), *(t.end for t in original_tokens)}
        foreign_spans = []
        for start in sorted(starts):
            for end in sorted(ends, reverse=True):
                source = run[start:end]
                if len(source) < 2 or "ー" not in source:
                    continue
                kata = _to_katakana(source)
                tokens = analyze(kata)
                if (len(tokens) == 1 and not tokens[0].unknown
                        and tokens[0].goshu == "外"):
                    foreign_spans.append((start, end, kata))
        replaced: set[int] = set()
        foreign = list(run)
        for start, end, kata in sorted(foreign_spans,
                                       key=lambda span: span[0] - span[1]):
            if not replaced.intersection(range(start, end)):
                foreign[start:end] = kata
                replaced.update(range(start, end))
        candidates.append("".join(foreign))
        return min(candidates, key=score)

    return _HIRAGANA_LONG_VOWEL_RE.sub(normalize_run, text)

# ---------------------------------------------------------------------------
# Direct katakana-to-Hepburn romaji table
# ---------------------------------------------------------------------------
# Match the longest combination first, including three-character spellings.
_KATAKANA_ROMAJI: dict[str, str] = {
    # --- Digraphs (consonant + small ャ/ュ/ョ) ---
    "キャ": "kya", "キュ": "kyu", "キョ": "kyo",
    "シャ": "sha", "シュ": "shu", "ショ": "sho",
    "チャ": "cha", "チュ": "chu", "チョ": "cho",
    "ニャ": "nya", "ニュ": "nyu", "ニョ": "nyo",
    "ヒャ": "hya", "ヒュ": "hyu", "ヒョ": "hyo",
    "ミャ": "mya", "ミュ": "myu", "ミョ": "myo",
    "リャ": "rya", "リュ": "ryu", "リョ": "ryo",
    "ギャ": "gya", "ギュ": "gyu", "ギョ": "gyo",
    "ジャ": "ja",  "ジュ": "ju",  "ジョ": "jo",
    "ヂャ": "ja",  "ヂュ": "ju",  "ヂョ": "jo",
    "ビャ": "bya", "ビュ": "byu", "ビョ": "byo",
    "ピャ": "pya", "ピュ": "pyu", "ピョ": "pyo",
    # --- Extended katakana for foreign sounds ---
    "ティ": "ti",  "ディ": "di",
    "トゥ": "tu",  "ドゥ": "du",
    "ツァ": "tsa", "ツィ": "tsi", "ツェ": "tse", "ツォ": "tso",
    "ファ": "fa",  "フィ": "fi",  "フェ": "fe",  "フォ": "fo", "フュ": "fyu",
    "ウィ": "wi",  "ウェ": "we",  "ウォ": "wo",
    "ヴァ": "va",  "ヴィ": "vi",  "ヴェ": "ve",  "ヴォ": "vo", "ヴュ": "vyu",
    "シェ": "she", "ジェ": "je",  "チェ": "che",
    "テュ": "tyu", "デュ": "dyu",
    "イェ": "ye",
    "クヮ": "kwa", "グヮ": "gwa",
    "クァ": "kwa", "クィ": "kwi", "クェ": "kwe", "クォ": "kwo",
    "グァ": "gwa", "グィ": "gwi", "グェ": "gwe", "グォ": "gwo",
    "スィ": "si", "ズィ": "zi",
    "フャ": "fya", "フョ": "fyo",
    "フィャ": "fya", "フィュ": "fyu", "フィョ": "fyo",
    "ティャ": "tya", "ティュ": "tyu", "ティョ": "tyo",
    "ディャ": "dya", "ディュ": "dyu", "ディョ": "dyo",
    "ヴャ": "vya", "ヴョ": "vyo",
    "ヴィャ": "vya", "ヴィュ": "vyu", "ヴィョ": "vyo",
    "ヷ": "va", "ヸ": "vi", "ヹ": "ve", "ヺ": "vo",
    # --- Basic katakana ---
    "ア": "a",  "イ": "i",  "ウ": "u",  "エ": "e",  "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "サ": "sa", "シ": "shi","ス": "su", "セ": "se", "ソ": "so",
    "タ": "ta", "チ": "chi","ツ": "tsu","テ": "te", "ト": "to",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya",             "ユ": "yu",             "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa",                                     "ヲ": "o",
    "ヰ": "i",              "ヱ": "e",   # archaic wi/we → modern i/e (consistent with ヲ → o)
    "ン": "n",
    # --- Dakuten ---
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    # --- Handakuten ---
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    # --- ヴ standalone ---
    "ヴ": "vu",
    # --- Small kana (standalone, not part of a digraph) ---
    "ァ": "a",  "ィ": "i",  "ゥ": "u",  "ェ": "e",  "ォ": "o",
    "ッ": "",   # gemination is handled at token level
    "ャ": "ya", "ュ": "yu", "ョ": "yo",
    "ヮ": "wa",
}

# Maps trailing romaji to its vowel, for extending with ー.
_TRAILING_VOWEL: dict[str, str] = {}
for _r in _KATAKANA_ROMAJI.values():
    if _r and _r[-1] in "aiueo":
        _TRAILING_VOWEL[_r] = _r[-1]
del _r
_KANA_MATCH_LENGTHS = tuple(sorted(
    {len(k) for k in _KATAKANA_ROMAJI}, reverse=True,
))


def _to_katakana(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(chr(ord(ch) + 0x60) if "ぁ" <= ch <= "ゖ" else ch
                   for ch in text)


def _kana_syllable(kana: str, index: int) -> tuple[str, int]:
    for length in _KANA_MATCH_LENGTHS:
        syllable = kana[index:index + length]
        if len(syllable) == length and syllable in _KATAKANA_ROMAJI:
            return _KATAKANA_ROMAJI[syllable], length
    return "", 0


def _kana_to_romaji(kana: str) -> str:
    """Convert a katakana (or hiragana) string to Hepburn romaji."""
    kana = _to_katakana(kana)

    parts: list[str] = []
    last_vowel = ""
    i = 0
    while i < len(kana):
        ch = kana[i]
        if ch == "ー":
            # Long vowel mark: repeat the previous vowel
            if last_vowel:
                parts.append(last_vowel)
            else:
                parts.append(ch)  # no known vowel: do not silently lose text
            # last_vowel stays the same
        elif ch == "ッ":
            # Small tsu (gemination): look ahead to the next syllable
            # and prepend the appropriate consonant(s).
            next_romaji, _ = _kana_syllable(kana, i + 1)
            if next_romaji:
                geminated = _geminate_romaji(next_romaji)
                # Extract just the prepended consonant(s)
                prefix = geminated[:len(geminated) - len(next_romaji)]
                if prefix:
                    parts.append(prefix)
            # last_vowel stays the same (ッ has no vowel)
        elif ch == "ン":
            # Syllabic n: insert an apostrophe when the next syllable in
            # this reading begins with a vowel or y, to disambiguate
            # e.g. コンヤク → "kon'yaku" (not "konyaku" = こにゃく),
            # タンイ → "tan'i" (not "tani" = たに).
            next_romaji, _ = _kana_syllable(kana, i + 1)
            if next_romaji and next_romaji[0] in "aiueoy":
                parts.append("n'")
            else:
                parts.append("n")
            last_vowel = ""
        elif (syllable := _kana_syllable(kana, i))[1]:
            r, length = syllable
            parts.append(r)
            if r in _TRAILING_VOWEL:
                last_vowel = _TRAILING_VOWEL[r]
            elif r:
                last_vowel = ""
            i += length - 1
        else:
            # Unknown character (e.g. kanji with no reading) — pass through
            parts.append(ch)
            last_vowel = ""
        i += 1

    return "".join(parts)


def _pykakasi_fallback(surface: str) -> str:
    """Use pykakasi to romanise a surface form containing kanji that
    MeCab/UniDic could not provide a reading for.  Returns the surface
    unchanged if pykakasi is not installed."""
    return _kana_to_romaji(_pykakasi_reading(surface))


def _pykakasi_reading(surface: str) -> str:
    """Get fallback kana; all output goes through our shared Hepburn rules."""
    if not PYKAKASI_AVAILABLE:
        return surface
    parts = []
    offset = 0
    for token in _kks.convert(surface):
        original = token.get("orig", "")
        if not original:
            continue
        start = surface.find(original, offset)
        if start < 0:
            return surface
        # pykakasi can omit unsupported characters altogether.  Preserve
        # every unconverted gap rather than silently shortening a title.
        parts.extend((surface[offset:start], token.get("kana") or original))
        offset = start + len(original)
    parts.append(surface[offset:])
    return "".join(parts)


def _geminate_romaji(word: str) -> str:
    """Geminate the beginning of a lowercase Romaji word after a small tsu."""
    if word.startswith("ch"):
        return "tch" + word[2:]
    if word.startswith("sh"):
        return "ssh" + word[2:]
    if word.startswith("ts"):
        return "tts" + word[2:]
    if word.startswith("j"):
        return "jj" + word[1:]
    first = word[0] if word else ""
    if first and first in "bcdfghjklmnpqrstvwxz":
        return first + word
    return word

# ---------------------------------------------------------------------------
# MeCab-driven segment romanisation
# ---------------------------------------------------------------------------
@dataclass
class _Token:
    surface: str
    original: str
    reading: str
    pos: str
    sub_pos: str
    goshu: str
    lemma_reading: str
    start: int
    end: int
    unknown: bool = False
    conjugation_form: str = ""


def _read_tokens(text: str, original: str | None = None) -> list[_Token]:
    """Copy MeCab nodes while retaining written spans and surface readings."""
    original = text if original is None else original
    tokens: list[_Token] = []
    offset = 0
    node = _mecab.parseToNode(text)
    while node:
        surface = node.surface
        if surface:
            start = text.index(surface, offset)
            end = start + len(surface)
            offset = end
            parts = next(csv.reader([node.feature]))
            source = original[start:end]
            reading = _get_reading(node.feature)
            if _KANA_ONLY_RE.fullmatch(source):
                # Kana already specifies its reading, including expressive ー
                # and v/b distinctions that dictionary entries may normalize.
                reading = _to_katakana(source)
            elif surface == "々" and tokens:
                reading = tokens[-1].reading
            elif not reading:
                reading = (_pykakasi_reading(source)
                           if _KANJI_RE.search(source) else source)
            tokens.append(_Token(
                surface, source, reading, parts[0],
                parts[1] if len(parts) > 1 else "",
                parts[12] if len(parts) > 12 else "",
                parts[6] if len(parts) > 6 else "",
                start, end, node.stat == 1,
                conjugation_form=parts[5] if len(parts) > 5 else "",
            ))
        node = node.next
    return tokens


# Regular numeral/counter morphology belongs to the engine, independently of
# title/phrase overrides.  Limit the resolver to counters with reviewed rules.
# See the Japan Foundation's BTS00010 counter table (教科書を作ろう).
_COUNTERS = {
    "本": "ホン", "匹": "ヒキ", "杯": "ハイ", "個": "コ",
    "回": "カイ", "階": "カイ", "曲": "キョク", "冊": "サツ",
    "歳": "サイ", "人": "ニン", "月": "ガツ",
    "ヶ月": "カゲツ", "箇月": "カゲツ", "か月": "カゲツ", "カ月": "カゲツ",
}
_NUMERAL_CHARS = "0-9零〇一二三四五六七八九十百千万億"
_NUMBER_COUNTER_RE = re.compile(
    rf'(?<![{_NUMERAL_CHARS}.+−-])([{_NUMERAL_CHARS}]+)('
    + "|".join(sorted(_COUNTERS, key=len, reverse=True)) + ")"
)
_DIGIT_VALUES = dict(zip("零〇一二三四五六七八九", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)))
_DIGIT_READINGS = ("ゼロ", "イチ", "ニ", "サン", "ヨン", "ゴ", "ロク", "ナナ", "ハチ", "キュウ")


def _number_value(text: str) -> int | None:
    digits = "".join(str(_DIGIT_VALUES.get(ch, ch)) for ch in text)
    if digits.isascii() and digits.isdigit():
        # Leading zeros are identifiers; do not reinterpret their spelling.
        return int(digits) if len(digits) <= 12 and not (
            len(digits) > 1 and digits.startswith("0")) else None
    total = group = 0
    pending = ""
    last_small, last_large = 10000, 10**12
    for ch in digits:
        if ch in "0123456789":
            pending += ch
            if len(pending) > 4:
                return None
            continue
        unit = {"十": 10, "百": 100, "千": 1000, "万": 10000, "億": 10**8}.get(ch)
        if unit is None:
            return None
        if unit < 10000:
            if unit >= last_small:
                return None
            group += int(pending or "1") * unit
            last_small = unit
        else:
            if unit >= last_large:
                return None
            total += (group + int(pending or "0") or 1) * unit
            group, last_small, last_large = 0, 10000, unit
        pending = ""
    value = total + group + int(pending or "0")
    return value if value < 10**12 else None


def _number_reading(number: int) -> str:
    if number < 10:
        return _DIGIT_READINGS[number]
    for unit, kana in ((10**8, "オク"), (10000, "マン"), (1000, "セン"),
                       (100, "ヒャク"), (10, "ジュウ")):
        if number >= unit:
            count, remainder = divmod(number, unit)
            if unit == 1000 and count in (3, 8):
                head = {3: "サンゼン", 8: "ハッセン"}[count]
            elif unit == 100 and count in (3, 6, 8):
                head = {3: "サンビャク", 6: "ロッピャク", 8: "ハッピャク"}[count]
            else:
                head = ("" if count == 1 and unit < 10000 else _number_reading(count)) + kana
            return head + (_number_reading(remainder) if remainder else "")
    raise ValueError("Unsupported number")


def _counter_reading(number: int, counter: str) -> str | None:
    stem = _number_reading(number)
    tail = _COUNTERS[counter]
    if counter == "月":
        if not 1 <= number <= 12:
            return None
        stem = {4: "シ", 7: "シチ", 9: "ク"}.get(number, stem)
    elif counter == "人":
        if number in (1, 2):
            return {1: "ヒトリ", 2: "フタリ"}[number]
        if stem.endswith("ヨン"):
            stem = stem[:-2] + "ヨ"
    elif counter == "歳" and number == 20:
        return "ハタチ"
    elif tail[0] in "ホヒハカキコサ":
        # 1/8/10 before h/k/s; 6 and hundreds before h/k only.
        endings = ["イチ", "ハチ", "ジュウ"]
        if tail[0] in "ホヒハカキコ":
            endings += ["ロク", "ヒャク", "ビャク", "ピャク"]
        for ending in endings:
            if stem.endswith(ending):
                stem = stem[:-1] + "ッ"
                break
        if counter in ("本", "匹", "杯"):
            if stem.endswith("ッ"):
                tail = {"本": "ポン", "匹": "ピキ", "杯": "パイ"}[counter]
            elif stem.endswith(("サン", "セン", "ゼン", "マン")):
                tail = {"本": "ボン", "匹": "ビキ", "杯": "バイ"}[counter]
        elif counter == "階" and stem.endswith("サン"):
            tail = "ガイ"
    return stem + tail


def _number_counter_spans(segment: str, tokens: list[_Token]) -> dict[int, tuple[int, str]]:
    """Resolve complete token spans; never take 曲 out of 曲線, for example.

    Recognized counters are read as units, including Arabic-written 1人/2人.
    Standalone digits, version labels, decimals and unhandled units keep their
    spelling.  Phrase overrides are applied before these spans are consumed.
    """
    starts = {token.start: i for i, token in enumerate(tokens)}
    ends = {token.end: i + 1 for i, token in enumerate(tokens)}
    spans = {}
    for match in _NUMBER_COUNTER_RE.finditer(segment):
        if match.start() not in starts or match.end() not in ends:
            continue
        start, end = starts[match.start()], ends[match.end()]
        # 千曲 is also the place name Chikuma.  Keep dictionary-recognized
        # proper names and ordinal constructions (第一人者) out of counting.
        if any(t.sub_pos == "固有名詞" for t in tokens[start:end]):
            continue
        if start and tokens[start - 1].surface == "第":
            continue
        value = _number_value(match[1])
        if value is not None:
            reading = _counter_reading(value, match[2])
            if reading:
                spans[start] = end, reading
    return spans


@dataclass
class _RenderedWord:
    tokens: list[_Token]
    text: str
    reading: str
    opaque: bool = False  # a reviewed replacement is already romanized


def _loanword_match(tokens: list[_Token]) -> str | None:
    if any(t.pos == "助詞" for t in tokens):
        return None
    keys = [_kana_to_romaji("".join(t.reading for t in tokens)),
            "".join(_kana_to_romaji(t.reading) for t in tokens)]
    # Retain compatibility with foreign-word keys built from older UniDic
    # lemma spellings (e.g. ボヤージュ / ヴォヤージュ), without normalizing
    # native colloquial words such as あたし back into their lemmas.
    if all(t.goshu == "外" for t in tokens):
        keys.append("".join(_kana_to_romaji(t.lemma_reading) for t in tokens))
    for key in keys:
        if key.lower().strip() in _LOANWORDS_MAP:
            return _LOANWORDS_MAP[key.lower().strip()]
    return None


def _japanese_segment_to_romaji(
    segment: str, first_in_title: bool = False,
) -> str:
    """Analyze readings before applying replacements and word-boundary rules."""
    analysis = _normalize_hiragana_long_vowels(_normalize_katakana_okurigana(segment))
    tokens = [t for t in _read_tokens(analysis, segment) if t.surface != "・"]
    number_spans = _number_counter_spans(segment, tokens)
    phrase_spans: dict[int, tuple[int, str]] = {}
    reserved: set[int] = set()
    i = 0
    while i < len(tokens):
        for span in (6, 5, 4, 3, 2):
            group = tokens[i:i + span]
            if len(group) != span:
                continue
            replacement = None
            for surfaces in (tuple(t.surface for t in group),
                             tuple(t.original for t in group)):
                if surfaces in _PHRASE_OVERRIDES:
                    replacement = _PHRASE_OVERRIDES[surfaces]
                    break
            if replacement is not None:
                phrase_spans[i] = i + span, replacement
                reserved.update(range(i, i + span))
                i += span - 1
                break
        i += 1
    words: list[_RenderedWord] = []
    i = 0
    while i < len(tokens):
        replacement = None
        end = i + 1
        if i in phrase_spans:
            end, replacement = phrase_spans[i]
            group = tokens[i:end]
            words.append(_RenderedWord(group, replacement,
                                        "".join(t.reading for t in group), True))
            i = end
            continue
        if i in number_spans and not reserved.intersection(range(i, number_spans[i][0])):
            end, reading = number_spans[i]
            words.append(_RenderedWord(tokens[i:end], _kana_to_romaji(reading).capitalize(), reading))
            i = end
            continue
        for span in (4, 3, 2, 1):
            if i + span <= len(tokens) and not reserved.intersection(range(i, i + span)):
                replacement = _loanword_match(tokens[i:i + span])
                if replacement is not None:
                    end = i + span
                    break
        group = tokens[i:end]
        token = tokens[i]
        reading = "".join(t.reading for t in group)
        if replacement is None:
            word = _kana_to_romaji(reading)
            if token.pos == "助詞":
                # A literal katakana letter (ハ, ヘ) is not rewritten into a
                # phonetic particle unless the analysis normalized it.
                literal_kata = token.original == token.surface and all(
                    "ァ" <= ch <= "ヺ" for ch in token.original)
                if literal_kata:
                    word = word.capitalize()
                else:
                    word = {"ha": "wa", "he": "e"}.get(word, word)
                if i == 0 and first_in_title:
                    word = word.capitalize()
            elif token.pos != "接尾辞" or i == 0:
                word = word.capitalize()
        else:
            word = replacement
        words.append(_RenderedWord(group, word, reading, replacement is not None))
        i = end

    # Join only the explanatory な + ん (contracted の) + だ construction.
    # Recognize the complete triple before joining either boundary, so a
    # separator or reviewed replacement anywhere in it prevents the repair.
    contracted_boundaries: set[int] = set()
    for index in range(len(words) - 2):
        group = words[index:index + 3]
        if any(w.opaque or len(w.tokens) != 1 for w in group):
            continue
        na, n, da = (w.tokens[0] for w in group)
        if (tuple(t.original for t in (na, n, da)) == ("な", "ん", "だ")
                and tuple(t.surface for t in (na, n, da)) == ("な", "ん", "だ")
                and na.end == n.start and n.end == da.start
                and na.pos == da.pos == "助動詞"
                and na.lemma_reading == da.lemma_reading == "ダ"
                and na.conjugation_form.split("-", 1)[0] == "連体形"
                and n.pos == "助詞" and n.sub_pos == "準体助詞"
                and n.lemma_reading == "ノ"):
            contracted_boundaries.update((index + 1, index + 2))

    result = ""
    previous: _RenderedWord | None = None
    inflecting = {"動詞", "形容詞", "助動詞"}
    for index, word in enumerate(words):
        current = word.tokens[0]
        adjacent = previous is not None and previous.tokens[-1].end == current.start
        merge = bool(adjacent and (
            current.pos == "接尾辞" or (
                (current.pos == "助動詞" or current.sub_pos == "接続助詞")
                and previous.tokens[-1].pos in inflecting)))
        merge = merge or index in contracted_boundaries
        addition = word.text
        if adjacent and previous is not None and not previous.opaque and not word.opaque:
            # UniDic sometimes splits the classical adjective 儚き into the
            # adjective stem 儚 and a noun/verb き.  Repair only an exact,
            # adjacent hiragana ending after an explicitly identified stem;
            # full adjectives, homophones and reviewed replacements stay out.
            if (len(previous.tokens) == len(word.tokens) == 1
                    and previous.tokens[0].pos == "形容詞"
                    and previous.tokens[0].conjugation_form.split("-", 1)[0] == "語幹"
                    and current.original == current.surface == "き"):
                merge = True
            if previous.reading.endswith(("ッ", "っ")):
                geminated = _geminate_romaji(addition.lower())
                if geminated != addition.lower():
                    addition = geminated
                    merge = True
            if (word.reading and set(word.reading) == {"ー"}
                    and result and result[-1].lower() in "aeiou"):
                addition = result[-1].lower() * len(word.reading)
                merge = True
            if (merge and previous.reading.endswith(("ン", "ん"))
                    and result.lower().endswith("n") and addition
                    and addition[0].lower() in "aeiouy"):
                result += "'"
        if merge and not word.opaque:
            addition = addition.lower()
        if result and addition and not merge:
            result += " "
        result += addition
        previous = word
    return result

# ---------------------------------------------------------------------------
# Segment splitting and final assembly
# ---------------------------------------------------------------------------
_JP_SEGMENT_RE = re.compile(
    # Bring adjoining numbers into Japanese analysis, but leave ASCII names
    # such as R2-D2 and 2024ver intact.  Digits alone never form a segment.
    rf'(?:[{_JP_CHARS}・]+|(?<![A-Za-z0-9_.+−-])[0-9]+(?=[{_JP_CHARS}]))'
    rf'(?:[{_JP_CHARS}・]|[0-9]+(?![A-Za-z0-9_]))*'
)

# A title override describes the base title.  Variant labels and other
# annotations commonly follow it after whitespace or a delimiter, e.g.
# ``緋色月下、狂咲ノ絶 [Instrumental]`` or ``...- Radio Edit``.  Do not
# treat an arbitrary alphanumeric continuation as a suffix: a title override
# must not accidentally match the prefix of a different title.
_TITLE_OVERRIDE_SUFFIX_CHARS = frozenset(
    "([{<（［｛【〈《「『-–—~～/:：;；.・)]}>）］｝】〉》」』、,!！?？+＋·"
)
_TITLE_OVERRIDE_PREFIX_CHARS = frozenset("([{<（［｛【〈《「『:：;；/／+＋·・、,-–—~～")


def _reviewed_title_spans(text: str):
    """Match complete title bases at delimiters, never inside other words."""
    entries = {unicodedata.normalize("NFKC", value): (value, False)
               for value in _TITLE_SPELLING_ALIASES.values()}
    entries.update({unicodedata.normalize("NFKC", key): (value, False)
                    for key, value in _TITLE_SPELLING_ALIASES.items()})
    entries.update({unicodedata.normalize("NFKC", key): (value, True)
                    for key, value in _TITLE_OVERRIDES.items()})
    candidates = []
    for key, (value, is_romaji) in entries.items():
        if not key:
            continue
        start = text.find(key)
        while start >= 0:
            end = start + len(key)
            if ((start == 0 or text[start - 1].isspace()
                 or text[start - 1] in _TITLE_OVERRIDE_PREFIX_CHARS)
                    and (end == len(text) or text[end].isspace()
                         or text[end] in _TITLE_OVERRIDE_SUFFIX_CHARS)):
                candidates.append((start, end, value, is_romaji))
            start = text.find(key, start + 1)
    occupied_end = 0
    for span in sorted(candidates, key=lambda s: (s[0], -s[1])):
        if span[0] >= occupied_end:
            yield span
            occupied_end = span[1]


def _masking_circle_spans(text: str):
    """Protect word-masking circles; leave numeric/standalone circles unread."""
    for match in re.finditer("〇+", text):
        left = text[match.start() - 1:match.start()] if match.start() else ""
        right = text[match.end():match.end() + 1]
        numeric = set("0123456789零一二三四五六七八九十百千万億兆第年月日時分秒人本個回冊曲歳円話巻章番")
        if left in numeric or right in numeric:
            continue
        if (_KANA_ONLY_RE.fullmatch(left) or _KANA_ONLY_RE.fullmatch(right)
                or (len(match.group()) > 1 and (_JP_RE.search(left) or _JP_RE.search(right)))
                or (_KANJI_RE.search(left) and _KANJI_RE.search(right)
                    and any(_KANA_ONLY_RE.fullmatch(ch) for ch in text))):
            yield match.start(), match.end(), match.group(), True


def _language_skip_reason(title: str, path: str | None = None) -> str | None:
    """Assume Japanese unless an explicit exclusion or Chinese marker applies.

    Directory exclusions match whole parent-directory names, not substrings.
    Release/title exclusions require adjacent circle and album directories,
    including when the file is nested further inside disc subdirectories.
    They deliberately do not infer language from artist nationality.
    """
    text = unicodedata.normalize("NFKC", title)
    if text in {unicodedata.normalize("NFKC", t) for t in _NON_JAPANESE_TITLES}:
        return "skip_non_japanese"
    if path:
        parents = [unicodedata.normalize("NFKC", p).casefold()
                   for p in os.path.dirname(os.path.abspath(path)).split(os.sep)]
        excluded = {unicodedata.normalize("NFKC", p).casefold()
                    for p in _NON_JAPANESE_DIRECTORIES}
        if any(p in excluded for p in parents):
            return "skip_non_japanese"
        if any(text in _NON_JAPANESE_RELEASE_TITLES_MAP.get(release, ())
               for release in zip(parents, parents[1:])):
            return "skip_non_japanese"
    for start, end, _, _ in reversed(list(_reviewed_title_spans(text))):
        text = text[:start] + " " * (end - start) + text[end:]
    # These Chinese expressions are not evidence for Japanese readings, even
    # if another part of the title contains kana (e.g. Chinese credits).
    if any(marker in text for marker in (
            "你好", "欢迎", "歡迎", "主题曲", "翻自", "交响管乐",
            "交響管樂", "开场", "開場", "我们", "我們", "你们", "你們",
            "什么", "甚麼", "怎么", "怎麼", "这里", "這裡", "的故事")):
        return "skip_non_japanese"
    return None


def _has_unresolved_output(output: str, original: str) -> bool:
    protected_count = sum(end - start for start, end, _, _ in _masking_circle_spans(
        unicodedata.normalize("NFKC", original)))
    if output.count("〇") == protected_count:
        output = output.replace("〇", "")
    return not output.strip() or has_japanese(output)

_PUNCTUATION_NO_SPACE = frozenset({
    '.', ',', '!', '?', ':', ';', '"', "'", ')', ']', '}',
    '。', '、', '！', '？', '：', '；', '」', '』', '〉', '】', '≠',
})


def to_romaji(text: str) -> str:
    """Convert a string with Japanese characters to Hepburn romaji.

    This low-level function assumes the caller has identified Japanese text.
    File tagging assumes Japanese, with explicit Chinese exclusions and
    Chinese-language marker checks before conversion.
    Non-Japanese segments are preserved verbatim.  If the romaniser is
    not ready (MeCab/UniDic missing) the input is returned unchanged.
    Recognized numeral/counter expressions are read as words (2人 → Futari);
    standalone numbers and Latin identifiers retain their spelling.
    Title-level overrides from ``_TITLE_OVERRIDES`` short-circuit conversion
    of the matching base title.  A recognized suffix (such as
    ``[Instrumental]``) is retained and any Japanese in that suffix is
    romanised normally.
    """
    if not MECAB_AVAILABLE:
        return text

    # Title-level override (exact match on the full input)
    if text in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[text]

    # Normalise half-width katakana (ｱ-ﾝ) to full-width, and full-width
    # Latin/digits (Ａ, １) to ASCII, before any processing.
    text = unicodedata.normalize("NFKC", text)

    spans = list(_reviewed_title_spans(text))
    spans.extend(span for span in _masking_circle_spans(text)
                 if not any(start < span[1] and end > span[0] for start, end, _, _ in spans))
    if spans:
        result = []
        offset = 0
        for start, end, value, is_romaji in sorted(spans):
            result.append(_romanize_fragment(text[offset:start]))
            # Alias targets are Japanese text, not another alias lookup;
            # this prevents cycles in an edited companion data file.
            result.append(value if is_romaji else _romanize_alias_target(value))
            offset = end
        result.append(_romanize_fragment(text[offset:]))
        return "".join(result)
    return _japanese_text_to_romaji(text)


def _romanize_fragment(text: str) -> str:
    if not text.strip():
        return text
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    return text[:start] + _japanese_text_to_romaji(text[start:end]) + text[end:]


def _romanize_alias_target(text: str) -> str:
    if text in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[text]
    result = []
    offset = 0
    for start, end, value, _ in _masking_circle_spans(text):
        result.extend((_romanize_fragment(text[offset:start]), value))
        offset = end
    result.append(_romanize_fragment(text[offset:]))
    return "".join(result)


def _japanese_text_to_romaji(text: str) -> str:

    result_parts: list[str] = []
    last_end = 0
    first = True

    for match in _JP_SEGMENT_RE.finditer(text):
        prefix = text[last_end:match.start()]
        if prefix:
            result_parts.append(prefix)
            first = False

        romaji = _japanese_segment_to_romaji(
            match.group(), first_in_title=first,
        )
        first = False

        if romaji:
            if result_parts and not result_parts[-1][-1].isspace():
                last_char = result_parts[-1][-1]
                if last_char not in _PUNCTUATION_NO_SPACE:
                    result_parts.append(" ")
            result_parts.append(romaji)

        last_end = match.end()

    if last_end < len(text):
        suffix = text[last_end:]
        if (
            result_parts
            and not result_parts[-1][-1].isspace()
            and suffix
            and not suffix[0].isspace()
        ):
            last_char = result_parts[-1][-1]
            if last_char not in _PUNCTUATION_NO_SPACE:
                result_parts.append(" ")
        result_parts.append(suffix)

    result = "".join(result_parts)
    result = re.sub(r" {2,}", " ", result).strip()
    # Modern Hepburn: syllabic ん stays "n" before b/m/p (shinbun, not
    # shimbun).  The old n→m regex also corrupted Latin passthrough and
    # loanword values (e.g. "Rainbow" → "Raimbow") and has been removed.
    return result

# ---------------------------------------------------------------------------
# Tag I/O — read title, read titlesort, write titlesort
# ---------------------------------------------------------------------------
# titlesort tag mappings per format:
#   ID3 (mp3)                   → TSOT frame
#   Vorbis comments (FLAC/Ogg)  → "titlesort" field
#   MP4 (m4a)                   → "sonm" atom
#
# Reads use mutagen's "easy" interface (which already maps "titlesort"
# across all of these for free).  Writes use the format-specific path
# to mirror touhou_tagger.py's set_grouping().

def read_title(path: str) -> str | None:
    """Return the existing ``title`` tag, or None if missing."""
    try:
        f = mutagen.File(path, easy=True)
        if not f:
            return None
        val = f.get("title", [None])[0]
        return str(val).strip() if val else None
    except Exception:
        return None


def read_titlesort(path: str) -> str | None:
    """Return the existing ``titlesort`` tag, or None if missing."""
    try:
        f = mutagen.File(path, easy=True)
        if not f:
            return None
        val = f.get("titlesort", [None])[0]
        return str(val).strip() if val else None
    except Exception:
        return None


def set_titlesort(path: str, value: str, dry_run: bool = False) -> None:
    """Write `value` to the titlesort tag of the file at `path`."""
    if dry_run:
        return

    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        tags["TSOT"] = TSOT(encoding=3, text=value)
        tags.save(path)
    elif ext == ".flac":
        f = FLAC(path)
        f["titlesort"] = value
        f.save()
    elif ext == ".ogg":
        f = OggVorbis(path)
        f["titlesort"] = value
        f.save()
    elif ext == ".opus":
        f = OggOpus(path)
        f["titlesort"] = value
        f.save()
    elif ext == ".m4a":
        f = MP4(path)
        f["sonm"] = [value]
        f.save()
    else:
        raise ValueError(f"Unsupported file extension: {ext}")

# ---------------------------------------------------------------------------
# Per-file romanisation
# ---------------------------------------------------------------------------
# Status values returned by romanize_file:
#   "romanized"        — wrote (or would write) a new titlesort
#   "overwritten"      — replaced (or would replace) existing titlesort
#                        because force_titlesort=True
#   "skip_no_japanese" — title contains no Japanese characters
#   "skip_exists"      — titlesort already set; not forcing
#   "skip_no_title"    — file has no title tag (and no fallback supplied)
#   "skip_unchanged"   — romaji output is identical to the existing tag
#   "skip_unresolved"  — output is empty or still contains Japanese/CJK text
#   "skip_non_japanese" — Chinese-language evidence; leave the tags alone
#   "skip_ambiguous_language" — legacy status, retained for report compatibility
#   "error"            — exception while reading/writing
#
# The "title" field in the result is whichever string was actually
# romanised — the file's title tag, or the supplied fallback.

def romanize_file(
    path: str,
    *,
    force_titlesort: bool = False,
    dry_run: bool = False,
    fallback_title: str | None = None,
) -> dict:
    """Romanise one music file's title into its titlesort tag.

    Args:
        path:            Absolute path to the music file.
        force_titlesort: If True, overwrite an existing titlesort.
        dry_run:         If True, don't write anything to disk.
        fallback_title:  Used when the file has no title tag.  Pass the
                         wiki track title here when calling from the
                         tagger so we still get a result for files
                         whose title hasn't been set yet.

    Returns a dict with keys: status, title, titlesort_old,
    titlesort_new, error.
    """
    result = {
        "status": "error",
        "title": None,
        "titlesort_old": None,
        "titlesort_new": None,
        "error": None,
    }

    if not is_ready():
        result["status"] = "error"
        result["error"] = "Romaniser not ready (MeCab/UniDic missing)"
        return result

    try:
        title = read_title(path) or fallback_title
        existing = read_titlesort(path)
        result["title"] = title
        result["titlesort_old"] = existing

        if not title:
            result["status"] = "skip_no_title"
            return result

        if not has_japanese(title):
            result["status"] = "skip_no_japanese"
            return result

        language_skip = _language_skip_reason(title, path)
        if language_skip:
            result["status"] = language_skip
            return result

        new_value = to_romaji(title)
        result["titlesort_new"] = new_value

        # Preserve the attempted conversion for diagnostics, but never write
        # a partial Japanese/CJK result (even into an empty sort tag).
        if _has_unresolved_output(new_value, title):
            result["status"] = "skip_unresolved"
            return result

        if existing and existing == new_value:
            # Nothing to do — already correct.
            result["status"] = "skip_unchanged"
            return result

        if existing and not force_titlesort:
            result["status"] = "skip_exists"
            return result

        # Either no existing tag, or we're forcing.
        set_titlesort(path, new_value, dry_run=dry_run)
        result["status"] = "overwritten" if existing else "romanized"
        return result

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result

# ---------------------------------------------------------------------------
# Per-list romanisation (used by touhou_tagger.py integration)
# ---------------------------------------------------------------------------
# Accepts pre-scanned file dicts in the same format produced by
# touhou_tagger.py's _scan_single_dir(): {path, filename, disc, number,
# title}.  Optionally accepts a ``wiki_titles_by_key`` dict mapping
# (disc, number) → wiki title, used as the fallback when a file's own
# title tag is empty.

def romanize_files(
    local_files: list[dict],
    *,
    dry_run: bool = False,
    force_titlesort: bool = False,
    wiki_titles_by_key: dict[tuple[int, int], str] | None = None,
    log: callable = print,
    indent: str = "  ",
    is_locked: callable = None,
) -> dict:
    """Romanise titles for a list of pre-scanned files.

    Logs each file's outcome via the supplied ``log`` callable so the
    output integrates with whatever stream the caller is writing to
    (stdout for CLI, the GUI's redirected print, etc.).

    ``is_locked`` is an optional ``(path) -> bool`` predicate so the GUI can
    honour the user's manual titlesort locks without this module importing the
    configuration layer.  A locked file counts as ``skipped``; the CLI passes
    nothing and stays lock-free.

    Returns a summary dict: {romanized, overwritten, skipped, errors,
    no_title, results}.  ``results`` is a list of (file_dict,
    romanize_file_result) tuples for callers that want the raw data.
    """
    summary = {
        "romanized": 0,
        "overwritten": 0,
        "skipped": 0,
        "no_title": 0,
        "errors": 0,
        "results": [],
    }

    if not is_ready():
        log(f"{indent}Romaniser not ready: {get_install_hint()}")
        return summary

    wiki_titles_by_key = wiki_titles_by_key or {}
    multi_disc = len({f.get("disc", 1) for f in local_files}) > 1
    current_disc = None

    for f in local_files:
        if multi_disc and f.get("disc") != current_disc:
            current_disc = f.get("disc")
            log(f"{indent}── Disc {current_disc} ──")

        if is_locked is not None and is_locked(f["path"]):
            log(f"{indent}[LOCKED]     "
                f"{f.get('filename', f['path'])}  "
                f"titlesort locked by hand")
            summary["skipped"] += 1
            continue

        fb = wiki_titles_by_key.get((f.get("disc", 1), f.get("number") or -1))
        res = romanize_file(
            f["path"],
            force_titlesort=force_titlesort,
            dry_run=dry_run,
            fallback_title=fb,
        )
        summary["results"].append((f, res))

        # Build a nice display label: "NN. <original title>"
        track_label = ""
        if f.get("number") is not None:
            track_label = f"{f['number']:02d}. "
        # Show the file's title where we have it; otherwise filename
        display_title = res.get("title") or f.get("filename", "?")

        status = res["status"]
        prefix = {
            "romanized":        "[ROMANIZE]   ",
            "overwritten":      "[OVERWRITE]  ",
            "skip_no_japanese": "[SKIP-NJP]   ",
            "skip_exists":      "[SKIP-EX]    ",
            "skip_unchanged":   "[SKIP-OK]    ",
            "skip_unresolved":  "[UNRESOLVED] ",
            "skip_non_japanese": "[NON-JP]    ",
            "skip_ambiguous_language": "[LANG-REVIEW] ",
            "skip_no_title":    "[NO-TITLE]   ",
            "error":            "[ERROR]      ",
        }.get(status, f"[{status.upper()}] ")

        if status == "romanized":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             titlesort = {res['titlesort_new']}")
            summary["romanized"] += 1
        elif status == "overwritten":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             was = {res['titlesort_old']}")
            log(f"{indent}             now = {res['titlesort_new']}")
            summary["overwritten"] += 1
        elif status == "skip_no_japanese":
            log(f"{indent}{prefix}{track_label}{display_title}  "
                f"(no Japanese)")
            summary["skipped"] += 1
        elif status == "skip_exists":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             current = {res['titlesort_old']}")
            log(f"{indent}             would set = {res['titlesort_new']}")
            log(f"{indent}             (use --force-titlesort or "
                f"tick 'Force overwrite' to replace)")
            summary["skipped"] += 1
        elif status == "skip_unchanged":
            log(f"{indent}{prefix}{track_label}{display_title}  "
                f"(already correct: {res['titlesort_old']})")
            summary["skipped"] += 1
        elif status in {"skip_non_japanese", "skip_ambiguous_language"}:
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             language outside Japanese scope or uncertain; titlesort preserved")
            summary["skipped"] += 1
        elif status == "skip_unresolved":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             incomplete = {res['titlesort_new']}")
            log(f"{indent}             titlesort preserved")
            summary["skipped"] += 1
        elif status == "skip_no_title":
            log(f"{indent}{prefix}{f.get('filename', '?')}  (no title tag)")
            summary["no_title"] += 1
        else:  # error
            log(f"{indent}{prefix}{f.get('filename', '?')}  "
                f"— {res.get('error')}")
            summary["errors"] += 1

    return summary

# ---------------------------------------------------------------------------
# Standalone file scanning (mirrors touhou_tagger.py so this module can
# run on its own without a circular dependency)
# ---------------------------------------------------------------------------
def _scan_single_dir(directory: str, disc: int) -> list[dict]:
    files = []
    for fname in sorted(os.listdir(directory)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        fpath = os.path.join(directory, fname)
        number = None
        title = None
        try:
            f = mutagen.File(fpath, easy=True)
            if f:
                tracknumber = f.get("tracknumber", [None])[0]
                if tracknumber:
                    number = int(str(tracknumber).split("/")[0])
                title_val = f.get("title", [None])[0]
                if title_val:
                    title = str(title_val).strip()
        except Exception:
            pass

        if number is None:
            m = re.match(r"^(\d+)", fname)
            if m:
                number = int(m.group(1))

        files.append({
            "path":     fpath,
            "filename": fname,
            "disc":     disc,
            "number":   number,
            "title":    title,
        })
    return files


def scan_music_files(directory: str) -> list[dict]:
    """Same shape and behaviour as touhou_tagger.py's scan_music_files."""
    disc_dirs: list[tuple[int, str]] = []
    for entry in sorted(os.listdir(directory)):
        entry_path = os.path.join(directory, entry)
        if not os.path.isdir(entry_path):
            continue
        m = DISC_DIR_RE.match(entry)
        if m:
            disc_dirs.append((int(m.group(1)), entry_path))

    if disc_dirs:
        disc_dirs.sort(key=lambda x: x[0])
        files: list[dict] = []
        for disc_num, disc_path in disc_dirs:
            files.extend(_scan_single_dir(disc_path, disc=disc_num))
        return files

    return _scan_single_dir(directory, disc=1)

# ---------------------------------------------------------------------------
# Per-album processing (CLI / GUI Romanization tab entry point)
# ---------------------------------------------------------------------------
def process_album_romanize(
    music_dir: str,
    *,
    dry_run: bool = False,
    force_titlesort: bool = False,
    is_locked: callable = None,
) -> dict:
    """Romanise every applicable track in a single album folder.

    ``is_locked`` is the optional ``(path) -> bool`` predicate described on
    :func:`romanize_files`; locked files count into ``skipped``, so the result
    shape is identical whether or not the caller supplies one.

    Returns a summary dict:
        {"album": str, "tagged_dir": str,
         "romanized": int, "overwritten": int,
         "skipped": int, "no_title": int, "errors": int,
         "error": str | None}
    """
    print(f"\n{'=' * 60}")
    print(f"Romanise: {music_dir}")
    print("=" * 60)

    if not os.path.isdir(music_dir):
        print(f"Error: '{music_dir}' is not a directory.")
        return {
            "album": os.path.basename(music_dir.rstrip(os.sep)),
            "tagged_dir": music_dir,
            "romanized": 0, "overwritten": 0,
            "skipped": 0, "no_title": 0, "errors": 0,
            "error": "directory not found",
        }

    if not is_ready():
        print(get_install_hint())
        return {
            "album": os.path.basename(music_dir.rstrip(os.sep)),
            "tagged_dir": music_dir,
            "romanized": 0, "overwritten": 0,
            "skipped": 0, "no_title": 0, "errors": 0,
            "error": "romaniser not ready",
        }

    if _DATA_LOAD_ERROR:
        print(f"  Warning: shared data file not loaded "
              f"({_DATA_LOAD_ERROR}).  Proceeding with empty loanword "
              f"and override tables.")

    local_files = scan_music_files(music_dir)
    if not local_files:
        print(f"\nNo supported music files found in '{music_dir}'.")
        return {
            "album": os.path.basename(music_dir.rstrip(os.sep)),
            "tagged_dir": music_dir,
            "romanized": 0, "overwritten": 0,
            "skipped": 0, "no_title": 0, "errors": 0,
            "error": "no music files found",
        }

    multi_disc = len({f["disc"] for f in local_files}) > 1
    if multi_disc:
        print(f"\nFound {len(local_files)} local file(s) "
              f"across multiple discs.")
    else:
        print(f"\nFound {len(local_files)} local file(s).")

    prefix = "DRY RUN — " if dry_run else ""
    print(f"\n{prefix}Romanisation results:")
    print("-" * 60)

    summary = romanize_files(
        local_files,
        dry_run=dry_run,
        force_titlesort=force_titlesort,
        is_locked=is_locked,
    )

    print("-" * 60)
    action = "Would write" if dry_run else "Wrote"
    print(
        f"{action}: {summary['romanized']} new  |  "
        f"{summary['overwritten']} overwritten  |  "
        f"Skipped: {summary['skipped']}  |  "
        f"No title: {summary['no_title']}  |  "
        f"Errors: {summary['errors']}"
    )

    return {
        "album":       os.path.basename(music_dir.rstrip(os.sep)),
        "tagged_dir":  music_dir,
        "romanized":   summary["romanized"],
        "overwritten": summary["overwritten"],
        "skipped":     summary["skipped"],
        "no_title":    summary["no_title"],
        "errors":      summary["errors"],
        "error":       None,
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Romanise Japanese song titles into the 'titlesort' tag of "
            "music files, leaving 'title' untouched."
        ),
        epilog=(
            "By default an existing titlesort is preserved (with a "
            "warning showing both the current and would-be values).  "
            "Pass --force-titlesort to overwrite."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "directories",
        nargs="+",
        metavar="music_dir",
        help="One or more album folders to romanise.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be tagged without writing anything.",
    )
    parser.add_argument(
        "--force-titlesort",
        action="store_true",
        help="Overwrite existing titlesort tags.",
    )
    args = parser.parse_args()

    if not is_ready():
        print(get_install_hint())
        sys.exit(2)

    results = []
    for music_dir in args.directories:
        results.append(process_album_romanize(
            music_dir,
            dry_run=args.dry_run,
            force_titlesort=args.force_titlesort,
        ))

    # Grand summary for multi-album runs
    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print("GRAND SUMMARY")
        print("=" * 60)
        total_r  = sum(r["romanized"] for r in results)
        total_ow = sum(r["overwritten"] for r in results)
        total_s  = sum(r["skipped"] for r in results)
        total_nt = sum(r["no_title"] for r in results)
        total_e  = sum(r["errors"] for r in results)
        for r in results:
            mark = "✗" if r["error"] else "✓"
            line = (
                f"  {mark} {r['album']}  — "
                f"Romanised: {r['romanized']}  |  "
                f"Overwritten: {r['overwritten']}  |  "
                f"Skipped: {r['skipped']}"
            )
            if r["error"]:
                line += f"  — {r['error']}"
            print(line)
        print("-" * 60)
        action = "Would write" if args.dry_run else "Wrote"
        print(
            f"{action}: {total_r} new  |  "
            f"{total_ow} overwritten  |  "
            f"Skipped: {total_s}  |  "
            f"No title: {total_nt}  |  "
            f"Errors: {total_e}"
        )
        if args.dry_run:
            print("\nRe-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
