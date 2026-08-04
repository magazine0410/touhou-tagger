"""library_stats.py — Collection-wide statistics for the Touhou Tagger GUI.

Provides the **Statistics** tab: scan a music library laid out as
``<root>/<artist>/<album>/<tracks>`` and visualise how much of it has been
grouping-tagged.

Two views:

* A clickable pie chart of **tagged vs. untagged artists** — an artist counts
  as *tagged* when at least one track in any of their albums carries a
  ``grouping`` value that is a known Touhou theme (one of the English names in
  ``touhou_theme_mapping.json``).  Clicking a slice lists those artists inline;
  in the **tagged** list each artist can be expanded to the albums under it that
  have no ``grouping`` theme — classified during the scan itself (and persisted
  with the result) so expanding reads from memory — to surface off-wiki/
  un-matched albums not yet marked unavailable.
* A **theme-popularity** list — each known theme that actually appears, with the
  number of songs tagged with it, most-popular first.  A track tagged
  ``"A; B"`` counts once toward each of ``A`` and ``B``.  Right-clicking a
  theme offers **Information**: a scrollable window with the theme's top-5
  longest/shortest solo and multi-theme remixes and the circle with the most
  remixes (foldable to its songs grouped by album), all read from the
  ``theme_details`` computed during the scan — no disk I/O on open.
* A **genre-popularity** list — the same bar chart + list, but for the
  multi-value ``genre`` tags (each of a track's genres counts once).
  Release-type labels (:data:`_EXCLUDED_GENRES` — "Game", "Indie") are
  dropped at display time: everything this tagger handles is a doujin game
  arrange, so they say nothing and would dwarf the real musical styles.
  Both charts are reached from the **Popularity charts** drop-down.

This module is self-contained: it imports PyQt5 at the top (unlike ``gui.py``,
which defers the import).  ``gui.py`` imports :class:`StatisticsTab` lazily from
inside ``gui_main`` so the CLI path never pulls in PyQt5.  The pure scanning
logic (:func:`scan_library`, :func:`load_known_themes`) has no Qt dependency and
can be exercised headlessly.

Named ``library_stats`` rather than ``statistics`` on purpose: the latter would
shadow Python's stdlib ``statistics`` module, which is importable from this
directory (it's on ``sys.path``).
"""
from __future__ import annotations

import json
import math
import os
import shlex
from collections import Counter

from PyQt5 import QtCore, QtGui, QtWidgets

import availability
import preferences
from file_scan import SUPPORTED_EXTENSIONS, _expand_to_album_dirs
from tag_io import _CJK_RE, read_stats_fields
from theme_mapping import load_theme_mapping

def _default_library_root() -> str:
    """Return a portable first-run library root.

    ``TOUHOU_TAGGER_LIBRARY_ROOT`` is useful for managed/portable setups.
    Otherwise use the platform's standard Music folder.  The Statistics tab
    persists the user's chosen root after the first scan, so this value is
    only a starting point.
    """
    override = os.environ.get("TOUHOU_TAGGER_LIBRARY_ROOT", "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))
    return QtCore.QStandardPaths.writableLocation(
        QtCore.QStandardPaths.MusicLocation
    )


# Default for the Scan path field; overridden by the persisted config or
# whatever the user types/browses to.
DEFAULT_ROOT = _default_library_root()


# ---------------------------------------------------------------------------
# Config persistence (mirrors gui.py's _THWIKI_AUTH_CONFIG_PATH helpers)
# ---------------------------------------------------------------------------
_STATS_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "stats.json",
)


def _load_stats_config() -> dict:
    """Return the persisted stats config as a dict, or {} if absent/unreadable."""
    try:
        with open(_STATS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_stats_config(library_root: str) -> None:
    """Persist the last-scanned library root.

    Errors are swallowed — persistence is a convenience, not a hard
    requirement, and a read-only home dir shouldn't break the feature.
    """
    try:
        availability.ensure_private_directory(
            os.path.dirname(_STATS_CONFIG_PATH)
        )
        tmp = _STATS_CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"library_root": library_root}, f,
                      ensure_ascii=False, indent=2)
        availability.restrict_private_file(tmp)
        os.replace(tmp, _STATS_CONFIG_PATH)
        availability.restrict_private_file(_STATS_CONFIG_PATH)
    except OSError:
        pass


# Per-file scan cache keyed by absolute path → [mtime_ns, grouping,
# present_list, cjk_list, title, album, albumartist, length, genres]
# (see _stats_record_for).  Lets a re-scan skip the
# (expensive, network-latency-bound) mutagen open for every file whose mtime is
# unchanged since the last scan — so tagging one artist and re-scanning re-reads
# only that artist's files.
_STATS_CACHE_PATH = os.path.join(
    os.path.dirname(_STATS_CONFIG_PATH), "stats_cache.json",
)
# The last completed scan's aggregated result, reloaded on launch so the tab
# shows data immediately without re-scanning.
_STATS_RESULT_PATH = os.path.join(
    os.path.dirname(_STATS_CONFIG_PATH), "stats_result.json",
)

_RESULT_KEYS = {
    "root", "total_artists", "tagged_artists", "untagged_artists",
    "theme_counts", "cancelled",
}


