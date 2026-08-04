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


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_key(s: str) -> str:
    """
    Normalize a theme name for use as a lookup key.

    THBWiki's ``ogmusicname`` and the Touhou Patch Center's Japanese
    titles may differ in whitespace (fullwidth vs ASCII), tilde
    characters (～ vs ~ vs 〜), minor punctuation, and the presence
    or absence of a trailing period.  This function collapses those
    differences so that lookups succeed even when the sources aren't
    byte-identical.

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
    return s


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

    # ----- Build output -----
    output = {
        "metadata": {
            "description": (
                "Mapping of Touhou original theme names: Japanese → "
                "English.  Generated by build_theme_mapping.py from "
                "Touhou Patch Center data."
            ),
            "theme_count": len(raw_mapping),
            "source": "https://www.thpatch.net/",
        },
        "mapping": raw_mapping,
        "normalized_keys": norm_to_raw,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ----- Summary -----
    print(f"\nSaved {len(raw_mapping)} theme mappings to {args.output}")
    print(f"  Already-English (included): {skipped_identical}")
    print(f"  Unique translations:        "
          f"{len(raw_mapping) - skipped_identical}")

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
