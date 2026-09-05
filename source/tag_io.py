"""
tag_io.py — Read and write audio tags across MP3, FLAC, OGG, Opus, and M4A.

Provides format-agnostic functions for reading/writing individual tags
(grouping, catalognumber, arranger, etc.), plus the CJK/Latin script
detection used by the albumartist write policy.
"""
import os
import re

import mutagen
from mutagen.id3 import (
    ID3, TIT1, TIT2, TSOT, TXXX, TDRC, TCON, TALB, TPE1, TPE2, TSOP, TSO2,
    ID3NoHeaderError,
)
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus


# ---------------------------------------------------------------------------
# CJK / Latin script detection
# ---------------------------------------------------------------------------
# Matches any Japanese/Chinese (CJK) character.  Used to decide whether an
# existing albumartist tag is already romanised (Latin) or still in its
# original Japanese/Chinese form, so that hand-romanised values aren't
# clobbered.  The ranges cover Hiragana, Katakana (incl. halfwidth),
# CJK Unified Ideographs (incl. extension A), and CJK Compatibility
# Ideographs — enough for any Touhou doujin context.
_CJK_RE = re.compile(
    '['
    '\u3040-\u309F'    # Hiragana
    '\u30A0-\u30FF'    # Katakana
    '\u3400-\u4DBF'    # CJK Unified Ideographs Extension A
    '\u4E00-\u9FFF'    # CJK Unified Ideographs
    '\uF900-\uFAFF'    # CJK Compatibility Ideographs
    '\uFF66-\uFF9F'    # Halfwidth Katakana
    ']'
)


def _is_latin_script(text: str) -> bool:
    """Return True when ``text`` contains no CJK characters.

    Punctuation, ASCII letters, digits, accented Latin characters, etc.
    all count as Latin script.  An empty or whitespace-only string is
    treated as Latin (it carries no script information either way).
    """
    return _CJK_RE.search(text) is None


# ---------------------------------------------------------------------------
# Tag name mapping (internal name → format-specific keys)
# ---------------------------------------------------------------------------
# Maps our logical tag names to the keys used by each audio format.
# Vorbis comments (FLAC/OGG/Opus) use the tag name directly.
# ID3 (MP3) uses frame IDs — "TXXX:DESC" for custom text frames.
# M4A uses MP4 atom keys — "----:com.apple.iTunes:NAME" for freeform.
_TAG_MAP_ID3: dict[str, str] = {
    "grouping":        "TIT1",
    "title":           "TIT2",
    "titlesort":       "TSOT",
    "catalognumber":   "TXXX:CATALOGNUMBER",
    "date":            "TDRC",
    "year":            "TXXX:YEAR",
    "arranger":        "TXXX:ARRANGER",
    "lyricist":        "TXXX:LYRICIST",
    "vocalist":        "TXXX:VOCALIST",
    "album":           "TALB",
    "artist":          "TPE1",
    "artistsort":      "TSOP",
    "albumartist":     "TPE2",
    "albumartistsort": "TSO2",
    "genre":           "TCON",
}
_TAG_MAP_M4A: dict[str, str] = {
    "grouping":        "----:com.apple.iTunes:GROUPING",
    "title":           "\xa9nam",
    "titlesort":       "sonm",
    "catalognumber":   "----:com.apple.iTunes:CATALOGNUMBER",
    "date":            "\xa9day",
    "year":            "----:com.apple.iTunes:YEAR",
    "arranger":        "----:com.apple.iTunes:ARRANGER",
    "lyricist":        "----:com.apple.iTunes:LYRICIST",
    "vocalist":        "----:com.apple.iTunes:VOCALIST",
    "album":           "\xa9alb",
    "artist":          "\xa9ART",
    "artistsort":      "soar",
    "albumartist":     "aART",
    "albumartistsort": "soaa",
    "genre":           "\xa9gen",
}


# The tag fields exposed by the Tag Edit GUI tab, in display order.
# Album-level fields first (grouping, album, then the artist/album-artist
# cluster), then the per-track title/titlesort pair, then credits and
# catalog info.  The artist columns precede title/titlesort because it
# reads more naturally to see who made the track before its name.
EDITABLE_TAGS: list[str] = [
    "grouping", "album",
    "artist", "artistsort", "albumartist", "albumartistsort",
    "title", "titlesort",
    "arranger", "vocalist", "lyricist",
    "catalognumber", "date", "year",
]