def _load_stats_cache() -> dict:
    """Return the persisted per-file grouping cache, or {} if absent/unreadable."""
    try:
        with open(_STATS_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_stats_cache(cache: dict) -> None:
    """Persist the per-file grouping cache (atomic replace; errors swallowed)."""
    try:
        availability.ensure_private_directory(
            os.path.dirname(_STATS_CACHE_PATH)
        )
        tmp = _STATS_CACHE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        availability.restrict_private_file(tmp)
        os.replace(tmp, _STATS_CACHE_PATH)
        availability.restrict_private_file(_STATS_CACHE_PATH)
    except OSError:
        pass


def _load_last_result() -> dict | None:
    """Return the last persisted scan result, or None if absent/invalid."""
    try:
        with open(_STATS_RESULT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and _RESULT_KEYS <= set(data):
        return data
    return None


def _save_last_result(result: dict) -> None:
    """Persist the aggregated scan result (atomic replace; errors swallowed)."""
    try:
        availability.ensure_private_directory(
            os.path.dirname(_STATS_RESULT_PATH)
        )
        tmp = _STATS_RESULT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        availability.restrict_private_file(tmp)
        os.replace(tmp, _STATS_RESULT_PATH)
        availability.restrict_private_file(_STATS_RESULT_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Pure logic — no Qt, independently testable
# ---------------------------------------------------------------------------
def load_known_themes(mapping_path: str | None = None) -> set[str]:
    """Return the set of known English theme names from the mapping JSON.

    These are the values the tagger writes into the ``grouping`` tag, so
    membership in this set is what makes a ``grouping`` value count as a
    "known Touhou theme".  Returns an empty set if the mapping is missing.
    """
    data = load_theme_mapping(mapping_path)
    if not data:
        return set()
    return set(data.get("mapping", {}).values())


def _list_artist_dirs(root: str) -> list[tuple[str, str]]:
    """Immediate, non-hidden subdirectories of *root* → ``(name, path)``."""
    out: list[tuple[str, str]] = []
    try:
        names = sorted(os.listdir(root), key=str.lower)
    except OSError:
        return []
    for name in names:
        if name.startswith("."):
            continue
        p = os.path.join(root, name)
        if os.path.isdir(p):
            out.append((name, p))
    return out


def _list_album_dirs(artist_dir: str) -> list[str]:
    """Candidate album folders under an artist.

    Normally the artist folder's immediate subdirectories.  As a safety net,
    if there are no subdirectories but audio sits directly in the artist
    folder, the artist folder itself is treated as a single album.
    """
    subdirs: list[str] = []
    has_direct_audio = False
    try:
        entries = sorted(os.listdir(artist_dir), key=str.lower)
    except OSError:
        return []
    for name in entries:
        if name.startswith("."):
            continue
        p = os.path.join(artist_dir, name)
        if os.path.isdir(p):
            subdirs.append(p)
        elif os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
            has_direct_audio = True
    if subdirs:
        return subdirs
    return [artist_dir] if has_direct_audio else []


def _album_audio_files(album_dir: str) -> tuple[list[str], int]:
    """Audio files in an album folder, plus the folder's total size in bytes.

    Walks recursively so multi-disc layouts (``Disc 1`` / ``CD2`` …) are
    included.  Hidden subdirectories are skipped.  Returns ``(audio_files,
    total_bytes)`` where *total_bytes* sums the size of **every** file walked
    (audio, cover art, logs, …) so it reflects the true on-disk folder size.
    """
    out: list[str] = []
    total = 0
    for dirpath, dirnames, filenames in os.walk(album_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            fp = os.path.join(dirpath, name)
            try:
                total += os.stat(fp).st_size
            except OSError:
                pass
            if os.path.splitext(name)[1].lower() in SUPPORTED_EXTENSIONS:
                out.append(fp)
    return out, total


def _format_size(num_bytes: int) -> str:
    """Human-readable binary folder size, e.g. ``"1.23 GiB"`` / ``"456 MiB"``.

    Sizes ``>= 1 GiB`` are shown in GiB with two decimals; everything below
    that is shown as whole MiB (so a tiny or empty folder reads ``"0 MiB"``).
    """
    mib = num_bytes / (1024 * 1024)
    if mib >= 1024:
        return f"{mib / 1024:.2f} GiB"
    return f"{mib:.0f} MiB"


def _format_length(seconds) -> str:
    """``"M:SS"`` for a duration in seconds, or ``"?:??"`` when unknown."""
    if not seconds or seconds <= 0:
        return "?:??"
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


# Genres hidden from the genre-popularity view (compared casefolded).  This
# tagger only handles Touhou remixes — doujin (indie) arranges of game music —
# so "Game" and "Indie" describe every release rather than a musical style and
# would dwarf the real genres.  Filtered at display time, not during the scan,
# so extending this set never requires a re-scan.
_EXCLUDED_GENRES: frozenset[str] = frozenset({"game", "indie"})


def _split_grouping(value: str | None) -> list[str]:
    """Split a ``grouping`` tag value into individual theme names.

    Multiple themes are stored as ``"A; B"`` (semicolon-separated); each piece
    is stripped and empties are dropped.
    """
    if not value:
        return []
    return [piece.strip() for piece in value.split(";") if piece.strip()]


# The Core set of fetched fields the "missing tags" view flags as absent (see
# the Statistics-tab docs).  Split into always-checked album/credit fields and
# the two romanised "sort" fields, which are only *expected* when their source
# field is Japanese — so an all-English album isn't flagged for a missing
# titlesort, nor a Latin-named circle for a missing albumartistsort.  Excludes
# grouping (the untagged-albums branch already surfaces it), the TouhouDB-only
# artist/artistsort and title (not fetched).
_MISSING_BASE: list[str] = [
    "album", "albumartist", "arranger", "catalognumber",
    "date", "lyricist", "vocalist", "year",
]
# sort field → the source field whose CJK-ness makes that sort field expected.
_MISSING_CJK: dict[str, str] = {
    "albumartistsort": "albumartist",
    "titlesort": "title",
}
# Every field read per file for the missing-tags check (presence only).
_MISSING_TAGS: tuple[str, ...] = tuple(_MISSING_BASE) + tuple(_MISSING_CJK)
# Source fields whose Japanese-ness gates a "sort" field (deduped values above).
_CJK_SOURCES: tuple[str, ...] = tuple(sorted(set(_MISSING_CJK.values())))


def _has_cjk(text: str | None) -> bool:
    """True when *text* is non-empty and contains a CJK character."""
    return bool(text) and _CJK_RE.search(text) is not None


def _read_stats_record(
    fp: str,
) -> tuple:
    """Open *fp* once and derive its scan record (no caching).

    Returns ``(grouping, present, cjk, title, album, albumartist, length,
    genres)`` where *present* is the subset of :data:`_MISSING_TAGS` carrying
    a non-empty value, *cjk* is the subset of :data:`_CJK_SOURCES` whose value
    contains a CJK character, the next four fields feed the per-theme detail
    index (*length* is the duration in seconds, or ``None`` when unreadable),
    and *genres* is the multi-value ``genre`` tag as a list (feeds the
    genre-popularity chart).
    """
    tags = read_stats_fields(fp)
    present = {t for t in _MISSING_TAGS if (tags.get(t) or "").strip()}
    cjk = {src for src in _CJK_SOURCES if _has_cjk(tags.get(src))}
    return (tags.get("grouping"), present, cjk,
            tags.get("title"), tags.get("album"), tags.get("albumartist"),
            tags.get("length"), tags.get("genres") or [])


def _album_missing_tags(present: set[str], cjk: set[str]) -> list[str]:
    """Core fetched fields a processed album lacks, alphabetical.

    A field is missing when *no* track in the album carries it (*present* is the
    union across the album's tracks).  The two romanised "sort" fields are only
    counted as missing when their source field is Japanese on some track
    (*cjk*) — an all-English album legitimately has no titlesort, a Latin-named
    circle no albumartistsort.
    """
    missing = [t for t in _MISSING_BASE if t not in present]
    for sort_tag, src in _MISSING_CJK.items():
        if src in cjk and sort_tag not in present:
            missing.append(sort_tag)
    missing.sort()
    return missing


def _stats_record_for(
    fp: str, cache: dict | None, seen: set | None,
) -> tuple:
    """Return the :func:`_read_stats_record` tuple for a file, cached.

    When *cache* is provided it is keyed by path → ``[mtime_ns, grouping,
    present_list, cjk_list, title, album, albumartist, length, genres]``.  A
    hit (same modification time *and* the current 9-element shape) skips the
    mutagen open entirely; a miss — including any legacy entry of a different
    length (e.g. one predating this shape) — reads the file and updates the
    cache (so the first scan after such an upgrade re-reads every file, then
    later scans are fast again).  *seen* collects every path looked at, so the
    caller can prune entries for deleted files.  Files that can't be
    ``stat``-ed are read directly and not cached.
    """
    if cache is None:
        return _read_stats_record(fp)
    try:
        mtime = os.stat(fp).st_mtime_ns
    except OSError:
        return _read_stats_record(fp)
    if seen is not None:
        seen.add(fp)
    entry = cache.get(fp)
    if entry is not None and entry[0] == mtime and len(entry) == 9:
        return (entry[1], set(entry[2]), set(entry[3]),
                entry[4], entry[5], entry[6], entry[7], list(entry[8]))
    record = _read_stats_record(fp)
    (grouping, present, cjk,
     title, album, albumartist, length, genres) = record
    cache[fp] = [mtime, grouping, sorted(present), sorted(cjk),
                 title, album, albumartist, length, list(genres)]
    return record


def _build_theme_details(theme_tracks: dict[str, list[dict]]) -> dict:
    """Reduce the raw per-theme track lists to compact detail records.

    *theme_tracks* maps each theme to every track carrying it, as dicts with
    ``title``/``length``/``circle``/``album``/``solo`` keys (``solo`` is True
    when the track's grouping names exactly that one theme).  The returned
    ``{theme: record}`` dict is what the Information window shows and what is
    persisted with the scan result, so it deliberately keeps only:

    * ``solo_longest`` / ``solo_shortest`` — up to 5 tracks each (dicts with
      ``title``/``length``/``circle``/``album``) among the solo remixes,
      longest/shortest first respectively.  Tracks whose duration couldn't be
      read are left out of these lists (they can't be ranked).
    * ``multi_longest`` / ``multi_shortest`` — the same for multi-theme
      remixes.
    * ``top_circle`` / ``top_circle_count`` / ``top_circle_songs`` — the
      circle with the most remixes of the theme (solo **and** multi; ties
      break alphabetically), its count, and all of its remixes grouped by
      album (``{album: [{title, length}, …]}``, titles sorted).  Absent when
      no track had a circle.
    """
    def _compact(e: dict) -> dict:
        return {"title": e["title"], "length": e["length"],
                "circle": e["circle"], "album": e["album"]}

    details: dict[str, dict] = {}
    for theme, entries in theme_tracks.items():
        solo = [e for e in entries if e["solo"] and e["length"]]
        multi = [e for e in entries if not e["solo"] and e["length"]]
        rec: dict = {}
        for key, rows in (("solo", solo), ("multi", multi)):
            # Pre-sort by title so equal-length tracks list alphabetically
            # (sorted() is stable).
            rows.sort(key=lambda e: e["title"].lower())
            rec[key + "_longest"] = [
                _compact(e)
                for e in sorted(rows, key=lambda e: -e["length"])[:5]
            ]
            rec[key + "_shortest"] = [
                _compact(e)
                for e in sorted(rows, key=lambda e: e["length"])[:5]
            ]
        counts = Counter(e["circle"] for e in entries if e["circle"])
        if counts:
            top_n = max(counts.values())
            top = sorted((c for c, n in counts.items() if n == top_n),
                         key=str.lower)[0]
            songs: dict[str, list[dict]] = {}
            for e in entries:
                if e["circle"] == top:
                    songs.setdefault(e["album"], []).append(
                        {"title": e["title"], "length": e["length"]})
            for lst in songs.values():
                lst.sort(key=lambda s: s["title"].lower())
            rec["top_circle"] = top
            rec["top_circle_count"] = top_n
            rec["top_circle_songs"] = songs
        details[theme] = rec
    return details


def scan_library(
    root: str,
    known_themes: set[str],
    *,
    cache=None,
    progress_cb=None,
    cancel_cb=None,
) -> dict:
    """Scan a ``<root>/<artist>/<album>/<tracks>`` library for tag coverage.

    For every artist, reads each track's ``grouping`` tag.  An artist is
    *tagged* when at least one of its tracks has a grouping value (or one of
    its semicolon-separated pieces) found in *known_themes*.  Every matching
    grouping piece also increments a per-theme song counter.  Every value of a
    track's multi-value ``genre`` tag likewise increments a per-genre song
    counter (``genre_counts``) — counted case-insensitively with the most
    common spelling as the display form, and unfiltered: the
    genre-popularity view drops :data:`_EXCLUDED_GENRES` at display time.

    When *cache* (a dict) is supplied it is used and updated in place as an
    mtime-keyed per-file grouping cache — unchanged files skip the mutagen
    read.  On a fully-completed scan, entries for files no longer on disk are
    pruned; a cancelled scan leaves the cache otherwise untouched so unvisited
    entries survive.

    ``progress_cb(done_artists, total_artists)`` is called after each artist;
    ``cancel_cb()`` is polled between artists and, when it returns truthy,
    stops the scan early (the result is marked ``cancelled``).

    Because every file is already opened for its tags, two per-album
    classifications are computed here for free, in the same pass — rather than
    re-walking the disk later, per artist, when an artist row is expanded:

    * ``untagged_albums`` — albums with no known theme, per artist as **paths
      relative to** *root* (only artists with ≥ 1 such album appear).
    * ``missing_tags`` — for each *processed* album (one that has a theme),
      the Core fetched fields it lacks (:func:`_album_missing_tags`),
      as ``{artist name: {album path relative to root: [tag, …]}}`` (only
      processed albums with ≥ 1 missing field, only artists with ≥ 1 such
      album).  This drives the Statistics tab's "Missing tags" view.
    * ``theme_details`` — per-theme detail records for the theme-popularity
      "Information" window (:func:`_build_theme_details`): the top-5
      longest/shortest solo and multi-theme remixes, and the circle with the
      most remixes plus its songs grouped by album.

    Either key's mere presence in the result signals the data was computed for
    *every* artist, so an absent artist simply has none.

    Returns::

        {"root", "total_artists", "tagged_artists" (sorted names),
         "untagged_artists" (sorted names), "theme_counts" (count >= 1 only),
         "genre_counts" (genre → song count, count >= 1 only),
         "artist_sizes" (name → total folder size in bytes),
         "untagged_albums" (name → [album path relative to root, …]),
         "missing_tags" (name → {album path relative to root: [tag, …]}),
         "theme_details" (theme → detail record),
         "cancelled"}
    """
    artists = _list_artist_dirs(root)
    total = len(artists)
    tagged: list[str] = []
    untagged: list[str] = []
    theme_counts: Counter[str] = Counter()
    # Genre song counts, keyed casefolded so "Jpop"/"JPop" pool together;
    # genre_spellings tallies the raw spellings per key so the result can use
    # the most common one as the display form (deterministically — file walk
    # order must not decide between "Rock" and "rock").
    genre_counts: Counter[str] = Counter()
    genre_spellings: dict[str, Counter] = {}
    artist_sizes: dict[str, int] = {}
    untagged_albums: dict[str, list[str]] = {}
    missing_tags: dict[str, dict[str, list[str]]] = {}
    # theme → every track carrying it (one shared entry dict per track), the
    # raw material _build_theme_details reduces to the compact per-theme
    # records at the end of the scan.
    theme_tracks: dict[str, list[dict]] = {}
    cancelled = False
    seen: set | None = set() if cache is not None else None

    for i, (name, adir) in enumerate(artists):
        if cancel_cb is not None and cancel_cb():
            cancelled = True
            break
        artist_has_theme = False
        artist_bytes = 0
        artist_untagged: list[str] = []
        artist_missing: dict[str, list[str]] = {}
        for album in _list_album_dirs(adir):
            files, album_bytes = _album_audio_files(album)
            artist_bytes += album_bytes
            album_has_theme = False
            album_present: set[str] = set()
            album_cjk: set[str] = set()
            for fp in files:
                (grouping, present, cjk,
                 title, album_tag, albumartist, length,
                 genres) = _stats_record_for(fp, cache, seen)
                for g in genres:
                    key = g.casefold()
                    genre_spellings.setdefault(key, Counter())[g] += 1
                    genre_counts[key] += 1
                pieces = _split_grouping(grouping)
                known = [t for t in pieces if t in known_themes]
                if known:
                    album_has_theme = True
                    entry = {
                        "title": title
                        or os.path.splitext(os.path.basename(fp))[0],
                        "length": length,
                        "circle": albumartist or name,
                        "album": album_tag or os.path.basename(album),
                        # "Solo" = the grouping names exactly one theme; any
                        # second piece (known or not) makes it a multi-theme
                        # remix.
                        "solo": len(pieces) == 1,
                    }
                    for theme in known:
                        theme_counts[theme] += 1
                        theme_tracks.setdefault(theme, []).append(entry)
                album_present |= present
                album_cjk |= cjk
            if album_has_theme:
                artist_has_theme = True
                # Only already-processed albums are checked for missing fields;
                # an untagged album's gaps are the untagged-albums branch's job.
                miss = _album_missing_tags(album_present, album_cjk)
                if miss:
                    artist_missing[os.path.relpath(album, root)] = miss
            else:
                artist_untagged.append(os.path.relpath(album, root))
        artist_sizes[name] = artist_bytes
        if artist_untagged:
            untagged_albums[name] = artist_untagged
        if artist_missing:
            missing_tags[name] = artist_missing
        (tagged if artist_has_theme else untagged).append(name)
        if progress_cb is not None:
            progress_cb(i + 1, total)

    # Drop cache entries for files that no longer exist — but only after a
    # complete scan, since a cancelled run never visited every file.
    if cache is not None and not cancelled and seen is not None:
        for stale in set(cache) - seen:
            del cache[stale]

    tagged.sort(key=str.lower)
    untagged.sort(key=str.lower)
    return {
        "root": root,
        "total_artists": total,
        "tagged_artists": tagged,
        "untagged_artists": untagged,
        "theme_counts": dict(theme_counts),
        # Display form per genre: the most common spelling, ties broken
        # alphabetically (so "Rock" beats "rock" on an even split).
        "genre_counts": {
            min(genre_spellings[k].items(),
                key=lambda kv: (-kv[1], kv[0]))[0]: n
            for k, n in genre_counts.items()
        },
        "artist_sizes": artist_sizes,
        "untagged_albums": untagged_albums,
        "missing_tags": missing_tags,
        "theme_details": _build_theme_details(theme_tracks),
        "cancelled": cancelled,
    }


def classify_artist_albums(
    artist_dir: str,
    known_themes: set[str],
    *,
    cache=None,
) -> list[tuple[str, bool]]:
    """Return ``[(album_dir, has_known_theme), …]`` for one artist folder.

    *has_known_theme* is True when any track in that album carries a
    ``grouping`` value (or one of its semicolon-separated pieces) found in
    *known_themes*.  Used when marking an artist as unavailable: albums that
    are already tagged are left alone, only the rest are flagged.

    Reuses the same mtime-keyed per-file *cache* as :func:`scan_library` when
    one is supplied, so repeated marks don't re-open every file.  The caller
    owns loading/saving the cache.
    """
    seen: set | None = set() if cache is not None else None
    out: list[tuple[str, bool]] = []
    for album in _list_album_dirs(artist_dir):
        files, _ = _album_audio_files(album)
        has_theme = False
        for fp in files:
            grouping = _stats_record_for(fp, cache, seen)[0]
            for theme in _split_grouping(grouping):
                if theme in known_themes:
                    has_theme = True
                    break
            if has_theme:
                break
        out.append((album, has_theme))
    return out


# ---------------------------------------------------------------------------
# Pie chart widget (custom-painted; modelled on gui.py's _FetchStatusBar)
# ---------------------------------------------------------------------------
class _PieChartWidget(QtWidgets.QWidget):
    """A clickable three-slice pie chart: tagged / untagged / unavailable.

    Emits :pyattr:`sliceClicked` with ``"tagged"``, ``"untagged"`` or
    ``"unavailable"`` when the matching wedge is clicked.  Tagged uses the
    palette highlight; untagged a fixed red; unavailable (artists with no page
    on either wiki) a fixed yellow — all chosen to read in light/dark themes.
    """

    sliceClicked = QtCore.pyqtSignal(str)

    _FAIL_COLOR = "#c0392b"     # same red _FetchStatusBar uses for failures
    _UNAVAIL_COLOR = "#f1c40f"  # yellow for "no wiki page — can't be tagged"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tagged = 0
        self._untagged = 0
        self._unavailable = 0
        self._hover = ""   # "", "tagged", "untagged", or "unavailable"
        self.setMouseTracking(True)
        self.setMinimumSize(220, 200)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        self.setCursor(QtCore.Qt.PointingHandCursor)

    # --- public API ---
    def setCounts(
        self, tagged: int, untagged: int, unavailable: int = 0
    ) -> None:
        self._tagged = max(0, int(tagged))
        self._untagged = max(0, int(untagged))
        self._unavailable = max(0, int(unavailable))
        self._hover = ""
        self.update()

    # --- slice model ---
    def _ordered_slices(self) -> list[tuple[str, int]]:
        """Wedges in draw order, including zero-count ones (for the legend)."""
        return [
            ("tagged", self._tagged),
            ("untagged", self._untagged),
            ("unavailable", self._unavailable),
        ]

    def _slice_color(self, key: str) -> QtGui.QColor:
        pal = self.palette()
        if key == "tagged":
            color = pal.color(QtGui.QPalette.Highlight)
        elif key == "untagged":
            color = QtGui.QColor(self._FAIL_COLOR)
        else:
            color = QtGui.QColor(self._UNAVAIL_COLOR)
        if self._hover == key:
            color = color.lighter(120)
        return color

    # --- geometry ---
    def _pie_rect(self) -> QtCore.QRect:
        """Square drawing area for the pie, left-aligned with margins."""
        m = 12
        size = min(self.width() - 2 * m, self.height() - 2 * m)
        size = max(10, size)
        return QtCore.QRect(m, (self.height() - size) // 2, size, size)

    def _slice_at(self, x: int, y: int) -> str:
        """Return which wedge contains point (x, y), or "" if outside."""
        data = [(k, c) for k, c in self._ordered_slices() if c > 0]
        total = sum(c for _, c in data)
        if total <= 0:
            return ""
        rect = self._pie_rect()
        cx = rect.x() + rect.width() / 2.0
        cy = rect.y() + rect.height() / 2.0
        r = rect.width() / 2.0
        dx = x - cx
        dy = y - cy
        if dx * dx + dy * dy > r * r:
            return ""
        # Angle measured counter-clockwise from 3 o'clock, matching how Qt's
        # drawPie interprets start/span angles (which are in 1/16°).
        ang = math.degrees(math.atan2(-dy, dx)) % 360.0
        # Wedges are drawn from 90° (12 o'clock) going clockwise; ``delta`` is
        # the clockwise distance of the click from that start, and each wedge
        # occupies the next ``span`` degrees of it.
        delta = (90.0 - ang) % 360.0
        acc = 0.0
        for key, count in data:
            span = 360.0 * count / total
            if delta < acc + span:
                return key
            acc += span
        return data[-1][0]

    # --- painting ---
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = self.palette()
        total = self._tagged + self._untagged + self._unavailable

        rect = self._pie_rect()
        if total <= 0:
            painter.setPen(pal.color(QtGui.QPalette.Mid))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "No data — click Scan",
            )
            painter.end()
            return

        data = [(k, c) for k, c in self._ordered_slices() if c > 0]
        # Start at 90° (12 o'clock); spans are negative to go clockwise.  The
        # final wedge fills whatever's left so rounding never leaves a gap.
        start16 = int(90 * 16)
        painter.setPen(QtGui.QPen(pal.color(QtGui.QPalette.Base), 1))
        drawn16 = 0
        for idx, (key, count) in enumerate(data):
            if idx < len(data) - 1:
                span16 = -int(round(360.0 * count / total * 16))
            else:
                span16 = -(360 * 16) - drawn16
            painter.setBrush(self._slice_color(key))
            painter.drawPie(rect, start16 + drawn16, span16)
            drawn16 += span16

        # --- legend, to the right of the pie ---
        lx = rect.right() + 18
        ly = rect.y() + 8
        box = 14
        gap = 26
        labels = {
            "tagged": "Tagged",
            "untagged": "Untagged",
            "unavailable": "Unavailable",
        }
        counts = {
            "tagged": self._tagged,
            "untagged": self._untagged,
            "unavailable": self._unavailable,
        }
        painter.setPen(pal.color(QtGui.QPalette.WindowText))
        for idx, key in enumerate(("tagged", "untagged", "unavailable")):
            n = counts[key]
            pct = 100.0 * n / total
            y = ly + idx * gap
            painter.fillRect(
                QtCore.QRect(lx, y, box, box), self._slice_color(key)
            )
            painter.drawText(
                QtCore.QRect(lx + box + 8, y - 2, 240, box + 6),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                f"{labels[key]}: {n:,}  ({pct:.0f}%)",
            )
        painter.end()

    # --- interaction ---
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        which = self._slice_at(event.x(), event.y())
        if which != self._hover:
            self._hover = which
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover:
            self._hover = ""
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.LeftButton:
            which = self._slice_at(event.x(), event.y())
            if which:
                self.sliceClicked.emit(which)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Theme-popularity bar chart (custom-painted; swaps in for the pie)
# ---------------------------------------------------------------------------
def _nice_axis_max(value: float) -> tuple[float, float]:
    """Return ``(axis_max, tick)`` — a round upper bound and gridline step.

    Picks the round step (a 1/2/2.5/5 × power-of-ten value) that lands the
    chart on roughly 4–6 evenly-spaced gridlines, so the axis re-scales as the
    library grows (e.g. ~2000 songs → ticks every 500: 500/1000/1500/2000).
    ``axis_max`` is rounded up to a whole number of ticks so the longest bar
    never reaches the very edge unless the count is exactly on a tick.
    """
    if value <= 0:
        return 1.0, 1.0
    if value <= 8:   # tiny counts: integer ticks, no fractional steps
        return float(value), 1.0
    mag = 10 ** math.floor(math.log10(value))
    for mult in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10):
        tick = mult * mag
        n = math.ceil(value / tick)
        if 4 <= n <= 6:
            return n * tick, tick
    tick = float(mag)
    return math.ceil(value / tick) * tick, tick


class _ThemeBarChart(QtWidgets.QWidget):
    """Horizontal bar chart of theme popularity, tallest bar on top.

    Also reused as-is for the genre-popularity view — the bars are just
    ``(label, count)`` pairs, only the data and the empty-state text differ
    (both supplied via :meth:`setData`).

    Fed a list of ``(theme, count)`` pre-sorted descending.  Sizes itself to
    its full content height so it scrolls vertically inside a ``QScrollArea``.
    Bars use the palette highlight (matching the pie's "tagged" slice); faint
    vertical gridlines at :func:`_nice_axis_max` intervals are labelled along
    the top so a bar's length reads off as a song count.  Each bar's name +
    count is drawn **inside** the bar — elided with an ellipsis (and a hover
    tooltip with the full name) when it doesn't fit — until the bar is too
    short to hold even ~``_MIN_INSIDE_CHARS`` characters, at which point the
    full name is drawn just past the bar's end on the background instead.
    """

    _ROW_H = 26          # px per bar row (bar + gap)
    _BAR_GAP = 6         # vertical gap between consecutive bars
    _TOP_PAD = 24        # room along the top for the axis value labels
    _BOTTOM_PAD = 8
    _LEFT_PAD = 10
    _RIGHT_PAD = 14
    _TEXT_PAD = 12       # total horizontal padding for text inside a bar
    _MIN_INSIDE_CHARS = 8  # below ~this much room, label moves to the right

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._data: list[tuple[str, int]] = []   # (theme, count), desc by count
        self._max = 0
        self._empty_text = "No data yet."
        # row index → full theme name, for rows whose label was truncated;
        # rebuilt each paint and consulted on hover for the tooltip.
        self._row_tooltips: dict[int, str] = {}
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )

    def setData(
        self, data: list[tuple[str, int]], empty_text: str | None = None,
    ) -> None:
        """Replace the bars.  *data* must be pre-sorted most-popular-first.

        *empty_text*, when given, is what an empty chart displays — the
        theme and genre views pass their own wording.
        """
        if empty_text is not None:
            self._empty_text = empty_text
        self._data = list(data)
        self._max = max((c for _, c in self._data), default=0)
        self._row_tooltips = {}
        # Size to fit every bar so the scroll area gets the full extent.
        height = self._TOP_PAD + self._BOTTOM_PAD + self._ROW_H * len(self._data)
        self.setMinimumHeight(max(height, self._TOP_PAD + self._BOTTOM_PAD))
        self.updateGeometry()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pal = self.palette()

        if not self._data or self._max <= 0:
            painter.setPen(pal.color(QtGui.QPalette.Mid))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter, self._empty_text
            )
            painter.end()
            return

        x0 = self._LEFT_PAD
        plot_w = max(1, self.width() - self._LEFT_PAD - self._RIGHT_PAD)
        axis_max, tick = _nice_axis_max(self._max)

        # --- background gridlines + value labels along the top ---
        # Derive the grid/label colours from WindowText (not Mid): in dark
        # themes Mid sits almost on the window background and was invisible.
        # A faded WindowText reads in both light and dark palettes.
        wt = pal.color(QtGui.QPalette.WindowText)
        grid_col = QtGui.QColor(wt)
        grid_col.setAlpha(60)
        label_col = QtGui.QColor(wt)
        label_col.setAlpha(180)
        small_font = painter.font()
        small_font.setPointSizeF(max(7.0, small_font.pointSizeF() - 1.0))
        grid_fm = QtGui.QFontMetrics(small_font)
        bottom = self.height() - self._BOTTOM_PAD
        v = 0.0
        while v <= axis_max + 1e-9:
            x = x0 + plot_w * (v / axis_max)
            painter.setPen(QtGui.QPen(grid_col, 1, QtCore.Qt.DotLine))
            painter.drawLine(int(x), self._TOP_PAD, int(x), bottom)
            painter.setPen(label_col)
            painter.setFont(small_font)
            label = f"{int(round(v)):,}"
            fm = grid_fm
            tw = fm.horizontalAdvance(label)
            # Anchor the first label left and the last right so neither clips.
            if v <= 0:
                lx = int(x)
            elif v >= axis_max - 1e-9:
                lx = int(x) - tw
            else:
                lx = int(x) - tw // 2
            painter.drawText(lx, self._TOP_PAD - 6, label)
            v += tick

        # --- bars, tallest first ---
        painter.setFont(self.font())
        fm = self.fontMetrics()
        flags = int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        bar_color = pal.color(QtGui.QPalette.Highlight)
        inside_pen = pal.color(QtGui.QPalette.HighlightedText)
        outside_pen = pal.color(QtGui.QPalette.WindowText)
        # Minimum room for a label to stay *inside* the bar — below this the
        # bar is too short to read even a few characters, so the name moves to
        # the background on the right.
        min_inside = fm.averageCharWidth() * self._MIN_INSIDE_CHARS
        self._row_tooltips = {}
        for i, (theme, count) in enumerate(self._data):
            y = self._TOP_PAD + i * self._ROW_H + self._BAR_GAP // 2
            bh = self._ROW_H - self._BAR_GAP
            bar_w = plot_w * (count / axis_max)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(bar_color)
            painter.drawRoundedRect(
                QtCore.QRectF(x0, y, max(2.0, bar_w), bh), 3, 3
            )
            inner_w = bar_w - self._TEXT_PAD
            if inner_w >= min_inside:
                # Enough room to read inside the bar: draw there, eliding the
                # theme (but always keeping the count) when it overflows, with
                # a hover tooltip giving the full name.
                painter.setPen(inside_pen)
                shown, truncated = self._compose_label(fm, theme, count, inner_w)
                if truncated:
                    self._row_tooltips[i] = theme
                painter.drawText(
                    QtCore.QRectF(x0 + 6, y, max(2.0, inner_w), bh),
                    flags, shown,
                )
            else:
                # Bar too short for even a few characters: draw the name + count
                # just past its end on the background, clipped to the plot so a
                # very long name doesn't run off the widget.
                painter.setPen(outside_pen)
                tx = x0 + bar_w + 6
                avail = max(10.0, x0 + plot_w + self._RIGHT_PAD - tx)
                shown, truncated = self._compose_label(fm, theme, count, avail)
                if truncated:
                    self._row_tooltips[i] = theme
                painter.drawText(QtCore.QRectF(tx, y, avail, bh), flags, shown)
        painter.end()

    @staticmethod
    def _compose_label(fm, theme: str, count: int, avail: float) -> tuple[str, bool]:
        """Build a ``"theme  (count)"`` label that fits in *avail* px.

        The ``(count)`` suffix is always preserved; only the theme name is
        elided (so ``The Maid …  (449)`` rather than losing the count off the
        end).  Returns ``(text, truncated)`` where *truncated* is True when the
        theme had to be shortened — the caller uses it to attach a tooltip.
        """
        suffix = f"  ({count:,})"
        full = theme + suffix
        if fm.horizontalAdvance(full) <= avail:
            return full, False
        theme_avail = int(avail - fm.horizontalAdvance(suffix))
        if theme_avail <= 0:
            # Not even room for the count plus a sliver of theme — fall back to
            # eliding the whole label (very narrow bar and/or a huge count).
            return fm.elidedText(full, QtCore.Qt.ElideRight, int(max(0.0, avail))), True
        return fm.elidedText(theme, QtCore.Qt.ElideRight, theme_avail) + suffix, True

    # --- hover tooltip for truncated labels ---
    def _row_at(self, y: int) -> int:
        """Return the bar-row index under vertical position *y*, or -1."""
        if not self._data or y < self._TOP_PAD:
            return -1
        row = (y - self._TOP_PAD) // self._ROW_H
        return row if 0 <= row < len(self._data) else -1

    def event(self, e) -> bool:  # noqa: N802 (Qt naming)
        """Show the full theme name when hovering a row whose label was cut."""
        if e.type() == QtCore.QEvent.ToolTip:
            text = self._row_tooltips.get(self._row_at(e.pos().y()))
            if text:
                QtWidgets.QToolTip.showText(e.globalPos(), text, self)
            else:
                QtWidgets.QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)


