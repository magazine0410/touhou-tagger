"""
touhoudb.py — TouhouDB (touhoudb.com) verification source for the standalone
tagger.

TouhouDB is **not** a primary metadata source.  It is queried only to:

  1. Verify that the staff names found on the source wiki (English Touhou
     Wiki or THBWiki) are also credited on TouhouDB — surfacing "missing
     members" that appear on one source but not the other.
  2. Supply *official romanizations* for Japanese/Chinese artist names, used
     for the ``artistsort`` and ``albumartist`` tags.  A TouhouDB romanization
     takes precedence over the THBWiki Staff-section mapping.
  3. Cross-check the album's release date and catalog number against the wiki
     values (verify-and-notify only — TouhouDB never overwrites them).

TouhouDB is built on the same platform as VocaDB and shares its public REST
API (https://touhoudb.com/api).  No authentication is needed for read-only
queries.  Like THBWiki, requests go through ``curl`` via ``subprocess`` to
keep the network layer stdlib-only and consistent with ``thwiki.py``.

Request etiquette (per VocaDB's published API guidance): a descriptive
User-Agent is sent, requests are rate-limited to roughly one per second, and
every lookup is cached for the lifetime of the client so the same name/album
is never fetched twice in a run.  The expensive per-song resolution used for
"auto-add missing members" is performed *only* when that toggle is enabled.
"""
import json
import subprocess
import time
import unicodedata
import urllib.parse

from external_tools import resolve_tool
from app_version import __version__ as _APP_VERSION

TOUHOUDB_API = "https://touhoudb.com/api"

# Descriptive UA so TouhouDB can identify the traffic source; version tracks the
# root VERSION file (see app_version.py).
_USER_AGENT = (
    f"TouhouTagger/{_APP_VERSION} (personal music tagging project; "
    "TouhouDB verification)"
)

# Be polite: one request per second is well within VocaDB's guidance.
_RATE_LIMIT = 1.0      # minimum seconds between requests
_TIMEOUT = 30          # per-request curl timeout (seconds)
_RETRY_MAX = 3
_RETRY_DELAY = 4.0     # initial backoff before first retry (seconds)
_RETRY_FACTOR = 2.0


# ---------------------------------------------------------------------------
# Cooperative hard-cancel hook
# ---------------------------------------------------------------------------
# Mirrors thwiki.set_cancel_check: lets the GUI's double-Cancel interrupt the
# (longer) TouhouDB backoff sleeps mid-album instead of waiting them out.
# Default None means no cancellation, so the CLI is unaffected.
_cancel_check = None


def set_cancel_check(predicate) -> None:
    """Register a zero-arg predicate consulted during retry/rate-limit waits.

    ``predicate()`` returns True once an immediate abort is requested; pass
    ``None`` to clear.  Safe to call from another thread (read-only access,
    atomic attribute swap under the GIL).
    """
    global _cancel_check
    _cancel_check = predicate


def _cancel_requested() -> bool:
    check = _cancel_check
    if check is None:
        return False
    try:
        return bool(check())
    except Exception:
        return False


def _interruptible_sleep(seconds: float, poll: float = 0.1) -> bool:
    """Sleep up to *seconds*, returning True if cut short by a cancel."""
    waited = 0.0
    while waited < seconds:
        if _cancel_requested():
            return True
        step = min(poll, seconds - waited)
        time.sleep(step)
        waited += step
    return _cancel_requested()