# ---------------------------------------------------------------------------
# Tag reading
# ---------------------------------------------------------------------------
def read_all_tags(filepath: str) -> dict[str, str | None]:
    """Read every tag in :data:`EDITABLE_TAGS` from *filepath* in a
    single ``mutagen.File`` open.

    Returns a dict mapping each tag name to its string value (or
    ``None`` when the tag is absent or empty).  Used by the Tag Edit
    GUI tab to populate its table without opening the file N times.
    """
    result: dict[str, str | None] = {t: None for t in EDITABLE_TAGS}
    ext = os.path.splitext(filepath)[1].lower()
    try:
        f = mutagen.File(filepath)
        if f is None or f.tags is None:
            return result

        for tag_name in EDITABLE_TAGS:
            if ext in (".flac", ".ogg", ".opus"):
                vals = f.tags.get(tag_name)
                if vals:
                    result[tag_name] = str(vals[0]).strip() or None

            elif ext == ".mp3":
                frame_id = _TAG_MAP_ID3.get(tag_name)
                if not frame_id:
                    continue
                if frame_id.startswith("TXXX:"):
                    desc = frame_id[5:]
                    for frame in f.tags.getall("TXXX"):
                        if frame.desc == desc and frame.text:
                            result[tag_name] = str(
                                frame.text[0]
                            ).strip() or None
                            break
                else:
                    frame = f.tags.get(frame_id)
                    if frame and frame.text:
                        result[tag_name] = str(
                            frame.text[0]
                        ).strip() or None

            elif ext == ".m4a":
                key = _TAG_MAP_M4A.get(tag_name)
                if not key:
                    continue
                vals = f.tags.get(key)
                if vals:
                    v = vals[0]
                    s = (v.decode("utf-8") if isinstance(v, bytes)
                         else str(v))
                    result[tag_name] = s.strip() or None

    except Exception:
        pass
    return result


# Every editable field, read by the library scan in one mutagen open to tell
# which fetched fields an album is missing.
_STATS_FIELDS: list[str] = list(EDITABLE_TAGS)


def read_stats_fields(filepath: str) -> dict:
    """Read every :data:`EDITABLE_TAGS` field, plus duration/genres, in one open.

    Same single-``mutagen.File`` pattern as :func:`read_all_tags`, but also
    returns the audio duration.  Used by the library statistics scan, which
    needs the fetched fields (to flag which ones an album is missing) and the
    duration (for the per-theme longest/shortest track lists) together,
    without a second open per file.
    Each tag value is the stripped string or ``None`` when absent/empty;
    ``"length"`` is the duration in seconds as a float, or ``None`` when the
    stream info is unavailable; ``"genres"`` is the multi-value ``genre`` tag
    as a list (same per-format semantics as :func:`read_genres`, ``[]`` when
    absent) — it feeds the Statistics tab's genre-popularity chart.
    """
    result: dict = {t: None for t in _STATS_FIELDS}
    result["length"] = None
    result["genres"] = []
    ext = os.path.splitext(filepath)[1].lower()
    try:
        f = mutagen.File(filepath)
        if f is None:
            return result
        # Duration comes from the stream info, which exists even on files
        # with no tags at all — capture it before the tags check.
        length = getattr(getattr(f, "info", None), "length", None)
        if isinstance(length, (int, float)) and length > 0:
            result["length"] = float(length)
        if f.tags is None:
            return result

        for tag_name in _STATS_FIELDS:
            if ext in (".flac", ".ogg", ".opus"):
                vals = f.tags.get(tag_name)
                if vals:
                    result[tag_name] = str(vals[0]).strip() or None

            elif ext == ".mp3":
                frame_id = _TAG_MAP_ID3.get(tag_name)
                if not frame_id:
                    continue
                if frame_id.startswith("TXXX:"):
                    desc = frame_id[5:]
                    for frame in f.tags.getall("TXXX"):
                        if frame.desc == desc and frame.text:
                            result[tag_name] = str(
                                frame.text[0]
                            ).strip() or None
                            break
                else:
                    frame = f.tags.get(frame_id)
                    if frame and frame.text:
                        result[tag_name] = str(
                            frame.text[0]
                        ).strip() or None

            elif ext == ".m4a":
                key = _TAG_MAP_M4A.get(tag_name)
                if not key:
                    continue
                vals = f.tags.get(key)
                if vals:
                    v = vals[0]
                    s = (v.decode("utf-8") if isinstance(v, bytes)
                         else str(v))
                    result[tag_name] = s.strip() or None

        # Multi-value genre read, in the same open (mirrors read_genres —
        # genre isn't in _STATS_FIELDS because the single-value loop above
        # would keep only the first of a multi-genre field).
        genres: list[str] = []
        if ext in (".flac", ".ogg", ".opus"):
            for v in f.tags.get("genre", []):
                s = str(v).strip()
                if s:
                    genres.append(s)
        elif ext == ".mp3":
            for frame in f.tags.getall("TCON"):
                for v in frame.text:
                    s = str(v).strip()
                    if s:
                        genres.append(s)
        elif ext == ".m4a":
            for v in f.tags.get("\xa9gen", []):
                s = (v.decode("utf-8") if isinstance(v, bytes)
                     else str(v)).strip()
                if s:
                    genres.append(s)
        result["genres"] = genres

    except Exception:
        pass
    return result


