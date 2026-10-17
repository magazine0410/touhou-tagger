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
import contextvars
import csv
from dataclasses import dataclass, field, replace
from functools import lru_cache
import importlib
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
    "explain_romaji",
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
_MECAB_DICTIONARY: str | None = None
# The full dictionary first; unidic-lite (26 fields, handled by
# _get_reading) is the fallback when it is not installed or not downloaded.
_DICTIONARY_PACKAGES = ("unidic", "unidic_lite")


def _load_tagger(mecab_module, packages: tuple[str, ...] = _DICTIONARY_PACKAGES):
    """Build a tagger from the first usable UniDic package.

    mecab-python3 splits its option string with shlex, so a dictionary path
    containing a space must be quoted (quoting also keeps the backslashes
    of a Windows path).  It also prepends ``-r``/``-d`` for the first unidic
    package it can import, even one whose dictionary was never downloaded;
    naming the chosen dictionary's own resource file makes the later
    options win.  Returns ``(tagger, package_name)``.
    """
    failures = []
    for name in packages:
        try:
            dicdir = importlib.import_module(name).DICDIR
            if not os.path.isdir(dicdir):
                raise FileNotFoundError(f"dictionary directory {dicdir} is missing")
            options = f'-d "{dicdir}"'
            rcfile = os.path.join(dicdir, "mecabrc")
            if os.path.isfile(rcfile):
                options = f'-r "{rcfile}" {options}'
            return mecab_module.Tagger(options), name
        except Exception as exc:  # ImportError, OSError, RuntimeError
            detail = str(exc).strip().splitlines()
            failures.append(f"{name}: {detail[0] if detail else type(exc).__name__}")
    raise RuntimeError("; ".join(failures))


