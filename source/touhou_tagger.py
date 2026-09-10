#!/usr/bin/env python3
"""
touhou_tagger.py — Tag Touhou remix albums with original theme names
using the Touhou Wiki as a database, with THBWiki (thwiki.cc) as a
fallback source.

Dependencies (see requirements*.txt / docs/DEPENDENCIES.md for pinned versions
and the full optional-group breakdown):
  Core (required):  beautifulsoup4, mutagen, curl_cffi
  GUI (optional):   PyQt5
  English wiki (optional): playwright  (then: playwright install chromium)
THBWiki is the mandatory source, so curl_cffi is required even for CLI runs;
Playwright/PyQt5 are optional and their absence degrades gracefully.

Usage:
# Launch the GUI (drag & drop album folders, edit slugs, tag all):
python source/touhou_tagger.py
# CLI mode — single album:
python source/touhou_tagger.py "Wishes_Hidden_In_The_Foreground_Noises" "path/to/Wishes" --dry-run
# CLI mode — multiple albums in one invocation:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" "Unforgettable_Duet" "path/to/Duet" --dry-run
# Force THBWiki only (skip English wiki):
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --thwiki-only
# Specify a different mapping file:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --mapping "path/to/touhou_theme_mapping.json"
"""
import argparse
import datetime
import difflib
import logging
import os
import platform
import re
import sys
import threading
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

# --- Sub-module imports ---
from app_version import __version__
from touhou_wiki import (
    fetch_album_html,
    parse_tracklist,
    parse_album_staff,
    is_available as english_wiki_available,
)
from thwiki import (
    fetch_thwiki_tracks,
    _fetch_thwiki_page_html,
    _parse_thwiki_html_titles,
    parse_thwiki_album_info,
    translate_genre,
    genre_is_cjk,
    parse_thwiki_staff_names,
    parse_thwiki_album_staff,
    _parse_thwiki_html_credits,
    _parse_thwiki_html_tracklist,
    validate_thwiki_cookie,
    ThwikiCookieError,
)
from tag_io import (
    set_grouping,
    clear_grouping,
    _get_existing_tag,
    _set_tag,
    set_genres,
    read_genres,
    _is_latin_script,
    _romanize_credit_names,
    read_grouping,
    read_all_tags,
)
import touhoudb
import availability
import tag_locks
from theme_mapping import (
    load_theme_mapping,
    translate_titles,
    _inherit_instrumental_titles,
    normalize,
)
from file_scan import scan_music_files
from tag_selection import (
    STAFF_TAGS as _CREDIT_TAGS,
    WIKI_TAGS,
    normalize_selected_tags,
)

# Optional: companion romaniser module.  When present, this script can
# auto-fill the `titlesort` tag with a Hepburn romanisation of any
# Japanese title it finds, in the same pass that writes `grouping`.
# When absent, the wiki-tagging flow works as before and the
# Romanization GUI tab simply won't appear.
try:
    import japanese_romanizer  # type: ignore
    ROMANIZER_AVAILABLE = japanese_romanizer.is_ready()
    ROMANIZER_IMPORT_OK = True
except Exception as _romaniser_exc:
    japanese_romanizer = None  # type: ignore
    ROMANIZER_AVAILABLE = False
    ROMANIZER_IMPORT_OK = False

# True when the romaniser is otherwise ready but pykakasi is not
# installed.  Surfaced as a GUI status-bar hint so the user knows they
# can opt in for better rare-kanji coverage.
PYKAKASI_HINT_NEEDED = (
    ROMANIZER_IMPORT_OK
    and ROMANIZER_AVAILABLE
    and not getattr(japanese_romanizer, "PYKAKASI_AVAILABLE", True)
)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# GUI sessions write a fresh timestamped log file in the platform-appropriate
# per-user log directory (see _setup_gui_logging).  The primary reason this
# exists is so that GUI crashes — which otherwise vanish when the process dies
# — leave a full traceback on disk that can be shared after the fact.
# The CLI path doesn't touch this; CLI output already goes to the
# terminal, where the user can redirect it if they want a copy.
LOGGER_NAME = "touhou_tagger"
# How many old log files to keep when a new GUI session starts.
# Anything past this is silently deleted from the user log directory.
_MAX_LOG_FILES = 20
# Module-level guard so _setup_gui_logging() is idempotent — calling
# it a second time in the same process is a no-op and returns the
# already-configured logger.
_GUI_LOGGING_INITIALISED = False


def _setup_gui_logging() -> tuple[logging.Logger, str | None]:
    """Configure a file logger for the GUI session and install crash hooks.

    Opens a fresh ``touhou_tagger_<YYYYMMDD_HHMMSS>.log`` in the
    platform-appropriate per-user log directory. Writes an environment header
    (Python version, platform, dependency versions, romaniser status) so a
    shared log file is self-describing.

    Installs both ``sys.excepthook`` and ``threading.excepthook`` so
    any unhandled exception — in the GUI thread or a worker QThread —
    is recorded with a full traceback before the process dies.  Both
    hooks chain through to their previous values so stderr output is
    preserved.

    Returns ``(logger, log_path)``.  ``log_path`` is ``None`` only
    when the log directory couldn't be created; in that case the returned
    logger has no file handler attached and crash-logging silently degrades to
    whatever the OS does with stderr.
    """
    global _GUI_LOGGING_INITIALISED
    logger = logging.getLogger(LOGGER_NAME)
    if _GUI_LOGGING_INITIALISED:
        # Already set up — return the existing logger and the file
        # path of its FileHandler (if any).
        existing_path = next(
            (
                h.baseFilename for h in logger.handlers
                if isinstance(h, logging.FileHandler)
            ),
            None,
        )
        return logger, existing_path

    logs_dir = availability.app_log_dir()
    log_path: str | None = None
    try:
        availability.ensure_private_directory(logs_dir)
    except OSError as e:
        # If we can't even create the logs directory, carry on without
        # file logging — better than refusing to start the GUI.  The
        # excepthook below still installs and will at least chain to
        # the default stderr printer.
        print(
            f"Warning: couldn't create logs dir at {logs_dir!r}: {e}.  "
            f"Crashes will not be logged to disk.",
            file=sys.stderr,
        )

    logger.setLevel(logging.DEBUG)
    # Drop any handlers from a prior _setup call (shouldn't happen
    # given the idempotency guard, but cheap insurance).
    logger.handlers.clear()
    # Don't double-log to the root logger if some library configures one.
    logger.propagate = False

    if os.path.isdir(logs_dir):
        # Rotate: keep only the N most recent log files so this folder
        # doesn't grow unbounded.  Errors here are non-fatal — the
        # worst case is one stale log doesn't get cleaned up.
        try:
            existing = sorted(
                (
                    os.path.join(logs_dir, f)
                    for f in os.listdir(logs_dir)
                    if f.startswith("touhou_tagger_") and f.endswith(".log")
                ),
                key=os.path.getmtime,
                reverse=True,
            )
            # Keep _MAX_LOG_FILES - 1 because we're about to add one more.
            for stale in existing[max(_MAX_LOG_FILES - 1, 0):]:
                try:
                    os.remove(stale)
                except OSError:
                    pass
        except OSError:
            pass

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(
            logs_dir, f"touhou_tagger_{timestamp}.log"
        )
        try:
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            logger.addHandler(fh)
            availability.restrict_private_file(log_path)
        except OSError as e:
            print(
                f"Warning: couldn't open log file at {log_path!r}: {e}.  "
                f"Crashes will not be logged to disk.",
                file=sys.stderr,
            )
            log_path = None

    # --- Header: environment snapshot for the bug report ---
    logger.info("=" * 60)
    logger.info("Touhou Tagger GUI session started")
    logger.info("=" * 60)
    if log_path:
        logger.info("Log file: %s", log_path)
    logger.info("Version:  %s", __version__)
    logger.info("Python:   %s", sys.version.replace("\n", " "))
    logger.info("Platform: %s", platform.platform())
    logger.info("Script:   %s", os.path.abspath(__file__))
    logger.info("CWD:      %s", os.getcwd())

    # Dependency versions — wrapped individually so a single broken
    # import doesn't blank out the rest of the snapshot.
    for module_name, version_attr in (
        ("PyQt5.QtCore", "PYQT_VERSION_STR"),
        ("playwright",   "__version__"),
        ("bs4",          "__version__"),
        ("mutagen",      "version_string"),
    ):
        try:
            mod = __import__(module_name, fromlist=[version_attr])
            ver = getattr(mod, version_attr, "?")
            logger.info("  %-14s %s", module_name + ":", ver)
        except Exception as e:
            logger.info(
                "  %-14s (import failed: %s)", module_name + ":", e,
            )

    logger.info("Romaniser import OK: %s", ROMANIZER_IMPORT_OK)
    logger.info("Romaniser ready:     %s", ROMANIZER_AVAILABLE)
    if ROMANIZER_AVAILABLE:
        logger.info(
            "pykakasi available:  %s",
            getattr(japanese_romanizer, "PYKAKASI_AVAILABLE", "?"),
        )
    logger.info("-" * 60)

    # --- Install crash hooks ---
    # sys.excepthook fires for uncaught exceptions in the main thread.
    # We chain through to whatever was installed previously (typically
    # sys.__excepthook__, the stderr printer) so console output is
    # preserved.
    previous_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical(
                "Uncaught exception in main thread:",
                exc_info=(exc_type, exc_value, exc_tb),
            )
        previous_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # threading.excepthook (3.8+) fires for uncaught exceptions in
    # Python threads.  QThread runs Python code, so this catches
    # anything that escapes the per-worker try/except wrappers below.
    if hasattr(threading, "excepthook"):
        previous_threading_excepthook = threading.excepthook

        def _threading_excepthook(args):
            if not issubclass(args.exc_type, KeyboardInterrupt):
                thread_name = (
                    args.thread.name if args.thread is not None else "?"
                )
                logger.critical(
                    "Uncaught exception in thread %r:", thread_name,
                    exc_info=(
                        args.exc_type,
                        args.exc_value,
                        args.exc_traceback,
                    ),
                )
            previous_threading_excepthook(args)

        threading.excepthook = _threading_excepthook

    _GUI_LOGGING_INITIALISED = True
    return logger, log_path


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------
def match_tracks(
    wiki_tracks: list[dict],
    local_files: list[dict],
) -> list[tuple]:
    """
    Pair each local file with the best matching wiki track.

    **Title is the primary key, track number the tiebreaker.**  The local
    title is taken from the *filename* first (decorations like ``(01)`` /
    ``[circle]`` stripped — see :func:`_filename_title`) and the ``title`` tag
    second; matching is case-insensitive (``normalize`` lowercases).  Each wiki
    track is claimed by at most one file.  Three passes, most-confident first:

    1. **Title + number agree** — the file's title matches a wiki track that
       also sits at its ``(disc, )number``.
    2. **Title matches (any position)** — handles albums ordered differently on
       the source than on disk; when a title is non-unique (e.g. a vocal and an
       instrumental share it), the closest track number breaks the tie.
    3. **Positional fallback** — track number alone (``(disc, number)`` for
       multi-disc, else number), for files whose title matched nothing (typos,
       differently-romanised titles, or an instrumental whose wiki title gained
       a suffix the filename lacks — which falls through here to its own slot).

    Returns list of (local_file_dict, wiki_track_dict | None), one per local
    file in input order.
    """
    multi_disc = len({t["disc"] for t in wiki_tracks}) > 1

    wiki_by_disc_number = {(t["disc"], t["number"]): t for t in wiki_tracks}
    wiki_by_number: dict = {}
    for t in wiki_tracks:
        wiki_by_number.setdefault(t["number"], t)   # first wins on dup numbers
    wiki_by_title: dict[str, list] = {}
    for t in wiki_tracks:
        nt = normalize(t.get("title") or "")
        if nt:
            wiki_by_title.setdefault(nt, []).append(t)

    def _local_keys(f: dict) -> list[str]:
        # Filename-derived title first, then the `title` tag (de-duplicated).
        keys: list[str] = []
        for s in (_filename_title(f), f.get("title")):
            ns = normalize(s or "")
            if ns and ns not in keys:
                keys.append(ns)
        return keys

    claimed: set[int] = set()
    result: dict[int, dict] = {}

    def _unclaimed(nt: str) -> list[dict]:
        return [t for t in wiki_by_title.get(nt, []) if id(t) not in claimed]

    # Pass 1 — title matches AND the track number agrees (most confident).
    for i, f in enumerate(local_files):
        for nt in _local_keys(f):
            chosen = None
            for cand in _unclaimed(nt):
                if (f["number"] is not None
                        and cand["number"] == f["number"]
                        and (not multi_disc or cand["disc"] == f["disc"])):
                    chosen = cand
                    break
            if chosen is not None:
                result[i] = chosen
                claimed.add(id(chosen))
                break

    # Pass 2 — title matches at any position; closest number breaks a tie.
    for i, f in enumerate(local_files):
        if i in result:
            continue
        for nt in _local_keys(f):
            avail = _unclaimed(nt)
            if not avail:
                continue
            if len(avail) == 1:
                chosen = avail[0]
            else:
                chosen = min(avail, key=lambda c: abs(
                    (c["number"] or 0) - (f["number"] or 0)))
            result[i] = chosen
            claimed.add(id(chosen))
            break

    # Pass 3 — positional fallback for anything still unmatched.
    for i, f in enumerate(local_files):
        if i in result:
            continue
        cand = None
        if f["number"] is not None:
            if multi_disc:
                cand = wiki_by_disc_number.get((f["disc"], f["number"]))
            if cand is None or id(cand) in claimed:
                cand = wiki_by_number.get(f["number"])
        if cand is not None and id(cand) not in claimed:
            result[i] = cand
            claimed.add(id(cand))

    return [(f, result.get(i)) for i, f in enumerate(local_files)]