def _get_existing_tag(filepath: str, tag_name: str) -> str | None:
    """
    Read a single tag value from a file.

    ``tag_name`` is the Vorbis comment name (e.g. "catalognumber",
    "arranger").  The function translates it to the appropriate frame
    ID / atom key for MP3 and M4A files.

    Returns the string value, or None if the tag is absent or empty.
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        f = mutagen.File(filepath)
        if f is None or f.tags is None:
            return None

        if ext in (".flac", ".ogg", ".opus"):
            vals = f.tags.get(tag_name)
            return str(vals[0]).strip() if vals else None

        elif ext == ".mp3":
            frame_id = _TAG_MAP_ID3.get(tag_name)
            if not frame_id:
                return None
            if frame_id.startswith("TXXX:"):
                desc = frame_id[5:]
                for frame in f.tags.getall("TXXX"):
                    if frame.desc == desc and frame.text:
                        return str(frame.text[0]).strip()
            else:
                frame = f.tags.get(frame_id)
                if frame and frame.text:
                    return str(frame.text[0]).strip()
            return None

        elif ext == ".m4a":
            key = _TAG_MAP_M4A.get(tag_name)
            if not key:
                return None
            vals = f.tags.get(key)
            if vals:
                v = vals[0]
                s = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                return s.strip() if s else None
            return None
    except Exception:
        return None
    return None


def read_grouping(filepath: str) -> str | None:
    """Return the existing 'grouping' tag value of a file, or None.

    Mirrors :func:`set_grouping` format-by-format so the value we
    surface in the GUI is the same one set_grouping would overwrite.
    Failures (corrupt headers, missing tags, unsupported extensions)
    yield None silently — the caller treats that as "no grouping".
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == ".mp3":
            try:
                tags = ID3(filepath)
            except ID3NoHeaderError:
                return None
            frame = tags.get("TIT1")
            if frame is None:
                return None
            text = "".join(frame.text).strip()
            return text or None
        elif ext == ".flac":
            vals = FLAC(filepath).get("grouping")
            return (str(vals[0]).strip() or None) if vals else None
        elif ext == ".ogg":
            vals = OggVorbis(filepath).get("grouping")
            return (str(vals[0]).strip() or None) if vals else None
        elif ext == ".opus":
            vals = OggOpus(filepath).get("grouping")
            return (str(vals[0]).strip() or None) if vals else None
        elif ext == ".m4a":
            vals = MP4(filepath).get("----:com.apple.iTunes:GROUPING")
            if not vals:
                return None
            raw = vals[0]
            if isinstance(raw, bytes):
                return raw.decode("utf-8", errors="replace").strip() or None
            return str(raw).strip() or None
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Tag writing
# ---------------------------------------------------------------------------
def set_grouping(filepath: str, value: str, dry_run: bool = False) -> None:
    """Write `value` to the grouping tag of the file at `filepath`."""
    if dry_run:
        return

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        tags["TIT1"] = TIT1(encoding=3, text=value)
        tags.save(filepath)
    elif ext == ".flac":
        f = FLAC(filepath)
        f["grouping"] = value
        f.save()
    elif ext == ".ogg":
        f = OggVorbis(filepath)
        f["grouping"] = value
        f.save()
    elif ext == ".opus":
        f = OggOpus(filepath)
        f["grouping"] = value
        f.save()
    elif ext == ".m4a":
        f = MP4(filepath)
        f["----:com.apple.iTunes:GROUPING"] = value.encode("utf-8")
        f.save()


