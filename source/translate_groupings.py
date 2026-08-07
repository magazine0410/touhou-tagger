#!/usr/bin/env python3
"""
Translate existing Japanese/mixed ``grouping`` tags to their canonical
English names using ``touhou_theme_mapping.json``.

This is a local, network-free migration tool for files tagged before a theme
mapping or normalization correction was available.  Semicolon-separated
multi-theme groupings are translated one component at a time; unknown and
hand-written components are preserved exactly.  The operation is idempotent.

Examples:
    python source/translate_groupings.py --dry-run "path/to/music-library"
    python source/translate_groupings.py "path/to/music-library"
    python source/translate_groupings.py --verbose "path/to/artist"
    python source/translate_groupings.py --stats-cache --dry-run \
        "path/to/music-library"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

import availability
from file_scan import SUPPORTED_EXTENSIONS
from tag_io import read_grouping, set_grouping
from theme_mapping import load_theme_mapping, translate_title


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


def _stats_cache_path() -> str:
    """Return the Statistics tab's active per-user cache path."""
    return os.path.join(availability.app_config_dir(), "stats_cache.json")


def _iter_audio_files(paths: list[str]):
    """Yield every supported audio file under *paths* (files or dirs)."""
    for path in paths:
        if os.path.isfile(path):
            if os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS:
                yield path
        elif os.path.isdir(path):
            for dirpath, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                        yield os.path.join(dirpath, name)
        else:
            print(f"⚠ Not found, skipping: {path}", file=sys.stderr)


def translate_grouping_value(
    value: str, mapping_data: dict,
) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Translate one grouping value.

    Returns ``(new_value, applied, untranslated)``.  Formatting and unmatched
    components are left untouched when no mapping applies.
    """
    components = [part.strip() for part in value.split(";")]
    translated: list[str] = []
    applied: list[tuple[str, str]] = []
    untranslated: list[str] = []

    for component in components:
        english = translate_title(component, mapping_data)
        translated.append(english)
        if english != component:
            applied.append((component, english))
        elif _CJK_RE.search(component):
            untranslated.append(component)

    if not applied:
        return value, applied, untranslated
    return "; ".join(translated), applied, untranslated


def process_paths(
    paths: list[str], *, mapping_data: dict, dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Translate grouping tags under *paths* and return summary counts."""
    scanned = with_grouping = changed_files = written = errors = 0
    mapped: Counter[str] = Counter()
    untranslated: Counter[str] = Counter()

    for fpath in _iter_audio_files(paths):
        scanned += 1
        grouping = read_grouping(fpath)
        if not grouping:
            continue
        with_grouping += 1

        new_value, applied, still = translate_grouping_value(
            grouping, mapping_data,
        )
        for term in set(still):
            untranslated[term] += 1
        if not applied:
            continue

        changed_files += 1
        for old, new in set(applied):
            mapped[f"{old} → {new}"] += 1

        if verbose or dry_run:
            prefix = "[dry] " if dry_run else ""
            print(f"{prefix}{fpath}")
            print(f"        {grouping}  →  {new_value}")

        if dry_run:
            continue
        try:
            set_grouping(fpath, new_value, dry_run=False)
            written += 1
        except Exception as exc:
            errors += 1
            print(f"⚠ write failed: {fpath}: {exc}", file=sys.stderr)

    return {
        "mode": "walk",
        "scanned": scanned,
        "with_grouping": with_grouping,
        "changed_files": changed_files,
        "written": written,
        "errors": errors,
        "mapped": mapped,
        "untranslated": untranslated,
    }


def _cache_scopes(paths: list[str]) -> list[tuple[str, bool]]:
    """Return normalized ``(path, is_directory)`` cache filters."""
    scopes: list[tuple[str, bool]] = []
    for path in paths:
        expanded = os.path.abspath(os.path.expanduser(path))
        if os.path.isfile(expanded):
            scopes.append((os.path.normcase(expanded), False))
        elif os.path.isdir(expanded):
            scopes.append((os.path.normcase(expanded), True))
        else:
            print(f"⚠ Not found, skipping: {path}", file=sys.stderr)
    return scopes


def _cache_path_is_in_scope(fpath: str, scopes: list[tuple[str, bool]]) -> bool:
    candidate = os.path.normcase(os.path.abspath(fpath))
    for scope, is_directory in scopes:
        if not is_directory:
            if candidate == scope:
                return True
            continue
        try:
            if os.path.commonpath((candidate, scope)) == scope:
                return True
        except ValueError:
            # Different Windows drives cannot share a common path.
            continue
    return False


