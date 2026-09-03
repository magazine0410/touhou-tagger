"""
file_scan.py — Scan local directories for music files, detect album
folder structures, guess wiki slugs from file tags, and read existing
tags for the GUI tree view.
"""
import os
import re

import mutagen

from tag_io import read_grouping

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".ogg", ".m4a", ".opus"}
# Matches disc subdirectory names: "Disc 1", "DISC 01", "disc2", "CD1",
# "Disk1(第一部)", "CD 02 - Bonus", etc.  Accepts "disc", "disk", and "cd"
# prefixes (case-insensitive) followed by a disc number, with optional
# trailing text (parenthesized subtitles, dash-separated labels, etc.).
DISC_DIR_RE = re.compile(r"(?i)^(?:disc|disk|cd)\s*(\d+).*$")


def album_dir_for_file(path: str) -> str:
    """The album folder that owns the music file at *path*.

    A file inside a ``Disc N`` subfolder belongs to the album one level up.
    Scanning the disc folder on its own would find no disc subdirectories and
    number every track as disc 1, so a caller resolving a dropped file by
    ``os.path.dirname`` alone would build a second, wrongly numbered album
    beside the real one.  Matches on :data:`DISC_DIR_RE`, the same regex
    :func:`scan_music_files` uses, so the two cannot disagree.
    """
    parent = os.path.dirname(os.path.abspath(path))
    if DISC_DIR_RE.match(os.path.basename(parent)):
        grandparent = os.path.dirname(parent)
        if grandparent and grandparent != parent:
            return grandparent
    return parent