# ---------------------------------------------------------------------------
# Track-discrepancy comparison (titles: local vs wiki vs TouhouDB)
# ---------------------------------------------------------------------------
# A local file is counted as "lining up" with the fetched data when its title
# is at least this similar (0..1, difflib ratio on normalized strings) to the
# wiki track it matched by (disc, number).  Below it, the pair is treated as a
# real disagreement and does not count toward ``match_rate``.
_MATCH_RATIO = 0.6
# An album is flagged "severe" (wholesale wrong) when fewer than this fraction
# of local files line up with a fetched track …
_SEVERE_MATCH_RATE = 0.5
# … or when the local and fetched track counts differ by more than this
# fraction of the larger of the two.
_SEVERE_COUNT_DELTA = 0.5

# Strip a leading track-number prefix (and a disc-track form like "1-03")
# plus common separators from a filename stem, to recover a display title
# when a file has no `title` tag.
# Leading track-number prefix (and the disc-track form like "1-03").  The
# number must be followed by a separator — punctuation or whitespace — so a
# title that merely *starts* with digits ("07th Expansion") is left intact.
_FILENAME_TRACKNO_RE = re.compile(
    r"^\s*\d{1,3}(?:[-.]\d{1,3})?(?:\s*[-._)\].]+\s*|\s+)")
# A leading bracketed / parenthesised group — a "(01)" track number or a
# "[circle]" credit in the common "(01) [circle] title" doujin convention.
_FILENAME_BRACKET_RE = re.compile(
    r"^\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*[-–—._]*\s*")


def _filename_title(local_file: dict) -> str:
    """Recover a song title from a filename by stripping leading decorations.

    Iteratively removes leading track-number tokens (``04.``, ``02 -``, the
    disc-track ``1-03`` form) and bracketed/parenthesised groups (a ``(01)``
    track number, a ``[circle]`` credit), e.g.::

        (01) [ri meちゃん] ポイしないで下さい.flac  →  ポイしないで下さい
        04. Insert Song Here.flac                →  Insert Song Here

    Stops before stripping everything away (a title that is itself fully
    bracketed is returned unchanged).  Returns ``""`` when there is no filename.
    """
    stem = os.path.splitext(local_file.get("filename", "") or "")[0].strip()
    while stem:
        stripped = _FILENAME_BRACKET_RE.sub("", stem, count=1)
        if stripped == stem:                       # no leading bracket group
            stripped = _FILENAME_TRACKNO_RE.sub("", stem, count=1)
        stripped = stripped.strip()
        if stripped == stem or not stripped:       # nothing left to strip
            break
        stem = stripped
    return stem


def _local_display_title(local_file: dict) -> str:
    """Best available local title for *display*: the ``title`` tag, else the
    filename with its extension and leading track-number/bracket decorations
    stripped (see :func:`_filename_title`)."""
    title = (local_file.get("title") or "").strip()
    if title:
        return title
    return _filename_title(local_file) or os.path.splitext(
        local_file.get("filename", ""))[0].strip()


def _merge_genres(existing: list[str], wiki: list[str]) -> list[str]:
    """Union a file's existing genres with the wiki's, for the genre write.

    The ``genre`` tag is **merged, not replaced**: an album keeps its
    hand-added / pre-existing genres (e.g. ``Indie``, or the doujin-file
    ``Touhou``) *and* gains the wiki's style tags, for a fuller picture of
    the album's styles.

    Both sides are run through :func:`translate_genre`, so a pre-existing
    CJK genre with a known mapping (e.g. ``独立音乐``) lands as its English
    form (``Indie``) and dedups against a wiki ``Indie`` instead of sitting
    beside it as a near-duplicate; wiki genres are already English, so the
    pass is a no-op for them, and any existing genre that's plain English or
    an unmapped term is preserved verbatim.  De-duplication is
    case-insensitive; existing genres keep their order first, then any wiki
    genres not already present are appended.
    """
    out: list[str] = []
    seen: set[str] = set()
    for g in list(existing) + list(wiki):
        t = translate_genre(g)
        key = t.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def _title_sim(a: str, b: str) -> float:
    """Similarity of two titles in 0..1 (1.0 == equal after normalize)."""
    na, nb = normalize(a or ""), normalize(b or "")
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return difflib.SequenceMatcher(None, na, nb).ratio()


def compare_tracklists(
    wiki_tracks: list[dict],
    local_files: list[dict],
    tdb_titles: dict[tuple[int, int], str] | None = None,
) -> dict:
    """Compare local titles against the fetched wiki (and optional TouhouDB)
    titles to surface typos, wrong track numbers, and missing/extra tracks.

    Pure and Qt-free (headlessly testable).  Returns a dict:

      ``discrepancies`` — list of ``{disc, number, kind, local, wiki, tdb,
                          path, filename}`` where ``kind`` is one of
                          ``title_mismatch``, ``wrong_track_number``,
                          ``missing_local``, ``no_fetch_match``.  ``path`` /
                          ``filename`` are empty for ``missing_local`` (no
                          local file); otherwise they point at the local file,
                          letting the GUI write a corrected ``title`` to it.
      ``severe``        — True when the album looks wholesale wrong.
      ``match_rate``    — fraction of local files that line up with a fetched
                          track by title.
      ``local_count`` / ``fetched_count`` — track counts on each side.

    Matching reuses :func:`match_tracks` for the (disc, number) alignment, so
    it agrees with what the tagger would actually write.
    """
    tdb_titles = tdb_titles or {}
    local_count = len(local_files)
    fetched_count = len(wiki_tracks)
    discrepancies: list[dict] = []

    if not local_files:
        return {
            "discrepancies": [], "severe": False, "match_rate": 1.0,
            "local_count": 0, "fetched_count": fetched_count,
        }

    # Normalized wiki-title index → the (disc, number)s carrying that title,
    # used to recognise a title that exists but at the wrong track number.
    wiki_title_index: dict[str, set[tuple[int, int]]] = {}
    for t in wiki_tracks:
        wt = (t.get("title") or "").strip()
        if wt:
            wiki_title_index.setdefault(normalize(wt), set()).add(
                (t["disc"], t["number"]))

    pairs = match_tracks(wiki_tracks, local_files)
    matched_wiki_keys: set[tuple[int, int]] = set()
    aligned = 0

    for local_file, wiki_track in pairs:
        local_title = _local_display_title(local_file)
        # Both forms the matcher considered: filename-derived and the `title`
        # tag.  A file matched by its filename must not read as a mismatch just
        # because its tag is a different romanisation of the same song, so the
        # comparison takes the best agreement across both forms.
        local_forms = [s for s in (_filename_title(local_file),
                                   (local_file.get("title") or "").strip())
                       if s] or [local_title]
        if wiki_track is not None:
            key = (wiki_track["disc"], wiki_track["number"])
            matched_wiki_keys.add(key)
            wiki_title = (wiki_track.get("title") or "").strip()
            tdb_title = tdb_titles.get(key, "")
            sim = max((_title_sim(s, wiki_title) for s in local_forms),
                      default=0.0)
            if sim >= _MATCH_RATIO:
                aligned += 1
            # Flag a per-track discrepancy when neither local form equals the
            # wiki title, or when a present TouhouDB title disagrees.
            wiki_norm = normalize(wiki_title)
            wiki_disagrees = all(normalize(s) != wiki_norm for s in local_forms)
            tdb_disagrees = bool(tdb_title) and max(
                (_title_sim(s, tdb_title) for s in local_forms),
                default=0.0) < _MATCH_RATIO
            if wiki_disagrees or tdb_disagrees:
                if sim < _MATCH_RATIO and any(
                        normalize(s) in wiki_title_index for s in local_forms):
                    kind = "wrong_track_number"
                else:
                    kind = "title_mismatch"
                discrepancies.append({
                    "disc": local_file["disc"], "number": local_file["number"],
                    "kind": kind, "local": local_title,
                    "wiki": wiki_title, "tdb": tdb_title,
                    "path": local_file["path"],
                    "filename": local_file["filename"],
                })
        else:
            # No fetched track aligned to this local file.
            elsewhere = any(normalize(s) in wiki_title_index
                            for s in local_forms)
            discrepancies.append({
                "disc": local_file["disc"], "number": local_file["number"],
                "kind": "wrong_track_number" if elsewhere else "no_fetch_match",
                "local": local_title, "wiki": "", "tdb": "",
                "path": local_file["path"],
                "filename": local_file["filename"],
            })

    # Fetched tracks that no local file aligned to.
    for t in wiki_tracks:
        key = (t["disc"], t["number"])
        if key not in matched_wiki_keys:
            discrepancies.append({
                "disc": t["disc"], "number": t["number"],
                "kind": "missing_local",
                "local": "", "wiki": (t.get("title") or "").strip(),
                "tdb": tdb_titles.get(key, ""),
                "path": "", "filename": "",
            })

    match_rate = aligned / local_count if local_count else 1.0
    larger = max(local_count, fetched_count, 1)
    count_delta = abs(local_count - fetched_count) / larger
    severe = (match_rate < _SEVERE_MATCH_RATE
              or count_delta > _SEVERE_COUNT_DELTA)

    discrepancies.sort(key=lambda d: (d["disc"], d["number"] or 0))
    return {
        "discrepancies": discrepancies, "severe": severe,
        "match_rate": match_rate,
        "local_count": local_count, "fetched_count": fetched_count,
    }


def _build_mismatch_context(
    plan: "AlbumPlan",
    local_files: list[dict],
    pairs: list[tuple],
    report: dict,
) -> dict:
    """Build the plain-dict context the GUI confirmation dialog renders.

    Produces a Local / TouhouDB / Wiki value view of every tag — album-level
    rows plus one node per local track — with a precomputed ``diff`` flag per
    row (True when the present values disagree, via :func:`normalize`) so the
    GUI tints discrepancies without re-implementing the comparison.  The
    TouhouDB column is left empty for fields TouhouDB doesn't supply (e.g.
    ``grouping``); the GUI hides it entirely when ``use_touhoudb`` is off.
    """
    info = plan.album_info or {}
    tdb_titles = plan.tdb_track_titles or {}
    tdb_info = plan.tdb_album_info or {}

    def _row(tag: str, local, tdb, wiki) -> dict:
        present = [v for v in (local or "", tdb or "", wiki or "") if v]
        diff = len({normalize(v) for v in present}) > 1
        return {"tag": tag, "local": local or "", "tdb": tdb or "",
                "wiki": wiki or "", "diff": diff}

    # --- Album-level rows (read one representative file for local values) ---
    rep_tags = read_all_tags(local_files[0]["path"]) if local_files else {}
    wiki_date = info.get("date") or ""
    wiki_aa = " & ".join(info.get("album_artists") or [])
    wiki_cat = "; ".join(info.get("catalog_numbers") or [])
    tdb_date = tdb_info.get("date", "")
    album_rows = [
        _row("album", rep_tags.get("album"),
             tdb_info.get("album", ""), info.get("album") or ""),
        _row("albumartist", rep_tags.get("albumartist"),
             tdb_info.get("circle", ""), wiki_aa),
        _row("catalognumber", rep_tags.get("catalognumber"),
             tdb_info.get("catalog", ""), wiki_cat),
        _row("date", rep_tags.get("date"), tdb_date, wiki_date),
        _row("year", rep_tags.get("year"), tdb_date[:4], wiki_date[:4]),
    ]

    # --- Per-track rows ---
    multi = len({f["disc"] for f in local_files}) > 1
    tracks: list[dict] = []
    for local_file, wiki_track in pairs:
        local_tags = read_all_tags(local_file["path"])
        local_title = _local_display_title(local_file)
        disc, number = local_file["disc"], local_file["number"]
        if wiki_track is not None:
            key = (wiki_track["disc"], wiki_track["number"])
            wiki_title = (wiki_track.get("title") or "").strip()
            grouping = "; ".join(wiki_track.get("original_titles") or [])
            arr = "; ".join(wiki_track.get("arrangers") or [])
            voc = "; ".join(wiki_track.get("vocalists") or [])
            lyr = "; ".join(wiki_track.get("lyricists") or [])
            artist_wiki = "; ".join(
                (wiki_track.get("arrangers_jp") or [])
                + (wiki_track.get("vocalists_jp") or []))
            tdb_title = tdb_titles.get(key, "")
        else:
            wiki_title = grouping = arr = voc = lyr = artist_wiki = ""
            tdb_title = tdb_titles.get((disc, number), "")
        rows = [
            _row("title", local_tags.get("title") or local_title,
                 tdb_title, wiki_title),
            _row("grouping", local_tags.get("grouping"), "", grouping),
            _row("artist", local_tags.get("artist"), "", artist_wiki),
            _row("arranger", local_tags.get("arranger"), "", arr),
            _row("vocalist", local_tags.get("vocalist"), "", voc),
            _row("lyricist", local_tags.get("lyricist"), "", lyr),
            _row("titlesort", local_tags.get("titlesort"), "", ""),
        ]
        if multi and number:
            label_no = f"{disc}-{number:02d}"
        elif number:
            label_no = f"{number:02d}"
        else:
            label_no = "??"
        tracks.append({
            "label": f"{label_no}  {local_title}".strip(),
            "disc": disc, "number": number, "rows": rows,
        })

    missing = [d for d in report["discrepancies"]
               if d["kind"] == "missing_local"]

    return {
        "music_dir": plan.music_dir,
        "album": os.path.basename(plan.music_dir.rstrip("/\\"))
                 or plan.wiki_album,
        "use_touhoudb": plan.use_touhoudb,
        "match_rate": report["match_rate"],
        "local_count": report["local_count"],
        "fetched_count": report["fetched_count"],
        "album_rows": album_rows,
        "tracks": tracks,
        "missing": missing,
    }


# ---------------------------------------------------------------------------
# Single-album processing (used by both CLI and GUI)
# ---------------------------------------------------------------------------
_METADATA_TAGS = frozenset({
    "album", "albumartist", "albumartistsort", "catalognumber", "date",
    "year", "genre",
})
_ARTIST_TAGS = frozenset({"artist", "artistsort"})
# Every output a TouhouDB lookup can change.  Besides the artist pair it also
# supplies the official romanizations behind `albumartistsort` and the credit
# tags (both resolve through the TouhouDB client when one exists), so a run
# that selects only those must still build the client.
_TOUHOUDB_TAGS = _ARTIST_TAGS | _CREDIT_TAGS | frozenset({"albumartistsort"})