# ---------------------------------------------------------------------------
# Name / catalog / date normalization helpers
# ---------------------------------------------------------------------------
def _norm_name(text: str) -> str:
    """Aggressive normalization for cross-source name comparison.

    NFKC-folds width/compatibility variants, casefolds, and removes all
    whitespace so that ``"Foreground  Eclipse"`` and ``"Foreground Eclipse"``
    compare equal, and halfwidth/fullwidth kana differences collapse.
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).casefold()
    return "".join(s.split())


def _norm_catalog(text: str) -> str:
    """Normalize a catalog number to uppercase alphanumerics only.

    ``"ABCD-1234"`` and ``"abcd 1234"`` both reduce to ``"ABCD1234"`` so that
    formatting differences between the wikis and TouhouDB don't read as a
    mismatch.
    """
    if not text:
        return ""
    return "".join(ch for ch in text.upper() if ch.isalnum())


def _is_latin_script(text: str) -> bool:
    """True when ``text`` has no CJK/kana characters.

    Mirrors ``tag_io._is_latin_script`` (the tagger's canonical script test)
    so this module agrees with the rest of the pipeline on what counts as
    "already romanized".  Kept local to avoid an import cycle.
    """
    for ch in text:
        cp = ord(ch)
        if (
            0x3040 <= cp <= 0x30FF      # Hiragana / Katakana
            or 0x3400 <= cp <= 0x4DBF   # CJK Ext. A
            or 0x4E00 <= cp <= 0x9FFF   # CJK Unified Ideographs
            or 0xF900 <= cp <= 0xFAFF   # CJK Compatibility Ideographs
            or 0xFF66 <= cp <= 0xFF9F   # Halfwidth Katakana
        ):
            return False
    return True


def _parse_release_date(rd: dict | None) -> str | None:
    """Convert a VocaDB OptionalDateTime contract to ``YYYY[-MM[-DD]]``.

    VocaDB returns release dates as ``{"year": int|None, "month": int|None,
    "day": int|None, "isEmpty": bool, ...}``.  Returns the most precise
    string the data supports, or ``None`` when empty.
    """
    if not rd or rd.get("isEmpty"):
        return None
    year = rd.get("year")
    if not year:
        return None
    month = rd.get("month")
    day = rd.get("day")
    out = f"{int(year):04d}"
    if month:
        out += f"-{int(month):02d}"
        if day:
            out += f"-{int(day):02d}"
    return out


def _dates_match(wiki_date: str | None, tdb_date: str | None) -> bool:
    """Compare two ``YYYY[-MM[-DD]]`` strings at their coarser precision."""
    if not wiki_date or not tdb_date:
        return False
    a = wiki_date.split("-")
    b = tdb_date.split("-")
    n = min(len(a), len(b))
    return a[:n] == b[:n]


# ---------------------------------------------------------------------------
# Artist participation classification (mirrors the TouhouDB album sidebar)
# ---------------------------------------------------------------------------
# Album/song artist entries carry a comma-separated ``categories`` string
# ("Producer", "Vocalist", "Circle", "Subject", "Label", "Other"…) and a
# comma-separated ``roles`` string ("Arranger", "Composer", "Vocalist",
# "VoiceManipulator", "Default"…).  TouhouDB's album page groups artists into
# the same sections we reconstruct here:
#
#   Producers : category "Producer", or any of the Arranger/Composer/
#               VoiceManipulator roles  (this is the "Producers 涼織長月"
#               line in the sidebar — the arranger/composer, NOT the circle)
#   Vocalists : category "Vocalist", or the Vocalist role
#   Circle    : category "Circle"
#   Subject   : category "Subject"  (the Touhou character — excluded)
_PRODUCER_ROLES = {"arranger", "composer", "voicemanipulator"}


def _split_csv(value: str | None) -> set[str]:
    if not value:
        return set()
    return {p.strip().casefold() for p in value.split(",") if p.strip()}


def _classify(entry: dict) -> set[str]:
    """Return the set of section labels an artist entry belongs to.

    Labels: ``"producer"``, ``"vocalist"``, ``"circle"``, ``"subject"``.
    An entry may belong to several (e.g. a circle that also vocalizes).
    """
    cats = _split_csv(entry.get("categories"))
    roles = _split_csv(entry.get("roles"))
    labels: set[str] = set()
    if "producer" in cats or (roles & _PRODUCER_ROLES):
        labels.add("producer")
    if "vocalist" in cats or "vocalist" in roles:
        labels.add("vocalist")
    if "circle" in cats:
        labels.add("circle")
    if "subject" in cats:
        labels.add("subject")
    return labels


def _entry_name(entry: dict) -> str:
    """The credited display name for an album/song artist entry."""
    return (entry.get("name") or "").strip()


def _entry_all_names(entry: dict) -> set[str]:
    """All known name forms for an entry (credited name + the linked artist's
    primary and additional names), normalized for matching.

    Uses only what the ``fields=Artists`` response already contains — no extra
    per-artist request — so cross-source verification stays cheap.
    """
    names: set[str] = set()
    name = _entry_name(entry)
    if name:
        names.add(name)
    art = entry.get("artist") or {}
    if art.get("name"):
        names.add(art["name"].strip())
    extra = art.get("additionalNames") or ""
    for part in extra.split(","):
        part = part.strip()
        if part:
            names.add(part)
    return {_norm_name(n) for n in names if n}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class TouhouDBClient:
    """Read-only TouhouDB client using ``curl`` for transport.

    All lookups are cached on the instance, so creating one client per album
    run (or reusing one across a batch) keeps request volume to the minimum.
    """

    def __init__(self) -> None:
        self._last_request = 0.0
        # Title/slug strings used to confirm a name match in find_album.
        self._match_titles: list[str] = []
        # name (NFC-stripped) -> romanized str | None
        self._roman_cache: dict[str, str | None] = {}
        # album id -> {(disc, trackno): song_id}
        self._tracks_cache: dict[int, dict[tuple[int, int], int]] = {}
        # album id -> {(disc, trackno): track title}
        self._track_titles_cache: dict[int, dict[tuple[int, int], str]] = {}
        # song id -> {"producer": [names], "vocalist": [names]}
        self._song_artist_cache: dict[int, dict[str, list[str]]] = {}

    # -- transport ---------------------------------------------------------
    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < _RATE_LIMIT:
            _interruptible_sleep(_RATE_LIMIT - elapsed)

    def _get(self, path: str, params: dict) -> dict | None:
        """GET ``{API}{path}?{params}`` as JSON via curl, with rate limiting
        and exponential-backoff retry.  Returns the parsed dict or ``None``."""
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        url = f"{TOUHOUDB_API}{path}?{query}"

        delay = _RETRY_DELAY
        for attempt in range(1, _RETRY_MAX + 1):
            if attempt > 1 and _cancel_requested():
                print("  [TouhouDB] aborted by user (cancel).")
                return None
            self._rate_limit()
            try:
                curl = resolve_tool("curl")
                if not curl:
                    print("  [TouhouDB] curl is not installed or its "
                          "configured path is unavailable — TouhouDB "
                          "verification skipped")
                    return None
                result = subprocess.run(
                    [
                        curl, "-s", "-L",
                        "-H", f"User-Agent: {_USER_AGENT}",
                        "-H", "Accept: application/json",
                        url,
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_TIMEOUT,
                )
                self._last_request = time.monotonic()
                if result.returncode != 0:
                    print(f"  [TouhouDB] curl exited {result.returncode} "
                          f"(attempt {attempt}/{_RETRY_MAX})")
                elif not result.stdout.strip():
                    print(f"  [TouhouDB] empty response "
                          f"(attempt {attempt}/{_RETRY_MAX})")
                else:
                    try:
                        return json.loads(result.stdout)
                    except json.JSONDecodeError:
                        print(f"  [TouhouDB] non-JSON response "
                              f"(attempt {attempt}/{_RETRY_MAX})")
            except FileNotFoundError:
                print("  [TouhouDB] configured curl executable could not be "
                      "started — TouhouDB verification skipped")
                return None
            except subprocess.TimeoutExpired:
                self._last_request = time.monotonic()
                print(f"  [TouhouDB] timeout "
                      f"(attempt {attempt}/{_RETRY_MAX})")

            if attempt < _RETRY_MAX:
                if _interruptible_sleep(delay):
                    print("  [TouhouDB] aborted by user (cancel).")
                    return None
                delay *= _RETRY_FACTOR

        print(f"  [TouhouDB] giving up after {_RETRY_MAX} attempts: {url}")
        return None

    # -- name romanization -------------------------------------------------
    def romanize(self, jp_name: str) -> str | None:
        """Return TouhouDB's official romanization for a single name.

        Prefers an English name, then a Romaji name.  Confirms the queried
        Japanese name actually appears on the matched entry so a fuzzy search
        result can't introduce a wrong romanization.  Returns ``None`` when no
        confident romanization is found (caller should then fall back to the
        Staff-section map, then to the Japanese name).  Cached per name;
        names already in Latin script are returned unchanged without a query.
        """
        if not jp_name:
            return None
        if _is_latin_script(jp_name):
            return jp_name
        key = unicodedata.normalize("NFC", jp_name).strip()
        if key in self._roman_cache:
            return self._roman_cache[key]

        data = self._get(
            "/artists",
            {
                "query": jp_name,
                "nameMatchMode": "Exact",
                "fields": "Names",
                "maxResults": 10,
                "lang": "Default",
            },
        )
        result: str | None = None
        if data:
            for item in data.get("items", []):
                names = item.get("names", []) or []
                # Confirm the searched Japanese name is actually present.
                has_jp = any(
                    unicodedata.normalize("NFC", n.get("value", "")).strip() == key
                    for n in names
                    if n.get("language") == "Japanese"
                )
                if not has_jp:
                    continue
                by_lang = {
                    n["language"]: n["value"].strip()
                    for n in names
                    if n.get("value", "").strip()
                }
                for lang in ("English", "Romaji"):
                    val = by_lang.get(lang, "").strip()
                    if val and _is_latin_script(val):
                        result = val
                        break
                if result:
                    break

        self._roman_cache[key] = result
        return result

    # -- name-cache persistence -------------------------------------------
    def load_name_cache(self, cache: dict) -> int:
        """Seed the romanization cache from a previously exported dict.

        Long batches (``retag_credits.py``) run across several sessions, and
        at one request per second a cold cache re-queries every name each
        time.  Only well-formed string keys are accepted, so a corrupted or
        hand-edited cache file cannot inject a bogus romanization; a cached
        ``None`` (no romanization found) is preserved as such.
        """
        loaded = 0
        for key, value in (cache or {}).items():
            if not isinstance(key, str) or not key:
                continue
            if value is not None and (not isinstance(value, str)
                                      or not _is_latin_script(value)):
                continue
            self._roman_cache.setdefault(
                unicodedata.normalize("NFC", key).strip(), value)
            loaded += 1
        return loaded

    def export_name_cache(self) -> dict:
        """Return the romanization cache for persisting between runs."""
        return dict(self._roman_cache)

    # -- album lookup ------------------------------------------------------
    def find_album(
        self,
        *,
        album_title: str | None,
        slug: str | None,
        catalog_numbers: list[str] | None,
        date: str | None,
        circle_names: list[str] | None,
    ) -> dict | None:
        """Find the TouhouDB album matching the wiki data, or ``None``.

        Generates candidates from (1) the THBWiki Japanese title, (2) the
        romanized slug, and (3) the catalog number, then confirms a candidate
        with the strict rule in ``_score_album``.  Fails closed: anything
        short of a confident, unambiguous match returns ``None`` so the run
        proceeds on wiki data alone.
        """
        catalog_numbers = catalog_numbers or []
        circle_names = circle_names or []

        queries: list[str] = []
        for q in (
            album_title,
            (slug.replace("_", " ") if slug else None),
            (catalog_numbers[0] if catalog_numbers else None),
        ):
            q = (q or "").strip()
            if q and q not in queries:
                queries.append(q)

        seen_ids: set[int] = set()
        best: tuple[int, dict] | None = None  # (signal count, album)

        for q in queries:
            data = self._get(
                "/albums",
                {
                    "query": q,
                    "fields": "Artists",
                    "nameMatchMode": "Auto",
                    "maxResults": 10,
                    "lang": "Default",
                },
            )
            if not data:
                continue
            for item in data.get("items", []):
                aid = item.get("id")
                if aid in seen_ids:
                    continue
                seen_ids.add(aid)
                signals = self._score_album(
                    item, catalog_numbers, date, circle_names
                )
                if signals is None:
                    continue
                if best is None or signals > best[0]:
                    best = (signals, item)
            # A catalog-confirmed match (max signal weight) is decisive —
            # stop querying once we have one.
            if best is not None and best[0] >= 100:
                break

        return best[1] if best else None

    def _score_album(
        self,
        item: dict,
        catalog_numbers: list[str],
        date: str | None,
        circle_names: list[str],
    ) -> int | None:
        """Confidence score for an album candidate, or ``None`` to reject.

        Catalog match alone is decisive (weight 100).  Otherwise a name match
        is required *and* at least one corroborating signal (date or circle).
        Returns the additive signal weight so the caller can pick the
        best-corroborated candidate.
        """
        # --- Catalog (strong, near-unique) ---
        cat_match = False
        tdb_cat = _norm_catalog(item.get("catalogNumber") or "")
        if tdb_cat:
            wanted = {_norm_catalog(c) for c in catalog_numbers if c}
            cat_match = tdb_cat in wanted

        # --- Date (strong) ---
        tdb_date = _parse_release_date(item.get("releaseDate"))
        date_match = _dates_match(date, tdb_date)

        # --- Name (medium): match candidate's names (any language) against
        #     the wiki title/slug confirmation targets ---
        cand_names = {_norm_name(item.get("name") or "")}
        for part in (item.get("additionalNames") or "").split(","):
            part = part.strip()
            if part:
                cand_names.add(_norm_name(part))
        cand_names.discard("")
        name_targets = {
            _norm_name(t) for t in getattr(self, "_match_titles", []) if t
        }
        name_match = bool(cand_names & name_targets)

        # --- Circle (weak) ---
        circle_match = False
        if circle_names:
            wanted_circles = {_norm_name(c) for c in circle_names if c}
            for entry in item.get("artists", []) or []:
                if "circle" in _classify(entry):
                    if _entry_all_names(entry) & wanted_circles:
                        circle_match = True
                        break

        if cat_match:
            score = 100
            if date_match:
                score += 1
            if name_match:
                score += 1
            if circle_match:
                score += 1
            return score
        if name_match and (date_match or circle_match):
            return 10 + int(date_match) + int(circle_match)
        return None

    def set_match_titles(self, titles: list[str]) -> None:
        """Provide the title/slug strings used to confirm a name match.

        Set before calling :meth:`find_album`; keeps the name-comparison
        targets out of the candidate-generation queries (which intentionally
        use loose ``nameMatchMode=Auto``) while the confirmation stays strict.
        """
        self._match_titles = [t for t in titles if t]

    # -- per-song artists (auto-add missing members only) ------------------
    def _album_track_songs(self, album_id: int) -> dict[tuple[int, int], int]:
        """Map ``(disc, trackno) -> song_id`` for an album. Cached.

        A single ``/albums/{id}?fields=Tracks`` fetch also yields each track's
        title, so this populates :attr:`_track_titles_cache` in the same pass
        (consumed by :meth:`album_track_titles`) — no extra request.
        """
        if album_id in self._tracks_cache:
            return self._tracks_cache[album_id]
        data = self._get(
            f"/albums/{album_id}",
            {"fields": "Tracks", "lang": "Default"},
        )
        mapping: dict[tuple[int, int], int] = {}
        titles: dict[tuple[int, int], str] = {}
        if data:
            for tr in data.get("tracks", []) or []:
                disc = int(tr.get("discNumber") or 1)
                no = tr.get("trackNumber")
                if no is None:
                    continue
                key = (disc, int(no))
                song = tr.get("song") or {}
                sid = song.get("id")
                if sid is not None:
                    mapping[key] = int(sid)
                # Prefer the song's name; fall back to the track's own name
                # (some compilation entries carry a track-level title).
                name = (song.get("name") or tr.get("name") or "").strip()
                if name:
                    titles[key] = name
        self._tracks_cache[album_id] = mapping
        self._track_titles_cache[album_id] = titles
        return mapping

    def album_track_titles(
        self, album_id: int,
    ) -> dict[tuple[int, int], str]:
        """Map ``(disc, trackno) -> track title`` for an album. Cached.

        Used by the tagger's track-discrepancy check as a third reference
        (alongside the wiki and local titles).  Shares the single Tracks
        fetch with :meth:`_album_track_songs`, so calling both costs one
        request.
        """
        if album_id not in self._track_titles_cache:
            self._album_track_songs(album_id)
        return self._track_titles_cache.get(album_id, {})

    def song_credits(self, song_id: int) -> dict[str, list[str]]:
        """Return ``{"producer": [names], "vocalist": [names]}`` (Japanese
        credited names) for a song. Cached."""
        if song_id in self._song_artist_cache:
            return self._song_artist_cache[song_id]
        data = self._get(
            f"/songs/{song_id}",
            {"fields": "Artists", "lang": "Default"},
        )
        out: dict[str, list[str]] = {"producer": [], "vocalist": []}
        if data:
            for entry in data.get("artists", []) or []:
                if entry.get("isSupport"):
                    continue
                labels = _classify(entry)
                name = _entry_name(entry)
                if not name:
                    continue
                if "producer" in labels and name not in out["producer"]:
                    out["producer"].append(name)
                if "vocalist" in labels and name not in out["vocalist"]:
                    out["vocalist"].append(name)
        self._song_artist_cache[song_id] = out
        return out

    def track_extra_artists(
        self, album_id: int, disc: int, trackno: int,
    ) -> list[str]:
        """TouhouDB producer+vocalist names for one track (for auto-add).

        Used only when the *auto-add missing members* toggle is on.  Performs
        one rate-limited per-song request (cached).  Returns the Japanese
        names in producer-then-vocalist order.
        """
        songs = self._album_track_songs(album_id)
        sid = songs.get((disc, trackno))
        if sid is None and disc != 1:
            sid = songs.get((1, trackno))
        if sid is None:
            return []
        cr = self.song_credits(sid)
        ordered: list[str] = []
        for name in cr["producer"] + cr["vocalist"]:
            if name not in ordered:
                ordered.append(name)
        return ordered


# ---------------------------------------------------------------------------
# Album-level staff extraction (for verification)
# ---------------------------------------------------------------------------
def classify_album_staff(album: dict) -> dict[str, list[dict]]:
    """Bucket a matched album's ``artists`` into sidebar sections.

    Returns ``{"circle": [...], "producer": [...], "vocalist": [...]}`` where
    each value is a list of the raw artist entries (so callers can read both
    the credited name and all name forms).  The Subject category (the Touhou
    character) and pure "Other artists" (illustrators, instrumentalists) are
    excluded — only the people who feed the ``artist``/``albumartist`` tags
    are verified.
    """
    out: dict[str, list[dict]] = {
        "circle": [], "producer": [], "vocalist": [],
    }
    for entry in album.get("artists", []) or []:
        if entry.get("isSupport"):
            # Supporting artists are shown parenthesized on TouhouDB and are
            # not authoritative credits — skip for verification.
            continue
        labels = _classify(entry)
        for label in ("circle", "producer", "vocalist"):
            if label in labels:
                out[label].append(entry)
    return out


def find_missing_members(
    album: dict, wiki_staff_norm: set[str],
) -> list[str]:
    """Credited names of album staff absent from the wiki staff set.

    For each circle/producer/vocalist entry, an artist counts as present if
    *any* of its name forms (in any language) appears in the normalized wiki
    staff set; otherwise it's reported as a "missing member".  Returns the
    credited display names, de-duplicated, in section order.
    """
    buckets = classify_album_staff(album)
    missing: list[str] = []
    for label in ("circle", "producer", "vocalist"):
        for entry in buckets[label]:
            if _entry_all_names(entry) & wiki_staff_norm:
                continue
            name = _entry_name(entry)
            if name and name not in missing:
                missing.append(name)
    return missing


def release_date(album: dict) -> str | None:
    """The album's release date as ``YYYY[-MM[-DD]]``, or ``None``."""
    return _parse_release_date(album.get("releaseDate"))


def catalog_number(album: dict) -> str | None:
    """The album's catalog number string, or ``None`` when absent."""
    cat = (album.get("catalogNumber") or "").strip()
    return cat or None
