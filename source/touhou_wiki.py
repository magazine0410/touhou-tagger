"""
touhou_wiki.py — Fetch and parse album data from the English Touhou Wiki
(en.touhouwiki.net).

Fetching a page uses Playwright (headless Chromium) so that JS-rendered
tooltips are present in the page DOM.  Playwright is an **optional** dependency
(the "browser-fetch" group): when it is not installed, English-wiki lookups are
unavailable and callers fall back to THBWiki, which is the mandatory source
anyway.  Only ``fetch_album_html`` needs Playwright — the parsers below work on
already-fetched HTML and depend on Beautiful Soup alone, so this module always
imports successfully.
"""
import re
import urllib.parse

from bs4 import BeautifulSoup

from app_version import USER_AGENT

try:
    from playwright.sync_api import sync_playwright
except ImportError as _exc:  # pragma: no cover - exercised only without the dep
    sync_playwright = None
    _PLAYWRIGHT_IMPORT_ERROR: str | None = str(_exc)
else:
    _PLAYWRIGHT_IMPORT_ERROR = None

# Shown when an English-wiki fetch is attempted without Playwright installed.
PLAYWRIGHT_INSTALL_HINT = (
    "Playwright is required for English Touhou Wiki lookups. Install the "
    "browser-fetch dependency group:\n"
    "  python -m pip install -r requirements/browser-fetch.txt\n"
    "  python -m playwright install chromium"
)


def is_available() -> bool:
    """Return ``True`` when Playwright is importable.

    When ``False``, ``fetch_album_html`` cannot run and callers should skip the
    English Touhou Wiki and use THBWiki instead.
    """
    return sync_playwright is not None

# Zero-width space (U+200B).  The Touhou Wiki uses these around literal
# slashes in page titles (e.g. "東方beats to relax​/​study to") so that
# MediaWiki doesn't interpret the "/" as a subpage separator.  Users can't
# type these invisible characters, so we insert them automatically.
ZWS = "\u200b"


def fetch_album_html(wiki_page_name: str) -> str:
    if sync_playwright is None:
        raise RuntimeError(
            "English Touhou Wiki lookups are unavailable — "
            + PLAYWRIGHT_INSTALL_HINT
        )
    # Try the page name as supplied first (handles bare slashes like
    # "BloodDark/KARMANATIONS"); if that 404s, retry with zero-width
    # spaces padding the slashes (for titles where '/' is a literal
    # character in the title).
    candidates = [wiki_page_name]
    if "/" in wiki_page_name and ZWS not in wiki_page_name:
        candidates.append(wiki_page_name.replace("/", f"{ZWS}/{ZWS}"))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=USER_AGENT)
        html = None
        last_error: Exception | None = None
        for candidate in candidates:
            url = f"https://en.touhouwiki.net/wiki/{urllib.parse.quote(candidate)}"
            print(f"Fetching: {url}")
            response = page.goto(url, wait_until="networkidle")
            if response is not None and response.status == 404:
                last_error = ValueError(f"HTTP 404 — page {candidate!r} not found")
                continue
            html = page.content()
            break
        browser.close()

    if html is None:
        raise last_error or ValueError("Page not found on the wiki")
    return html


def extract_title_from_li(li) -> list[str]:
    """
    Given a <li> element that contains 'original title: ...',
    return a list of extracted title strings.
    Priority:
    1. Any descendant element with a non-empty ``title`` attribute —
       this is the JS-rendered tooltip with the full English/romaji
       name.  We don't constrain by class because the wiki's
       tooltip-wrapper class has changed in the past and may change
       again; the tooltip text is always in ``title=``.
    2. Fallback: visible text of the <li>, minus the
       "original title:" prefix.  Preserves Japanese characters so
       that ``translate_titles`` can map them to English later.
    """
    results = []
    # Strategy 1: first descendant with a title= attribute
    for el in li.find_all(attrs={"title": True}):
        tooltip = el.get("title", "").strip()
        if not tooltip:
            continue
        # Tooltip format: "Song Name [Character Name]"
        # Strip the trailing "[Character Name]" part if present
        title = tooltip.split("[")[0].strip()
        if title:
            results.append(title)
        return results

    # Strategy 2: visible text, minus the "original title:" prefix.
    # Preserves Japanese characters as a useful fallback when no
    # tooltip is available — translate_titles() will convert them
    # to English via the theme mapping.
    full_text = li.get_text()
    value = full_text.removeprefix("original title:").strip()
    if value:
        results.append(value)
    return results