def _effective_selected_tags(selected_tags) -> tuple[str, ...]:
    """Return a canonical selection, preserving all-tags legacy callers."""
    if selected_tags is None:
        return WIKI_TAGS
    return normalize_selected_tags(selected_tags)


def _tag_selection_fetch_options(
    selected_tags,
    *,
    fetch_metadata: bool,
    fetch_credits: bool,
    use_touhoudb: bool,
) -> dict[str, bool]:
    """Derive the optional source enrichment required by selected outputs.

    Core track lookup and HTML title cross-checking remain unconditional; this
    only avoids album metadata, credit, and staff-name work when no selected
    output could consume it.
    """
    selected = frozenset(_effective_selected_tags(selected_tags))
    wants_metadata = bool(selected & _METADATA_TAGS)
    wants_credits = bool(selected & _CREDIT_TAGS)
    wants_artists = bool(selected & _ARTIST_TAGS) and use_touhoudb
    metadata = bool(fetch_metadata and wants_metadata)
    credits = bool(fetch_credits and (wants_credits or wants_artists))
    staff_names = bool(
        (metadata and "albumartistsort" in selected)
        or (credits and wants_credits)
        or (credits and use_touhoudb and "artistsort" in selected)
    )
    return {
        "fetch_metadata": metadata,
        "fetch_credits": credits,
        "fetch_staff_names": staff_names,
    }


def _empty_result(
    album: str,
    *,
    music_dir: str = "",
    source: str | None = None,
    error: str | None = None,
) -> dict:
    """Build a process_album() result dict with all counters zeroed."""
    return {
        "album":       album,
        "music_dir":   music_dir,
        "source":      source,
        "tagged":      0,
        "skipped":     0,
        "cleared":     0,
        "errors":      0,
        "romanized":   0,
        "overwritten": 0,
        "rm_skipped":  0,
        "rm_no_title": 0,
        "rm_errors":   0,
        "meta_wrote":  0,
        "meta_skipped": 0,
        "cred_wrote":  0,
        "cred_skipped": 0,
        "artist_wrote":   0,
        "artist_skipped": 0,
        "locked_skipped": 0,
        "missing_members": [],
        "date_mismatch":   None,
        "catalog_mismatch": None,
        "tag_changes": [],
        "title_discrepancies": [],
        "severe_mismatch": False,
        "mismatch_skipped": False,
        "cancel_batch": False,
        "error":       error,
    }


def _slug_case_variants(slug: str) -> list[str]:
    """Alternative capitalizations of ``slug`` to retry a failed lookup with.

    MediaWiki page titles are case-sensitive past the first character, and
    local album names often disagree with the wiki's capitalization
    (``A_Certain_Music_Album`` vs ``A_CERTAIN_MUSIC_ALBUM`` vs
    ``a_certain_music_album``).  Returns the variants drawn from
    (Title_Case, UPPERCASE, lowercase) in that order, excluding whichever
    form the original slug already is — two for a pure Title/UPPER/lower
    original, three for a mixed-case one like ``Skyruin_EP`` (whose page
    can hide under any of the three; capping at two was observed to drop
    the lowercase form that actually matched).  A slug with no cased
    Latin characters (e.g. a fully-CJK title) has no variants.
    """
    if slug.upper() == slug.lower():
        return []

    def _title(s: str) -> str:
        # str.title() would break on apostrophes ("Owen's" → "Owen'S"), so
        # capitalize each Latin letter-run (apostrophes included) manually.
        return re.sub(
            r"[A-Za-z][A-Za-z']*",
            lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(),
            s,
        )

    variants = []
    for cand in (_title(slug), slug.upper(), slug.lower()):
        if cand != slug and cand not in variants:
            variants.append(cand)
    return variants


@dataclass
class AlbumPlan:
    """Everything needed to tag one album, gathered during the fetch phase.

    Produced by :func:`fetch_album_plan` (all network I/O — both wikis,
    THBWiki page, theme translation, album-level TouhouDB verification) and
    consumed by :func:`tag_album_from_plan` (all local file I/O).  Splitting
    the two lets the batch driver fetch *every* album up front, while the
    THBWiki cookie is fresh, and only then write tags — so the cookie can't
    expire partway through a tagging run.

    The cache is purely in-memory for the duration of one run; nothing is
    written to disk.  A ``soup`` is intentionally *not* kept — everything
    parsed from the THBWiki page (titles, credits, metadata, staff map) is
    already distilled into the fields below, so the plan stays lightweight.

    When the fetch failed in a way that means there's nothing to tag (no
    music directory, no tracks on either wiki), ``error`` is set and the
    tag phase short-circuits to an error result.
    """
    wiki_album: str
    music_dir: str
    # Options captured at fetch time so the tag phase is self-contained.
    dry_run: bool
    romanize: bool
    force_titlesort: bool
    force_credits: bool
    fetch_metadata: bool
    fetch_credits: bool
    use_touhoudb: bool
    touhoudb_add_missing: bool
    # Selected output fields, captured from the GUI at fetch time.  Direct
    # callers that construct an AlbumPlan keep the historical all-tags mode.
    selected_tags: tuple[str, ...] = field(default_factory=lambda: WIKI_TAGS)
    # Fetched + fully-prepared track data and album metadata.
    wiki_tracks: list = field(default_factory=list)
    source_used: str | None = None
    album_info: dict = field(default_factory=dict)
    staff_name_map: dict = field(default_factory=dict)
    # TouhouDB verification results carried into the tag phase.  ``tdb_client``
    # is a live, per-run-cached client reused for per-track auto-add lookups
    # (which hit TouhouDB, not THBWiki, so they're cookie-independent and may
    # safely run during the tag phase).
    tdb_client: "touhoudb.TouhouDBClient | None" = None
    tdb_album_id: object | None = None
    # TouhouDB per-track titles {(disc, number): title}, used by the
    # track-discrepancy check as a third reference (populated only when a
    # TouhouDB album matched).
    tdb_track_titles: dict = field(default_factory=dict)
    # TouhouDB album-level values {album, date, catalog, circle} for the
    # mismatch dialog's TouhouDB column (populated only when matched).
    tdb_album_info: dict = field(default_factory=dict)
    missing_members: list[str] = field(default_factory=list)
    date_mismatch: tuple[str, str] | None = None
    catalog_mismatch: tuple[str, str] | None = None
    # Set when there is nothing to tag (see class docstring).
    error: str | None = None


_warned_english_wiki_unavailable = False


def _warn_english_wiki_unavailable() -> None:
    """Print the "English wiki disabled (no Playwright)" note once per process."""
    global _warned_english_wiki_unavailable
    if _warned_english_wiki_unavailable:
        return
    _warned_english_wiki_unavailable = True
    print(
        "English Touhou Wiki lookups are disabled (Playwright not installed) "
        "— using THBWiki only. Install the browser-fetch dependency group to "
        "enable them (see docs/DEPENDENCIES.md)."
    )


def _build_credit_romanization_map(
    wiki_tracks: list[dict],
    tdb_client,
    staff_name_map: dict[str, str],
) -> dict[str, str]:
    """Romanize every CJK name credited on an album, once per unique name.

    Applies the tagger's documented resolver priority — TouhouDB's official
    name, then the THBWiki Staff map, then nothing — and returns only the
    names that actually resolved, so ``_romanize_credit_names`` leaves the
    rest untouched.

    TouhouDB is consulted only when the run enabled it (``tdb_client`` is
    ``None`` otherwise); it is rate-limited to one request per second and
    caches per name, which is why this collects the album's unique names
    first instead of querying per track.  Latin-script names never reach a
    query — ``romanize()`` returns them unchanged.
    """
    names: list[str] = []
    seen: set[str] = set()
    for t in wiki_tracks:
        for field in ("arrangers", "vocalists", "lyricists"):
            for name in t.get(field) or []:
                if name and name not in seen and not _is_latin_script(name):
                    seen.add(name)
                    names.append(name)

    resolved: dict[str, str] = {}
    for name in names:
        roman = None
        if tdb_client is not None:
            try:
                roman = tdb_client.romanize(name)
            except Exception as exc:                  # noqa: BLE001
                print(f"  TouhouDB romanization failed for {name!r}: {exc}")
                roman = None
        if not roman:
            roman = staff_name_map.get(name)
        if roman and roman != name and _is_latin_script(roman):
            resolved[name] = roman
    return resolved