# ---------------------------------------------------------------------------
# Per-theme "Information" window (right-click a theme in Theme popularity)
# ---------------------------------------------------------------------------
class _ThemeLengthSection(QtWidgets.QWidget):
    """A titled top-5 track list, switchable between longest and shortest.

    Shows one of the two pre-computed lists from the theme's detail record
    (``*_longest`` / ``*_shortest``); the button in the header row swaps
    between them in place.
    """

    def __init__(self, title: str, longest: list[dict],
                 shortest: list[dict], parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._longest = list(longest)
        self._shortest = list(shortest)
        self._showing_longest = True

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        head = QtWidgets.QHBoxLayout()
        self._header = QtWidgets.QLabel()
        font = self._header.font()
        font.setBold(True)
        self._header.setFont(font)
        self._header.setWordWrap(True)
        head.addWidget(self._header, stretch=1)
        self._toggle = QtWidgets.QPushButton()
        self._toggle.clicked.connect(self._on_toggle)
        head.addWidget(self._toggle)
        layout.addLayout(head)

        self._body = QtWidgets.QLabel()
        self._body.setWordWrap(True)
        self._body.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self._body)
        self._refresh()

    def _on_toggle(self) -> None:
        self._showing_longest = not self._showing_longest
        self._refresh()

    def _refresh(self) -> None:
        rows = self._longest if self._showing_longest else self._shortest
        which = "longest" if self._showing_longest else "shortest"
        self._header.setText(f"{self._title} — {which}")
        self._toggle.setText(
            "Show shortest" if self._showing_longest else "Show longest"
        )
        self._toggle.setEnabled(bool(self._longest or self._shortest))
        if not rows:
            self._body.setText("(no tracks)")
            return
        lines = [
            f"{i}.  {_format_length(e.get('length'))} — "
            f"{e.get('title') or '?'}\n"
            f"      {e.get('circle') or '?'} — {e.get('album') or '?'}"
            for i, e in enumerate(rows, start=1)
        ]
        self._body.setText("\n".join(lines))


