"""
thwiki.py — Fetch and parse album data from THBWiki (thwiki.cc).

Handles the asktrack REST API (via curl subprocess, since Python's urllib
gets its TLS connection dropped by THBWiki's server) and the rendered
HTML page (for album info, staff names, per-track credits, gap-filling
original titles, and a complete tracklist fallback when asktrack has not
indexed an album).

The asktrack API is not behind Cloudflare's challenge and still uses curl.
The rendered page, however, is gated behind Cloudflare's managed challenge
plus a SafeLine WAF, which only a real browser can clear.  A valid browser
cookie (THWIKI_COOKIE) is therefore **mandatory**: the page is fetched with
curl_cffi reusing that cookie, and there is no automated fallback.  If the
cookie is missing or stale the fetch raises ``ThwikiCookieError`` so the
caller can abort the run instead of silently degrading to API-only data.

The page is treated as the authoritative source: ``process_album`` in
``touhou_tagger.py`` cross-checks the asktrack scaffold against it and lets
the page correct, fill, and clear both original titles and per-track credits.
"""
import json
import os
import re
import subprocess
import time
import unicodedata
import urllib.parse

from bs4 import BeautifulSoup
from external_tools import resolve_tool

# Optional helper that pulls the live THBWiki cookie straight from a local
# browser, so THWIKI_COOKIE no longer has to be copy-pasted by hand.  Soft
# import: if the module (or its browser_cookie3 dependency) is absent, the
# manual-cookie path below works exactly as before.
try:
    import browser_cookie as _browser_cookie
except ImportError:
    _browser_cookie = None

THWIKI_API_URL = "https://thwiki.cc/rest/asktrack/v0/query"

# A lightweight, always-present page used to validate the cookie before a
# run starts.  Any rendered page is gated by the same WAF, so fetching the
# wiki home page and checking it is not a challenge confirms the cookie works.
THWIKI_HOME_URL = "https://thwiki.cc/"


class ThwikiCookieError(RuntimeError):
    """Raised when THBWiki can't be reached because the browser cookie is
    missing, expired, or otherwise rejected (a challenge page came back).

    A valid cookie is mandatory, so this is a **batch-fatal** condition: the
    caller should abort the whole run rather than silently degrade to the
    asktrack API alone.  It is deliberately distinct from a plain ``None``
    return (a transport error or an album that simply isn't on THBWiki),
    which is only a per-album soft failure.
    """

# Matches disc header labels used by THBWiki in multi-disc album tracklists,
# e.g. "Disk1(第一部)", "Disk2（第二部・第三部）", "DISC 3 - Bonus", "DISC-1".
# Used to detect disc-separator rows when parsing the rendered HTML page so
# that a bolded disc number like "Disk<b>1</b>(...)" is not mistaken for
# track number 1.
_DISC_HEADER_RE = re.compile(r'(?i)Dis[ck][\s\-]*(\d+)')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _td_text_preserving_breaks(td) -> str:
    """Return the text content of a cell with ``<br>`` rendered as newlines.

    BeautifulSoup's ``get_text()`` strips ``<br>`` entirely, so a cell
    containing two stacked producer names::

        <td>Alstroemeria Records<br/>森羅万象</td>

    would collapse to a single line.  This walks the cell's descendants
    and injects ``\\n`` wherever a ``<br>`` appears, leaving other text
    untouched.  Whitespace is not stripped here — callers are expected
    to split on newlines and strip each line themselves.
    """
    parts: list[str] = []
    for el in td.descendants:
        if isinstance(el, str):
            parts.append(str(el))
        elif getattr(el, "name", None) == "br":
            parts.append("\n")
    return "".join(parts)


def _expand_catalog_range(catno_str: str) -> list[str]:
    """Expand a slash-shorthand catalog range into the full list.

    Mirrors the THBWiki userscript's parser::

        'ABCD-12345'   → ['ABCD-12345']
        'ABCD-12345/6' → ['ABCD-12345', 'ABCD-12346']
        'ABCD-59/60'   → ['ABCD-59', 'ABCD-60']

    Returns a single-element list when the input doesn't match a clean
    range pattern (no slash, empty suffix, non-numeric suffix, or a
    numeric suffix that doesn't line up with the digits at the end of
    the first catno).  Real-world edge cases like ``ABCD-99/100`` —
    where the digit count crosses a power-of-10 boundary — fall into
    this fallback because the suffix can't be unambiguously substituted
    back into the prefix.
    """
    parts = catno_str.split("/")
    first = parts[0].strip()
    if len(parts) < 2 or not parts[1].strip():
        return [first]
    end_str = parts[1].strip()
    if not end_str.isdigit():
        return [first]
    end = int(end_str)
    if len(first) < len(end_str):
        return [first]
    start_suffix = first[-len(end_str):]
    if not start_suffix.isdigit():
        return [first]
    start = int(start_suffix)
    if end <= start:
        return [first]
    prefix = first[:-len(end_str)]
    result = [first]
    for i in range(start + 1, end + 1):
        # Pad to the same width as the original suffix so that
        # 'ABCD-09/10' expands to ['ABCD-09', 'ABCD-10'] rather than
        # ['ABCD-09', 'ABCD-9'].
        result.append(prefix + str(i).zfill(len(end_str)))
    return result


# ---------------------------------------------------------------------------
# Genre vocabulary translation
# ---------------------------------------------------------------------------
# THBWiki's album info box carries a "Genre" row (label "Genre" / "风格类型"
# / "ジャンル" depending on the page's template locale) whose values
# come from a small controlled vocabulary mixing English loan-terms (Rock,
# House, Trance, Jpop, …) and Chinese terms (金属, 嘻哈, …).  Multiple
# genres are separated with an enumeration comma ("House、Trance、民族").
#
# This table maps the known CJK vocabulary to conventional English genre
# names.  Latin values pass through unchanged; an unknown CJK value falls
# back to itself (the caller may log it), mirroring the theme-mapping
# fallback philosophy — a kept-original is recoverable, a wrong guess isn't.
#
# It also covers a few CJK genre terms that don't come from THBWiki at all,
# but appear pre-set in the original doujin/TLMC file tags (e.g. the
# traditional-character "東方アレンジ" that circles tag their own releases
# with).  These reach the table only via translate_genres.py, which re-reads
# existing genre tags — they never pass through the fetch-phase accumulator,
# since that only sees THBWiki-sourced genres.
GENRE_TRANSLATIONS: dict[str, str] = {
    # --- Chinese (THBWiki's usual locale) ---
    "流行":     "Pop",
    "摇滚":     "Rock",
    "金属":     "Metal",
    "电子":     "Electronic",
    "其他电子": "Electronic",
    "舞曲":     "Dance",
    "民族":     "Folk",
    "古典":     "Classical",
    "爵士":     "Jazz",
    # THBWiki's own help page (帮助:同人专辑) notes 硬核 means the
    # electronic-music Hardcore, not metal/rock hardcore.
    "硬核":     "Hardcore",
    "嘻哈":     "Hip-Hop",
    "说唱":     "Rap",
    "朋克":     "Punk",
    "后摇":     "Post-Rock",
    "纯音乐":   "Instrumental",
    "原声":     "Acoustic",
    "氛围":     "Ambient",
    "合唱":     "Choral",
    "蓝调":     "Blues",
    "乡村":     "Country",
    "雷鬼":     "Reggae",
    "灵魂":     "Soul",
    "放克":     "Funk",
    "独立":     "Indie",
    "独立音乐": "Indie",
    "另类":     "Alternative",
    "演歌":     "Enka",
    # 电波萌系 = denpa (電波) + moe (萌系); "Denpa" is the established
    # English name for this quirky Japanese otaku genre.
    "电波萌系": "Denpa",
    "游戏音乐": "Game Music",
    "其他":     "Other",
    # --- Japanese (JP-locale album templates) ---
    "ロック":       "Rock",
    "メタル":       "Metal",
    "ポップ":       "Pop",
    "ポップス":     "Pop",
    "エレクトロニカ": "Electronica",
    "テクノ":       "Techno",
    "トランス":     "Trance",
    "ハウス":       "House",
    "ジャズ":       "Jazz",
    "クラシック":   "Classical",
    "フォーク":     "Folk",
    "ヒップホップ": "Hip-Hop",
    "ダンス":       "Dance",
    "インストゥルメンタル": "Instrumental",
    "インスト":     "Instrumental",
    # --- Pre-existing doujin file tags (not THBWiki vocabulary) ---
    # Traditional-character / Japanese forms circles put in their own rips'
    # genre tags.  These describe the *source* (Touhou fan-arrangement)
    # rather than a musical style, but they're translated faithfully since
    # that's what the value literally says; retag them by hand if you'd
    # rather they carried a musical genre instead.
    "東方":         "Touhou",
    "東方アレンジ": "Touhou Arrange",
}