def clear_grouping(filepath: str, dry_run: bool = False) -> None:
    """Remove the grouping tag from the file at `filepath`.

    Used when a re-scan identifies a track as an original composition
    but the file already carries a stale grouping value from an earlier
    (possibly incorrect) tagging run.  Does nothing if the file has no
    grouping tag or if the format is unsupported.

    A failure to write the file is raised, not swallowed — the caller
    counts it as an error rather than reporting a cleared tag that is
    still on disk.
    """
    if dry_run:
        return

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            return
        if "TIT1" in tags:
            del tags["TIT1"]
            tags.save(filepath)
    elif ext == ".flac":
        f = FLAC(filepath)
        if "grouping" in f:
            del f["grouping"]
            f.save()
    elif ext == ".ogg":
        f = OggVorbis(filepath)
        if "grouping" in f:
            del f["grouping"]
            f.save()
    elif ext == ".opus":
        f = OggOpus(filepath)
        if "grouping" in f:
            del f["grouping"]
            f.save()
    elif ext == ".m4a":
        f = MP4(filepath)
        key = "----:com.apple.iTunes:GROUPING"
        if key in f:
            del f[key]
            f.save()


def _set_tag(
    filepath: str,
    tag_name: str,
    value: str,
    dry_run: bool = False,
) -> None:
    """
    Write a single tag value to a file.

    ``tag_name`` is the Vorbis comment name; it is translated to the
    appropriate frame/atom key for MP3 and M4A.
    """
    if dry_run:
        return

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        frame_id = _TAG_MAP_ID3.get(tag_name)
        if not frame_id:
            return
        if frame_id.startswith("TXXX:"):
            desc = frame_id[5:]
            tags.add(TXXX(encoding=3, desc=desc, text=[value]))
        elif frame_id == "TIT1":
            tags.add(TIT1(encoding=3, text=[value]))
        elif frame_id == "TIT2":
            tags.add(TIT2(encoding=3, text=[value]))
        elif frame_id == "TSOT":
            tags.add(TSOT(encoding=3, text=[value]))
        elif frame_id == "TDRC":
            tags.add(TDRC(encoding=3, text=[value]))
        elif frame_id == "TCON":
            tags.add(TCON(encoding=3, text=[value]))
        elif frame_id == "TALB":
            tags.add(TALB(encoding=3, text=[value]))
        elif frame_id == "TPE1":
            tags.add(TPE1(encoding=3, text=[value]))
        elif frame_id == "TSOP":
            tags.add(TSOP(encoding=3, text=[value]))
        elif frame_id == "TPE2":
            tags.add(TPE2(encoding=3, text=[value]))
        elif frame_id == "TSO2":
            tags.add(TSO2(encoding=3, text=[value]))
        tags.save(filepath)
    elif ext in (".flac", ".ogg", ".opus"):
        if ext == ".flac":
            f = FLAC(filepath)
        elif ext == ".ogg":
            f = OggVorbis(filepath)
        else:
            f = OggOpus(filepath)
        f[tag_name] = value
        f.save()
    elif ext == ".m4a":
        f = MP4(filepath)
        key = _TAG_MAP_M4A.get(tag_name)
        if not key:
            return
        if key.startswith("----:"):
            f[key] = [value.encode("utf-8")]
        else:
            f[key] = [value]
        f.save()


def read_genres(filepath: str) -> list[str]:
    """Read every ``genre`` value from a file as a list.

    The multi-value counterpart to :func:`set_genres`: returns one entry
    per genre — every ``genre=`` Vorbis comment on FLAC/OGG/Opus, every
    text value of the MP3 ``TCON`` frame, every value of the M4A ``©gen``
    atom.  Empty/whitespace values are dropped; order is preserved.
    Returns ``[]`` when the tag is absent or the file can't be read.
    """
    ext = os.path.splitext(filepath)[1].lower()
    out: list[str] = []
    try:
        f = mutagen.File(filepath)
        if f is None or f.tags is None:
            return out

        if ext in (".flac", ".ogg", ".opus"):
            for v in f.tags.get("genre", []):
                s = str(v).strip()
                if s:
                    out.append(s)
        elif ext == ".mp3":
            for frame in f.tags.getall("TCON"):
                for v in frame.text:
                    s = str(v).strip()
                    if s:
                        out.append(s)
        elif ext == ".m4a":
            for v in f.tags.get("\xa9gen", []):
                s = (v.decode("utf-8") if isinstance(v, bytes)
                     else str(v)).strip()
                if s:
                    out.append(s)
    except Exception:
        return out
    return out