def process_stats_cache(
    paths: list[str], *, mapping_data: dict, cache_path: str,
    dry_run: bool = False, verbose: bool = False,
) -> dict:
    """Translate files shortlisted by a Statistics ``stats_cache.json``.

    Fresh cache candidates are trusted without reopening their tags.  A
    candidate whose current mtime differs from the cached nanosecond mtime is
    reread before deciding whether to write it.  Non-candidates are never
    touched, which makes this mode fast but intentionally means files absent
    from the cache (or changed since the scan to acquire a problematic
    grouping) are outside its coverage.
    """
    try:
        with open(cache_path, "r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"could not load Statistics cache {cache_path!r}: {exc}")
    if not isinstance(cache, dict):
        raise ValueError(
            f"Statistics cache {cache_path!r} does not contain an object"
        )

    scopes = _cache_scopes(paths)
    scanned = with_grouping = cache_candidates = changed_files = 0
    written = errors = stale_candidates = missing_candidates = 0
    invalid_records = 0
    mapped: Counter[str] = Counter()
    untranslated: Counter[str] = Counter()

    for fpath, entry in cache.items():
        if not isinstance(fpath, str) or not _cache_path_is_in_scope(
            fpath, scopes,
        ):
            continue
        scanned += 1
        if not isinstance(entry, list) or len(entry) != 9:
            invalid_records += 1
            continue
        cached_grouping = entry[1]
        if not isinstance(cached_grouping, str) or not cached_grouping.strip():
            continue
        with_grouping += 1

        cached_new, cached_applied, cached_still = translate_grouping_value(
            cached_grouping, mapping_data,
        )
        if not cached_applied:
            for term in set(cached_still):
                untranslated[term] += 1
            continue
        cache_candidates += 1

        try:
            current_mtime = os.stat(fpath).st_mtime_ns
        except OSError:
            missing_candidates += 1
            continue

        grouping = cached_grouping
        new_value = cached_new
        applied = cached_applied
        still = cached_still
        if entry[0] != current_mtime:
            stale_candidates += 1
            grouping = read_grouping(fpath)
            if not grouping:
                continue
            new_value, applied, still = translate_grouping_value(
                grouping, mapping_data,
            )
            if not applied:
                for term in set(still):
                    untranslated[term] += 1
                continue

        for term in set(still):
            untranslated[term] += 1
        changed_files += 1
        for old, new in set(applied):
            mapped[f"{old} → {new}"] += 1

        if verbose or dry_run:
            prefix = "[dry] " if dry_run else ""
            print(f"{prefix}{fpath}")
            print(f"        {grouping}  →  {new_value}")

        if dry_run:
            continue
        try:
            set_grouping(fpath, new_value, dry_run=False)
            written += 1
        except Exception as exc:
            errors += 1
            print(f"⚠ write failed: {fpath}: {exc}", file=sys.stderr)

    return {
        "mode": "stats_cache",
        "cache_path": cache_path,
        "scanned": scanned,
        "with_grouping": with_grouping,
        "cache_candidates": cache_candidates,
        "stale_candidates": stale_candidates,
        "missing_candidates": missing_candidates,
        "invalid_records": invalid_records,
        "changed_files": changed_files,
        "written": written,
        "errors": errors,
        "mapped": mapped,
        "untranslated": untranslated,
    }


def _print_summary(summary: dict, *, dry_run: bool) -> None:
    print()
    if summary.get("mode") == "stats_cache":
        print(f"Examined {summary['scanned']:,} in-scope Statistics cache "
              f"record(s); {summary['with_grouping']:,} had a grouping tag.")
        print(f"Cache candidates: {summary['cache_candidates']:,}; "
              f"stale candidates reread: {summary['stale_candidates']:,}; "
              f"missing candidates skipped: "
              f"{summary['missing_candidates']:,}.")
        if summary["invalid_records"]:
            print(f"Skipped {summary['invalid_records']:,} incompatible cache "
                  f"record(s).")
        print("Cache-only mode: files absent from the cache were not examined.")
    else:
        print(f"Scanned {summary['scanned']:,} audio file(s); "
              f"{summary['with_grouping']:,} had a grouping tag.")
    if dry_run:
        print(f"Would translate grouping tags in "
              f"{summary['changed_files']:,} file(s) "
              f"(dry run — nothing written).")
    else:
        print(f"Translated grouping tags in {summary['written']:,} file(s)."
              + (f"  {summary['errors']:,} write error(s)."
                 if summary["errors"] else ""))

    if summary["mapped"]:
        print("\nMappings applied:")
        for label, count in sorted(
            summary["mapped"].items(), key=lambda item: -item[1],
        ):
            print(f"    {label}: {count:,} file(s)")

    if summary["untranslated"]:
        print("\nStill-unmapped CJK grouping components:")
        for term, count in sorted(
            summary["untranslated"].items(), key=lambda item: -item[1],
        ):
            print(f"    {term}  ({count:,} file(s))")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Translate existing Japanese/mixed grouping tags to "
                    "canonical English theme names.",
    )
    parser.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="Library root(s), artist/album folder(s), or audio file(s). "
             "Directories are walked recursively.",
    )
    parser.add_argument(
        "--mapping", metavar="PATH",
        help="Theme mapping JSON (default: beside this script).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing any files.",
    )
    parser.add_argument(
        "--stats-cache", action="store_true",
        help="Use the Statistics tab's stats_cache.json to shortlist files "
             "instead of walking and opening the complete library. Only "
             "files present in the cache are considered.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print every changed file (implied by --dry-run).",
    )
    args = parser.parse_args(argv)

    mapping_data = load_theme_mapping(args.mapping)
    if mapping_data is None:
        target = args.mapping or "touhou_theme_mapping.json beside this script"
        print(f"Error: could not load theme mapping: {target}", file=sys.stderr)
        return 2

    if args.stats_cache:
        cache_path = _stats_cache_path()
        try:
            summary = process_stats_cache(
                args.paths, mapping_data=mapping_data, cache_path=cache_path,
                dry_run=args.dry_run, verbose=args.verbose,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    else:
        summary = process_paths(
            args.paths, mapping_data=mapping_data,
            dry_run=args.dry_run, verbose=args.verbose,
        )
    _print_summary(summary, dry_run=args.dry_run)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
