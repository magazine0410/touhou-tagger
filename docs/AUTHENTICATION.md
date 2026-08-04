# THBWiki authentication and browser privacy

Touhou Tagger needs a current THBWiki browser session to fetch rendered
album pages. This document explains the supported manual setup and the
optional browser-cookie helper.

## Why THBWiki authentication is required

THBWiki protects rendered album pages with a Cloudflare/SafeLine human
verification challenge. The tagger needs those pages for authoritative
album information, staff credits, and original-theme cross-checking. Regular
HTTP clients and automated browsers cannot reliably pass the challenge.

Open `https://thwiki.cc/` in your normal browser and complete the challenge
there. The tagger then reuses the session cookie with `curl_cffi`, which can
match a browser-like network fingerprint. A cookie is required even when an
album also appears on the English Touhou Wiki: the tagger validates it before
starting a batch so it can fail before changing any music files rather than
silently omit THBWiki data.

The cookie is tied to the browser session, User-Agent, network identity, and
fingerprint. It expires or rotates, so repeat this setup whenever THBWiki
reports that the cookie has been re-challenged.

## Manual setup (supported without browser-cookie extraction)

Manual setup does **not** need `browser_cookie.py`, `browser_cookie3`, or the
keepalive userscript.

1. In the browser you will use, open THBWiki and complete its human check.
2. Open the browser developer tools, reload a THBWiki page, and select the
   page/document request in the Network panel.
3. From that request's headers, copy the complete `Cookie` header value and
   the exact `User-Agent` value. Treat the cookie as a password: do not put it
   in a repository, issue, chat message, screenshot, or shared log.
4. Set the values in the same terminal session that starts the tagger. Also
   disable automatic loading so the manually supplied cookie is used exactly
   as entered.

On Linux and macOS shells:

```bash
export THWIKI_COOKIE='the complete Cookie header value'
export THWIKI_UA='the exact User-Agent header value'
export THWIKI_IMPERSONATE='chrome'
export THWIKI_COOKIE_AUTO=0
python source/touhou_tagger.py "Wiki_Page_Slug" "path/to/album" --dry-run
```

In PowerShell:

```powershell
$env:THWIKI_COOKIE = 'the complete Cookie header value'
$env:THWIKI_UA = 'the exact User-Agent header value'
$env:THWIKI_IMPERSONATE = 'chrome'
$env:THWIKI_COOKIE_AUTO = '0'
python source/touhou_tagger.py "Wiki_Page_Slug" "path/to/album" --dry-run
```

Set `THWIKI_IMPERSONATE` to the matching browser family: `chrome` for Chrome,
Chromium, and Brave; `firefox`, `safari`, or `edge` for those families. The
tagger defaults to `chrome` when this variable is omitted. A mismatched
User-Agent or profile can cause a new challenge.

In the GUI, select **THBWiki Authentication…**. The dialog lets you choose the
browser whose cookie store should be read, enable or disable auto-pull, paste a
manual Cookie and User-Agent, and select the matching impersonation profile. The
cookie stays in memory only for that run. The GUI remembers the browser choice,
auto-pull preference, User-Agent, and impersonation profile; it never saves the
Cookie header to disk. **Test authentication** makes a live home-page request
with the
current in-memory values before a batch starts and reports only whether the
cookie is missing, a challenge was returned, transport failed, or a normal page
was received. It never prints or displays cookie contents.

## Optional automatic browser-cookie loading

`browser_cookie.py` is a convenience helper, not a requirement. When the
optional `browser_cookie3` Python package is installed, it reads only the
cookies for `thwiki.cc` from the browser selected by
`THWIKI_COOKIE_BROWSER` (Chrome by default). It builds the `Cookie` request
header from those domain-matching cookies and places that header only in the
current process's `THWIKI_COOKIE` environment value.

The helper does not launch a browser, solve the human challenge, copy a
browser profile, or save cookies to the tagger configuration, project folder,
or logs. If the browser store cannot be read—for example, because
`browser_cookie3` is not installed or the OS keyring is locked—it leaves an
existing manual `THWIKI_COOKIE` unchanged and the manual path continues to
work.

When auto-pull succeeds, it refreshes `THWIKI_COOKIE` with the selected
browser's current session. Set `THWIKI_COOKIE_AUTO=0` to disable that behavior
and use a manually supplied cookie exclusively. To use a different browser,
set `THWIKI_COOKIE_BROWSER` to one of `chrome`, `brave`, `chromium`,
`firefox`, `edge`, `opera`, `vivaldi`, `librewolf`, or `safari`; choose the
browser in which you completed the THBWiki challenge.

The helper is used only in these places:

- `thwiki.py` tries a best-effort refresh before THBWiki cookie validation and
  rendered-page fetches, then may force one fresh read after a challenge
  response.
- `gui.py` performs a best-effort refresh at GUI startup and when its
  authentication dialog opens or its **Pull from browser** button is used.

It cannot retrieve a User-Agent from the browser cookie store, so you must
still provide `THWIKI_UA` yourself (or let the GUI reuse the value it saved).

## Cookie privacy, logs, and bug reports

Cookie headers are assembled only in memory and passed to THBWiki as request
headers. They are not written to the project directory, the tagger's user
configuration, or the normal GUI log. Cookie-fetch failures deliberately use
generic messages rather than printing a client command or exception that
could contain request headers.

The tagger has no automatic bug-report or issue-submission feature. Its GUI
logs remain local; sharing one is a manual choice. Logs can still contain
personal paths, album names, and crash details, so review them before sharing.
Never include a Cookie header in a bug report or support request.

## Keepalive userscript

`thwiki_keepalive.user.js` is optional. It only makes periodic requests from a
browser tab that has already passed the challenge, helping that session remain
warm. It silently fetches the THBWiki root with that browser session roughly
every 60–120 seconds and coordinates open tabs so they do not all ping at
once. It cannot solve, bypass, or automate the human check; it can only keep
an already verified session active. Python never reads or executes it, and it
is not needed for either manual authentication or automatic cookie loading.

## Related privacy information

See [USER_DATA.md](USER_DATA.md) for the tagger's configuration and log
locations, including the guarantee that `auth.json` never contains a cookie.
