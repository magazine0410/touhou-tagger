"""
browser_cookie.py — best-effort live browser-cookie extraction.

Pulls the current cookies for a WAF-gated site straight from a local browser's
cookie store (via the optional ``browser_cookie3`` package), assembles them
into the full ``Cookie`` request header the tagger needs, and injects it into
the site's cookie environment variable.  This removes the manual DevTools
copy-paste step: as long as a browser holds a live session (kept warm by a
keepalive userscript), the tagger reads the current cookie itself — including
rotating WAF session cookies and the Cloudflare ``cf_clearance`` — joined into
one header just as a manual paste of the whole DevTools "Cookie:" value would.

The site is selected via the ``site`` parameter, which defaults to the only
site currently wired up:

  * ``THWIKI`` (default) — thwiki.cc, env ``THWIKI_COOKIE`` /
    ``THWIKI_COOKIE_AUTO`` / ``THWIKI_COOKIE_BROWSER``.

The ``site``-parameterised design is kept so another WAF-gated site can be
added as a ``_Site`` profile without touching call sites; per-site mutable
state (TTL cache, announce tracking) is keyed by domain so sites never share
a cache.

It is strictly **best-effort** and never makes things worse:

  * If ``browser_cookie3`` isn't installed, or the store can't be read (e.g.
    the OS keyring is locked), whatever is already in the site's cookie env (a
    manual paste, a shell export) is left **untouched**.  This only ever
    *upgrades* the env cookie to a fresher one — it never clears a working one.
  * Set ``<SITE>_COOKIE_AUTO=0`` (or false/no/off) to disable entirely.
  * Set ``<SITE>_COOKIE_BROWSER`` to choose the source browser
    (default ``chrome``; also brave / chromium / firefox / edge / opera /
    vivaldi / librewolf / safari).  Set this to whichever browser you solved
    the site's challenge in — the auto-pull reads that browser's cookie store.

A browser can only *provide* a cookie it already has — it cannot pass the
Cloudflare / SafeLine human-verification challenge.  When the session truly
expires you must still solve the check once in the browser; the fresh cookie
is then picked up automatically on the next read.

This module is a leaf: it imports nothing from the rest of the tagger, so
``thwiki.py`` / ``gui.py`` can soft-import it (and degrade gracefully if it is
absent).
"""
import os
import time
from collections import namedtuple

# A site profile: which domain to read, and the three env vars that control it.
_Site = namedtuple(
    "_Site",
    "domain cookie_env auto_env browser_env default_browser label",
)

THWIKI = _Site(
    domain="thwiki.cc",
    cookie_env="THWIKI_COOKIE",
    auto_env="THWIKI_COOKIE_AUTO",
    browser_env="THWIKI_COOKIE_BROWSER",
    default_browser="chrome",
    label="THBWiki",
)

# Back-compat aliases (the original module exposed these THBWiki constants).
_COOKIE_ENV = THWIKI.cookie_env
_AUTO_ENV = THWIKI.auto_env
_BROWSER_ENV = THWIKI.browser_env
_DOMAIN = THWIKI.domain
_DEFAULT_BROWSER = THWIKI.default_browser

# Re-reading the cookie store hits an SQLite file plus the OS keyring, so a
# short TTL coalesces the back-to-back reads of a typical run (cookie validation
# immediately followed by the first album) into one.  A forced refresh (used
# between retries after a re-challenge) bypasses it.
_TTL_SECONDS = 30.0

# --- per-site module state (keyed by domain) --------------------------------
_last_pull: dict[str, float] = {}
_cached_header: dict[str, str | None] = {}
_announced: dict[str, bool] = {}             # printed the silent first-load line?
_last_announced_header: dict[str, str | None] = {}  # last header via announce=True
_warned: dict[str, bool] = {}               # printed a read-failure warning?

# --- shared state (the imported package is process-wide) ---------------------
_import_checked = False
_bc3 = None                                  # the imported browser_cookie3, or None


