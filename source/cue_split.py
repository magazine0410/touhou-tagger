"""cue_split.py — split a single whole-album image into per-track FLACs via a CUE.

A common cause of the tagger's *severe track mismatch* gate firing (see
``compare_tracklists`` in ``touhou_tagger.py``) is an **un-split album**: the
folder holds one big whole-album FLAC plus a CUE sheet (external or embedded in
the FLAC), while the wiki reports many tracks.  Almost every fetched track then
shows up as ``missing_local`` and the album auto-skips.

This module is the one-click recovery for that situation, surfaced as a button
in the GUI's mismatch dialog:

1. :func:`detect_cue` — recognise a lone FLAC image + a findable CUE.
2. :func:`split_album` — split it into per-track FLACs with ``ffmpeg``, tag
   them from the CUE with ``mutagen``, **verify** the result decodes cleanly
   with no mojibake names, then apply the caller's post-processing choice to
   the original image (Trash or keep) and leave the folder ready for a normal
   re-tag.

CUE titles are decoded with encoding auto-detect (CUEs for Japanese albums are
routinely Shift-JIS / CP932, not UTF-8); a decode that still yields U+FFFD
replacement characters is treated as **mojibake** and aborts the split with the
original untouched — a wrong-album tag (or a folder full of garbled filenames)
is worse than a missed recovery.

Leaf module: imports nothing from the project (mirrors ``availability.py`` /
``browser_cookie.py``), so both ``gui.py`` and ``touhou_tagger.py`` can
soft-import it without a cycle or dragging anything onto the CLI path.  The
audio work is delegated to external CLIs probed at call time — ``ffmpeg`` for
the split, ``flac`` for decode verification, ``metaflac`` for embedded-CUE
extraction, and ``gio`` (with ``trash-put`` / ``kioclient5`` fallbacks) for the
Trash — while the per-track tags are written with ``mutagen`` directly from our
own correctly-decoded CUE titles.  We deliberately use neither ``shnsplit`` nor
``cuetag``: the former's WAV-to-FLAC pipe is rejected by FLAC 1.4+, and the
latter assumes the CUE is UTF-8 and silently mangles Shift-JIS / CP932 titles.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace

# The whole-album image we know how to split.  Scoped to FLAC: every embedded
# CUE path needs metaflac, and FLAC is what this collection actually uses.
_IMAGE_EXT = ".flac"

# A lone FLAC longer than this is almost certainly a whole-album/disc image
# rather than a single track, so the split button is offered for it even before
# a CUE is confirmed (duration is format-independent, unlike a byte size — the
# same 150 MiB is ~21 min of CD audio but only ~4 min at 24/192).
_MIN_IMAGE_DURATION_SEC = 600     # 10 minutes
# Per-track audio extensions that, if already present in numbers, mean the
# folder is *already split* — so there's nothing to do.
_AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".m4a", ".opus", ".wav", ".ape"}

# Replacement character: a decode that produces this means the CUE encoding was
# guessed wrong (mojibake), so the titles can't be trusted.
_REPLACEMENT = "�"

# Control characters that never appear in a legitimate title/CUE body (tab,
# newline and carriage return excepted).  Their presence after a "successful"
# decode means a single-byte codec (cp1251/latin-1, which accept any byte
# without raising) swallowed genuinely corrupt bytes — i.e. mojibake the
# U+FFFD check alone can't see.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Characters not allowed (or unwise) in a filename; replaced with "_".
_FS_UNSAFE_RE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')

# Disc indicator in a *filename* (not a subfolder): "Disc 1", "DISC2",
# "[Disc 1]", "- disc3", "CD 2", "Disk1" …  The lookarounds keep it from
# firing inside a longer token ("ACID", "CD2000"): no letter/digit directly
# before the prefix, and no further digit after the (1-2 digit) disc number.
_DISC_IN_NAME_RE = re.compile(
    r'(?<![a-z0-9])(?:disc|disk|cd)[\s._\-]*(\d{1,2})(?![0-9])',
    re.IGNORECASE)


# Keep this module Qt-free and project-import-free.  The GUI installs the
# shared external-tools resolver at startup so saved executable overrides are
# honored there; direct callers still get ordinary PATH lookup.
_TOOL_RESOLVER = shutil.which


def set_tool_resolver(resolver) -> None:
    """Install an optional external-command resolver supplied by the caller."""
    global _TOOL_RESOLVER
    _TOOL_RESOLVER = resolver if callable(resolver) else shutil.which


class CueDecodeError(Exception):
    """Raised when a CUE sheet can't be decoded without mojibake."""


@dataclass
class CueSource:
    """A detected split-able situation in a folder."""

    image_path: str            # the lone whole-album FLAC
    music_dir: str
    source_kind: str           # "external" | "vorbis_tag" | "binary_block"
    encoding: str              # encoding the CUE text was decoded with
    tracks: list               # [(number:int, title:str, performer:str), ...]
    starts: list = field(default_factory=list)   # per-track start time (sec)
    file_count: int = 1        # number of FILE lines (>1 ⇒ multi-file CUE)
    album: str = ""            # disc-level TITLE
    album_performer: str = ""  # disc-level PERFORMER
    cue_path: str | None = None        # set for source_kind == "external"
    cue_text: str | None = None        # the decoded CUE text (always set)
    disc_no: int | None = None         # set on multi-disc plans (from filename)