class _ThemeInfoDialog(QtWidgets.QDialog):
    """Scrollable per-theme details: track lengths + the top circle.

    Built entirely from the theme's entry in the scan result's
    ``theme_details`` — no disk I/O, so it opens instantly.  The sections are
    stacked vertically inside a scroll area (leaving room for more info
    later): solo-remix lengths, multi-theme-remix lengths, then the circle
    with the most remixes as a foldable tree (circle → albums → songs).
    """

    def __init__(self, theme: str, info: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Theme information — {theme}")
        self.resize(680, 620)
        self._tree: QtWidgets.QTreeWidget | None = None

        outer = QtWidgets.QVBoxLayout(self)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setSpacing(18)

        title = QtWidgets.QLabel(theme)
        font = title.font()
        font.setBold(True)
        font.setPointSizeF(font.pointSizeF() + 2)
        title.setFont(font)
        title.setWordWrap(True)
        layout.addWidget(title)

        layout.addWidget(_ThemeLengthSection(
            "Remixes of only this theme",
            info.get("solo_longest") or [],
            info.get("solo_shortest") or [],
        ))
        layout.addWidget(_ThemeLengthSection(
            "Remixes including this theme (among others)",
            info.get("multi_longest") or [],
            info.get("multi_shortest") or [],
        ))

        head = QtWidgets.QLabel("Circle with the most remixes")
        font = head.font()
        font.setBold(True)
        head.setFont(font)
        layout.addWidget(head)
        circle = info.get("top_circle")
        if not circle:
            layout.addWidget(QtWidgets.QLabel("(no circle information)"))
        else:
            n = int(info.get("top_circle_count") or 0)
            tree = QtWidgets.QTreeWidget()
            tree.setHeaderHidden(True)
            tree.setColumnCount(1)
            tree.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            # The outer scroll area does the scrolling; the tree just grows
            # and shrinks with its expanded rows.
            tree.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            root = QtWidgets.QTreeWidgetItem(
                [f"{circle}  ({n:,} song{'s' if n != 1 else ''})"]
            )
            tree.addTopLevelItem(root)
            songs = info.get("top_circle_songs") or {}
            for album in sorted(songs, key=str.lower):
                album_item = QtWidgets.QTreeWidgetItem([album])
                root.addChild(album_item)
                for song in songs[album]:
                    album_item.addChild(QtWidgets.QTreeWidgetItem([
                        f"{song.get('title') or '?'}  "
                        f"({_format_length(song.get('length'))})"
                    ]))
                # Expanding the circle should reveal the songs already
                # grouped under their album headers, so albums start open
                # (invisible until the collapsed root is expanded).
                album_item.setExpanded(True)
            tree.itemExpanded.connect(self._resize_tree)
            tree.itemCollapsed.connect(self._resize_tree)
            self._tree = tree
            self._resize_tree()
            layout.addWidget(tree)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _resize_tree(self, *_args) -> None:
        """Fix the circle tree's height to its currently-visible rows."""
        tree = self._tree
        if tree is None:
            return

        def visible(item) -> int:
            count = 1
            if item.isExpanded():
                for i in range(item.childCount()):
                    count += visible(item.child(i))
            return count

        rows = sum(
            visible(tree.topLevelItem(i))
            for i in range(tree.topLevelItemCount())
        )
        row_h = tree.sizeHintForRow(0)
        if row_h <= 0:
            row_h = tree.fontMetrics().height() + 8
        tree.setFixedHeight(rows * row_h + 2 * tree.frameWidth() + 4)


# ---------------------------------------------------------------------------
# Scan worker (off the GUI thread; modelled on gui.py's _WikiWorker)
# ---------------------------------------------------------------------------
_WRAP_PAD = 4   # px of breathing room around wrapped item text
_WRAP_FLAGS = int(QtCore.Qt.TextWordWrap | QtCore.Qt.AlignLeft
                  | QtCore.Qt.AlignVCenter)

# Item-data roles for the detail tree (alongside Qt.UserRole, which holds the
# folder path).  ``_ROLE_KIND`` distinguishes top-level artist/theme rows from
# the lazily-added album children (and the non-selectable placeholder/note
# rows); ``_ROLE_LOADED`` records whether an artist's album children have been
# computed yet, so re-expanding doesn't recompute.
_ROLE_KIND = int(QtCore.Qt.UserRole) + 1
_ROLE_LOADED = int(QtCore.Qt.UserRole) + 2
# Theme rows only: the raw theme name (display text prepends the count), so
# the context menu's "Information" action doesn't have to parse it back out.
_ROLE_THEME = int(QtCore.Qt.UserRole) + 3


class _WrapTextDelegate(QtWidgets.QStyledItemDelegate):
    """Paints list item text word-wrapped into the row's full width.

    Used together with :class:`_WrapListWidget`, which sets each row's height
    (via the item's own size hint) from the *actual* viewport width.  Painting
    the wrapped text here — rather than relying on ``QListWidget``'s built-in
    wrap, whose sizing and painting can disagree on width and end up
    ellipsising the overflow — keeps sizing and drawing on the same width, so
    the full name always shows.
    """

    def paint(self, painter, option, index):  # noqa: N802 (Qt naming)
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""   # draw background / selection without the default text
        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget)

        painter.save()
        role = (QtGui.QPalette.HighlightedText
                if opt.state & QtWidgets.QStyle.State_Selected
                else QtGui.QPalette.Text)
        painter.setPen(opt.palette.color(role))
        painter.setFont(opt.font)
        text_rect = opt.rect.adjusted(_WRAP_PAD + 2, _WRAP_PAD,
                                      -_WRAP_PAD, -_WRAP_PAD)
        painter.drawText(text_rect, _WRAP_FLAGS, text)
        painter.restore()