def fetch_album_plan(
    wiki_album: str,
    music_dir: str,
    *,
    dry_run: bool = False,
    thwiki_only: bool = False,
    mapping_path: str | None = None,
    romanize: bool = True,
    force_titlesort: bool = False,
    force_credits: bool = False,
    fetch_metadata: bool = True,
    fetch_credits: bool = True,
    use_touhoudb: bool = False,
    touhoudb_add_missing: bool = False,
    selected_tags=None,
    retry_case_variants: bool = False,
) -> AlbumPlan:
    """Fetch and prepare all wiki/TouhouDB data for one album (no file I/O).

    This is the network half of the old ``process_album``: it queries the
    English wiki and/or THBWiki, fetches the authoritative THBWiki page via
    the (mandatory) cookie, cross-checks and translates titles and credits,
    and runs album-level TouhouDB verification.  The result is an
    :class:`AlbumPlan` the tag phase can apply offline.

    ``retry_case_variants`` — when True and neither wiki matched the slug,
    retry the lookup with the re-capitalised forms of the slug (two for a
    pure Title/UPPER/lower original, three for a mixed-case one — see
    :func:`_slug_case_variants`).  Callers should only enable this for
    auto-suggested slugs, never for one the user typed or edited by hand.

    Raises ``ThwikiCookieError`` if the THBWiki page can't be fetched
    because the cookie is missing or stale — a batch-fatal condition the
    caller should abort on.  Per-album problems that aren't cookie-related
    (no music dir, album not on either wiki) are returned as a plan with
    ``error`` set instead.

    ``selected_tags`` optionally limits the output fields prepared and written
    by the resulting plan.  ``None`` preserves the historical all-fields
    behaviour used by CLI callers.
    """
    print(f"\n{'=' * 60}")
    print(f"Album: {wiki_album}  →  {music_dir}")
    print("=" * 60)

    selected_tags = _effective_selected_tags(selected_tags)
    # Verification is an optional enrichment path for the TouhouDB-derived
    # outputs (the artist pair, albumartistsort, and the credit tags).  With
    # none of them selected it cannot affect a file, so don't perform its
    # network work for a deliberately limited run.
    use_touhoudb = bool(use_touhoudb and set(selected_tags) & _TOUHOUDB_TAGS)
    touhoudb_add_missing = bool(touhoudb_add_missing and use_touhoudb)
    selection_options = _tag_selection_fetch_options(
        selected_tags,
        fetch_metadata=fetch_metadata,
        fetch_credits=fetch_credits,
        use_touhoudb=use_touhoudb,
    )
    fetch_metadata = selection_options["fetch_metadata"]
    fetch_credits = selection_options["fetch_credits"]
    fetch_staff_names = selection_options["fetch_staff_names"]

    def _plan(**kw) -> AlbumPlan:
        """Build an AlbumPlan, defaulting the captured options from args."""
        base = dict(
            wiki_album=wiki_album, music_dir=music_dir, dry_run=dry_run,
            romanize=romanize, force_titlesort=force_titlesort,
            force_credits=force_credits,
            fetch_metadata=fetch_metadata, fetch_credits=fetch_credits,
            use_touhoudb=use_touhoudb,
            touhoudb_add_missing=touhoudb_add_missing,
            selected_tags=selected_tags,
        )
        base.update(kw)
        return AlbumPlan(**base)

    if not os.path.isdir(music_dir):
        print(f"Error: '{music_dir}' is not a directory.")
        return _plan(error="directory not found")


    # --- Fetch & parse wiki ---
    def _try_wikis(slug: str) -> tuple[list, str | None, str | None]:
        """One English-wiki → THBWiki lookup pass for ``slug``.

        Returns ``(wiki_tracks, source_used, english_html)``; the tracks
        list is empty when the slug matched nothing on either wiki.
        """
        tracks: list = []
        source: str | None = None
        en_html: str | None = None

        if not thwiki_only and english_wiki_available():
            # Try the English Touhou Wiki first
            print("Trying English Touhou Wiki...")
            try:
                en_html = fetch_album_html(slug)
                tracks = parse_tracklist(en_html)
                if tracks:
                    source = "English Touhou Wiki"
            except Exception as exc:
                print(f"  English wiki failed: {exc}")
        elif not thwiki_only:
            # Playwright (the optional "browser-fetch" group) isn't installed,
            # so the English wiki can't be fetched.  THBWiki is the mandatory
            # source and has broader coverage, so this is a soft degradation —
            # note it once, then go straight to THBWiki.
            _warn_english_wiki_unavailable()

        if not tracks:
            # Fall back to THBWiki
            if not thwiki_only:
                print("\nFalling back to THBWiki (thwiki.cc)...")
            else:
                print("Using THBWiki (thwiki.cc)...")
            tracks = fetch_thwiki_tracks(slug)
            if tracks:
                source = "THBWiki"
        return tracks, source, en_html

    wiki_tracks, source_used, english_html = _try_wikis(wiki_album)

    # Auto-suggested slugs get extra lookup passes with re-capitalised
    # forms (Title_Case / UPPERCASE / lowercase minus the original — up to
    # three for a mixed-case original) — local capitalization often
    # disagrees with the wiki page title.  The rest of the fetch (THBWiki
    # page, TouhouDB query, the plan itself) uses the variant that matched.
    if not wiki_tracks and retry_case_variants:
        variants = _slug_case_variants(wiki_album)
        for attempt, variant in enumerate(variants, 1):
            print(f"\n↻ No match for '{wiki_album}' — retrying with "
                  f"capitalization variant {attempt}/{len(variants)}: "
                  f"'{variant}'")
            wiki_tracks, source_used, english_html = _try_wikis(variant)
            if wiki_tracks:
                print(f"  ✓ Matched on {source_used} as '{variant}'")
                wiki_album = variant
                break

    # If THBWiki's API returned some tracks with empty ogmusicname,
    # try scraping the rendered HTML page to fill in the gaps.  The
    # semantic data (API) and the page content (templates) are
    # independent in Semantic MediaWiki, so gaps are common.
    #
    # Also fetch the THBWiki page whenever we need album metadata or
    # staff credits — even when the English wiki was the primary source
    # for original titles.  The THBWiki page is the single source for
    # catalog number, release date, and the staff name mapping.
    # We fetch the THBWiki page HTML whenever we have a tracklist: it is the
    # title gap-filler for variant/edge-case tracks the primary source left
    # blank (see the cross-check block below), and the sole source for album
    # metadata and the staff name mapping.  It is also the complete-tracklist
    # fallback when neither wiki/API lookup returned rows; newly created or
    # otherwise unindexed THBWiki albums can still have a full rendered page.
    # This means the page is needed even when metadata and credits were both
    # explicitly disabled.
    need_html = bool(wiki_tracks) or fetch_metadata or fetch_credits
    if not wiki_tracks:
        need_html = True
    thwiki_soup: BeautifulSoup | None = None
    album_info: dict = {
        "catalog_numbers": [],
        "date":            None,
        "album":           None,
        "album_artists":   [],
        "genres":          [],
    }
    staff_name_map: dict[str, str] = {}

    if need_html:
        # A ThwikiCookieError here is batch-fatal (the mandatory cookie is
        # missing or stale): let it propagate so the driver can abort the
        # whole run before any tagging.  Any other failure is a per-album
        # soft error — the album just won't get the page's gap-fill/metadata.
        try:
            thwiki_soup = _fetch_thwiki_page_html(wiki_album)
        except ThwikiCookieError:
            raise
        except Exception as exc:
            print(f"  THBWiki HTML fetch failed: {exc}")

    if thwiki_soup is not None and not wiki_tracks:
        # asktrack is a semantic index and can lag behind the rendered page.
        # Use the page's numbered track rows as the scaffold in that case;
        # the normal HTML title/credit cross-check below will then enrich and
        # validate the same records as it does for API-backed albums.
        html_tracks = _parse_thwiki_html_tracklist(thwiki_soup)
        if html_tracks:
            wiki_tracks = html_tracks
            source_used = "THBWiki"
            print(f"  asktrack returned no rows; recovered "
                  f"{len(wiki_tracks)} track(s) from page HTML")

    if thwiki_soup is not None:
        # --- Cross-check original titles against HTML ---
        # The asktrack API's semantic data can disagree with the rendered
        # page (wrong ogmusicname, stale data, cross-disc leaks), and the
        # English wiki frequently omits original titles for variant tracks
        # (e.g. "Type C" / instrumental re-arranges).  The rendered THBWiki
        # HTML is what editors see and maintain, so it's the best gap-filler.
        #
        # Gap-FILLING (empty -> populated) runs whenever the THBWiki page is
        # available, regardless of which wiki was the primary source — this
        # rescues tracks the primary source left blank.  The more aggressive
        # CORRECT (overwrite a different value) and CLEAR (drop to empty)
        # behaviours treat the HTML as authoritative, so they only run when
        # THBWiki itself was the primary source; otherwise we'd risk
        # clobbering original-title data we trusted from the English wiki.
        if wiki_tracks:
            html_titles, html_tracks_seen = _parse_thwiki_html_titles(
                thwiki_soup)
            thwiki_is_primary = (source_used == "THBWiki")
            if html_titles or html_tracks_seen:
                filled = 0
                corrected = 0
                cleared = 0
                for t in wiki_tracks:
                    key = (t["disc"], t["number"])
                    if key in html_titles:
                        if not t["original_titles"]:
                            t["original_titles"] = html_titles[key]
                            filled += 1
                        elif (thwiki_is_primary
                              and t["original_titles"] != html_titles[key]):
                            t["original_titles"] = html_titles[key]
                            corrected += 1
                    elif (thwiki_is_primary
                          and key in html_tracks_seen
                          and t["original_titles"]):
                        # HTML saw this track but it has no original
                        # titles on the page — the API data is wrong
                        t["original_titles"] = []
                        cleared += 1
                parts = []
                if filled:
                    parts.append(f"filled {filled} gap(s)")
                if corrected:
                    parts.append(
                        f"corrected {corrected} mismatch(es)")
                if cleared:
                    parts.append(
                        f"cleared {cleared} spurious title(s)")
                if parts:
                    print(f"  HTML cross-check: {', '.join(parts)}")

        # --- Album info (catalog, date, album title, album artists) ---
        if fetch_metadata:
            album_info = parse_thwiki_album_info(thwiki_soup)
            # Translate the genre vocabulary to English here in the fetch
            # phase, so the plan carries write-ready values.  An unknown
            # CJK term is kept as-is (better recoverable than guessed) and
            # flagged in the log.
            translated_genres = []
            for g in album_info.get("genres", []):
                t = translate_genre(g)
                if genre_is_cjk(t):
                    print(f"  ⚠ No English translation for genre "
                          f"'{g}' — keeping original")
                translated_genres.append(t)
            album_info["genres"] = translated_genres
            info_parts = []
            if album_info["catalog_numbers"]:
                info_parts.append(
                    f"catalog={'; '.join(album_info['catalog_numbers'])}"
                )
            if album_info["date"]:
                info_parts.append(f"date={album_info['date']}")
            if album_info["album"]:
                info_parts.append(f"album={album_info['album']}")
            if album_info["album_artists"]:
                info_parts.append(
                    f"artist={' & '.join(album_info['album_artists'])}"
                )
            if album_info["genres"]:
                info_parts.append(
                    f"genre={'; '.join(album_info['genres'])}"
                )
            if info_parts:
                print(f"  Album metadata: {', '.join(info_parts)}")
            else:
                print("  No album metadata found on THBWiki page")

        # --- Staff name mapping (Japanese → romanized) ---
        # Built whenever we have the soup and either flag is on.  The
        # map is used to romanise per-track credits (fetch_credits) and
        # also to romanise the album-artist string (fetch_metadata), so
        # gating only on fetch_credits would leave --no-credits runs
        # writing Japanese album-artists even when a romanisation was
        # available.
        if fetch_staff_names:
            staff_name_map = parse_thwiki_staff_names(thwiki_soup)
            if staff_name_map:
                print(f"  Built name mapping: {len(staff_name_map)} "
                      f"romanized name(s) from Staff section")

        # --- Cross-check per-track credits against HTML ---
        # Mirrors the original-title cross-check above: the rendered THBWiki
        # page is authoritative.  Gap-FILLING (empty -> HTML) runs whenever
        # the page is available, per field.  CORRECTING (HTML overwrites a
        # *different* asktrack value) runs only on THBWiki-primary runs,
        # where the page outranks the asktrack API; on English-wiki-primary
        # runs the credits came from the page first anyway (the asktrack
        # credit injection below is fill-only), so there's nothing to
        # correct.  Both happen before the JP-form snapshot and romanisation
        # below, so corrected names flow into artist/artistsort and the
        # romanised credit tags alike.
        if fetch_credits and wiki_tracks:
            html_credits = _parse_thwiki_html_credits(thwiki_soup)
            if html_credits:
                thwiki_is_primary = (source_used == "THBWiki")
                filled = 0
                corrected = 0
                _CRED_FIELDS = (
                    ("arrangers", "arrange"),
                    ("vocalists", "vocal"),
                    ("lyricists", "lyric"),
                )
                for t in wiki_tracks:
                    hc = html_credits.get((t["disc"], t["number"]))
                    if not hc:
                        continue
                    for track_field, html_key in _CRED_FIELDS:
                        html_names = hc.get(html_key) or []
                        if not html_names:
                            continue
                        current = t.get(track_field) or []
                        if not current:
                            t[track_field] = list(html_names)
                            filled += 1
                        elif thwiki_is_primary and current != html_names:
                            t[track_field] = list(html_names)
                            corrected += 1
                parts = []
                if filled:
                    parts.append(f"filled {filled} credit field(s)")
                if corrected:
                    parts.append(f"corrected {corrected} credit field(s)")
                if parts:
                    print(f"  Credit cross-check: {', '.join(parts)} "
                          f"from THBWiki page HTML")

    # If the English wiki was the primary source but we still need
    # per-track credits, fetch them from the THBWiki asktrack API.
    if (fetch_credits and source_used == "English Touhou Wiki"
            and wiki_tracks):
        print("  Fetching per-track credits from THBWiki API...")
        credit_tracks = fetch_thwiki_tracks(wiki_album)
        if credit_tracks:
            # Build a (disc, number) → credits lookup
            credit_lookup = {
                (t["disc"], t["number"]): t for t in credit_tracks
            }
            injected = 0
            for t in wiki_tracks:
                key = (t["disc"], t["number"])
                ct = credit_lookup.get(key)
                if ct is None:
                    continue
                if not t.get("arrangers") and ct.get("arrangers"):
                    t["arrangers"] = ct["arrangers"]
                    injected += 1
                if not t.get("vocalists") and ct.get("vocalists"):
                    t["vocalists"] = ct["vocalists"]
                    injected += 1
                if not t.get("lyricists") and ct.get("lyricists"):
                    t["lyricists"] = ct["lyricists"]
                    injected += 1
            if injected:
                print(f"  Injected {injected} credit field(s) from "
                      f"THBWiki API")

    # Ensure all track dicts have credit keys (English wiki parser
    # doesn't produce them, and the API may have omitted some)
    for t in wiki_tracks:
        t.setdefault("arrangers", [])
        t.setdefault("vocalists", [])
        t.setdefault("lyricists", [])

    # Preserve the original (Japanese/canonical) credit names *before* the
    # arranger/vocalist/lyricist tags get romanised below.  The new `artist`
    # tag carries these original names, while `artistsort` carries the
    # romanised form, so the two must be captured separately.
    if use_touhoudb and set(selected_tags) & _ARTIST_TAGS:
        for t in wiki_tracks:
            t["arrangers_jp"] = list(t.get("arrangers", []))
            t["vocalists_jp"] = list(t.get("vocalists", []))
            t["lyricists_jp"] = list(t.get("lyricists", []))

    # Fill in missing original titles for variant tracks (instrumental,
    # piano version, off-vocal, etc.) by copying from another variant
    # of the same song that has the data.
    if wiki_tracks and "grouping" in selected_tags:
        wiki_tracks = _inherit_instrumental_titles(wiki_tracks)

    # Translate any Japanese/mixed theme names to English.
    # Always applied regardless of source: THBWiki returns Japanese
    # names, and the English wiki's fallback (when tooltips are
    # unavailable) also preserves the original Japanese text.
    # Titles already in English won't match the mapping and are
    # left unchanged.
    if wiki_tracks and "grouping" in selected_tags:
        mapping_data = load_theme_mapping(mapping_path)
        if mapping_data:
            print(f"  Loaded theme mapping "
                  f"({mapping_data['metadata']['theme_count']} themes)")
            wiki_tracks = translate_titles(wiki_tracks, mapping_data)
        else:
            print("  Warning: No theme mapping file found — "
                  "titles containing Japanese will not be translated.")
            print("  Run build_theme_mapping.py to create one.")

    if not wiki_tracks:
        print("\nError: No tracks found on either wiki. "
              "Check that the album name is correct.")
        return _plan(error="no tracks found on either wiki")

    print(f"\nFound {len(wiki_tracks)} tracks on {source_used}:")
    multi_disc = len({t["disc"] for t in wiki_tracks}) > 1
    current_disc = None
    for t in wiki_tracks:
        if multi_disc and t["disc"] != current_disc:
            current_disc = t["disc"]
            print(f"\n── Disc {current_disc} ──")
        if t["original_titles"]:
            label = "; ".join(t["original_titles"])
        else:
            label = "(original composition)"
        print(f"  {t['number']:02d}. {t['title']:<45} → {label}")

    # ============================================================
    # TouhouDB verification layer (optional secondary source)
    # ============================================================
    # TouhouDB is never a primary source.  When enabled it (1) verifies the
    # wiki's staff against TouhouDB's credits, (2) supplies official
    # romanizations that take precedence over the THBWiki Staff map, and
    # (3) cross-checks the release date and catalog number (notify-only).
    tdb_client: touhoudb.TouhouDBClient | None = None
    tdb_album: dict | None = None
    tdb_album_id = None
    tdb_track_titles: dict[tuple[int, int], str] = {}
    tdb_album_info: dict[str, str] = {}
    missing_members: list[str] = []
    date_mismatch: tuple[str, str] | None = None
    catalog_mismatch: tuple[str, str] | None = None

    # Build the album-level wiki staff set (normalized) used both for
    # verification and as the basis for what may legitimately appear in the
    # `artist` field.  Sources, unioned: every track's original-language
    # credits, the album-level Staff section (THBWiki) or aggregated track
    # credits (English wiki — its own parser), and the circle name(s).
    wiki_staff_norm: set[str] = set()
    for t in wiki_tracks:
        for n in (t.get("arrangers_jp", []) + t.get("vocalists_jp", [])
                  + t.get("lyricists_jp", [])):
            wiki_staff_norm.add(touhoudb._norm_name(n))
    if source_used == "THBWiki" and thwiki_soup is not None:
        thb_staff = parse_thwiki_album_staff(thwiki_soup)
        for role in ("arrangement", "vocal", "lyrics"):
            for n in thb_staff.get(role, []):
                wiki_staff_norm.add(touhoudb._norm_name(n))
    elif source_used == "English Touhou Wiki" and english_html:
        en_staff = parse_album_staff(english_html)
        for role in ("arrangement", "vocal", "lyrics"):
            for n in en_staff.get(role, []):
                wiki_staff_norm.add(touhoudb._norm_name(n))
    for c in album_info.get("album_artists", []):
        wiki_staff_norm.add(touhoudb._norm_name(c))
    wiki_staff_norm.discard("")

    if use_touhoudb:
        print("\n  Querying TouhouDB for verification...")
        tdb_client = touhoudb.TouhouDBClient()
        tdb_client.set_match_titles([
            album_info.get("album"),
            wiki_album,
            wiki_album.replace("_", " "),
        ])
        tdb_album = tdb_client.find_album(
            album_title=album_info.get("album"),
            slug=wiki_album,
            catalog_numbers=album_info.get("catalog_numbers"),
            date=album_info.get("date"),
            circle_names=album_info.get("album_artists"),
        )
        if tdb_album:
            tdb_album_id = tdb_album.get("id")
            print(f"  TouhouDB match: Al/{tdb_album_id} "
                  f"({tdb_album.get('name', '?')})")

            # --- Per-track titles (third reference for the discrepancy check) ---
            if tdb_album_id is not None:
                try:
                    tdb_track_titles = tdb_client.album_track_titles(
                        tdb_album_id)
                except Exception as exc:
                    print(f"  TouhouDB track-title fetch failed: {exc}")

            # --- Album-level values for the mismatch dialog's TouhouDB column ---
            tdb_circle = "; ".join(
                touhoudb._entry_name(e)
                for e in touhoudb.classify_album_staff(tdb_album)["circle"]
                if touhoudb._entry_name(e)
            )
            tdb_album_info = {
                "album":   tdb_album.get("name") or "",
                "date":    touhoudb.release_date(tdb_album) or "",
                "catalog": touhoudb.catalog_number(tdb_album) or "",
                "circle":  tdb_circle,
            }

            # --- Staff verification (album-level) ---
            missing_members = touhoudb.find_missing_members(
                tdb_album, wiki_staff_norm)
            if missing_members:
                print(f"  ⚠ Missing members (on TouhouDB, not on "
                      f"{source_used}): {', '.join(missing_members)}")
                if touhoudb_add_missing:
                    print("    auto-add is ON — these will be added per "
                          "track from TouhouDB song credits where they "
                          "apply.")
                else:
                    print("    not added (auto-add is off); reported only.")

            # --- Release date / catalog cross-check (notify-only) ---
            tdb_date = touhoudb.release_date(tdb_album)
            if (album_info.get("date") and tdb_date
                    and not touhoudb._dates_match(
                        album_info["date"], tdb_date)):
                date_mismatch = (album_info["date"], tdb_date)
                print(f"  ⚠ Release date differs — {source_used}: "
                      f"{album_info['date']}  |  TouhouDB: {tdb_date}")
            tdb_cat = touhoudb.catalog_number(tdb_album)
            if tdb_cat and album_info.get("catalog_numbers"):
                wiki_cats_norm = {
                    touhoudb._norm_catalog(c)
                    for c in album_info["catalog_numbers"]
                }
                if touhoudb._norm_catalog(tdb_cat) not in wiki_cats_norm:
                    catalog_mismatch = (
                        "; ".join(album_info["catalog_numbers"]), tdb_cat)
                    print(f"  ⚠ Catalog number differs — {source_used}: "
                          f"{'; '.join(album_info['catalog_numbers'])}  |  "
                          f"TouhouDB: {tdb_cat}")
        else:
            print("  No confident TouhouDB album match — "
                  "proceeding on wiki data only.")

    # --- Romanize credit names -------------------------------------------
    # Deliberately placed after the TouhouDB block: the credit tags follow
    # the same resolver priority as the sort fields (TouhouDB official name >
    # THBWiki Staff map > the original name), and the client only exists by
    # this point.  The `*_jp` snapshots above already hold the original
    # forms for the `artist` tag, so rewriting these fields is safe here.
    if (fetch_credits and wiki_tracks
            and set(selected_tags) & _CREDIT_TAGS):
        credit_map = _build_credit_romanization_map(
            wiki_tracks, tdb_client, staff_name_map)
        if credit_map:
            print(f"  Romanized {len(credit_map)} credit name(s) "
                  f"(TouhouDB / Staff map)")
            for t in wiki_tracks:
                for field in ("arrangers", "vocalists", "lyricists"):
                    t[field] = _romanize_credit_names(t[field], credit_map)

    # All network / data-prep done — package the in-memory plan for tagging.
    return _plan(
        wiki_tracks=wiki_tracks,
        source_used=source_used,
        album_info=album_info,
        staff_name_map=staff_name_map,
        tdb_client=tdb_client,
        tdb_album_id=tdb_album_id,
        tdb_track_titles=tdb_track_titles,
        tdb_album_info=tdb_album_info,
        missing_members=missing_members,
        date_mismatch=date_mismatch,
        catalog_mismatch=catalog_mismatch,
    )