try:
    import MeCab  # type: ignore
    _mecab, _MECAB_DICTIONARY = _load_tagger(MeCab)
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
        ready = "Romaniser ready."
        if _MECAB_DICTIONARY == "unidic_lite":
            ready = ("Romaniser ready (unidic-lite fallback; install unidic and run "
                     "python -m unidic download for the full dictionary).")
        if not PYKAKASI_AVAILABLE:
            return (
                f"{ready}  (Optional: pip install --user pykakasi "
                "for better rare-kanji coverage.)"
            )
        return ready
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
        "    (or: pip install --user unidic-lite for the smaller dictionary)\n"
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

    UniDic 2.2+/3.x has 29 fields with kana at 20; the 26-field
    UniDic 2.1.2 binary/lite layout has kana at 17 and formBase at 20.
    Features such as fConType contain quoted commas, so parse CSV before
    identifying the layout.  Unknown layouts and missing kana fall back to
    the shared surface-pronunciation field, then the lemma as a last resort.
    """
    parts = next(csv.reader([feature]))
    kana_index = {26: 17, 29: 20}.get(len(parts))
    indices = (kana_index, 9, 6) if kana_index is not None else (9, 6)
    for index in indices:
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
# Fragmented hiragana word and long-vowel-mark normalisation
# ---------------------------------------------------------------------------
_HIRAGANA_WORD_RE = re.compile(r"[ぁ-ゖー]{3,}")


def _breaks_reviewed_match(before: list[_Token], after: list[_Token],
                           start: int, end: int) -> bool:
    """True when a candidate parse cuts an unknown word across a reviewed spelling.

    ぬえ + の admits the reviewed Nue; the katakana candidate's ヌ + エノ
    (unknown) would lose it.  A candidate that covers the same span with a
    match of its own (ハート for はーと) or with a known word is fine.
    """
    def matches(tokens: list[_Token]) -> set[tuple[int, int]]:
        found = set()
        for i in range(len(tokens)):
            for size in range(1, 5):
                group = tokens[i:i + size]
                if len(group) < size:
                    break
                if group[-1].end <= start or group[0].start >= end:
                    continue
                if _loanword_match(group) is not None:
                    found.add((group[0].start, group[-1].end))
        return found
    kept = matches(after)
    for a, b in matches(before):
        for t in after:
            if (t.unknown and t.start < b and t.end > a and (t.start, t.end) != (a, b)
                    and not any(m[0] <= t.start and m[1] >= t.end for m in kept)):
                return True
    return False


def _normalize_hiragana_long_vowels(text: str, *, use_overrides: bool = True) -> str:
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
        contextual_cache: dict[str, list[_Token]] = {}

        def analyze(candidate: str) -> list[_Token]:
            if candidate not in cache:
                cache[candidate] = _read_tokens(candidate)
            return cache[candidate]

        def analyze_context(candidate: str) -> list[_Token]:
            if candidate not in contextual_cache:
                alternate = text[:match.start()] + candidate + text[match.end():]
                contextual_cache[candidate] = _read_tokens(alternate, text)
            return contextual_cache[candidate]

        def fragmentation(tokens: list[_Token]) -> int:
            broken = sum(len(t.surface) for t in tokens if t.unknown or
                         all(ch in "ーぁぃぅぇぉゃゅょ" for ch in t.surface))
            broken += sum(len(t.surface) for t in tokens
                          if t.pos == "感動詞" and t.sub_pos == "フィラー")
            broken += sum(len(a.surface) for a, b in zip(tokens, tokens[1:])
                          if a.conjugation_form.endswith("ウ音便")
                          and b.original == "た" and b.pos == "助詞")
            return broken

        def score(candidate: str) -> tuple[int, int, int]:
            tokens = analyze(candidate)
            # Okurigana at the start of a run belongs to the preceding kanji.
            # Include contextual fragmentation: an isolated parse can hide
            # the actual broken word (くおでんぱ in 聴くおでんぱ). Keep the
            # local boundary score; surrounding kanji must not reward an
            # unrelated homophone solely because it uses fewer tokens.
            contextual = [t for t in analyze_context(candidate)
                          if t.start < match.end() and t.end > match.start()]
            broken = fragmentation(tokens) + fragmentation(contextual)
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
        candidates = [run, expand(run, False), expand(run, True)] if "ー" in run else [run]
        kata = _to_katakana(run)
        kata_tokens = analyze(kata)
        if (score(run)[0] and kata_tokens and all(not t.unknown for t in kata_tokens)
                and all(t.pos in ("名詞", "接頭辞", "接尾辞", "副詞", "助詞")
                        for t in kata_tokens)):
            candidates.append(kata)

        # Only a single known foreign word qualifies; leave neighbouring
        # grammar, such as は after パーティー, available to the parser.
        # A wrong token can cross the correct boundary (ろふ in
        # なないろふぁんたじー). Examine character boundaries, bounded above.
        starts = range(len(run))
        ends = range(1, len(run) + 1)
        foreign_spans = []
        context = analyze_context(run)
        damaged = [(t.start - match.start(), t.end - match.start()) for t in context
                   if t.unknown or (t.pos == "感動詞" and t.sub_pos == "フィラー")
                   or all(ch in "ーぁぃぅぇぉゃゅょ" for ch in t.original)]
        for start in sorted(starts):
            for end in sorted(ends, reverse=True):
                source = run[start:end]
                if len(source) < 3 or ("ー" not in source and not any(
                        start < b and end > a for a, b in damaged)):
                    continue
                if "ー" not in source:
                    a, b = match.start() + start, match.start() + end
                    covered = [t for t in context if t.start < b and t.end > a]
                    # Without an explicit long-vowel cue, avoid mining
                    # coincidental words out of an unknown name or a
                    # recognized neighbouring word (みしゃくじ, ゆかりん).
                    # Repair complete fragment groups, not arbitrary cuts.
                    grammatical = {"助詞", "接続詞", "感動詞"}
                    if (not covered
                            or (covered[0].start != a and covered[0].pos not in grammatical)
                            or (covered[-1].end != b and covered[-1].pos not in grammatical)
                            or any(t.unknown and len(t.original) > 1 for t in covered)
                            or (any(t.end == a and t.pos == "助動詞" for t in context)
                                and not any(all(ch in "ぁぃぅぇぉゃゅょ" for ch in t.original)
                                            for t in covered))):
                        continue
                kata = _to_katakana(source)
                tokens = analyze(kata)
                if (len(tokens) == 1 and not tokens[0].unknown and tokens[0].pos in ("名詞", "形状詞")
                        and (tokens[0].goshu == "外" or ("ー" not in source and tokens[0].goshu == "漢"))):
                    foreign_spans.append((start, end, kata))
        replaced: set[int] = set()
        foreign = list(run)
        for start, end, kata in sorted(foreign_spans,
                                       key=lambda span: span[0] - span[1]):
            if not replaced.intersection(range(start, end)):
                foreign[start:end] = kata
                replaced.update(range(start, end))
        candidates.append("".join(foreign))
        ordered = sorted(set(candidates), key=lambda value: (score(value), candidates.index(value)))
        original_context = None
        for candidate in ordered:
            if candidate == run:
                return run
            # Local kana parses lack the preceding kanji/word context. Do
            # not turn okurigana into a new noun or swallow an adjacent word
            # into an unknown katakana run (喰らう, お会いしましょう,
            # コイはふぃっしんぐ). Real particles also keep their boundaries.
            if original_context is None:
                original_context = context
            contextual = analyze_context(candidate)
            if use_overrides and _LOANWORDS_MAP and _breaks_reviewed_match(
                    original_context, contextual, match.start(), match.end()):
                continue
            particles = [(t.start, t.end) for i, t in enumerate(original_context)
                         if i and t.pos == "助詞"
                         and t.original in {"は", "が", "を", "の", "に", "へ", "も", "と", "で"}
                         and not original_context[i - 1].unknown
                         and original_context[i - 1].pos in ("名詞", "動詞", "形容詞", "代名詞")]
            def fixed(group):
                return [replace(t, surface=t.original) for t in group
                        if t.start < match.start() or t.end > match.end()
                        or any(t.start < end and t.end > start for start, end in particles)]
            if fixed(original_context) == fixed(contextual):
                return candidate
        return run

    return _HIRAGANA_WORD_RE.sub(normalize_run, text)


def _normalize_native_katakana(text: str) -> str:
    """Recover a single native verb/adjective disguised as foreign fragments."""
    def recover(match: re.Match[str]) -> str:
        word = match.group()
        current = _read_tokens(word)
        if len(current) <= 1:
            return word
        hira = "".join(chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch for ch in word)
        native = _read_tokens(hira)
        if (len(native) == 1 and not native[0].unknown and native[0].goshu == "和"
                and native[0].pos in ("動詞", "形容詞")
                and _to_katakana(native[0].original) == word):
            return hira
        return word
    return re.sub(r"[ァ-ヺー]{3,64}", recover, text)

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


def _expand_kana_iteration_marks(text: str) -> str:
    """Expand valid same-script kana repeats, retaining malformed marks.

    Unlike kanji 々, these marks encode voicing explicitly.  An unvoiced
    repeat removes dakuten; a voiced repeat adds it only to a kana that
    supports it.  Expansion preserves offsets (one codepoint per mark).
    """
    out: list[str] = []
    for ch in text:
        if ch in "ゝゞヽヾ" and out:
            previous = out[-1]
            lower, upper = ("ぁ", "ゖ") if ch in "ゝゞ" else ("ァ", "ヶ")
            if lower <= previous <= upper and previous not in "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ":
                base = unicodedata.normalize("NFD", previous)[0]
                repeated = (unicodedata.normalize("NFC", base + "\u3099")
                            if ch in "ゞヾ" else base)
                if len(repeated) == 1:
                    ch = repeated
        out.append(ch)
    return "".join(out)


def _to_katakana(text: str) -> str:
    text = _expand_kana_iteration_marks(unicodedata.normalize("NFKC", text))
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
    lemma: str = ""
    replacement: str | None = None
    # UniDic's third part-of-speech level (地名, 人名, ...).  Excluded from
    # equality: the normalizers compare neighbouring tokens across parses,
    # and a name's level can differ between them without changing the word.
    pos3: str = field(default="", compare=False)
    # A person-name reading for which the dictionary also holds a non-name
    # entry of the same surface (蓮 as Ren or Hasu).  Set by the lattice
    # scan in _prefer_common_noun_readings; informational only.
    ambiguous_name: bool = field(default=False, compare=False)


# Positions in the segment being romanized that no token may cross.  Set by
# _japanese_segment_to_romaji and consulted for every parse of a derived
# analysis string of the same length: where the title switches between
# hiragana and katakana, a derived string that has katakana on both sides
# (a normalizer's katakana candidate) must not fuse the two words
# (スナックさなえ, けもフレこんさーと).  The original string keeps its scripts,
# so mixed-script dictionary words (ヤバい, サボる) are never cut, and
# strings of another length (isolated runs, phrase portions) are unaffected.
_SEGMENT_BOUNDARIES: contextvars.ContextVar[tuple[int, tuple[int, ...]]] = \
    contextvars.ContextVar("segment_boundaries", default=(0, ()))
_SCRIPT_EDGE_RE = re.compile(r"(?<=[ぁ-ゖ])(?=[ァ-ヺ])|(?<=[ァ-ヺ])(?=[ぁ-ゖ])")


def _script_boundaries(segment: str) -> tuple[int, ...]:
    return tuple(m.start() for m in _SCRIPT_EDGE_RE.finditer(segment))


def _parse_nodes(text: str, cuts: tuple[int, ...]) -> list[tuple[str, str, int]]:
    """MeCab nodes as (surface, feature, stat); no token crosses a cut.

    Partial parsing keeps both sides in one lattice with full context; it
    only forbids a token from spanning the cut.  Without cuts, or when the
    lattice API is unavailable (a fake tagger), the plain parse is used.
    """
    if cuts and "\n" not in text and "\t" not in text:
        try:
            lattice = MeCab.Lattice()
            lattice.set_request_type(MeCab.MECAB_PARTIAL)
            edges = (0, *cuts, len(text))
            lattice.set_sentence("\n".join(text[a:b] for a, b in zip(edges, edges[1:])) + "\nEOS\n")
            if _mecab.parse(lattice):
                nodes = []
                node = lattice.bos_node().next
                while node and node.stat != MeCab.MECAB_EOS_NODE:
                    nodes.append((node.surface, node.feature, node.stat))
                    node = node.next
                if "".join(surface for surface, _, _ in nodes) == text:
                    return nodes
        except (AttributeError, NameError, RuntimeError, TypeError):
            pass
    nodes = []
    node = _mecab.parseToNode(text)
    while node:
        if node.surface:
            nodes.append((node.surface, node.feature, node.stat))
        node = node.next
    return nodes


def _read_tokens(text: str, original: str | None = None) -> list[_Token]:
    """Copy MeCab nodes while retaining written spans and surface readings."""
    original = text if original is None else original
    if not text:
        return []
    expanded_original = _expand_kana_iteration_marks(original)
    tokens: list[_Token] = []
    offset = 0
    length, boundaries = _SEGMENT_BOUNDARIES.get()
    cuts = tuple(i for i in boundaries if len(text) == length
                 and "ァ" <= text[i - 1] <= "ヺ" and "ァ" <= text[i] <= "ヺ")
    for node_surface, node_feature, node_stat in _parse_nodes(text, cuts):
        if node_surface:
            node_start = text.index(node_surface, offset)
            offset = node_start + len(node_surface)
            parts = next(csv.reader([node_feature]))
            unknown = node_stat == 1
            # The dictionary separates ・ from the words it knows, but its
            # unknown-word grouping keeps the dot inside one katakana run
            # (ヘカーティア・ラピスラズリ).  Split such a run so each name is
            # read, capitalized and restored on its own, with the dot as
            # the symbol token a known word would have beside it.
            if unknown and "・" in node_surface:
                pieces = [(node_start + m.start(), node_start + m.end())
                          for m in re.finditer(r"・|[^・]+", node_surface)]
            else:
                pieces = [(node_start, offset)]
            for start, end in pieces:
                surface = text[start:end]
                source = original[start:end]
                if surface == "・":
                    tokens.append(_Token(surface, source, surface, "補助記号",
                                         "一般", "記号", "*", start, end))
                    continue
                reading = _get_reading(node_feature)
                if _KANA_ONLY_RE.fullmatch(source):
                    # Kana already specifies its reading, including expressive ー
                    # and v/b distinctions that dictionary entries may normalize.
                    reading = _to_katakana(expanded_original[start:end])
                    # Written は in lexical greetings is pronounced wa even
                    # when the whole greeting is an interjection, not a particle.
                    # Retain all other written vowels and expressive spellings.
                    pronunciation = parts[9] if len(parts) > 9 else ""
                    if (parts[0] == "感動詞" and reading.endswith("ハ")
                            and pronunciation == reading[:-1] + "ワ"):
                        reading = pronunciation
                    elif source in _KATAKANA_OKURIGANA_EXEMPT:
                        reading = _get_reading(node_feature) or source
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
                    start, end, unknown,
                    conjugation_form=parts[5] if len(parts) > 5 else "",
                    lemma=parts[7] if len(parts) > 7 else "",
                    pos3=parts[2] if len(parts) > 2 else "",
                ))
    return _prefer_common_noun_readings(text, tokens)


# How much cheaper (more frequent) a common-noun entry must be than the
# surname entry the path chose before it replaces that reading.  東方's
# noun beats its surnames by about 2400; the known false flips (涼風 as
# Ryoufuu, 三善 as Sanzen) sit below 2000, and 西行, 望月 and 千秋 are
# cheaper as names than as nouns, so they are never touched.
_COMMON_NOUN_COST_MARGIN = 2000


def _prefer_common_noun_readings(text: str, tokens: list[_Token]) -> list[_Token]:
    """Read a two-kanji Sino-Japanese noun as the noun, not as a surname.

    A short title gives the dictionary no context, so 東方 can come out as
    the surnames トウボウ or ヒガシカタ and every new compound built on it
    inherits the error.  When the chosen path used a person-name entry for
    exactly two kanji and the lattice holds a common-noun entry of the same
    surface and Sino-Japanese origin at that position that is clearly the
    more frequent word (``_COMMON_NOUN_COST_MARGIN``), take the noun's
    reading.  Boundaries never change.  Single kanji (蓮), native words
    (涼風 as a name), longer names (西行寺) and names that are themselves
    the frequent word (西行, 望月, 千秋) keep the dictionary's choice: in
    this collection those are right about as often as they are wrong.
    """
    targets = [i for i, t in enumerate(tokens)
               if t.pos3 == "人名" and not t.unknown and t.surface == t.original
               and _KANJI_RE.search(t.surface)]
    if not targets:
        return tokens
    try:
        lattice = MeCab.Lattice()
        lattice.set_sentence(text)
        if not _mecab.parse(lattice):
            return tokens
        for index in targets:
            token = tokens[index]
            name_cost = None
            nouns = []
            node = lattice.begin_nodes(len(text[:token.start].encode("utf-8")))
            while node:
                if node.stat == MeCab.MECAB_NOR_NODE and node.surface == token.surface:
                    parts = next(csv.reader([node.feature]))
                    reading = _get_reading(node.feature)
                    if len(parts) > 12 and parts[2] == "人名":
                        if parts[3] == "姓" and reading == token.reading:
                            name_cost = (node.wcost if name_cost is None
                                         else min(name_cost, node.wcost))
                    elif len(parts) > 12 and reading and reading != token.reading:
                        tokens[index] = token = replace(token, ambiguous_name=True)
                        if (parts[0] == "名詞" and parts[1] == "普通名詞"
                                and parts[12] == "漢"):
                            nouns.append((node.wcost, reading, parts))
                node = node.bnext
            if (name_cost is None or not nouns or len(token.surface) != 2
                    or not all(_KANJI_RE.fullmatch(ch) for ch in token.surface)):
                continue
            cost, reading, parts = min(nouns, key=lambda item: item[0])
            if cost + _COMMON_NOUN_COST_MARGIN <= name_cost:
                tokens[index] = replace(
                    token, reading=reading, sub_pos=parts[1], goshu=parts[12],
                    lemma_reading=parts[6], lemma=parts[7],
                    conjugation_form=parts[5], pos3=parts[2], ambiguous_name=False)
    except (AttributeError, NameError, RuntimeError, TypeError):
        # The lattice API is optional; a fake or older tagger keeps the
        # path's own readings.
        return tokens
    return tokens


@lru_cache(maxsize=8)
def _phrase_pattern(entries: tuple) -> tuple[re.Pattern, dict[str, str]]:
    """Compile written phrases independently of a dictionary's token splits."""
    phrases = {"".join(key): value for key, value in entries if key and all(key)}
    return re.compile("|".join(re.escape(key) for key in
                               sorted(phrases, key=len, reverse=True)) or r"(?!)"), phrases