class _WrapListWidget(QtWidgets.QListWidget):
    """A list whose rows grow to fit word-wrapped text at the current width.

    Each item's height is computed from the live viewport width and recomputed
    on resize, so the height the view reserves always matches the width the
    text is painted into — no clipping, no ellipsis.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTextElideMode(QtCore.Qt.ElideNone)
        self.setWordWrap(True)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(_WrapTextDelegate(self))

    def _text_width(self) -> int:
        return max(16, self.viewport().width() - 2 * _WRAP_PAD - 2)

    def relayout_rows(self) -> None:
        """Recompute every row's height for the current viewport width."""
        fm = self.fontMetrics()
        width = self._text_width()
        for i in range(self.count()):
            item = self.item(i)
            rect = fm.boundingRect(
                QtCore.QRect(0, 0, width, 1_000_000), _WRAP_FLAGS, item.text(),
            )
            item.setSizeHint(QtCore.QSize(0, rect.height() + 2 * _WRAP_PAD))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.relayout_rows()


class _WrapTreeWidget(QtWidgets.QTreeWidget):
    """A single-column tree whose rows word-wrap to the current width.

    The tree analogue of :class:`_WrapListWidget`: it reuses the same
    :class:`_WrapTextDelegate` and per-row sizing-from-viewport-width approach,
    but supports the one extra thing a flat list can't — **expandable artist
    rows**, where each tagged artist can be opened (via its native expansion
    arrow) to reveal the albums under it that carry no ``grouping`` theme.
    Child rows are indented, so each row's
    available text width is reduced by its depth's worth of indentation.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setTextElideMode(QtCore.Qt.ElideNone)
        self.setWordWrap(True)
        self.setUniformRowHeights(False)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(_WrapTextDelegate(self))
        # Let the user drag selected artist/album rows *out* of the app —
        # e.g. onto a terminal (which reads text/uri-list and inserts the
        # folder paths) or a file manager.  DragOnly: rows can leave but the
        # tree accepts no drops (no reordering / no drop target).
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)

    def mimeData(self, items):  # noqa: N802 (Qt naming)
        """Build the drag payload from the selected rows' folder paths.

        Each artist/album row stores its absolute directory in
        ``Qt.UserRole`` (note/placeholder/theme rows store ``None`` and are
        skipped).  We expose the paths two ways so a wide range of drop
        targets work: ``text/uri-list`` (``file://`` URLs — what terminals
        and file managers consume to insert local paths) and ``text/plain``
        (shell-quoted, space-separated — a fallback for targets that only
        read plain text).
        """
        paths: list[str] = []
        for it in items:
            p = it.data(0, QtCore.Qt.UserRole)
            if p and p not in paths:
                paths.append(p)
        md = QtCore.QMimeData()
        if paths:
            md.setUrls([QtCore.QUrl.fromLocalFile(p) for p in paths])
            md.setText(" ".join(shlex.quote(p) for p in paths))
        return md

    @staticmethod
    def _depth(item) -> int:
        depth = 0
        p = item.parent()
        while p is not None:
            depth += 1
            p = p.parent()
        return depth

    def _text_width(self, depth: int) -> int:
        # Subtract one indentation step per level *plus one* for the branch
        # arrow column reserved at the root, so the wrapped width matches what
        # the delegate paints into (the indented cell rect).
        usable = self.viewport().width() - self.indentation() * (depth + 1)
        return max(16, usable - 2 * _WRAP_PAD - 2)

    def relayout_rows(self) -> None:
        """Recompute every row's height (top-level and children) for the
        current viewport width."""
        fm = self.fontMetrics()
        it = QtWidgets.QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            width = self._text_width(self._depth(item))
            rect = fm.boundingRect(
                QtCore.QRect(0, 0, width, 1_000_000), _WRAP_FLAGS, item.text(0),
            )
            item.setSizeHint(0, QtCore.QSize(0, rect.height() + 2 * _WRAP_PAD))
            it += 1

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self.relayout_rows()


class _StatsScanWorker(QtCore.QThread):
    """Runs :func:`scan_library` off the GUI thread."""

    progress = QtCore.pyqtSignal(int, int)   # (done_artists, total_artists)
    scan_done = QtCore.pyqtSignal(dict)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, root: str, known_themes: set[str]) -> None:
        super().__init__()
        self._root = root
        self._known = known_themes
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Safe to call from the GUI thread; sampled between artists."""
        self._cancel_requested = True

    def run(self) -> None:  # noqa: D401
        try:
            cache = _load_stats_cache()
            result = scan_library(
                self._root, self._known,
                cache=cache,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                cancel_cb=lambda: self._cancel_requested,
            )
            # Persist the refreshed cache (off the GUI thread) before
            # reporting — even a cancelled scan's reads are valid to keep.
            _save_stats_cache(cache)
            self.scan_done.emit(result)
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# The tab
# ---------------------------------------------------------------------------
class StatisticsTab(QtWidgets.QWidget):
    """Collection-wide tagging statistics with a clickable pie chart."""

    def __init__(self) -> None:
        super().__init__()
        self._worker: _StatsScanWorker | None = None
        self._known_themes: set[str] = load_known_themes()
        self._last: dict | None = None      # cached scan result
        self._persisted = False             # _last came from a reloaded scan
        # Artist names partitioned by availability, recomputed from _last and
        # the live availability store every time either changes.
        self._buckets: dict[str, list[str]] = {
            "tagged": [], "untagged": [], "unavailable": [],
        }
        # artist folder (normalised) → basenames of its flagged albums; drives
        # the warning sign + tooltip on partially-tagged artists.
        self._missing_by_artist: dict[str, list[str]] = {}
        self._panel_mode = ""               # tagged/untagged/unavailable/themes
        # Artist bucket shown before switching to the theme bar chart, so the
        # "Artist details" toggle can restore the exact prior pie+list view.
        self._prev_artist_mode = ""
        # Unfiltered rows currently shown, each (display_text, folder_path,
        # theme_name); folder_path is None for theme rows (nothing to open)
        # and theme_name is None for artist rows.
        self._panel_rows: list[tuple[str, str | None, str | None]] = []
        # Raw source data behind the panel, kept so re-sorting doesn't have to
        # re-parse display strings.  Artists: (name, path, size_bytes);
        # themes: (theme, None, count).
        self._raw_rows: list[tuple] = []
        # Per-artist cache of "untagged" albums (no grouping theme),
        # keyed by normalised artist path → list of
        # (album_basename, album_path).  Normally populated wholesale from the
        # scan result (``untagged_albums``, computed during the scan itself);
        # for an old persisted result that predates that data it falls back to
        # computing one artist on first expand and caching it here.
        self._artist_untagged_albums: dict[str, list[tuple[str, str]]] = {}
        # True when the loaded result carried per-album classification for the
        # whole library, so an artist *absent* from the cache means "scanned,
        # has no untagged albums" rather than "not computed yet" (no disk walk).
        self._albums_classified = False
        # Per-artist cache of *processed* albums missing one or more Core fetched
        # fields, keyed by normalised artist path → list of (album_basename,
        # album_path, [missing_tag, …]).  Populated wholesale from the scan
        # result (``missing_tags``); drives the "Missing tags" view.
        self._artist_missing_albums: dict[
            str, list[tuple[str, str, list[str]]]
        ] = {}
        # True when the loaded result carried the missing-tags classification
        # (a fresh scan with this feature); an old persisted result has False,
        # and the Missing-tags view then prompts a re-scan instead.
        self._missing_classified = False
        # Normalised paths of artists currently expanded, so expansion survives
        # a filter/sort/mark-driven rebuild of the tree.
        self._expanded_artists: set[str] = set()
        self._sort_desc = True              # current sort direction
        # Cross-tab "Send to…" targets, wired by TaggerWindow after all tabs
        # exist.  Each entry is (label, tab); tab exposes add_directory().
        self._send_targets: list = []
        self._tab_widget: QtWidgets.QTabWidget | None = None

        layout = QtWidgets.QVBoxLayout(self)

        # --- Controls row: library root + Browse + Scan + Cancel ---
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Library root:"))
        self._root_edit = QtWidgets.QLineEdit()
        cfg = _load_stats_config()
        self._root_edit.setText(cfg.get("library_root") or DEFAULT_ROOT)
        self._root_edit.setPlaceholderText(
            "Choose the folder containing artist folders"
        )
        controls.addWidget(self._root_edit, stretch=1)

        browse_btn = QtWidgets.QPushButton("&Browse…")
        browse_btn.clicked.connect(self._browse)
        controls.addWidget(browse_btn)

        self._scan_btn = QtWidgets.QPushButton("&Scan")
        self._scan_btn.clicked.connect(self._start_scan)
        controls.addWidget(self._scan_btn)

        self._cancel_btn = QtWidgets.QPushButton("Ca&ncel")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel_scan)
        controls.addWidget(self._cancel_btn)
        layout.addLayout(controls)

        # --- Progress bar (hidden until first scan) ---
        self._progress = QtWidgets.QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("%v / %m artists  (%p%)")
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # --- Summary label ---
        self._summary = QtWidgets.QLabel("Not scanned yet.")
        self._summary.setStyleSheet("color: palette(text);")
        layout.addWidget(self._summary)

        # --- Body: pie on the left, inline detail panel on the right ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._pie = _PieChartWidget()
        self._pie.sliceClicked.connect(self._show_artists)

        # The theme bar chart lives in a scroll area and swaps in for the pie
        # whenever the theme-popularity view is active.
        self._chart = _ThemeBarChart()
        self._chart_scroll = QtWidgets.QScrollArea()
        self._chart_scroll.setWidgetResizable(True)
        self._chart_scroll.setWidget(self._chart)
        self._chart_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._chart_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )

        self._left_stack = QtWidgets.QStackedWidget()
        self._left_stack.addWidget(self._pie)           # index 0
        self._left_stack.addWidget(self._chart_scroll)  # index 1
        splitter.addWidget(self._left_stack)

        panel = QtWidgets.QWidget()
        panel_layout = QtWidgets.QVBoxLayout(panel)
        # A little breathing room (mainly on the left) so the header, filter
        # row and list don't butt right up against the splitter handle.
        panel_layout.setContentsMargins(8, 0, 0, 0)

        top_row = QtWidgets.QHBoxLayout()
        self._panel_header = QtWidgets.QLabel(
            "Click a pie slice, or “Popularity charts”."
        )
        font = self._panel_header.font()
        font.setBold(True)
        self._panel_header.setFont(font)
        top_row.addWidget(self._panel_header, stretch=1)
        self._missing_btn = QtWidgets.QPushButton("&Missing tags")
        self._missing_btn.setToolTip(
            "List already-tagged albums that are missing fields the tagger "
            "fetches (e.g. albumartist, year, titlesort)."
        )
        self._missing_btn.clicked.connect(self._on_missing_toggle)
        top_row.addWidget(self._missing_btn)
        # Drop-down offering the two popularity bar charts (theme / genre),
        # plus the way back to the pie + artist list once one is showing.
        self._charts_btn = QtWidgets.QToolButton()
        self._charts_btn.setText("&Popularity charts")
        self._charts_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        charts_menu = QtWidgets.QMenu(self._charts_btn)
        charts_menu.addAction("Theme popularity", self._show_themes)
        charts_menu.addAction("Genre popularity", self._show_genres)
        charts_menu.addSeparator()
        self._charts_exit_action = charts_menu.addAction(
            "Artist details", self._exit_charts_view
        )
        # "Artist details" only makes sense while a chart is showing.
        charts_menu.aboutToShow.connect(
            lambda: self._charts_exit_action.setEnabled(
                self._panel_mode in ("themes", "genres")
            )
        )
        self._charts_btn.setMenu(charts_menu)
        top_row.addWidget(self._charts_btn)
        panel_layout.addLayout(top_row)

        filter_row = QtWidgets.QHBoxLayout()
        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("Filter…")
        self._filter.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._filter, stretch=1)

        filter_row.addWidget(QtWidgets.QLabel("Sort:"))
        self._sort_combo = QtWidgets.QComboBox()
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_row.addWidget(self._sort_combo)

        self._sort_dir_btn = QtWidgets.QToolButton()
        self._sort_dir_btn.setCheckable(True)
        self._sort_dir_btn.setChecked(self._sort_desc)
        self._sort_dir_btn.toggled.connect(self._on_sort_changed)
        self._update_sort_dir_button()
        filter_row.addWidget(self._sort_dir_btn)
        panel_layout.addLayout(filter_row)

        # Long theme / artist names wrap to the (narrow) panel width and each
        # row grows to fit, so nothing is clipped or ellipsised.  A tree (not a
        # flat list) so each tagged artist can be expanded to its untagged
        # albums via the native arrow.
        self._list = _WrapTreeWidget()
        # Allow selecting several artists/albums at once (for "Send to…").
        self._list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        # Right-click an artist/album row → "Open" its folder in the file
        # manager (and mark/send actions).
        self._list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(
            self._show_list_context_menu
        )
        # Lazily fill an artist's untagged-album children when it is expanded,
        # and remember expansion across rebuilds.
        self._list.itemExpanded.connect(self._on_item_expanded)
        self._list.itemCollapsed.connect(self._on_item_collapsed)
        panel_layout.addWidget(self._list, stretch=1)

        splitter.addWidget(panel)
        # Give the chart/pie the lion's share by default and keep the artist /
        # theme list a thinner side panel; the user can still drag the handle.
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([640, 280])
        layout.addWidget(splitter, stretch=1)

        # Show the last completed scan immediately, without re-scanning.
        last = _load_last_result()
        if last:
            self._apply_result(last, persisted=True)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # Re-partition when the tab is shown so marks made elsewhere (e.g. the
        # Wiki Tagger tab auto-marking an artist) are reflected without a
        # re-scan.  Cheap — _recompute does no disk I/O.
        super().showEvent(event)
        self._recompute()

    # --- controls ---
    def _browse(self) -> None:
        start = self._root_edit.text().strip() or DEFAULT_ROOT
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select library root", start,
        )
        if path:
            self._root_edit.setText(path)

    def _start_scan(self) -> None:
        if self._worker is not None:
            return
        root = self._root_edit.text().strip()
        if not root or not os.path.isdir(root):
            QtWidgets.QMessageBox.warning(
                self, "Statistics",
                "Please choose an existing library root folder.",
            )
            return
        if not self._known_themes:
            QtWidgets.QMessageBox.warning(
                self, "Statistics",
                "No theme mapping found (touhou_theme_mapping.json).\n"
                "Nothing can be classified without it.",
            )
            return
        _save_stats_config(root)

        self._scan_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._root_edit.setEnabled(False)
        self._progress.setRange(0, 0)   # busy until the first progress tick
        self._progress.setVisible(True)
        self._summary.setText("Scanning…")

        self._worker = _StatsScanWorker(root, self._known_themes)
        self._worker.progress.connect(self._on_progress)
        self._worker.scan_done.connect(self._on_scan_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cancel_scan(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()
            self._cancel_btn.setEnabled(False)
            self._summary.setText("Cancelling…")

    # --- worker slots ---
    @QtCore.pyqtSlot(int, int)
    def _on_progress(self, done: int, total: int) -> None:
        if self._progress.maximum() != total:
            self._progress.setRange(0, max(1, total))
        self._progress.setValue(done)

    @QtCore.pyqtSlot(dict)
    def _on_scan_done(self, result: dict) -> None:
        self._apply_result(result)
        _save_last_result(result)

    def _apply_result(self, result: dict, *, persisted: bool = False) -> None:
        """Store a scan result (fresh or reloaded) and refresh the views."""
        self._last = result
        self._persisted = persisted
        # Populate the per-artist untagged-album cache wholesale from the scan
        # result, which classified every album in the same pass that read the
        # tags.  Availability marks (which don't change tags) are filtered at
        # display time, not here.  An old result predating this data leaves the
        # cache empty and falls back to per-artist lazy computation on expand.
        per_artist = result.get("untagged_albums")
        self._albums_classified = isinstance(per_artist, dict)
        cache: dict[str, list[tuple[str, str]]] = {}
        root = result.get("root") or ""
        if self._albums_classified and root:
            for name, rels in per_artist.items():
                norm = availability._norm(os.path.join(root, name))
                cache[norm] = [
                    (os.path.basename(rel), os.path.join(root, rel))
                    for rel in rels
                ]
        self._artist_untagged_albums = cache

        # Same wholesale load for the missing-tags classification (processed
        # albums lacking Core fetched fields), keyed by normalised artist path →
        # [(basename, abs_path, [missing_tag, …]), …], album-sorted.
        per_missing = result.get("missing_tags")
        self._missing_classified = isinstance(per_missing, dict)
        mcache: dict[str, list[tuple[str, str, list[str]]]] = {}
        if self._missing_classified and root:
            for name, albums in per_missing.items():
                norm = availability._norm(os.path.join(root, name))
                rows = [
                    (os.path.basename(rel), os.path.join(root, rel), list(tags))
                    for rel, tags in albums.items()
                ]
                rows.sort(key=lambda t: t[0].lower())
                mcache[norm] = rows
        self._artist_missing_albums = mcache
        self._recompute()

    def _artist_path(self, name: str) -> str | None:
        """Absolute folder path for an artist *name*, or None if root unknown."""
        root = (self._last or {}).get("root") or ""
        return os.path.join(root, name) if root else None

    def _recompute(self) -> None:
        """Re-partition the scan into tagged/untagged/unavailable and repaint.

        Cheap (no disk I/O): it only re-reads the in-memory availability store,
        so it's safe to call whenever a mark changes or the tab is shown.  An
        artist marked unavailable is carved out of whichever theme-based bucket
        it would otherwise land in, so "untagged" keeps meaning "not tagged
        *yet*" and "unavailable" means "no wiki page to tag from".
        """
        result = self._last
        if not result:
            return
        tagged: list[str] = []
        untagged: list[str] = []
        unavailable: list[str] = []
        for bucket, names in (
            (tagged, result["tagged_artists"]),
            (untagged, result["untagged_artists"]),
        ):
            for name in names:
                path = self._artist_path(name)
                if path is not None and availability.is_artist_unavailable(path):
                    unavailable.append(name)
                else:
                    bucket.append(name)
        unavailable.sort(key=str.lower)
        self._buckets = {
            "tagged": tagged,
            "untagged": untagged,
            "unavailable": unavailable,
        }
        self._pie.setCounts(len(tagged), len(untagged), len(unavailable))

        # Map each artist folder → the basenames of its individually-flagged
        # albums, so a *tagged* artist with some (but not all) albums marked
        # unavailable can show a warning + tooltip listing what's missing.
        # Grouped from the album store by parent folder; no disk I/O.
        missing: dict[str, list[str]] = {}
        for album_path in availability.album_set():
            missing.setdefault(os.path.dirname(album_path), []).append(
                os.path.basename(album_path)
            )
        for names_ in missing.values():
            names_.sort(key=str.lower)
        self._missing_by_artist = missing

        themes_used = len(result["theme_counts"])
        notes = []
        if result.get("cancelled"):
            notes.append("cancelled — partial")
        if self._persisted:
            notes.append("from last scan")
        note = ("  (" + "; ".join(notes) + ")") if notes else ""
        self._summary.setText(
            f"{result['total_artists']:,} artists · {len(tagged):,} tagged · "
            f"{len(untagged):,} untagged · {len(unavailable):,} unavailable · "
            f"{themes_used:,} themes used{note}"
        )

        # Keep an open panel in sync (e.g. an artist just left/joined a bucket).
        if self._panel_mode in self._buckets:
            self._show_artists(self._panel_mode)
        elif self._panel_mode == "themes":
            self._show_themes()
        elif self._panel_mode == "genres":
            self._show_genres()
        elif self._panel_mode == "missing":
            self._show_missing()

    @QtCore.pyqtSlot(str)
    def _on_failed(self, message: str) -> None:
        self._summary.setText(f"Scan failed: {message}")
        QtWidgets.QMessageBox.critical(self, "Statistics", message)

    @QtCore.pyqtSlot()
    def _on_worker_finished(self) -> None:
        self._worker = None
        self._scan_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._root_edit.setEnabled(True)
        if self._progress.maximum() == 0:   # never got a progress tick
            self._progress.setRange(0, 1)
            self._progress.setValue(1)

    # --- detail panel ---
    def _show_artists(self, which: str) -> None:
        if not self._last or which not in self._buckets:
            return
        # Showing artists means the pie is the left-hand view; the buttons
        # offer switching to a popularity chart / the missing-tags view.
        self._left_stack.setCurrentWidget(self._pie)
        self._missing_btn.setText("&Missing tags")
        names = self._buckets[which]
        label = {
            "tagged": "Tagged",
            "untagged": "Untagged",
            "unavailable": "Unavailable",
        }[which]
        self._panel_mode = which
        self._panel_header.setText(f"{label} artists ({len(names):,})")
        root = self._last.get("root") or ""
        sizes = self._last.get("artist_sizes") or {}
        # size is None when no size is known (reloaded pre-size scan), so the
        # display falls back to a bare name and size-sort keeps them together.
        self._raw_rows = [
            (name,
             os.path.join(root, name) if root else None,
             sizes.get(name))
            for name in names
        ]
        self._configure_sort_for_mode(which)
        self._rebuild_rows()
        self._populate_list()

    def _show_themes(self) -> None:
        if not self._last:
            return
        counts = self._last["theme_counts"]
        # Remember which artist bucket (if any) was showing, so "Artist
        # details" can restore the exact pie + list view it replaced.
        if self._panel_mode in self._buckets:
            self._prev_artist_mode = self._panel_mode
        self._panel_mode = "themes"
        # Swap the pie out for the bar chart, always sorted most-popular-first
        # regardless of how the right-hand list is sorted.
        chart_data = sorted(
            counts.items(), key=lambda kv: (-kv[1], kv[0].lower())
        )
        self._chart.setData(chart_data, empty_text="No themes tagged yet.")
        self._left_stack.setCurrentWidget(self._chart_scroll)
        self._missing_btn.setText("&Missing tags")
        self._panel_header.setText(f"Theme popularity ({len(counts):,} used)")
        self._raw_rows = [
            (theme, None, count) for theme, count in counts.items()
        ]
        self._configure_sort_for_mode("themes")
        self._rebuild_rows()
        self._populate_list()

    def _show_genres(self) -> None:
        """Swap in the genre-popularity chart + list (the themes view's twin).

        Counts come from the scan's ``genre_counts``; the release-type labels
        in :data:`_EXCLUDED_GENRES` ("Game", "Indie") are dropped here, at
        display time — every album in the collection is a doujin game
        arrange, so they aren't musical styles and would dwarf the real
        genres.
        """
        if not self._last:
            return
        if self._panel_mode in self._buckets:
            self._prev_artist_mode = self._panel_mode
        self._panel_mode = "genres"
        self._left_stack.setCurrentWidget(self._chart_scroll)
        self._missing_btn.setText("&Missing tags")
        raw = self._last.get("genre_counts")
        if raw is None:
            # Old persisted result predating genre data — prompt a re-scan
            # rather than showing an empty chart as "no genres".
            self._chart.setData(
                [], empty_text="No genre data — run a new Scan to compute it."
            )
            self._panel_header.setText("Genre popularity — re-scan to compute")
            self._raw_rows = []
            self._panel_rows = []
            self._list.clear()
            return
        counts = {
            g: n for g, n in raw.items()
            if g.casefold() not in _EXCLUDED_GENRES
        }
        chart_data = sorted(
            counts.items(), key=lambda kv: (-kv[1], kv[0].lower())
        )
        self._chart.setData(chart_data, empty_text="No genres tagged yet.")
        self._panel_header.setText(f"Genre popularity ({len(counts):,} used)")
        self._raw_rows = [
            (genre, None, count) for genre, count in counts.items()
        ]
        self._configure_sort_for_mode("genres")
        self._rebuild_rows()
        self._populate_list()

    def _exit_charts_view(self) -> None:
        """Return from a popularity bar chart to the pie + artist list view."""
        if self._panel_mode not in ("themes", "genres"):
            return
        if self._prev_artist_mode in self._buckets:
            # _show_artists restores the pie and the prior list.
            self._show_artists(self._prev_artist_mode)
            return
        # No artist slice was open beforehand — fall back to the initial state.
        self._left_stack.setCurrentWidget(self._pie)
        self._panel_mode = ""
        self._raw_rows = []
        self._panel_rows = []
        self._list.clear()
        self._panel_header.setText(
            "Click a pie slice, or “Popularity charts”."
        )

    def _on_missing_toggle(self) -> None:
        """Toggle the right panel between the missing-tags view and artists."""
        if self._panel_mode == "missing":
            self._exit_missing_view()
        else:
            self._show_missing()

    def _show_missing(self) -> None:
        """List tagged artists whose processed albums lack fetched fields.

        Mirrors the tagged-artist list (pie on the left), but each artist
        expands to the *already-tagged* albums under it that are missing one or
        more Core fetched fields, and each album expands to one
        ``missing <tag> tag`` bullet per lacked field.
        """
        if not self._last:
            return
        # Remember the artist bucket showing (if any) so toggling back restores
        # it, exactly like the themes view does.
        if self._panel_mode in self._buckets:
            self._prev_artist_mode = self._panel_mode
        self._panel_mode = "missing"
        # The left pane stays the pie; relabel the toggle for the way back.
        self._left_stack.setCurrentWidget(self._pie)
        self._missing_btn.setText("&Artist details")
        if not self._missing_classified:
            # Old persisted result predating this data — prompt a re-scan rather
            # than walking the disk lazily (the cache lacks the fields anyway).
            self._panel_header.setText("Albums missing tags — re-scan to compute")
            self._raw_rows = []
            self._panel_rows = []
            self._list.clear()
            return
        root = self._last.get("root") or ""
        sizes = self._last.get("artist_sizes") or {}
        names = sorted(
            (name for name in self._buckets.get("tagged", ())
             if root and availability._norm(os.path.join(root, name))
             in self._artist_missing_albums),
            key=str.lower,
        )
        self._panel_header.setText(f"Albums missing tags ({len(names):,} artists)")
        self._raw_rows = [
            (name,
             os.path.join(root, name) if root else None,
             sizes.get(name))
            for name in names
        ]
        self._configure_sort_for_mode("missing")
        self._rebuild_rows()
        self._populate_list()

    def _exit_missing_view(self) -> None:
        """Return from the missing-tags view to the pie + artist list view."""
        if self._prev_artist_mode in self._buckets:
            self._show_artists(self._prev_artist_mode)
            return
        # No artist slice was open beforehand — fall back to the initial state.
        self._left_stack.setCurrentWidget(self._pie)
        self._missing_btn.setText("&Missing tags")
        self._panel_mode = ""
        self._raw_rows = []
        self._panel_rows = []
        self._list.clear()
        self._panel_header.setText(
            "Click a pie slice, or “Popularity charts”."
        )

    # --- sorting ---
    def _configure_sort_for_mode(self, mode: str) -> None:
        """Repopulate the sort combo for the panel *mode* and pick a default.

        Theme/genre sort keys are Count/Name; artist keys are Name/Size.  A
        previously-selected key is preserved across the rebuild when it still
        exists for the new mode; otherwise the per-mode default applies (Count
        descending for themes/genres, Name ascending for artists) — matching
        the behaviour the panels had before sorting was configurable.
        """
        if mode in ("themes", "genres"):
            keys = [("Count", "count"), ("Name", "name")]
            default_key, default_desc = "count", True
        else:
            keys = [("Name", "name"), ("Size", "size")]
            default_key, default_desc = "name", False

        prev = self._sort_combo.currentData()
        self._sort_combo.blockSignals(True)
        self._sort_combo.clear()
        for label, key in keys:
            self._sort_combo.addItem(label, key)
        # Keep the prior key if it's valid for this mode, else use the default.
        want = prev if any(prev == k for _, k in keys) else default_key
        idx = self._sort_combo.findData(want)
        self._sort_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._sort_combo.blockSignals(False)

        # Only reset the direction when switching to a key that wasn't already
        # active (so an explicit asc/desc choice survives re-opening a panel).
        if prev is None or not any(prev == k for _, k in keys):
            self._sort_desc = default_desc
            self._sort_dir_btn.blockSignals(True)
            self._sort_dir_btn.setChecked(self._sort_desc)
            self._sort_dir_btn.blockSignals(False)
            self._update_sort_dir_button()

    def _update_sort_dir_button(self) -> None:
        """Reflect the current direction on the toggle button."""
        if self._sort_desc:
            self._sort_dir_btn.setText("▼")
            self._sort_dir_btn.setToolTip("Sorting descending — click for ascending")
        else:
            self._sort_dir_btn.setText("▲")
            self._sort_dir_btn.setToolTip("Sorting ascending — click for descending")

    def _rebuild_rows(self) -> None:
        """Sort ``_raw_rows`` by the current key/direction → ``_panel_rows``.

        Does not touch the filter, so it is reused both when opening a panel
        and when re-sorting an already-shown one.
        """
        key = self._sort_combo.currentData()
        rows = list(self._raw_rows)
        if key == "name":
            rows.sort(key=lambda r: r[0].lower(), reverse=self._sort_desc)
        else:   # "count" or "size" — numeric, tie-break by name ascending
            rows.sort(key=lambda r: r[0].lower())
            rows.sort(key=lambda r: (r[2] or 0), reverse=self._sort_desc)

        if self._panel_mode in ("themes", "genres"):
            self._panel_rows = [
                (f"{count:,} — {theme}", None, theme)
                for theme, _, count in rows
            ]
        else:
            self._panel_rows = [
                (f"{name} — {_format_size(size)}" if size is not None else name,
                 path, None)
                for name, path, size in rows
            ]

    def _on_sort_changed(self, *_args) -> None:
        """Re-sort in place, preserving the current filter text."""
        if not self._raw_rows:
            return
        self._sort_desc = self._sort_dir_btn.isChecked()
        self._update_sort_dir_button()
        self._rebuild_rows()
        self._apply_filter(self._filter.text())

    def _populate_list(self) -> None:
        self._filter.clear()        # also triggers _apply_filter → full list
        self._apply_filter("")

    @staticmethod
    def _missing_tooltip(missing: list[str]) -> str:
        """Tooltip text naming up to 3 missing albums, then 'and X more'."""
        shown = missing[:3]
        text = ", ".join(shown)
        extra = len(missing) - len(shown)
        if extra > 0:
            text += f" and {extra} more"
        head = "Missing album:" if len(missing) == 1 else "Missing albums:"
        return (
            "Not all albums could be tagged — no wiki page.\n"
            f"{head} {text}"
        )

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        self._list.clear()
        # Only the tagged list flags partial coverage and offers per-artist
        # expansion to its untagged albums: a tagged artist with some (not all)
        # albums marked unavailable gets a warning + tooltip; every tagged
        # artist gets an expansion arrow.
        is_tagged = self._panel_mode == "tagged"
        is_missing = self._panel_mode == "missing"
        for display, path, theme in self._panel_rows:
            if needle and needle not in display.lower():
                continue
            item_text = display
            tooltip = ""
            # Genre rows get their own kind (no folder to open, and no
            # per-theme "Information" details), so the theme context menu
            # never applies to them.
            if path is not None:
                kind = "artist"
            elif self._panel_mode == "genres":
                kind = "genre"
            else:
                kind = "theme"
            if is_tagged and path:
                missing = self._missing_by_artist.get(availability._norm(path))
                if missing:
                    item_text = "⚠ " + display   # ⚠ warning sign
                    tooltip = self._missing_tooltip(missing)
            item = QtWidgets.QTreeWidgetItem([item_text])
            # Names already wrap fully in the panel, so a plain row needs no
            # tooltip; only the warning rows carry the missing-album list.
            if tooltip:
                item.setToolTip(0, tooltip)
            # Stash the folder path so the context menu can open it
            # (None for theme/genre rows — nothing to open).
            item.setData(0, QtCore.Qt.UserRole, path)
            item.setData(0, _ROLE_KIND, kind)
            if theme is not None and kind == "theme":
                item.setData(0, _ROLE_THEME, theme)
            self._list.addTopLevelItem(item)
            if is_tagged and path:
                self._attach_album_branch(item, availability._norm(path))
            elif is_missing and path:
                self._attach_missing_branch(item, availability._norm(path))
        # Size the freshly-added rows to their wrapped height.
        self._list.relayout_rows()

    def _attach_album_branch(self, item, norm_path: str) -> None:
        """Give a tagged-artist *item* its expandable untagged-album branch.

        A lightweight placeholder child is added so the expansion arrow appears
        without building the real rows up front (keeping the collapsed tree
        cheap for a large library); the album rows are materialised on first
        expand — from the in-memory cache when the scan classified the album
        (the normal case, no disk I/O), or by walking that one artist's folder
        as a fallback for an old result that predates the per-album data.  An
        artist that was expanded before a rebuild is re-expanded here.
        """
        placeholder = QtWidgets.QTreeWidgetItem(["…"])
        placeholder.setData(0, _ROLE_KIND, "placeholder")
        placeholder.setFlags(QtCore.Qt.ItemIsEnabled)
        item.addChild(placeholder)
        item.setData(0, _ROLE_LOADED, False)
        if norm_path in self._expanded_artists:
            item.setExpanded(True)

    def _populate_album_children(self, item, raw_albums) -> None:
        """Fill *item* with one child row per still-actionable untagged album.

        *raw_albums* is the cached/computed ``[(basename, album_path), …]`` of
        albums lacking a grouping theme.  Albums
        the user has since marked unavailable are filtered out here — they've
        been handled, so what remains is the "did I forget this one?" set.  When
        nothing is left, a non-selectable italic note row is shown instead.
        """
        item.takeChildren()
        pending = [
            (base, apath) for base, apath in raw_albums
            if not availability.is_album_unavailable(apath)
        ]
        if not pending:
            note = QtWidgets.QTreeWidgetItem(["(no untagged albums)"])
            note.setData(0, _ROLE_KIND, "note")
            note.setFlags(QtCore.Qt.ItemIsEnabled)   # not selectable
            font = note.font(0)
            font.setItalic(True)
            note.setFont(0, font)
            item.addChild(note)
            return
        for base, apath in pending:
            child = QtWidgets.QTreeWidgetItem(["• " + base])
            child.setData(0, QtCore.Qt.UserRole, apath)
            child.setData(0, _ROLE_KIND, "album")
            child.setToolTip(0, apath)
            item.addChild(child)

    def _attach_missing_branch(self, item, norm_path: str) -> None:
        """Give a missing-tags artist *item* its expandable album branch.

        Like :meth:`_attach_album_branch` but for the Missing-tags view: a
        placeholder child gives the arrow, and the album rows (each expandable to
        its ``missing <tag> tag`` bullets) are materialised from memory on first
        expand.  A previously-expanded artist is re-expanded here.
        """
        placeholder = QtWidgets.QTreeWidgetItem(["…"])
        placeholder.setData(0, _ROLE_KIND, "placeholder")
        placeholder.setFlags(QtCore.Qt.ItemIsEnabled)
        item.addChild(placeholder)
        item.setData(0, _ROLE_LOADED, False)
        if norm_path in self._expanded_artists:
            item.setExpanded(True)

    def _populate_missing_albums(self, item, albums) -> None:
        """Fill a missing-tags artist *item* with album rows + field bullets.

        *albums* is ``[(basename, album_path, [missing_tag, …]), …]``.  Each
        album becomes an expandable ``"• " + basename`` row (album-scoped, so the
        existing Open / Send to… context menu applies) whose
        children are one non-selectable ``missing <tag> tag`` bullet per lacked
        field (alphabetical, as stored by the scan).
        """
        item.takeChildren()
        if not albums:
            note = QtWidgets.QTreeWidgetItem(["(no albums missing tags)"])
            note.setData(0, _ROLE_KIND, "note")
            note.setFlags(QtCore.Qt.ItemIsEnabled)   # not selectable
            font = note.font(0)
            font.setItalic(True)
            note.setFont(0, font)
            item.addChild(note)
            return
        for base, apath, tags in albums:
            album_item = QtWidgets.QTreeWidgetItem(["• " + base])
            album_item.setData(0, QtCore.Qt.UserRole, apath)
            album_item.setData(0, _ROLE_KIND, "album")
            album_item.setToolTip(0, apath)
            item.addChild(album_item)
            for tag in tags:
                bullet = QtWidgets.QTreeWidgetItem([f"missing {tag} tag"])
                bullet.setData(0, _ROLE_KIND, "missingtag")
                bullet.setFlags(QtCore.Qt.ItemIsEnabled)   # not selectable
                album_item.addChild(bullet)

    @QtCore.pyqtSlot("QTreeWidgetItem*")
    def _on_item_expanded(self, item) -> None:
        """Materialise an artist's album rows on first expand.

        In the **missing-tags** view this is the per-album missing-field tree
        (built eagerly from memory); in the tagged-artist view it's the
        untagged-album list (from the in-memory cache the scan populated, with a
        one-artist disk-walk fallback for an old result predating that data).
        """
        if item.data(0, _ROLE_KIND) != "artist":
            return
        path = item.data(0, QtCore.Qt.UserRole)
        if not path:
            return
        norm = availability._norm(path)
        self._expanded_artists.add(norm)
        if item.data(0, _ROLE_LOADED):
            return
        item.setData(0, _ROLE_LOADED, True)

        if self._panel_mode == "missing":
            self._populate_missing_albums(
                item, self._artist_missing_albums.get(norm) or []
            )
            self._list.relayout_rows()
            return

        raw = self._artist_untagged_albums.get(norm)
        if raw is None and not self._albums_classified:
            # Old persisted result without per-album data — compute this one
            # artist on demand (and cache it), under a busy cursor.
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                fcache = _load_stats_cache()
                raw = [
                    (os.path.basename(album), album)
                    for album, has_theme in classify_artist_albums(
                        path, self._known_themes, cache=fcache,
                    )
                    if not has_theme
                ]
                _save_stats_cache(fcache)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            raw.sort(key=lambda t: t[0].lower())
            self._artist_untagged_albums[norm] = raw
        # raw is None here only when classified-but-absent → no untagged albums.
        self._populate_album_children(item, raw or [])
        self._list.relayout_rows()

    @QtCore.pyqtSlot("QTreeWidgetItem*")
    def _on_item_collapsed(self, item) -> None:
        if item.data(0, _ROLE_KIND) == "artist":
            path = item.data(0, QtCore.Qt.UserRole)
            if path:
                self._expanded_artists.discard(availability._norm(path))

    # --- artist folder context menu ---
    def _show_list_context_menu(self, pos) -> None:
        """Right-click a row → folder/mark/send actions.

        Album child rows (under an expanded tagged artist) get album-scoped
        actions; artist rows keep the existing artist-scoped ones.
        """
        clicked = self._list.itemAt(pos)
        selected = list(self._list.selectedItems())
        if clicked is not None and clicked not in selected:
            # A plain right-click on an unselected row acts on just that row.
            selected = [clicked]

        def _kind(it):
            return it.data(0, _ROLE_KIND)

        # Theme rows (the Theme popularity list) get their own menu — themes
        # have no folder, so none of the artist/album actions below apply.
        if clicked is not None and _kind(clicked) == "theme":
            theme = clicked.data(0, _ROLE_THEME)
            if theme:
                menu = QtWidgets.QMenu(self)
                menu.addAction(
                    "Information",
                    lambda _t=theme: self._show_theme_info(_t),
                )
                menu.exec_(self._list.viewport().mapToGlobal(pos))
            return

        album_paths = [
            p for it in selected
            if _kind(it) == "album" and (p := it.data(0, QtCore.Qt.UserRole))
        ]
        artist_paths = [
            p for it in selected
            if _kind(it) == "artist" and (p := it.data(0, QtCore.Qt.UserRole))
        ]
        # A pure album-row selection gets album actions; otherwise fall through
        # to the artist menu (mixed selections favour the artist scope).
        if album_paths and not artist_paths:
            self._show_album_context_menu(album_paths, clicked, pos)
            return

        paths = artist_paths
        clicked_path = (
            clicked.data(0, QtCore.Qt.UserRole)
            if clicked is not None and _kind(clicked) == "artist" else None
        )
        if clicked_path and clicked_path not in paths:
            paths = [clicked_path]
        if not paths:   # theme panel, note/placeholder row, or empty area
            return

        menu = QtWidgets.QMenu(self)
        if clicked_path:
            menu.addAction("Open", lambda p=clicked_path: self._open_folder(p))
        # Mark/unmark these artists as unavailable on the wikis.  Marking also
        # flags every album under the artist that has no known theme yet (the
        # ones that genuinely can't be wiki-tagged); albums already carrying a
        # theme are left alone.
        menu.addSeparator()
        any_unmarked = any(
            not availability.is_artist_unavailable(p) for p in paths
        )
        any_marked = any(
            availability.is_artist_unavailable(p) for p in paths
        )
        n = len(paths)
        if any_unmarked:
            menu.addAction(
                "Mark as unavailable" if n == 1
                else f"Mark {n} artists as unavailable",
                lambda _p=list(paths): self._set_artists_unavailable(_p, True),
            )
        if any_marked:
            menu.addAction(
                "Unmark as unavailable" if n == 1
                else f"Unmark {n} artists as unavailable",
                lambda _p=list(paths): self._set_artists_unavailable(_p, False),
            )

        if self._send_targets:
            send_menu = menu.addMenu("Send to…")
            for label, tab in self._send_targets:
                send_menu.addAction(
                    label,
                    lambda _p=list(paths), _t=tab: self._send_to_tab(_t, _p),
                )
        menu.exec_(self._list.viewport().mapToGlobal(pos))

    def _show_theme_info(self, theme: str) -> None:
        """Open the per-theme Information window from its cached details.

        The details are computed during the scan (:func:`_build_theme_details`)
        and persisted with the result, so this opens instantly with no disk
        I/O.  A persisted result from before the feature has no
        ``theme_details`` — prompt a re-scan instead, mirroring how the
        Missing-tags view handles its missing classification.
        """
        details = (self._last or {}).get("theme_details")
        info = (details or {}).get(theme)
        if info is None:
            QtWidgets.QMessageBox.information(
                self, "Theme information",
                "No cached details for this theme — run a new Scan to "
                "compute them.",
            )
            return
        _ThemeInfoDialog(theme, info, self).exec_()

    def _set_artists_unavailable(
        self, artist_paths: list[str], flag: bool
    ) -> None:
        """Mark/unmark artists (and their albums) as unavailable on the wikis.

        On *mark*, every album under the artist that doesn't already carry a
        known theme is flagged too, so the Wiki Tagger tab shows them as
        unavailable.  Albums that *do* have a theme are left untouched.  On
        *unmark*, the artist and all its albums are cleared.

        Album classification reuses the Statistics scan cache, so a re-mark
        doesn't re-open every file.  A busy cursor covers the (usually brief)
        disk walk.
        """
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            cache = _load_stats_cache()
            albums_to_set: list[str] = []
            for artist in artist_paths:
                for album, has_theme in classify_artist_albums(
                    artist, self._known_themes, cache=cache
                ):
                    # Flagging: only albums without a theme.  Clearing: all.
                    if not flag or not has_theme:
                        albums_to_set.append(album)
            _save_stats_cache(cache)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        availability.set_artists(artist_paths, flag)
        availability.set_albums(albums_to_set, flag)
        self._recompute()

    def _show_album_context_menu(self, album_paths, clicked, pos) -> None:
        """Right-click menu for album child rows under an expanded artist."""
        menu = QtWidgets.QMenu(self)
        clicked_path = (
            clicked.data(0, QtCore.Qt.UserRole) if clicked is not None else None
        )
        if clicked_path:
            menu.addAction("Open", lambda p=clicked_path: self._open_folder(p))
        n = len(album_paths)
        # Mark/unmark just these albums (album-scoped — does not touch the
        # artist mark).  Once marked, they drop out of the artist's expander.
        menu.addSeparator()
        any_unmarked = any(
            not availability.is_album_unavailable(p) for p in album_paths
        )
        any_marked = any(
            availability.is_album_unavailable(p) for p in album_paths
        )
        if any_unmarked:
            menu.addAction(
                "Mark album as unavailable" if n == 1
                else f"Mark {n} albums as unavailable",
                lambda _p=list(album_paths): self._set_albums_unavailable(_p, True),
            )
        if any_marked:
            menu.addAction(
                "Unmark album as unavailable" if n == 1
                else f"Unmark {n} albums as unavailable",
                lambda _p=list(album_paths): self._set_albums_unavailable(_p, False),
            )

        if self._send_targets:
            send_menu = menu.addMenu("Send to…")
            for label, tab in self._send_targets:
                send_menu.addAction(
                    label,
                    lambda _p=list(album_paths), _t=tab:
                        self._send_albums_to_tab(_t, _p),
                )
        menu.exec_(self._list.viewport().mapToGlobal(pos))

    def _set_albums_unavailable(self, album_paths, flag: bool) -> None:
        """Mark/unmark individual albums as unavailable, then refresh."""
        availability.set_albums(album_paths, flag)
        self._recompute()

    def _send_albums_to_tab(self, tab, album_paths) -> None:
        """Add album folders directly to *tab* and switch to it."""
        for album in album_paths:
            tab.add_directory(album)
        if self._tab_widget is not None:
            self._tab_widget.setCurrentWidget(tab)

    def _send_to_tab(self, tab, artist_paths: list[str]) -> None:
        """Add the artists' album folders to *tab* and switch to it.

        Each artist folder is a container; expand it to its album dirs (the
        same one-level expansion dropping an ``[Artist]`` folder onto a tab
        performs) so the target tab gets album rows, not the bare container.
        """
        for artist in artist_paths:
            for album in _expand_to_album_dirs(
                    artist, max_depth=preferences.scan_depth()):
                tab.add_directory(album)
        if self._tab_widget is not None:
            self._tab_widget.setCurrentWidget(tab)

    def _open_folder(self, path: str) -> None:
        """Open *path* in the system default file manager."""
        if not os.path.isdir(path):
            QtWidgets.QMessageBox.warning(
                self, "Statistics",
                f"Folder not found:\n{path}",
            )
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(path))
