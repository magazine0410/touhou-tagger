# Touhou Tagger

Tags a personal Touhou remix music collection with original theme names (`grouping` tag) and Hepburn romaji sort keys (`titlesort`), sourced from the English Touhou Wiki and THBWiki, optionally cross-checked against TouhouDB.

For the full design rationale, anti-bot history, and edge cases, see the project's internal design notes (kept locally, not in the public repo) — this file only holds what must be in context every session.

## Environment

- OS: Fedora KDE, package manager `dnf5`
- Player: Quod Libet (reads `grouping`/`titlesort` as arbitrary tags)
- Preferred tagging UI: the standalone PyQt5 GUI, launched with `./launch.sh`
- Standalone alternative: `source/touhou_tagger.py` (CLI or PyQt5 GUI)

## Module layout (standalone tagger)

All standalone tagger files live in `source/` and share one directory; imports flow downward only (acyclic):

```
touhou_tagger.py   entry point: fetch_album_plan() / tag_album_from_plan() /
                    process_album() / process_albums(), CLI, GUI dispatch, logging
  ├── touhou_wiki.py  English wiki — Playwright/Chromium (optional) + BeautifulSoup
  ├── thwiki.py       THBWiki — curl_cffi + mandatory cookie + BeautifulSoup
  ├── browser_cookie.py  optional live cookie pull from a local browser (THBWiki);
  │                   soft-imported by thwiki.py, gui.py
  ├── external_tools.py  persistent external-command discovery and GUI path
  │                   overrides (leaf; imported by network/statistics/gui)
  ├── album_overrides.py  persistent path-keyed reviewed Wiki Slug overrides
  │                   (leaf; imported by gui.py)
  ├── preferences.py  non-secret GUI behavior/window/CUE preferences (leaf)
  ├── app_version.py  single source of the app version — reads the root VERSION
  │                   file; exposes __version__ + a shared User-Agent (leaf,
  │                   stdlib-only; imported by touhou_tagger/touhou_wiki/touhoudb)
  ├── config_backup.py  allow-listed secret-free config export/import (leaf)
  ├── availability.py  persistent "unavailable on the wikis" album/artist marks
  │                   + platform-aware user config/log paths (leaf; imported
  │                   by touhou_tagger.py, gui.py & library_stats.py)
  ├── cue_split.py    split whole-album FLAC image(s) into per-track FLACs via
  │                   CUE (external or embedded); lone image in place, or a
  │                   multi-disc set into "Disc N" subfolders — leaf, no project
  │                   imports; soft-imported by gui.py & touhou_tagger.py
  ├── touhoudb.py     TouhouDB verification + per-track titles — curl + stdlib
  ├── tag_io.py       mutagen read/write, CJK/Latin detection
  ├── theme_mapping.py  JP→EN translation, variant-title inheritance
  ├── file_scan.py    directory scanning, slug guessing (imports tag_io)
  └── gui.py          PyQt5 GUI (lazy-imported only when no CLI args)
        └── library_stats.py  Statistics tab — library scan, pie chart,
                              theme/genre popularity (imports file_scan /
                              tag_io / theme_mapping / availability;
                              lazy-imported only inside gui_main)
```

`japanese_romanizer.py` (+ `japanese_romanizer_data.py`) is a standalone romaniser, soft-imported by `touhou_tagger.py` when present. `translate_genres.py` is a standalone CLI (imports only `tag_io` + `thwiki`, no network/Qt) that re-translates already-written CJK `genre` tags through `thwiki.GENRE_TRANSLATIONS` — the fast way to apply newly-added genre mappings to a library tagged before they existed, without re-fetching THBWiki. `translate_groupings.py` is the equivalent network-free migration CLI for already-written semicolon-separated `grouping` tags; it uses `touhou_theme_mapping.json`, preserves unknown/manual components, and supports dry runs. `retag_credits.py` is the **network-bound** migration CLI for `arranger`/`vocalist`/`lyricist` tags written with the artist's circle by the pre-2026-08-23 Staff-map bug; it re-fetches each album (the mapping is not invertible), is **dry-run by default** (`--apply` to write), checkpoints per album so an expired THBWiki session resumes (records are stamped with the mode, so a dry-run checkpoint never lets a later `--apply` run skip that album), pauses on an expiry to let the challenge be solved again and retries the same album rather than ending the run (`--no-wait`, and any non-TTY stdin, stops instead — the prompt would block forever), and rewrites a tag only when it both disagrees with the wiki and equals that album's circle-mapped form. Its `--romanize` flag adds the separately-counted TouhouDB romanisation pass and persists resolved names (negative results included) to `retag_credits_names.json`, because TouhouDB allows one request per second and a resumed session would otherwise re-query every name. Its `--stats-cache` mode shortlists paths from the Statistics scan cache, trusts only matching mtimes, rereads stale candidates, and deliberately excludes uncached files. `build_theme_mapping/build_theme_mapping.py` (in the `build_theme_mapping/` subdirectory, alongside its `thpatch_ja.json`/`thpatch_en.json` input dumps and reviewed `additional_theme_mappings.json`) generates `source/touhou_theme_mapping.json`. The generated JSON keeps Len'en and Seihou Project in named `sections`; `theme_mapping.load_theme_mapping()` merges them into the runtime `mapping`. Regenerate after a new Touhou game/CD release or a reviewed additional-section update.