def _read_reviewed_tokens(analysis: str, original: str, *, use_overrides: bool) -> list[_Token]:
    if not use_overrides or not _PHRASE_OVERRIDES:
        return _read_tokens(analysis, original)
    pattern, phrases = _phrase_pattern(tuple(_PHRASE_OVERRIDES.items()))
    spans = {(m.start(), m.end()): phrases[m.group()]
             for text in (analysis, original) for m in pattern.finditer(text)}
    if not spans:
        return _read_tokens(analysis, original)
    raw = _read_tokens(analysis, original)
    # Short kana names can overlap real auxiliary constructions. A name
    # entry must not turn 見てゐる into "Mi Tewi Ru". Deliberate title puns
    # can still have a complete, reviewed title/phrase override.
    for start, end in list(spans):
        if end - start > 3 or not re.fullmatch(r"[ぁ-ゖ]+", original[start:end]):
            continue
        first = next((i for i, t in enumerate(raw) if t.start == start), None)
        if (first and raw[first].pos == "助詞" and raw[first].sub_pos == "接続助詞"
                and raw[first - 1].end == start and raw[first - 1].pos == "動詞"
                and raw[first - 1].conjugation_form.startswith("連用形")):
            del spans[start, end]
    def portion(start: int, end: int) -> list[_Token]:
        result = []
        for token in raw:
            a, b = max(start, token.start), min(end, token.end)
            if a >= b:
                continue
            if (a, b) == (token.start, token.end):
                result.append(token)
            else:
                result.extend(replace(t, start=t.start + a, end=t.end + a)
                              for t in _read_tokens(analysis[a:b], original[a:b]))
        def fragments(group):
            return sum(t.unknown or (t.pos == "感動詞" and t.sub_pos == "フィラー")
                       for t in group)
        # A newly established name boundary can resolve a neighbouring
        # fragmented word. Keep valid context-sensitive particles as-is.
        if fragments(result) or (len(result) > 1 and _KANA_ONLY_RE.fullmatch(original[start:end])):
            candidate = _read_tokens(_normalize_hiragana_long_vowels(analysis[start:end],
                                                                    use_overrides=use_overrides),
                                     original[start:end])
            if candidate and all(not t.unknown for t in candidate) and (
                    fragments(candidate) < fragments(result)
                    or (len(candidate) == 1 and candidate[0].pos == "名詞")):
                result = [replace(t, start=t.start + start, end=t.end + start) for t in candidate]
        return result
    tokens = []
    end = 0
    for (start, stop), value in sorted(spans.items(), key=lambda p: (p[0][0], -p[0][1])):
        if start < end:
            continue
        tokens.extend(portion(end, start))
        tokens.append(_Token(analysis[start:stop], original[start:stop], "", "名詞",
                             "", "", "", start, stop, replacement=value))
        end = stop
    tokens.extend(portion(end, len(original)))
    return tokens


def _repair_katakana_fragments(segment: str, tokens: list[_Token]) -> list[_Token]:
    """Keep a dictionary-confirmed whole katakana word together phonetically.

    A best parse can prefer ナイ / ツ despite a complete ナイツ entry. A
    whole-word alternative establishes a boundary, not an English spelling;
    competing etymons still disable automatic spelling recovery.
    """
    repairs = {}
    for match in re.finditer(r"[ァ-ヺー]{2,64}", segment):
        group = [t for t in tokens if match.start() <= t.start and t.end <= match.end()]
        if (len(group) < 2 or group[0].start != match.start() or group[-1].end != match.end()
                or any(t.replacement is not None or t.original != t.surface for t in group)):
            continue
        try:
            lattice = MeCab.Lattice()
            lattice.set_sentence(match.group())
            if not _mecab.parse(lattice):
                continue
            node = lattice.begin_nodes(0)
            entries = []
            while node:
                if node.stat == MeCab.MECAB_NOR_NODE and node.surface == match.group():
                    fields = next(csv.reader([node.feature]))
                    if len(fields) > 12 and fields[0] == "名詞":
                        entries.append(fields)
                node = node.bnext
            if not entries:
                if any(t.unknown for t in group) and any(t.pos in ("助詞", "助動詞") for t in group):
                    # A fragmentary native parse is not evidence for spaces
                    # inside an unknown katakana word. Preserve every sound
                    # as one phonetic word, without guessing English.
                    repairs[match.start()] = _Token(match.group(), match.group(), match.group(),
                        "名詞", "普通名詞", "", "", match.start(), match.end(), unknown=True)
                continue
            fields = entries[0]
            lemma = fields[7] if len({f[7] for f in entries}) == 1 else ""
            repairs[match.start()] = _Token(match.group(), match.group(), match.group(),
                fields[0], fields[1], fields[12], fields[6], match.start(), match.end(),
                lemma=lemma)
        except (AttributeError, RuntimeError, TypeError):
            continue
    result = []
    end = 0
    for token in tokens:
        if token.start in repairs:
            result.append(repairs[token.start])
            end = result[-1].end
        elif token.start >= end:
            result.append(token)
    return result


