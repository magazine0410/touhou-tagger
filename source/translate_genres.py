#!/usr/bin/env python3
"""
translate_genres.py — Re-translate CJK genre tags to English, in place.

The wiki tagger translates THBWiki's genre vocabulary to English *at tag
time* via ``thwiki.GENRE_TRANSLATIONS``.  Any genre term missing from that
table is written to the file as-is (its original CJK form) and flagged with a
``⚠ No English translation for genre`` log warning so the vocabulary can be
filled in later.  Once a new mapping is added to the table, though, the
already-tagged files still carry the old CJK values, and re-running the tagger
won't reliably fix them: its ``genre`` write only merges/normalises when the
album *also* has a THBWiki genre row (and pre-existing off-wiki terms may not
be in the table at all).

This script closes that gap without going back to THBWiki: it walks the given
folders, reads each file's ``genre`` tag, runs every value through the
(now-updated) translation table, and rewrites the tag when anything changed.
It's the fast way to apply freshly-added genre mappings across a large library
that was tagged before those mappings existed.

Standalone and network-free: it imports only ``tag_io`` (read/write) and
``thwiki`` (the translation table + helpers), no Playwright/curl/cookie.  The
operation is idempotent — a second run over already-English tags writes
nothing — and safe to preview with ``--dry-run``.

Usage
-----
    # Preview what would change across a whole library / artist / album:
    python source/translate_genres.py --dry-run "path/to/music-library"

    # Apply for real (any mix of library roots, artist folders, albums):
    python source/translate_genres.py "path/to/artist" "path/to/another/album"

    # Show every changed file, not just the summary:
    python source/translate_genres.py --verbose "path/to/music-library"

Directories are walked recursively, so a library root, an artist folder, or a
single album folder all work.  Individual audio files may also be passed.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

from file_scan import SUPPORTED_EXTENSIONS
from tag_io import read_genres, set_genres
from thwiki import genre_is_cjk, translate_genre


def _iter_audio_files(paths: list[str]):
    """Yield every supported audio file under *paths* (files or dirs)."""
    for p in paths:
        if os.path.isfile(p):
            if os.path.splitext(p)[1].lower() in SUPPORTED_EXTENSIONS:
                yield p
        elif os.path.isdir(p):
            for dirpath, _dirs, files in os.walk(p):
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                        yield os.path.join(dirpath, name)
        else:
            print(f"⚠ Not found, skipping: {p}", file=sys.stderr)


def translate_genre_list(
    genres: list[str],
) -> tuple[list[str], bool, list[tuple[str, str]], list[str]]:
    """Translate one file's genre list.

    Returns ``(new_genres, changed, applied, still_cjk)``:

    * ``new_genres`` — each value passed through :func:`translate_genre`,
      de-duplicated in first-seen order (translation can collapse two
      source terms onto one English name).
    * ``changed`` — whether ``new_genres`` differs from the input.
    * ``applied`` — the ``(original, translated)`` pairs that actually
      changed, for reporting which mappings fired.
    * ``still_cjk`` — translated values that are *still* CJK, i.e. terms the
      table doesn't know yet (surfaced so they can be added).
    """
    new: list[str] = []
    applied: list[tuple[str, str]] = []
    still: list[str] = []
    for g in genres:
        t = translate_genre(g)
        if t != g:
            applied.append((g, t))
        if genre_is_cjk(t):
            still.append(t)
        if t not in new:
            new.append(t)
    return new, (new != genres), applied, still


def process_paths(
    paths: list[str], *, dry_run: bool = False, verbose: bool = False,
) -> dict:
    """Translate genre tags under *paths*.  Returns a summary dict."""
    scanned = with_genre = changed_files = written = errors = 0
    mapped: Counter[str] = Counter()          # "其他 → Other" → file count
    untranslated: Counter[str] = Counter()    # unknown CJK term → file count

    for fpath in _iter_audio_files(paths):
        scanned += 1
        genres = read_genres(fpath)
        if not genres:
            continue
        with_genre += 1

        new, changed, applied, still = translate_genre_list(genres)

        # Report unknown CJK terms whether or not anything changed — a file
        # can have one known and one unknown genre, or only unknown ones.
        for term in set(still):
            untranslated[term] += 1

        if not changed:
            continue
        changed_files += 1
        for old, t in {(o, n) for o, n in applied}:
            mapped[f"{old} → {t}"] += 1

        if verbose or dry_run:
            prefix = "[dry] " if dry_run else ""
            print(f"{prefix}{fpath}")
            print(f"        {genres}  →  {new}")

        if dry_run:
            continue
        try:
            set_genres(fpath, new, dry_run=False)
            written += 1
        except Exception as exc:
            errors += 1
            print(f"⚠ write failed: {fpath}: {exc}", file=sys.stderr)

    return {
        "scanned": scanned,
        "with_genre": with_genre,
        "changed_files": changed_files,
        "written": written,
        "errors": errors,
        "mapped": mapped,
        "untranslated": untranslated,
    }


def _print_summary(s: dict, *, dry_run: bool) -> None:
    print()
    print(f"Scanned {s['scanned']:,} audio file(s); "
          f"{s['with_genre']:,} had a genre tag.")
    if dry_run:
        print(f"Would translate genres in {s['changed_files']:,} file(s) "
              f"(dry run — nothing written).")
    else:
        print(f"Translated genres in {s['written']:,} file(s)."
              + (f"  {s['errors']:,} write error(s)." if s['errors'] else ""))

    if s["mapped"]:
        print("\nMappings applied:")
        for label, n in sorted(s["mapped"].items(), key=lambda kv: -kv[1]):
            print(f"    {label}: {n:,} file(s)")

    if s["untranslated"]:
        print("\nStill untranslated — add these to "
              "thwiki.GENRE_TRANSLATIONS:")
        for term, n in sorted(s["untranslated"].items(), key=lambda kv: -kv[1]):
            print(f"    {term}  ({n:,} file(s))")
    elif s["with_genre"]:
        print("\nNo untranslated CJK genres remain.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Re-translate CJK genre tags to English in place, using "
                    "thwiki.GENRE_TRANSLATIONS.",
    )
    parser.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="Library root(s), artist/album folder(s), or audio file(s). "
             "Directories are walked recursively.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing any files.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print every changed file (implied by --dry-run).",
    )
    args = parser.parse_args(argv)

    summary = process_paths(
        args.paths, dry_run=args.dry_run, verbose=args.verbose,
    )
    _print_summary(summary, dry_run=args.dry_run)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
