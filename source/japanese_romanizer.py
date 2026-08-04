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
_JP_RE = re.compile(
    r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\u3005]'
)
_KANJI_RE = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF]')


def has_japanese(text: str) -> bool:
    """True if the text contains any hiragana, katakana, kanji, or 々."""
    return bool(_JP_RE.search(text))


def _get_reading(feature: str) -> str | None:
    parts = feature.split(",")
    pos = parts[0] if parts else ""

    if pos in ("動詞", "形容詞", "助動詞"):
        if len(parts) > 9 and parts[9] not in ("*", ""):
            return parts[9]

    if len(parts) > 6 and parts[6] not in ("*", ""):
        return parts[6]
    if len(parts) > 9 and parts[9] not in ("*", ""):
        return parts[9]
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
    """Convert isolated single katakana characters back to hiragana.

    Song titles sometimes use katakana for okurigana or particles as a
    stylistic choice (e.g. 永イ夜ハ空ヲ歩キ instead of 永い夜は空を歩き).
    MeCab expects hiragana okurigana and cannot correctly tokenise these
    titles.  This function detects katakana characters that are *not*
    adjacent to other katakana (i.e. not part of a multi-character
    katakana loanword run) and converts them to hiragana so MeCab can
    process them normally.

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
        if not prev_kata and not next_kata:
            result[i] = chr(cp - 0x60)  # katakana → hiragana offset
    return "".join(result)

# ---------------------------------------------------------------------------
# Hiragana long-vowel-mark normalisation
# ---------------------------------------------------------------------------
_HIRAGANA_LONG_VOWEL_RE = re.compile(
    r'[\u3041-\u3096ー]*ー[\u3041-\u3096ー]*'
)


def _hiragana_with_chouon_to_katakana(text: str) -> str:
    """Convert hiragana runs containing ー (chouon) to katakana.

    The long-vowel mark ー (U+30FC) is fundamentally a katakana feature;
    its appearance inside a hiragana run is a stylistic indicator that
    the underlying word is a katakana loanword spelled phonetically in
    hiragana (e.g. にーと instead of ニート, ふぃーばー instead of
    フィーバー).

    UniDic has no hiragana entries for foreign loanwords, so MeCab fails
    to tokenise these runs sensibly — it splits them into fragments that
    lose the long-vowel association and that the loanword dictionary
    cannot reassemble.  Converting the entire run to katakana before
    MeCab sees it lets UniDic and the loanword dictionary recognise the
    word as a single token.

    A matched run consists of one or more hiragana characters and ー
    marks surrounding at least one ー.  Pure hiragana sequences with no
    ー are left untouched, as are non-kana characters on either side of
    the run.

    Edge case: a hiragana copula like です sitting immediately after a
    hiragana-with-ー loanword with no intervening character (e.g.
    にーとです) will be absorbed into the run and converted alongside
    it, which can lead MeCab to read です as the loanword デス.  This
    pattern is very rare in song titles, but if encountered, add a
    _PHRASE_OVERRIDES or _TITLE_OVERRIDES entry to handle it.
    """
    def _convert(match: "re.Match[str]") -> str:
        run = match.group(0)
        out = []
        for ch in run:
            cp = ord(ch)
            if 0x3041 <= cp <= 0x3096:
                out.append(chr(cp + 0x60))  # hiragana → katakana offset
            else:
                out.append(ch)  # ー stays as ー
        return "".join(out)
    return _HIRAGANA_LONG_VOWEL_RE.sub(_convert, text)

# ---------------------------------------------------------------------------
# Direct katakana-to-Hepburn romaji table
# ---------------------------------------------------------------------------
# Digraphs and extended combinations are checked first via 2-character
# lookahead; single-character entries cover the basic syllabary.
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


def _kana_to_romaji(kana: str) -> str:
    """Convert a katakana (or hiragana) string to Hepburn romaji."""
    # Normalise hiragana to katakana so the table handles both.
    chars = []
    for ch in kana:
        cp = ord(ch)
        if 0x3041 <= cp <= 0x3096:
            chars.append(chr(cp + 0x60))
        else:
            chars.append(ch)
    kana = "".join(chars)

    parts: list[str] = []
    last_vowel = ""
    i = 0
    while i < len(kana):
        # Two-character lookahead for digraphs
        if i + 1 < len(kana):
            pair = kana[i:i+2]
            if pair in _KATAKANA_ROMAJI:
                r = _KATAKANA_ROMAJI[pair]
                parts.append(r)
                if r in _TRAILING_VOWEL:
                    last_vowel = _TRAILING_VOWEL[r]
                elif r:
                    last_vowel = ""
                i += 2
                continue

        ch = kana[i]
        if ch == "ー":
            # Long vowel mark: repeat the previous vowel
            if last_vowel:
                parts.append(last_vowel)
            # last_vowel stays the same
        elif ch == "ッ":
            # Small tsu (gemination): look ahead to the next syllable
            # and prepend the appropriate consonant(s).
            next_romaji = ""
            if i + 1 < len(kana):
                # Check for digraph first
                if i + 2 < len(kana):
                    pair = kana[i+1:i+3]
                    if pair in _KATAKANA_ROMAJI:
                        next_romaji = _KATAKANA_ROMAJI[pair]
                if not next_romaji and kana[i+1] in _KATAKANA_ROMAJI:
                    next_romaji = _KATAKANA_ROMAJI[kana[i+1]]
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
            next_romaji = ""
            if i + 2 < len(kana):
                pair = kana[i+1:i+3]
                if pair in _KATAKANA_ROMAJI:
                    next_romaji = _KATAKANA_ROMAJI[pair]
            if not next_romaji and i + 1 < len(kana) \
                    and kana[i+1] in _KATAKANA_ROMAJI:
                next_romaji = _KATAKANA_ROMAJI[kana[i+1]]
            if next_romaji and next_romaji[0] in "aiueoy":
                parts.append("n'")
            else:
                parts.append("n")
            last_vowel = ""
        elif ch in _KATAKANA_ROMAJI:
            r = _KATAKANA_ROMAJI[ch]
            parts.append(r)
            if r in _TRAILING_VOWEL:
                last_vowel = _TRAILING_VOWEL[r]
            elif r:
                last_vowel = ""
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
    if not PYKAKASI_AVAILABLE:
        return surface
    tokens = _kks.convert(surface)
    return "".join(token["hepburn"] for token in tokens).strip()


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
    if first and first not in "aeiouy":
        return first + word
    return word

# ---------------------------------------------------------------------------
# MeCab-driven segment romanisation
# ---------------------------------------------------------------------------
def _japanese_segment_to_romaji(
    segment: str, first_in_title: bool = False,
) -> str:
    """
    Convert a Japanese-only text segment to Romaji with token-level
    awareness (POS, particles, gemination, ん boundaries, etc.).
    """
    _INFLECTING = {"動詞", "形容詞", "助動詞"}

    tokens = []
    conjunctive_particle_indices = set()
    node = _mecab.parseToNode(segment)
    while node:
        surface = node.surface
        if not surface:
            node = node.next
            continue
        feat_parts = node.feature.split(",")
        pos = feat_parts[0]
        sub_pos = feat_parts[1] if len(feat_parts) > 1 else ""

        if surface == "々" and tokens:
            tokens.append((tokens[-1][0], tokens[-1][1], "々"))
            node = node.next
            continue

        # Nakaguro (・) is a word separator in katakana loanwords
        # (e.g. ヘクセン・タンツ).  Skip it so the surrounding tokens
        # remain adjacent for multi-token loanword matching, and the
        # normal inter-token space in the assembly step takes its place.
        if surface == "・":
            node = node.next
            continue

        reading = _get_reading(node.feature)
        if not reading or reading == "*":
            if _KANJI_RE.search(surface):
                romaji = _pykakasi_fallback(surface)
            else:
                romaji = _kana_to_romaji(surface)
        else:
            romaji = _kana_to_romaji(reading)

        if romaji:
            if pos == "助詞" and sub_pos == "接続助詞":
                conjunctive_particle_indices.add(len(tokens))
            tokens.append((romaji, pos, surface))
        node = node.next

    if not tokens:
        return ""

    cased: list[str | None] = [None] * len(tokens)
    skip_indices: set[int] = set()

    # --- Phrase-level overrides (token-based, longest-first) ---
    # Matches sequences of 2-6 MeCab surface forms against
    # _PHRASE_OVERRIDES.  The start token index is added to skip_indices
    # so the loanword loop cannot overwrite the result.
    i = 0
    while i < len(tokens):
        matched = False
        for span in (6, 5, 4, 3, 2):
            if i + span <= len(tokens):
                surfaces = tuple(tokens[i + j][2] for j in range(span))
                if surfaces in _PHRASE_OVERRIDES:
                    cased[i] = _PHRASE_OVERRIDES[surfaces]
                    skip_indices.update(range(i, i + span))
                    matched = True
                    i += span
                    break
        if not matched:
            i += 1

    # --- Multi-token loanword matching (POS-safe, longest-first) ---
    for i, (word, pos, surface) in enumerate(tokens):
        if i in skip_indices:
            continue

        lower = word.lower().strip()
        merged = False

        if pos != "助詞":
            for span in (4, 3, 2):
                if i + span <= len(tokens):
                    if any((i + j) in skip_indices for j in range(1, span)):
                        continue
                    if any(tokens[i + j][1] == "助詞" for j in range(span)):
                        continue
                    combined = "".join(
                        tokens[i + j][0] for j in range(span)
                    ).lower().strip()
                    if combined in _LOANWORDS_MAP:
                        cased[i] = _LOANWORDS_MAP[combined]
                        skip_indices.update(range(i + 1, i + span))
                        merged = True
                        break

        if merged:
            continue

        # Single-token processing
        if lower in _LOANWORDS_MAP:
            cased[i] = _LOANWORDS_MAP[lower]
        elif i == 0:
            if pos == "助詞":
                # Phonetic particle conversion applies regardless of
                # position; only the casing depends on first_in_title.
                p = (
                    "wa" if lower == "ha"
                    else ("e" if lower == "he" else lower)
                )
                cased[i] = p.capitalize() if first_in_title else p
            else:
                cased[i] = word.capitalize()
        elif pos == "助詞":
            cased[i] = (
                "wa" if lower == "ha"
                else ("e" if lower == "he" else lower)
            )
        elif pos == "接尾辞":
            cased[i] = lower
        else:
            cased[i] = word.capitalize()

    # --- Gemination ---
    for i in range(len(tokens) - 1):
        if cased[i + 1] is None:
            continue
        if tokens[i][2].endswith(("っ", "ッ")):
            next_cased = cased[i + 1]
            if not next_cased:
                continue
            lower_next = next_cased.lower()
            geminated_lower = _geminate_romaji(lower_next)
            if next_cased[0].isupper():
                cased[i + 1] = geminated_lower.capitalize()
            else:
                cased[i + 1] = geminated_lower

    # --- Assembly with apostrophe handling for ん across boundaries ---
    result = ""
    for i, (cased_word, (_, pos, surface)) in enumerate(zip(cased, tokens)):
        if cased_word is None:
            continue

        # Determine whether this token merges with the previous one.
        merge_with_prev = False
        if i > 0:
            if pos == "接尾辞":
                merge_with_prev = True
            elif (pos == "助動詞" or i in conjunctive_particle_indices) \
                    and tokens[i - 1][1] in _INFLECTING:
                merge_with_prev = True

        if i == 0:
            result = cased_word
        elif (
            i > 0
            and tokens[i - 1][2].endswith(("ん", "ン"))
            and cased_word
            and cased_word[0].lower() in "aeiouy"
        ):
            word_to_add = cased_word.lower() if merge_with_prev else cased_word
            if result.endswith("n"):
                result = result[:-1]
                result += "n'" + word_to_add
            else:
                result += ("" if merge_with_prev else " ") + word_to_add
        elif merge_with_prev:
            result += cased_word.lower()
        else:
            result += " " + cased_word

    return result

# ---------------------------------------------------------------------------
# Segment splitting and final assembly
# ---------------------------------------------------------------------------
_JP_SEGMENT_RE = re.compile(
    r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\u3400-\u4DBF\u3005]+'
)

# A title override describes the base title.  Variant labels and other
# annotations commonly follow it after whitespace or a delimiter, e.g.
# ``緋色月下、狂咲ノ絶 [Instrumental]`` or ``...- Radio Edit``.  Do not
# treat an arbitrary alphanumeric continuation as a suffix: a title override
# must not accidentally match the prefix of a different title.
_TITLE_OVERRIDE_SUFFIX_CHARS = frozenset(
    "([{<（［｛【〈《「『-–—~～/:：;；.・"
)

_PUNCTUATION_NO_SPACE = frozenset({
    '.', ',', '!', '?', ':', ';', '"', "'", ')', ']', '}',
    '。', '、', '！', '？', '：', '；', '」', '』', '〉', '】', '≠',
})


def to_romaji(text: str) -> str:
    """Convert a string with Japanese characters to Hepburn romaji.

    Non-Japanese segments are preserved verbatim.  If the romaniser is
    not ready (MeCab/UniDic missing) the input is returned unchanged.
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

    # Title-level override on the base title, retaining a variant label or
    # other annotation after it.  Try longest titles first in case one
    # override is a prefix of another.
    for override_title, override_romaji in sorted(
        _TITLE_OVERRIDES.items(), key=lambda item: len(item[0]), reverse=True
    ):
        if not text.startswith(override_title):
            continue
        suffix = text[len(override_title):]
        if suffix and not (
            suffix[0].isspace()
            or suffix[0] in _TITLE_OVERRIDE_SUFFIX_CHARS
        ):
            continue

        if not suffix:
            return override_romaji

        # Keep leading/trailing whitespace in the annotation, while allowing
        # any Japanese inside it to use the normal romanisation path.
        leading_len = len(suffix) - len(suffix.lstrip())
        trailing_len = len(suffix) - len(suffix.rstrip())
        leading = suffix[:leading_len]
        trailing = suffix[len(suffix) - trailing_len:] if trailing_len else ""
        middle_end = len(suffix) - trailing_len if trailing_len else len(suffix)
        middle = suffix[leading_len:middle_end]
        return override_romaji + leading + (
            to_romaji(middle) + trailing if middle else trailing
        )

    text = _hiragana_with_chouon_to_katakana(text)
    text = _normalize_katakana_okurigana(text)

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

        new_value = to_romaji(title)
        result["titlesort_new"] = new_value

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
) -> dict:
    """Romanise titles for a list of pre-scanned files.

    Logs each file's outcome via the supplied ``log`` callable so the
    output integrates with whatever stream the caller is writing to
    (stdout for CLI, the GUI's redirected print, etc.).

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
) -> dict:
    """Romanise every applicable track in a single album folder.

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