# Regular numeral/counter morphology belongs to the engine, independently of
# title/phrase overrides.  Limit the resolver to counters with reviewed rules.
# See the Japan Foundation's BTS00010 counter table (教科書を作ろう).
_COUNTERS = {
    "本": "ホン", "匹": "ヒキ", "杯": "ハイ", "個": "コ",
    "回": "カイ", "階": "カイ", "曲": "キョク", "冊": "サツ",
    "歳": "サイ", "人": "ニン", "月": "ガツ",
    "番": "バン", "番目": "バンメ", "時間": "ジカン",
    "ヶ月": "カゲツ", "箇月": "カゲツ", "か月": "カゲツ", "カ月": "カゲツ",
    "つ": "ツ",
}
# The native series is irregular and stops at nine (ten is 十 alone, とお).
_NATIVE_TSU_READINGS = {
    1: "ヒトツ", 2: "フタツ", 3: "ミッツ", 4: "ヨッツ", 5: "イツツ",
    6: "ムッツ", 7: "ナナツ", 8: "ヤッツ", 9: "ココノツ",
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
    if counter == "つ":
        return _NATIVE_TSU_READINGS.get(number)
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
    elif counter == "時間":
        for ending, replacement in (("ヨン", "ヨ"), ("キュウ", "ク")):
            if stem.endswith(ending):
                stem = stem[:-len(ending)] + replacement
                break
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


# Sino-Japanese numeral sandhi (一/六/八/十 → イッ/ロッ/ハッ/ジッ) only occurs
# before k/s/t/p and their palatal or voiced variants.
_NUMERAL_GEMINATION_ONSETS = "kstpcgzdbj"


def _repair_numeral_allomorphs(tokens: list[_Token]) -> list[_Token]:
    """Use a numeral's lemma reading where its pre-geminate form cannot apply.

    UniDic can give 一 the reading イッ before 輪 (雲居一輪), but a sokuon
    cannot precede r: the plain reading イチ applies, giving Ichirin rather
    than Irrin.  Only numerals are repaired; a verb's っ-stem is correct.
    """
    result = list(tokens)
    for i, token in enumerate(result):
        if (token.sub_pos != "数詞" or not token.reading.endswith("ッ")
                or not _KANA_ONLY_RE.fullmatch(token.lemma_reading)
                or token.lemma_reading.endswith("ッ")):
            continue
        following = result[i + 1] if i + 1 < len(result) else None
        if following is not None and following.start == token.end:
            onset, _ = _kana_syllable(_to_katakana(following.reading), 0)
            if onset and onset[0] in _NUMERAL_GEMINATION_ONSETS:
                continue
        result[i] = replace(token, reading=token.lemma_reading)
    return result


def _kept_as_digits(token: _Token) -> bool:
    """A numeral the engine renders as digits rather than as a Japanese word."""
    return (token.sub_pos == "数詞" and token.reading.isascii()
            and token.reading.isdigit())


def _restore_counter_base_readings(
    tokens: list[_Token], number_spans: dict[int, tuple[int, str]],
) -> list[_Token]:
    """After a numeral kept as digits, read its counter in the base form.

    UniDic gives 分間 the assimilated reading プンカン after 3, but digits
    carry no sound to assimilate to: 3分間 is 3 Funkan, not 3 Punkan.
    Counters with reviewed rules are read as complete units instead.
    """
    result = list(tokens)
    for i, token in enumerate(result[:-1]):
        following = result[i + 1]
        if (not _kept_as_digits(token) or i in number_spans
                or following.start != token.end
                or following.pos not in ("名詞", "接尾辞")
                or following.conjugation_form not in ("", "*")
                or following.lemma_reading == following.reading
                or not _KANA_ONLY_RE.fullmatch(following.lemma_reading)):
            continue
        result[i + 1] = replace(following, reading=following.lemma_reading)
    return result


@dataclass
class _RenderedWord:
    tokens: list[_Token]
    text: str
    reading: str
    opaque: bool = False  # a reviewed replacement is already romanized


# Reading keys this short (rin, doa, rein) coincide with the readings of
# kanji too easily to apply to a run of several words that contains any.
_SHORT_LOANWORD_KEY = 4


def _loanword_match(tokens: list[_Token],
                    dots: frozenset[int] = frozenset()) -> str | None:
    """Match a reviewed spelling to a run of tokens.

    ``dots`` holds the segment positions of ・ symbols already removed from
    ``tokens``: a run may cross them, trying its key with and without the
    dot (イントゥ・バックドア).  Otherwise the tokens must be adjacent.
    """
    if not tokens or any(t.replacement is not None for t in tokens):
        return None
    gaps = []
    for a, b in zip(tokens, tokens[1:]):
        if a.end != b.start and not all(i in dots for i in range(a.end, b.start)):
            return None
        gaps.append("・" * (b.start - a.end))
    gaps.append("")
    written = "".join(t.original for t in tokens)
    if any(t.pos == "助詞" for t in tokens) and not (
            re.fullmatch(r"[ァ-ヺー]+", written)
            or (_KANA_ONLY_RE.fullmatch(written)
                and any(ch in "ぁぃぅぇぉゃゅょ" for ch in written))):
        return None
    readings = [t.reading for t in tokens]
    keys = [_kana_to_romaji("".join(readings)),
            "".join(_kana_to_romaji(r) for r in readings)]
    if any(gaps):
        keys += [_kana_to_romaji("".join(r + g for r, g in zip(readings, gaps))),
                 "".join(_kana_to_romaji(r) + g for r, g in zip(readings, gaps))]
    # The table spells katakana words, and kana spellings of the same words
    # (まじかる, ぬえ) read no differently.  A kanji-written native or
    # Sino-Japanese word whose reading merely coincides with a borrowing
    # (減る/ヘル, 帰路/キロ, 瑠奈/ルナ, 三輪車) keeps its Japanese reading,
    # unless the dictionary marks the word foreign (煙草) or as a place
    # name, whose spelling is conventional (上海/Shanghai).  A run of
    # several words containing kanji may still match a long key.
    eligible = (not _KANJI_RE.search(written)
                or all(t.goshu == "外" for t in tokens)
                or (len(tokens) == 1 and tokens[0].sub_pos == "固有名詞"
                    and tokens[0].pos3 == "地名"))
    # Retain compatibility with foreign-word keys built from older UniDic
    # lemma spellings (e.g. ボヤージュ / ヴォヤージュ), without normalizing
    # native colloquial words such as あたし back into their lemmas.
    for key in keys:
        key = key.lower().strip()
        if key in _LOANWORDS_MAP and (
                eligible or (len(tokens) > 1 and len(key) > _SHORT_LOANWORD_KEY)):
            return _LOANWORDS_MAP[key]
    if len(tokens) == 1 and tokens[0].goshu == "外":
        token = tokens[0]
        base = _LOANWORDS_MAP.get(_kana_to_romaji(token.lemma_reading).lower())
        if base:
            return _written_loanword_form(token.reading, token.lemma_reading, base)
    return None


def _written_loanword_form(reading: str, lemma: str, spelling: str) -> str | None:
    """Keep equivalent v/b spellings and explicit plurals, never erase a form."""
    def comparable(kana: str) -> str:
        for a, b in (("ヴァ", "バ"), ("ヴィ", "ビ"), ("ヴェ", "ベ"),
                     ("ヴォ", "ボ"), ("ヴ", "ブ")):
            kana = kana.replace(a, b)
        return _kana_to_romaji(kana)
    if comparable(reading) == comparable(lemma):
        return spelling
    # Japanese commonly omits a borrowing's final long-vowel mark
    # (メロディ / メロディー). Do not do the reverse: adding length can
    # distinguish a proper name from a common word, e.g. ミニ / ミニー.
    if lemma.endswith("ー") and comparable(reading) == comparable(lemma[:-1]):
        return spelling
    plural = (reading in {lemma + "ズ", lemma + "ス"}
              or (lemma.endswith("ト") and reading == lemma[:-1] + "ツ"))
    if plural and re.fullmatch(r"[A-Za-z]+", spelling):
        if spelling.lower().endswith("y") and len(spelling) > 1 and spelling[-2].lower() not in "aeiou":
            return spelling[:-1] + "ies"
        return spelling + ("es" if spelling.lower().endswith(("s", "x", "z", "ch", "sh")) else "s")
    return None


def _dictionary_loanwords(segment: str, tokens: list[_Token]) -> dict[int, str]:
    """Restore a complete foreign-word segment from UniDic's Latin lemmas.

    UniDic annotates e.g. ローズマリー-rosemary.  These are etymons, not
    translations or guaranteed spellings of a title.  Require an entirely
    known katakana segment and exact written lemma forms; do not partly
    anglicize mixed Japanese, unfamiliar names, or altered/plural forms.
    Reject expanding a short borrowing into a longer etymon (アニメ-animation,
    テレビ-television).  This conservative length check can decline valid
    spellings too; the fallback remains the complete written kana reading.
    Homophones with competing foreign lemmas (シック-sick/chic) also stay
    phonetic.  No companion-data tables are used here.
    """
    if not tokens or not re.fullmatch(r"[ァ-ヺー・]+", segment):
        return {}
    replacements = {}
    for index, token in enumerate(tokens):
        if (token.unknown or token.goshu != "外"
                or token.pos not in ("名詞", "形状詞")
                or token.conjugation_form not in ("", "*")
                or token.original != token.surface):
            return {}
        match = re.fullmatch(r"([ァ-ヺー]+)-([A-Za-z]{2,})", token.lemma)
        if match is None or match[1] != token.original:
            return {}
        spelling = match[2]
        # Capitalized etymons often denote brands/drugs/proper names, not
        # the author's English word (e.g. a medicine for a fragile title).
        if not spelling.islower():
            return {}
        # Very short readings can be abbreviations or native interjections
        # even in isolation (キャン in camping titles is not English can).
        if len(re.sub(r"[ァィゥェォャュョ]", "", token.original)) < 3:
            return {}
        # An adjectival etymon need not be the borrowed noun. English -ic
        # has a final /k/; a written borrowing without it is not equivalent.
        if spelling.endswith("ic") and not token.original.endswith("ク"):
            return {}
        phonetic = _kana_to_romaji(token.original)
        if len(spelling) > sum(ch.isascii() and ch.isalpha() for ch in phonetic):
            return {}
        replacements[index] = spelling[0].upper() + spelling[1:]

    # The best parse alone cannot settle an English spelling.  Inspect all
    # dictionary candidates for each exact written span, not just N-best
    # sentences (whose arbitrary cutoff can miss a competing etymon).
    # MeCab indexes lattice positions by UTF-8 bytes, not Python characters.
    try:
        lattice = MeCab.Lattice()
        lattice.set_sentence(segment)
        if not _mecab.parse(lattice):
            return {}
        for token in tokens:
            candidate = lattice.begin_nodes(len(segment[:token.start].encode("utf-8")))
            found = False
            while candidate:
                if (candidate.stat == MeCab.MECAB_NOR_NODE
                        and len(candidate.surface) > len(token.surface)
                        and segment[token.start:].startswith(candidate.surface)
                        and "・" not in candidate.surface):
                    # Another lexical entry crosses the proposed English
                    # boundary (セイ/バー, スリー/プレス). Do not invent words.
                    return {}
                if candidate.stat == MeCab.MECAB_NOR_NODE and candidate.surface == token.surface:
                    parts = next(csv.reader([candidate.feature]))
                    if len(parts) > 12 and parts[12] == "外":
                        if parts[7] != token.lemma:
                            return {}
                        found = True
                candidate = candidate.bnext
            if not found:
                return {}
    except (AttributeError, RuntimeError, TypeError):
        # Restoration is optional; an unavailable lattice API must not make
        # otherwise valid phonetic romanization fail or count as evidence.
        return {}
    return replacements


def _automatic_loanword_spans(segment: str, tokens: list[_Token], reserved: set[int]) -> dict[int, str]:
    """Evaluate complete katakana runs between grammar or reviewed boundaries.

    A failed run is never retried at its internal token boundaries. A known
    reviewed word, however, supplies a real boundary for its neighbours.
    """
    replacements = {}
    i = 0
    while i < len(tokens):
        if i in reserved or not re.fullmatch(r"[ァ-ヺー]+", tokens[i].original):
            i += 1
            continue
        end = i + 1
        while (end < len(tokens) and end not in reserved
               and re.fullmatch(r"[ァ-ヺー]+", tokens[end].original)
               and segment[tokens[end - 1].end:tokens[end].start] in ("", "・")
               # An unknown name on either side of a ・ is its own word;
               # it must not make a known neighbour (サロン・ド・…) fail.
               and not (segment[tokens[end - 1].end:tokens[end].start]
                        and (tokens[end].unknown or tokens[end - 1].unknown))):
            end += 1
        start = tokens[i].start
        # Japanese derivational suffixes belong to the complete Japanese
        # word; translating only the stem produces hybrids like Campjou
        # and Metalppoi. Reviewed replacements can still specify a spelling.
        if (end < len(tokens) and tokens[end].pos == "接尾辞"
                and tokens[end - 1].end == tokens[end].start):
            i = end
            continue
        # A tiny reviewed fragment is not reliable evidence for an English
        # boundary inside one katakana run: リン + ゲージ need not be Rin Gauge.
        adjacent_reviewed = []
        if i and i - 1 in reserved and tokens[i - 1].end == start:
            a = i - 1
            while a and a - 1 in reserved and tokens[a - 1].end == tokens[a].start:
                a -= 1
            adjacent_reviewed.append(segment[tokens[a].start:start])
        if end < len(tokens) and end in reserved and tokens[end].start == tokens[end - 1].end:
            b = end + 1
            while b < len(tokens) and b in reserved and tokens[b - 1].end == tokens[b].start:
                b += 1
            adjacent_reviewed.append(segment[tokens[end].start:tokens[b - 1].end])
        if any(re.fullmatch(r"[ァ-ヺー]{1,2}", value) for value in adjacent_reviewed):
            i = end
            continue
        group = [replace(t, start=t.start - start, end=t.end - start) for t in tokens[i:end]]
        values = _dictionary_loanwords(segment[start:tokens[end - 1].end], group)
        replacements.update((i + key, value) for key, value in values.items())
        i = end
    return replacements


def _splits_kana_mora(left: _Token, right: _Token) -> bool:
    """A tokenizer boundary must not split a written kana digraph/trigraph."""
    if left.end != right.start or not right.original:
        return False
    if right.original[0] in "ゝゞヽヾ":
        # Readings were expanded with full original context in _read_tokens;
        # a valid repeat remains part of the preceding written kana word.
        return bool(right.reading and right.reading[0] not in "ゝゞヽヾ"
                    and _KANA_ONLY_RE.fullmatch(left.original[-1:]))
    before = _to_katakana(left.original[-2:])
    after = _to_katakana(right.original[:2])
    if not after or after[0] not in "ァィゥェォャュョヮ":
        return False
    # Require literal kana on both sides; do not invent combinations between
    # a kanji's reading and a separately written small kana.
    return any(before[-n:] + after[:m] in _KATAKANA_ROMAJI
               for n in (1, 2) for m in (1, 2)
               if len(before) >= n and len(after) >= m)


def _rendaku_bound(token: _Token) -> bool:
    """True when a word's surface reading is the voiced form of its own lemma.

    Rendaku only happens inside a word, so 塚 read ヅカ, 川 read ガワ or
    囃子 read バヤシ is bound to the element before it.  Compare only the
    first kana and require the rest to match, so an unrelated voiced
    reading (a different lemma) is not taken as evidence.
    """
    if not token.reading or not token.lemma_reading:
        return False
    first = unicodedata.normalize("NFD", token.reading[0])
    return (len(first) == 2 and first[1] in "\u3099\u309a"
            and token.lemma_reading[0] == first[0]
            and token.reading[1:] == token.lemma_reading[1:])


# Old-form (kyūjitai) and other variant kanji paired with the modern form
# UniDic indexes.  Only the analysis string is rewritten; the title's own
# spelling is never changed.  龍 is deliberately absent: modern titles use it
# as an ordinary character (蒼龍 Souryuu) and UniDic reads it well.  The
# simplified Chinese forms that a few reviewed spelling aliases map per
# title are also absent: mapping them here would turn Chinese-language
# titles into Japanese sort keys instead of leaving them unresolved.
_KANJI_VARIANT_PAIRS = (
    "亞亜惡悪壓圧圍囲爲為醫医壹壱隱隠榮栄營営衞衛驛駅圓円緣縁艷艶鹽塩奧奥應応橫横歐欧毆殴黃黄溫温穩穏"
    "假仮價価畫画會会懷懐繪絵壞壊槪概擴拡殼殻覺覚學学嶽岳樂楽渴渇勸勧卷巻寬寛歡歓罐缶觀観關関陷陥"
    "巖巌顏顔氣気旣既歸帰龜亀僞偽戲戯犧犠舊旧據拠擧挙虛虚峽峡挾挟狹狭鄕郷鄉郷曉暁區区驅駆勳勲薰薫"
    "徑径惠恵揭掲溪渓經経繼継莖茎螢蛍輕軽鷄鶏藝芸擊撃缺欠硏研縣県儉倹劍剣險険圈圏檢検權権獻献驗験"
    "嚴厳效効廣広恆恒鑛鉱號号國国黑黒濟済碎砕齋斎劑剤櫻桜雜雑參参慘惨棧桟蠶蚕贊賛殘残絲糸齒歯兒児"
    "辭辞濕湿實実寫写釋釈壽寿收収從従澁渋獸獣縱縦肅粛處処緖緒敍叙將将稱称涉渉燒焼證証奬奨條条淨浄"
    "狀状疊畳孃嬢讓譲釀醸囑嘱觸触寢寝愼慎晉晋眞真盡尽圖図粹粋醉酔隨随髓髄數数樞枢瀨瀬聲声靜静齊斉"
    "攝摂竊窃專専淺浅戰戦踐践錢銭潛潜纖繊禪禅雙双壯壮搜捜插挿爭争巢巣莊荘瘦痩裝装騷騒增増藏蔵臟臓"
    "卽即屬属續続墮堕對対體体帶帯滯滞臺台瀧滝擇択澤沢單単擔担膽胆團団彈弾斷断癡痴遲遅晝昼蟲虫鑄鋳"
    "廳庁徵徴聽聴敕勅鎭鎮遞逓鐵鉄點点轉転傳伝黨党盜盗燈灯當当鬪闘德徳獨独讀読屆届繩縄貳弐惱悩腦脳"
    "霸覇廢廃拜拝賣売麥麦發発髮髪拔抜晚晩蠻蛮祕秘濱浜拂払佛仏倂併竝並變変邊辺步歩寶宝豐豊飜翻每毎"
    "萬万麵麺默黙彌弥譯訳藥薬與与豫予餘余譽誉搖揺樣様謠謡來来賴頼亂乱覽覧獵猟綠緑淚涙壘塁禮礼"
    "勵励戾戻靈霊齡齢曆暦歷歴戀恋鍊錬爐炉勞労郞郎樓楼錄録灣湾遙遥彥彦說説靑青淸清槇槙"
)
_KANJI_VARIANTS = {ord(old): new for old, new in
                   zip(_KANJI_VARIANT_PAIRS[::2], _KANJI_VARIANT_PAIRS[1::2]) if old != new}


def _modernize_variant_kanji(text: str) -> str:
    """Analyze old-form kanji through their modern forms when that helps.

    A title written with kyūjitai is read kanji by kanji or not at all
    (天體觀測 as Ten Tei Kan Soku, 鄉 unresolved).  Rewriting the analysis
    string with modern forms lets the dictionary see the compound.  The
    rewrite is kept only when the parse improves: fewer characters in unknown words, or
    the same with fewer tokens, or an unchanged parse that still contains
    an unknown word.  So a word the dictionary already knows in its old
    form (櫻 before 月夜, 戀 before 獄) keeps its own reading rather
    than a different split of the modern spelling.
    """
    mapped = text.translate(_KANJI_VARIANTS)
    if mapped == text:
        return text
    def score(tokens: list[_Token]) -> tuple[int, int]:
        return sum(len(t.surface) for t in tokens if t.unknown), len(tokens)
    before, after = score(_read_tokens(text)), score(_read_tokens(mapped))
    if after < before or (after == before and before[0]):
        return mapped
    return text


# Address honorifics are written hyphenated after the name (Reimu-san,
# Marisa-chan, Kami-sama) rather than fused into it.  Keyed by written form
# with the reading that makes it an honorific (君 as クン, 殿 as ドノ).
_HONORIFIC_SUFFIXES = {"さん": "サン", "ちゃん": "チャン", "くん": "クン", "君": "クン",
                       "さま": "サマ", "様": "サマ", "殿": "ドノ"}


_CLASSICAL_ADJECTIVE_RE = re.compile(rf'[{_KANJI_CHARS}]+[ぁ-ゖ]{{0,16}}き')


def _repair_classical_adjectives(
    analysis: str, original: str, tokens: list[_Token], *, use_overrides: bool,
) -> list[_Token]:
    """Recover fragmented classical -ki adjectives using dictionary evidence.

    A title's following noun can make UniDic parse 懐かしき as 懐/か/しき.
    Try its modern -i spelling in the same sentence, accepting it only when
    the dictionary recognizes the entire span as one inflected adjective.
    This is not a kanji-reading guess; valid existing analyses and reviewed
    phrases win, and written gaps or katakana endings are never rewritten.
    """
    repaired: dict[int, list[_Token]] = {}
    for match in _CLASSICAL_ADJECTIVE_RE.finditer(original):
        start, end = match.span()
        group = [t for t in tokens if t.start < end and t.end > start]
        if (len(group) < 2 or group[0].start != start
                or any(t.replacement is not None for t in group)
                or (group[-1].end == end and any(t.pos == "形容詞" for t in group))
                or any(t.original != t.surface for t in group)):
            continue
        if (group[-1].end > end and not group[-1].unknown
                and group[-1].pos not in ("助詞", "助動詞", "補助記号")
                and not any(t.pos == "形容詞" and t.conjugation_form.startswith("語幹")
                            for t in group[:-1])):
            continue
        if use_overrides and any(
            (tuple(t.surface for t in tokens[i:i + size]) in _PHRASE_OVERRIDES
             or tuple(t.original for t in tokens[i:i + size]) in _PHRASE_OVERRIDES)
            and tokens[i].start < end and tokens[i + size - 1].end > start
            for size in range(2, 7) for i in range(len(tokens) - size + 1)
        ):
            continue
        if use_overrides and any(
            tokens[i].start < end and tokens[i + size - 1].end > start
            and _loanword_match(tokens[i:i + size]) is not None
            for size in range(1, 5) for i in range(len(tokens) - size + 1)
        ):
            continue
        candidate = analysis[:end - 1] + "い" + analysis[end:]
        alternatives = _read_reviewed_tokens(candidate, original, use_overrides=use_overrides)
        adjective = next((t for t in alternatives
                          if t.start == start and t.end == end), None)
        if (adjective is None or adjective.unknown or adjective.pos != "形容詞"
                or not adjective.reading.endswith("イ")):
            continue
        # Reanalysis is evidence for this span only.  Reject it if it changes
        # the boundaries, identity or grammatical role of surrounding words.
        # A token can straddle the adjective's end (古 / きに / ゃん…).
        # Reparse only that overlapping tail with its unchanged following
        # text; completely disjoint words must still remain identical.
        boundary = group[-1].end
        if boundary > end:
            while boundary < len(original) and _KANA_ONLY_RE.fullmatch(original[boundary]):
                boundary += 1
        def neighbours(group):
            # Alternative readings of the *same* neighbouring lemma do not
            # invalidate the adjective. Preserve the original reading when
            # assembling the result; changes to boundaries/POS still veto.
            return [replace(t, reading="", lemma_reading="", goshu="") for t in group
                    if t.end <= start or t.start >= boundary]
        if neighbours(tokens) != neighbours(alternatives):
            continue
        repaired[start] = [replace(adjective, surface=adjective.original,
                                   reading=adjective.reading[:-1] + "キ",
                                   conjugation_form="連体形-一般")]
        repaired[start].extend(t for t in alternatives if end <= t.start < boundary)
    result = []
    covered_until = 0
    for token in tokens:
        if token.start in repaired:
            group = repaired[token.start]
            result.extend(group)
            covered_until = group[-1].end
        elif token.start >= covered_until:
            result.append(token)
    return result


def _japanese_segment_to_romaji(
    segment: str, first_in_title: bool = False, *, use_overrides: bool = True,
    restore_loanwords: bool = True, report: list[dict] | None = None,
) -> str:
    """Romanize one Japanese segment; see :func:`_romanize_segment`.

    Records the segment's hiragana/katakana edges as parse boundaries
    (``_SEGMENT_BOUNDARIES``) for the duration of the call.
    """
    token = _SEGMENT_BOUNDARIES.set((len(segment), _script_boundaries(segment)))
    try:
        return _romanize_segment(segment, first_in_title, use_overrides=use_overrides,
                                 restore_loanwords=restore_loanwords, report=report)
    finally:
        _SEGMENT_BOUNDARIES.reset(token)


def _romanize_segment(
    segment: str, first_in_title: bool = False, *, use_overrides: bool = True,
    restore_loanwords: bool = True, report: list[dict] | None = None,
) -> str:
    """Analyze readings before applying replacements and word-boundary rules.

    ``report``, when given, receives one dict per rendered word (see
    :func:`explain_romaji`) so callers can tell which words came from a
    reviewed table, a numeral rule, a UniDic etymon or a guessed reading.
    """
    analysis = _normalize_hiragana_long_vowels(_normalize_native_katakana(
        _normalize_katakana_okurigana(_modernize_variant_kanji(
            _expand_kana_iteration_marks(segment)))), use_overrides=use_overrides)
    tokens = _repair_classical_adjectives(
        analysis, segment, _read_reviewed_tokens(analysis, segment, use_overrides=use_overrides),
        use_overrides=use_overrides)
    tokens = _repair_katakana_fragments(segment, tokens)
    dots = frozenset(t.start for t in tokens if t.surface == "・")
    tokens = _repair_numeral_allomorphs([t for t in tokens if t.surface != "・"])
    number_spans = _number_counter_spans(segment, tokens)
    tokens = _restore_counter_base_readings(tokens, number_spans)
    phrase_spans: dict[int, tuple[int, str]] = {}
    reserved: set[int] = set()
    i = 0
    while use_overrides and i < len(tokens):
        if tokens[i].replacement is not None:
            phrase_spans[i] = i + 1, tokens[i].replacement
            reserved.add(i)
        i += 1
    # Resolve reviewed loanwords before optional dictionary restoration, so
    # an opaque prefix such as Sleepless cannot prevent the independently
    # known following Escape from being restored (or be split itself).
    i = 0
    while use_overrides and i < len(tokens):
        if i in phrase_spans:
            i = phrase_spans[i][0]
            continue
        if i in number_spans:
            i = number_spans[i][0]
            continue
        for span in range(min(16, len(tokens) - i), 0, -1):
            if reserved.intersection(range(i, i + span)):
                continue
            replacement = _loanword_match(tokens[i:i + span], dots)
            if replacement is not None:
                phrase_spans[i] = i + span, replacement
                reserved.update(range(i, i + span))
                i += span - 1
                break
        i += 1
    dictionary_words = (_automatic_loanword_spans(segment, tokens, reserved)
                        if restore_loanwords else {})
    words: list[_RenderedWord] = []
    entries: list[tuple[dict, list[_Token]]] = []

    def note(group: list[_Token], romaji: str, reading: str, source: str,
             flags: tuple[str, ...] = ()) -> None:
        if report is not None:
            entry = {"written": segment[group[0].start:group[-1].end],
                     "romaji": romaji, "reading": reading, "source": source,
                     "flags": list(flags)}
            report.append(entry)
            entries.append((entry, group))

    i = 0
    while i < len(tokens):
        replacement = None
        end = i + 1
        if i in phrase_spans:
            end, replacement = phrase_spans[i]
            group = tokens[i:end]
            reading = "".join(t.reading for t in group)
            words.append(_RenderedWord(group, replacement, reading, True))
            note(group, replacement, reading,
                 "phrase" if group[0].replacement is not None else "loanword")
            i = end
            continue
        if i in number_spans and not reserved.intersection(range(i, number_spans[i][0])):
            end, reading = number_spans[i]
            words.append(_RenderedWord(tokens[i:end], _kana_to_romaji(reading).capitalize(), reading))
            note(tokens[i:end], words[-1].text, reading, "counter")
            i = end
            continue
        if replacement is None and i in dictionary_words:
            replacement = dictionary_words[i]
        if replacement is None:
            while (end < len(tokens) and end not in reserved
                   and _splits_kana_mora(tokens[end - 1], tokens[end])
                   and not (use_overrides and any(
                       _loanword_match(tokens[end:end + span]) is not None
                       for span in range(1, min(4, len(tokens) - end) + 1)))):
                end += 1
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
            elif (token.pos == "助動詞" and token.lemma_reading == "ダ"
                  and token.surface in ("な", "に", "で") and i > 0
                  and tokens[i - 1].pos == "形状詞"
                  and tokens[i - 1].end == token.start):
                # UniDic splits the copula off a na-adjective.  These forms
                # function like particles in a title, not capitalized nouns.
                pass
            elif token.pos != "接尾辞" or i == 0 or _kept_as_digits(tokens[i - 1]):
                # A suffix is lowercased when joined to its stem; after a
                # numeral kept as digits it stands alone (10 Tsu, 3 Ka).
                word = word.capitalize()
        else:
            word = replacement
        words.append(_RenderedWord(group, word, reading, replacement is not None))
        if replacement is not None:
            note(group, word, reading, "etymon", ("etymon",))
        else:
            flags = []
            if any(t.unknown and _KANJI_RE.search(t.original) for t in group):
                flags.append("guessed")
            elif any(t.unknown and _JP_RE.search(t.original) for t in group):
                # Kana outside the dictionary reads phonetically; the letters
                # are certain, only a loanword spelling could be missing.
                flags.append("unknown")
            if any(t.ambiguous_name for t in group):
                flags.append("name")
            note(group, word, reading, "dictionary", tuple(flags))
        i = end
    # A run of single kanji each read as its own dictionary word is the
    # usual shape of a name or compound the dictionary does not know
    # (比那名居 as Hi Ano Mei Kyo); the letters may be right by chance.
    def lone_kanji(entry: dict, group: list[_Token]) -> bool:
        return (bool(group) and entry["source"] == "dictionary" and len(group) == 1
                and len(group[0].original) == 1
                and bool(_KANJI_RE.fullmatch(group[0].original))
                and group[0].sub_pos != "数詞"
                and group[0].pos not in ("助詞", "助動詞", "補助記号", "記号"))

    run: list[tuple[dict, list[_Token]]] = []
    for entry, group in entries + [({}, [])]:
        if lone_kanji(entry, group) and (not run or run[-1][1][-1].end == group[0].start):
            run.append((entry, group))
            continue
        if len(run) >= 3:
            for item, _ in run:
                item["flags"].append("fragments")
        run = [(entry, group)] if lone_kanji(entry, group) else []

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
        # A numeral kept as digits offers no sound for a suffix to attach
        # to; a counter after it is its own word, as a noun already is
        # (3 Byou, 01 Ban): 10 Tsu rather than 10tsu.
        after_digits = adjacent and previous.text.isascii() and previous.text.isdigit()
        merge = bool(adjacent and (
            (current.pos == "接尾辞" and not after_digits) or (
                (current.pos == "助動詞" or (
                    current.sub_pos == "接続助詞"
                    and current.surface in ("て", "で", "ば", "ちゃ", "じゃ")))
                and previous.tokens[-1].pos in inflecting)))
        if (adjacent and previous is not None and not previous.opaque and not word.opaque
                and previous.tokens[-1].pos == "助動詞"
                and previous.tokens[-1].lemma_reading == "ダ"
                and previous.tokens[-1].surface == "だ"
                and current.pos == "助詞" and current.surface == "から"):
            # Copula + kara forms dakara; ordinary verbs still keep kara
            # separate (imasu kara, itta kara).
            merge = True
        if (adjacent and previous is not None
                and not previous.opaque and not word.opaque
                and previous.tokens[-1].pos == "接頭辞"
                and previous.tokens[-1].reading in ("オ", "ゴ")
                and previous.tokens[-1].original in ("お", "ご", "御")
                and current.pos in ("名詞", "動詞", "形容詞", "形状詞")):
            merge = True
        if (adjacent and previous is not None
                and not previous.opaque and not word.opaque):
            head = previous.tokens[-1]
            # A prefix belongs to the word it modifies (大妖精, 無条件,
            # 超新星), mirroring the suffix merge above.  The ordinal 第
            # stays its own word (Dai Ichi, Dai 8 Ban), digits never take
            # a prefix sound, and a lone kana after a prefix is more likely
            # a broken name (新ちゆり) than its stem.
            if (head.pos == "接頭辞" and not after_digits and head.original != "第"
                    and current.pos in ("名詞", "形状詞", "動詞", "形容詞")
                    and current.sub_pos != "数詞" and not current.unknown
                    and not current.original[:1].isdigit()
                    and not (len(current.original) == 1
                             and _KANA_ONLY_RE.fullmatch(current.original))):
                merge = True
            # Rendaku is evidence of a compound (無縁塚, 三途川, ほたる囃子):
            # UniDic's short units split it, but the voiced reading can
            # only occur word-internally.
            if (current.pos in ("名詞", "接尾辞", "形状詞")
                    and head.pos in ("名詞", "接尾辞", "形状詞", "接頭辞")
                    and not after_digits and _rendaku_bound(current)):
                merge = True
        merge = merge or index in contracted_boundaries
        addition = word.text
        if (adjacent and previous is not None and not word.opaque and not after_digits
                and len(word.tokens) == 1
                and _HONORIFIC_SUFFIXES.get(current.original) == current.reading
                and (current.pos == "接尾辞"
                     or (current.pos == "名詞" and (previous.opaque
                                                  or previous.tokens[-1].sub_pos == "固有名詞")))
                and (previous.opaque
                     or previous.tokens[-1].pos in ("名詞", "代名詞", "接尾辞", "形状詞"))
                and not previous.reading.endswith(("ッ", "っ"))):
            # A geminate before the suffix is a word of its own (おっさん,
            # 坊っちゃん), not a name plus honorific.
            merge = True
            addition = "-" + addition.lower()
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
            if (word.reading.startswith(("ッ", "っ"))
                    and _KANA_ONLY_RE.fullmatch(previous.tokens[-1].original)
                    and current.lemma == "と"):
                merge = True
            if (word.reading.startswith("ー")
                    and (not word.reading.strip("ー")
                         or _KANA_ONLY_RE.fullmatch(previous.tokens[-1].original[-1:]))
                    and result and result[-1].lower() in "aeiou"):
                # Extend the established bare-mark handling (夢ーー) to
                # mixed tokens only after written kana. After bare kanji,
                # a mixed token may be a separator (子守唄ーユカウラー).
                count = len(word.reading) - len(word.reading.lstrip("ー"))
                addition = result[-1].lower() * count + _kana_to_romaji(word.reading[count:])
                merge = True
            if (merge and previous.reading.endswith(("ン", "ん"))
                    and result.lower().endswith("n") and addition
                    and addition[0].lower() in "aeiouy"):
                result += "'"
        if merge and not word.opaque:
            addition = addition.lower()
        elif merge and addition[:1].isupper() and not addition.isupper():
            # A reviewed spelling joined to the preceding fragment must not
            # leave a capital inside the word (Real + Ism); acronyms stay.
            addition = addition[0].lower() + addition[1:]
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


def _decoration_spans(text: str):
    """Protect unmistakable faces/gestures, not arbitrary unconverted kana."""
    for match in re.finditer(r"\([^()\n]{1,32}\)|[oO]彡[\u3099\u309a゜°]*", text):
        value = match.group()
        if value.startswith(("o彡", "O彡")) or (
                any(ch in value for ch in "∀ωД⊿益ಠ")
                and not re.search(r"[A-Za-z0-9ぁ-ゖァ-ヺ]", value)
                and not _KANJI_RE.search(value.replace("益", ""))):
            yield match.start(), match.end(), value, True


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
    if not output.strip():
        return True
    protected_count = sum(end - start for start, end, _, _ in _masking_circle_spans(
        unicodedata.normalize("NFKC", original)))
    if output.count("〇") == protected_count:
        output = output.replace("〇", "")
    for _, _, value, _ in _decoration_spans(unicodedata.normalize("NFKC", original)):
        output = output.replace(value, "", 1)
    # A ・ only survives inside an unread word; between words it is dropped.
    return has_japanese(output) or "・" in output

def to_romaji(text: str, *, use_overrides: bool = True,
              restore_loanwords: bool = True,
              report: list[dict] | None = None) -> str:
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
    Set ``use_overrides=False`` to evaluate the base engine with all companion
    title, spelling, phrase and loanword tables disabled.  This is local to
    the call; it never mutates the shared tables or changes file-tagging policy.
    Complete foreign katakana runs may use Latin spellings provided by
    UniDic, including runs bounded by Japanese grammar or a sufficiently
    long reviewed replacement. Short ambiguous fragments, competing word
    boundaries/etymons and Japanese derivational suffixes stay phonetic.
    This spelling policy cannot guarantee an author's intended wordplay.
    Set ``restore_loanwords=False`` to retain
    phonetic kana output from the engine (combine with ``use_overrides=False``
    to also exclude reviewed spellings from the companion data).
    ``report`` collects one dict per rendered word; :func:`explain_romaji`
    is the convenient wrapper.
    """
    if not MECAB_AVAILABLE:
        return text

    # Title-level override (exact match on the full input)
    if use_overrides and text in _TITLE_OVERRIDES:
        if report is not None:
            report.append({"written": text, "romaji": _TITLE_OVERRIDES[text],
                           "reading": "", "source": "title", "flags": []})
        return _TITLE_OVERRIDES[text]

    # Normalise half-width katakana (ｱ-ﾝ) to full-width, and full-width
    # Latin/digits (Ａ, １) to ASCII, before any processing.
    text = unicodedata.normalize("NFKC", text)

    spans = list(_reviewed_title_spans(text)) if use_overrides else []
    spans.extend(span for span in [*_masking_circle_spans(text), *_decoration_spans(text)]
                 if not any(start < span[1] and end > span[0] for start, end, _, _ in spans))
    if spans:
        result = []
        offset = 0
        for start, end, value, is_romaji in sorted(spans):
            result.append(_romanize_fragment(text[offset:start], use_overrides=use_overrides,
                                             restore_loanwords=restore_loanwords,
                                             report=report))
            # Alias targets are Japanese text, not another alias lookup;
            # this prevents cycles in an edited companion data file.
            if is_romaji:
                result.append(value)
                if report is not None:
                    report.append({"written": text[start:end], "romaji": value,
                                   "reading": "", "source": "title", "flags": []})
            else:
                result.append(_romanize_alias_target(
                    value, restore_loanwords=restore_loanwords, report=report))
            offset = end
        result.append(_romanize_fragment(text[offset:], use_overrides=use_overrides,
                                         restore_loanwords=restore_loanwords,
                                         report=report))
        return "".join(result)
    return _japanese_text_to_romaji(text, use_overrides=use_overrides,
                                    restore_loanwords=restore_loanwords,
                                    report=report)


# Word flags that make a title worth a human look.  ``unknown`` (kana
# outside the dictionary) and ``etymon`` stay informational: their letters
# follow from the kana, only a spelling choice could differ.
_REVIEW_REASONS = {
    "guessed": "reading of {written} guessed outside the dictionary",
    "name": "{written} read as a person's name ({romaji})",
    "fragments": "{written} read kanji by kanji ({romaji})",
}


def _review_reasons(report: list[dict]) -> list[str]:
    """Summarize the words whose reading deserves a human look."""
    reasons: list[str] = []
    fragments: list[dict] = []
    def flush() -> None:
        if fragments:
            reasons.append(_REVIEW_REASONS["fragments"].format(
                written="".join(e["written"] for e in fragments),
                romaji=" ".join(e["romaji"] for e in fragments)))
            fragments.clear()
    for entry in report:
        if "fragments" in entry["flags"]:
            fragments.append(entry)
            continue
        flush()
        for flag in ("guessed", "name"):
            if flag in entry["flags"]:
                reasons.append(_REVIEW_REASONS[flag].format(**entry))
                break
    flush()
    return reasons


def explain_romaji(text: str, *, use_overrides: bool = True,
                   restore_loanwords: bool = True) -> dict:
    """Romanize ``text`` and say where each word came from.

    Returns ``{"romaji", "words", "review"}``.  ``words`` holds one dict per
    rendered word in order: ``written`` (the title's characters), ``romaji``,
    ``reading`` (kana, empty for reviewed text), ``source`` (``title``,
    ``phrase``, ``loanword``, ``counter``, ``etymon`` for a UniDic Latin
    etymon, or ``dictionary``) and ``flags``.  ``review`` is a list of plain
    sentences, empty when nothing looks guessed: a kanji reading outside the
    dictionary, a word read as a person's name although the dictionary also
    knows it as something else, or a run of kanji read one by one.  Reviewed
    replacements are trusted and never flagged; kana outside the dictionary
    and UniDic etymon spellings appear only as word flags.
    """
    report: list[dict] = []
    romaji = to_romaji(text, use_overrides=use_overrides,
                       restore_loanwords=restore_loanwords, report=report)
    return {"romaji": romaji, "words": report, "review": _review_reasons(report)}


def _romanize_fragment(text: str, *, use_overrides: bool = True,
                       restore_loanwords: bool = True,
                       report: list[dict] | None = None) -> str:
    if not text.strip():
        return text
    start = len(text) - len(text.lstrip())
    end = len(text.rstrip())
    return text[:start] + _japanese_text_to_romaji(
        text[start:end], use_overrides=use_overrides,
        restore_loanwords=restore_loanwords, report=report) + text[end:]


def _romanize_alias_target(text: str, *, restore_loanwords: bool = True,
                           report: list[dict] | None = None) -> str:
    if text in _TITLE_OVERRIDES:
        if report is not None:
            report.append({"written": text, "romaji": _TITLE_OVERRIDES[text],
                           "reading": "", "source": "title", "flags": []})
        return _TITLE_OVERRIDES[text]
    result = []
    offset = 0
    for start, end, value, _ in sorted([*_masking_circle_spans(text), *_decoration_spans(text)]):
        result.extend((_romanize_fragment(text[offset:start],
                                           restore_loanwords=restore_loanwords,
                                           report=report), value))
        offset = end
    result.append(_romanize_fragment(text[offset:], restore_loanwords=restore_loanwords,
                                     report=report))
    return "".join(result)


_KANA_CHAR_RE = re.compile(f"[{_KANA_CHARS}]")


def _dash_long_vowel_marks(text: str) -> str:
    """Rewrite a ー that can only be a dash as a hyphen.

    Titles use the long-vowel mark as a bracket or dash (夢 ー終焉ー,
    雷音ーBEAT), which otherwise leaves the mark unresolved so no sort key
    is written.  A lone mark is a dash at the start of the text, after a
    space, punctuation or Latin, between two kanji, or after kanji before
    digits or Latin; a closing mark after kanji at the end or before
    punctuation is a dash only when an opening dash precedes it, so
    expressive lengthening (限界突破ー！！) survives.  A mark after kana is
    always a long vowel (スーパー図書館), and ーー is lengthening (夢ーー).
    A mark after kanji before kana stays ambiguous and unresolved.
    """
    out = list(text)
    open_dash = False
    for match in re.finditer("ー+", text):
        if len(match.group()) > 1:
            continue
        i = match.start()
        prev = text[i - 1] if i else ""
        nxt = text[i + 1:i + 2]
        if prev and _KANA_CHAR_RE.fullmatch(prev):
            continue
        prev_kanji = bool(prev) and bool(_KANJI_RE.fullmatch(prev))
        next_kana = bool(nxt) and bool(_KANA_CHAR_RE.fullmatch(nxt))
        next_kanji = bool(nxt) and bool(_KANJI_RE.fullmatch(nxt))
        closing = not nxt or nxt.isspace() or not nxt.isalnum()
        dash = (not prev or prev.isspace() or not has_japanese(prev)
                or next_kanji
                or (prev_kanji and closing and open_dash)
                or (prev_kanji and not next_kana and not closing))
        if dash:
            out[i] = "-"
            open_dash = not open_dash
    return "".join(out)


def _japanese_text_to_romaji(text: str, *, use_overrides: bool = True,
                             restore_loanwords: bool = True,
                             report: list[dict] | None = None) -> str:
    """Preserve delimiters; separate only adjoining Latin/romanized words.

    The old asymmetric punctuation rule inserted spaces inside brackets and
    before exclamation marks, but glued Japanese→Latin transitions inside
    a title (e.g. とAD).  Apply the same boundary rule to every fragment.
    """
    text = _dash_long_vowel_marks(text)
    result_parts: list[str] = []
    last_end = 0
    first = True

    def append(fragment: str) -> None:
        if not fragment:
            return
        if (result_parts and result_parts[-1][-1].isalnum()
                and fragment[0].isalnum()):
            result_parts.append(" ")
        result_parts.append(fragment)

    # A reviewed phrase can explicitly contain a separator (射命丸 文).
    # Reserve those exact written spans before dividing Japanese/Latin
    # segments. Ordinary phrases never acquire an implicit space match.
    separated = []
    if use_overrides:
        for key, value in _PHRASE_OVERRIDES.items():
            written = unicodedata.normalize("NFKC", "".join(key))
            if written and not _JP_SEGMENT_RE.fullmatch(written):
                separated.extend((m.start(), m.end(), value)
                                 for m in re.finditer(re.escape(written), text))
    mask = list(text)
    spans = []
    for start, end, value in sorted(separated, key=lambda item: (item[0], -item[1])):
        if spans and start < spans[-1][1]:
            continue
        spans.append((start, end, value))
        mask[start:end] = " " * (end - start)
    spans.extend((m.start(), m.end(), None) for m in _JP_SEGMENT_RE.finditer("".join(mask)))
    for start, end, reviewed in sorted(spans):
        prefix = text[last_end:start]
        if prefix:
            append(prefix)
            if any(ch.isalnum() for ch in prefix):
                first = False

        if reviewed is not None:
            romaji = reviewed
            if report is not None:
                report.append({"written": text[start:end], "romaji": reviewed,
                               "reading": "", "source": "phrase", "flags": []})
        else:
            romaji = _japanese_segment_to_romaji(
                text[start:end], first_in_title=first, use_overrides=use_overrides,
                restore_loanwords=restore_loanwords, report=report,
            )
        first = False

        append(romaji)

        last_end = end

    if last_end < len(text):
        append(text[last_end:])

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
    titlesort_new, error, review.  ``review`` lists the reasons (plain
    sentences from :func:`explain_romaji`) why the new value deserves a
    human look; it is empty when nothing was guessed.
    """
    result = {
        "status": "error",
        "title": None,
        "titlesort_old": None,
        "titlesort_new": None,
        "error": None,
        "review": [],
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

        explained = explain_romaji(title)
        new_value = explained["romaji"]
        result["titlesort_new"] = new_value
        result["review"] = explained["review"]

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
    no_title, review, results}.  ``review`` counts written values whose
    reading was partly guessed (logged with a ``review:`` line).
    ``results`` is a list of (file_dict, romanize_file_result) tuples for
    callers that want the raw data.
    """
    summary = {
        "romanized": 0,
        "overwritten": 0,
        "skipped": 0,
        "no_title": 0,
        "errors": 0,
        "review": 0,
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

        review = "; ".join(res.get("review") or ())
        if status == "romanized":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             titlesort = {res['titlesort_new']}")
            summary["romanized"] += 1
        elif status == "overwritten":
            log(f"{indent}{prefix}{track_label}{display_title}")
            log(f"{indent}             was = {res['titlesort_old']}")
            log(f"{indent}             now = {res['titlesort_new']}")
            summary["overwritten"] += 1
        if review and status in ("romanized", "overwritten", "skip_exists"):
            log(f"{indent}             review: {review}")
            if status != "skip_exists":
                summary["review"] += 1
        if status in ("romanized", "overwritten"):
            pass
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
        f"Errors: {summary['errors']}  |  "
        f"Review: {summary['review']}"
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