## Non-negotiable network rules

These are the result of extensive trial and error against anti-bot systems — do not "simplify" them:

- **THBWiki rendered pages require a browser cookie reuse via `curl_cffi`.** Plain `curl`/`urllib`/Playwright cannot pass the SafeLine WAF challenge. A missing/stale `THWIKI_COOKIE` is a hard, batch-fatal error (`ThwikiCookieError`) — never silently degrade to skipping the HTML cross-check.
- **THBWiki cookie auto-pull (`browser_cookie.py`).** The mandatory cookie can be supplied automatically: `_fetch_thwiki_via_cookie()` calls `browser_cookie.refresh_env()` before reading `THWIKI_COOKIE`, pulling the live `thwiki.cc` cookies (incl. the rotating SafeLine `sl-session` and Cloudflare `cf_clearance`) from a local browser into the env, and force-re-pulls between retries when re-challenged. It is **best-effort**: it never clears a manual cookie, and degrades silently if `browser_cookie3` is missing. Opt out with `THWIKI_COOKIE_AUTO=0`; pick the browser with `THWIKI_COOKIE_BROWSER` (default `chrome`). It pulls the cookie but **cannot pass the human-verification challenge** — that still needs a real browser solving it once; keep the session warm with `thwiki_keepalive.user.js`. The **UA is not auto-pulled** (browsers don't expose it that way) — `THWIKI_UA` still comes from the persisted config / shell export, and `cf_clearance` is bound to it, so it must match.
- **Challenge detection (`_looks_like_challenge`) must not match the bare `cdn-cgi/challenge-platform` path.** Cloudflare injects a *passive* JS-detection beacon (`/cdn-cgi/challenge-platform/scripts/jsd/main.js` + a `window.__CF$cv$params` blob) into normally-served pages, so matching that path flags valid pages as challenges (a false positive that discards good fetches). Detect a genuine block by `_cf_chl_opt` / the "Just a moment" title / SafeLine markers instead.
- **THBWiki's `asktrack` REST API** uses plain `curl` subprocess (no cookie needed) — `urllib` is blocked by TLS-fingerprint detection at the nginx level.
- **English Touhou Wiki** requires real Chromium (Playwright) with a non-`HeadlessChrome` User-Agent on the rendered `/wiki/PAGE` path. `urllib` and Playwright's Node-based `request.new_context()` both get HTTP 418/403. Playwright is an **optional** dependency (the `browser-fetch` group): `touhou_wiki.py` soft-imports it and exposes `is_available()`, and `fetch_album_html()` raises a clear install hint if called without it. When it's absent, `fetch_album_plan()`'s `_try_wikis` skips the English wiki entirely (warning once) and uses THBWiki, the mandatory source — so the whole tagger imports and runs Playwright-free. Keep the import soft; don't turn it back into a hard top-level import.
- **TouhouDB** is `curl`-based, rate-limited to 1 req/sec with exponential backoff, and cached per run. It is verification-only — never the source of original theme names.
- Don't reintroduce a headless-Playwright fallback for THBWiki pages; it was removed deliberately (see context doc, "THBWiki page HTML fetch — current approach").

## Tag write policies

- **Most tags are skip-if-present**: if the file already has a non-empty value, leave it untouched (`date`, `year`, `catalognumber`, credits, and TouhouDB-sourced `artist`/`artistsort`). The one opt-out is `force_credits` (GUI: "Force overwrite staff tags"; CLI: `--force-credits`), which makes the wiki authoritative for `arranger`/`vocalist`/`lyricist` so a re-run can correct credits an earlier release wrote. It still skips a credit the wiki already agrees with, and never writes a role the wiki has no credit for — forcing overwrites, it never clears.
- **`genre`** is album-level from the THBWiki info box (label `Genre`/`风格类型`/`ジャンル` — **not** `曲风`, which THBWiki's own help page documents as a *separate per-track* field sharing the same vocabulary; including it in the album-label set would let a track's style clobber the album's genre), translated CN/JP→EN via `thwiki.GENRE_TRANSLATIONS` (unknown CJK values kept as-is with a log warning), and written **multi-value** via `tag_io.set_genres()` — one `genre=` Vorbis field per genre on FLAC/OGG/Opus (the Vorbis convention for multiple genres), a multi-text `TCON` frame on MP3, a multi-value `©gen` atom on M4A. **Unlike the skip-if-present tags, `genre` is _merged_, not skipped**: the wiki genres are unioned with whatever the file already has (via `_merge_genres` in `touhou_tagger.py`), so an album keeps its pre-existing/hand-added genres (e.g. `Indie`, or the doujin-file `Touhou`) and gains the wiki's styles. Existing genres are run through the same translator (a mapped pre-existing CJK genre like `独立音乐` lands as `Indie` and dedups against a wiki `Indie`; English/unmapped values are preserved verbatim); dedup is case-insensitive, existing-first order; the write is skipped only when the merge adds nothing new. Deliberately not in `EDITABLE_TAGS` — the Tag Edit tab is single-value per cell and would collapse a multi-genre field on save.
- **`album` always overwrites** on mismatch — THBWiki/wiki data is authoritative.
- **`albumartist`/`titlesort`/`artistsort`** follow a CJK-display / Latin-sort pairing: original-language form goes in the display field, romanised form in the sort field, and a sort field is never written if it still contains CJK (the "CJK guard").
- **Romanization resolver priority**: TouhouDB official name > THBWiki Staff-section mapping > original name (with the CJK guard suppressing a CJK fallback from ever landing in a sort field). This priority now drives the **credit tags** (`arranger`/`vocalist`/`lyricist`) as well as the sort fields — `_build_credit_romanization_map()` resolves each album's unique CJK credit names once, which is why credit romanisation runs *after* the TouhouDB block in `fetch_album_plan()` (the client does not exist before it). TouhouDB stays opt-in: without `--touhoudb` the credits keep the wiki's original names. The Staff-section tier is near-empty by design: a stafflist row is `[Artist, Circle, Tracks]`, so its **second column is the artist's circle, never a romanization** — reading it as one replaced every credited artist with their circle. Only piped `<dd>` credit links (CJK title → Latin label) may contribute a romanization.
- Field-by-field tag IDs (ID3/M4A/Vorbis) and the full write-policy tables are in the project's internal design notes (kept locally, not in the public repo) — check there before adding a new tag.

## Commands

```bash
# Standalone tagger — GUI (double-click or run the launcher)
./launch.sh
# Equivalent direct command:
python source/touhou_tagger.py

# Standalone tagger — CLI, always dry-run first
python source/touhou_tagger.py "Wiki_Page_Slug" "path/to/album" --dry-run
python source/touhou_tagger.py "Wiki_Page_Slug" "path/to/album"

# Romaniser only (no Touhou-wiki dependency)
python source/japanese_romanizer.py "path/to/album" --dry-run
python source/japanese_romanizer.py "path/to/album"

# Re-translate CJK genre tags to English in place (no Touhou-wiki dependency),
# e.g. after adding new entries to thwiki.GENRE_TRANSLATIONS — applies them to
# already-tagged files without re-fetching THBWiki. Idempotent; dry-run first.
python source/translate_genres.py "path/to/music-library" --dry-run
python source/translate_genres.py "path/to/music-library"

# Repair credit tags written with the circle instead of the artist
# (pre-2026-08-23 Staff-map bug). Network-bound; dry run unless --apply.
# Checkpointed per album — re-run the same command to resume after the
# THBWiki session expires.
python source/retag_credits.py "path/to/music-library"
python source/retag_credits.py --apply "path/to/music-library"
# Add --romanize to also rewrite credits that merely hold the wiki's
# Japanese name (TouhouDB romanisation). That is a naming-policy pass, not
# a bug fix — it touches albums the bug never damaged, so dry-run it alone.
python source/retag_credits.py --romanize "path/to/music-library"

# Re-translate existing grouping tags after a theme-mapping correction.
# Network-free and idempotent; dry-run first.
python source/translate_groupings.py "path/to/music-library" --dry-run
python source/translate_groupings.py "path/to/music-library"
# Large-library fast path after a completed Statistics scan:
python source/translate_groupings.py --stats-cache --dry-run \
  "path/to/music-library"

# Regenerate the theme mapping after a new game/CD release.
# Note: the builder and its two thpatch.net JSON dumps live in the
# build_theme_mapping/ subdirectory, not the project root.
cd build_theme_mapping && python build_theme_mapping.py thpatch_ja.json thpatch_en.json \
  --output ../source/touhou_theme_mapping.json
```

THBWiki auth (mandatory every run): with `browser_cookie3` installed the cookie is pulled from your browser automatically (default Chrome) — just keep a verified THBWiki tab open, ideally with `thwiki_keepalive.user.js` running to hold the session. Otherwise set it manually: `export THWIKI_COOKIE='...'` and `THWIKI_UA='...'`, copied from a browser that has passed the SafeLine challenge (DevTools → Network → a document request). Either way `THWIKI_UA` must match the cookie's browser (auto-pull does not fetch the UA). The GUI pulls the cookie once at startup (in `gui_main()`), and its "THBWiki Authentication…" dialog also pre-fills the Cookie box from a live browser pull on open (with a "Pull from browser" button), shows the auto-pull status, and persists only the UA/impersonate profile in the platform user-config directory documented in `docs/USER_DATA.md`.

## Dependencies

Every external executable, its feature, installation routes, and missing-tool
behaviour are documented in @docs/EXTERNAL_TOOLS.md.
Pinned Python dependencies, supported versions, and optional feature groups
are documented in @docs/DEPENDENCIES.md.
Per-user config/log locations and privacy boundaries are documented in
@docs/USER_DATA.md.
THBWiki's manual-authentication path and the optional browser-cookie helper
are documented in @docs/AUTHENTICATION.md.
Supported folder layouts, naming recommendations, and inference safeguards
are documented in @docs/FOLDER_LAYOUT.md.

```bash
# Usual GUI install + English-wiki fetcher:
python -m pip install -r requirements.txt -r requirements/gui.txt \
  -r requirements/browser-fetch.txt
python -m playwright install chromium
# Optional groups are documented in docs/DEPENDENCIES.md.
```

## Conventions when editing this codebase

- Keep both `AGENTS.md` and `CLAUDE.md` as regular, byte-identical files.
  Different coding assistants discover different filenames, while regular
  files also work in Windows checkouts and source archives where symlinks may
  not. Any change to repository guidance must be applied to both files, then
  verified with `cmp -s AGENTS.md CLAUDE.md`.
- Keep the import graph acyclic — only `touhou_tagger.py` may import `gui.py`, and only lazily inside `main()`; only `gui.py` may import `library_stats.py`, and only lazily inside `gui_main()` (keeps PyQt5 off the CLI path). Do not rename `library_stats.py` to `statistics.py` — that shadows Python's stdlib `statistics` module.
- New per-album network I/O belongs in `fetch_album_plan()`; new local file I/O belongs in `tag_album_from_plan()`. Don't blur the fetch-then-tag split — it's what lets a `ThwikiCookieError` abort a whole batch before any file is touched.
- Keep `compare_tracklists()` pure (no Qt, no I/O) so it stays headlessly testable; it's reused by both the summary report and the severe-mismatch gate. The mismatch confirmation is a callback (`on_confirm`) threaded through `process_albums`/`tag_album_from_plan` — the GUI supplies a blocking signal/Event bridge, the CLI supplies nothing (auto-skip). Don't make `tag_album_from_plan` import or call Qt directly.
- The severe-mismatch gate's scan→match→`compare_tracklists`→confirm block in `tag_album_from_plan` is a **loop** (capped at 3 rescans) so `on_confirm` can return `"rescan"`: the GUI's "Split via CUE sheet" button splits a lone un-split album image into per-track files on disk, then the loop re-scans and re-compares (a correctly-split album is then no longer severe and falls through to tagging). The four decisions are `"skip"`/`"continue"`/`"cancel"`/`"rescan"`; the worker's Event bridge passes any string through unchanged, so a new decision needs no protocol change.
- Keep `cue_split.py` a leaf (no project imports), like `availability.py`/`browser_cookie.py`, so both `gui.py` and `touhou_tagger.py` can soft-import it without a cycle or dragging the GUI/Qt onto the CLI path. The actual split worker (`_CueSplitWorker` QThread) and the dialog button live in `gui.py`; `cue_split.py` itself is Qt-free and shells out to `ffmpeg`/`flac`/`metaflac`/`gio`. The cut is done by **`ffmpeg`** at breakpoints we compute ourselves from the CUE's `INDEX` times (`-ss`/`-t` per track, `-map 0:a:0`), **not** `shnsplit` — shntool pipes a non-canonical WAV to the `flac` encoder, which flac 1.4+ rejects ("child encoder process had non-zero exit status"), and it can't derive split points from a multi-FILE CUE. `detect_cue` collects *every* CUE source (external `*.cue` + the embedded CUESHEET) and **merges the best offsets with the best titles by track number** — the common EAC/TLMC case is a sidecar `.cue` with one `FILE` per track (real titles, useless `INDEX 01 00:00:00` offsets) alongside a single-file embedded CUESHEET (real offsets, no titles); neither alone can split the image but together they can. Only when *no* source has usable single-file offsets (a genuine multi-FILE-only CUE, or non-increasing starts) is the split refused with a clear message rather than producing garbage. **Multi-image sets** go through `detect_split()`/`split_plan()` (the GUI's entry points, wrapping the lone-image path too), each image split into its own `Disc N` subfolder via the shared `_build_multi_plan()`: (a) 2+ FLACs whose names carry distinct disc indicators (`Disc 1`, `DISC2`, `cd 3` — `_DISC_IN_NAME_RE`) → keyed by those numbers, *any duration*; (b) 2+ non-disc-named FLACs that are **all** ≥ 10 min (`_MIN_IMAGE_DURATION_SEC` — a folder of continuous mixes, not a normal album with one long track) → disc numbers assigned by sorted filename. Each image is paired with its own CUE (same-stem `.cue` first, then — disc-named only — disc-number match, then that image's embedded CUESHEET) and merged. The dialog's split **button visibility** is a separate, cheaper check — `looks_splittable()`: a disc-named set (any duration), a lone disc-named FLAC, or *every* audio file being a FLAC ≥ 10 min (duration from the STREAMINFO header — not a byte size, which is format-dependent; requiring **all** large avoids a normal album with one long track). So the button is offered for a plausible album image even before a CUE is confirmed; if `detect_split()` then finds none, the click reports "nothing to split" rather than the button silently not appearing. `split_plan` pre-flights **every** disc before moving anything (all-or-nothing), then per disc creates a `Disc N` subfolder (named to match `file_scan.DISC_DIR_RE` so the rescan assigns disc numbers), moves the image + its CUE in, and splits there — each split file also gets a `discnumber` tag. Tags on split files are written with `mutagen` from our own encoding-auto-detected CUE titles — **not** `cuetag`, which assumes UTF-8 and mangles the Shift-JIS/CP932 CUEs this collection uses. The mojibake guard prefers the decode yielding the most CJK/kana and rejects U+FFFD or stray control chars; a verified-clean split is the only path that trashes the original image.
- THBWiki HTML parsing must stay tolerant of label-text variants (English/Chinese/Japanese) and the `info[A-Z]` class regex for track rows — don't hard-code a single class or label string.
- Any change to THBWiki/English-wiki fetch logic should be cross-checked against the anti-bot findings in the project's internal design notes (kept locally, not in the public repo) before assuming a simpler approach will work; most "simpler" approaches were already tried and documented as failing.
- Keep `browser_cookie.py` a leaf (no project imports) so `thwiki.py`/`gui.py` can soft-import it. It keeps a `site=` parameterised design (the `site=THWIKI` default) so another WAF-gated site could be added as a `_Site` profile without touching call sites; per-site state is keyed by domain. The THBWiki cookie auto-pull and the `_looks_like_challenge` detector live in `thwiki.py`. Auto-pull must stay best-effort: never clear an existing manual cookie, and never assume `browser_cookie3` is present.
- Keep `availability.py` a leaf (no project imports) so `touhou_tagger.py`, `gui.py`, and `library_stats.py` can import it without a cycle or pulling PyQt5 onto the CLI path. It also owns the shared platform-aware config/log path helpers; keep those stdlib-only. Mutations are keyed by `_norm()`'d absolute paths (don't bypass it — the Wiki Tagger album dir, the Statistics `root/name` artist dir, and an album's parent dir must all normalise to the same key). The Wiki Tagger album styling never touches column 0 (the directory key many callers read) — the warning is an icon + background tint only.
- For GitHub-related work, if a command fails in the restricted sandbox and completing the request may require running it outside the sandbox, first ask the user for explicit permission to retry it outside the sandbox. Once given, that permission applies to further GitHub-related work for the rest of the session; still tell the user whenever the authenticated CLI is used outside the sandbox.
