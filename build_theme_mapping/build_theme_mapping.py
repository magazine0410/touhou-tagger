#!/usr/bin/env python3
"""
build_theme_mapping.py — Build a Japanese→English mapping of all Touhou
original theme names using data from the Touhou Patch Center.

Produces a JSON file that maps canonical Japanese/mixed theme names
(as used by THBWiki's `ogmusicname` field) to their English translations.
The mapping file is used by the standalone touhou_tagger.py to translate
THBWiki theme names into English when using THBWiki as a fallback data source.

Since the Touhou Patch Center's API is behind Cloudflare, the input
files must be saved manually from a browser (one-time step).

Setup (one time):
    1. Open these URLs in your browser and save the JSON responses:

       Japanese titles:
       https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=ja&format=json&utf8&rawcontinue

       English titles:
       https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=en&format=json&utf8&rawcontinue

    2. Save them as e.g. thpatch_ja.json and thpatch_en.json

Usage:
    python build_theme_mapping/build_theme_mapping.py \
        build_theme_mapping/thpatch_ja.json build_theme_mapping/thpatch_en.json
    python build_theme_mapping/build_theme_mapping.py \
        build_theme_mapping/thpatch_ja.json build_theme_mapping/thpatch_en.json \
        -o my_mapping.json
"""

import argparse
import json
import os
import re
import sys


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_OUTPUT = os.path.join(
    _PROJECT_ROOT, "source", "touhou_theme_mapping.json"
)
_ADDITIONAL_MAPPINGS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "additional_theme_mappings.json",
)


# Reviewed aliases and source variants that are absent from, or misspelled in,
# the thpatch title dumps.  Keeping them here ensures regeneration preserves
# the corresponding entries in the generated JSON.  A ``None`` anchor means
# the entry is deliberately appended at the end.
_MANUAL_ALIASES: tuple[tuple[str, str | None, str, str], ...] = (
    ("after", "夜の鳩山を飛ぶ - Power MIX",
     "夜の鳩山を飛ぶ -Power MIX", "Fly above Hatoyama at night - Power MIX"),
    ("after", "ハーセルヴス", "ハーセルヴズ", "Herselves"),
    ("after", "幽夢　～ Inanimate Dream",
     "幽夢　～ Inanimate Dream（未使用バージョン）",
     "Faint Dream ~ Inanimate Dream (Unused Version)"),
    ("after", "東方萃夢想", "東方萃夢想（Arrange）",
     "Eastern Forgathering Dream (Arrange)"),
    ("after", "月まで届け、不死の煙", "月まで届け不死の煙",
     "Reach for the Moon, Immortal Smoke"),
    ("after", "君はあの影を見たか？", "君はあの影を見たか",
     "Did You See that Shadow?"),
    ("after", "ロマンチック逃旅行", "ロマンチック逃飛行",
     "Romantic Escape Flight"),
    ("before", "今宵は飄逸なエゴイスト(Live ver) ～ Egoistic Flowers.",
     "今宵は飄逸なエゴイスト　～ Egoistic Flowers.",
     "Tonight Stars an Easygoing Egoist ~ Egoistic Flowers."),
    ("after", "遥か38万キロのボヤージュ", "遥か３８万キロのボヤージュ",
     "Faraway Voyage of 380,000 Kilometers"),
    ("after", "風神少女", "風神少女(Short Version)",
     "Wind God Girl (short version)"),
    ("after", None, "河童様の云う通り ～ One-way Accelerator",
     "The Kappa Way as Said ~ One-way Accelerator"),
)