# ---------------------------------------------------------------------------
# Local file scanning
# ---------------------------------------------------------------------------
def _scan_single_dir(directory: str, disc: int) -> list[dict]:
    """
    Scan a single directory for supported music files and read their tags.
    Returns a list of file dicts with the given disc number.
    """
    files = []
    for fname in sorted(os.listdir(directory)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        fpath = os.path.join(directory, fname)
        number = None
        title = None

        # Try reading tags first
        try:
            f = mutagen.File(fpath, easy=True)
            if f:
                tracknumber = f.get("tracknumber", [None])[0]
                if tracknumber:
                    # tracknumber may be "2/10" format
                    number = int(str(tracknumber).split("/")[0])
                title_val = f.get("title", [None])[0]
                if title_val:
                    title = str(title_val).strip()
        except Exception:
            pass

        # Fallback: extract leading digits from filename
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
    """
    Scan a directory for supported music files and read their tags.
    If the directory contains disc subdirectories (e.g. "Disc 1", "DISC 01",
    "disc2"), each subdirectory is scanned separately and files are tagged
    with the corresponding disc number.  Otherwise the directory is scanned
    as a single-disc album (disc = 1).
    Returns a list of file dicts:
    {
        "path":     str,
        "filename": str,
        "disc":     int,
        "number":   int or None,
        "title":    str or None,
    }
    """
    # Check for disc subdirectories
    disc_dirs: list[tuple[int, str]] = []
    for entry in sorted(os.listdir(directory)):
        entry_path = os.path.join(directory, entry)
        if not os.path.isdir(entry_path):
            continue
        m = DISC_DIR_RE.match(entry)
        if m:
            disc_dirs.append((int(m.group(1)), entry_path))

    if disc_dirs:
        # Multi-disc: scan each disc subdirectory
        disc_dirs.sort(key=lambda x: x[0])
        files: list[dict] = []
        for disc_num, disc_path in disc_dirs:
            files.extend(_scan_single_dir(disc_path, disc=disc_num))
        return files

    # Single-disc: scan the directory directly
    return _scan_single_dir(directory, disc=1)


# ---------------------------------------------------------------------------
# Album slug auto-detection
# ---------------------------------------------------------------------------
# Matches the leading date stamp in folder names like
# "2022.08.14_[EUCD-0022]_ALBUM_NAME_[C100]".  Accepts YYYY.MM.DD,
# YYYY-MM-DD, and YYYYMMDD, with an optional trailing separator.
_FOLDER_DATE_RE = re.compile(
    r'^\d{4}[.\-]?\d{2}[.\-]?\d{2}[_\s]*'
)
# Matches bracketed metadata segments: [EUCD-0022], [C100], [M3-49],
# [例大祭19], etc.  These are catalog IDs, event tags, or other
# annotations that never appear in wiki page URLs.
_FOLDER_BRACKET_RE = re.compile(
    r'[_\s]*\[[^\]]*\][_\s]*'
)


def _clean_folder_slug(basename: str) -> str:
    """Strip common folder-naming decorations from an album basename.

    Many Touhou music collections follow a naming convention like::

        2022.08.14_[EUCD-0022]_EURO_BAKAICHIDAI_VOL.22_[C100]

    This strips:

    - Leading date stamps (``YYYY.MM.DD``, ``YYYY-MM-DD``, ``YYYYMMDD``)
    - Bracketed metadata segments (``[CATALOG]``, ``[EVENT]``, etc.)
    - Residual leading/trailing/double underscores

    Returns the cleaned string, or *basename* unchanged if stripping
    would leave nothing useful.
    """
    slug = _FOLDER_DATE_RE.sub('', basename)
    slug = _FOLDER_BRACKET_RE.sub('_', slug)
    slug = re.sub(r'_+', '_', slug).strip('_ ')
    return slug if slug else basename


def guess_album_slug(directory: str) -> str:
    """
    Read the `album` tag from the first supported music file in
    `directory` and return it as a wiki URL slug (spaces → underscores).
    Falls back to the directory's basename — with date stamps and
    bracketed metadata stripped — if no album tag is found.
    """
    for fname in sorted(os.listdir(directory)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        try:
            f = mutagen.File(os.path.join(directory, fname), easy=True)
            if f:
                album_val = f.get("album", [None])[0]
                if album_val:
                    return str(album_val).strip().replace(" ", "_")
        except Exception:
            pass
    basename = os.path.basename(directory)
    return _clean_folder_slug(basename).replace(" ", "_")


# Matches an artist/circle folder name that is wholly wrapped in a single
# bracket pair, e.g. "[ShibayanRecords]" -> "ShibayanRecords".  Used by the
# path fallback in :func:`guess_album_artist`.
_ARTIST_BRACKET_RE = re.compile(r'^\[(.+)\]$')


def _strip_artist_brackets(name: str) -> str:
    """Strip the surrounding brackets from a wrapped artist folder name.

    Some ``<library>/<artist>/<album>`` collections wrap artist/circle
    folders in brackets (``[ShibayanRecords]``).  Returns the inner text when
    the whole name is one bracket pair, otherwise the name unchanged.
    """
    name = name.strip()
    m = _ARTIST_BRACKET_RE.match(name)
    return m.group(1).strip() if m else name


def guess_album_artist(directory: str) -> str:
    """Best-effort album artist / circle name for an album folder.

    Prefers the ``albumartist`` tag of the first supported music file in
    *directory* (mirroring :func:`guess_album_slug`'s tag-first approach).
    Falls back to the parent folder's name — the ``<artist>`` level of a
    ``<library>/<artist>/<album>`` layout — with optional surrounding
    brackets stripped off (``[ShibayanRecords]`` -> ``ShibayanRecords``).

    Returns an empty string only if neither source yields a name.
    """
    for fname in sorted(os.listdir(directory)):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue
        try:
            f = mutagen.File(os.path.join(directory, fname), easy=True)
            if f:
                val = f.get("albumartist", [None])[0]
                if val and str(val).strip():
                    return str(val).strip()
        except Exception:
            pass
    parent = os.path.basename(os.path.dirname(os.path.normpath(directory)))
    return _strip_artist_brackets(parent)


# ---------------------------------------------------------------------------
# Folder classification (used by the GUI to expand `[Artist]` containers
# into their album subfolders on drop / Add Folders…)
# ---------------------------------------------------------------------------
def _is_album_dir(path: str) -> bool:
    """Return True if ``path`` looks like an album folder.

    A directory qualifies as an album if it contains at least one
    supported audio file directly, or if it has at least one disc
    subdirectory (matching ``DISC_DIR_RE``, e.g. ``Disc 1`` / ``CD2``)
    that itself contains audio.  Anything else — empty folders, folders
    with only non-audio files, folders whose only children are other
    container folders — is treated as a non-album.
    """
    if not os.path.isdir(path):
        return False
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    # Audio file directly inside → it's an album.
    for name in entries:
        full = os.path.join(path, name)
        if os.path.isfile(full):
            ext = os.path.splitext(name)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                return True
    # Disc subdirectory with audio inside → also an album.
    for name in entries:
        full = os.path.join(path, name)
        if os.path.isdir(full) and DISC_DIR_RE.match(name):
            try:
                inner_entries = os.listdir(full)
            except OSError:
                continue
            for inner in inner_entries:
                inner_full = os.path.join(full, inner)
                if os.path.isfile(inner_full):
                    ext = os.path.splitext(inner)[1].lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        return True
    return False


def _expand_to_album_dirs(path: str, max_depth: int = 1) -> list[str]:
    """Resolve a dropped/picked folder into one or more album folders.

    If ``path`` itself looks like an album (per :func:`_is_album_dir`),
    returns ``[path]`` unchanged.  Otherwise treats ``path`` as a
    container — typically an ``[Artist]`` folder — and returns every
    immediate subdirectory that looks like an album.  ``max_depth`` controls
    how many container levels may be searched; the default of one preserves
    the historical ``[Artist]/Album/...`` behavior while the GUI can opt into
    two or three levels for deeper libraries.

    If the folder isn't an album and has no album-like children, the
    original path is returned in a single-element list so the caller's
    existing duplicate-detection / fallback behaviour still applies and
    the unexpected drop remains visible to the user.
    """
    if not os.path.isdir(path):
        return [path]
    if _is_album_dir(path):
        return [path]
    max_depth = max(1, int(max_depth))

    def _walk(container: str, remaining: int) -> list[str]:
        try:
            entries = sorted(os.listdir(container))
        except OSError:
            return []
        children = [
            os.path.join(container, name) for name in entries
            if os.path.isdir(os.path.join(container, name))
        ]
        album_children = [d for d in children if _is_album_dir(d)]
        if album_children or remaining <= 1:
            return album_children
        found: list[str] = []
        for child in children:
            found.extend(_walk(child, remaining - 1))
        return found

    album_children = _walk(path, max_depth)
    if album_children:
        return album_children
    return [path]


# ---------------------------------------------------------------------------
# Reading existing tags (used by the GUI tree view to show what's already
# on disk before tagging — both before and after a run).
# ---------------------------------------------------------------------------
def scan_album_for_view(directory: str) -> list[dict]:
    """Like :func:`scan_music_files` but also reads each track's existing
    ``grouping`` tag.

    Used by the GUI tree view when an album folder is added, and again
    after tagging completes to refresh the displayed values.  Returns
    one dict per track in disc/track order::

        {"path", "filename", "disc", "number", "title", "grouping"}

    where ``title`` and ``grouping`` may be None.
    """
    tracks = scan_music_files(directory)
    for t in tracks:
        t["grouping"] = read_grouping(t["path"])
    return tracks


def _format_track_label(t: dict, multi_disc: bool) -> str:
    """Display label for a track row in the GUI tree view.

    Pads the track number to two digits so that lexicographic sort
    (which QTreeWidget uses on the column-0 string) matches numeric
    order.  For multi-disc albums the disc number is prefixed, again
    so that sort order matches "disc 1 first, then disc 2".
    """
    num = t.get("number")
    title = t.get("title") or t.get("filename") or "?"
    num_str = f"{num:02d}" if isinstance(num, int) else "??"
    if multi_disc:
        disc = t.get("disc") or 1
        return f"{disc}-{num_str}. {title}"
    return f"{num_str}. {title}"


def _format_track_number(t: dict, multi_disc: bool) -> str:
    """Display label for the track-number-only column.

    Same numbering scheme as :func:`_format_track_label` (zero-padded,
    disc-prefixed for multi-disc albums so lexicographic sort matches
    numeric order) but without the title — used by the Tag Edit tab,
    which has its own editable Title column.
    """
    num = t.get("number")
    num_str = f"{num:02d}" if isinstance(num, int) else "??"
    if multi_disc:
        disc = t.get("disc") or 1
        return f"{disc}-{num_str}"
    return num_str