def tag_album_from_plan(plan: AlbumPlan, *, on_confirm=None) -> dict:
    """Apply an :class:`AlbumPlan` to the local files (file I/O, no network).

    This is the tagging half of the old ``process_album``: scan the music
    directory, match local files to the fetched tracks, and write grouping,
    metadata, credits, artist, and titlesort tags.  Returns the per-album
    summary dict (the same shape ``process_album`` has always returned).

    When ``plan.error`` is set there was nothing to fetch (no directory, no
    tracks on either wiki), so this short-circuits to a zeroed error result.
    The only network this phase ever does is the optional ``--touhoudb-add-
    missing`` per-track lookups, which hit TouhouDB (not THBWiki) and so are
    cookie-independent.

    Before writing anything, a title-discrepancy check (local vs wiki vs
    TouhouDB titles) runs; the report is attached to the result.  When the
    album looks wholesale wrong (``severe``), the run pauses: if ``on_confirm``
    is given (GUI), it is called with a context dict and must return one of
    ``"skip"`` (don't tag this album), ``"cancel"`` (abort the batch — sets
    ``cancel_batch`` in the result), or ``"continue"``.  With no ``on_confirm``
    (CLI/headless), a severe mismatch auto-skips the album.
    """
    if plan.error:
        return _empty_result(
            plan.wiki_album, music_dir=plan.music_dir,
            source=plan.source_used, error=plan.error,
        )

    # Unpack the plan into the locals the tagging body below expects.
    wiki_album           = plan.wiki_album
    music_dir            = plan.music_dir
    dry_run              = plan.dry_run
    romanize             = plan.romanize
    force_titlesort      = plan.force_titlesort
    fetch_metadata       = plan.fetch_metadata
    fetch_credits        = plan.fetch_credits
    use_touhoudb         = plan.use_touhoudb
    touhoudb_add_missing = plan.touhoudb_add_missing
    force_credits        = plan.force_credits
    selected_tags        = frozenset(_effective_selected_tags(plan.selected_tags))
    wiki_tracks          = plan.wiki_tracks
    source_used          = plan.source_used
    album_info           = plan.album_info
    staff_name_map       = plan.staff_name_map
    tdb_client           = plan.tdb_client
    tdb_album_id         = plan.tdb_album_id
    tdb_track_titles     = plan.tdb_track_titles
    missing_members      = plan.missing_members
    date_mismatch        = plan.date_mismatch
    catalog_mismatch     = plan.catalog_mismatch

    print(f"\n{'=' * 60}")
    print(f"Tagging: {wiki_album}  →  {music_dir}")
    print("=" * 60)

    # Romanization resolver used for `artist`/`artistsort` and the
    # `albumartist` policy: TouhouDB official romanization first, then the
    # THBWiki Staff map, then the original name as a last resort.  Works
    # with or without a TouhouDB album match (per-name artist lookups are
    # independent of album matching); falls back to the staff map alone
    # when TouhouDB is disabled.
    def resolve_roman(name: str) -> str:
        if not name or _is_latin_script(name):
            return name
        if tdb_client is not None:
            r = tdb_client.romanize(name)
            if r and _is_latin_script(r):
                return r
        r2 = staff_name_map.get(name)
        if r2 and _is_latin_script(r2):
            return r2
        return name

    # --- Scan, match & severe-mismatch check (re-runnable loop) ---
    # The whole scan→match→compare→confirm block is a loop so the GUI's
    # "Split via CUE sheet" recovery can return a "rescan" decision: it splits
    # an un-split album image into per-track files on disk, then we re-scan and
    # re-compare from scratch.  A correctly-split album is then no longer severe
    # and falls straight through to tagging.  Capped so a pathological case
    # (split that never resolves the mismatch) can't loop forever.
    _MAX_RESCANS = 3
    rescan_count = 0
    while True:
        local_files = scan_music_files(music_dir)
        if not local_files:
            print(f"\nNo supported music files found in '{music_dir}'.")
            return _empty_result(
                wiki_album, music_dir=music_dir, source=source_used,
                error="no music files found",
            )

        local_discs = {f["disc"] for f in local_files}
        if len(local_discs) > 1:
            print(f"\nFound {len(local_files)} local file(s) "
                  f"across {len(local_discs)} discs.")
        else:
            print(f"\nFound {len(local_files)} local file(s).")

        # --- Match ---
        pairs = match_tracks(wiki_tracks, local_files)

        # --- Track-discrepancy check (titles: local vs wiki vs TouhouDB) ---
        # Always computed and reported.  When the album looks wholesale wrong
        # (severe), pause for confirmation (GUI on_confirm) or auto-skip (CLI).
        report = compare_tracklists(
            wiki_tracks, local_files, tdb_track_titles)
        title_discrepancies = report["discrepancies"]
        severe_mismatch = report["severe"]

        def _mismatch_result(*, mismatch_skipped=False,
                             cancel_batch=False) -> dict:
            res = _empty_result(
                wiki_album, music_dir=music_dir, source=source_used)
            res["title_discrepancies"] = title_discrepancies
            res["severe_mismatch"] = severe_mismatch
            res["mismatch_skipped"] = mismatch_skipped
            res["cancel_batch"] = cancel_batch
            return res

        if not severe_mismatch:
            break

        print(f"\n⚠ Severe track mismatch: only "
              f"{report['match_rate'] * 100:.0f}% of "
              f"{report['local_count']} local track(s) line up with "
              f"{report['fetched_count']} fetched track(s).")
        if on_confirm is None:
            print("  → Auto-skipping (severe mismatch; no interactive "
                  "confirmation available). Re-run in the GUI to review.")
            return _mismatch_result(mismatch_skipped=True)

        context = _build_mismatch_context(plan, local_files, pairs, report)
        decision = on_confirm(context)
        if decision == "cancel":
            print("  → Cancelled from the confirmation dialog; "
                  "no files were tagged.")
            return _mismatch_result(cancel_batch=True)
        if decision == "rescan":
            rescan_count += 1
            if rescan_count > _MAX_RESCANS:
                print("  → Still mismatched after re-scanning; skipping "
                      "(no files were tagged).")
                return _mismatch_result(mismatch_skipped=True)
            print("  → Re-scanning the folder (e.g. after a CUE split)…")
            continue
        if decision == "skip":
            print("  → Skipped (user choice); no files were tagged.")
            return _mismatch_result(mismatch_skipped=True)
        print("  → Continuing with tagging (user choice).")
        break

    prefix = "DRY RUN — " if dry_run else ""
    print(f"\n{prefix}Tagging results:")
    print("-" * 60)
    tagged  = 0
    skipped = 0
    cleared = 0
    errors  = 0
    # Romanisation counters (only incremented when ROMANIZER_AVAILABLE
    # and ``romanize`` is True; otherwise stay at zero).
    romanized   = 0
    overwritten = 0
    rm_skipped  = 0
    rm_no_title = 0
    rm_errors   = 0
    # Album metadata counters
    meta_wrote   = 0
    meta_skipped = 0
    # Per-track credit counters
    cred_wrote   = 0
    cred_skipped = 0
    # Per-track artist / artistsort counters (TouhouDB-driven)
    artist_wrote   = 0
    artist_skipped = 0
    # Tags the user locked by hand in the Tag Edit tab and that this run
    # therefore left alone.  Counts locked tags respected, not writes
    # prevented: a locked tag that would have been skipped anyway is counted.
    locked_skipped = 0
    # Per-track tag change log — each entry is a dict with keys:
    #   filename, path, tag, old (str|None), new (str|None)
    # Populated for every tag that would be written (or cleared/deleted)
    # so the GUI can show a per-track diff view.  `path` is the key the view
    # groups on: two discs of one album routinely hold the same `filename`
    # ("01 - Intro.flac"), and grouping on that alone merges them.
    tag_changes: list[dict] = []

    do_romanize = (
        romanize and "titlesort" in selected_tags and ROMANIZER_AVAILABLE
    )
    if romanize and "titlesort" in selected_tags and not ROMANIZER_AVAILABLE:
        if not ROMANIZER_IMPORT_OK:
            print("  (Romanisation disabled: japanese_romanizer module "
                  "not importable.)")
        else:
            print("  (Romanisation disabled: MeCab / UniDic not "
                  "installed.  Run: pip install --user mecab-python3 "
                  "unidic && python -m unidic download)")
    local_multi_disc = len(local_discs) > 1
    current_disc = None

    for local_file, wiki_track in pairs:
        fname = local_file["filename"]
        fpath = local_file["path"]
        # A tag the user set by hand in the Tag Edit tab is locked and the
        # wiki never overrides it — not even `force_credits`, and not even
        # `album`, which is otherwise authoritative.  Narrowing the existing
        # per-tag gate is all it takes: every write decision below is already
        # spelled `<tag> in file_tags`.
        locked_here = selected_tags & tag_locks.locked_tags(fpath)
        file_tags = selected_tags - locked_here
        if locked_here:
            locked_skipped += len(locked_here)
            print(f"  [LOCKED]    {fname}  "
                  f"{', '.join(sorted(locked_here))}")
        # Print disc header when transitioning between discs
        if local_multi_disc and local_file["disc"] != current_disc:
            current_disc = local_file["disc"]
            print(f"\n── Disc {current_disc} ──")

        # --- Grouping write (existing behaviour) ---
        if "grouping" not in file_tags:
            pass
        elif wiki_track is None:
            print(f"  [NO MATCH]  {fname}")
            skipped += 1
        elif not wiki_track["original_titles"]:
            # No theme to write — the track is an original composition.
            no_theme_note = "(original composition)"
            existing = read_grouping(fpath)
            if existing:
                print(f"  [CLEAR]     {fname}  {no_theme_note}")
                print(f"              removed = {existing}")
                try:
                    clear_grouping(fpath, dry_run=dry_run)
                    cleared += 1
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": "grouping",
                                        "old": existing, "new": None})
                except Exception as e:
                    print(f"              ERROR: {e}")
                    errors += 1
            else:
                print(f"  [SKIP]      {fname}  {no_theme_note}")
                skipped += 1
        else:
            value = "; ".join(wiki_track["original_titles"])
            existing_grp = read_grouping(fpath)
            print(f"  [TAG]       {fname}")
            print(f"              grouping = {value}")
            try:
                set_grouping(fpath, value, dry_run=dry_run)
                tagged += 1
                if existing_grp != value:
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": "grouping",
                                        "old": existing_grp,
                                        "new": value})
            except Exception as e:
                print(f"              ERROR: {e}")
                errors += 1

        # --- Album metadata (catalog, date, year, album, albumartist) ---
        # Written to every matched file.  Skip-logic varies per field:
        #
        # catalognumber, date, year  -> skip if file already has a value
        # album                      -> always overwrite local on mismatch
        #                               (THBWiki is the authoritative source)
        # albumartist                -> set to the original (CJK) circle
        #                               name; the romanised / official
        #                               English form goes to albumartistsort
        #                               (see the album-artist block below)
        if fetch_metadata:
            # Per-disc catno: for a 2-disc album whose Catalog ID is
            # "ABCD-12345/6", disc 1 files get "ABCD-12345" and disc 2
            # files get "ABCD-12346".  Single-catno albums always
            # write the same value to every track.  When the disc count
            # in the catno list doesn't line up with the local file's
            # disc number, fall back to the joined string so nothing is
            # silently dropped.
            catnos = album_info.get("catalog_numbers") or []
            if len(catnos) == 0:
                catno_val: str | None = None
            elif len(catnos) == 1:
                catno_val = catnos[0]
            else:
                disc_idx = local_file["disc"] - 1
                if 0 <= disc_idx < len(catnos):
                    catno_val = catnos[disc_idx]
                else:
                    catno_val = "; ".join(catnos)

            # Derive year from the date (always the first 4 characters
            # of a "YYYY-MM-DD" / "YYYY-MM" / "YYYY" string).
            album_date = album_info.get("date")
            album_year = album_date[:4] if album_date else None

            # Fields that follow the simple "skip if existing" rule.
            for meta_tag, meta_val in (
                ("catalognumber", catno_val),
                ("date",          album_date),
                ("year",          album_year),
            ):
                if meta_tag not in file_tags or not meta_val:
                    continue
                existing = _get_existing_tag(fpath, meta_tag)
                if existing:
                    meta_skipped += 1
                    continue
                try:
                    _set_tag(fpath, meta_tag, meta_val, dry_run=dry_run)
                    print(f"  [META]      {fname}  "
                          f"{meta_tag} = {meta_val}")
                    meta_wrote += 1
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": meta_tag,
                                        "old": None, "new": meta_val})
                except Exception as exc:
                    print(f"  [META-ERR]  {fname}  "
                          f"{meta_tag}: {exc}")
                    errors += 1

            # --- Genre (multi-value, MERGED with existing) ---
            # Album-level, from the THBWiki info box (translated to
            # English in the fetch phase).  Unlike the skip-if-present
            # metadata above, genre is *merged* with whatever the file
            # already has (see _merge_genres): the album keeps its
            # pre-existing / hand-added genres AND gains the wiki's, for
            # a fuller picture of its styles.  Written as separate
            # multi-value fields (one genre= per genre on FLAC/OGG/Opus)
            # via set_genres — it can't share the _set_tag loop above.
            wiki_genres = album_info.get("genres") or []
            if "genre" in file_tags and wiki_genres:
                existing_genres = read_genres(fpath)
                merged = _merge_genres(existing_genres, wiki_genres)
                if merged == existing_genres:
                    # Nothing new to add (and no existing CJK genre to
                    # normalise) — leave the file untouched.
                    meta_skipped += 1
                else:
                    genre_disp = "; ".join(merged)
                    old_disp = "; ".join(existing_genres) or None
                    try:
                        set_genres(fpath, merged, dry_run=dry_run)
                        if existing_genres:
                            print(f"  [META-OVR]  {fname}  "
                                  f"genre = {genre_disp}")
                            print(f"              was: {old_disp}")
                        else:
                            print(f"  [META]      {fname}  "
                                  f"genre = {genre_disp}")
                        meta_wrote += 1
                        tag_changes.append({"filename": fname, "path": fpath,
                                            "tag": "genre",
                                            "old": old_disp,
                                            "new": genre_disp})
                    except Exception as exc:
                        print(f"  [META-ERR]  {fname}  genre: {exc}")
                        errors += 1

            # --- Album title: always overwrite on mismatch ---
            new_album = album_info.get("album")
            if "album" in file_tags and new_album:
                existing = _get_existing_tag(fpath, "album")
                if existing == new_album:
                    meta_skipped += 1
                else:
                    try:
                        _set_tag(
                            fpath, "album", new_album, dry_run=dry_run,
                        )
                        if existing:
                            print(f"  [META-OVR]  {fname}  "
                                  f"album = {new_album}")
                            print(f"              was: {existing}")
                        else:
                            print(f"  [META]      {fname}  "
                                  f"album = {new_album}")
                        meta_wrote += 1
                        tag_changes.append({"filename": fname, "path": fpath,
                                            "tag": "album",
                                            "old": existing,
                                            "new": new_album})
                    except Exception as exc:
                        print(f"  [META-ERR]  {fname}  album: {exc}")
                        errors += 1

            # --- Album artist (CJK original) + album-artist-sort (romanised) ---
            # Policy: keep BOTH forms, mirroring the title/titlesort
            # convention and pairing with the streaming-sync swap script:
            #   * `albumartist`     holds the ORIGINAL circle name(s), as
            #     fetched — usually CJK (e.g. "森羅万象").
            #   * `albumartistsort` holds the romanised / official English
            #     name(s) (e.g. "ShinRa-Bansho").
            #
            # The fetched circle list (`album_artists`, from THBWiki) is the
            # canonical source for the CJK display form; `resolve_roman`
            # (TouhouDB official > Staff map) supplies the romanisation.
            #
            # `albumartist` (display) target, first applicable wins:
            #   1. the fetched circle name(s), joined with " & ";
            #   2. an existing CJK `albumartist` already on the file;
            #   3. otherwise leave the file's `albumartist` untouched — there
            #      is no CJK source to write (e.g. no THBWiki match).
            #
            # `albumartistsort` (romanised) target, first applicable wins:
            #   1. an existing Latin `albumartistsort` — a hand-set value is
            #      respected and never overwritten;
            #   2. an existing Latin `albumartist` — e.g. one left by the old
            #      romanise-in-place policy, reused as the sort form;
            #   3. the romanised circle (TouhouDB official > Staff map), when
            #      fully Latin.
            # The sort value is written only when it is Latin AND differs from
            # the (effective) `albumartist`, so the field is never a duplicate
            # of the display name nor a second CJK copy.
            wants_albumartist = "albumartist" in file_tags
            wants_albumartistsort = "albumartistsort" in file_tags
            raw_artists = album_info.get("album_artists") or []
            existing_aa = (
                _get_existing_tag(fpath, "albumartist")
                if wants_albumartist or wants_albumartistsort else None
            )
            existing_aas = (
                _get_existing_tag(fpath, "albumartistsort")
                if wants_albumartistsort else None
            )

            # 1. CJK display value for `albumartist`.
            if not wants_albumartist:
                new_aa = None
            elif raw_artists:
                new_aa = " & ".join(raw_artists)
            elif existing_aa and not _is_latin_script(existing_aa):
                new_aa = existing_aa
            else:
                new_aa = None  # no CJK source — leave albumartist as-is

            # 2. Romanised value for `albumartistsort` (most authoritative
            #    first); an existing Latin value wins over a fresh resolve.
            if not wants_albumartistsort:
                new_aas = None
            elif existing_aas and _is_latin_script(existing_aas):
                new_aas = existing_aas
            elif existing_aa and _is_latin_script(existing_aa):
                new_aas = existing_aa
            elif raw_artists:
                romanised = " & ".join(resolve_roman(c) for c in raw_artists)
                new_aas = romanised if _is_latin_script(romanised) else None
            else:
                new_aas = None

            # Guard: the sort field must be Latin and must not merely
            # duplicate whatever `albumartist` will end up being.
            effective_aa = new_aa if new_aa is not None else existing_aa
            if new_aas is not None and (
                not _is_latin_script(new_aas) or new_aas == effective_aa
            ):
                new_aas = None

            # --- Write `albumartist` (CJK display) ---
            if (wants_albumartist
                    and new_aa is not None and new_aa != existing_aa):
                try:
                    _set_tag(fpath, "albumartist", new_aa, dry_run=dry_run)
                    if existing_aa:
                        print(f"  [META-OVR]  {fname}  "
                              f"albumartist = {new_aa}")
                        print(f"              was: {existing_aa}")
                    else:
                        print(f"  [META]      {fname}  "
                              f"albumartist = {new_aa}")
                    meta_wrote += 1
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": "albumartist",
                                        "old": existing_aa,
                                        "new": new_aa})
                except Exception as exc:
                    print(f"  [META-ERR]  {fname}  albumartist: {exc}")
                    errors += 1
            elif wants_albumartist and new_aa is not None:
                # Computed value equals what's already there.
                meta_skipped += 1

            # --- Write `albumartistsort` (romanised) ---
            if (wants_albumartistsort
                    and new_aas is not None and new_aas != existing_aas):
                try:
                    _set_tag(fpath, "albumartistsort", new_aas,
                             dry_run=dry_run)
                    if existing_aas:
                        print(f"  [META-OVR]  {fname}  "
                              f"albumartistsort = {new_aas}")
                        print(f"              was: {existing_aas}")
                    else:
                        print(f"  [META]      {fname}  "
                              f"albumartistsort = {new_aas}")
                    meta_wrote += 1
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": "albumartistsort",
                                        "old": existing_aas,
                                        "new": new_aas})
                except Exception as exc:
                    print(f"  [META-ERR]  {fname}  "
                          f"albumartistsort: {exc}")
                    errors += 1
            elif wants_albumartistsort and new_aas is not None:
                # Computed value equals what's already there.
                meta_skipped += 1

        # --- Per-track credits (arranger, vocalist, lyricist) ---
        if fetch_credits and wiki_track is not None:
            # Credits are skip-if-present by default.  `force_credits`
            # ("Force overwrite staff tags") makes the wiki authoritative
            # instead, which is what lets a re-run replace credits an earlier
            # release wrote — including the circle names the Staff-map bug
            # produced, and credits predating TouhouDB romanisation.  A value
            # the wiki already agrees with is still left alone, so forcing
            # does not churn files or fill the log with no-op writes.
            for cred_tag, cred_list in (
                ("arranger",  wiki_track.get("arrangers", [])),
                ("vocalist",  wiki_track.get("vocalists", [])),
                ("lyricist",  wiki_track.get("lyricists", [])),
            ):
                if cred_tag not in file_tags or not cred_list:
                    continue
                existing = _get_existing_tag(fpath, cred_tag)
                cred_val = "; ".join(cred_list)
                if existing and not force_credits:
                    cred_skipped += 1
                    continue
                if existing == cred_val:
                    # Forcing, but the wiki agrees with the file already.
                    cred_skipped += 1
                    continue
                try:
                    _set_tag(fpath, cred_tag, cred_val,
                             dry_run=dry_run)
                    if existing:
                        print(f"  [CRED-OVR]  {fname}  "
                              f"{cred_tag} = {cred_val}")
                        print(f"              was: {existing}")
                    else:
                        print(f"  [CREDIT]    {fname}  "
                              f"{cred_tag} = {cred_val}")
                    cred_wrote += 1
                    tag_changes.append({"filename": fname, "path": fpath,
                                        "tag": cred_tag,
                                        "old": existing or None,
                                        "new": cred_val})
                except Exception as exc:
                    print(f"  [CRED-ERR]  {fname}  "
                          f"{cred_tag}: {exc}")
                    errors += 1

        # --- Per-track artist / artistsort (TouhouDB feature) ---
        # `artist`     = original-language producer/arranger + vocalist names
        # `artistsort` = their romanised forms (TouhouDB official > Staff map)
        # Names come from the wiki's per-track credits (the original JP forms
        # stashed before romanisation).  When the auto-add-missing toggle is
        # on AND we have a TouhouDB album match, TouhouDB's own per-song
        # producer/vocalist credits are merged in (one rate-limited request
        # per track).  Both tags follow skip-if-present so hand-set values
        # are never clobbered; `artistsort` additionally won't be written if
        # the romanised join still contains CJK (incomplete romanisation).
        if (use_touhoudb and wiki_track is not None
                and file_tags & _ARTIST_TAGS):
            names_jp: list[str] = []
            for n in (wiki_track.get("arrangers_jp", [])
                      + wiki_track.get("vocalists_jp", [])):
                if n and n not in names_jp:
                    names_jp.append(n)
            if (touhoudb_add_missing and tdb_client is not None
                    and tdb_album_id is not None):
                try:
                    extra = tdb_client.track_extra_artists(
                        tdb_album_id,
                        local_file["disc"],
                        wiki_track["number"],
                    )
                except Exception as exc:
                    extra = []
                    print(f"  [ARTIST-ERR] {fname}  "
                          f"TouhouDB song lookup: {exc}")
                for n in extra:
                    if n and n not in names_jp:
                        names_jp.append(n)

            if names_jp:
                # artist (original names)
                if "artist" not in file_tags:
                    pass
                elif _get_existing_tag(fpath, "artist"):
                    artist_skipped += 1
                else:
                    artist_val = "; ".join(names_jp)
                    try:
                        _set_tag(fpath, "artist", artist_val,
                                 dry_run=dry_run)
                        print(f"  [ARTIST]    {fname}  "
                              f"artist = {artist_val}")
                        artist_wrote += 1
                        tag_changes.append({"filename": fname, "path": fpath,
                                            "tag": "artist",
                                            "old": None,
                                            "new": artist_val})
                    except Exception as exc:
                        print(f"  [ARTIST-ERR] {fname}  artist: {exc}")
                        errors += 1

                # artistsort (romanised)
                sort_val = "; ".join(resolve_roman(n) for n in names_jp)
                if "artistsort" not in file_tags:
                    pass
                elif not _is_latin_script(sort_val):
                    # incomplete romanisation — don't write CJK to a sort
                    artist_skipped += 1
                elif _get_existing_tag(fpath, "artistsort"):
                    artist_skipped += 1
                else:
                    try:
                        _set_tag(fpath, "artistsort", sort_val,
                                 dry_run=dry_run)
                        print(f"  [ARTIST]    {fname}  "
                              f"artistsort = {sort_val}")
                        artist_wrote += 1
                        tag_changes.append({"filename": fname, "path": fpath,
                                            "tag": "artistsort",
                                            "old": None,
                                            "new": sort_val})
                    except Exception as exc:
                        print(f"  [ARTIST-ERR] {fname}  artistsort: {exc}")
                        errors += 1

        # --- Romanisation (independent of whether grouping was set —
        #     a track with no wiki match or no original-title may still
        #     have a Japanese title that benefits from titlesort) ---
        if do_romanize and "titlesort" in file_tags:
            fb = wiki_track["title"] if wiki_track else None
            try:
                rm = japanese_romanizer.romanize_file(
                    local_file["path"],
                    force_titlesort=force_titlesort,
                    dry_run=dry_run,
                    fallback_title=fb,
                )
            except Exception as exc:
                print(f"              ROMANIZE ERROR: {exc}")
                rm_errors += 1
                continue

            status = rm["status"]
            if status == "romanized":
                print(f"  [ROMANIZE]  {fname}")
                print(f"              titlesort = {rm['titlesort_new']}")
                romanized += 1
                tag_changes.append({"filename": fname, "path": fpath,
                                    "tag": "titlesort",
                                    "old": rm.get("titlesort_old"),
                                    "new": rm["titlesort_new"]})
            elif status == "overwritten":
                print(f"  [OVERWRITE] {fname}")
                print(f"              was = {rm['titlesort_old']}")
                print(f"              now = {rm['titlesort_new']}")
                overwritten += 1
                tag_changes.append({"filename": fname, "path": fpath,
                                    "tag": "titlesort",
                                    "old": rm["titlesort_old"],
                                    "new": rm["titlesort_new"]})
            elif status == "skip_no_japanese":
                print(f"  [SKIP-RM]   {fname}  (no Japanese)")
                rm_skipped += 1
            elif status == "skip_exists":
                print(f"  [SKIP-RM]   {fname}  "
                      f"(titlesort already set; not forcing)")
                print(f"              current   = {rm['titlesort_old']}")
                print(f"              would set = {rm['titlesort_new']}")
                rm_skipped += 1
            elif status == "skip_unchanged":
                print(f"  [SKIP-RM]   {fname}  "
                      f"(titlesort already correct: "
                      f"{rm['titlesort_old']})")
                rm_skipped += 1
            elif status in {"skip_non_japanese", "skip_ambiguous_language"}:
                print(f"  [LANG-REVIEW] {fname}  "
                      f"(non-Japanese or uncertain language; titlesort preserved)")
                rm_skipped += 1
            elif status == "skip_unresolved":
                print(f"  [UNRESOLVED] {fname}  (titlesort preserved)")
                print(f"              incomplete = {rm['titlesort_new']}")
                rm_skipped += 1
            elif status == "skip_no_title":
                rm_no_title += 1
            else:  # error
                print(f"              ROMANIZE ERROR: {rm.get('error')}")
                rm_errors += 1

        # --- Report what the wiki would have written for locked tags ---
        # Locked tags were excluded from file_tags so no writes happened.
        # Compute the would-be values here (best-effort; some complex tags
        # like titlesort are omitted) so the GUI summary can show a
        # "wiki would have set X" diff for each locked tag.
        if locked_here:
            _cred_key = {
                "arranger": "arrangers", "vocalist": "vocalists",
                "lyricist": "lyricists",
            }
            for ltag in sorted(locked_here):
                wiki_val: str | None = None

                if ltag == "grouping":
                    if (wiki_track
                            and wiki_track.get("original_titles")):
                        wiki_val = "; ".join(
                            wiki_track["original_titles"])
                    elif (wiki_track
                          and not wiki_track["original_titles"]):
                        wiki_val = ""  # would clear (original composition)
                elif ltag == "album" and fetch_metadata:
                    wiki_val = album_info.get("album")
                elif ltag == "catalognumber" and fetch_metadata:
                    catnos_l = album_info.get("catalog_numbers") or []
                    if len(catnos_l) == 1:
                        wiki_val = catnos_l[0]
                    elif len(catnos_l) > 1:
                        di = local_file["disc"] - 1
                        wiki_val = (catnos_l[di]
                                    if 0 <= di < len(catnos_l)
                                    else "; ".join(catnos_l))
                elif ltag == "date" and fetch_metadata:
                    wiki_val = album_info.get("date")
                elif ltag == "year" and fetch_metadata:
                    d = album_info.get("date")
                    wiki_val = d[:4] if d else None
                elif ltag == "albumartist" and fetch_metadata:
                    ra = album_info.get("album_artists") or []
                    if ra:
                        wiki_val = " & ".join(ra)
                elif ltag == "albumartistsort" and fetch_metadata:
                    ra = album_info.get("album_artists") or []
                    if ra:
                        rom = " & ".join(resolve_roman(c) for c in ra)
                        if _is_latin_script(rom):
                            wiki_val = rom
                elif ltag in _cred_key and fetch_credits and wiki_track:
                    cl = wiki_track.get(_cred_key[ltag], [])
                    if cl:
                        wiki_val = "; ".join(cl)
                # artist, artistsort, titlesort — too complex to
                # recompute outside the main write logic; omitted.

                if wiki_val is None:
                    continue
                existing = (
                    read_grouping(fpath) if ltag == "grouping"
                    else _get_existing_tag(fpath, ltag)
                )
                # Only report when the wiki value differs from what's
                # already on disk — a lock that agrees with the wiki is
                # a no-op and not interesting.
                if wiki_val == "" and not existing:
                    continue  # would-clear on already-empty
                if wiki_val and wiki_val == existing:
                    continue
                tag_changes.append({
                    "filename": fname, "path": fpath, "tag": ltag,
                    "old": existing or None,
                    "new": wiki_val if wiki_val else None,
                    "locked": True,
                })

    print("-" * 60)
    action = "Would tag" if dry_run else "Tagged"
    clear_action = "Would clear" if dry_run else "Cleared"
    summary_line = (
        f"{action}: {tagged}  |  {clear_action}: {cleared}  |  "
        f"Skipped: {skipped}  |  "
        f"Errors: {errors}"
    )
    if fetch_metadata and selected_tags & _METADATA_TAGS and any(
            album_info.get(k) for k in (
                "catalog_numbers", "date", "album", "album_artists", "genres"
            )):
        m_action = "Would write" if dry_run else "Wrote"
        summary_line += (
            f"  ||  {m_action} metadata: {meta_wrote} new, "
            f"{meta_skipped} skipped"
        )
    if fetch_credits and selected_tags & _CREDIT_TAGS:
        c_action = "Would write" if dry_run else "Wrote"
        summary_line += (
            f"  ||  {c_action} credits: {cred_wrote} new, "
            f"{cred_skipped} skipped"
        )
    if do_romanize:
        rm_action = "Would write" if dry_run else "Wrote"
        summary_line += (
            f"  ||  {rm_action} titlesort: "
            f"{romanized} new, {overwritten} overwritten  |  "
            f"RM-skipped: {rm_skipped}  |  RM-errors: {rm_errors}"
        )
    if (use_touhoudb and selected_tags & _ARTIST_TAGS
            and (artist_wrote or artist_skipped)):
        a_action = "Would write" if dry_run else "Wrote"
        summary_line += (
            f"  ||  {a_action} artist: {artist_wrote} new, "
            f"{artist_skipped} skipped"
        )
    if locked_skipped:
        summary_line += (
            f"  ||  Locked: {locked_skipped} tag(s) left untouched"
        )
    print(summary_line)
    if use_touhoudb:
        if missing_members:
            print(f"  Missing members ({len(missing_members)}): "
                  f"{', '.join(missing_members)}")
        if date_mismatch:
            print(f"  Release date mismatch — wiki: {date_mismatch[0]}  |  "
                  f"TouhouDB: {date_mismatch[1]}")
        if catalog_mismatch:
            print(f"  Catalog mismatch — wiki: {catalog_mismatch[0]}  |  "
                  f"TouhouDB: {catalog_mismatch[1]}")

    if title_discrepancies:
        kinds: dict[str, int] = {}
        for d in title_discrepancies:
            kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
        print("  Track discrepancies: "
              + ", ".join(f"{v} {k}" for k, v in kinds.items()))

    return {
        "album":       wiki_album,
        "music_dir":   music_dir,
        "source":      source_used,
        "tagged":      tagged,
        "skipped":     skipped,
        "cleared":     cleared,
        "errors":      errors,
        "romanized":   romanized,
        "overwritten": overwritten,
        "rm_skipped":  rm_skipped,
        "rm_no_title": rm_no_title,
        "rm_errors":   rm_errors,
        "meta_wrote":  meta_wrote,
        "meta_skipped": meta_skipped,
        "cred_wrote":  cred_wrote,
        "cred_skipped": cred_skipped,
        "artist_wrote":   artist_wrote,
        "artist_skipped": artist_skipped,
        "locked_skipped": locked_skipped,
        "missing_members": missing_members,
        "date_mismatch":   date_mismatch,
        "catalog_mismatch": catalog_mismatch,
        "tag_changes": tag_changes,
        "title_discrepancies": title_discrepancies,
        "severe_mismatch": severe_mismatch,
        "mismatch_skipped": False,
        "cancel_batch": False,
        "error":       None,
    }