# Enumeration comma (、), full/half-width commas and semicolons, and the
# slash.  The interpunct (・) is deliberately NOT a separator — it joins
# words *within* one Japanese genre name (e.g. ドラムン・ベース).
_GENRE_SPLIT_RE = re.compile(r"[、，,；;/]")

# Hiragana, Katakana, CJK ideographs (incl. ext. A), and compatibility
# ideographs — the same coverage as tag_io's CJK detector (kept local
# so thwiki.py stays free of project imports beyond browser_cookie).
_GENRE_CJK_RE = re.compile(
    '['
    '\u3040-\u30FF'    # Hiragana + Katakana
    '\u3400-\u4DBF'    # CJK Unified Ideographs Extension A
    '\u4E00-\u9FFF'    # CJK Unified Ideographs
    '\uF900-\uFAFF'    # CJK Compatibility Ideographs
    ']'
)


def split_genres(value: str) -> list[str]:
    """Split an info-box Genre cell into individual genre names.

    NFKC-normalises first so full-width Latin ("Ｊｐｏｐ") folds to ASCII,
    then splits on the separator set and drops empties.
    """
    value = unicodedata.normalize("NFKC", value)
    return [p.strip() for p in _GENRE_SPLIT_RE.split(value) if p.strip()]


def translate_genre(name: str) -> str:
    """Translate one THBWiki genre term to English.

    Known CJK vocabulary is mapped via :data:`GENRE_TRANSLATIONS`;
    anything else (already-English loan-terms, unknown CJK) is returned
    unchanged.  Use :func:`genre_is_cjk` to tell an untranslated CJK
    value apart from a pass-through English one.
    """
    return GENRE_TRANSLATIONS.get(name, name)


def genre_is_cjk(name: str) -> bool:
    """True when *name* still contains CJK characters (untranslated)."""
    return _GENRE_CJK_RE.search(name) is not None


# English genre values the tagger *keeps* but never fetches from the wiki as a
# musical style: the doujin-provenance / release-type labels that rips commonly
# carry on their own (see the "Pre-existing doujin file tags" group above and
# library_stats._EXCLUDED_GENRES).  They're excluded from
# tagger_genre_vocabulary() so their mere presence isn't read as "the wiki
# genre fetch already ran on this album".
_NON_STYLE_GENRES = frozenset({"indie", "touhou", "touhou arrange"})


def tagger_genre_vocabulary() -> frozenset[str]:
    """Casefolded English genres the wiki genre-fetch writes as musical styles.

    The translated values of :data:`GENRE_TRANSLATIONS`, minus the
    provenance/release-type labels in :data:`_NON_STYLE_GENRES`.  Membership
    is a best-effort signal that an album has already had its genre fetched
    from the wiki — used by the GUI's "Skip genre-tagged on add" option.  It
    can't catch pass-through Latin genres the tagger writes verbatim that
    aren't in the map (e.g. "Jpop"), and it can false-positive on a
    pre-existing musical genre; both are accepted limits of the heuristic.
    """
    return frozenset(
        v.casefold() for v in GENRE_TRANSLATIONS.values()
        if v.casefold() not in _NON_STYLE_GENRES
    )


def _extract_wpg_names(wpg_list: list) -> list[str]:
    """Extract plain-string names from a list of WpgValue objects or strings."""
    names = []
    for item in wpg_list:
        if isinstance(item, dict):
            name = item.get("fulltext", "")
        else:
            name = str(item)
        if name:
            names.append(name)
    return names


# ---------------------------------------------------------------------------
# Slug normalisation for THBWiki
# ---------------------------------------------------------------------------
# Half-width ASCII symbols that THBWiki reliably renders full-width in page
# titles, mapped to their full-width (+0xFEE0) equivalents.  Deliberately a
# curated whitelist rather than "all punctuation": symbols like ``.`` and
# ``-`` are used inconsistently on THBWiki, so converting them would break as
# many lookups as it fixes.  Underscore is excluded too — it's the slug's
# space placeholder, which MediaWiki maps to a real space.
_THWIKI_FULLWIDTH_SYMBOLS = "/~?!&()+*:"


# The full-width counterparts of the curated symbols, for the reverse map.
_THWIKI_HALFWIDTH_SYMBOLS = "".join(
    chr(ord(ch) + 0xFEE0) for ch in _THWIKI_FULLWIDTH_SYMBOLS
)


def to_thwiki_fullwidth(name: str) -> str:
    """
    Map the curated set of half-width ASCII symbols to their full-width
    equivalents for THBWiki lookups.

    THBWiki page titles use full-width symbols where the English wiki uses
    plain ASCII — e.g. the album the English wiki slugs ``ANSWER//TALKER``
    lives at ``ANSWER／／TALKER`` on THBWiki.  Every THBWiki query (asktrack
    API + rendered page) runs the slug through this so the symbols match,
    while the English-wiki path keeps the ASCII form.
    """
    return "".join(
        chr(ord(ch) + 0xFEE0) if ch in _THWIKI_FULLWIDTH_SYMBOLS else ch
        for ch in name
    )


def to_thwiki_halfwidth(name: str) -> str:
    """
    Inverse of :func:`to_thwiki_fullwidth`: map the curated set of full-width
    symbols back to plain ASCII.  Used for the second lookup attempt, since
    THBWiki doesn't *always* use full-width symbols.
    """
    return "".join(
        chr(ord(ch) - 0xFEE0) if ch in _THWIKI_HALFWIDTH_SYMBOLS else ch
        for ch in name
    )