def set_genres(
    filepath: str,
    values: list[str],
    dry_run: bool = False,
) -> None:
    """
    Write the ``genre`` tag as a proper multi-value field.

    Vorbis comments (FLAC/OGG/Opus) get one ``genre=`` field per entry —
    the convention the Vorbis-comment spec (and players like Quod Libet)
    expect for multiple genres, rather than a single joined string.  MP3
    gets one ``TCON`` frame with multiple text values (mutagen emits the
    ID3v2.4 null-separated form), and M4A one ``\xa9gen`` atom with
    multiple values.  Replaces any existing genre value(s) — callers
    enforce their own skip-if-present policy before calling.
    """
    if dry_run or not values:
        return

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            tags = ID3()
        tags.add(TCON(encoding=3, text=list(values)))
        tags.save(filepath)
    elif ext in (".flac", ".ogg", ".opus"):
        if ext == ".flac":
            f = FLAC(filepath)
        elif ext == ".ogg":
            f = OggVorbis(filepath)
        else:
            f = OggOpus(filepath)
        f["genre"] = list(values)
        f.save()
    elif ext == ".m4a":
        f = MP4(filepath)
        f["\xa9gen"] = list(values)
        f.save()


def _delete_tag(
    filepath: str,
    tag_name: str,
    dry_run: bool = False,
) -> bool:
    """Remove a single tag from a file.  Returns True if a value was removed.

    ``tag_name`` is the Vorbis comment name; it is translated to the
    appropriate frame/atom key for MP3 and M4A.  Returns False (no removal
    needed) for an unsupported format, an unmapped tag name, or a tag the
    file doesn't carry.

    A failure to *write* the file — a read-only file, a full disk, a
    corrupt header — is raised, not swallowed: the caller has to be able to
    tell "there was nothing to remove" from "the removal did not happen",
    or it reports a cleared tag that is still on disk.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".mp3":
        try:
            tags = ID3(filepath)
        except ID3NoHeaderError:
            return False
        frame_id = _TAG_MAP_ID3.get(tag_name)
        if not frame_id:
            return False
        removed = False
        if frame_id.startswith("TXXX:"):
            desc = frame_id[5:]
            for frame in list(tags.getall("TXXX")):
                if frame.desc == desc:
                    if not dry_run:
                        tags.delall(f"TXXX:{desc}")
                    removed = True
                    break
        elif frame_id in tags:
            if not dry_run:
                del tags[frame_id]
            removed = True
        if removed and not dry_run:
            tags.save(filepath)
        return removed
    elif ext in (".flac", ".ogg", ".opus"):
        if ext == ".flac":
            f = FLAC(filepath)
        elif ext == ".ogg":
            f = OggVorbis(filepath)
        else:
            f = OggOpus(filepath)
        if tag_name in f:
            if not dry_run:
                del f[tag_name]
                f.save()
            return True
        return False
    elif ext == ".m4a":
        f = MP4(filepath)
        key = _TAG_MAP_M4A.get(tag_name)
        if key and key in f:
            if not dry_run:
                del f[key]
                f.save()
            return True
        return False
    return False


# ---------------------------------------------------------------------------
# Name romanization helper
# ---------------------------------------------------------------------------
def _romanize_credit_names(
    names: list[str],
    name_map: dict[str, str],
) -> list[str]:
    """
    Apply a Japanese → romanized name mapping to a list of credit names.

    Returns a new list where every CJK name that appears as a key in
    ``name_map`` is replaced by its romanized value; others are kept
    as-is.  A name that is already Latin script is never replaced: a
    romanization has nothing to add to it, and the guard stops a bad
    mapping from rewriting a correct Latin credit.
    """
    return [
        name if _is_latin_script(name) else name_map.get(name, name)
        for name in names
    ]