def process_album(
    wiki_album: str,
    music_dir: str,
    *,
    dry_run: bool = False,
    thwiki_only: bool = False,
    mapping_path: str | None = None,
    romanize: bool = True,
    force_titlesort: bool = False,
    force_credits: bool = False,
    fetch_metadata: bool = True,
    fetch_credits: bool = True,
    use_touhoudb: bool = False,
    touhoudb_add_missing: bool = False,
    selected_tags=None,
    retry_case_variants: bool = False,
    on_confirm=None,
) -> dict:
    """Fetch, match, and tag a single album in one shot (fetch then tag).

    Thin back-compatible wrapper around :func:`fetch_album_plan` +
    :func:`tag_album_from_plan`, kept for any caller that wants the old
    one-call behaviour.  Batch callers should prefer :func:`process_albums`,
    which fetches every album first (while the THBWiki cookie is fresh) and
    only then tags — see that function and :class:`AlbumPlan`.

    Note: this wrapper does **not** do the up-front cookie validation;
    :func:`fetch_album_plan` will still raise ``ThwikiCookieError`` if the
    cookie is missing or stale.

    ``on_confirm`` is forwarded to :func:`tag_album_from_plan` for the
    severe-mismatch confirmation (see that function).

    Returns the per-album summary dict (see :func:`tag_album_from_plan`).
    """
    plan = fetch_album_plan(
        wiki_album, music_dir,
        dry_run=dry_run, thwiki_only=thwiki_only, mapping_path=mapping_path,
        romanize=romanize, force_titlesort=force_titlesort,
        force_credits=force_credits,
        fetch_metadata=fetch_metadata, fetch_credits=fetch_credits,
        use_touhoudb=use_touhoudb, touhoudb_add_missing=touhoudb_add_missing,
        selected_tags=selected_tags,
        retry_case_variants=retry_case_variants,
    )
    return tag_album_from_plan(plan, on_confirm=on_confirm)