def _thwiki_slug_candidates(name: str) -> list[str]:
    """
    Ordered, de-duplicated THBWiki slug variants to try for one album:

      1. full-width symbols — the common THBWiki form (tried first);
      2. half-width ("normal") symbols — for the albums that don't use the
         full-width form;
      3. the slug exactly as supplied — so a manual override is always tried
         verbatim as a last resort, whatever symbols the user typed.

    Duplicates are dropped while preserving order, so a slug with no
    convertible symbols (or one already in the desired form) only produces a
    single lookup.
    """
    out: list[str] = []
    for cand in (to_thwiki_fullwidth(name), to_thwiki_halfwidth(name), name):
        if cand not in out:
            out.append(cand)
    return out


# ---------------------------------------------------------------------------
# asktrack API
# ---------------------------------------------------------------------------
def fetch_thwiki_tracks(album_name: str) -> list[dict]:
    """
    Fetch track data from THBWiki's asktrack API.
    Returns data in the same format as parse_tracklist(), extended with
    per-track credits:
    [{"number": int, "disc": int, "title": str, "original_titles": list[str],
      "arrangers": list[str], "vocalists": list[str], "lyricists": list[str]}, ...]
    The disc number comes from the API's discno field (defaults to 1
    for single-disc albums that omit it).  The original_titles will
    contain Japanese/mixed names as returned by THBWiki's ogmusicname
    field.  These should be translated via the theme mapping before
    writing to tags.

    Uses curl via subprocess because Python's urllib gets its TLS
    connection dropped by THBWiki's server (same fingerprint-based
    bot detection seen on the English wiki).

    THBWiki uses full-width symbols in album names more often than not, but
    not always, so each slug variant (full-width, then half-width, then the
    verbatim override — see :func:`_thwiki_slug_candidates`) is tried in turn
    and the first one that returns any tracks wins.
    """
    candidates = _thwiki_slug_candidates(album_name)
    for idx, candidate in enumerate(candidates):
        if idx > 0:
            print(f"  No THBWiki match for {album_name!r}; "
                  f"retrying as {candidate!r}…")
        tracks = _fetch_thwiki_tracks_one(candidate)
        if tracks:
            return tracks
    return []


def _fetch_thwiki_tracks_one(album_name: str) -> list[dict]:
    """Single asktrack API query for one exact album name (no slug variants)."""
    url = f"{THWIKI_API_URL}?limit=500"
    payload = json.dumps({
        "album": [album_name],
        "ogmusicname": None,
        "trackno": None,
        "name": None,
        "discno": None,
        "arrange": None,
        "vocal": None,
        "lyric": None,
    })

    try:
        curl = resolve_tool("curl")
        if not curl:
            print("  Error: curl is not installed or its configured path "
                  "is unavailable (required for THBWiki fallback)")
            return []
        result = subprocess.run(
            [
                curl, "-s", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", payload,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  THBWiki API error: curl exited with {result.returncode}")
            return []
        data = json.loads(result.stdout)
    except FileNotFoundError:
        print("  Error: configured curl executable could not be started "
              "(required for THBWiki fallback)")
        return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"  THBWiki API error: {exc}")
        return []

    results = data.get("results", [])
    if not results:
        return []

    tracks = []
    for entry in results:
        # trackno is a list of ints, e.g. [1]
        trackno_list = entry.get("trackno", [])
        if not trackno_list:
            continue
        track_num = int(trackno_list[0])

        # discno is a list of ints, e.g. [1]; default to 1 for
        # single-disc albums that omit it
        discno_list = entry.get("discno", [])
        disc_num = int(discno_list[0]) if discno_list else 1

        # name is a list of WpgValue objects or strings
        name_list = entry.get("name", [])
        if name_list:
            name_val = name_list[0]
            track_title = (
                name_val.get("fulltext", "")
                if isinstance(name_val, dict)
                else str(name_val)
            )
        else:
            track_title = ""

        # ogmusicname is a list of strings (the original theme names)
        original_titles = _extract_wpg_names(entry.get("ogmusicname", []))

        # Per-track credits (arrange, vocal, lyric)
        arrangers = _extract_wpg_names(entry.get("arrange", []))
        vocalists = _extract_wpg_names(entry.get("vocal", []))
        lyricists = _extract_wpg_names(entry.get("lyric", []))

        tracks.append({
            "number":          track_num,
            "disc":            disc_num,
            "title":           track_title,
            "original_titles": original_titles,
            "arrangers":       arrangers,
            "vocalists":       vocalists,
            "lyricists":       lyricists,
        })

    # Sort by (disc, track) for consistent ordering
    tracks.sort(key=lambda t: (t["disc"], t["number"]))
    return tracks


# ---------------------------------------------------------------------------
# THBWiki page HTML fetching
# ---------------------------------------------------------------------------
# Environment variables for the cookie-reuse fetch path:
#   THWIKI_COOKIE       — the verbatim Cookie header copied from a browser that
#                         has already passed THBWiki's Cloudflare challenge.
#                         Must include cf_clearance=...; the whole header string
#                         is fine (e.g. "cf_clearance=abc...; other=...").
#   THWIKI_UA           — the exact User-Agent of that same browser.  cf_clearance
#                         is bound to the UA, so this must match what the browser
#                         sent or Cloudflare will re-challenge.  Optional but
#                         strongly recommended.
#   THWIKI_IMPERSONATE  — the curl_cffi fingerprint profile to impersonate
#                         ("chrome" default; use "firefox"/"safari"/"edge" if the
#                         cookie was obtained from that browser family).
_THWIKI_COOKIE_ENV = "THWIKI_COOKIE"
_THWIKI_UA_ENV = "THWIKI_UA"
_THWIKI_IMPERSONATE_ENV = "THWIKI_IMPERSONATE"


def _looks_like_challenge(html: str) -> bool:
    """
    Heuristically detect a Cloudflare / SafeLine interstitial.

    THBWiki sits behind Cloudflare's *managed challenge* (the "Just a
    moment…" page) and, more recently, a SafeLine WAF layer.  Both serve
    an HTTP 200 with a challenge body rather than the real page, so a
    naive fetch "succeeds" while returning junk.  Callers use this to
    treat a challenge body as a fetch failure instead of silently parsing
    an empty tracklist.
    """
    if not html:
        return True
    # Strong, unambiguous challenge markers — these strings only ever occur on
    # a block page, so a bare substring match anywhere in the body is safe.
    needles = (
        "_cf_chl_opt",                   # Cloudflare challenge options blob
        "Enable JavaScript and cookies", # Cloudflare noscript text
        "SafeLine",                      # Chaitin SafeLine WAF branding
        "/_safeline/",                   # SafeLine challenge asset path
    )
    # NB: deliberately NOT matching the bare "cdn-cgi/challenge-platform"
    # path.  Cloudflare injects its *passive* JS-detection beacon
    # (/cdn-cgi/challenge-platform/scripts/jsd/main.js, alongside a
    # window.__CF$cv$params blob) into normally-served pages as well, so
    # matching that path flagged perfectly good pages as challenges — a false
    # positive that made the tagger discard valid fetches.  A genuine
    # interactive/managed challenge is identified by the _cf_chl_opt blob,
    # which is present only on the block page.
    if any(n in html for n in needles):
        return True
    # "Just a moment" is Cloudflare's interstitial, but it's also an ordinary
    # English phrase that appears verbatim as a track/song title on real album
    # pages (e.g. THBWiki's "Monsters" has a track named "Just a moment") — a
    # bare substring match there flagged the valid page as a challenge and
    # aborted the batch with a bogus ThwikiCookieError.  It's only a challenge
    # signal when it's the page <title>, so scope the check accordingly.
    title = re.search(r"<title[^>]*>(.*?)</title>", html,
                      re.IGNORECASE | re.DOTALL)
    return bool(title and "just a moment" in title.group(1).lower())