# Reviewed corrections that intentionally differ from the current thpatch
# English dump.  Keep these here so rebuilding cannot silently replace an
# established canonical output.
_MANUAL_OVERRIDES = {
    "少女綺想曲　～ Capriccio": "Maiden's Capriccio",
}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_key(s: str) -> str:
    """
    Normalize a theme name for use as a lookup key.

    THBWiki's ``ogmusicname`` and the Touhou Patch Center's Japanese
    titles may differ in whitespace (fullwidth vs ASCII), spacing around
    tilde characters (～ vs ~ vs 〜), Latin capitalization, minor
    punctuation, and the presence or absence of a trailing period.  This
    function collapses those differences so that lookups succeed even when
    the sources aren't byte-identical.

    NOTE: this function is the single source of truth for normalization.
    The standalone tagger (touhou_tagger.py) re-derives
    the ``normalized_keys`` table from ``mapping`` at load time using
    their own copy of this function, so changes here don't strictly
    require regenerating the JSON — but re-running this script keeps
    the JSON's precomputed table in sync for external consumers.
    """
    # Collapse all whitespace variants (incl. fullwidth space U+3000,
    # ideographic half-fill space, zero-width spaces, etc.)
    s = re.sub(r'[\s\u3000\u2002-\u200b]+', ' ', s.strip())
    # Normalize tilde variants to ASCII tilde
    s = s.replace('\uff5e', '~').replace('\u301c', '~')
    # Some THBWiki entries omit one or both spaces around the separator.
    s = re.sub(r'\s*~\s*', ' ~ ', s)
    # Normalize fullwidth punctuation that sometimes varies
    s = s.replace('\uff0c', ',').replace('\uff1f', '?').replace('\uff01', '!')
    # Strip trailing periods.  Some THBWiki album pages render theme
    # names with a trailing '.' that the canonical thpatch form lacks
    # (e.g. ``永夜抄　～ Eastern Night.``).  Stripping symmetrically on
    # both sides of the lookup makes the match succeed; themes whose
    # canonical name does end in '.' or '...' are unaffected because
    # their normalized form also loses the trailing dots, and the
    # English output value (read from ``mapping``, not the normalized
    # key) preserves whatever punctuation it has.
    s = s.rstrip('.')
    # Wiki capitalization is not consistent (e.g. "Red and White" versus
    # the thpatch key "Red And White").  This is a lookup key only; the
    # canonical English output keeps its original capitalization.
    return s.casefold()


def _add_manual_aliases(mapping: dict[str, str]) -> dict[str, str]:
    """Return *mapping* with reviewed aliases inserted by their anchors."""
    existing = set(mapping)
    anchored: dict[tuple[str, str], list[tuple[str, str]]] = {}
    trailing: list[tuple[str, str]] = []
    for position, anchor, title, english in _MANUAL_ALIASES:
        if title in existing:
            continue
        if anchor is None:
            trailing.append((title, english))
        else:
            anchored.setdefault((position, anchor), []).append(
                (title, english)
            )

    result: dict[str, str] = {}
    inserted: set[str] = set()
    for title, english in mapping.items():
        for alias, alias_english in anchored.get(("before", title), []):
            result[alias] = alias_english
            inserted.add(alias)
        result[title] = english
        for alias, alias_english in anchored.get(("after", title), []):
            result[alias] = alias_english
            inserted.add(alias)

    # If an input dump drops an anchor, retain the reviewed alias rather than
    # silently losing it. Explicit trailing entries remain last.
    for aliases in anchored.values():
        for alias, alias_english in aliases:
            if alias not in inserted:
                result[alias] = alias_english
    for alias, alias_english in trailing:
        result[alias] = alias_english
    return result