@dataclass
class SplitPlan:
    """Everything :func:`split_plan` needs — one or several disc images.

    ``multi_disc`` False: a single lone-image source, split in place (the
    original behaviour).  True: one source per disc image; each is moved into
    a ``Disc N`` subfolder before being split there.
    """

    sources: list              # [CueSource, ...] (multi-disc: sorted by disc)
    multi_disc: bool = False


@dataclass
class SplitResult:
    ok: bool
    reason: str = ""                   # machine-readable failure reason
    message: str = ""                  # human-readable summary / error
    created: list = field(default_factory=list)   # new per-track file paths
    trashed: str | None = None         # the image path moved to Trash


_POST_PROCESSING = {"trash", "keep"}


# --------------------------------------------------------------------------- #
# Tooling probes
# --------------------------------------------------------------------------- #

def _which(*names: str) -> str | None:
    """Return the first configured/PATH-resolved tool matching ``names``."""
    for n in names:
        p = _TOOL_RESOLVER(n)
        if p:
            return p
    return None


def cue_tools_available() -> bool:
    """True when the external CLIs needed to split + verify are installed.

    Splitting is done with ``ffmpeg`` (cutting at breakpoints we compute from
    the CUE's INDEX times) and verified with ``flac -t``.  We deliberately do
    *not* use ``shnsplit``: it pipes a non-canonical WAV to the ``flac``
    encoder, which flac 1.4+ rejects ("child encoder process had non-zero exit
    status"), and it can't derive split points from a multi-FILE CUE.
    """
    return bool(_which("ffmpeg") and _which("flac"))


def install_hint() -> str:
    return ("CUE splitting needs the 'ffmpeg' and 'flac' commands on your "
            "PATH. Install them with your OS package manager, e.g.:\n"
            "  Fedora:        sudo dnf install ffmpeg flac\n"
            "  Debian/Ubuntu: sudo apt install ffmpeg flac\n"
            "  Arch:          sudo pacman -S ffmpeg flac\n"
            "  macOS (brew):  brew install ffmpeg flac\n"
            "  Windows:       install FFmpeg and FLAC and add them to PATH")


# --------------------------------------------------------------------------- #
# CUE decode + parse
# --------------------------------------------------------------------------- #

def _looks_garbled(text: str) -> bool:
    """True if ``text`` shows mojibake: U+FFFD or stray control characters."""
    return _REPLACEMENT in text or bool(_CTRL_RE.search(text))


def _cjk_score(text: str) -> int:
    """Count CJK ideographs and kana — the signal that a multibyte JP codec
    decoded correctly (a wrong single-byte decode of JP bytes yields Latin /
    Cyrillic punctuation soup instead, scoring 0)."""
    n = 0
    for ch in text:
        o = ord(ch)
        if (0x3040 <= o <= 0x30FF      # hiragana + katakana
                or 0x4E00 <= o <= 0x9FFF   # CJK unified ideographs
                or 0x3400 <= o <= 0x4DBF   # CJK ext-A
                or 0xFF66 <= o <= 0xFF9F   # half-width katakana
                or 0x3000 <= o <= 0x303F): # CJK symbols/punctuation
            n += 1
    return n