def _fetch_thwiki_via_cookie(url: str) -> BeautifulSoup | None:
    """
    Fetch a THBWiki page using a user-supplied browser cookie.

    THBWiki's pages sit behind a Cloudflare *interactive* Turnstile
    challenge that a headless or even headed automated browser cannot
    reliably clear (it loops the "verify you are human" checkbox).  The
    robust way around it is to solve the challenge once in a real browser
    and reuse the resulting ``cf_clearance`` cookie — but that cookie is
    bound to the browser's TLS/JA3 fingerprint, User-Agent, and IP, so a
    plain ``curl`` (whose TLS fingerprint differs from a browser's) gets
    re-challenged.  ``curl_cffi`` impersonates a real browser's
    TLS/JA3/HTTP2 fingerprint, so the cookie validates.

    Reads ``THWIKI_COOKIE`` (required), ``THWIKI_UA`` (recommended), and
    ``THWIKI_IMPERSONATE`` (default "chrome") from the environment.

    Returns a BeautifulSoup of the page on success, or ``None`` for a plain
    transport error (curl_cffi/curl failure, timeout) — a per-album soft
    failure the caller may tolerate.  Raises ``ThwikiCookieError`` when no
    cookie is configured, or when the fetch comes back still challenged
    after retrying (cookie expired, or UA/IP/fingerprint mismatch); that is
    a batch-fatal condition, since a valid cookie is mandatory.

    The cookie typically expires within 30–60 minutes; when it does,
    re-copy it (and the matching User-Agent) from the browser.
    """
    # Best-effort: pull the current cookie straight from the browser into the
    # environment before reading it, so a manual copy-paste isn't needed and a
    # cookie that has rotated since the run started is picked up.  A no-op if
    # the helper or browser_cookie3 is unavailable; never clears a manual value.
    if _browser_cookie is not None:
        _browser_cookie.refresh_env(announce=True)

    cookie = os.environ.get(_THWIKI_COOKIE_ENV, "").strip()
    if not cookie:
        raise ThwikiCookieError(
            "No THBWiki cookie configured. A valid browser cookie is now "
            f"required for every run: set {_THWIKI_COOKIE_ENV} (and "
            f"{_THWIKI_UA_ENV}) — in the GUI use the 'THBWiki "
            "Authentication…' dialog, or export the variables in your shell. "
            "Open any THBWiki page in your browser, pass the human check, "
            "then copy the Cookie header and User-Agent from DevTools."
        )

    ua = os.environ.get(_THWIKI_UA_ENV, "").strip()
    impersonate = (
        os.environ.get(_THWIKI_IMPERSONATE_ENV, "").strip() or "chrome"
    )

    def _build_headers() -> dict[str, str]:
        # Read the cookie from the env each time so a refresh between retries
        # (below) is honoured; UA / Accept-Language are stable.
        hdrs = {"Cookie": os.environ.get(_THWIKI_COOKIE_ENV, "").strip()}
        if ua:
            hdrs["User-Agent"] = ua
        # A realistic accompanying header reduces the chance of a re-challenge.
        hdrs.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        return hdrs

    print(f"  Fetching THBWiki page HTML (cookie + curl_cffi "
          f"impersonate={impersonate}): {url}")

    # curl_cffi is strongly preferred (its TLS/JA3 fingerprint matches the
    # browser that obtained cf_clearance).  Plain curl is a last-resort
    # fallback that usually fails on fingerprint, but is better than nothing.
    try:
        from curl_cffi import requests as cffi_requests
    except ImportError:
        cffi_requests = None
        print("  (curl_cffi not installed — falling back to plain curl, "
              "which usually fails because its TLS fingerprint won't match "
              "the browser that obtained the cookie. Install it with: "
              "pip install --user curl_cffi)")

    def _attempt(headers: dict[str, str]) -> str | None:
        """One fetch attempt; returns the response body or None on error."""
        if cffi_requests is not None:
            try:
                resp = cffi_requests.get(
                    url,
                    headers=headers,
                    impersonate=impersonate,
                    timeout=30,
                )
                return resp.text
            except Exception:
                # Do not print a transport exception here: some clients put
                # the complete request command/headers in their error text.
                # That could expose the Cookie header in a GUI log.
                print("  THBWiki cookie fetch error (curl_cffi).")
                return None
        # Plain-curl fallback
        curl = resolve_tool("curl")
        if not curl:
            print("  THBWiki cookie fetch error: curl is not installed or "
                  "its configured path is unavailable.")
            return None
        cmd = [curl, "-s", "-L", url]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30,
            )
        except FileNotFoundError:
            print("  THBWiki cookie fetch error: configured curl executable "
                  "could not be started.")
            return None
        except subprocess.TimeoutExpired:
            # TimeoutExpired may include the entire curl command, including
            # its Cookie header, so never format the exception into output.
            print("  THBWiki cookie fetch timed out.")
            return None
        return result.stdout

    # Cloudflare's bot-scoring is probabilistic: a valid cookie can still
    # be re-challenged on the first request after an idle period, while an
    # immediate retry rides through.  So retry a few times with a short
    # backoff before concluding the cookie is genuinely stale.  We track
    # whether failures were challenges (cookie problem -> raise) or plain
    # transport errors (network blip / curl_cffi missing -> soft None).
    max_attempts = 4
    saw_challenge = False
    for attempt in range(1, max_attempts + 1):
        html = _attempt(_build_headers())
        if html is None:
            pass  # transport error — neither success nor a challenge body
        elif not _looks_like_challenge(html):
            if attempt > 1:
                print(f"  (cleared on attempt {attempt})")
            return BeautifulSoup(html, "html.parser")
        else:
            saw_challenge = True
        if attempt < max_attempts:
            # 1.5s, 3s, 4.5s — brief, since a usable cookie usually clears
            # within a couple of tries.
            delay = 1.5 * attempt
            print(f"  Re-challenged (attempt {attempt}/{max_attempts}); "
                  f"retrying in {delay:.0f}s…")
            time.sleep(delay)
            # A re-challenge usually means the cookie has rotated.  Force a
            # fresh pull from the browser (bypassing the TTL) so the next
            # attempt uses the current cookie — this is the automatic recovery
            # for "the cookie went stale mid-run".  No-op without the helper.
            if html is not None and _looks_like_challenge(html) \
                    and _browser_cookie is not None:
                _browser_cookie.refresh_env(force=True, announce=True)

    if saw_challenge:
        raise ThwikiCookieError(
            f"THBWiki still returned a challenge page after {max_attempts} "
            "attempts — the cookie has likely expired, or the User-Agent / "
            "IP / TLS fingerprint doesn't match the browser that obtained "
            f"it (also check that curl_cffi is installed). Re-copy "
            f"{_THWIKI_COOKIE_ENV} (and {_THWIKI_UA_ENV}) from your browser "
            "and ensure THWIKI_IMPERSONATE matches its family."
        )

    # No challenge ever seen — every attempt was a transport error.  Treat
    # as a per-album soft failure (the cookie itself may be fine).
    print("  THBWiki page fetch failed (network / transport error).")
    return None