def _load_additional_sections() -> dict[str, dict]:
    """Load reviewed non-Touhou mapping sections kept beside this builder."""
    try:
        with open(_ADDITIONAL_MAPPINGS, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error reading additional mappings: {exc}")
        sys.exit(1)

    sections = data.get("sections")
    if not isinstance(sections, dict):
        print("Error: additional mappings file has no 'sections' object.")
        sys.exit(1)
    for name, section in sections.items():
        if not isinstance(section, dict) or not isinstance(
            section.get("mapping"), dict
        ):
            print(f"Error: additional mapping section {name!r} is invalid.")
            sys.exit(1)
    return sections


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a JSON mapping of Touhou original theme names "
            "(Japanese → English) from Touhou Patch Center data files."
        ),
    )
    parser.add_argument(
        "ja_file",
        help=(
            "Path to the Japanese titles JSON file saved from: "
            "https://www.thpatch.net/w/api.php?action=query"
            "&list=tdbtitles&language=ja&format=json&utf8&rawcontinue"
        ),
    )
    parser.add_argument(
        "en_file",
        help=(
            "Path to the English titles JSON file saved from: "
            "https://www.thpatch.net/w/api.php?action=query"
            "&list=tdbtitles&language=en&format=json&utf8&rawcontinue"
        ),
    )
    parser.add_argument(
        "--output", "-o",
        default=_DEFAULT_OUTPUT,
        help="Output JSON file path (default: source/touhou_theme_mapping.json)",
    )
    args = parser.parse_args()

    # ----- Load input files -----
    try:
        with open(args.ja_file, "r", encoding="utf-8") as f:
            ja_raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Error reading Japanese titles file: {exc}")
        sys.exit(1)

    try:
        with open(args.en_file, "r", encoding="utf-8") as f:
            en_raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"Error reading English titles file: {exc}")
        sys.exit(1)

    # ----- Extract the title dicts -----
    # The API response may be either:
    #   - a flat dict of {theme_id: title, ...}  (if the browser saved
    #     just the inner object)
    #   - a nested structure with the titles under a known key
    # Handle both cases gracefully.
    ja_titles = _extract_titles(ja_raw)
    en_titles = _extract_titles(en_raw)

    if not ja_titles:
        print("Error: No Japanese titles found in the input file.")
        print("Make sure you saved the full JSON response from the API.")
        sys.exit(1)

    if not en_titles:
        print("Error: No English titles found in the input file.")
        print("Make sure you saved the full JSON response from the API.")
        sys.exit(1)

    print(f"Loaded {len(ja_titles)} Japanese titles, "
          f"{len(en_titles)} English titles.")

    # ----- Build the mapping -----
    # For each theme ID present in both files, create a mapping from
    # the Japanese name to the English name.  We iterate in theme ID
    # order so the output file is structured chronologically (th01 first,
    # th02 second, etc.).

    raw_mapping: dict[str, str] = {}
    norm_to_raw: dict[str, str] = {}
    skipped_identical = 0
    skipped_empty = 0
    skipped_dupes: list[tuple[str, str, str]] = []  # (id, ja, existing_id)

    common_ids = sorted(set(ja_titles.keys()) & set(en_titles.keys()))
    ja_only = set(ja_titles.keys()) - set(en_titles.keys())
    en_only = set(en_titles.keys()) - set(ja_titles.keys())

    # Track which theme ID first introduced each normalized key
    norm_to_id: dict[str, str] = {}

    # Some thpatch entries are stubs where the "title" is just the
    # track identifier code (e.g. "th07_10", "mcd_09_01").  These
    # aren't real theme names and should be excluded.
    STUB_PREFIXES = ("th0", "th1", "th2", "mcd", "alcostg", "sh0")

    for theme_id in common_ids:
        ja_val = ja_titles[theme_id]
        en_val = en_titles[theme_id]

        # Some entries are lists (e.g. themes with alternate versions);
        # use the first element.
        if isinstance(ja_val, list):
            if not ja_val:
                skipped_empty += 1
                continue
            ja_val = ja_val[0]
        if isinstance(en_val, list):
            if not en_val:
                skipped_empty += 1
                continue
            en_val = en_val[0]

        if not isinstance(ja_val, str) or not isinstance(en_val, str):
            skipped_empty += 1
            continue

        ja_name = ja_val.strip()
        en_name = en_val.strip()

        if not ja_name or not en_name:
            skipped_empty += 1
            continue

        # Skip stub entries where the "title" is just a track ID code
        if ja_name.startswith(STUB_PREFIXES):
            skipped_empty += 1
            continue

        if ja_name == en_name:
            skipped_identical += 1

        nk = normalize_key(ja_name)

        # If we've already seen this normalized key (e.g. a theme
        # that appears in multiple games), keep the first mapping.
        if nk in norm_to_raw:
            skipped_dupes.append((theme_id, ja_name, norm_to_id[nk]))
            continue

        raw_mapping[ja_name] = en_name
        norm_to_raw[nk] = ja_name
        norm_to_id[nk] = theme_id

    # Add reviewed source aliases and preserve established corrections.
    raw_mapping = _add_manual_aliases(raw_mapping)
    for title, english in _MANUAL_OVERRIDES.items():
        if title in raw_mapping:
            raw_mapping[title] = english

    # Non-Touhou projects are stored as explicit sections.  Remove any
    # section entries supplied by thpatch (notably the first two Seihou
    # games) from the primary mapping by normalized key so each title has
    # one physical home in the output JSON.
    sections = _load_additional_sections()
    section_norms = {
        normalize_key(title)
        for section in sections.values()
        for title in section["mapping"]
    }
    raw_mapping = {
        title: english
        for title, english in raw_mapping.items()
        if normalize_key(title) not in section_norms
    }

    all_mappings = [raw_mapping]
    all_mappings.extend(section["mapping"] for section in sections.values())
    norm_to_raw = {}
    total_theme_count = 0
    identical_theme_count = 0
    for mapping in all_mappings:
        total_theme_count += len(mapping)
        for title, english in mapping.items():
            if title == english:
                identical_theme_count += 1
            norm_to_raw.setdefault(normalize_key(title), title)

    # ----- Build output -----
    output = {
        "metadata": {
            "description": (
                "Mapping of Touhou original theme names: Japanese → "
                "English, with reviewed Len'en and Seihou sections.  "
                "Generated by build_theme_mapping.py from Touhou Patch "
                "Center data and the section sources recorded below."
            ),
            "theme_count": total_theme_count,
            "section_counts": {
                "touhou_and_reviewed": len(raw_mapping),
                **{
                    name: len(section["mapping"])
                    for name, section in sections.items()
                },
            },
            "source": "https://www.thpatch.net/",
        },
        "mapping": raw_mapping,
        "sections": sections,
        "normalized_keys": norm_to_raw,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ----- Summary -----
    print(f"\nSaved {total_theme_count} theme mappings to {args.output}")
    print(f"  Primary section:            {len(raw_mapping)}")
    for name, section in sections.items():
        print(f"  {name.title() + ' section:':<28}{len(section['mapping'])}")
    print(f"  Already-English (included): {identical_theme_count}")
    print(f"  Unique translations:        "
          f"{total_theme_count - identical_theme_count}")

    if skipped_dupes:
        print(f"  Duplicates (skipped):       {len(skipped_dupes)}")
        for dup_id, dup_name, orig_id in skipped_dupes:
            print(f"    {dup_id} ({dup_name}) — same as {orig_id}")

    if skipped_empty:
        print(f"  Empty/invalid (skipped):    {skipped_empty}")

    if ja_only:
        print(f"\n  {len(ja_only)} theme(s) in Japanese file but not "
              f"English (no translation available)")
    if en_only:
        print(f"  {len(en_only)} theme(s) in English file but not "
              f"Japanese")

    print(f"\nTo update after a new game/CD release, re-save the two "
          f"API URLs\nand re-run this script.")


def _extract_titles(data: dict) -> dict[str, str]:
    """
    Extract the theme ID → title mapping from the API response.

    The response format is:
        {"query": {"tdbtitles": {"th01_01": "A Sacred Lot", ...}}}

    But the user might have saved just the inner dict, or the browser
    might have wrapped it differently.  Try multiple paths.
    """
    # Standard API response structure
    if "query" in data and "tdbtitles" in data["query"]:
        return data["query"]["tdbtitles"]

    # Maybe they saved just the tdbtitles object
    if "tdbtitles" in data:
        return data["tdbtitles"]

    # Maybe they saved the flat dict directly
    # Heuristic: if the dict has theme-ID-like keys, use it as-is
    sample_keys = list(data.keys())[:5]
    if any(re.match(r'^th\d+_', k) for k in sample_keys):
        return data

    # Last resort: search one level deep for a dict with theme-like keys
    for value in data.values():
        if isinstance(value, dict):
            sample = list(value.keys())[:5]
            if any(re.match(r'^th\d+_', k) for k in sample):
                return value

    return {}


if __name__ == "__main__":
    main()