def process_albums(
    album_pairs: "list[tuple[str, str] | tuple[str, str, bool]]",
    *,
    dry_run: bool = False,
    thwiki_only: bool = False,
    mapping_path: str | None = None,
    romanize: bool = True,
    force_titlesort: bool = False,
    force_credits: bool = False,
    fetch_metadata: bool = True,
    fetch_credits: bool = True,
    use_touhoudb: bool = False,
    touhoudb_add_missing: bool = False,
    selected_tags=None,
    validate_cookie: bool = True,
    on_result=None,
    on_plan=None,
    on_confirm=None,
    cancel_requested=None,
) -> list[dict]:
    """Tag a batch of albums in two phases: fetch everything, then tag.

    The THBWiki browser cookie is mandatory and can expire within the hour,
    so this:

      0. validates the cookie up front (unless ``validate_cookie`` is
         False — e.g. the caller already validated it);
      1. fetches *every* album's data into in-memory :class:`AlbumPlan`
         objects while the cookie is fresh;
      2. only then writes tags for every album, from the cached plans.

    Because all THBWiki network access happens in phase 1, the cookie can't
    go stale partway through the (offline) tagging in phase 2.  A
    ``ThwikiCookieError`` from phase 0 or phase 1 aborts the whole batch
    *before any file is touched* and propagates to the caller — no album is
    left half-tagged on a cookie failure.

    Each ``album_pairs`` item is ``(wiki_album, music_dir)`` or
    ``(wiki_album, music_dir, slug_is_auto)``.  When ``slug_is_auto`` is
    True (the slug was auto-suggested, not hand-edited — the GUI knows the
    difference), a slug that matches neither wiki is retried with its
    capitalization variants (see :func:`_slug_case_variants`); a plain pair
    is never retried.

    ``on_result`` (optional) is called with each album's summary dict as it
    finishes tagging, for live UI updates.  ``on_plan`` (optional) is called
    as ``on_plan(index, plan)`` after *each* album is fetched in phase 1
    (``index`` 0-based, ``plan`` an :class:`AlbumPlan` whose ``error`` is
    None on a successful fetch) — used to drive a per-album fetch status
    display.  ``cancel_requested`` (optional) is a zero-arg callable polled
    between albums in both phases; when it returns True the batch stops at
    the next boundary (in phase 1 that means nothing is tagged at all).

    Returns the list of per-album summary dicts (one per album actually
    tagged, in order).
    """
    opts = dict(
        dry_run=dry_run, thwiki_only=thwiki_only, mapping_path=mapping_path,
        romanize=romanize, force_titlesort=force_titlesort,
        force_credits=force_credits,
        fetch_metadata=fetch_metadata, fetch_credits=fetch_credits,
        use_touhoudb=use_touhoudb, touhoudb_add_missing=touhoudb_add_missing,
        selected_tags=selected_tags,
    )

    def _cancelled() -> bool:
        return bool(cancel_requested and cancel_requested())

    # --- Phase 0: mandatory cookie pre-flight ---
    if validate_cookie:
        validate_thwiki_cookie()  # raises ThwikiCookieError on failure

    # --- Phase 1: fetch every album up front (network) ---
    n = len(album_pairs)
    print(f"\n{'#' * 60}")
    print(f"Phase 1/2: fetching data for {n} album(s) from the wikis…")
    print("#" * 60)
    plans: list[AlbumPlan] = []
    for idx, pair in enumerate(album_pairs, 1):
        wiki_album, music_dir = pair[0], pair[1]
        slug_is_auto = bool(pair[2]) if len(pair) > 2 else False
        print(f"\n[fetch {idx}/{n}]")
        # A ThwikiCookieError here (cookie expired mid-batch) propagates and
        # aborts before phase 2, so nothing has been tagged yet.
        plans.append(fetch_album_plan(
            wiki_album, music_dir,
            retry_case_variants=slug_is_auto, **opts))
        if on_plan is not None:
            on_plan(idx - 1, plans[-1])
        if _cancelled():
            print("\nCancelled during fetch — no files were tagged.")
            return []

    # --- Phase 2: tag every album (local file I/O) ---
    print(f"\n{'#' * 60}")
    print(f"Phase 2/2: writing tags for {n} album(s)…")
    print("#" * 60)
    results: list[dict] = []
    for idx, plan in enumerate(plans, 1):
        print(f"\n[tag {idx}/{n}]")
        result = tag_album_from_plan(plan, on_confirm=on_confirm)
        results.append(result)
        if on_result is not None:
            on_result(result)
        # A "Cancel run" choice in the mismatch dialog aborts the whole batch.
        if result.get("cancel_batch"):
            print("\nCancelled from a confirmation dialog — remaining "
                  "albums were not tagged.")
            break
        if _cancelled():
            print("\nCancelled — remaining albums were not tagged.")
            break
    return results