def _falsey(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off"}


def _browser_name(site: _Site = THWIKI) -> str:
    return (os.environ.get(site.browser_env, "").strip()
            or site.default_browser).lower()


def _env_cookie(site: _Site = THWIKI) -> str:
    return os.environ.get(site.cookie_env, "").strip()


def _import_bc3():
    """Soft-import browser_cookie3 once, caching the result (module or None)."""
    global _import_checked, _bc3
    if not _import_checked:
        _import_checked = True
        try:
            import browser_cookie3 as bc3
            _bc3 = bc3
        except Exception:       # noqa: BLE001 — any import problem disables us
            _bc3 = None
    return _bc3


def _loader(site: _Site = THWIKI):
    """Return the browser_cookie3 loader function for the configured browser."""
    bc3 = _import_bc3()
    if bc3 is None:
        return None
    return getattr(bc3, _browser_name(site), None)


def is_enabled(site: _Site = THWIKI) -> bool:
    """True if auto-pull is switched on and browser_cookie3 is importable."""
    if _falsey(os.environ.get(site.auto_env, "")):
        return False
    return _loader(site) is not None


def disabled_reason(site: _Site = THWIKI) -> str | None:
    """Human-readable reason auto-pull is off, or ``None`` if it's available."""
    if _falsey(os.environ.get(site.auto_env, "")):
        return f"disabled via {site.auto_env}"
    if _import_bc3() is None:
        return ("browser_cookie3 not installed "
                "(pip install --user browser_cookie3)")
    if _loader(site) is None:
        return f"unknown browser {_browser_name(site)!r} (set {site.browser_env})"
    return None


def status_text(site: _Site = THWIKI) -> str:
    """Short human-readable auto-pull status, for display in a UI."""
    reason = disabled_reason(site)
    if reason:
        return f"auto-pull off — {reason}"
    return f"auto-pull on — from {_browser_name(site)}"


def pull_cookie_header(site: _Site = THWIKI) -> str | None:
    """
    Read the live cookies for ``site`` from the configured browser and return
    them as a single ``name=value; name=value`` header string, or ``None`` if
    the browser has no such cookies or the store can't be read.
    """
    loader = _loader(site)
    if loader is None:
        return None
    try:
        jar = loader(domain_name=site.domain)
    except Exception:           # noqa: BLE001 — keyring locked, db busy, etc.
        if not _warned.get(site.domain):
            _warned[site.domain] = True
            print(f"  [browser-cookie] Could not read {site.domain} cookies "
                  f"from {_browser_name(site)}. Falling back to the "
                  f"existing {site.cookie_env} (manual paste), if any.")
        return None

    parts: list[str] = []
    seen: set[str] = set()
    for c in jar:
        # The jar is already domain-filtered; one value per cookie name is what
        # a real request sends, so de-dupe (e.g. a name set on both the bare
        # and dotted domain), keeping the first occurrence.
        if c.name in seen:
            continue
        seen.add(c.name)
        parts.append(f"{c.name}={c.value}")
    return "; ".join(parts) if parts else None


def _announce(header: str, announce: bool, site: _Site = THWIKI) -> None:
    """Emit a log line for a cookie load / rotation (per site).

    With ``announce=True`` (the run path), prints on the first header seen and
    again whenever the cookie value changes.  With ``announce=False`` (a
    silent/dialog/CLI pull), prints only the very first load once.
    """
    n = header.count(";") + 1
    name = _browser_name(site)
    if announce:
        if header != _last_announced_header.get(site.domain):
            verb = ("Loaded" if _last_announced_header.get(site.domain) is None
                    else "Updated")
            print(f"  [browser-cookie] {verb} {site.label} cookie from "
                  f"{name} ({n} cookie(s)).")
            _last_announced_header[site.domain] = header
    elif not _announced.get(site.domain):
        print(f"  [browser-cookie] Loaded {site.label} cookie from "
              f"{name} ({n} cookie(s)).")
    _announced[site.domain] = True


def refresh_env(
    *, force: bool = False, announce: bool = False, site: _Site = THWIKI,
) -> bool:
    """
    Best-effort: pull the live cookie from the browser and write it to the
    site's cookie env var (``THWIKI_COOKIE`` by default).

    Returns ``True`` if the cookie env ends up non-empty (whether from a fresh
    pull or a pre-existing manual value), ``False`` otherwise.  A pull failure
    never clears an existing env cookie.

    Args:
        force:    bypass the TTL cache and read the store again — used between
                  fetch retries to pick up a freshly rotated cookie.
        announce: log when the cookie is first loaded and whenever it changes.
        site:     which site profile to operate on (default THBWiki).
    """
    if not is_enabled(site):
        return bool(_env_cookie(site))

    now = time.monotonic()
    cached = _cached_header.get(site.domain)
    last = _last_pull.get(site.domain, 0.0)
    if (not force) and cached and (now - last) < _TTL_SECONDS:
        # Still fresh — make sure the env reflects our cached value, and still
        # run the announce check so a first announce=True caller reports it.
        os.environ[site.cookie_env] = cached
        _announce(cached, announce, site)
        return True

    header = pull_cookie_header(site)
    if not header:
        # Couldn't read anything; leave any existing (manual) cookie in place.
        return bool(_env_cookie(site))

    _cached_header[site.domain] = header
    _last_pull[site.domain] = now
    os.environ[site.cookie_env] = header
    _announce(header, announce, site)
    return True