def _fetch_thwiki_page_html(
    album_name: str,
) -> BeautifulSoup | None:
    """
    Fetch the rendered THBWiki album page and return a BeautifulSoup
    object.  This is the single network call for all THBWiki HTML parsing
    (album info, staff, per-track titles/credits) and the authoritative
    source the asktrack scaffold is cross-checked against.

    THBWiki's rendered pages are gated behind Cloudflare's challenge (an
    interactive Turnstile "verify you are human" checkbox) plus a SafeLine
    WAF.  Only a real browser can clear it, so a valid browser cookie
    (``THWIKI_COOKIE``) is **mandatory** — it is reused via curl_cffi.  The
    asktrack REST API is *not* challenged and still uses curl elsewhere in
    this module.

    THBWiki uses full-width symbols in page titles more often than not, but
    not always, so each slug variant (full-width, then half-width, then the
    verbatim override — see :func:`_thwiki_slug_candidates`) is tried in turn.
    The first variant that resolves to a real album page (one with an info box
    / tracklist / staff section) wins; if none clearly resolves, the first
    successfully-fetched page is returned so behaviour matches the old
    single-fetch path.

    Returns:
      * a ``BeautifulSoup`` of the page on success;
      * ``None`` on a transport error or when the album simply isn't on
        THBWiki (a non-challenge "no such page" body) — a per-album soft
        failure the caller may tolerate.

    Raises ``ThwikiCookieError`` when no cookie is configured or the page
    comes back still challenged — a batch-fatal condition the caller should
    abort on rather than degrade to API-only data.
    """
    candidates = _thwiki_slug_candidates(album_name)
    first_soup: BeautifulSoup | None = None
    for idx, candidate in enumerate(candidates):
        if idx > 0:
            print(f"  No THBWiki page for {album_name!r}; "
                  f"retrying as {candidate!r}…")
        album_url = (
            f"https://thwiki.cc/{urllib.parse.quote(candidate, safe='')}"
        )
        # A ThwikiCookieError propagates straight out — it's the same cookie
        # for every candidate, so retrying other slugs would fail identically.
        soup = _fetch_thwiki_via_cookie(album_url)
        if soup is None:
            continue  # transport error — try the next variant
        if first_soup is None:
            first_soup = soup
        if _thwiki_page_exists(soup):
            return soup
    # None of the variants resolved to a recognisable album page: return the
    # first page we did fetch (preserving the old behaviour, where the caller
    # parses it and simply finds no data), or None if all transport-errored.
    return first_soup


def _thwiki_page_exists(soup: BeautifulSoup) -> bool:
    """
    True if ``soup`` looks like a real THBWiki album page rather than a
    MediaWiki "no such page" / redlink page.  Keyed on the album content
    structures the parsers consume (info box, tracklist, or staff section);
    a missing-article page has none of them.
    """
    return bool(
        soup.find("table", class_="doujininfo")
        or soup.find("table", class_="musicTable")
        or soup.find("table", class_="stafflist")
    )


def validate_thwiki_cookie() -> None:
    """Verify that a usable THBWiki browser cookie is configured.

    A valid cookie is mandatory for every run, so this is meant to be
    called once up front — before any album is fetched or any file is
    tagged — so the run can fail fast with a clear message instead of
    discovering the problem partway through.

    Fetches a known-stable THBWiki page (the wiki home page, gated by the
    same WAF as album pages) and confirms it is not a challenge.  Raises
    ``ThwikiCookieError`` if the cookie is missing, expired, or rejected,
    or if THBWiki can't be reached at all to confirm it.  Returns ``None``
    on success.
    """
    print("Validating THBWiki cookie…")
    soup = _fetch_thwiki_via_cookie(THWIKI_HOME_URL)
    if soup is None:
        # Transport error during validation — we can't confirm the cookie
        # works, and nothing downstream will either, so fail loudly.
        raise ThwikiCookieError(
            "Couldn't reach THBWiki to validate the cookie (network or "
            "transport error). Check your connection and that curl_cffi is "
            "installed, then try again."
        )
    print("  THBWiki cookie OK.")


# ---------------------------------------------------------------------------
# HTML tracklist extraction
# ---------------------------------------------------------------------------
def _thwiki_track_tables(soup: BeautifulSoup) -> list:
    """Return the rendered THBWiki tables that contain track rows.

    Current album pages normally use ``musicTable``.  Older and some
    localized templates render the same rows as a plain ``wikitable``.  The
    ``info[A-Z]`` check excludes the album info box and staff tables from the
    latter fallback.
    """
    tables = soup.find_all("table", class_="musicTable")
    if tables:
        return tables
    return [
        table for table in soup.find_all("table", class_="wikitable")
        if table.find("td", class_=re.compile(r'^info[A-Z]'))
    ]