# ---------------------------------------------------------------------------
# Main (dispatches between GUI and CLI)
# ---------------------------------------------------------------------------
def _force_utf8_io() -> None:
    """Make stdout/stderr use UTF-8 so the log glyphs (→, ✓, ⚠, …) don't crash
    on a non-UTF-8 console — notably Windows, whose default cp1252 code page
    cannot encode them (raises UnicodeEncodeError on the first such print)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # TextIOWrapper, Python 3.7+
        except (AttributeError, ValueError, OSError):
            # Not a reconfigurable text stream (redirected/captured/detached);
            # leave it as-is.
            pass


def main() -> None:
    _force_utf8_io()
    # If no arguments are provided, launch the GUI
    if len(sys.argv) == 1:
        from gui import gui_main
        gui_main()
        return

    parser = argparse.ArgumentParser(
        description="Tag Touhou remix albums with original theme names from the Touhou Wiki.",
        epilog=(
            "Run with no arguments to launch the GUI.\n"
            "Multiple albums can be processed in one invocation by "
            "supplying additional wiki_album/music_dir pairs, e.g.:\n"
            '  %(prog)s "Album_A" "path/to/A" '
            '"Album_B" "path/to/B" --dry-run'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "albums",
        nargs="+",
        metavar="wiki_album music_dir",
        help=(
            "Pairs of: wiki page name (URL slug) followed by the "
            "directory containing that album's music files"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be tagged without writing anything to disk",
    )
    parser.add_argument(
        "--thwiki-only",
        action="store_true",
        help="Skip the English Touhou Wiki and use THBWiki (thwiki.cc) directly",
    )
    parser.add_argument(
        "--mapping",
        default=None,
        help=(
            "Path to the theme mapping JSON file "
            "(default: touhou_theme_mapping.json next to this script)"
        ),
    )
    parser.add_argument(
        "--no-romanize",
        action="store_true",
        help=(
            "Don't romanise Japanese titles into the titlesort tag.  "
            "By default, when the japanese_romanizer module is "
            "importable and MeCab/UniDic are installed, every "
            "Japanese-titled track gets a Hepburn 'titlesort' written "
            "alongside the wiki-derived 'grouping' tag."
        ),
    )
    parser.add_argument(
        "--force-titlesort",
        action="store_true",
        help=(
            "Overwrite existing titlesort tags during romanisation.  "
            "Without this flag, files that already have a titlesort "
            "are skipped (the current and would-be values are shown)."
        ),
    )
    parser.add_argument(
        "--force-credits",
        action="store_true",
        help=(
            "Overwrite existing arranger/vocalist/lyricist tags with the "
            "wiki's credits.  Without this flag an existing credit is "
            "preserved, so a re-run cannot correct one written by an "
            "earlier release.  A credit the wiki already agrees with is "
            "left alone either way."
        ),
    )
    parser.add_argument(
        "--no-metadata",
        action="store_true",
        help=(
            "Don't fetch album metadata (catalog number, release date, "
            "year) from THBWiki.  By default, these are scraped from "
            "the album's info box and written to every file."
        ),
    )
    parser.add_argument(
        "--no-credits",
        action="store_true",
        help=(
            "Don't fetch per-track credits (arranger, vocalist, "
            "lyricist) from THBWiki.  By default, these are fetched "
            "from the asktrack API and written to each track."
        ),
    )
    parser.add_argument(
        "--touhoudb",
        action="store_true",
        help=(
            "Enable TouhouDB (touhoudb.com) as a verification source: "
            "checks the wiki's staff against TouhouDB, prefers TouhouDB "
            "official romanizations for the artist/artistsort/albumartist "
            "tags, and cross-checks the release date and catalog number "
            "(reporting any differences).  Off by default."
        ),
    )
    parser.add_argument(
        "--touhoudb-add-missing",
        action="store_true",
        help=(
            "When TouhouDB lists a staff member that the source wiki does "
            "not, add them to the per-track 'artist' field using TouhouDB's "
            "per-song credits (one extra rate-limited request per track).  "
            "Off by default; only meaningful together with --touhoudb."
        ),
    )
    args = parser.parse_args()

    # Positional args must come in pairs: wiki_album, music_dir
    if len(args.albums) % 2 != 0:
        parser.error(
            "Positional arguments must be wiki_album/music_dir pairs. "
            f"Got {len(args.albums)} argument(s) (expected an even number)."
        )

    album_pairs = [
        (args.albums[i], args.albums[i + 1])
        for i in range(0, len(args.albums), 2)
    ]

    # Two-phase batch: validate the (mandatory) THBWiki cookie, fetch every
    # album while it's fresh, then tag.  A cookie problem aborts before any
    # file is touched.
    try:
        results = process_albums(
            album_pairs,
            dry_run=args.dry_run,
            thwiki_only=args.thwiki_only,
            mapping_path=args.mapping,
            romanize=not args.no_romanize,
            force_titlesort=args.force_titlesort,
            force_credits=args.force_credits,
            fetch_metadata=not args.no_metadata,
            fetch_credits=not args.no_credits,
            use_touhoudb=args.touhoudb,
            touhoudb_add_missing=args.touhoudb_add_missing,
        )
    except ThwikiCookieError as exc:
        print(f"\nTHBWiki cookie error — aborted before tagging:\n  {exc}",
              file=sys.stderr)
        sys.exit(2)

    # --- Grand summary (only shown for multi-album runs) ---
    if len(album_pairs) > 1:
        print(f"\n{'=' * 60}")
        print("GRAND SUMMARY")
        print("=" * 60)
        total_tagged      = 0
        total_skipped     = 0
        total_cleared     = 0
        total_errors      = 0
        total_romanized   = 0
        total_overwritten = 0
        total_rm_skipped  = 0
        total_rm_errors   = 0
        total_meta_wrote  = 0
        total_meta_skipped = 0
        total_cred_wrote  = 0
        total_cred_skipped = 0
        total_locked      = 0
        failed            = []
        any_romanize = (
            not args.no_romanize and ROMANIZER_AVAILABLE
        )
        any_metadata = not args.no_metadata
        any_credits  = not args.no_credits

        for r in results:
            total_tagged      += r["tagged"]
            total_skipped     += r["skipped"]
            total_cleared     += r.get("cleared", 0)
            total_errors      += r["errors"]
            total_romanized   += r.get("romanized", 0)
            total_overwritten += r.get("overwritten", 0)
            total_rm_skipped  += r.get("rm_skipped", 0)
            total_rm_errors   += r.get("rm_errors", 0)
            total_meta_wrote  += r.get("meta_wrote", 0)
            total_meta_skipped += r.get("meta_skipped", 0)
            total_cred_wrote  += r.get("cred_wrote", 0)
            total_cred_skipped += r.get("cred_skipped", 0)
            total_locked      += r.get("locked_skipped", 0)
            if r["error"]:
                failed.append(r)
            else:
                src = r["source"] or "?"
                line = (
                    f"  ✓ {r['album']}  ({src})  — "
                    f"Tagged: {r['tagged']}  |  "
                    f"Cleared: {r.get('cleared', 0)}  |  "
                    f"Skipped: {r['skipped']}"
                )
                if any_romanize:
                    line += (
                        f"  ||  Romanised: {r.get('romanized', 0)}"
                    )
                    if r.get("overwritten", 0):
                        line += f" (+{r['overwritten']} overwritten)"
                print(line)

        for r in failed:
            print(f"  ✗ {r['album']}  — {r['error']}")

        print("-" * 60)
        action = "Would tag" if args.dry_run else "Tagged"
        clear_action = "Would clear" if args.dry_run else "Cleared"
        line = (
            f"{action}: {total_tagged}  |  "
            f"{clear_action}: {total_cleared}  |  "
            f"Skipped: {total_skipped}  |  "
            f"Errors: {total_errors}  |  "
            f"Failed albums: {len(failed)}"
        )
        print(line)
        if any_metadata and (total_meta_wrote or total_meta_skipped):
            m_action = "Would write" if args.dry_run else "Wrote"
            print(
                f"{m_action} metadata: "
                f"{total_meta_wrote} new, "
                f"{total_meta_skipped} skipped"
            )
        if any_credits and (total_cred_wrote or total_cred_skipped):
            c_action = "Would write" if args.dry_run else "Wrote"
            print(
                f"{c_action} credits: "
                f"{total_cred_wrote} new, "
                f"{total_cred_skipped} skipped"
            )
        if total_locked:
            print(
                f"Locked: {total_locked} tag(s) left untouched "
                f"(edited by hand in the Tag Edit tab)"
            )
        if any_romanize:
            rm_action = "Would write" if args.dry_run else "Wrote"
            print(
                f"{rm_action} titlesort: "
                f"{total_romanized} new, "
                f"{total_overwritten} overwritten  |  "
                f"RM-skipped: {total_rm_skipped}  |  "
                f"RM-errors: {total_rm_errors}"
            )
        if args.touhoudb:
            total_artist_wrote = sum(
                r.get("artist_wrote", 0) for r in results)
            total_artist_skipped = sum(
                r.get("artist_skipped", 0) for r in results)
            a_action = "Would write" if args.dry_run else "Wrote"
            print(
                f"{a_action} artist: {total_artist_wrote} new, "
                f"{total_artist_skipped} skipped"
            )
            flagged = [
                r for r in results
                if r.get("missing_members")
                or r.get("date_mismatch")
                or r.get("catalog_mismatch")
            ]
            if flagged:
                print("TouhouDB flags:")
                for r in flagged:
                    if r.get("missing_members"):
                        print(f"  • {r['album']}: missing members — "
                              f"{', '.join(r['missing_members'])}")
                    if r.get("date_mismatch"):
                        d = r["date_mismatch"]
                        print(f"  • {r['album']}: date wiki={d[0]} "
                              f"TouhouDB={d[1]}")
                    if r.get("catalog_mismatch"):
                        c = r["catalog_mismatch"]
                        print(f"  • {r['album']}: catalog wiki={c[0]} "
                              f"TouhouDB={c[1]}")

        skipped_mm = [r for r in results if r.get("mismatch_skipped")]
        if skipped_mm:
            print("Skipped (severe track mismatch — not tagged):")
            for r in skipped_mm:
                print(f"  • {r['album']}  ({r['music_dir']})")
        flagged_disc = [
            r for r in results
            if r.get("title_discrepancies") and not r.get("mismatch_skipped")
        ]
        if flagged_disc:
            print("Track discrepancies:")
            for r in flagged_disc:
                kinds: dict[str, int] = {}
                for d in r["title_discrepancies"]:
                    kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
                print(f"  • {r['album']}: "
                      + ", ".join(f"{v} {k}" for k, v in kinds.items()))

        if args.dry_run:
            print("\nRe-run without --dry-run to apply changes.")

if __name__ == "__main__":
    main()