def parse_tracklist(html: str) -> list[dict]:
    """
    Parse the album page HTML and return a list of track dicts:
    {
        "number":          int,
        "disc":            int,           # always 1 (English wiki has no disc info)
        "title":           str,
        "original_titles": list[str]      # empty for original compositions
    }
    """
    soup = BeautifulSoup(html, "html.parser")
    tracks = []
    track_number_re = re.compile(r"^(\d+)\.\s+")

    for li in soup.find_all("li"):
        # Only process top-level track entries (they start with "NN. ")
        # Use the direct text of the <li>, not nested elements
        direct_text = "".join(
            chunk for chunk in li.strings
            if li == chunk.parent or li == chunk.parent.parent
        ).strip()

        m = track_number_re.match(direct_text)
        if not m:
            continue
        # Skip if this <li> is itself nested inside another track's sub-list
        # (i.e. if any ancestor <li> also looks like a track entry)
        if li.find_parent("li"):
            continue

        track_num = int(m.group(1))
        # Track title is in the <b> tag
        bold = li.find("b")
        track_title = bold.get_text().strip() if bold else li.get_text()[m.end():].strip()

        # Original titles are in the nested <ul>
        original_titles = []
        nested_ul = li.find("ul")
        if nested_ul:
            for sub_li in nested_ul.find_all("li", recursive=False):
                text = sub_li.get_text()
                if text.startswith("original title:"):
                    original_titles.extend(extract_title_from_li(sub_li))

        tracks.append({
            "number":          track_num,
            "disc":            1,
            "title":           track_title,
            "original_titles": original_titles,
        })
    return tracks


# Credit label prefixes used in the English Touhou Wiki tracklist's nested
# list items (e.g. "arrangement: ZUN", "vocals: Foo, Bar").  Mapped to the
# same three role buckets as thwiki.parse_thwiki_album_staff so the two
# sources can be compared.  Labels vary slightly between album pages, so
# several spellings are accepted per role.
_EN_STAFF_LABELS: dict[str, str] = {
    "arrangement": "arrangement",
    "arrange":     "arrangement",
    "vocals":      "vocal",
    "vocal":       "vocal",
    "lyrics":      "lyrics",
    "lyric":       "lyrics",
}

# Splits a free-text credit value into individual names.
_NAME_SPLIT_RE = re.compile(r"[,、，/&]| and ")


def _names_from_credit_li(sub_li, label: str) -> list[str]:
    """Extract one or more names from a 'label: ...' credit list item.

    Prefers linked artist names (``<a>`` tags); falls back to the visible
    text after the label, split on common separators.
    """
    names: list[str] = []
    for a in sub_li.find_all("a"):
        text = a.get_text().strip()
        if text:
            names.append(text)
    if not names:
        raw = sub_li.get_text().strip()
        # Strip the leading "label:" (case-insensitive) before splitting.
        lowered = raw.lower()
        prefix = lowered.split(":", 1)[0]
        if prefix in _EN_STAFF_LABELS:
            raw = raw.split(":", 1)[1] if ":" in raw else raw
        names = [n.strip() for n in _NAME_SPLIT_RE.split(raw) if n.strip()]
    return names


def parse_album_staff(html: str) -> dict[str, list[str]]:
    """Parse album-level staff from the English Touhou Wiki page.

    The English wiki has no dedicated album-level Staff box; credits live in
    each track's nested list (``arrangement:``, ``vocals:``, ``lyrics:``).
    This aggregates them across every track into album-level role buckets,
    matching the shape of ``thwiki.parse_thwiki_album_staff`` so the verifier
    can union both sources uniformly.

    Returns ``{"arrangement": [...], "vocal": [...], "lyrics": [...]}`` with
    duplicates removed and original order preserved.  Runs on the already
    fetched album HTML, so it costs no extra network request.
    """
    soup = BeautifulSoup(html, "html.parser")
    staff: dict[str, list[str]] = {
        "arrangement": [], "vocal": [], "lyrics": [],
    }
    track_number_re = re.compile(r"^(\d+)\.\s+")

    for li in soup.find_all("li"):
        if not track_number_re.match(li.get_text()):
            continue
        if li.find_parent("li"):
            continue
        nested_ul = li.find("ul")
        if not nested_ul:
            continue
        for sub_li in nested_ul.find_all("li", recursive=False):
            text = sub_li.get_text().strip()
            label_key = text.lower().split(":", 1)[0]
            role = _EN_STAFF_LABELS.get(label_key)
            if not role:
                continue
            for name in _names_from_credit_li(sub_li, label_key):
                if name and name not in staff[role]:
                    staff[role].append(name)

    return staff