def _decode_cue_bytes(raw: bytes) -> tuple[str, str]:
    """Decode CUE bytes to text, auto-detecting the encoding.

    Strict UTF-8 wins outright when valid.  Otherwise every plausible codec is
    decoded and the one yielding the **most CJK/kana characters** is chosen —
    a deliberately JP-biased tie-break, because this collection's non-UTF-8
    CUEs are Shift-JIS/CP932 and a statistical detector (``charset_normalizer``
    / ``chardet``) routinely mis-guesses short JP text as a Western single-byte
    encoding that decodes without raising but is pure mojibake.  When no
    candidate contains CJK (a genuinely Western CUE) the detector's guess, then
    latin-1, is used.  Raises :class:`CueDecodeError` if nothing decodes
    without mojibake (U+FFFD or stray control characters).
    """
    # 1. Strict UTF-8 (handles the BOM too) — authoritative when it validates.
    for enc in ("utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            if not _looks_garbled(text):
                return text, enc
        except UnicodeDecodeError:
            pass

    # 2. Statistical detector's guess, as one candidate among many.
    detected: str | None = None
    try:
        import charset_normalizer  # type: ignore
        best = charset_normalizer.from_bytes(raw).best()
        if best is not None:
            detected = best.encoding
    except Exception:
        try:
            import chardet  # type: ignore
            guess = chardet.detect(raw)
            if guess and guess.get("encoding"):
                detected = guess["encoding"]
        except Exception:
            detected = None

    # 3. Candidate set: JP codecs first (this collection's reality), then the
    # detector guess and a permissive latin-1 catch-all.  Order also breaks
    # ties when CJK scores are equal (e.g. a Western CUE: all score 0).
    candidates = ["cp932", "shift_jis", "euc-jp", "gbk", "big5"]
    if detected and detected.lower() not in {c.lower() for c in candidates}:
        candidates.append(detected)
    candidates.append("latin-1")

    best_text: str | None = None
    best_enc = ""
    best_cjk = -1
    for enc in candidates:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        if _looks_garbled(text):
            continue
        score = _cjk_score(text)
        if score > best_cjk:
            best_cjk, best_text, best_enc = score, text, enc

    if best_text is not None:
        return best_text, best_enc

    # Nothing decoded cleanly — treat as mojibake; the caller must abort.
    raise CueDecodeError(
        "could not decode the CUE sheet without garbled characters "
        f"(tried {', '.join(['utf-8'] + candidates)})")


def _read_cue_file(path: str) -> tuple[str, str]:
    with open(path, "rb") as fh:
        return _decode_cue_bytes(fh.read())


_TRACK_RE = re.compile(r'^\s*TRACK\s+(\d+)\s+AUDIO', re.IGNORECASE)
_TITLE_RE = re.compile(r'^\s*TITLE\s+(.*)$', re.IGNORECASE)
_PERFORMER_RE = re.compile(r'^\s*PERFORMER\s+(.*)$', re.IGNORECASE)
_FILE_RE = re.compile(r'^\s*FILE\s+', re.IGNORECASE)
_INDEX_RE = re.compile(r'^\s*INDEX\s+(\d+)\s+(\d+):(\d+):(\d+)', re.IGNORECASE)


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    return s.strip()


def _index_seconds(mm: str, ss: str, ff: str) -> float:
    """CUE ``MM:SS:FF`` (FF = CD frames, 75/s) → seconds."""
    return int(mm) * 60 + int(ss) + int(ff) / 75.0


def _parse_cue(text: str):
    """Parse a CUE.

    Returns ``(tracks, album_title, album_performer, starts, file_count)``:

    * ``tracks``      — ``[(track_number, title, performer), ...]``
    * ``starts``      — per-track start offset in seconds (INDEX 01, falling
                        back to INDEX 00), aligned 1:1 with ``tracks``
    * ``file_count``  — number of ``FILE`` lines; ``> 1`` means a multi-FILE
                        CUE (each track in its own file), which can't be used
                        to carve a single image.

    The disc-level ``TITLE`` / ``PERFORMER`` (before the first TRACK) become
    the album fields.  Track titles default to ``Track NN`` when the CUE omits
    them (e.g. a binary FLAC CUESHEET block carries no titles).
    """
    tracks: list[list] = []
    starts: list[float | None] = []
    cur: list | None = None
    album = ""
    album_perf = ""
    file_count = 0
    for line in text.splitlines():
        if _FILE_RE.match(line):
            file_count += 1
            continue
        m = _TRACK_RE.match(line)
        if m:
            cur = [int(m.group(1)), "", ""]
            tracks.append(cur)
            starts.append(None)
            continue
        mt = _TITLE_RE.match(line)
        if mt:
            if cur is None:
                album = _unquote(mt.group(1))
            else:
                cur[1] = _unquote(mt.group(1))
            continue
        mp = _PERFORMER_RE.match(line)
        if mp:
            if cur is None:
                album_perf = _unquote(mp.group(1))
            else:
                cur[2] = _unquote(mp.group(1))
            continue
        mi = _INDEX_RE.match(line)
        if mi and cur is not None:
            idx = int(mi.group(1))
            secs = _index_seconds(mi.group(2), mi.group(3), mi.group(4))
            # Prefer INDEX 01 (track audio start); accept INDEX 00 (pregap)
            # only if no INDEX 01 has been seen for this track yet.
            if idx == 1 or starts[-1] is None:
                starts[-1] = secs
    out = []
    for num, title, perf in tracks:
        if not title:
            title = f"Track {num:02d}"
        out.append((num, title, perf))
    starts = [0.0 if s is None else s for s in starts]
    return out, album, album_perf, starts, max(file_count, 1)


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

def _flac_duration(path: str) -> float:
    """Length of a FLAC in seconds, read cheaply from the STREAMINFO header
    (no decode).  Returns 0.0 if it can't be read."""
    try:
        from mutagen.flac import FLAC
        return float(FLAC(path).info.length)
    except Exception:
        return 0.0


def _list_audio(music_dir: str) -> list[str]:
    try:
        names = os.listdir(music_dir)
    except OSError:
        return []
    return sorted(
        os.path.join(music_dir, n) for n in names
        if os.path.splitext(n)[1].lower() in _AUDIO_EXTS
        and os.path.isfile(os.path.join(music_dir, n))
    )


def _extract_embedded_cue(flac_path: str) -> tuple[str, str, str] | None:
    """Return ``(cue_text, encoding, kind)`` for a CUE embedded in ``flac_path``.

    Prefers the ``CUESHEET`` Vorbis comment (carries titles), then the binary
    FLAC CUESHEET metadata block (timing only — titles become ``Track NN``).
    Returns None if neither is present or metaflac is unavailable.
    """
    metaflac = _which("metaflac")
    if not metaflac:
        return None
    # 1. CUESHEET as a Vorbis comment (full text, with titles).
    try:
        out = subprocess.run(
            [metaflac, "--show-tag=CUESHEET", flac_path],
            capture_output=True, timeout=30)
        raw = out.stdout
        # Output is "CUESHEET=<text...>"; strip the leading tag name.
        if raw:
            text = raw.decode("utf-8", "replace")
            if text.upper().startswith("CUESHEET="):
                body = raw.split(b"=", 1)[1]
                try:
                    decoded, enc = _decode_cue_bytes(body)
                except CueDecodeError:
                    decoded, enc = None, None
                if decoded and "TRACK" in decoded.upper():
                    return decoded, enc, "vorbis_tag"
    except Exception:
        pass
    # 2. Binary CUESHEET metadata block (no titles).
    try:
        out = subprocess.run(
            [metaflac, "--export-cuesheet-to=-", flac_path],
            capture_output=True, timeout=30)
        if out.returncode == 0 and out.stdout:
            decoded, enc = _decode_cue_bytes(out.stdout)
            if "TRACK" in decoded.upper():
                return decoded, enc, "binary_block"
    except CueDecodeError:
        pass
    except Exception:
        pass
    return None


_GENERIC_TITLE_RE = re.compile(r'^Track\s+\d+$', re.IGNORECASE)


def _real_title_count(tracks) -> int:
    """How many tracks carry a real title (not the ``Track NN`` placeholder)."""
    return sum(1 for _n, t, _p in tracks if not _GENERIC_TITLE_RE.match(t.strip()))


def _usable_offsets(cs: "CueSource") -> bool:
    """True if this CUE has real, strictly-increasing single-image offsets.

    A multi-FILE CUE (``file_count > 1``) lists each track in its own file
    with ``INDEX 01 00:00:00``, so its starts are all 0 — useless for cutting
    one image.  A single-FILE CUE with increasing INDEX times is what we need.
    """
    s = cs.starts
    return (cs.file_count == 1 and len(s) >= 2
            and all(s[i] > s[i - 1] for i in range(1, len(s))))


def _list_cue_files(music_dir: str) -> list[str]:
    try:
        return sorted(
            os.path.join(music_dir, n) for n in os.listdir(music_dir)
            if n.lower().endswith(".cue")
            and os.path.isfile(os.path.join(music_dir, n))
        )
    except OSError:
        return []


def _collect_candidates(music_dir: str, image: str,
                        cue_paths: list[str] | None = None,
                        ) -> list["CueSource"]:
    """Parse every CUE source for ``image`` — external ``*.cue`` files first,
    then the embedded CUESHEET — into candidate :class:`CueSource` objects.

    ``cue_paths`` restricts which external CUEs are considered (used by the
    multi-disc detection to pair each disc image with *its* CUE); ``None``
    means every ``*.cue`` in the folder.
    """
    cands: list[CueSource] = []
    cue_files = (_list_cue_files(music_dir)
                 if cue_paths is None else list(cue_paths))
    for cue_path in cue_files:
        try:
            text, enc = _read_cue_file(cue_path)
        except CueDecodeError:
            continue
        tracks, album, perf, starts, fcount = _parse_cue(text)
        if tracks:
            cands.append(CueSource(
                image_path=image, music_dir=music_dir, source_kind="external",
                encoding=enc, tracks=tracks, starts=starts, file_count=fcount,
                album=album, album_performer=perf,
                cue_path=cue_path, cue_text=text))
    embedded = _extract_embedded_cue(image)
    if embedded:
        text, enc, kind = embedded
        tracks, album, perf, starts, fcount = _parse_cue(text)
        if tracks:
            cands.append(CueSource(
                image_path=image, music_dir=music_dir, source_kind=kind,
                encoding=enc, tracks=tracks, starts=starts, file_count=fcount,
                album=album, album_performer=perf, cue_text=text))
    return cands


def _merge_candidates(cands: list["CueSource"]) -> CueSource | None:
    """Merge the best offsets with the best titles across CUE candidates.

    When several CUE sources disagree, the best **offsets** and the best
    **titles** are combined by track number.  This is a common EAC/rip layout
    where the sidecar ``*.cue`` lists one ``FILE`` per track (real
    titles, but useless ``INDEX 01 00:00:00`` offsets) while the FLAC embeds a
    single-file CUESHEET with the real timing but no titles — neither alone can
    split the image, but together they can.
    """
    if not cands:
        return None
    image = cands[0].image_path
    music_dir = cands[0].music_dir

    # Best title source: most real (non-placeholder) titles, external winning
    # ties (its titles are usually richest).
    title_cands = [c for c in cands if _real_title_count(c.tracks) > 0]
    titles = max(
        title_cands,
        key=lambda c: (_real_title_count(c.tracks),
                       c.source_kind == "external"),
        default=None)

    # Best offset source: the first CUE with usable single-image offsets.
    offset = next((c for c in cands if _usable_offsets(c)), None)

    if offset is None:
        # Nothing has usable offsets — return the richest candidate so
        # split_album reports the precise reason (multi-file / bad breakpoints)
        # instead of producing garbage.
        return titles or cands[0]

    # Merge: offset source defines the track set + start times; titles are
    # filled in per track number from the best title source.
    title_by_num = ({num: (t, p) for num, t, p in titles.tracks}
                    if titles is not None else {})
    merged = [(num, title_by_num.get(num, (ot, op))[0],
               title_by_num.get(num, (ot, op))[1])
              for num, ot, op in offset.tracks]
    if titles is not None and titles is not offset:
        kind = f"{titles.source_kind} titles + {offset.source_kind} offsets"
        enc = titles.encoding
        album = titles.album or offset.album
        album_perf = titles.album_performer or offset.album_performer
        cue_path, cue_text = titles.cue_path, titles.cue_text
    else:
        kind, enc = offset.source_kind, offset.encoding
        album, album_perf = offset.album, offset.album_performer
        cue_path, cue_text = offset.cue_path, offset.cue_text
    return CueSource(
        image_path=image, music_dir=music_dir, source_kind=kind, encoding=enc,
        tracks=merged, starts=offset.starts, file_count=1,
        album=album, album_performer=album_perf,
        cue_path=cue_path, cue_text=cue_text)


def detect_cue(music_dir: str) -> CueSource | None:
    """Detect a split-able *lone*-image-plus-CUE folder, or return None.

    Returns None (no button shown) when the folder is already split (more than
    one audio file), has no FLAC image, or no CUE can be found/decoded.  See
    :func:`_merge_candidates` for how disagreeing CUE sources are combined.
    Multi-disc folders (several disc-named images) are :func:`detect_split`'s
    job — this keeps the original single-image contract.
    """
    audio = _list_audio(music_dir)
    flacs = [p for p in audio if p.lower().endswith(_IMAGE_EXT)]
    # Already split (or ambiguous): more than one audio file means there is no
    # single image to carve up.
    if len(audio) != 1 or len(flacs) != 1:
        return None
    return _merge_candidates(_collect_candidates(music_dir, flacs[0]))


def _build_multi_plan(music_dir: str, pairs: list[tuple[int, str]],
                      *, disc_fallback: bool) -> SplitPlan | None:
    """Build a multi-image :class:`SplitPlan` from ``(disc_no, image)`` pairs.

    Each image is paired with its CUE by identical stem first; when
    ``disc_fallback`` (the true disc-named case) also by matching disc number
    in the CUE filename; then that image's embedded CUESHEET.  All-or-nothing:
    if any image yields no usable CUE, returns None.
    """
    all_cues = _list_cue_files(music_dir)
    sources: list[CueSource] = []
    for disc_no, image in sorted(pairs):
        stem = os.path.splitext(os.path.basename(image))[0].casefold()
        matched = [c for c in all_cues
                   if os.path.splitext(os.path.basename(c))[0].casefold()
                   == stem]
        if not matched and disc_fallback:
            matched = [
                c for c in all_cues
                if (m := _DISC_IN_NAME_RE.search(os.path.basename(c)))
                and int(m.group(1)) == disc_no
            ]
        src = _merge_candidates(
            _collect_candidates(music_dir, image, cue_paths=matched))
        if src is None:
            return None            # all-or-nothing
        sources.append(replace(src, disc_no=disc_no))
    return SplitPlan(sources=sources, multi_disc=True)


def detect_split(music_dir: str,
                 min_duration_sec: float = _MIN_IMAGE_DURATION_SEC,
                 *, allow_ambiguous: bool = False,
                 ) -> SplitPlan | None:
    """Detect anything split-able in ``music_dir`` — lone image or image set.

    * Exactly one audio file (a FLAC image) → the :func:`detect_cue` case,
      wrapped in a single-source :class:`SplitPlan` (split in place).
    * Two or more FLACs (nothing else audio) that are all **disc-named**
      ("Disc 1", "DISC2", "cd 3", … with distinct numbers) → a multi-disc plan
      keyed by those numbers, *any duration* (a short bonus disc still counts).
    * Two or more FLACs (nothing else audio), not disc-named, but **all long**
      (``>= min_duration_sec`` — i.e. a folder of continuous mixes/images, not
      a normal album with one long track) → a multi-image plan with disc
      numbers assigned by sorted filename.
    * In both multi-image cases the originals go into ``Disc N`` subfolders and
      are split there.  All-or-nothing: if any image yields no usable CUE,
      returns None rather than a partial split.
    * With ``allow_ambiguous=True``, a caller that has independent evidence of
      an incomplete tracklist may ask us to inspect 2–3 FLACs individually.
      A plan is returned only when exactly one image has a uniquely matched
      external/embedded CUE; ambiguity still returns None.
    * Anything else (mixed content, duplicate disc numbers, a normal album) →
      None.
    """
    audio = _list_audio(music_dir)
    flacs = [p for p in audio if p.lower().endswith(_IMAGE_EXT)]

    if len(audio) == 1 and len(flacs) == 1:
        src = detect_cue(music_dir)
        return SplitPlan(sources=[src]) if src is not None else None

    if (allow_ambiguous and 1 <= len(flacs) <= 3
            and len(audio) == len(flacs)):
        candidates: list[CueSource] = []
        all_cues = _list_cue_files(music_dir)
        for image in flacs:
            stem = os.path.splitext(os.path.basename(image))[0].casefold()
            matched = [
                c for c in all_cues
                if os.path.splitext(os.path.basename(c))[0].casefold() == stem
            ]
            src = _merge_candidates(
                _collect_candidates(music_dir, image, cue_paths=matched)
            )
            if src is not None:
                candidates.append(src)
        if len(candidates) == 1:
            return SplitPlan(sources=candidates)

    if len(flacs) < 2 or len(audio) != len(flacs):
        return None

    # Disc-named set: commit to the parsed disc numbers (any duration).
    matches = [_DISC_IN_NAME_RE.search(os.path.basename(p)) for p in flacs]
    if all(matches):
        nums = [int(m.group(1)) for m in matches]
        if len(set(nums)) != len(nums):
            return None            # duplicate disc numbers → ambiguous
        return _build_multi_plan(
            music_dir, list(zip(nums, flacs)), disc_fallback=True)

    # Not disc-named: only treat as several images to split when every FLAC is
    # long enough to be a mix/image (avoids grabbing a normal multi-track
    # album).  Disc numbers assigned by sorted filename.
    if all(_flac_duration(p) >= min_duration_sec for p in flacs):
        return _build_multi_plan(
            music_dir, list(enumerate(sorted(flacs), start=1)),
            disc_fallback=False)
    return None


def looks_splittable(music_dir: str,
                     min_duration_sec: float = _MIN_IMAGE_DURATION_SEC) -> bool:
    """Cheap "should the split button be offered here?" check — no CUE needed.

    Broader than :func:`detect_split` (which requires a usable CUE): this only
    decides *button visibility*, so the button appears for a plausible
    whole-album/disc image even before a CUE is confirmed, then reports at
    click time if none is found.  True when the folder matches a shape
    :func:`split_plan` can act on:

    * **Disc set** — 2+ FLACs, every audio file a FLAC carrying a distinct disc
      indicator ("Disc 1", "DISC2", …): always offered, *regardless of
      duration* (a short bonus disc still counts).
    * **Lone disc-named FLAC** — a single disc-named image, any duration.
    * **All-large images** — every audio file is a FLAC and *all* of them are
      long enough (``>= min_duration_sec``): covers a lone album/disc image and
      a folder of two-plus continuous mixes alike.  Requiring *all* to be long
      (not just one) keeps a normal album that merely contains one long track
      from triggering.
    """
    audio = _list_audio(music_dir)
    flacs = [p for p in audio if p.lower().endswith(_IMAGE_EXT)]
    if not flacs:
        return False
    all_flac = len(audio) == len(flacs)

    # Disc set: 2+ disc-named FLACs, nothing else audio — duration-independent.
    if all_flac and len(flacs) >= 2:
        discs = [_DISC_IN_NAME_RE.search(os.path.basename(p)) for p in flacs]
        if all(discs) and len({int(m.group(1)) for m in discs}) == len(discs):
            return True

    # Lone disc-named image — any duration.
    if len(audio) == 1 and len(flacs) == 1 \
            and _DISC_IN_NAME_RE.search(os.path.basename(flacs[0])):
        return True

    # All audio files are FLAC images and every one is long enough (a lone
    # album image, or several continuous mixes).
    if all_flac and all(_flac_duration(p) >= min_duration_sec for p in flacs):
        return True
    return False


# --------------------------------------------------------------------------- #
# Split
# --------------------------------------------------------------------------- #

def _has_mojibake(s: str) -> bool:
    return _looks_garbled(s)


def _safe_filename(name: str) -> str:
    name = _FS_UNSAFE_RE.sub("_", name).strip().rstrip(".")
    return name or "track"


def _write_track_tags(path: str, num: int, title: str, performer: str,
                      album: str, album_performer: str, log,
                      disc_no: int | None = None) -> None:
    """Write title/tracknumber (+ artist/album) onto a split FLAC via mutagen.

    Titles come straight from our correctly-decoded CUE parse, so they're UTF-8
    clean.  These are starting values for the subsequent wiki re-tag — the
    title + tracknumber are what ``compare_tracklists`` re-reads.
    """
    try:
        from mutagen.flac import FLAC
    except Exception as exc:        # mutagen always present in this project
        log(f"    could not import mutagen to tag split files: {exc}")
        return
    try:
        audio = FLAC(path)
        audio["title"] = title
        audio["tracknumber"] = f"{num:02d}"
        if disc_no is not None:
            audio["discnumber"] = str(disc_no)
        if performer:
            audio["artist"] = performer
        elif album_performer:
            audio["artist"] = album_performer
        if album:
            audio["album"] = album
        if album_performer:
            audio["albumartist"] = album_performer
        audio.save()
    except Exception as exc:
        log(f"    tag write failed for {os.path.basename(path)}: {exc}")


def _trash(path: str, log) -> bool:
    """Move ``path`` to the desktop Trash.  Returns True on success."""
    gio = _which("gio")
    if gio:
        r = subprocess.run([gio, "trash", "--", path],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            return True
        log(f"    gio trash failed: {r.stderr.strip()}")
    tp = _which("trash-put")
    if tp:
        if subprocess.run([tp, "--", path]).returncode == 0:
            return True
    kio = _which("kioclient5", "kioclient")
    if kio:
        if subprocess.run([kio, "move", path, "trash:/"]).returncode == 0:
            return True
    log("    no working trash backend (gio/trash-put/kioclient) — original "
        "left in place")
    return False


def _check_source(source: CueSource) -> tuple[SplitResult | None, list]:
    """Pre-flight one CueSource: mojibake + usable split points.

    Returns ``(failure, starts)`` — ``failure`` is a failed
    :class:`SplitResult` (and ``starts`` empty) when the source can't be split
    safely, else ``None`` plus the derived per-track start times.  Pure check:
    touches no files, so :func:`split_plan` can validate *every* disc before
    moving anything.
    """
    tracks = source.tracks

    # Mojibake: never write garbled titles.
    for _, title, perf in tracks:
        if _has_mojibake(title) or _has_mojibake(perf):
            return SplitResult(
                ok=False, reason="mojibake",
                message=("The CUE sheet's track titles are garbled (could not "
                         "be decoded) — split aborted, original untouched."),
            ), []

    # Split points (seconds).  The first track always starts at 0 so no
    # lead-in audio is ever dropped.
    starts = list(source.starts) or [0.0] * len(tracks)
    if starts:
        starts[0] = 0.0
    if source.file_count > 1:
        return SplitResult(
            ok=False, reason="multifile_cue",
            message=("This CUE references one file per track (a multi-file "
                     "CUE), so it carries no offsets for cutting a single "
                     "image — can't split it. The album may need a "
                     "single-file CUE.")), []
    if any(starts[i] <= starts[i - 1] for i in range(1, len(starts))):
        return SplitResult(
            ok=False, reason="bad_breakpoints",
            message=("The CUE's track start times aren't increasing, so no "
                     "usable split points could be derived — split aborted, "
                     "original untouched.")), []
    return None, starts


def split_album(source: CueSource, *, dry_run: bool = False,
                original_policy: str = "trash", log=print) -> SplitResult:
    """Split a source and either Trash or keep its verified original.

    On any verification failure the original image is left untouched and a
    failed :class:`SplitResult` is returned with a machine-readable ``reason``.
    """
    if not cue_tools_available():
        return SplitResult(ok=False, reason="no_tools", message=install_hint())

    if original_policy not in _POST_PROCESSING:
        original_policy = "trash"
    music_dir = source.music_dir
    image = source.image_path
    tracks = source.tracks

    # --- 1/2. Pre-flight: mojibake guard + derived split points. -----------
    failure, starts = _check_source(source)
    if failure is not None:
        return failure

    log(f"  Splitting {os.path.basename(image)} into {len(tracks)} track(s) "
        f"using {source.source_kind} CUE [{source.encoding}] via ffmpeg.")
    if dry_run:
        listing = ", ".join(f"{n:02d} {t}" for n, t, _ in tracks[:4])
        return SplitResult(
            ok=True, reason="dry_run",
            message=f"Would split into {len(tracks)} tracks: {listing}…")

    ffmpeg = _which("ffmpeg")
    flac = _which("flac")
    tmp_dir = tempfile.mkdtemp(prefix=".cue_split_", dir=music_dir)
    try:
        # --- 3. Cut each track with ffmpeg. --------------------------------
        # Output-side -ss/-t (after -i) give sample-accurate cuts; -map 0:a:0
        # takes only the first audio stream, ignoring any embedded cover art
        # or CUESHEET so the encoder can't trip over them (the flac-1.5 /
        # shntool-pipe failure mode this replaces).  Re-encode to FLAC -8.
        produced: list[str] = []
        for i, ((num, _t, _p), start) in enumerate(zip(tracks, starts)):
            out = os.path.join(tmp_dir, f"{num:02d}.flac")
            cmd = [ffmpeg, "-nostdin", "-v", "error", "-y",
                   "-i", image, "-ss", f"{start:.6f}"]
            if i + 1 < len(starts):
                cmd += ["-t", f"{starts[i + 1] - start:.6f}"]
            cmd += ["-map", "0:a:0", "-vn", "-c:a", "flac",
                    "-compression_level", "8", out]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            if proc.returncode != 0 or not os.path.exists(out):
                return SplitResult(
                    ok=False, reason="ffmpeg_failed",
                    message=(f"ffmpeg failed on track {num:02d}:\n"
                             f"{proc.stderr.strip()[:800]}"))
            produced.append(out)

        # --- 4. Decode-verify every output (catches corruption). -----------
        for f in produced:
            v = subprocess.run([flac, "-st", f], capture_output=True)
            if v.returncode != 0:
                return SplitResult(
                    ok=False, reason="decode_failed",
                    message=(f"Verification failed: {os.path.basename(f)} did "
                             "not decode cleanly — aborted, original kept."))

        # --- 5. Tag from our own decoded CUE, rename to "NN - Title.flac",
        # and move into the album dir.  Tags are written with mutagen (not
        # cuetag) so the correctly-decoded titles never get re-mangled. -----
        created: list[str] = []
        for (num, title, perf), src in zip(tracks, produced):
            fname = f"{num:02d} - {_safe_filename(title)}.flac"
            if _has_mojibake(fname):           # belt-and-suspenders
                return SplitResult(
                    ok=False, reason="mojibake",
                    message="A split filename came out garbled — aborted.")
            dest = os.path.join(music_dir, fname)
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest)
                dest = f"{base}_split{ext}"
            shutil.move(src, dest)
            _write_track_tags(dest, num, title, perf, source.album,
                              source.album_performer, log,
                              disc_no=source.disc_no)
            created.append(dest)

        # --- 6. Apply the selected post-processing after verification. ------
        trashed = None
        if original_policy == "trash":
            trashed = image if _trash(image, log) else None
        else:
            log("  ✔ Verified split; original image kept in place by choice.")

        outcome = "moved to Trash." if trashed else "left in place."
        log(f"  ✔ Split into {len(created)} track(s); original {outcome}")
        return SplitResult(
            ok=True, reason="ok", created=created, trashed=trashed,
            message=(f"Split into {len(created)} track(s); original "
                     + ("sent to Trash." if trashed else "left in place.")))
    finally:
        # Clean up the temp dir regardless of outcome.
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


def split_plan(plan: SplitPlan, *, dry_run: bool = False,
               original_policy: str = "trash", log=print) -> SplitResult:
    """Execute a :class:`SplitPlan` — the entry point the GUI button uses.

    Single-source plan: delegates straight to :func:`split_album` (split in
    place, the original behaviour).

    Multi-disc plan: **every** disc is pre-flighted first (mojibake, usable
    offsets, target subfolder free) so a doomed plan aborts before a single
    file has moved.  Then, per disc in disc order: create the ``Disc N``
    subfolder, move the original image (+ its external CUE) into it, and run
    :func:`split_album` there — which splits, verifies, tags and applies the
    selected original policy to that disc's image.  The subfolder names match
    ``file_scan.DISC_DIR_RE`` (``Disc 1``, ``Disc 2`` …), so the tagger's
    re-scan assigns the right disc numbers afterwards.

    If a disc fails *after* moves began (rare: ffmpeg/verify error), earlier
    discs stay split in their subfolders and the failed disc's image is left
    unsplit (and untrashed) in its own subfolder; the message says exactly
    which disc failed and what was already done.
    """
    if not plan.multi_disc:
        return split_album(
            plan.sources[0], dry_run=dry_run,
            original_policy=original_policy, log=log,
        )

    if not cue_tools_available():
        return SplitResult(ok=False, reason="no_tools", message=install_hint())
    music_dir = plan.sources[0].music_dir

    # --- Pre-flight every disc before touching any file. -------------------
    for src in plan.sources:
        failure, _starts = _check_source(src)
        if failure is not None:
            return SplitResult(
                ok=False, reason=failure.reason,
                message=(f"Disc {src.disc_no}: {failure.message}\n"
                         "Nothing was moved or split."))
        dest_dir = os.path.join(music_dir, f"Disc {src.disc_no}")
        if os.path.isdir(dest_dir) and _list_audio(dest_dir):
            return SplitResult(
                ok=False, reason="dest_exists",
                message=(f"The subfolder 'Disc {src.disc_no}' already exists "
                         "and contains audio files — not overwriting. "
                         "Nothing was moved or split."))

    subs = ", ".join(f"Disc {s.disc_no}/" for s in plan.sources)
    log(f"  Multi-disc split: {len(plan.sources)} disc image(s) → {subs}")
    if dry_run:
        total = sum(len(s.tracks) for s in plan.sources)
        return SplitResult(
            ok=True, reason="dry_run",
            message=(f"Would move {len(plan.sources)} disc image(s) into "
                     f"{subs} and split them into {total} track(s)."))

    # --- Move each image (+ its external CUE) into its Disc N subfolder. ---
    moved: list[CueSource] = []
    done_moves: list[tuple[str, str]] = []   # (now_at, was_at) for rollback
    try:
        for src in plan.sources:
            dest_dir = os.path.join(music_dir, f"Disc {src.disc_no}")
            os.makedirs(dest_dir, exist_ok=True)
            new_image = os.path.join(dest_dir,
                                     os.path.basename(src.image_path))
            shutil.move(src.image_path, new_image)
            done_moves.append((new_image, src.image_path))
            new_cue = src.cue_path
            if src.cue_path and os.path.dirname(src.cue_path) == music_dir:
                new_cue = os.path.join(dest_dir,
                                       os.path.basename(src.cue_path))
                shutil.move(src.cue_path, new_cue)
                done_moves.append((new_cue, src.cue_path))
            moved.append(replace(src, image_path=new_image,
                                 music_dir=dest_dir, cue_path=new_cue))
    except OSError as exc:
        # A move failed — put everything back so the folder is unchanged.
        for now_at, was_at in reversed(done_moves):
            try:
                shutil.move(now_at, was_at)
            except OSError:
                pass
        return SplitResult(
            ok=False, reason="move_failed",
            message=f"Could not move a disc image into its subfolder: {exc}\n"
                    "All files were put back; nothing was split.")

    # --- Split each disc in place (verify + tag + trash per disc). ----------
    created: list[str] = []
    trashed: list[str] = []
    for i, src in enumerate(moved):
        log(f"  — Disc {src.disc_no} —")
        res = split_album(src, original_policy=original_policy, log=log)
        if not res.ok:
            done = ", ".join(f"Disc {s.disc_no}" for s in moved[:i])
            note = (f" Already split successfully: {done}." if done else "")
            return SplitResult(
                ok=False, reason=res.reason, created=created,
                message=(f"Disc {src.disc_no}: {res.message}\n"
                         f"Its image was left unsplit in 'Disc "
                         f"{src.disc_no}/'.{note}"))
        created += res.created
        if res.trashed:
            trashed.append(res.trashed)

    log(f"  ✔ All {len(moved)} disc(s) split — {len(created)} track(s) "
        f"in {subs}")
    return SplitResult(
        ok=True, reason="ok", created=created,
        trashed=", ".join(trashed) or None,
        message=(f"Split {len(moved)} disc image(s) into {len(created)} "
                 f"track(s) in {subs}"))