def _iter_thwiki_track_rows(soup: BeautifulSoup):
    """Yield ``(disc, number, row, starts_track)`` for track-table rows.

    A track's number appears only on its first row; following rows carry its
    Original Title and credit fields.  ``starts_track`` distinguishes the
    numbered row from those continuation rows, while all rows retain the
    current track key for the existing title/credit parsers.
    """
    tables = _thwiki_track_tables(soup)
    auto_disc = 0

    for table in tables:
        # Separate tables are usually introduced by a DISC/Disk heading.  If
        # the heading names a source album instead, page order still gives us
        # a stable disc number.
        auto_disc += 1
        current_disc = auto_disc
        current_track: int | None = None
        for sibling in table.previous_siblings:
            if not hasattr(sibling, "name") or sibling.name is None:
                continue
            if sibling.name in ("h2", "h3"):
                dm = _DISC_HEADER_RE.search(sibling.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    auto_disc = current_disc
                break
            if sibling.name not in ("br", "p", "div", "span"):
                break

        for tr in table.find_all("tr"):
            # A single-table multi-disc layout uses separator rows such as
            # ``Disk1`` or ``DISC-2``.  Check these before interpreting the
            # bold number inside the label as a track number.
            th = tr.find("th")
            if th:
                dm = _DISC_HEADER_RE.search(th.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue

            starts_track = False
            info_td = tr.find(
                "td", class_=re.compile(r'^info[A-Z]'))
            if info_td:
                cell_text = info_td.get_text().strip()
                dm = _DISC_HEADER_RE.search(cell_text)
                if dm and not cell_text.isdigit():
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue

                bold = info_td.find("b")
                if bold:
                    try:
                        current_track = int(bold.get_text().strip())
                        starts_track = True
                    except ValueError:
                        pass

            if current_track is not None:
                yield current_disc, current_track, tr, starts_track


def _extract_thwiki_track_title(tr, info_td) -> str:
    """Extract the title cell from a numbered track row.

    THBWiki has used both ``title`` and generic ``text`` classes for this
    cell.  The numbered cell and duration cells use ``info[A-Z]`` classes;
    the first remaining non-label cell is therefore the least template-
    dependent title candidate.
    """
    duration_re = re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?$')
    for td in tr.find_all("td", recursive=False):
        if td is info_td:
            continue
        classes = td.get("class", [])
        if "label" in classes or any(
                re.match(r'^info[A-Z]', cls) for cls in classes):
            continue
        text = " ".join(td.stripped_strings).strip()
        if not text or duration_re.fullmatch(text):
            continue
        # A few old templates put the duration in the same cell as the title.
        text = re.sub(
            r'\s*\d{1,2}:\d{2}(?::\d{2})?\s*$', '', text).strip()
        if text:
            return text
    return ""


# HTML title extraction
# ---------------------------------------------------------------------------
def _parse_thwiki_html_titles(
    soup: BeautifulSoup,
) -> tuple[dict[tuple[int, int], list[str]], set[tuple[int, int]]]:
    """
    Extract original theme names from a pre-fetched THBWiki album page.
    Returns a tuple of:
    - ``{(disc_number, track_number): [japanese_theme_name, …]}`` —
      only tracks that have original titles on the page.
    - ``{(disc_number, track_number), …}`` — **all** tracks seen in
      the HTML tracklist, including those without original titles.
      This lets callers distinguish "track is an original composition"
      (present in ``tracks_seen`` but absent from ``track_titles``)
      from "track wasn't found in the HTML at all".
    """
    track_titles: dict[tuple[int, int], list[str]] = {}
    tracks_seen: set[tuple[int, int]] = set()

    # Some multi-disc albums use separate <table> elements per disc,
    # preceded by <h2>/<h3> headings like "DISC-1", "DISC-2".  Others
    # use a single table with internal disc-header rows (<th> or
    # <td class="info*">).  We handle both by iterating per-table and
    # checking preceding headings for an external disc number, then
    # letting the per-row logic detect any internal disc headers.
    tables = soup.find_all("table", class_="musicTable")
    if not tables:
        # Some pages use plain "wikitable" without the musicTable class.
        # Exclude non-tracklist wikitables — notably the album info box (also a
        # wikitable, class "doujininfo") and the staff tables — by keeping only
        # those with a track row (a td.info[A-Z] cell).  Otherwise the
        # sequential disc counter would count the info box as disc 1 and shift
        # every real track onto disc 2, so the (disc, number) cross-check misses.
        tables = [
            t for t in soup.find_all("table", class_="wikitable")
            if t.find("td", class_=re.compile(r'^info[A-Z]'))
        ]
    if not tables:
        return track_titles, tracks_seen

    # Sequential disc counter: when a separate-table-per-disc album uses
    # section headings that don't carry an explicit disc number — e.g.
    # compilation albums that label each section by its source album
    # ("from 幻想パブ：午後7時") instead of "DISC 1" — number the tables
    # by page order so each section becomes its own disc instead of all
    # collapsing onto disc 1.  An explicit "Disc N" heading still wins
    # and re-syncs the counter; a single-table album still gets disc 1.
    auto_disc = 0
    for table in tables:
        # --- External disc header detection ---
        # Walk backwards through preceding siblings to find the nearest
        # heading (h2/h3) with a disc label like "DISC-1", "DISC 2",
        # "Disk1(第一部)", etc.  Skip whitespace-only text nodes and
        # minor elements (br, p, div) that may sit between the heading
        # and the table.
        auto_disc += 1
        current_disc: int = auto_disc
        current_track: int | None = None
        for sibling in table.previous_siblings:
            # Skip NavigableString nodes (whitespace between elements)
            if not hasattr(sibling, "name") or sibling.name is None:
                continue
            if sibling.name in ("h2", "h3"):
                dm = _DISC_HEADER_RE.search(sibling.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    auto_disc = current_disc
                break
            # Stop at block-level elements that aren't headings — the
            # heading, if any, must be the closest block-level sibling.
            if sibling.name not in ("br", "p", "div", "span"):
                break

        for tr in table.find_all("tr"):
            # --- Internal disc header detection ---
            # Multi-disc albums that use a single table have separator
            # rows labelled "Disk1(第一部)", "Disk2（第二部・第三部）", etc.
            # These may appear as <th> cells or as <td class="info*">
            # cells.  We must identify them *before* trying to parse
            # the bold text as a track number — otherwise a label
            # rendered as "Disk<b>1</b>(...)" would be mistaken for
            # track 1, corrupting all original-title lookups that
            # follow.

            # Strategy A: <th> containing a disc-label pattern
            th = tr.find("th")
            if th:
                dm = _DISC_HEADER_RE.search(th.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue

            # Strategy B: info td whose full text matches a disc-label
            # pattern (but is not a bare integer — those are real track
            # numbers)
            info_td = tr.find("td", class_=re.compile(r'^info[A-Z]'))
            if info_td:
                cell_text = info_td.get_text().strip()
                dm = _DISC_HEADER_RE.search(cell_text)
                if dm and not cell_text.isdigit():
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue
                # Normal track row: extract the bold track number
                bold = info_td.find("b")
                if bold:
                    try:
                        current_track = int(bold.get_text().strip())
                        tracks_seen.add((current_disc, current_track))
                    except ValueError:
                        pass

            if current_track is None:
                continue

            # Original title row: accept both English and Chinese labels
            label_td = tr.find("td", class_="label")
            if not label_td:
                continue
            label_text = label_td.get_text().strip()
            if label_text not in ("Original Title", "原曲"):
                continue

            text_td = tr.find("td", class_="text")
            if not text_td:
                continue

            titles = []
            for div in text_td.find_all("div", class_="ogmusic"):
                title_text = div.get_text().strip()
                if title_text:
                    titles.append(title_text)
            if titles:
                track_titles[(current_disc, current_track)] = titles

    return track_titles, tracks_seen


# ---------------------------------------------------------------------------
# THBWiki album info parsing (catalog number, release date)
# ---------------------------------------------------------------------------
def parse_thwiki_album_info(soup: BeautifulSoup) -> dict:
    """
    Parse the album info box from THBWiki's rendered page.

    Returns a dict with keys:

    ``catalog_numbers``
        ``list[str]`` — one entry per medium, expanded from any
        slash-shorthand range (``ABCD-12345/6`` → ``['ABCD-12345',
        'ABCD-12346']``).  Empty list when absent.
    ``date``
        ``str | None`` — ``YYYY``, ``YYYY-MM`` or ``YYYY-MM-DD``.
    ``album``
        ``str | None`` — the album's display title, as shown on
        THBWiki.  May contain Japanese characters.
    ``album_artists``
        ``list[str]`` — producer names in the order they appear on the
        page.  Pages with multiple producers stack them with ``<br>``,
        which is preserved here.  Names are returned in their
        canonical (often Japanese) form; the caller is expected to
        apply ``parse_thwiki_staff_names()``'s mapping to romanise
        them before writing.
    ``genres``
        ``list[str]`` — genre names exactly as they appear on the page
        (mixed English loan-terms and CJK vocabulary), split on the
        enumeration separators.  The caller is expected to translate
        them via :func:`translate_genre` before writing.  Empty list
        when the page has no Genre row.

    The info box is typically a ``<table>`` (class varies across album
    templates) containing ``<td class="label">`` cells.  Labels appear
    in English or Chinese depending on album locale (e.g. "Catalog ID"
    vs "编号").  Rather than relying on a specific table class name,
    this function searches all ``<td class="label">`` cells on the page
    — the label text matching is restrictive enough to avoid false
    positives from the tracklist section.
    """
    info: dict = {
        "catalog_numbers": [],
        "date":            None,
        "album":           None,
        "album_artists":   [],
        "genres":          [],
    }

    # Search every label cell on the page — the info box, tracklist,
    # and staff section all use class="label", but we filter by the
    # specific label strings we care about.
    #
    # THBWiki uses multiple album templates with inconsistent labels:
    # some pages use English ("Release", "Catalog ID"), others use
    # Chinese ("首发日期", "发售日期", "编号"), and Japanese-locale
    # pages use a third set ("タイトル", "メーカー", "型番", "発売日"
    # — the latter two are handled at the call site since they appear
    # under different keys in some templates).  We accept all known
    # variants.
    _CATALOG_LABELS = {
        "Catalog ID", "CatalogID", "编号", "编号ID", "品番",
    }
    _RELEASE_LABELS = {
        "Release", "发售日期", "发售", "首发日期", "首发",
    }
    _ALBUM_LABELS = {
        "Title", "名称", "タイトル",
    }
    _ARTIST_LABELS = {
        "Producer", "制作方", "メーカー",
    }
    # "风格类型" is the album-level field per THBWiki's own help page
    # (帮助:同人专辑 §专辑信息).  "曲风", also documented there, is a
    # *separate*, per-track field (§曲目列表) that happens to share the
    # same vocabulary — it must NOT be in this set, since find_all below
    # scans the whole page and would otherwise pick up a track's style
    # as if it were the album's, clobbering the real genre with
    # whichever track's 曲风 cell was seen last.
    _GENRE_LABELS = {
        "Genre", "风格类型", "风格", "ジャンル",
    }
    _ALL_WANTED = (
        _CATALOG_LABELS | _RELEASE_LABELS
        | _ALBUM_LABELS | _ARTIST_LABELS | _GENRE_LABELS
    )

    for label_td in soup.find_all("td", class_="label"):
        label = label_td.get_text().strip()

        # Quick reject: only process labels we're interested in
        if label not in _ALL_WANTED:
            continue

        # The value is in the next <td> sibling (not the label itself)
        value_td = label_td.find_next_sibling("td")
        if not value_td:
            continue

        # Producer cells stack multiple artists with <br>, which
        # BS4's get_text() drops — use the br-preserving extractor.
        if label in _ARTIST_LABELS:
            raw = _td_text_preserving_breaks(value_td)
            names = [
                line.strip() for line in raw.split("\n")
                if line.strip()
            ]
            if names:
                info["album_artists"] = names
            continue

        value = value_td.get_text().strip()
        if not value:
            continue

        if label in _CATALOG_LABELS:
            # Expand slash-shorthand ranges (e.g. "ABCD-12345/6") into
            # individual catnos.  Stored as a list so the caller can
            # do per-disc matching for multi-disc box sets.
            info["catalog_numbers"] = _expand_catalog_range(value)
        elif label in _RELEASE_LABELS:
            # Extract just the date: "2006-10-01 （SunshineCreation33）"
            # The \xa0 is the non-breaking space from &#160;
            date_match = re.match(r'(\d{4}(?:-\d{2}(?:-\d{2})?)?)', value)
            if date_match:
                info["date"] = date_match.group(1)
        elif label in _ALBUM_LABELS:
            info["album"] = value
        elif label in _GENRE_LABELS:
            info["genres"] = split_genres(value)

    return info


# ---------------------------------------------------------------------------
# THBWiki staff section parsing (name mapping + album-level credits)
# ---------------------------------------------------------------------------
def parse_thwiki_staff_names(
    soup: BeautifulSoup,
) -> dict[str, str]:
    """
    Build a Japanese → romanized name mapping from THBWiki's Staff section.

    The Staff section uses ``<p><b>Role</b></p>`` headers followed by
    ``<div class="stafflist-wrapper"><table class="stafflist">`` tables.
    Each row typically has ``[Japanese name, Romanized name, Track range]``
    in separate ``<td>`` cells.  This function extracts the first and
    second ``<td>`` texts as a name pair.

    Also picks up names from ``<dl><dt>Role</dt><dd>Name</dd>`` entries
    outside stafflist tables: if an ``<a>`` tag in a ``<dd>`` has a
    ``title`` attribute that differs from its visible text, the ``title``
    is treated as the Japanese name and the visible text as romanized.

    Returns ``{japanese_name: romanized_name}`` for every name where a
    distinct romanized form is available.  Names that are already in
    Latin script appear in both positions and should be treated as
    identity mappings (i.e. no translation needed).
    """
    name_map: dict[str, str] = {}

    # --- Stafflist tables ---
    for wrapper in soup.find_all("div", class_="stafflist-wrapper"):
        table = wrapper.find("table", class_="stafflist")
        if not table:
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            jp_name = cells[0].get_text().strip()
            roman_name = cells[1].get_text().strip()
            if jp_name and roman_name and jp_name != roman_name:
                name_map[jp_name] = roman_name

    # --- Definition list entries (e.g. Guitar, Mixing, etc.) ---
    for dd in soup.find_all("dd"):
        for a_tag in dd.find_all("a"):
            title = a_tag.get("title", "").strip()
            visible = a_tag.get_text().strip()
            if title and visible and title != visible:
                # title= often contains the page name, which may be
                # the Japanese or canonical form
                name_map.setdefault(title, visible)

    return name_map


def parse_thwiki_album_staff(
    soup: BeautifulSoup,
) -> dict[str, list[str]]:
    """
    Parse album-level staff credits from THBWiki's Staff section.

    Returns ``{"arrangement": [name, …], "vocal": [name, …],
    "lyrics": [name, …]}``.  Only the three music-relevant roles are
    extracted.  Names are the Japanese ``fulltext`` forms (matching
    the asktrack API output); use ``parse_thwiki_staff_names()`` to
    get a romanization mapping.

    The staff section has ``<p><b>Arrangement</b></p>`` (or Chinese
    equivalents) followed by stafflist tables.
    """
    staff: dict[str, list[str]] = {
        "arrangement": [],
        "vocal": [],
        "lyrics": [],
    }
    _ROLE_MAP = {
        "arrangement":  "arrangement",
        "编曲":          "arrangement",
        "arrange":       "arrangement",
        "vocal":         "vocal",
        "演唱":          "vocal",
        "lyrics":        "lyrics",
        "作词":          "lyrics",
        "作詞":          "lyrics",
    }

    # Walk <p><b>Role</b></p> + following stafflist-wrapper pairs
    for bold in soup.find_all("b"):
        role_text = bold.get_text().strip().lower()
        role_key = _ROLE_MAP.get(role_text)
        if not role_key:
            continue

        # The stafflist table follows the <p> containing this <b>
        p_parent = bold.parent
        if not p_parent:
            continue
        wrapper = p_parent.find_next_sibling("div", class_="stafflist-wrapper")
        if not wrapper:
            continue
        table = wrapper.find("table", class_="stafflist")
        if not table:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            # First cell is the canonical (Japanese) name
            name = cells[0].get_text().strip()
            if name and name not in staff[role_key]:
                staff[role_key].append(name)

    return staff


# ---------------------------------------------------------------------------
# THBWiki per-track credits from HTML (fallback for asktrack gaps)
# ---------------------------------------------------------------------------
def _parse_thwiki_html_credits(
    soup: BeautifulSoup,
) -> dict[tuple[int, int], dict[str, list[str]]]:
    """
    Parse per-track arranger/vocalist/lyricist from THBWiki's rendered
    tracklist.  Works alongside ``_parse_thwiki_html_titles`` — walks
    the same ``<tr>`` rows but looks for credit labels instead of
    "Original Title".

    Returns ``{(disc, track): {"arrange": [...], "vocal": [...],
    "lyric": [...]}}`` for tracks where at least one credit is found.
    """
    _CREDIT_LABELS = {
        "Arrange":       "arrange",
        "编曲":          "arrange",
        "Vocal":         "vocal",
        "演唱":          "vocal",
        "Lyrics":        "lyric",
        "作词":          "lyric",
        "作詞":          "lyric",
    }

    credits: dict[tuple[int, int], dict[str, list[str]]] = {}

    # Per-table iteration with external disc header detection — same
    # strategy as _parse_thwiki_html_titles (see its docstring).
    tables = soup.find_all("table", class_="musicTable")
    if not tables:
        # Mirror _parse_thwiki_html_titles: keep only wikitables with a track
        # row (td.info[A-Z]) so the info box / staff tables don't get counted
        # as discs by the sequential counter and shift the real track numbers.
        tables = [
            t for t in soup.find_all("table", class_="wikitable")
            if t.find("td", class_=re.compile(r'^info[A-Z]'))
        ]
    if not tables:
        return credits

    # Sequential disc counter — mirrors _parse_thwiki_html_titles so
    # per-source-album sections without an explicit "Disc N" heading
    # (e.g. "from 幻想パブ：午後7時") are numbered by page order rather
    # than all collapsing onto disc 1.
    auto_disc = 0
    for table in tables:
        auto_disc += 1
        current_disc: int = auto_disc
        current_track: int | None = None
        for sibling in table.previous_siblings:
            if not hasattr(sibling, "name") or sibling.name is None:
                continue
            if sibling.name in ("h2", "h3"):
                dm = _DISC_HEADER_RE.search(sibling.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    auto_disc = current_disc
                break
            if sibling.name not in ("br", "p", "div", "span"):
                break

        for tr in table.find_all("tr"):
            # Internal disc header detection
            th = tr.find("th")
            if th:
                dm = _DISC_HEADER_RE.search(th.get_text())
                if dm:
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue

            info_td = tr.find("td", class_=re.compile(r'^info[A-Z]'))
            if info_td:
                cell_text = info_td.get_text().strip()
                dm = _DISC_HEADER_RE.search(cell_text)
                if dm and not cell_text.isdigit():
                    current_disc = int(dm.group(1))
                    current_track = None
                    continue
                bold = info_td.find("b")
                if bold:
                    try:
                        current_track = int(bold.get_text().strip())
                    except ValueError:
                        pass

            if current_track is None:
                continue

            label_td = tr.find("td", class_="label")
            if not label_td:
                continue
            label_text = label_td.get_text().strip()
            credit_key = _CREDIT_LABELS.get(label_text)
            if not credit_key:
                continue

            text_td = tr.find("td", class_="text")
            if not text_td:
                continue

            names = []
            # Names may be in <a> tags or plain text
            for a_tag in text_td.find_all("a"):
                name = a_tag.get_text().strip()
                if name:
                    names.append(name)
            if not names:
                # Fall back to raw text, splitting on common separators
                raw = text_td.get_text().strip()
                if raw:
                    names = [n.strip() for n in re.split(r'[,、，/]', raw) if n.strip()]

            if names:
                key = (current_disc, current_track)
                credits.setdefault(key, {"arrange": [], "vocal": [], "lyric": []})
                for name in names:
                    if name not in credits[key][credit_key]:
                        credits[key][credit_key].append(name)

    return credits


def _parse_thwiki_html_tracklist(soup: BeautifulSoup) -> list[dict]:
    """Build complete track records from a rendered THBWiki album page.

    The asktrack REST API is normally the tracklist scaffold, but newly
    created or otherwise unindexed albums can still have a complete rendered
    page.  The existing HTML parsers intentionally only returned original
    titles and credits for tracks supplied by that scaffold; this function
    supplies the missing scaffold from each numbered track row and then
    enriches it with those parsers.

    The returned shape matches :func:`fetch_thwiki_tracks`, so the caller can
    use it without a separate tagging path.
    """
    tracks_by_key: dict[tuple[int, int], dict] = {}

    for disc, number, tr, starts_track in _iter_thwiki_track_rows(soup):
        if not starts_track:
            continue
        info_td = tr.find("td", class_=re.compile(r'^info[A-Z]'))
        if not info_td:
            continue
        tracks_by_key[(disc, number)] = {
            "number": number,
            "disc": disc,
            "title": _extract_thwiki_track_title(tr, info_td),
            "original_titles": [],
            "arrangers": [],
            "vocalists": [],
            "lyricists": [],
        }

    if not tracks_by_key:
        return []

    html_titles, _ = _parse_thwiki_html_titles(soup)
    html_credits = _parse_thwiki_html_credits(soup)
    for key, track in tracks_by_key.items():
        if key in html_titles:
            track["original_titles"] = list(html_titles[key])
        credits = html_credits.get(key, {})
        track["arrangers"] = list(credits.get("arrange", []))
        track["vocalists"] = list(credits.get("vocal", []))
        track["lyricists"] = list(credits.get("lyric", []))

    return [
        tracks_by_key[key]
        for key in sorted(tracks_by_key, key=lambda k: (k[0], k[1]))
    ]
