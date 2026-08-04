# Touhou Tagger — Project Context

## Goal

Tag a large personal collection of Touhou Project remix music with the **original theme names** (e.g. "U.N. Owen Was Her?", "Higan Retour ~ Riverside View") so that searching by theme name in a music player surfaces all remixes of that theme.

Additionally, write **Hepburn romaji sort keys** to the `titlesort` tag for tracks whose titles contain Japanese characters, enabling alphabetical sorting by reading rather than by Unicode code point.

## Environment

- **OS**: Fedora KDE
- **Music player**: Quod Libet
- **Tagger**: standalone PyQt5 GUI/CLI (the GUI is launched with `launch.sh`)
- **Package manager**: dnf5

## Chosen Tag Fields

### `grouping` — original theme names

The `grouping` tag (ID3v2 frame `TIT1` for MP3, `grouping` for FLAC/OGG/Opus, `----:com.apple.iTunes:GROUPING` for M4A). Quod Libet supports searching and filtering by arbitrary tags, so this field is queryable as:

```
grouping = "U.N. Owen Was Her?"
```

Multiple original themes on one track are separated by `; ` (semicolon + space).

### `titlesort` — Hepburn romaji sort key

Written by `japanese_romanizer.py` (and optionally by `touhou_tagger.py` during wiki tagging). Maps to ID3v2 frame `TSOT` for MP3, the `titlesort` Vorbis comment for FLAC/OGG/Opus, and the `sonm` atom for M4A. Contains the romaji reading of the track's `title` tag, used by music players for alphabetical sorting.

### THBWiki-sourced album metadata

Written by `touhou_tagger.py` to every file in the album, sourced from the THBWiki album info box. Each tag has its own write policy, described below.

- **`catalognumber`** — the album's catalog ID (e.g. `TOCD-0003`). Skipped if the file already has a value. For multi-disc albums where THBWiki encodes a range in slash-shorthand form (e.g. `ABCD-12345/6` for a 2-disc set), the range is expanded into individual catalog numbers (`ABCD-12345`, `ABCD-12346`) and each file receives the catno corresponding to its disc. Single-catno albums write the same value to every file. ID3: `TXXX:CATALOGNUMBER`; M4A: `----:com.apple.iTunes:CATALOGNUMBER`; Vorbis: `catalognumber`.
- **`date`** — the release date in `YYYY-MM-DD` or `YYYY-MM` or `YYYY` format. Skipped if already present. ID3: `TDRC`; M4A: `©day`; Vorbis: `date`.
- **`year`** — the release year, derived from the first four characters of `date`. Skipped if already present. Useful for players with a dedicated year column. ID3: `TXXX:YEAR`; M4A: `----:com.apple.iTunes:YEAR`; Vorbis: `year`.
- **`album`** — the album title as it appears on THBWiki. **Always overwrites** the local value on mismatch; THBWiki is considered the authoritative source. Skipped only when the local value already matches. ID3: `TALB`; M4A: `©alb`; Vorbis: `album`.
- **`genre`** — the album's genre(s) from the info box's Genre row, translated to English (e.g. `金属` → `Metal`). **Merged with the file's existing genres, not skip-if-present** (see the merge policy below): the wiki genres are unioned with whatever the file already carries, so an album keeps its pre-existing/hand-added genres and gains the wiki's styles. Written as a **proper multi-value field**, not a joined string: one `genre=` Vorbis comment per genre on FLAC/OGG/Opus (the Vorbis-comment convention for multiple genres), one `TCON` frame with multiple text values on MP3 (mutagen emits the ID3v2.4 null-separated form), one multi-value `©gen` atom on M4A. Written by `tag_io.set_genres()` rather than the single-value `_set_tag()` path. ID3: `TCON`; M4A: `©gen`; Vorbis: `genre`.

  **Merge policy (`_merge_genres` in `touhou_tagger.py`).** `genre` is the one album-metadata field that is *neither* skip-if-present *nor* overwrite-on-mismatch — it's a **union**. The rationale: the collection's files often carry pre-existing doujin/hand-added genres worth keeping (`Indie`, `Touhou`), while THBWiki supplies the actual musical styles — keeping both gives the fullest representation. Mechanics: both the existing genres and the wiki genres are run through `translate_genre()` (so a mapped pre-existing CJK genre like `独立音乐` normalises to `Indie` and dedups against a wiki `Indie` instead of sitting beside it; wiki values are already English so the pass is a no-op for them; English/unmapped existing values pass through verbatim). Dedup is case-insensitive with the **existing** genres kept first (their casing wins), then any wiki genres not already present appended. The write is skipped only when the merge equals the file's current genres (nothing new to add and no existing CJK genre to normalise), so re-tagging an already-merged album is a no-op — no churn. The log uses `[META-OVR]` (with a `was:` line) when existing genres were present, `[META]` when writing fresh.
- **`albumartist`** — the album's circle name(s) in their original (usually CJK) form (e.g. `森羅万象`). The romanised / official English form goes to `albumartistsort`. See the write policy below.

#### `albumartist` and `albumartistsort` write policy

Both fields are maintained as a pair, mirroring the `title`/`titlesort` convention:

- **`albumartist`** holds the **original (CJK) circle name(s)** as fetched from THBWiki (e.g. `森羅万象`).
- **`albumartistsort`** holds the **romanised / official English name(s)** (e.g. `ShinRa-Bansho`).

**`albumartist` (display)** — first applicable wins:

1. The fetched circle name(s) from THBWiki, joined with `" & "`.
2. An existing CJK `albumartist` already on the file (kept as-is when no fresh fetch is available).
3. Otherwise the field is left untouched — there is no CJK source (e.g. no THBWiki match).

**`albumartistsort` (romanised)** — first applicable wins:

1. An existing Latin `albumartistsort` — a hand-set value is respected and never overwritten.
2. An existing Latin `albumartist` — e.g. one left by an older romanise-in-place tagging run, reused as the sort form.
3. The romanised circle name(s) via the **romanization resolver** (TouhouDB official > THBWiki Staff map), when fully Latin.

The sort field is only written when the result is Latin *and* differs from the effective `albumartist`, so it is never a duplicate of the display name nor a second CJK copy.

Tag fields: `albumartist` — ID3: `TPE2`; M4A: `aART`; Vorbis: `albumartist`. `albumartistsort` — ID3: `TSO2`; M4A: `soaa`; Vorbis: `albumartistsort`.

### THBWiki-sourced per-track credits

Written by `touhou_tagger.py` per track, sourced from the THBWiki asktrack API and/or the rendered tracklist HTML — the latter is treated as authoritative, filling empty API credit fields unconditionally and correcting mismatched ones on THBWiki-primary runs (see the credit cross-check in "Known data gap" below). Skipped at write time if the file already has a non-empty value. Multiple names are joined with `; `. Names are romanized via the THBWiki Staff section's name mapping where available (e.g. `こたろう` → `Kota-rocK`), falling back to the Japanese/canonical name.

- **`arranger`** — track arranger(s). ID3: `TXXX:ARRANGER`; M4A: `----:com.apple.iTunes:ARRANGER`; Vorbis: `arranger`.
- **`vocalist`** — track vocalist(s). ID3: `TXXX:VOCALIST`; M4A: `----:com.apple.iTunes:VOCALIST`; Vorbis: `vocalist`.
- **`lyricist`** — track lyricist(s). ID3: `TXXX:LYRICIST`; M4A: `----:com.apple.iTunes:LYRICIST`; Vorbis: `lyricist`.

### TouhouDB-sourced per-track artist tags

Written only when the **Verify with TouhouDB** toggle is enabled (CLI: `--touhoudb`). Both tags follow skip-if-present: if the file already has a non-empty value the existing tag is left untouched. Multiple names are joined with `; `.

- **`artist`** — the original-language (Japanese/canonical) names of the track's arrangers and vocalists, in that order. These come from THBWiki's per-track `arrange`/`vocal` fields (the original-language forms stashed before any romanization). ID3: `TPE1`; M4A: `©ART`; Vorbis: `artist`.
- **`artistsort`** — the romanized form of the same names, using the **romanization resolver** (TouhouDB official > THBWiki Staff map > original). Not written if the join still contains CJK (incomplete romanization guard). ID3: `TSOP`; M4A: `soar`; Vorbis: `artistsort`.

#### Romanization resolver

Used for both `artistsort` and `albumartistsort`. Sources are tried in priority order:

1. **TouhouDB official romanization** — queried per unique artist name via `/api/artists?query=NAME&nameMatchMode=Exact&fields=Names`. Prefers English name, then Romaji. The matched entry must contain the searched Japanese name to guard against false positives. Cached per run so the same name is never fetched twice.
2. **THBWiki Staff map** — the Japanese → romanized mapping built from the album page's Staff section (e.g. `こたろう` → `Kota-rocK`).
3. **Original name** — used as a fallback when no romanization is available; the resulting `artistsort` join is then suppressed by the CJK guard so no CJK value is ever written to a sort field.

---

## Data Sources

### Primary: English Touhou Wiki

- URL: `https://en.touhouwiki.net/`
- Powered by **MediaWiki 1.39.3**, with a public API at `https://en.touhouwiki.net/api.php`
- Album pages list each track's `original title` field, which maps to the Touhou game theme that was arranged
- Accessed via **Playwright** (headless Chromium)

#### Original design: tooltip titles

The full English/romaji title (e.g. "Higan Retour ~ Riverside View") was originally **not** in the raw MediaWiki API HTML output. It was injected by JavaScript at runtime into a `title="..."` attribute on a tooltip wrapper element. Example:

```html
<span class="h:title" title="Higan Retour ~ Riverside View [Komachi Onozuka]">
  original title: <span lang="ja">彼岸帰航　～</span> Riverside View
</span>
```

The `[Character Name]` suffix in the tooltip is metadata, not part of the song title, and should be stripped.

#### Current status: tooltips no longer injected

As of 2026, the wiki stopped injecting `title=` attributes into the DOM. Both tagger scripts search for any descendant element with a `title=` attribute (Strategy 1) and find nothing. They fall back to the visible text of the `original title:` list item (Strategy 2), which contains the Japanese/mixed original name (e.g. `少女綺想曲　～ Dream Battle`). This is then translated to English via the theme mapping, the same path used for THBWiki results.

The tooltip search (Strategy 1) is still attempted first so that things will work automatically if the wiki ever restores the behaviour. The tooltip wrapper class is deliberately not constrained — it has changed at least once in the wiki's history, but the English name has always been in a `title=` attribute when present.

#### Wikitext patterns for `original title`

| Pattern | Rendered HTML | Current extraction |
|---|---|---|
| Plain text | `original title: Selection` | Visible text → use as-is; mapping lookup is a no-op |
| Japanese + English suffix | `<span lang="ja">彼岸帰航　～</span> Riverside View` | Visible text → Japanese+suffix → mapping translates |
| Japanese only | `<span lang="ja">遠野幻想物語</span>` | Visible text → Japanese → mapping translates |
| Prefix + Japanese | `U.N.<span lang="ja">オーエンは彼女なのか？</span>` | Visible text → mixed → mapping translates |
| Multiple entries | Two separate `original title:` list items | Each processed independently |

Tracks with no `original title:` field are original compositions and are skipped.

#### Zero-width space handling for page titles containing `/`

MediaWiki treats `/` as a subpage separator in page titles (e.g. `BloodDark/KARMANATIONS` would be interpreted as subpage `KARMANATIONS` of `BloodDark`). For album pages whose titles contain a literal forward slash, the wiki encodes the character with U+200B zero-width spaces on either side — e.g. `BloodDark​/​KARMANATIONS` — so the slash is a display character rather than a path separator.

`fetch_album_html` (in `touhou_wiki.py`) handles this transparently:

1. First tries the slug exactly as supplied by the user (handles bare slashes like `BloodDark/KARMANATIONS` for albums that are truly subpages).
2. If that returns HTTP 404, retries with zero-width spaces inserted around every slash (`BloodDark​/​KARMANATIONS`).

Users never need to type or know about U+200B; either form of the slug works.

### Fallback: THBWiki (thwiki.cc)

- URL: `https://thwiki.cc/`
- The largest Chinese-language Touhou wiki, with broader album coverage than the English wiki
- Uses **Semantic MediaWiki**, making track data inherently machine-readable
- Exposes a **REST API** (`asktrack`) that returns structured JSON — no HTML parsing or browser automation needed
- The `ogmusicname` field contains original theme names in ZUN's canonical Japanese/mixed format (e.g. `千年幻想郷　～ History of the Moon`)

#### asktrack API

Swagger docs: `https://thwiki.cc/rest/asktrack/v0/`

To query all tracks for an album:

```bash
curl -X POST "https://thwiki.cc/rest/asktrack/v0/query?limit=500" \
  -H "Content-Type: application/json" \
  -d '{"album":["ALBUM_NAME"],"ogmusicname":null,"trackno":null,"name":null,"discno":null,"arrange":null,"vocal":null,"lyric":null}'
```

Setting a field to `["value"]` searches by it; setting it to `null` includes it in the output without filtering.

Example response (abbreviated):

```json
{
  "results": [
    {
      "id": "NEXTRA2#1",
      "trackno": [1],
      "name": ["Kiss & Crazy (Instrumental)"],
      "ogmusicname": ["千年幻想郷　～ History of the Moon"],
      "discno": [1],
      "arrange": [{"fulltext": "鼓太蝋", "fullurl": "https://thwiki.cc/...", "exists": true}],
      "vocal": [],
      "lyric": []
    },
    {
      "id": "NEXTRA2#3",
      "trackno": [3],
      "ogmusicname": ["少女綺想曲　～ Dream Battle"],
      "arrange": [{"fulltext": "鼓太蝋", "fullurl": "https://thwiki.cc/...", "exists": true}],
      "vocal": [{"fulltext": "鼓太蝋", "fullurl": "https://thwiki.cc/...", "exists": true}],
      "lyric": [{"fulltext": "鼓太蝋", "fullurl": "https://thwiki.cc/...", "exists": true}]
    },
    {
      "id": "NEXTRA2#5",
      "trackno": [5],
      "ogmusicname": []
    }
  ]
}
```

Key fields: `trackno` (track number), `ogmusicname` (list of original theme names — empty means original composition), `name` (track title), `discno` (disc number — omitted by the API for single-disc albums, in which case the script defaults it to 1), `arrange` / `vocal` / `lyric` (per-track credits — each is a list of WpgValue objects with a `fulltext` key containing the artist name in Japanese/canonical form; empty list means not annotated for that track).

**Known data gap:** THBWiki uses Semantic MediaWiki, where the rendered page content (driven by wikitext templates) and the semantic properties (queryable via the API) are independent. Some tracks — particularly variant versions like instrumentals, piano versions, off-vocal mixes, or "separate" editions — have their original titles displayed on the rendered page but lack the `ogmusicname` semantic annotation, causing the API to return an empty list. The same gap can affect `arrange`, `vocal`, and `lyric` credit fields. More rarely, the API returns a *wrong* `ogmusicname` for a track (e.g. a cross-disc data error). The scripts work around both failure modes with an HTML cross-check (see "How it works" step 3) and a variant-title inheritance heuristic.

The HTML cross-check gap-fill runs whenever the THBWiki page is available — **regardless of which wiki was the primary source**. Previously it only ran when THBWiki itself was primary, which meant tracks with empty API `ogmusicname` were silently classified as original compositions on English-wiki-primary runs even when the rendered page had their themes. The fill-from-HTML path (empty → populated) is now unconditional; only the more aggressive *correct* (overwrite a different value) and *clear* (drop to empty) behaviours, which treat the HTML as fully authoritative, are restricted to THBWiki-primary runs. Correspondingly, `need_html` is now `True` whenever there is a tracklist, not only when THBWiki is primary or metadata/credits are requested.

The per-track credit fields (`arrange`/`vocal`/`lyric`) now follow the identical split. Previously the HTML cross-check for credits was fill-only — it could populate an empty API credit field but never touch one that already had a (possibly wrong) value. It now mirrors the title logic exactly: **fill** (empty → HTML value) runs unconditionally per field whenever the page is available, and **correct** (HTML overwrites a *different* API value) additionally runs on THBWiki-primary runs, where the page outranks the asktrack API. The log reports both counts separately, e.g. "filled 2 credit field(s), corrected 1 credit field(s) from THBWiki page HTML".

The HTML parser (in `thwiki.py`) matches track-number rows using a `class_=re.compile(r'^info[A-Z]')` regex rather than a hard-coded list of class names. THBWiki uses different `info*` classes to encode track category — `infoO` (standard), `infoRD` (re-arranged/derivative), `infoYD` (discovered on *TOUHOU meets HARDCORE 2*), and potentially others — and the suffix can appear without warning on different albums. The regex approach ensures all variants are matched automatically. The parser also accepts both `"Original Title"` and `"原曲"` as the label text, to handle variation between albums' locale settings.

**Multi-disc page layouts:** THBWiki albums present disc boundaries in two different ways depending on how the page was authored. Some use a single `<table>` with internal disc-header rows (a `<th>` cell or a `<td class="info*">` cell whose text matches `Disk1(第一部)`, `Disk2(…)`, etc.). Others use **separate `<table>` elements per disc**, preceded by `<h2>`/`<h3>` headings like `DISC-1`, `DISC-2`. The parser handles both: it iterates over `<table class="musicTable">` elements individually, and for each one walks backwards through its preceding siblings to find a heading whose text matches the disc-header pattern, setting the disc number for all tracks in that table. Internal disc-header rows still update the disc number if encountered. `_DISC_HEADER_RE` accepts both space-separated (`DISC 1`) and hyphen-separated (`DISC-1`) forms.

`_parse_thwiki_html_titles` (in `thwiki.py`) returns a tuple of two values: `track_titles` (the `{(disc, track): [theme_name, …]}` dict, only for tracks with original titles) and `tracks_seen` (a `set` of every `(disc, track)` pair encountered in the HTML, including tracks with no original title). The second value lets the cross-check distinguish "track is an original composition" (present in `tracks_seen` but absent from `track_titles`) from "track simply wasn't found in the HTML at all".

#### Album info box parsing

The album page contains a `<table class="wikitable doujininfo">` info box with structured album-level metadata. `parse_thwiki_album_info` (in `thwiki.py`) scrapes five categories of field from it:

- **Catalog number** → `catalog_numbers` (list) — expanded from any slash-shorthand range before being stored
- **Release date** → `date` / `TDRC` / `©day`; also derives a `year` tag from the first four characters
- **Album title** → `album` / `TALB` / `©alb`
- **Producer(s)** → `album_artists` (list) — raw circle names used for `albumartist` (CJK display form); romanised form (via romanization resolver) used for `albumartistsort`
- **Genre** → `genres` (list) — the info box's Genre row, split on the enumeration separators (`、`, `，`, `,`, `;`, `/` — the interpunct `・` is deliberately *not* a separator, it joins words inside one Japanese genre name) after NFKC normalisation (so full-width Latin like `Ｊｐｏｐ` folds to ASCII). Values are stored raw; `fetch_album_plan` translates them to English via `translate_genre()` (see "Genre translation" below).

THBWiki uses different album templates with inconsistent label names. The parser accepts all known variants:

| Field | Label variants seen across albums |
|---|---|
| Catalog number | `Catalog ID`, `CatalogID`, `编号`, `编号ID`, `品番` |
| Release date | `Release`, `发售日期`, `发售`, `首发日期`, `首发` |
| Album title | `Title`, `名称`, `タイトル` |
| Producer(s) | `Producer`, `制作方`, `メーカー` |
| Genre | `Genre`, `风格类型`, `ジャンル` |

Because both the info box and the tracklist use `<td class="label">` cells, the parser searches the entire page but filters by the specific label strings above, which are restrictive enough to avoid false positives from the tracklist section.

Producer cells sometimes stack multiple circle names vertically using `<br>` elements (collaboration albums). `BeautifulSoup`'s `get_text()` discards `<br>` entirely, collapsing them into a single string. The parser uses a custom `_td_text_preserving_breaks` helper that walks the cell's descendants and emits `\n` for each `<br>`, then splits and strips the result into a list of names.

Catalog number range expansion (`_expand_catalog_range`): THBWiki sometimes encodes multi-disc catalog IDs in a slash-shorthand form, e.g. `ABCD-12345/6` (meaning discs 1 and 2 have catalog IDs `ABCD-12345` and `ABCD-12346`). The function mirrors the logic in the THBWiki MusicBrainz userscript: it takes the numeric suffix of the first catno and replaces it with each integer from `start+1` to `end`, zero-padding to match the original suffix width. Falls back to a single-element list on any edge case (empty suffix, non-numeric suffix, suffix too short, end ≤ start, or digit-count boundary crossing such as `ABCD-99/100`).

#### Genre translation

The Genre row's values come from a small controlled vocabulary mixing English loan-terms (`Rock`, `House`, `Trance`, `Jpop`, …) and CJK terms (`金属`, `嘻哈`, `硬核`, …); multiple genres are separated with the enumeration comma (e.g. `House、Trance、民族、硬核、其他电子`). `thwiki.GENRE_TRANSLATIONS` maps the known CJK vocabulary to conventional English genre names (`金属` → `Metal`, `嘻哈` → `Hip-Hop`, `民族` → `Folk`, `其他电子` → `Electronic`, …; per THBWiki's own help page (`帮助:同人专辑`), `硬核` means electronic-music Hardcore, not metal/rock hardcore). Latin values pass through unchanged (so `Jpop` stays `Jpop`). An unknown CJK value falls back to itself — mirroring the theme-mapping philosophy that a kept-original is recoverable while a wrong guess isn't — and `fetch_album_plan` logs a `⚠ No English translation for genre` warning for it (detected via `genre_is_cjk()`). Translation happens in the **fetch phase**, so the `AlbumPlan` carries write-ready English values.

**The album-level label is `风格类型`, not `风格` or `曲风`.** THBWiki's help page documents two distinct genre-shaped fields in two different template sections: `风格类型` under §专辑信息 (album info) and a separate `曲风` under §曲目列表 (track listing) — the latter explicitly noted as sharing the *same vocabulary* as the album field ("这里可供选择的类型与专辑风格类型列表相同") but living on a **different, per-track** row. Since `parse_thwiki_album_info` scans every `<td class="label">` cell on the whole page (not just the info box), including `曲风` in the album-level label set would let a track's per-track style overwrite the true album genre — the parser's `elif` branch replaces the whole `genres` list on each matching row, so whichever track's `曲风` cell is encountered last would silently win over the real album value. `风格` (without `类型`) is kept as a lenient, unconfirmed fallback in case some template variant renders it bare; `风格类型` is the label actually documented and used in practice, and `Genre` is the one directly observed on a real page in English-locale form.

The help page's vocabulary notes also confirm the current translation entries are on the right track: `硬核` → Hardcore is explicit ("注意这里的硬核应指电音曲中的Hardcore，而非金属/摇滚乐"), and it gives illustrative examples of sub-genres editors are instructed to bucket into a parent term rather than write standalone — e.g. "新世纪交响"/"钢琴独奏"/"室内乐" all get filed under `古典` (Classical), and "爱尔兰"/"和风"/"二胡" under `民族` (Folk). Those sub-genre terms are not expected to appear as raw Genre values themselves. The help page does **not**, however, enumerate the full genre vocabulary — `GENRE_TRANSLATIONS` remains best-effort, extended as unrecognised terms surface via the `⚠ No English translation` log warning.

The `genre` tag deliberately does **not** appear in `EDITABLE_TAGS` (no Tag Edit column): the Tag Edit tab reads and writes one string per cell, which would collapse a multi-genre field to its first value on load and a single joined value on save.

An unrecognised THBWiki genre is surfaced live during a run as a `⚠ No English translation for genre '…' — keeping original` log warning (detected via `genre_is_cjk()`); add it to `GENRE_TRANSLATIONS` when one appears. *(A temporary accumulator that also appended these terms to an `untranslated_genres.txt` file was removed once the vocabulary stabilised — the log warning is now the only surfacing.)*

**Pre-existing / off-wiki genres go through `translate_genres.py`, not the tagger.** Genres already in a file's tags from another source (e.g. the original doujin/TLMC rip metadata — traditional-character forms like `東方アレンジ`, which THBWiki's simplified vocabulary would never carry) are only normalised by the tagger's `genre` merge when the album *also* has THBWiki genres *and* the term has a mapping (`_merge_genres` runs both sides through `translate_genre()`); an unmapped pre-existing CJK genre, or one on an album THBWiki has no genre row for, is left as-is. `translate_genres.py` is the tool for *those* — it re-reads every existing genre tag, translates in place, and reports any still CJK afterwards, without touching THBWiki. A few such pre-existing terms are mapped in `GENRE_TRANSLATIONS` under the "Pre-existing doujin file tags" group.

#### Staff section parsing and name romanization

THBWiki album pages include a Staff section with roles presented as `<p><b>Role</b></p>` headers followed by `<div class="stafflist-wrapper"><table class="stafflist">` tables. Each stafflist row typically contains `[Japanese name, Romanized name, Track range]` in separate `<td>` cells.

Before writing any credit or album-artist tags, the script builds a **Japanese → romanized name mapping** from these stafflist rows. For example, `こたろう` → `Kota-rocK`. This mapping is used as the second-priority source in the **romanization resolver** (after TouhouDB, before the original name), which drives:

- **Per-track credits** (`arranger`, `vocalist`, `lyricist`) — so the final tag values use romanized names wherever THBWiki provides them, falling back to the Japanese name otherwise.
- **`albumartistsort`** — the circle name is passed through the resolver to produce the romanised sort value.
- **`artistsort`** — per-track artist names are passed through the resolver to produce the romanized sort value.

The map is built whenever the THBWiki page HTML is fetched and either `fetch_metadata` or `fetch_credits` is enabled. Previously it was only built when `fetch_credits` was on; the broader gate ensures that `--no-credits` runs still get correctly romanized `albumartistsort` values.

#### Per-track credit tag writing

Credit names are joined with `; ` (semicolon + space) and written to:

| Credit | Vorbis | ID3 | M4A |
|---|---|---|---|
| Arrangers | `arranger` | `TXXX:ARRANGER` | `----:com.apple.iTunes:ARRANGER` |
| Vocalists | `vocalist` | `TXXX:VOCALIST` | `----:com.apple.iTunes:VOCALIST` |
| Lyricists | `lyricist` | `TXXX:LYRICIST` | `----:com.apple.iTunes:LYRICIST` |

All metadata and credit tags follow the same **skip-if-already-present** rule: if the file already has a non-empty value for a given tag, it is left untouched.

#### THBWiki as credit source when English wiki is primary

When the English wiki successfully supplies original titles (i.e. it is `source_used`), the script still fetches THBWiki for album metadata and credits:

- The THBWiki album page HTML is fetched once and reused for both the info box (metadata) and the Staff section (name mapping).
- Per-track credits (`arrange`, `vocal`, `lyric`) are fetched from the asktrack API as a separate call, then merged into the track list from the English wiki by `(disc, track number)` key.

#### THBWiki page HTML fetch — current approach

THBWiki's **asktrack REST API** (`/rest/asktrack/v0/query`) is not behind any JS challenge and is still fetched via `curl` subprocess. Python's `urllib` is blocked by TLS-fingerprint detection at the nginx level (same root cause as the English wiki), so `curl` is used for all API calls.

The **rendered album page** (`https://thwiki.cc/PAGE`) sits behind a **SafeLine WAF** challenge (Chaitin's self-hosted WAF product). The WAF serves an HTTP 200 with a challenge body rather than the real page, so the response must be validated before parsing.

Neither plain `curl` nor headless/headed Playwright can reliably clear the SafeLine challenge. The only viable solution is **browser cookie reuse**: the user solves the challenge once in their real browser, copies the full `Cookie` request header and the matching `User-Agent` from DevTools, and provides them to the tagger. The fetch then uses `curl_cffi` — a library that impersonates a real browser's TLS/JA4/HTTP2 fingerprint — so the WAF session cookie validates against the fingerprint and User-Agent it was issued to.

**The cookie is mandatory on every run, not just an optional best-effort source.** Earlier revisions fell back to a headless Playwright browser when no cookie was set, and silently skipped the HTML cross-check/metadata/credits/staff-map steps if even that failed — so a run could complete "successfully" while quietly missing data it should have had. In practice almost every artist has at least one album that's missing from the English wiki and needs THBWiki, so degrading silently was actively hiding failures rather than avoiding them. The headless-Playwright fallback has been removed entirely (along with its persistent browser profile and bundled UA constant); the page is cookie-only now, and a missing or rejected cookie is a hard, batch-fatal error instead of a quiet degradation.

This is implemented with a dedicated exception, `ThwikiCookieError` (in `thwiki.py`, re-exported by `touhou_tagger.py`) and a `validate_thwiki_cookie()` pre-flight check that fetches the THBWiki home page (gated by the same WAF as album pages) before any album is touched:

- **`ThwikiCookieError`** is raised by `_fetch_thwiki_via_cookie()` when no `THWIKI_COOKIE` is configured, or when every retry attempt comes back as a challenge page (cookie expired, or a UA/IP/TLS fingerprint mismatch). It is deliberately distinct from a plain `None` return, which still means a transport error or an album genuinely not on THBWiki — a per-album soft failure the batch can tolerate. The retry loop tracks whether *any* attempt was challenged (`saw_challenge`); if so it raises, otherwise (every attempt failed only on transport grounds) it returns `None`.
- **`validate_thwiki_cookie()`** is called once, up front, by the batch driver (`process_albums()`) so a bad cookie is caught immediately — before any album is fetched and long before any file would be tagged — rather than discovered halfway through a long batch.
- Because the standalone tagger's batch driver fetches every album before tagging any of them (see "Two-phase batch processing: fetch-then-tag" below), a `ThwikiCookieError` raised at any point in the fetch phase aborts the **entire** batch with **zero files touched** — there is no partial-tagging state to clean up.

The WAF session cookie is bound to the originating browser's TLS fingerprint, User-Agent, and IP address. Three environment variables control it:

| Variable | Purpose |
|---|---|
| `THWIKI_COOKIE` | The full Cookie request header value copied from a browser that passed the challenge. **Required** for every run (but can be supplied automatically — see auto-pull below). |
| `THWIKI_UA` | The exact User-Agent of the browser that obtained the cookie |
| `THWIKI_IMPERSONATE` | curl_cffi fingerprint family to impersonate (`chrome` default; `firefox`/`safari`/`edge` for other browser families) |
| `THWIKI_COOKIE_AUTO` | Set to `0`/`false`/`no`/`off` to disable the browser cookie auto-pull (default on); falls back to a manual `THWIKI_COOKIE` |
| `THWIKI_COOKIE_BROWSER` | Which browser the auto-pull reads from (`chrome` default; also `brave`/`chromium`/`firefox`/`edge`/`opera`/`vivaldi`/`librewolf`/`safari`) |

If the cookie is stale (expired, wrong IP, UA mismatch), the fetch retries up to 4 times with an escalating backoff (1.5 s, 3 s, 4.5 s) before raising `ThwikiCookieError`. Re-paste the cookie (or re-verify the browser session, if auto-pulling) when a run reports it was re-challenged.

##### Browser cookie auto-pull (`browser_cookie.py`)

Copy-pasting the cookie from DevTools every run is tedious — the SafeLine session rotates frequently, sometimes without a fresh human-verification in between. `browser_cookie.py` removes that step: it reads the live `thwiki.cc` cookies straight from a local browser's cookie store via the optional `browser_cookie3` package, assembles them into the full `Cookie` header (the rotating SafeLine `sl-session`, the `sl_jwt_*` pair, the Cloudflare `cf_clearance`, etc. — exactly what a manual paste of the whole DevTools `Cookie:` value would contain), and writes it into `THWIKI_COOKIE`.

- **Where it hooks in:** `_fetch_thwiki_via_cookie()` calls `browser_cookie.refresh_env(announce=True)` **before** reading `THWIKI_COOKIE`, and force-re-pulls (`refresh_env(force=True, announce=True)`) between retries whenever an attempt comes back challenged — the automatic recovery for "the cookie rotated mid-run". A 30 s TTL coalesces back-to-back reads (validation + first album) into one keyring hit. The GUI additionally pulls once at **startup** (`gui_main()`, right after the persisted UA/impersonate are loaded) and on **auth-dialog open**, so the cookie is in the environment and the dialog is pre-filled before any run begins.
- **Strictly best-effort:** if `browser_cookie3` isn't installed, or the store can't be read (e.g. the OS keyring is locked), whatever is already in `THWIKI_COOKIE` (a manual paste / shell export) is left **untouched** — it only ever *upgrades* the env cookie to a fresher one, never clears a working one. Disable with `THWIKI_COOKIE_AUTO=0`.
- **What it can't do:** it only *provides* a cookie the browser already holds; it cannot pass the SafeLine/Cloudflare human-verification challenge. When the session genuinely expires you must still solve the check once in the browser. To keep the session alive (and the rotating cookie fresh) so that's rare, run the companion `thwiki_keepalive.user.js` userscript (Tampermonkey/Violentmonkey), which silently fetches the THBWiki root every 60–120 s (jittered, with cross-tab coordination so multiple open tabs don't multiply the request rate).
- **The UA is not auto-pulled** — browsers don't expose it through the cookie store. `THWIKI_UA` still comes from the persisted config / shell export, and `cf_clearance` is bound to it, so it must match the browser the cookies came from.

`_looks_like_challenge()` checks the returned HTML for known SafeLine and Cloudflare signatures before parsing, so a challenge body is never silently parsed as an empty tracklist. The Cloudflare signatures are retained in case the site re-adds Cloudflare in front of SafeLine. **It deliberately does *not* match the bare `cdn-cgi/challenge-platform` path.** Cloudflare injects a *passive* JS-detection beacon at that path (`/cdn-cgi/challenge-platform/scripts/jsd/main.js`, alongside a `window.__CF$cv$params` blob) into **normally-served** pages too — so matching it flagged perfectly good pages (HTTP 200, real content) as challenges, a false positive that discarded valid fetches and surfaced as a spurious `ThwikiCookieError` even with a valid cookie. A genuine interactive/managed challenge is identified by the `_cf_chl_opt` blob or the "Just a moment" `<title>` (and SafeLine by its `SafeLine`/`/_safeline/` markers), which appear only on the block page; the JSD beacon uses `__CF$cv$params`, which is distinct. This bug affected the manual-cookie path as well, so the fix matters regardless of auto-pull.

The **GUI** exposes credential entry via a **"THBWiki Authentication…"** button in the Wiki Tagger tab sidebar, which opens a modal dialog with Cookie, User-Agent, and Impersonate fields. When `browser_cookie.py` is available the dialog **pre-fills the Cookie box from a live browser pull on open** (calling `refresh_env()`), so it reflects what a run would actually use instead of looking empty until the first fetch; a **"Pull from browser"** button force-re-reads it on demand (e.g. after a mid-session rotation), and a status line shows the auto-pull state (`auto-pull on — from chrome`, or the reason it's off). The User-Agent and Impersonate profile are persisted to the platform config directory's `auth.json` and reloaded at startup (older `thwiki_auth.json` files are read only as a compatibility fallback), so only the cookie needs supplying each session and auto-pull usually handles even that. The cookie is intentionally never written to disk. When the cookie is missing or stale, the GUI no longer just logs a warning and continues — `_WikiWorker` catches `ThwikiCookieError` separately from a generic crash and emits a `cookie_error` signal, which the tab shows as a **"THBWiki cookie required"** modal pointing the user back at the auth dialog; no files are tagged. The CLI equivalent is exporting the environment variables before running the script (or relying on auto-pull); a `ThwikiCookieError` there prints a message to stderr and exits with status `2` before any album is processed.

During a run, cookie activity is visible in the log pane: `refresh_env(announce=True)` prints `[browser-cookie] Loaded THBWiki cookie from <browser> (N cookie(s))` on the first load (which happens during the up-front `validate_thwiki_cookie()` step) and `[browser-cookie] Updated …` whenever the cookie has rotated since it was last reported, staying silent when unchanged. These reach the GUI log via the worker's existing `print()`→`log_message` redirection.

### Theme Name Mapping (Japanese → English)

Both tagger scripts translate Japanese/mixed theme names to English through a local JSON mapping file. This was originally only needed for THBWiki results, but since the English wiki stopped injecting tooltip `title=` attributes, the mapping is now also the primary translation path for English wiki results (whose visible text contains the original Japanese names).

#### Data source: Touhou Patch Center

The Touhou Patch Center (`thpatch.net`) maintains a theme database covering all ~850 original themes across all Touhou games and music CDs (including ZUN's Music Collection volumes like Magical Astronomy, the Akyu's Untouched Score series, fighting game soundtracks, etc.).

The API exposes both Japanese and English titles keyed by a shared theme ID (e.g. `th06_13`):

- Japanese: `https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=ja&format=json&utf8&rawcontinue`
- English: `https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=en&format=json&utf8&rawcontinue`

These endpoints are behind Cloudflare's JS challenge, so they must be saved manually from a browser (not accessible via `curl` or Playwright).

#### Mapping file: `touhou_theme_mapping.json`

Built by `build_theme_mapping.py` from the two saved thpatch.net JSON files. Contains:

- `mapping`: `{"千年幻想郷　～ History of the Moon": "Gensokyo Millennium ~ History of the Moon", ...}`
- `normalized_keys`: whitespace/tilde/punctuation-normalized lookup index for fuzzy matching between THBWiki and thpatch.net data

At lookup time: normalize the `ogmusicname` → find in `normalized_keys` → get the raw key → look up in `mapping`. Falls back to the original Japanese/mixed name if no match exists.

The mapping only needs to be regenerated when a new Touhou game or music CD is released (~850 themes total, growing by ~15–20 per new game).

### Verification source: TouhouDB (touhoudb.com)

TouhouDB is a Touhou-specific music database built on the same platform as VocaDB. It provides a public REST API at `https://touhoudb.com/api` (VocaDB-compatible). Unlike the primary sources (English wiki and THBWiki), it is **never** used for original theme names — only for verification, romanization, and cross-checking.

All requests go through `curl` via `subprocess` (same pattern as THBWiki). The client enforces a 1-request-per-second rate limit with exponential-backoff retry, a descriptive versioned User-Agent (`TouhouTagger/<VERSION> (personal music tagging project; TouhouDB verification)`), and per-run caching so the same name or album is never fetched twice. The version comes from the root `VERSION` file. All lookups are cached; per-song resolution (for auto-add) is gated behind the opt-in toggle.

#### What TouhouDB is used for

**1. Staff verification (album-level).**
After the source wiki is parsed, the script builds an album-level wiki staff set (normalized) from:
- Every track's original-language arranger/vocalist/lyricist credits.
- The album-level Staff section credits (THBWiki path: `parse_thwiki_album_staff`; English wiki path: `parse_album_staff` — each wiki gets its own parser).
- The circle name(s).

TouhouDB's album entry (circle + producers + vocalists) is compared against this set. Any TouhouDB-credited artist whose name forms (in any language) do not appear in the wiki staff set is flagged as a **missing member** and reported in the log/summary. By default they are only reported; with **Add missing TouhouDB members** enabled, they are added to the per-track `artist` field via TouhouDB's per-song credits (see below).

**2. Official name romanizations.**
The **romanization resolver** (used for `artistsort` and `albumartistsort`) queries `/api/artists?query=NAME&nameMatchMode=Exact&fields=Names` per unique CJK name. The entry must include the searched Japanese form as a `language=Japanese` name to avoid false-positive matches; if confirmed, the English name is preferred, then Romaji. All lookups are cached.

**3. Release date and catalog number cross-check.**
TouhouDB's structured `releaseDate` (year/month/day) and `catalogNumber` are compared against the values obtained from the source wiki. Differences are printed and surfaced in the summary. These fields are **never overwritten** — mismatches are notify-only.

**4. Per-track titles (third reference for the track-discrepancy check).**
When an album matches, `TouhouDBClient.album_track_titles(album_id)` returns a `{(disc, trackno) → title}` map (the song name per track). These feed the track-discrepancy comparison (see "Track-discrepancy flagging and the severe-mismatch pause" below) as a third title reference alongside the wiki and local titles, and populate the TouhouDB column of the mismatch confirmation dialog and the Changes-tab title-overwrite action. The titles come from the **same** `/api/albums/{id}?fields=Tracks` response the per-song auto-add uses (`_album_track_songs` caches both the song-id map and the title map in one pass), so reading them costs no extra request.

#### Album matching (`find_album`)

Matching must be confident and unambiguous or it returns `None` (fail-closed). A wrong match would corrupt all three features silently, so the heuristic is deliberately strict.

**Candidate generation.** Up to three search queries are sent to `/api/albums?fields=Artists&nameMatchMode=Auto&maxResults=10`, using:
1. The THBWiki album title (Japanese) — best match since TouhouDB titles are predominantly Japanese.
2. The romanized wiki slug (underscores → spaces) — fallback for entries whose TouhouDB primary name is Latin.
3. The first catalog number — good disambiguator for releases whose names vary between sources.

Candidates are deduplicated by album ID. If a catalog-confirmed match is found during query 1 or 2, querying stops early.

**Scoring.** Each candidate is evaluated against the wiki data using four signals (all normalized: names are NFKC-casefold-stripped, catalogs are uppercase-alphanumeric, dates compared at coarser precision):

| Signal | Weight | Notes |
|---|---|---|
| Catalog number match | 100 | Near-unique; decisive on its own |
| Date match | +1 bonus | Strengthens a catalog match |
| Name match | medium | Candidate name (any language) vs. wiki title/slug |
| Circle match | weak | Candidate Circle vs. wiki `album_artists` |

**Decision rule.** A candidate is accepted if:
- Its catalog matches (weight ≥ 100), OR
- Its name matches **and** at least one of {date, circle} also matches.

If multiple candidates clear the bar, the one with the highest signal score is chosen. A tie → reject (ambiguous). No candidates clearing the bar → `None`.

#### Per-song artist resolution (auto-add missing members)

When **Add missing TouhouDB members** is enabled and an album match exists:
- The album's track listing is fetched once via `/api/albums/{id}?fields=Tracks`, giving a `(disc, trackno) → song_id` map (the same fetch also caches the `(disc, trackno) → title` map used by `album_track_titles()` for the discrepancy check).
- For each local track, `/api/songs/{id}?fields=Artists` is called (rate-limited, cached), returning the song's credited producer and vocalist names.
- Any name not already in the wiki's per-track credits is added to that track's `artist` field.

This means the auto-add toggle causes one extra rate-limited request per track (plus one album-tracks fetch), in addition to the album search and per-name romanization calls. It is off by default; missing members are only reported when the toggle is off.

---

## Track-discrepancy flagging and the severe-mismatch pause

Track matching is purely positional (`match_tracks`, by `(disc, track number)` with a title fallback), so the tagger never checked whether the local titles actually agree with the fetched ones. Two things were missing: surfacing per-track problems (typos, mis-numbered tracks, missing/extra tracks), and catching the case where a folder is matched to the **wrong** wiki page entirely (bad slug / mis-named folder), which otherwise mis-tags every file silently. Both are now handled.

### `compare_tracklists()` (pure, headlessly testable)

`compare_tracklists(wiki_tracks, local_files, tdb_titles)` in `touhou_tagger.py` is Qt-free and does no I/O. It aligns local↔wiki via `match_tracks` (so its verdict matches what would actually be written), then compares each local title against the aligned wiki title — and against the TouhouDB title (`tdb_titles`, a `{(disc, number): str}` map from `album_track_titles()`) when present. The local title is the `title` tag, falling back to the filename stem with a leading track-number prefix stripped (`_local_display_title`, regex `_FILENAME_TRACKNO_RE`). Similarity is `difflib.SequenceMatcher` over `theme_mapping.normalize`'d strings (`_title_sim`, where normalized-equal == 1.0). `theme_mapping.normalize()` is NFKC + lowercase + whitespace-collapse, so full-width Latin/punctuation, the full-width tilde `～`, and the ideographic space `　` (pure typography, common in Touhou titles) fold to their ASCII forms — this is also the key `match_tracks` uses for its exact-title pairing, so those variants pair by title rather than falling through to positional. Genuine punctuation differences (a trailing `?`/`!!`) are deliberately **not** folded. The theme-translation lookup uses a *separate* `_normalize_for_mapping`, unaffected by this.

It returns `{discrepancies, severe, match_rate, local_count, fetched_count}`:

- **Discrepancy kinds** (each entry `{disc, number, kind, local, wiki, tdb, path, filename}`):
  - `title_mismatch` — aligned local/wiki (or local/TouhouDB) titles differ (likely typo or wholesale-different title at this slot).
  - `wrong_track_number` — the local title equals a wiki title that sits at a *different* `(disc, number)`.
  - `missing_local` — a fetched track no local file aligned to (`path`/`filename` empty).
  - `no_fetch_match` — a local file with no aligned fetched track (and its title isn't found elsewhere — may legitimately be an original composition).
  - `path`/`filename` point at the local file so the GUI can write a corrected `title` to it.
- **`match_rate`** — fraction of local files whose aligned fetched title agrees or is highly similar (`≥ _MATCH_RATIO`, 0.6).
- **`severe`** — `match_rate < _SEVERE_MATCH_RATE` (0.5) **or** the local/fetched counts differ by more than `_SEVERE_COUNT_DELTA` (0.5) of the larger. The three constants are module-level and tunable.

### Where it runs and what it gates

`tag_album_from_plan()` runs the comparison after scanning local files and **before writing any tags**. The report is always attached to the result dict (`title_discrepancies`, `severe_mismatch`) and surfaces in the per-album/grand summary and the Changes tab — regardless of TouhouDB. TouhouDB is only the optional third reference/column.

When `severe` is true the album looks wholesale wrong, so the run **pauses**: `tag_album_from_plan(plan, *, on_confirm=None)` calls `on_confirm(context)` (built by `_build_mismatch_context`, a plain dict of Local/TouhouDB/Wiki values per tag with a precomputed `diff` flag per row), which must return:

- `"skip"` → don't tag this album (`mismatch_skipped=True`, no writes);
- `"cancel"` → abort the whole batch (`cancel_batch=True`; `process_albums` stops after this result, like a cancel);
- `"rescan"` → re-scan the local folder and re-run the comparison (see below);
- `"continue"`/anything else → tag normally.

To make `"rescan"` possible, the whole **scan → `match_tracks` → `compare_tracklists` → severe-gate** block in `tag_album_from_plan` is a `while True:` loop (capped at `_MAX_RESCANS = 3`). When `on_confirm` returns `"rescan"` the loop re-scans `music_dir` from scratch and re-compares; if the album is no longer `severe` it falls straight through to tagging, otherwise the dialog shows again. This exists for the **"Split via CUE sheet"** recovery (below): a folder holding one un-split whole-album FLAC (+ a CUE) vs. many fetched tracks is a common severe-mismatch cause; the dialog can split the image in place, then `"rescan"` picks up the now-split tracks without restarting the run. The cap stops a split that never resolves the mismatch from looping forever (it skips after 3 tries).

With **no `on_confirm`** (CLI/headless), a severe mismatch **auto-skips** the album with a warning — an unattended batch can never mis-tag a wrong-looking album. The callback is threaded `process_albums` → `process_album` → `tag_album_from_plan`; keep `compare_tracklists`/`tag_album_from_plan` Qt-free (the GUI supplies the dialog via a signal/Event bridge, below).

New result-dict keys (also zeroed in `_empty_result`): `title_discrepancies`, `severe_mismatch`, `mismatch_skipped`, `cancel_batch`. New `AlbumPlan` fields: `tdb_track_titles` and `tdb_album_info` (`{album, date, catalog, circle}` for the dialog's TouhouDB column), both populated in `fetch_album_plan` only when a TouhouDB album matched.

### GUI confirmation dialog

In `gui.py`, `_WikiWorker` adds a `confirm_needed = pyqtSignal(dict)`, a `threading.Event`, and a `_confirm_result`. Its `_request_confirm(context)` (the `on_confirm` it passes to `process_albums`, runs on the worker thread) emits `confirm_needed` and blocks on the Event, polling `_cancel_requested` so a hard Cancel can't deadlock it; `resolve_confirm(decision)` (GUI thread) stores the answer and sets the Event (a `"cancel"` decision also flips `_cancel_requested`). `WikiTaggerTab._on_confirm_needed` (queued → GUI thread) builds and `exec_()`s the modal `_build_mismatch_dialog`: the local folder path, a **Tag / Local / TouhouDB / Wiki** tree (Album node + one node per track + a "Missing locally" node), disagreeing rows tinted the faint yellow (`_YELLOW_TINT_RGBA`, the same hue the Changes tab uses), the TouhouDB column hidden when *Verify with TouhouDB* is off, and **Skip album / Continue tagging / Cancel run** buttons (closing the dialog defaults to Skip). In `_on_all_done`, mismatch-skipped and cancel_batch results are excluded from the success/auto-clear set and reported in their own summary section.

#### "Split via CUE sheet" recovery button

The button's **visibility** is decided by `cue_split.looks_splittable(music_dir)` (plus `cue_tools_available()`), *not* by whether a CUE is found: it appears whenever the folder looks like whole-album/disc image(s) — **every audio file being a FLAC ≥ 10 min** (`_MIN_IMAGE_DURATION_SEC`; duration read from the STREAMINFO header, format-independent unlike a byte size), which covers both a lone album image *and* a folder of two-plus continuous mixes (requiring **all** the FLACs to be long, not just one, keeps a normal album with a single long track from triggering), **or** a **disc-named set** (2+ FLACs with distinct disc indicators `Disc 1`/`DISC2`/`cd 3`…, offered *regardless of duration* so short bonus discs still qualify), **or** any lone disc-named FLAC. `_build_mismatch_dialog` also runs `cue_split.detect_split(music_dir)` up front: a resolved `SplitPlan` gives a precise tooltip and is what the split actually runs; when the button was shown on the duration/disc hunch but no usable CUE exists (`detect_split` → None), clicking pops a "Nothing to split — no usable CUE sheet" warning and leaves the dialog open rather than doing nothing. It's the leftmost button in the button row. Clicking it runs `cue_split.split_plan()` on a `_CueSplitWorker` QThread behind a modal busy `QProgressDialog` (`_run_cue_split`), streaming the split log into the main log pane. A lone image splits in place (`split_album`); a multi-image plan — a disc-named set, **or** 2+ non-disc-named FLACs that are all ≥ 10 min (a folder of continuous mixes, disc numbers assigned by sorted filename) — is **pre-flighted for every image before any file moves** (all-or-nothing — a mojibake or offset-less CUE on any image aborts with "Nothing was moved or split"), then per image: a `Disc N` subfolder is created (matching `file_scan.DISC_DIR_RE`, so the re-scan assigns disc numbers), the original image + its external CUE are moved in, and the split runs there — verify + per-image trash exactly like the lone case, with a `discnumber` tag added to each split file. On a verified-clean split it pops a "Split complete" info box and closes the dialog with the `"rescan"` decision, so the worker's `tag_album_from_plan` loop re-scans the now-split folder and tags it (multi-disc via `(disc, track)` matching). On failure it shows a warning and leaves the dialog open (Skip/Continue/Cancel still available); a rare mid-plan disc failure leaves earlier discs split and names the disc that failed. The button is omitted entirely when the situation doesn't fit — so a genuinely wrong-slug album (already split, real mismatch) shows the dialog **without** it. `cue_split.py` is a Qt-free leaf; only the worker/button live in `gui.py`.

### Tag overwrite from the Changes tab

The Summary dialog's Changes tab makes three kinds of ⚠ discrepancy row actionable: **title** discrepancies (per-track), and **date** / **catalog** mismatches (album-level, from TouhouDB). Each actionable row stashes a generalized **action dict** on the item (`_disc_data_role`, attached via the build-local `_attach_action()` helper) and is collected in `self._disc_items`. An action carries `tag` (`title`/`date`/`catalognumber`), `scope` (`track`/`album`), the candidate value per source (`wiki`/`tdb`), a `current` value for the skip/no-op check, and per-kind flags (`romanize` for title, `also_year` for date). Title actions store the per-track `path`; date/catalog actions store the `music_dir` and resolve to *every* file in the album at apply time via `_resolve_action_paths()` (→ `scan_music_files`); a date/catalog row is only made actionable when `music_dir` and the source value are both present.

The Changes tree uses `ExtendedSelection`, so several rows can be hand-picked with Ctrl-click (toggle) / Shift-click (range). **Right-click** any selected actionable row(s) → *Set selected from Wiki* / *Set selected from TouhouDB* (per-source enabled via `_overwrite_target(action, source)`, which returns `None` when the source has no value or it already matches `current` via `normalize` — so the "wiki" source is a no-op on a date/catalog row, whose displayed value *is* the wiki value). **Multi-select spans mixed tag kinds**, so one *Set selected from TouhouDB* can fix a title, a date, and a catalog in a single action.

The bottom **action bar** has one **split `QToolButton` per source** (only sources with an actionable value get a button — so "wiki" is dropped when only date/catalog rows exist). Each button is `InstantPopup` and its menu lists a *granular per-tag* entry for every tag kind that has an actionable discrepancy for that source (e.g. *Set all catalog numbers from TouhouDB*, built from `src_tags` in fixed `_TAG_ORDER` = title, date, catalognumber; the recommended safe path, since a source may be wrong for one tag but right for another), then a separator, then a **bold-red destructive entry** *Set all mismatches from …* (rendered via a `QWidgetAction`+styled `QLabel` helper, `_danger_menu_action`). Both call `_overwrite_all(source, tag=None)` — `tag` scopes to one kind (standard confirmation) while `tag=None` is the catch-all path (a stronger "Are you sure you want to overwrite all mismatches?" `QMessageBox` defaulting to Cancel). `_overwrite_entries(entries, source)` writes each action's tag via `tag_io._set_tag` to its resolved path(s) (date rows also derive `year` from the first four chars), and for title actions **re-romanises `titlesort`** via `japanese_romanizer.romanize_file(force_titlesort=True)` (a Japanese/partly-Japanese new title gets a fresh romaji sort key; a Latin one is left alone). All paths skip already-matching rows. These writes happen **for real even in a dry-run pass** — they're an explicit after-the-fact correction; applied rows are marked ✓ and dropped from the actionable set, and a popup reports the rows/files written (and titlesort re-romanisations). "Missing members" rows remain notify-only — adding those names is the *Add missing TouhouDB members* toggle's job.

---

## Files

| File | Purpose |
|---|---|
| `build_theme_mapping.py` | One-time setup / after a new Touhou game release — builds the Japanese→English theme name mapping file |
| `touhou_theme_mapping.json` | Output of the above; used by both tagger scripts as a translation table |
| `touhou_tagger.py` | Standalone tagger entry point and orchestrator — GUI dispatch (no args), CLI argument parsing, logging setup, romaniser import. Tagging logic is split into `fetch_album_plan()` (all network I/O for one album, returns an in-memory `AlbumPlan`) and `tag_album_from_plan()` (all local file I/O for one album, returns the summary dict); `process_album()` is a thin back-compat wrapper calling both in sequence. `process_albums()` is the batch driver: validates the mandatory THBWiki cookie once (`validate_thwiki_cookie()`), fetches every album's `AlbumPlan` first, then tags every album from the cached plans — so a `ThwikiCookieError` partway through fetching aborts the whole batch before any file is touched. The summary dict returned per album includes `tag_changes` (list of per-track `{"filename", "tag", "old", "new"}` dicts recording every tag write/overwrite/clear/delete) and `music_dir` (the local directory path), in addition to the per-category counters and TouhouDB mismatch fields. Also home to the pure `compare_tracklists()` track-discrepancy check and `_build_mismatch_context()`; `tag_album_from_plan(plan, *, on_confirm=None)` runs the check before writing and pauses/auto-skips on a severe mismatch — its scan→compare→confirm block is a capped loop so an `on_confirm` returning `"rescan"` (the GUI's CUE-split recovery) re-scans and re-compares (see "Track-discrepancy flagging and the severe-mismatch pause"). The result dict carries `title_discrepancies`, `severe_mismatch`, `mismatch_skipped`, and `cancel_batch`. |
| `touhou_wiki.py` | English Touhou Wiki fetching (Playwright/Chromium) and HTML parsing |
| `thwiki.py` | THBWiki asktrack API, mandatory-cookie HTML page fetching (curl_cffi), `validate_thwiki_cookie()` pre-flight check, `ThwikiCookieError`, `_looks_like_challenge()` (challenge detection, JSD-beacon-aware), browser cookie auto-pull hook, album info/staff/credits parsing |
| `cue_split.py` | Splits un-split whole-album FLAC image(s) into per-track FLACs via CUE — the GUI mismatch dialog's "Split via CUE sheet" recovery. `detect_split()` (the GUI entry point) recognises a lone one-FLAC-plus-CUE folder, a multi-disc set (2+ FLACs with distinct disc-indicator names, `_DISC_IN_NAME_RE`, any duration), **or** 2+ non-disc-named FLACs that are all ≥ 10 min (`_MIN_IMAGE_DURATION_SEC` — continuous mixes, disc numbers by sorted filename); each image is paired with its own CUE (same stem → disc-number match for disc-named → embedded CUESHEET) via the shared `_build_multi_plan()` (all-or-nothing) and returns a `SplitPlan`. `detect_cue()` remains the lone-image primitive and `looks_splittable()` is the cheaper button-visibility gate (all-FLAC-and-all-long, or disc-named). Every CUE source (external `*.cue`, embedded `CUESHEET` Vorbis comment, binary FLAC CUESHEET block) is parsed for per-track `INDEX` start times + `FILE` count and the best offsets are **merged with the best titles by track number** (the common EAC/TLMC layout: a multi-`FILE` sidecar `.cue` with titles-but-no-offsets + a single-file embedded CUESHEET with offsets-but-no-titles). `split_plan()` executes: lone → `split_album()` in place; multi-disc → pre-flight *all* discs, then per disc create a `Disc N` subfolder (matches `file_scan.DISC_DIR_RE`), move the image + its CUE in, split there, and add a `discnumber` tag. `split_album()` mojibake-guards the CUE titles (encoding auto-detect preferring the decode with the most CJK/kana, rejecting U+FFFD / control chars), then cuts each track with **`ffmpeg`** at breakpoints computed from the `INDEX` times (`-ss`/`-t`, `-map 0:a:0`; sample-accurate, format-preserving) — **not** `shnsplit`, whose WAV→`flac` pipe flac 1.4+ rejects and which can't split a multi-FILE CUE. A multi-FILE CUE or non-increasing starts are refused with a clear message. Tags each output with `mutagen` (title/tracknumber/discnumber/artist/album — **not** `cuetag`, which mangles Shift-JIS CUEs), verifies with `flac -t`, then moves the original to Trash (`gio trash`, falling back to `trash-put`/`kioclient5`). `CueDecodeError`/`SplitResult`/`SplitPlan` dataclasses. Leaf module — no project imports; soft-imported by `gui.py` (the `_CueSplitWorker` QThread + dialog button) and importable from `touhou_tagger.py` |
| `browser_cookie.py` | Optional live cookie pull from a local browser via `browser_cookie3` — assembles the full `Cookie` header and injects the site's cookie env var. Uses a `site=THWIKI`-default site-profile tuple (domain + `*_COOKIE`/`*_COOKIE_AUTO`/`*_COOKIE_BROWSER` names) so another WAF-gated site could be added without touching call sites; TTL/announce state is keyed by domain. Leaf module (no project imports); soft-imported by `thwiki.py`, `gui.py`; best-effort (never clears a manual cookie) |
| `thwiki_keepalive.user.js` | Tampermonkey/Violentmonkey userscript — silently pings the THBWiki root every 60–120 s (jittered, cross-tab-coordinated) to keep the WAF session warm so the auto-pulled cookie stays valid. Not Python; installed in the browser |
| `availability.py` | Persistent **"unavailable on the wikis"** marks for albums and artists that have no page on either wiki (and so can't be tagged), plus shared stdlib-only helpers for platform-appropriate user config/log directories. Stores absolute directory paths in the platform config directory's `availability.json` behind a module-level in-process cache, so a mark made in one tab is instantly visible in the other. Leaf module (no project imports — same constraint as `browser_cookie.py`); imported by `touhou_tagger.py` (log path), `gui.py` (auth path + Wiki Tagger album marks), and `library_stats.py` (config/cache paths + Statistics artist marks / yellow pie slice). All keys go through `_norm()` (abspath+normpath) so a folder maps to one key regardless of how the path arrives |
| `external_tools.py` | Persistent external-command discovery and GUI path overrides (leaf; no project imports). `resolve_tool()` is imported at module top by `thwiki.py`/`touhoudb.py`/`cue_split.py`/`library_stats.py`, so an override applies on the CLI path too, not just the GUI. Overrides persist to the platform config directory's `external_tools.json`; a broken override returns `None` (no silent PATH fallback) so a misconfigured tool fails loudly |
| `album_overrides.py` | Persistent, path-keyed reviewed Wiki Slug overrides (leaf; imported by `gui.py`). Stores `{album dir → slug}` in the platform config directory's `album_overrides.json`; lookup-only (returns just the slug). A saved/edited slug also disables the capitalization-variant retries via the `slug_is_auto` gate |
| `preferences.py` | Non-secret GUI behavior/window/CUE preferences (leaf) — window geometry, last tab, CUE post-split action, and the **folder scan depth** (`scan_depth`, 1–3; default 1). Persists to the platform config directory's `preferences.json`; recomputes its path per call so it honours a relocated config dir |
| `config_backup.py` | Allow-listed, secret-free config export/import (leaf). Export copies only whitelisted config values — cookies are never included even if planted in a source file; import re-applies the same allow-list and rejects a wrong `format`. Writes atomically (`*.json.tmp` → `os.replace`) |
| `app_version.py` | Single source of the application version — reads the repository-root `VERSION` file once at import and exposes `__version__` plus a shared `USER_AGENT` string. Leaf, standard-library only; imported by `touhou_tagger.py` (the `--version` flag + log header), `touhou_wiki.py`, and `touhoudb.py` (outgoing User-Agent), so all three report the same version without duplicating it |
| `tag_io.py` | Audio tag reading/writing across MP3, FLAC, OGG, Opus, M4A — format dispatch, CJK/Latin script detection, bulk tag reading (`read_all_tags`) |
| `touhoudb.py` | TouhouDB verification source — curl-based client, album matching heuristic, per-name romanization, staff verification, per-song artist resolution, and per-track titles (`album_track_titles()`, sharing the one Tracks fetch) for the track-discrepancy check |
| `theme_mapping.py` | Theme name translation (Japanese → English via mapping file), variant title inheritance |
| `file_scan.py` | Local directory scanning, disc subdirectory detection, wiki slug guessing, album folder classification |
| `gui.py` | PyQt5 GUI — Wiki Tagger tab, Romanise tab, Tag Edit tab, Statistics tab, QThread workers, drag-and-drop, cross-tab "Send to…", per-album segmented fetch status strip (`_FetchStatusBar`) |
| `library_stats.py` | Statistics tab — scans a whole music library laid out as `<root>/<artist>/<album>/<tracks>` for grouping-tag coverage and shows a clickable tagged/untagged/**unavailable**-artist pie chart plus theme- and genre-popularity bar charts (via the "Popularity charts" drop-down; the genre chart hides the release-type `Game`/`Indie` labels in `_EXCLUDED_GENRES`). Self-contained Qt module (imports PyQt5 at module top); lazy-imported by `gui.py` inside `gui_main()` so the CLI path stays PyQt5-free. Pure scan logic (`scan_library()`, `load_known_themes()`, `classify_artist_albums()`) has no Qt dependency. Imports `availability` to partition artists into the third (yellow) "unavailable" slice. Named `library_stats` rather than `statistics.py` to avoid shadowing Python's stdlib `statistics` module |
| `japanese_romanizer.py` | Companion romaniser — writes Hepburn romaji `titlesort` tags for Japanese-titled tracks. Used automatically by `touhou_tagger.py` when present; also runnable as a standalone tool for any Japanese album regardless of Touhou wiki coverage |
| `translate_genres.py` | Standalone CLI (imports only `tag_io` + `thwiki`; no network, no Qt) that walks folders, reads each file's multi-value `genre` tag, re-runs every value through `thwiki.GENRE_TRANSLATIONS`, and rewrites the tag when anything changed. The fast way to apply **newly-added genre mappings** to a library that was tagged before those mappings existed — the tagger's `genre` write is skip-if-present, so re-running it won't fix already-written CJK values, but this will. Idempotent (a second pass over English tags writes nothing); `--dry-run`/`--verbose` supported; reports which mappings fired and any CJK terms still missing from the table |
| `japanese_romanizer_data.py` | Data companion to the romaniser — contains `_LOANWORDS`, `_TITLE_OVERRIDES`, and `_PHRASE_OVERRIDES` dicts. May also be named `japanese_title_to_romaji_data.py` as a legacy filename; both names are tried at import time |

### Module architecture (standalone tagger)

The standalone tagger is split across the Python files in `source/`. `touhou_tagger.py` is the entry point and orchestrator; the others are imported as modules.

```
touhou_tagger.py          ← entry point, fetch_album_plan()/tag_album_from_plan()/
                             process_album()/process_albums(), CLI, GUI dispatch
  ├── touhou_wiki.py      ← English wiki (Playwright + BeautifulSoup)
  ├── thwiki.py           ← THBWiki (curl_cffi + mandatory cookie + BeautifulSoup)
  │     └── browser_cookie.py  ← optional live cookie pull (browser_cookie3); soft import
  ├── touhoudb.py         ← TouhouDB verification (curl + stdlib only)
  ├── tag_io.py           ← mutagen read/write, CJK detection
  ├── theme_mapping.py    ← JP→EN translation, variant inheritance
  ├── file_scan.py        ← directory scanning, slug guessing (imports tag_io)
  ├── availability.py     ← persistent "unavailable on the wikis" marks (leaf;
  │                         also imported by library_stats.py)
  └── gui.py              ← PyQt5 GUI (lazy-imported only when no CLI args; also imports
        │                    tag_io, browser_cookie and availability directly)
        └── library_stats.py  ← Statistics tab (imports file_scan / tag_io /
                                theme_mapping / availability; lazy-imported only
                                inside gui_main)
```

The import graph is acyclic: `gui.py` imports from `touhou_tagger`, `file_scan`, `tag_io`, and `availability`, but `touhou_tagger.py` only imports `gui` lazily inside `main()` when no CLI arguments are given. `gui.py` in turn imports `library_stats` lazily inside `gui_main()`, so the CLI path never pulls in PyQt5; `library_stats.py` only imports leaf modules (`file_scan`, `tag_io`, `theme_mapping`, `availability`). `browser_cookie.py` and `availability.py` are both leaves that import nothing from the project — `browser_cookie.py` so `thwiki.py`/`gui.py` can soft-import it, and `availability.py` so both `gui.py` and `library_stats.py` can import it without a cycle (it carries the shared in-process "unavailable" cache the two tabs both read/write). All other imports flow downward from `touhou_tagger.py` into the leaf modules.

The per-album orchestration logic in `touhou_tagger.py` is split into two halves joined by an in-memory `AlbumPlan` dataclass (see "Two-phase batch processing: fetch-then-tag" below for the full rationale):

- **`fetch_album_plan()`** — all network I/O for one album: queries `touhou_wiki`/`thwiki`, fetches the THBWiki page (mandatory cookie), cross-checks and translates titles/credits via `theme_mapping`, and runs TouhouDB verification via `touhoudb`. Returns an `AlbumPlan`.
- **`tag_album_from_plan(plan, *, on_confirm=None)`** — all local file I/O for one album: scans the directory via `file_scan`, runs the `compare_tracklists` discrepancy check, matches tracks, and writes tags via `tag_io`. Takes the `AlbumPlan` produced above and does no further network access (aside from the optional, cookie-independent TouhouDB per-song auto-add lookups). On a severe mismatch it calls `on_confirm` (GUI) to skip/continue/cancel, or auto-skips when no callback is supplied (CLI) — see "Track-discrepancy flagging and the severe-mismatch pause".
- **`process_album()`** — a thin back-compat wrapper: `fetch_album_plan()` followed immediately by `tag_album_from_plan()`, for any caller that wants the old one-call-per-album behaviour (forwards `on_confirm`).
- **`process_albums()`** — the batch driver used by both the CLI and the GUI: validates the cookie once, fetches every album's plan, then tags every album from the cached plans (forwarding `on_confirm`; a `cancel_batch` result stops the batch). The GUI workers (`gui.py`) call `process_albums()` on a background thread.

---

### Dependencies

None beyond Python's standard library.

### Setup (one time)

1. Open the two thpatch.net API URLs in a browser and save the JSON responses:

   ```
   https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=ja&format=json&utf8&rawcontinue
   https://www.thpatch.net/w/api.php?action=query&list=tdbtitles&language=en&format=json&utf8&rawcontinue
   ```

   Save as e.g. `thpatch_ja.json` and `thpatch_en.json`.

2. Run the builder:

   ```bash
   python build_theme_mapping/build_theme_mapping.py \
       build_theme_mapping/thpatch_ja.json build_theme_mapping/thpatch_en.json \
       --output source/touhou_theme_mapping.json
   ```

3. Place the output `touhou_theme_mapping.json`:
   - In `source/`, next to `touhou_tagger.py`, for the standalone script

### How it works

1. Loads both JSON files and extracts the `tdbtitles` dicts (theme ID → title)
2. Correlates entries by theme ID, pairing each Japanese name with its English translation
3. Filters out stub entries where the "title" is just a track identifier code (e.g. `th07_10`, `mcd_09_01`)
4. Builds a normalized key index for fuzzy matching (collapses fullwidth spaces, tilde variants, etc.)
5. Outputs the mapping ordered by game chronology (th01 → th20+ → music CDs → Seihou → other)
6. Reports duplicate themes (same theme in multiple games), empty/invalid entries, and already-English titles

### What it excludes

Entries whose Japanese title begins with `th0`, `th1`, `th2`, `mcd`, `alcostg`, or `sh0` are excluded — these are thpatch.net stub entries where the title is just the internal track identifier, not a real theme name.

---

## Standalone Script: `source/touhou_tagger.py` and modules

The standalone tagger is the entry point `source/touhou_tagger.py` plus its companion modules in `source/`. All standalone application files share that directory. See the Module Architecture section above for the import graph.

### Dependencies

For a complete inventory of external executables, installation routes, and
missing-tool behaviour, see [`EXTERNAL_TOOLS.md`](EXTERNAL_TOOLS.md).

```bash
# Core (required — THBWiki tagging works with just these):
pip install -r requirements.txt          # beautifulsoup4, mutagen, curl_cffi

# Optional groups (install only what you need):
pip install -r requirements/gui.txt           # PyQt5 — GUI mode
pip install -r requirements/browser-fetch.txt # Playwright — English wiki
python -m playwright install chromium          # only if browser-fetch installed
pip install -r requirements/cookie-auto-pull.txt  # browser_cookie3 — cookie auto-pull
```

Also requires `curl` (for THBWiki API requests), which is preinstalled on Fedora. `browser_cookie3` is optional: with it, the mandatory cookie is read from the browser automatically; without it, the cookie must be supplied manually (paste/export) but everything else works unchanged. PyQt5 is required only for GUI mode (the CLI runs without it). A **THBWiki browser cookie is mandatory for every run** (see "THBWiki page HTML fetch — current approach" above) — `curl_cffi` is what makes that cookie actually work: without it, the fetch falls back to plain `curl`, whose TLS fingerprint won't match the browser that obtained the cookie, so SafeLine re-challenges it and the run aborts with `ThwikiCookieError` regardless of how valid the cookie itself is. Playwright is an **optional** dependency used only for the English Touhou Wiki (`touhou_wiki.py`, which soft-imports it) — when it is absent the English-wiki step is skipped and THBWiki (the mandatory source) is used instead. `thwiki.py` no longer uses Playwright at all (the former headless-Playwright fallback for the THBWiki page was removed; see above).

### Usage

Running with no arguments launches the GUI:

```bash
python source/touhou_tagger.py
```

CLI mode is used when arguments are provided:

```bash
# Dry run first — no files are modified (grouping or titlesort)
python source/touhou_tagger.py "Wishes_Hidden_In_The_Foreground_Noises" "path/to/Wishes" --dry-run

# Apply for real
python source/touhou_tagger.py "Wishes_Hidden_In_The_Foreground_Noises" "path/to/Wishes"

# Multiple albums in one invocation:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" "Unforgettable_Duet" "path/to/Duet" --dry-run

# Force THBWiki only (skip English wiki):
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --thwiki-only

# Specify a different mapping file:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --mapping "path/to/touhou_theme_mapping.json"

# Skip romanisation for this run:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --no-romanize

# Overwrite existing titlesort tags:
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --force-titlesort

# Enable TouhouDB verification (staff check, romanizations, date/catalog cross-check):
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --touhoudb

# Also auto-add TouhouDB-only members to per-track artist (per-song resolution):
python source/touhou_tagger.py "NEXTRA2" "path/to/NEXTRA2" --touhoudb --touhoudb-add-missing
```

The wiki page name is the URL slug (spaces replaced with underscores). The same name is tried on both wikis. Multiple album/directory pairs can be given; the batch fetches every album first and only then tags any of them (see "Two-phase batch processing: fetch-then-tag" below), and a grand summary is printed at the end of multi-album runs. A valid `THWIKI_COOKIE` is required for every invocation, including titles-only runs — see "THBWiki page HTML fetch — current approach" above; if it's missing or rejected, the run prints a message to stderr and exits with status `2` before any album is fetched.

### GUI mode

The GUI launches when running the script with no arguments. The window is split into tabs — Wiki Tagger, Romanise (only when the romaniser is ready), Tag Edit, and Statistics.

Queue management lives in a window-level **File menu** (built in `TaggerWindow`, inside `gui_main()`) rather than as per-tab buttons — the old per-tab "Add Folders…" / "Remove Selected" / "Clear All" `QPushButton`s were removed from all three queue tabs (the Expand All / Collapse All / Tag All / Cancel / Romanise All / Save Changes buttons remain). The menu contains:

- **Add Folders… (Ctrl+O)** — opens the multi-select folder picker.
- **Remove Selected** — removes the selected queue row(s).
- **Clear All** — empties the queue/table.
- **Refresh (F5)** — re-checks the queued folders against the disk, picking up metadata or structure changes made outside the program (e.g. a split FLAC image). Each tab implements its own `_refresh_queue()`; the per-tab behaviour is described in the tab sections below.
- **Exit (Ctrl+Q)** — closes the window via `close()`, so it routes through `closeEvent` and the Tag Edit unsaved-changes warning still applies.

Each action dispatches to the **active tab's** `_add_folders` / `_remove_selected` / `_clear_all` / `_refresh_queue` handler (`_file_menu_call()`). The four queue actions are enabled on the Wiki Tagger, Romanise, and Tag Edit tabs and disabled on Statistics (`_update_file_menu()`, re-evaluated on every tab switch); Exit always works.

#### Wiki Tagger tab

The primary tab. Provides:

- **Drag & drop** from Dolphin (or any file manager) and **File → Add Folders… (Ctrl+O)**: drop or select one or more album folders. Both also accept *artist container folders* (e.g. `[Artist]` folders): if a dropped/selected folder doesn't itself contain audio files, the script looks one level down and adds its album subfolders instead. A folder is considered an album if it contains supported audio files directly, or if it contains `Disc N`/`CD N`-style subdirectories that themselves contain audio. This expansion is one level deep only — individual album folders can still be dropped directly.
- A **tree view** listing queued albums as expandable top-level rows. Expanding an album row reveals its tracks and any existing `grouping` tag values, making it easy to see at a glance which songs have already been tagged and which haven't. Tracks are shown in disc/track order; multi-disc tracks are prefixed `D-NN.` (e.g. `1-03.`, `2-01.`). After a successful (non-dry-run) tagging pass, the tree is refreshed in place to show the newly written grouping values — the album's expanded/collapsed state is preserved, only the child rows are rebuilt. Skipped in dry-run mode (nothing was written) and when auto-clear is on (the rows are about to be removed).
- **Four columns**: Directory, Album, Wiki Slug, and Grouping. All columns are resizable by dragging the header boundary. Click any column header to sort rows alphabetically by that column; click again to reverse. Within an expanded album, track rows also sort by the clicked column (e.g. sorting by Grouping clusters tracks with the same theme together).
- **Auto-suggested wiki slugs**: the `album` tag from the first music file in each folder is read and converted to a URL slug (spaces → underscores). When no album tag is present, the folder's basename is cleaned up before use: a leading date stamp (`YYYY.MM.DD`, `YYYY-MM-DD`, `YYYYMMDD`) is stripped, then any bracketed segments (`[CATALOG-ID]`, `[C100]`, `[M3-49]`, `[例大祭21]`, etc.) are removed, and residual double/leading/trailing underscores are collapsed. For example, `2022.08.14_[EUCD-0022]_EURO_BAKAICHIDAI_VOL.22_[C100]` is reduced to `EURO_BAKAICHIDAI_VOL.22`. To edit a slug, double-click its cell in the Wiki Slug column. Double-clicking anywhere else on an album row toggles its expand/collapse state. A slug left at its auto-suggestion also gets **capitalization-variant retries** when it matches neither wiki (up to three extra lookup passes — see "Capitalization-variant retries" under "How it works" below); a hand-edited slug is used exactly as typed, with no retries.
- **Expand All** and **Collapse All** buttons to show or hide all track rows at once.
- **File → Refresh (F5)** (`_refresh_queue()`): re-checks every queued album folder against the disk. Folders that no longer exist are removed from the queue (logged as `✖ Removed missing folder`); the remaining albums get their track/grouping rows re-scanned — picking up structure changes made outside the program, such as a FLAC image split — and their auto-suggested slug and Album column re-guessed from the current tags. A hand-edited slug is preserved: the auto-guess is stashed in a `Qt.UserRole` on the Wiki Slug column at add time, and the slug is only replaced when the cell still matches that stored guess (the stored guess is then updated either way, so a later refresh compares against the freshest auto-suggestion). Unavailable-mark styling is re-applied afterwards.
- **Settings sidebar** with the following checkboxes (kept in alphabetical order):
  - **Auto-clear done**: remove successfully tagged albums from the queue once the run completes.
  - **Auto-romanise titles** (only shown when the romaniser is ready): defaults to on; writes romaji `titlesort` tags interleaved with the `grouping` writes in the same pass.
  - **Dry run**: show what would be tagged without writing to disk.
  - **Force overwrite existing titlesort** (only shown alongside "Auto-romanise titles"): defaults to off; when off, existing `titlesort` tags are preserved and the log shows what would have been written.
  - **Skip fully-tagged on add**: when checked, albums where a **majority** of tracks are already tagged are silently skipped when added to the queue (e.g. 7 of 12, or 8 of 15). A track counts as tagged when it has a `grouping` tag. This tolerates a few untaggable original compositions scattered throughout an album without preventing the skip. Albums whose tracks couldn't be read are still added. Useful for re-processing a large music directory after most albums have already been tagged. The log records the skip as "⏭ Skipping mostly-tagged album (N/M tracks)". (`scan_album_for_view()` reads the `grouping` tag via `tag_io.read_grouping()`.)
  - **Skip genre-tagged on add**: when checked, albums that already carry any genre the wiki tagger writes are silently skipped when added to the queue. Purpose: after tagging a collection before the `genre`-fetch feature existed, this surfaces only the albums still missing wiki genres. "The genres the tagger writes" means its **translated musical-style vocabulary** — the English values of `thwiki.GENRE_TRANSLATIONS` (Metal, Rock, Trance, …), exposed as a casefolded set by `thwiki.tagger_genre_vocabulary()`. An album is skipped if **any** track carries **any** genre in that set (case-insensitive), matching that the tagger writes `genre` album-wide. Deliberately **excluded** from the vocabulary (`thwiki._NON_STYLE_GENRES`) are the provenance / release-type labels the tagger keeps but never fetches as a musical style — `Indie`, `Touhou`, `Touhou Arrange` — so the common pre-existing doujin tags don't over-skip the whole library. Known limits (accepted): a pass-through Latin genre the tagger writes verbatim that isn't in the map (e.g. `Jpop`) won't be recognised (false negative), and a stray pre-existing musical genre (e.g. a hand-set `Metal`) reads as tagged (false positive). Genres are read (via `tag_io.read_genres()`) **only when this toggle is on**, so the default add path keeps its single open per track. The log records the skip as "⏭ Skipping album that already has wiki genre tags: <path>". Independent of "Skip fully-tagged on add" — either, both, or neither may be enabled.
  - **THBWiki only**: skip the English wiki and query THBWiki directly.
  - **Verify with TouhouDB**: enable TouhouDB (touhoudb.com) as an optional verification source — compares wiki staff against TouhouDB, prefers TouhouDB official romanizations for `artist`/`artistsort`/`albumartistsort`, and cross-checks the release date and catalog number (differences reported only, never overwritten). Off by default.
  - **Add missing TouhouDB members**: only active when "Verify with TouhouDB" is enabled. When a TouhouDB-credited staff member is absent from the wiki, add them to the per-track `artist` field using TouhouDB's per-song credits (one rate-limited request per track). Off by default.
- **THBWiki Authentication… button**: opens a modal dialog for supplying browser credentials so THBWiki album pages can be fetched past the SafeLine WAF challenge. A valid cookie is now **mandatory for every run** — see "THBWiki page HTML fetch — current approach" above. The dialog contains three fields:
  - **Cookie**: the full `Cookie` request header value copied from a browser that has already passed the challenge. Per-session only — never written to disk.
  - **User-Agent**: the exact User-Agent of that browser (the WAF session cookie is bound to it).
  - **Impersonate**: the curl_cffi TLS fingerprint profile to use — `chrome` (default), `firefox`, `safari`, or `edge`. Match the family of the browser the cookie was obtained from.
  
  On Save, the cookie/UA/impersonate are applied to the process environment for the current session. The User-Agent and Impersonate profile are also **persisted** to the platform config directory's `auth.json` and reloaded at next launch; older `thwiki_auth.json` files are read only as a compatibility fallback. Only the cookie needs supplying when a run reports it was re-challenged, and the Cookie header itself is never written. A **Clear** button wipes both the environment and the config file. When `browser_cookie.py` is available the dialog **pre-fills the Cookie box from a live browser pull on open** (it calls `browser_cookie.refresh_env()`), so it reflects what a run would actually use rather than looking empty; a **"Pull from browser"** button force-re-reads the live cookie on demand (disabled when auto-pull is unavailable), and the status line reports the auto-pull state (`auto-pull on — from chrome`, or the reason it's off) alongside whether a cookie is currently set. Otherwise the dialog pre-fills from the current environment, so shell-exported values are visible and editable. The CLI equivalent is exporting `THWIKI_COOKIE`, `THWIKI_UA`, and optionally `THWIKI_IMPERSONATE` (or relying on auto-pull) before running the script. If the cookie turns out to be missing or stale when "Tag All" is run, the worker aborts before tagging anything and a **"THBWiki cookie required"** modal appears pointing back at this dialog (see "GUI threading model" below).
- **Tag All** button: processes all albums in the background; the log area shows live interleaved output for both grouping and titlesort operations.
- **Cancel** button (and **Esc** shortcut): requests graceful cancellation after the current album finishes. The in-progress album always completes fully before the run stops — no partial state is left. The button is disabled when no run is in flight. While waiting for the current album to finish, both the Tag All and Cancel button labels change to indicate cancellation is pending. The summary dialog notes how many albums were processed before stopping.
- A **fetch status strip** (`_FetchStatusBar`) sits just above the progress bar, with extra vertical spacing around both to give the two bars room. It's a thin, segmented strip with one section per queued album, ordered left-to-right in the same order as the queue (leftmost = first album, rightmost = last) — so it fills in during the **fetch phase** (phase 1 of `process_albums()`), which the progress bar below doesn't move for, giving the fetch phase visible progress for the first time. Each section starts in a muted "pending" shade and is coloured in as its album's fetch completes: the palette highlight colour for a successful fetch, red for one that failed or wasn't found — so a batch with, say, the 2nd and 6th albums missing shows those two sections red while the rest stay the default colour, making failures visible at a glance without reading the log. Each section is clickable (cursor changes to a pointing hand, and hovering shows a tooltip naming the album index): clicking jumps the log view to that album's `[fetch i/N]` marker, so its fetched data (titles, credits, metadata, any cross-check messages) is easy to review without scrolling. The strip becomes visible at the start of a run (reset to all-pending for the new album count) and remains visible afterward as a record of the last fetch phase, mirroring how the progress bar below it behaves.
- A **progress bar** between the Tag All/Cancel buttons and the log, showing `N / M albums (P%)`. Hidden until the first run of a session, then stays visible after completion as a record of the last run. Resets to 0% at the start of each new run. Tracks the **tagging phase** (phase 2) only — it does not move during the fetch phase, which is what the new fetch status strip above it is for.
- A **summary dialog** when all albums are done. The dialog is tabbed:
  - **Summary tab**: the same scrollable text summary as before — per-album tagged/cleared/skipped/error counts and, when romanisation ran, new/overwritten/skipped titlesort counts.
  - **Changes tab**: appears only when at least one album has tag changes, TouhouDB mismatches, or title discrepancies; omitted otherwise (the dialog then has only the Summary tab). See the Changes tab section below for full details (including the right-click / bulk title-overwrite actions on discrepancy rows).
- **Keyboard shortcuts**:
  - **Del** (when the tree has focus): removes the selected album(s) — same handler as **File → Remove Selected**. Supports multi-select (Ctrl+Click to toggle, Shift+Click for a range); all selected items are removed at once, and selecting a track row removes its whole parent album.
  - **Return / Enter**: starts a tagging run from anywhere in the tab. Guarded: if a slug cell is being edited, committing the edit takes precedence and no run starts.
  - **Esc**: cancels an in-flight run (same as clicking Cancel). Disabled when no run is active so it doesn't interfere with editing or dialogs.
- **Right-click context menu**: right-click any selected album row(s) for:
  - **Mark as unavailable / Unmark as unavailable** — flag the selected album(s) as having no page on either wiki (so they can't be wiki-tagged). The mark persists across sessions via `availability.py` and is shown as a warning-triangle icon plus a faint translucent-yellow row tint (the same tint the summary dialog's Changes tab uses for overwrites). Both actions appear when the selection is mixed; only the relevant one appears otherwise. Marking also **auto-marks the album's artist** (the parent folder) as unavailable, but only when the artist is *genuinely* absent from both wikis — i.e. it has **no** wiki-tagged album and **every** album under it is flagged missing (so it surfaces as the yellow "unavailable" slice on the Statistics tab). An artist that still has at least one tagged album stays "tagged" and instead shows a partial-coverage warning in the Statistics panel (see below). Unmarking any album clears the artist mark too. The album→theme check reuses `library_stats.classify_artist_albums()` and the Statistics scan cache. The directory key in column 0 is never altered — the warning is icon + tint only — so every caller that reads `item.text(0)` keeps working.
  - **Send to…** submenu — lists the other tabs ("Tag Edit", and "Romanise" if available); selecting a destination adds the selected albums' folders to that tab's queue and switches to it.
  
  Multi-selection works the same way as with deletion: selecting any row in an album acts on the whole album. The whole album tree restyles from the store whenever the Wiki Tagger tab is shown, so marks made on the Statistics tab (which can flag an artist's albums) appear here without re-adding the rows.

#### Summary dialog — Changes tab

The Changes tab is built by `_build_changes_tree()` in `gui.py` and provides a per-track diff view of everything `process_album()` would write, overwrite, clear, or delete. It is populated from the `tag_changes` list in each album's result dict (see `process_album()` return dict below), so it reflects the actual decision made by every tag-write path in the tagger — not a re-evaluation after the fact.

**Structure**: the tab contains a filter bar at the top and a scrollable `QTreeWidget` below it.

The tree is three levels deep:

- **Album (level 0, bold)**: labelled with the directory's basename; falls back to the wiki slug if `music_dir` is empty. Only albums that have at least one change or TouhouDB mismatch appear.
- **Track (level 1)**: the filename of the audio file. Only tracks with at least one change appear.
- **Tag change (level 2)**: one row per changed tag, with three columns — **Tag** (the tag name, e.g. `grouping`), **Old value** (the value that was there before, or `(none)` if the tag was absent), **New value** (the value that would be written, or `(cleared)` if the tag is being deleted). Rows where the old value existed — i.e. overwrites — are tinted with a soft translucent yellow background (`rgba(255, 220, 50, 55)`) so they stand out from new additions at a glance.

TouhouDB mismatches (date, catalog number, missing members) appear as level-1 rows directly under the album item, prefixed with `⚠`. Date and catalog mismatch rows show `wiki: VALUE` in the Old column and `TouhouDB: VALUE` in the New column; missing-member rows list the names in the Old column. **Date and catalog rows are actionable** (album-level): right-click → *Set selected from TouhouDB* writes that value as `date`/`year` or `catalognumber` to *every* file in the album. Missing-member rows stay notify-only.

**Title discrepancies** (from `title_discrepancies`) also appear as `⚠` level-1 rows (`Title differs` / `Wrong track #` / `Missing locally` / `No wiki/TDB match`, with the local value in the Old column and `wiki:`/`TouhouDB:` values in the New column). Rows whose discrepancy has a local file and a differing wiki/TouhouDB title are **actionable** (per-track). All actionable rows — title, date, and catalog — share one mechanism: right-click → *Set selected from Wiki* / *Set selected from TouhouDB* (Ctrl/Shift multi-select spans mixed tag kinds), or use the per-source split buttons at the bottom (a menu of granular per-tag bulk sets plus a bold-red, confirmation-gated *Set all mismatches* entry). Applying writes each row's tag via `tag_io._set_tag` (title rows also re-romanise `titlesort` via `japanese_romanizer.romanize_file(force_titlesort=True)`; date rows also derive `year`), skips rows already matching the chosen source, marks each applied row ✓, and reports rows/files written — see "Tag overwrite from the Changes tab" and "Track-discrepancy flagging and the severe-mismatch pause" for the full behaviour. These writes happen for real even after a dry-run pass.

**Filter bar**: a row of checkboxes at the top of the tab, one per tag type that actually appears anywhere in the results (e.g. `grouping`, `titlesort`, `albumartist`, `arranger`, …). The set is built from the union of all `tag_changes` across all album results; only tag types that were actually touched appear as checkboxes. By default all checkboxes are unchecked and all changes are shown. When one or more checkboxes are active, only tag rows matching those types are visible; track items with no visible children are hidden, and album items with no visible track children are hidden too. TouhouDB mismatch rows are always visible regardless of the active filters. Toggling any checkbox immediately re-evaluates visibility without rebuilding the tree.

An **"⚠ Only discrepancies"** checkbox on its **own row below** the per-tag toggles (which row is already crowded; shown only when there's at least one ⚠ row anywhere) isolates the mismatch rows: when checked it hides every normal track/tag-change row across all albums, leaving only the ⚠ rows (title discrepancies + TouhouDB date/catalog/missing-member flags) and the albums that carry them — so the things needing attention (and the title-overwrite targets) are easy to find in a multi-album batch without scrolling. It disables the per-tag checkboxes while active (they're moot) and shares the same `_apply_filters` pass.

The Changes tab is produced unconditionally whenever the dry-run and non-dry-run paths record changes — it is not restricted to dry-run mode. In a live (non-dry-run) run it reflects what was just written; in a dry-run it shows what would have been written. This makes it useful for reviewing a completed live run as well as previewing a dry run.

#### Romanise tab

Only shown when `japanese_romanizer.py` is present and MeCab/UniDic are installed. Allows romanising `titlesort` tags for any Japanese album — including albums not on either Touhou wiki, and non-Touhou Japanese albums. Uses a flat two-column table (Directory, Album) rather than the expandable tree of the Wiki Tagger tab, since there's no slug or per-track grouping to display. Provides:

- **Drag & drop** and **File → Add Folders… (Ctrl+O)** — same artist-container auto-expansion behaviour as the Wiki Tagger tab: dropping an `[Artist]` folder adds its album subfolders rather than the container itself.
- **File → Refresh (F5)** (`_refresh_queue()`): drops rows whose folder no longer exists on disk and re-guesses each remaining row's album name from the folder's current tags.
- **Settings sidebar** with:
  - **Auto-clear done**: remove successfully processed albums from the queue.
  - **Dry run**: show what would be written without modifying files.
  - **Force overwrite existing titlesort**: defaults to off; replace existing `titlesort` tags.
- **Romanise All** button: processes all queued folders and logs per-track results.
- **Cancel** button (and **Esc** shortcut): same graceful cancellation behaviour as the Wiki Tagger tab — finishes the current album before stopping.
- A **progress bar** between the Romanise All/Cancel buttons and the log, behaving identically to the one on the Wiki Tagger tab.
- Summary dialog with new/overwritten/skipped/no-title/error counts.
- **Keyboard shortcuts**:
  - **Del** (when the table has focus): removes selected row(s) — same handler as **File → Remove Selected**. Supports the same multi-select gestures as the Wiki Tagger tab.
  - **Return / Enter**: starts romanisation from anywhere in the tab.
  - **Esc**: cancels an in-flight run; disabled when idle.

If `japanese_romanizer.py` is not alongside the script, or if MeCab/UniDic are missing, the tab doesn't appear. The status bar shows a hint explaining which condition isn't met and how to fix it.

#### Tag Edit tab

Always shown. Provides a table-based editor for making quick manual corrections to the tags fetched by the Wiki Tagger, without needing to open an external tool. Editing is directly to disk — there is no intermediate "pending external-editor" state. Provides:

- **Drag & drop** and **File → Add Folders… (Ctrl+O)** — same artist-container auto-expansion as the other tabs.
- **"Send to…"** from the Wiki Tagger tab's right-click context menu (see above) — the most common entry path after a tagging run.
- A **tag table** with one row per track plus tinted, non-editable **album header rows** that span the full width. Album headers display the album name and folder path; they are visually distinct (bold, tinted) so album boundaries are easy to see when scrolling through a long list of albums. The columns are:
  - **Track** (non-editable): the track label in the same `NN. Title` / `D-NN. Title` format as the Wiki Tagger tree view. Stores the file path internally.
  - One editable column per tag field, in this order: **Grouping, Title Sort, Album, Album Artist, Artist, Artist Sort, Arranger, Vocalist, Lyricist, Catalog No., Date, Year**. Column widths are user-resizable. Values are loaded once via `read_all_tags()` (a single `mutagen.File` open per track reads all twelve fields).
- **Column visibility toggles** in the settings sidebar — one checkbox per tag field. Hiding unused columns (e.g. "Artist Sort", "Lyricist") narrows the table to the fields you actually care about. Toggling a checkbox calls `setColumnHidden()` on the table; hidden columns are not edited or saved.
- **Batch editing**: select multiple rows (Ctrl+Click, Shift+Click, or Ctrl+A), then edit any cell in the selection. When you finish editing that cell, the new value is automatically propagated to the same column in all other selected rows. This applies to any mix of tracks from any album(s). Typical use case: the fetched release date is wrong across an entire album — select all its rows with Ctrl+A, edit one Date cell, and all are updated.
- **Dirty tracking**: every cell edit is recorded as `(filepath, tag_name)`. The status label at the bottom of the main pane shows the running count of unsaved changes ("N unsaved changes."). Edits that revert a field back to its original value are removed from the dirty set automatically.
- **Save Changes** button: iterates over the dirty set and writes each changed value to disk using `_set_tag()`. Clearing a field (leaving the cell empty) calls `_delete_tag()` to remove the tag entirely. After saving, the dirty set is cleared and the status label resets to "No changes." A confirmation popup reports how many changes were saved and lists any write errors.
- **File → Remove Selected**: removes the entire album block for any selected row — selecting a track row walks up to its album header and removes the header plus every track row under it, cleaning the removed files out of the dirty set.
- **File → Clear All**: prompts for confirmation if there are unsaved changes before clearing the table.
- **File → Refresh (F5)** (`_refresh_queue()`): rebuilds the whole table from the current on-disk tags — folders that no longer exist (or no longer contain audio) drop out. Because every row is re-read from disk, unsaved edits would be lost, so it asks for confirmation first when there are dirty cells.
- **Unsaved-changes warning on exit**: `TaggerWindow.closeEvent` checks `TagEditTab.has_unsaved_changes()` before allowing the window to close — regardless of which tab is currently active. The dialog offers "Close without saving" (OK) or "Cancel" to return.

#### Statistics tab

Always shown. Gives a collection-wide view of how much of the library has been grouping-tagged — there is otherwise no way to see overall tagging progress across a large collection. Implemented in its own module, `library_stats.py` (self-contained; imports PyQt5 at module top and is lazy-imported by `gui.py` inside `gui_main()` so the CLI path never loads Qt). It expects a music library laid out as `<root>/<artist>/<album>/<tracks>` (for example, `<library>/[Circle Name]/<album>/…`), where the "artist" is the folder name one level below the root. Provides:

- A **library-root field + Browse… button + Scan button**. On first run the root uses `TOUHOU_TAGGER_LIBRARY_ROOT` when set, otherwise the operating system's standard Music folder. The selected root is **persisted** to the platform config directory's `stats.json` so it survives restarts. A **Cancel** button (and a progress bar showing `N / M artists`) appears during a scan.
- A **scan** that walks every artist → album → track, reads each track's `grouping` tag, splits grouping on `;`, and matches each piece against the set of known English theme names (the **values** of `touhou_theme_mapping.json`'s `mapping`, loaded via `load_known_themes()`). An artist is classified **tagged** if at least one of their tracks carries a known theme, **untagged** otherwise. Every matching grouping piece also increments a per-theme song counter (a track tagged `"A; B"` counts once toward each of `A` and `B`). Every value of a track's multi-value `genre` tag likewise increments a per-genre song counter (`genre_counts` — read in the same mutagen open via `read_stats_fields()`'s `genres` list; counted case-insensitively with the most common spelling as the display form, ties broken alphabetically so `Rock` beats `rock`). The genre counts are stored **unfiltered** — the genre-popularity view drops `_EXCLUDED_GENRES` at display time, so extending that set never requires a re-scan. The scan runs off the GUI thread in `_StatsScanWorker` with progress and cancellation, mirroring `_WikiWorker`. The mtime-keyed per-file cache stores `[mtime_ns, grouping, present_list, cjk_list, title, album, albumartist, length, genres]` (title/album/albumartist/length feed the per-theme Information window, `genres` the genre-popularity chart); any entry of a different length is treated as a miss and re-read, so the first scan after an upgrade re-reads every file and later scans are fast again.
- A **clickable, colour-coded pie chart** (`_PieChartWidget`, custom-painted like `_FetchStatusBar`) with **three** slices — tagged in the palette highlight colour, untagged in the same red `_FetchStatusBar` uses, and **unavailable in yellow** (`#f1c40f`) — with a legend showing counts and percentages. Clicking a slice lists those artists in an inline panel beside the chart (not a modal dialog). The slices are mutually exclusive and **unavailable takes precedence**: an artist marked unavailable (in `availability.py`) is carved out of whichever theme-based bucket it would otherwise land in, so "untagged" keeps its meaning of "not tagged *yet*" while "unavailable" means "no wiki page exists to tag from". The scan itself (`scan_library()`) still only knows tagged/untagged; the three-way split is recomputed at display time by `_recompute()` from the live availability store, so it stays correct as marks change without re-scanning (and `_recompute()` also re-runs on `showEvent` to pick up marks made in the Wiki Tagger tab).
- **Partial-coverage warning in the tagged list.** A tagged artist that has some — but not all — of its albums flagged unavailable is shown in the **tagged** panel with a leading ⚠ warning sign. Hovering it shows a tooltip naming up to **3** of its missing albums; if more are flagged, the list is truncated with " and X more" (e.g. seven missing → first three then "and 4 more"). The missing-album basenames are grouped from the availability store by parent folder in `_recompute()` (no disk I/O) into `_missing_by_artist`, and the prefix/tooltip are applied in `_apply_filter()` only for the tagged panel. This replaces the previous full-name hover tooltip (names already wrap fully in the panel, so plain rows now carry no tooltip).
- **Drag artists/albums out of the app.** The detail panel tree (`_WrapTreeWidget`) has `setDragEnabled(True)` + `DragDropMode.DragOnly`, and overrides `mimeData()` to build the payload from the selected rows' `Qt.UserRole` folder paths: a `text/uri-list` of `file://` URLs (what terminals and file managers consume to insert the local paths) plus a shell-quoted, space-separated `text/plain` fallback. So a selection of artists (or an expanded artist's albums) can be dragged straight onto a terminal to paste their folder paths, or onto a file manager. Note/placeholder/theme rows carry no path and are skipped; the tree accepts no drops (`DragOnly`).
- **Marking artists unavailable from the panel.** When the inline panel is showing artists, right-click a selection for **Mark as unavailable / Unmark as unavailable** (alongside the existing Open / Send to…). Marking flags the artist *and* every album under it that doesn't already carry a known theme (so those albums show as unavailable in the Wiki Tagger tab); albums that do have a theme are left untouched. This is an explicit override, so it moves even a partly-tagged artist into the yellow slice. Unmarking clears the artist and all its albums. The per-album classification uses `classify_artist_albums()` and reuses the scan cache. The Wiki Tagger tab's per-album marking only *auto*-marks the artist when **all** its albums are missing and none are tagged — the two share `availability.py`'s in-process store, so a mark in one tab is immediately reflected in the other.
- **Expandable untagged-album branch (tagged artists).** The right-hand detail panel is a single-column tree (`_WrapTreeWidget`, the tree analogue of `_WrapListWidget` — same `_WrapTextDelegate` and viewport-width row sizing, but child rows reduce the wrapped width by their indentation). In the **tagged** panel only, every artist row carries a native expansion arrow; expanding it lists that artist's albums that have **no `grouping` theme** (the same predicate the unavailable-marking uses, so the membership is consistent). This surfaces off-wiki or never-matched albums the user may have forgotten to mark unavailable (or tagged before that feature existed).
  - **Classification happens during the scan, not on expand.** Because `scan_library()` already opens every file for its tags, it computes the per-album split in the same pass at no extra disk cost and returns it as `untagged_albums` (`artist name → [album path relative to root, …]`, only artists with ≥ 1 such album; the key's mere presence signals the whole library was classified). This is persisted in `stats_result.json` and reloaded on launch, so the data survives restarts without re-scanning. `_apply_result()` populates `_artist_untagged_albums` (keyed by normalised artist path → `[(basename, abs_path), …]`) wholesale from it and sets `_albums_classified`. Expanding an artist then reads straight from memory — **no per-artist disk walk**. The previous behaviour (lazy `classify_artist_albums()` on first expand, under a busy cursor) survives only as a **fallback for an old persisted result** that predates the `untagged_albums` key (`_albums_classified` is False, so a classified-but-absent artist isn't assumed empty); a fresh scan upgrades it. A lightweight placeholder child still gives the arrow before first expand so the collapsed tree stays cheap for a large library; rows are materialised on expand.
  - `_ROLE_LOADED`/`_ROLE_KIND` (data roles alongside `Qt.UserRole`, which holds the folder path) distinguish artist/album/note/placeholder rows and track whether a branch is materialised. Expansion survives filter/sort/mark rebuilds via `_expanded_artists` (normalised paths, kept in sync by the `itemExpanded`/`itemCollapsed` slots). Albums already marked unavailable are filtered out of the branch at display time (they've been handled — `availability` marks don't change tags, so they're never baked into the cached list), so what remains is the actionable "did I forget this one?" set; when nothing is left, a non-selectable italic "(no untagged albums)" note is shown.
  - **Album child rows get their own right-click menu** (`_show_album_context_menu`): Open / **Mark album(s) as unavailable** (album-scoped — calls `availability.set_albums`, does *not* touch the artist mark; the marked album then drops out of the branch and the artist gains the partial-coverage ⚠) / Send to…. `_show_list_context_menu` routes a pure album-row selection here and otherwise falls through to the existing artist menu (mixed selections favour the artist scope; note/placeholder/theme rows have no path and do nothing).
- A **"Popularity charts" drop-down** (a `QToolButton` with an `InstantPopup` menu, replacing the former "Theme popularity" toggle button) offering three entries: **Theme popularity**, **Genre popularity**, and — below a separator — **Artist details**, which returns to the pie + the artist list that was showing before (the prior slice is remembered in `_prev_artist_mode`; if none was open it returns to the placeholder; implemented by `_exit_charts_view()`, shared by both chart views). The Artist details entry is enabled only while a chart is actually showing, re-evaluated on the menu's `aboutToShow`. **Theme popularity** (`_show_themes()`) fills the inline panel with the themes that actually appear, each with its song count, sorted most-popular first (only themes used ≥ 1 are listed — no zero-count padding; grouping values not in the JSON are ignored), and **swaps the pie chart out for a horizontal bar chart** (`_ThemeBarChart`) on the left. The right-hand list keeps its own filter/sort. The pie and chart share the left pane via a `QStackedWidget`; `_show_artists()` selects the pie and `_show_themes()`/`_show_genres()` the chart, so a re-scan that re-syncs the open panel keeps the correct left view.
- **Genre popularity** (`_show_genres()`) is the themes view's twin for the multi-value `genre` tags: the same bar chart + count list, fed from the scan's `genre_counts`. The release-type labels in `_EXCLUDED_GENRES` (`Game`, `Indie`, compared casefolded) are **dropped at display time** — every album in the collection is a doujin game arrange, so they describe the release rather than a musical style and would dwarf the real genres; extend the set (it's a module constant) and the chart updates on next view, no re-scan needed. Genre rows carry `_ROLE_KIND` `"genre"` (not `"theme"`) and no `_ROLE_THEME`, so the per-theme "Information" context menu never applies to them (genres have no folder and no cached details — right-clicking one shows nothing). A persisted result predating the feature has no `genre_counts`; the view then shows an empty chart and a "re-scan to compute" header instead of pretending the library has no genres.
- The **theme bar chart** (`_ThemeBarChart`, custom-painted like `_PieChartWidget`; the genre view reuses the same widget instance — only the data and the empty-state text differ, both supplied via `setData()`) draws one horizontal bar per theme, **tallest on top**, in the palette highlight colour, inside a `QScrollArea` (it sizes its own height to `TOP_PAD + n·ROW_H + BOTTOM_PAD` so all bars scroll vertically; horizontal scrollbar off). Each bar's `theme (count)` label is drawn **inside** the bar (light highlighted-text) — **elided with an ellipsis when it overflows, with a hover tooltip giving the full theme name** — until the bar is too short to hold even ~`_MIN_INSIDE_CHARS` (8) characters, at which point the full name is drawn just past the bar's end on the background instead (still elided to the plot width, with a tooltip, if even that overflows). The per-row truncated-name map (`_row_tooltips`) is rebuilt each paint and consulted by an overridden `event()` on `QEvent.ToolTip`, with `_row_at(y)` mapping the cursor to a row (scroll-aware, since the position is in the chart's own coordinates). Faint dotted **vertical gridlines with value labels** along the top mark round song-count intervals chosen by `_nice_axis_max(max_count)` — a 1/2/2.5/5×10ⁿ step giving ~4–6 gridlines, so the axis re-scales as the library grows (e.g. a top theme near 2000 songs → ticks at 500/1000/1500/2000; near 4300 → ticks every 1000). The grid/label colours are a **faded `WindowText`** (alpha 60 / 180), not `QPalette.Mid`, so they stay visible in dark themes (where `Mid` sits almost on the window background). The chart always sorts most-popular-first independently of the right-hand list's sort.
- **Per-theme "Information" window.** Right-clicking a theme row in the Theme popularity list offers **Information**, which opens a scrollable modal (`_ThemeInfoDialog`) built entirely from the scan result's `theme_details` key — no disk I/O, so it opens instantly. Stacked top to bottom: the top-5 **longest/shortest solo remixes** (tracks whose `grouping` names exactly that one theme — a second piece, known or not, makes it multi), the top-5 **longest/shortest multi-theme remixes** featuring the theme, each section switchable between longest and shortest via a button (`_ThemeLengthSection`); and the **circle with the most remixes** of the theme (solo + multi combined, ties broken alphabetically) as a foldable tree — circle → albums → songs with durations — whose height tracks its expanded rows so the outer scroll area does all the scrolling. `theme_details` is computed during the scan by `_build_theme_details()` (each track's title/circle/album/duration is captured in the same mutagen open the scan already does; the circle is the `albumartist` tag falling back to the artist folder name, the album the `album` tag falling back to the folder basename, the title falling back to the filename stem) and persisted in `stats_result.json` — only the top-5 lists and the winning circle's song list are kept, so the file stays small. Tracks whose duration can't be read are excluded from the length lists but still count toward the circle totals. A persisted result predating the feature has no `theme_details`; the action then prompts a re-scan (mirroring the Missing-tags view). The raw theme name rides on the row in a dedicated `_ROLE_THEME` data role so the menu never parses it back out of the `"count — theme"` display text.
- A **filter box** above the panel that live-filters the currently shown list (artists or themes) case-insensitively.

**Scan caching (mtime-based).** A full scan of a multi-thousand-artist library on a network mount is I/O-bound and can take ~an hour, so re-scans are accelerated by the platform config directory's `stats_cache.json`, keyed by absolute path (see the scan bullet above for the current record shape). On each scan the tree is still walked and every file `os.stat`-ed, but the (far more expensive) mutagen open is skipped for any file whose `st_mtime_ns` is unchanged since last time — so after tagging one artist, only that artist's rewritten files are re-read. The cache is loaded and saved by the worker (off the GUI thread); entries for files no longer on disk are pruned, but **only after a fully-completed scan** (a cancelled run leaves unvisited entries intact). The cache is updated even on a cancelled scan since each read it did is still valid. The first scan after enabling the cache is still full-speed (every file is a miss); subsequent scans are fast.

**Result persistence.** The aggregated result of the last completed scan (artist lists + theme counts + totals) is saved to the platform config directory's `stats_result.json` and reloaded on launch, so the tab shows the previous scan's pie chart and lists immediately — with no scan — and a "from last scan" note in the summary line. A fresh Scan overwrites it.

**Inline panel rendering.** The artist/theme lists use `_WrapListWidget`, a `QListWidget` subclass that word-wraps long names instead of eliding them with an ellipsis. Earlier attempts that relied on `QListWidget.setWordWrap(True)` alone (or on a delegate's `sizeHint`) failed in practice: the height a row was sized for and the width its text was painted at could disagree, so overflow was clipped and ellipsised (e.g. `896 — Necrofantasia` collapsed to `896 — …`). `_WrapListWidget` instead computes each row's height from the **live viewport width** (recomputed on `resizeEvent` and after every repopulate via `relayout_rows()`), and a companion `_WrapTextDelegate` paints the text word-wrapped into that same rect — so sizing and painting always use one width and the full name shows in any Qt style. Each item also gets a tooltip with its full text as a belt-and-suspenders fallback.

### Two-phase batch processing: fetch-then-tag

Wiki tagging runs (CLI multi-album invocations and every GUI "Tag All" run) are driven by `process_albums()`, which processes the whole batch in two strict phases instead of interleaving fetch-and-tag per album:

1. **Phase 0 — cookie pre-flight.** `validate_thwiki_cookie()` is called once, before anything else. A missing or rejected THBWiki cookie raises `ThwikiCookieError` immediately, before a single album is touched.
2. **Phase 1 — fetch every album.** Each album pair is passed to `fetch_album_plan()` in turn, producing an `AlbumPlan` (network/data only — no file writes). The plans accumulate in memory. An `album_pairs` item may also be a 3-tuple `(wiki_album, music_dir, slug_is_auto)` — the GUI sends `slug_is_auto=True` for slugs still matching their auto-suggestion, enabling the capitalization-variant retries (see "How it works" step 2); plain 2-tuples (the CLI's hand-typed slugs) never retry.
3. **Phase 2 — tag every album.** Each cached `AlbumPlan` is passed to `tag_album_from_plan()`, which does the local file scan, matching, and tag writing for that album.

This replaces the previous design, where `process_album()` fetched and tagged one album at a time, interleaved. The motivation is the THBWiki cookie: it typically expires within 30–60 minutes, and most artists have at least one album that needs THBWiki even when most others are on the English wiki. Fetching everything up front means the cookie only has to survive the (usually short) network phase, not the whole run including however long local file I/O takes across every album; and a cookie that goes stale partway through fetching aborts the **whole batch** before any file has been written, rather than leaving an arbitrary subset of albums tagged and the rest not.

`process_albums()` accepts optional callbacks used by the GUI to drive live UI updates without polling: `on_result(result_dict)`, called after each album finishes **tagging** (phase 2) — drives the existing progress bar and per-album log; `on_plan(index, plan)`, called after each album finishes **fetching** (phase 1), with `index` 0-based and `plan.error is None` indicating success — drives the new fetch status strip (see "Wiki Tagger tab" and "GUI threading model" below); and `on_confirm(context)`, called (phase 2) when an album trips the severe-mismatch gate — returns `"skip"`/`"continue"`/`"cancel"` (see "Track-discrepancy flagging and the severe-mismatch pause"). A `cancel_requested()` callable is polled between albums in both phases; cancelling during phase 1 means nothing at all gets tagged. A `"cancel"` from `on_confirm` (its result's `cancel_batch`) likewise stops the batch.

### How it works (wiki tagging)

These steps describe what happens to a single album; under `process_albums()` (used by both the CLI and the GUI), steps 1–5 run for **every** album during phase 1 before step 6 onward runs for **any** album in phase 2 — see "Two-phase batch processing" above.

1. **Tries the English Touhou Wiki** first: fetches the album page via Playwright, searches for any descendant element with a `title=` attribute (Strategy 1 — the old tooltip path; kept in case the wiki restores this behaviour). If none is found, falls back to the visible text of each `original title:` list item (Strategy 2), which preserves the Japanese/mixed name for translation in step 3.
2. **Falls back to THBWiki** automatically if the English wiki returns no tracks (HTTP error, page not found, or empty parse): queries the asktrack API via `curl` subprocess, gets `ogmusicname`, `arrange`, `vocal`, and `lyric` values (all in Japanese/canonical form).

   **Capitalization-variant retries (auto-suggested slugs only).** MediaWiki page titles are case-sensitive past the first character, and local album names often disagree with the wiki's capitalization. When steps 1–2 both come up empty *and* the slug was auto-suggested (never hand-typed or hand-edited — the GUI passes a `slug_is_auto` flag per job by comparing the slug cell against the auto-guess stashed in `Qt.UserRole`; CLI slugs are always manual and never retry), `fetch_album_plan(..., retry_case_variants=True)` re-runs the full English-wiki→THBWiki pass with the re-capitalised slugs from `_slug_case_variants()`: candidates are Title_Case, UPPERCASE, lowercase — in that order, minus whichever form the original already is (so `A_Certain_Music_Album` retries `A_CERTAIN_MUSIC_ALBUM` then `a_certain_music_album`; an all-caps original retries Title_Case then lowercase — two retries for any pure-case original). A **mixed-case** original like `Skyruin_EP` differs from all three canonical forms, so it gets **three** retries; an earlier cap at two was observed to drop exactly the variant that matched (`skyruin_ep`), so the list is deliberately uncapped. Title-casing capitalizes each Latin letter-run manually rather than `str.title()` (which would mangle apostrophes: `Owen's` → `Owen'S`). A slug with no cased Latin characters (fully-CJK) has no variants. On a hit, the matched variant becomes the plan's `wiki_album`, so the THBWiki page fetch, TouhouDB verification, and all summaries use it. Log markers: `↻ No match for '…' — retrying with capitalization variant i/N: '…'` and `✓ Matched on <source> as '…'`.
3. **Fetches the THBWiki album page HTML** once — regardless of which source supplied the original titles — and uses it for four purposes:
   - **HTML cross-check for original titles:** fills empty `ogmusicname`, and on THBWiki-primary runs additionally corrects wrong values and clears spurious ones — see "Known data gap" above for the exact three-case breakdown. This is the fix for variant tracks (e.g. "Type C" rearranges, off-vocal editions) whose `ogmusicname` is absent from the API semantic store but whose themes are visible on the rendered page.
   - **Album metadata:** the info box is scraped for catalog number, release date, album title, producer/album artist, and genre(s) (see THBWiki album info box parsing above; genres are translated to English via `translate_genre()` right here in the fetch phase).
   - **Staff name mapping:** the Staff section's stafflist tables are parsed to build a Japanese → romanized name map (e.g. `こたろう` → `Kota-rocK`), used to romanize credit names before writing them to tags.
   - **Per-track credit cross-check:** the identical fill/correct split as above, per `arrange`/`vocal`/`lyric` field — see "Known data gap" above.

   The HTML page is fetched via the mandatory cookie-reuse path; see "THBWiki page HTML fetch — current approach" above for the cookie/`ThwikiCookieError` mechanics. A non-cookie fetch failure (e.g. a transient transport error) skips this step for that album only — the four uses above simply aren't available for it, but the titles from step 1 or 2 are still used.
4. **Inherits variant titles:** For tracks with empty `original_titles` whose title contains a known variant suffix — parenthesized like "(instrumental)", "(off vocal)", or "(separate)", bracketed, full-width, or dash-delimited like "- Piano Ver. -", "- Instrumental -", or "-separate-" (space after the leading dash is optional) — strips the suffix to get a base title and groups tracks that share the same base. If any track in a group has original titles, they are copied to all other tracks in the group that lack them. This is bidirectional: whichever variant has the data donates to those that don't, working around gaps in THBWiki's semantic store.
5. **Translates** all original theme names to English using the theme mapping file, regardless of which source was used. Titles already in English (e.g. from a working tooltip) won't match any mapping key and are left unchanged. Warns and uses Japanese names as-is if the mapping file is missing.
6. **Scans** the local music directory for supported files (`.mp3`, `.flac`, `.ogg`, `.m4a`, `.opus`). If the directory contains disc subdirectories (prefix disc, disk, or cd, case-insensitive, followed by a number and optional trailing text — e.g. Disc 1, DISC 01, CD1, Disk1(第一部), CD 02 - Bonus), each subdirectory is scanned separately and files are assigned the corresponding disc number. Otherwise the directory is treated as a flat single-disc album (disc 1).
7. **Matches** local files to wiki tracks: for multi-disc albums, by `(disc, track number)` pair; for single-disc albums, by track number alone. Falls back to exact normalized title match in either case. Track numbers are read from tags first, then from leading digits in the filename.
8. **Writes tags** per matched file (and records each write in `tag_changes` for the summary dialog's Changes tab):
   - `grouping` (original theme names) — written for matched tracks with original titles. For matched tracks identified as original compositions, any existing `grouping` tag is **deleted** if one is present (e.g. left over from a previous incorrect tagging run); the log shows `[CLEAR]` for these. Tracks with no wiki match are left untouched.
   - `catalognumber`, `date`, `year` — written to every file if found on THBWiki and not already present. For multi-disc box sets with a slash-shorthand catalog ID (e.g. `ABCD-12345/6`), each file receives the catno for its disc.
   - `genre` — when the info box had a Genre row, the wiki genres are **merged** (unioned + deduped) with the file's existing genres rather than skipped or overwritten (via `_merge_genres` — see the merge policy under Chosen Tag Fields). Multi-value (via `set_genres()`): one Vorbis field / TCON text / `©gen` value per genre; the write is skipped when the merge adds nothing new; the Changes tab shows the `; `-joined form.
   - `album` — written to every file. Always overwrites the local value when it differs from THBWiki; skipped only when the values match exactly.
   - `albumartist` — written with the original (CJK) circle name(s) from THBWiki, joined with `" & "`. If no fresh fetch is available, an existing CJK `albumartist` is preserved. An existing Latin `albumartist` (from an older romanise-in-place run) is overwritten with the CJK form. `albumartistsort` — written with the romanised form (TouhouDB official > Staff map); an existing Latin `albumartistsort` is respected and never overwritten. The sort field is only written when it differs from `albumartist`.
   - `artist`, `artistsort` — written per track when **Verify with TouhouDB** is enabled. `artist` carries the original-language arranger and vocalist names; `artistsort` the romanized form (TouhouDB-first). Both are skip-if-present. `artistsort` additionally requires the fully-romanized join to be Latin (CJK guard). When **Add missing TouhouDB members** is on, TouhouDB per-song credits are merged in first.
   - `arranger`, `vocalist`, `lyricist` — written per track if the API or HTML supplied credits and the file doesn't already have the tag. Credit names are romanized via the staff name mapping where available. Multiple names are joined with `; `.
   - `titlesort` — if romanisation is enabled and the romaniser is ready, the file's `title` tag is romanised into `titlesort` in the same pass.

   Log prefixes: `[META]` for album-level metadata writes (new value); `[META-OVR]` for album-level overwrites (replacing an existing different value, with the old value shown on a continuation line); `[CREDIT]` for per-track credit writes; `[ARTIST]` for `artist`/`artistsort` writes; `[ARTIST-ERR]` for errors during artist tag resolution; `[TAG]` / `[ROMANIZE]` / `[SKIP-RM]` for original-title and titlesort operations; `[CLEAR]` when a stale `grouping` tag is removed from an original composition.

### Auto-romanisation behaviour during wiki tagging

When `japanese_romanizer.py` is available and romanisation is enabled (the default):

- The romaniser reads the file's **existing `title` tag** as input — not the wiki track title. This keeps `titlesort` consistent with whatever the player displays.
- If the file has no `title` tag, the wiki track's title is used as a fallback so tracks that haven't been title-tagged yet still get a `titlesort`.
- Only tracks whose title contains hiragana, katakana, or kanji are romanised. Tracks with purely Latin titles log `[SKIP-RM]` and are skipped.
- Existing `titlesort` tags are **not overwritten** by default. The log shows both the current value and what would have been written; use `--force-titlesort` (CLI) or "Force overwrite" (GUI) to replace them.
- Romanisation runs for every track in the album — not just the ones that got a `grouping` write. A track with no wiki match or an original composition still gets a `titlesort` if its title is Japanese.

Typical per-file log output:

```
  [TAG]       01 - 千年幻想郷.flac
              grouping = Gensokyo Millennium ~ History of the Moon
  [ROMANIZE]  01 - 千年幻想郷.flac
              titlesort = Sennen Gensoukyou ~ History of the Moon

  [TAG]       02 - Kiss & Crazy.flac
              grouping = Gensokyo Millennium ~ History of the Moon
  [SKIP-RM]   02 - Kiss & Crazy.flac  (no Japanese)

  [SKIP]      03 - Interlude.flac  (original composition)
  [SKIP-EX]   03 - Interlude.flac  (titlesort already set; not forcing)
              current   = Interlude
              would set = Interlude

  [CLEAR]     04 - Original Song.flac  (original composition)
              removed = Some Wrong Grouping From A Previous Run
```

### Supported formats and tag fields

| Format | `grouping` | `titlesort` | `catalognumber` | `date` | `year` | `album` | `albumartist` | `artist` | `artistsort` | `arranger` | `vocalist` | `lyricist` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `.mp3` | `TIT1` | `TSOT` | `TXXX:CATALOGNUMBER` | `TDRC` | `TXXX:YEAR` | `TALB` | `TPE2` | `TPE1` | `TSOP` | `TXXX:ARRANGER` | `TXXX:VOCALIST` | `TXXX:LYRICIST` |
| `.flac` | `grouping` | `titlesort` | `catalognumber` | `date` | `year` | `album` | `albumartist` | `artist` | `artistsort` | `arranger` | `vocalist` | `lyricist` |
| `.ogg` | `grouping` | `titlesort` | `catalognumber` | `date` | `year` | `album` | `albumartist` | `artist` | `artistsort` | `arranger` | `vocalist` | `lyricist` |
| `.opus` | `grouping` | `titlesort` | `catalognumber` | `date` | `year` | `album` | `albumartist` | `artist` | `artistsort` | `arranger` | `vocalist` | `lyricist` |
| `.m4a` | `----:com.apple.iTunes:GROUPING` | `sonm` | `----:com.apple.iTunes:CATALOGNUMBER` | `©day` | `----:com.apple.iTunes:YEAR` | `©alb` | `aART` | `©ART` | `soar` | `----:com.apple.iTunes:ARRANGER` | `----:com.apple.iTunes:VOCALIST` | `----:com.apple.iTunes:LYRICIST` |

`albumartistsort` (`TSO2` / `soaa` / Vorbis `albumartistsort`) is written alongside `albumartist` during the album-artist policy step; see the write policy above. `genre` (`TCON` / `©gen` / Vorbis `genre`) is written during the album-metadata step as a multi-value field — see the `genre` bullet in Chosen Tag Fields above. `grouping` and `titlesort` are written during the standard wiki tagging pass. `artist` and `artistsort` are written only when TouhouDB verification is enabled. All other tags are sourced from THBWiki; their individual write policies are described in the Chosen Tag Fields section above. `year` is derived from the first four characters of the `date` value (e.g. `"2006"` from `"2006-10-01"`).

The `grouping` read path (`read_grouping()` in `tag_io.py`) is used by the GUI tree view to display existing values when an album is added to the queue, and again after a tagging run to refresh the displayed values in place. The bulk read path (`read_all_tags()` in `tag_io.py`) is used by the Tag Edit tab to load all twelve editable fields per track in a single `mutagen.File` open.

### Local file scanning details

When scanning a local directory, track numbers are sourced as follows:

1. Read the `tracknumber` tag from the file via mutagen. Handles the common `"N/total"` format (e.g. `"3/12"`) by splitting on `/` and using only the first component.
2. If no `tracknumber` tag is present, falls back to extracting leading digits from the filename (e.g. `03 - Song Title.flac` → track 3).

Track numbers may be `None` if both sources fail. Matching falls back to exact normalised title comparison in that case.

### CLI arguments

| Argument | Description |
|---|---|
| `wiki_album music_dir [...]` | One or more pairs of: wiki page name (URL slug) followed by its music directory |
| `--dry-run` | Show what would be tagged without writing to disk (covers `grouping`, `titlesort`, metadata, and credits) |
| `--thwiki-only` | Skip the English wiki and use THBWiki directly |
| `--mapping PATH` | Path to the theme mapping JSON (default: `touhou_theme_mapping.json` next to the script) |
| `--no-romanize` | Skip romanisation for this run; only `grouping` and THBWiki metadata/credits are written |
| `--force-titlesort` | Overwrite existing `titlesort` tags; without this flag, existing values are preserved |
| `--no-metadata` | Skip fetching album metadata (catalog number, release date, year, album title, album artist) from THBWiki |
| `--no-credits` | Skip fetching per-track credits (arranger, vocalist, lyricist) from THBWiki |

When two or more album pairs are given in a single invocation, a **grand summary** is printed after all albums finish tagging (phase 2 of `process_albums()`). It lists each album with a ✓/✗ indicator, its data source, and per-album tagged/cleared/skipped/error counts; failed albums are listed separately with their error message. Aggregate totals across all albums appear at the bottom, including romanisation stats if the romaniser ran. This summary only ever covers a run that got past phase 0/1 — a missing or stale THBWiki cookie aborts the whole invocation with exit status `2` before phase 2 (or even phase 1, if the cookie expires mid-fetch) runs, so there is never a partial grand summary for a cookie failure.

### GUI threading model

The standalone GUI (in `gui.py`) runs heavy work (Playwright, curl, MeCab) off the GUI thread using two `QThread` subclasses:

- **`_WikiWorker`**: calls `process_albums()` once for the whole queued batch (not `process_album()` per album in a loop — see "Two-phase batch processing: fetch-then-tag" above). Emits `log_message(str)`, `album_done(dict)`, `fetch_progress(int, bool)`, `cookie_error(str)`, `confirm_needed(dict)`, and `all_done()`.
  - `album_done` fires once per album as phase 2 (tagging) finishes it, via the `on_result` callback passed to `process_albums()`. Its dict is the full per-album summary (the same shape `process_album()` has always returned), which includes `tag_changes` (the per-track diff list) and `music_dir`; these flow through to `_on_all_done` without any extra signal plumbing and are consumed by `_build_changes_tree()` to populate the summary dialog's Changes tab.
  - `fetch_progress` fires once per album as phase 1 (fetching) finishes it, via the `on_plan` callback: `self.fetch_progress.emit(idx, plan.error is None)`. The tab's `_on_fetch_progress` slot forwards this straight to `_FetchStatusBar.setStatus(index, ok)`, colouring that album's segment.
  - `cookie_error` fires once if `process_albums()` raises `ThwikiCookieError` — caught in a dedicated `except` clause, separate from the generic crash handler below, so a missing/stale cookie (an expected, recoverable condition) is never mistaken for a bug. The tab's `_on_cookie_error` slot shows a "THBWiki cookie required" `QMessageBox.critical` pointing back at the auth dialog; no files were tagged.
  - `confirm_needed` fires when an album trips the severe track-mismatch gate, via the `on_confirm` callback (`_request_confirm`, on the worker thread): it emits `confirm_needed(context)` and **blocks** on a `threading.Event` until the GUI thread answers. The tab's `_on_confirm_needed` slot (queued) builds and `exec_()`s the modal `_build_mismatch_dialog`, then calls `worker.resolve_confirm(decision)` which stores the decision and sets the Event. The wait loop polls `_cancel_requested` (and `request_cancel()` pre-sets a `"cancel"` result + sets the Event) so a Cancel can never deadlock the worker. See "Track-discrepancy flagging and the severe-mismatch pause".
- **`_RomanizeWorker`**: calls `japanese_romanizer.process_album_romanize()` for each directory. Same `log_message`/`album_done`/`all_done` signal set (no fetch phase, so no `fetch_progress`/`cookie_error`).

The **`_FetchStatusBar`** widget (also in `gui.py`) is a custom `QWidget` subclass, not a `QProgressBar` — segments are painted manually in `paintEvent()` so each one can be coloured independently (pending/success/failure) rather than the bar showing one uniform fill colour. `setCount(n)` resets it to `n` pending segments at the start of a run; `setStatus(index, ok)` colours one in as `fetch_progress` arrives. Clicking a segment (`mousePressEvent`) maps the click x-coordinate to a segment index and emits `segmentClicked(int)`; the tab's `_jump_to_fetch_section` slot searches the log widget's document for that index's `[fetch i/N]` marker (the same string `process_albums()` prints at the start of each phase-1 iteration) and scrolls it into view. Hovering a segment shows a tooltip and a lightened highlight via `mouseMoveEvent`/`leaveEvent`.

The **Tag Edit tab** does not use a worker thread. All I/O (loading tag values on `add_directory`, writing changes on "Save") happens synchronously on the GUI thread. Loads are fast because `read_all_tags()` opens each file once; saves iterate only over the dirty set, so only actually-changed fields are written.

**`print()` redirection:** both workers monkey-patch `builtins.print` at the start of `run()` with a local function that emits each call's text as a `log_message` signal. This routes all of `process_albums()`'s `print()` output — including the `[fetch i/N]`/`[tag i/N]` phase markers and phase-boundary banners — to the GUI log pane without any changes to the shared code. `builtins.print` is restored in the `finally` block, so CLI usage is never affected.

**Cancellation:** each worker stores a `_cancel_requested` flag (bare `bool`). The GUI thread sets it by calling `worker.request_cancel()`. The worker samples it between albums (via the `cancel_requested` callable passed to `process_albums()`); the GIL makes the read/write atomic at these well-defined boundaries, so no lock is needed. Cancelling during phase 1 (fetching) means the batch returns with nothing tagged at all.

**Crash handling:** `_WikiWorker.run()` wraps the `process_albums()` call in nested `try/except` blocks: `ThwikiCookieError` is caught first and routed to `cookie_error` (see above); any other `Exception` is treated as a genuine crash, logged to the debug log file, and surfaced as a message in the GUI log pane. The outer `finally` block always emits `all_done` so the GUI re-enables its buttons regardless of how the run ended — cookie error, crash, cancellation, or a clean finish.

The standalone script uses `QThread` because it is itself the Qt application; the workers dispatch results back to the Qt main thread through Qt signals.

---

## Debug Logging

Every GUI session writes a fresh `touhou_tagger_<YYYYMMDD_HHMMSS>.log` in the platform-appropriate per-user log directory (`XDG_STATE_HOME`/`~/.local/state` on Linux, `%LOCALAPPDATA%` on Windows, `~/Library/Logs` on macOS; overridable with `TOUHOU_TAGGER_LOG_DIR`). The logging setup (`_setup_gui_logging` in `touhou_tagger.py`) is called by `gui.py` before PyQt5 is imported, so even an import failure in the Qt layer is captured. The log file path is shown subdued in the permanent right side of the status bar throughout the session, so it's easy to find when something goes wrong. See [`USER_DATA.md`](USER_DATA.md) for the exact paths and privacy notes.

### What is logged

**Session header** (written on startup, before the window appears):

- Log file path
- Python version and platform string
- Full path to the script and current working directory
- Installed versions of PyQt5, playwright, bs4, and mutagen (with graceful "import failed" notes for any that aren't importable)
- Romaniser status: whether the import succeeded, whether `is_ready()` returned True, and whether pykakasi is available

**GUI log pane content:** everything displayed in the in-app log area (both Wiki Tagger and Romanise tabs) is also written to the file as `[INFO]` entries under the `touhou_tagger.gui` logger name. This means the full run — including per-track `[TAG]`/`[ROMANIZE]`/`[SKIP]` lines — is captured in the file. The Tag Edit tab has no log pane; its save errors are surfaced in a popup dialog rather than logged to the file. A shared log contains everything needed to diagnose what happened, without needing to reproduce the session.

**Uncaught exceptions (crash tracebacks):**

- `sys.excepthook` is replaced to log any unhandled exception in the main (GUI) thread as `[CRITICAL]` with a full traceback, then chains to the previous hook so stderr output is preserved.
- `threading.excepthook` (Python 3.8+) is similarly replaced to catch any unhandled exception in a worker `QThread` that escapes the per-worker try/except (e.g. a bug introduced during development).
- Both hooks chain through to whatever was previously installed, so debuggers and other tools are unaffected.

**Qt messages:** `QtCore.qInstallMessageHandler` is used to route Qt's own diagnostic messages (debug, info, warning, critical, fatal) into the log file. Qt fatals in particular call `abort()` and bypass Python's exception system entirely; without this handler they would leave no trace on disk.

**Worker crashes:** if an unhandled exception escapes the processing loop inside `_WikiWorker` or `_RomanizeWorker`, it is caught, written to the log as `[CRITICAL]` with a full traceback, and also surfaced in the GUI log pane as a `💥 Worker crashed` message with the traceback text. The `finally` block always emits `all_done` afterwards so the GUI buttons re-enable.

### Log rotation

On each GUI startup, files in the per-user log directory matching `touhou_tagger_*.log` are listed by modification time and all but the 20 most recent are deleted. This keeps the folder bounded without manual cleanup.

### Graceful degradation

If the per-user log directory cannot be created, a warning is printed to stderr and the GUI continues normally. The exception hooks are still installed and will at least print to stderr; only the file-logging part is skipped.

---

## Romaniser: `japanese_romanizer.py`

A self-contained module that romanises Japanese song titles into the `titlesort` tag using MeCab + UniDic for morphological analysis, a built-in Hepburn katakana table for direct kana conversion, and optional pykakasi as a fallback for kanji that UniDic can't provide a reading for.

Adapted from an earlier Japanese title-to-romaji implementation. The romanisation engine is preserved; the standalone tool uses mutagen-based file I/O.

### Dependencies

Required:
```bash
sudo dnf install mecab mecab-devel      # Fedora
sudo apt install mecab libmecab-dev     # Debian/Ubuntu
yay -S mecab                            # Arch (AUR)
pip install --user mecab-python3 unidic mutagen
python -m unidic download   # ~250 MB
```

Optional (recommended — improves coverage for unusual kanji not in UniDic's readings):
```bash
pip install --user pykakasi
```

### Placement

Place `japanese_romanizer.py` and its data companion (`japanese_romanizer_data.py` or `japanese_title_to_romaji_data.py`) in the same directory as `touhou_tagger.py` and its companion modules. The data file name is tried in that order; either name works.

`touhou_tagger.py` detects the module at startup with a soft import — if the file isn't there, or if MeCab/UniDic aren't installed, wiki tagging continues to work exactly as before and the Romanise GUI tab simply doesn't appear.

### Standalone usage

```bash
# Romanise all music files in one or more album folders:
python source/japanese_romanizer.py "path/to/Album1" "path/to/Album2"

# Dry run — show what would be written without modifying files:
python source/japanese_romanizer.py "path/to/Album1" --dry-run

# Overwrite existing titlesort tags:
python source/japanese_romanizer.py "path/to/Album1" --force-titlesort
```

Operates on any Japanese album — not just Touhou-related ones. Takes the file's existing `title` tag as input. Has no dependency on the wiki tagger or the theme mapping.

### Public API (for use by `touhou_tagger.py`)

| Function | Description |
|---|---|
| `is_ready()` | Returns True when MeCab + UniDic are importable; used to decide whether to show the Romanise tab and enable auto-romanisation |
| `get_install_hint()` | Returns a human-readable message explaining how to install missing dependencies |
| `has_japanese(text)` | Returns True if the string contains any hiragana, katakana, or kanji |
| `to_romaji(text)` | Converts a string with Japanese characters to Hepburn romaji; returns input unchanged if the romaniser is not ready |
| `read_title(path)` | Returns the file's existing `title` tag, or None |
| `read_titlesort(path)` | Returns the file's existing `titlesort` tag, or None |
| `set_titlesort(path, value, dry_run)` | Writes `value` to the appropriate format-specific titlesort tag |
| `romanize_file(path, *, force_titlesort, dry_run, fallback_title)` | Romanises a single file; returns a dict with keys: `status`, `title`, `titlesort_old`, `titlesort_new`, `error` |
| `romanize_files(local_files, *, dry_run, force_titlesort, wiki_titles_by_key, log, indent)` | Romanises a pre-scanned list of file dicts (same format as `touhou_tagger.py`'s scanner); returns a summary dict |
| `process_album_romanize(music_dir, *, dry_run, force_titlesort)` | Scans and romanises a directory; the entry point used by the Romanise GUI tab and the standalone CLI |

### Status values from `romanize_file`

| Status | Meaning |
|---|---|
| `romanized` | `titlesort` written (or would be in dry run) |
| `overwritten` | Existing `titlesort` replaced because `force_titlesort=True` |
| `skip_no_japanese` | `title` contains no Japanese characters |
| `skip_exists` | `titlesort` already set; not forcing |
| `skip_unchanged` | Romaji output is identical to the existing `titlesort` |
| `skip_no_title` | File has no `title` tag and no fallback was supplied |
| `error` | Exception while reading or writing |

### Romanisation engine

The standalone romanisation engine preserves these key behaviours:

- **Normalises** half-width katakana and full-width Latin/digits via `unicodedata.normalize("NFKC")` before processing
- **Detects isolated katakana okurigana**: single katakana characters not adjacent to other katakana are converted to hiragana before MeCab tokenisation (e.g. 永イ夜ハ → 永い夜は), so MeCab can read them correctly
- **MeCab tokenisation**: each Japanese segment is parsed into tokens with POS (part of speech) tags; readings come from UniDic's conjugation-form fields for inflecting POS, or the surface reading field for others
- **Particle normalisation**: は is romanised as "wa" (not "ha") and へ as "e" (not "he") when functioning as particles
- **Okurigana**: verb/adjective endings attach directly to their stem (no space)
- **ん boundary**: an apostrophe is inserted before vowels and y (e.g. 堕落の宴 → Daraku no En'kai would gain an apostrophe before a vowel)
- **Gemination**: っ/ッ doubles the following consonant (e.g. っt → tt, っch → tch)
- **Long vowels**: ー extends the preceding vowel
- **Loanword override**: multi-token katakana sequences are checked against `_LOANWORDS_MAP` (longest-first) and replaced with the canonical English spelling
- **Phrase override**: sequences of 2–6 MeCab surface forms are checked against `_PHRASE_OVERRIDES` before loanword matching
- **Title override**: the full input string, or a known base title followed by a delimiter/suffix such as `[Instrumental]`, is checked against `_TITLE_OVERRIDES` first; the known base uses its exact override and any Japanese in the suffix is processed normally
- **Capitalisation**: the first token in each Japanese segment is capitalised; particles and suffixes stay lowercase; tokens found in the loanword table use its casing

### No-overwrite default

By default, existing `titlesort` tags are never overwritten. The log always shows both the current value and what would have been set. This prevents unintentionally replacing manually corrected `titlesort` values. Pass `--force-titlesort` (CLI), tick "Force overwrite" (GUI), or pass `force_titlesort=True` in code to override.

---

## Supported distribution

The standalone tagger in `source/` is the supported application and is
launched with `launch.sh`.

## Anti-Bot Detection

Both the English Touhou Wiki and THBWiki apply bot detection, but in different ways. This section consolidates the findings from development.

### English Touhou Wiki (en.touhouwiki.net)

Applies TLS-fingerprint-based detection plus User-Agent deny-listing. The cascade of failures during development:

| Approach | Result | What it told us |
|---|---|---|
| `urllib` with default UA | HTTP 418 | Blocked at the TLS-fingerprint level — Python's HTTP stack is identifiable regardless of headers |
| `urllib` with browser UA | HTTP 418 | Confirms TLS fingerprint check; UA alone isn't enough |
| Playwright `request.new_context()` | HTTP 418 | Playwright's API client is Node.js-based, not Chromium-based, so it has its own fingerprint |
| Real Chromium → `api.php` | HTTP 403 | TLS check passes, but `api.php` denies anonymous access at the application layer |
| Real Chromium → `index.php?action=raw` | HTTP 200 | Works, but raw wikitext lacks JS-injected English titles for purely-Japanese tracks |
| Real Chromium → `/wiki/PAGE` (default UA) | HTTP 403 | The default Playwright UA contains "HeadlessChrome", which is on the wiki's deny-list |
| Real Chromium → `/wiki/PAGE` (custom UA) | HTTP 200 | Works ✓ |

The final approach combines real Chromium (correct TLS fingerprint), a non-`HeadlessChrome` UA (passes the deny-list), and the rendered `/wiki/` path (full DOM):

- **`touhou_tagger.py` (standalone):** uses `wait_until="networkidle"` (via `touhou_wiki.py`).

**Tooltip injection (historical):** The wiki previously injected English theme names as `title=` attributes on tooltip wrapper elements via JavaScript. As of 2026 this injection no longer occurs, so the standalone script now extracts the visible Japanese text and translates it via the theme mapping instead. The tooltip search code is retained so it will work automatically if the wiki restores this behaviour.

**Rate limiting:** The wiki also rate-limits after the first request from a single browser session. Batch-scraping multiple pages (attempted during theme mapping development) results in HTTP 403 on the second and subsequent requests. This is why the theme mapping is built from thpatch.net data instead.

### THBWiki (thwiki.cc)

THBWiki applies different protections to its API and rendered pages, so the two are handled differently.

#### asktrack REST API (`/rest/asktrack/v0/query`)

Applies TLS-fingerprint-based detection at the nginx level — the same class of protection as the English wiki. Python's `urllib` is blocked; `curl` works reliably.

| Approach | Result |
|---|---|
| `urllib` (any UA) | Connection dropped — `RemoteDisconnected: Remote end closed connection without response` |
| `curl` | Works ✓ |

**Note:** SafeLine WAF now fronts the entire `thwiki.cc` domain. If its rules are extended to cover API paths, `curl` calls may also be affected. Verify by checking whether the tagger raises `json.JSONDecodeError` from a challenge page being returned instead of JSON.

#### Rendered album pages (`https://thwiki.cc/PAGE`)

THBWiki's rendered pages sit behind a **SafeLine WAF** challenge (Chaitin's self-hosted WAF product). A Cloudflare interactive Turnstile was also present until mid-2025, when it was removed, leaving SafeLine as the interactive checkpoint. As of mid-2026, however, Cloudflare is back in front of SafeLine in a *passive* capacity: a valid session now carries **both** an `sl-session` (SafeLine) and a `cf_clearance` (Cloudflare) cookie (plus the `sl_jwt_*` pair), and Cloudflare injects its passive JS-detection beacon (`/cdn-cgi/challenge-platform/scripts/jsd/main.js`, with a `window.__CF$cv$params` blob) into **normally-served** pages — which is exactly why `_looks_like_challenge()` must *not* treat that path as a block page (see the detector note under "THBWiki page HTML fetch — current approach" above).

The progression of attempts during development (initially developed against Cloudflare; SafeLine produces the same class of failure for scripted clients):

| Approach | Result | Why |
|---|---|---|
| `curl` (any UA) | WAF challenge HTML | TLS-fingerprint detection blocks scripted HTTP clients |
| Headless Playwright (default UA) | WAF challenge page | SafeLine actively detects and blocks headless browsers |
| Headless Playwright (custom UA, de-automation flags) | WAF challenge page | SafeLine's headless detection is not bypassed by UA changes alone |
| Headed Playwright (visible browser, de-automation flags) | WAF challenge page | Automation signals are still detectable; challenge does not clear |
| `curl_cffi` + browser WAF session cookie | Works ✓ | Real browser passes the challenge; curl_cffi reuses the cookie with matching TLS fingerprint |

**Why Playwright fails:** SafeLine detects both headless browsers and headed browsers with automation signals (`navigator.webdriver`, `--enable-automation`). Stripping these signals (via `--disable-blink-features=AutomationControlled` and `ignore_default_args=["--enable-automation"]`) was partially effective against the former Cloudflare Turnstile but does not reliably bypass SafeLine's detection. This is why the headless-Playwright no-cookie fallback was removed entirely rather than kept as a best-effort option — see "THBWiki page HTML fetch — current approach" above.

**Why curl_cffi is required (not plain curl):** The WAF session cookie is bound to the TLS fingerprint, User-Agent, and IP of the browser that obtained it. SafeLine uses JA4 fingerprinting: plain `curl` presents a different fingerprint and is re-challenged even with a valid cookie. `curl_cffi` impersonates a real browser's TLS/JA4/HTTP2 fingerprint, so the cookie validates.

**Practical workflow:** Open any THBWiki page in a real browser and pass the "verify you are human" check. From there the cookie reaches the tagger one of two ways:

- **(a) Auto-pull (preferred).** With `browser_cookie3` installed, the tagger reads the live cookie straight from the browser on each run (`browser_cookie.py` → `THWIKI_COOKIE`), so there's nothing to copy. Just keep a verified THBWiki tab open — ideally with the `thwiki_keepalive.user.js` userscript running so the session stays warm and the rotating cookie keeps refreshing. See "Browser cookie auto-pull" above.
- **(b) Manual (fallback).** DevTools (F12) → Network → copy the full `Cookie` header value and `User-Agent` from a document request → paste both into the **"THBWiki Authentication…"** dialog in the GUI (or export `THWIKI_COOKIE`/`THWIKI_UA`). The dialog also has a **"Pull from browser"** button that does (a) on demand.

Either way the `User-Agent` must match the browser the cookie came from (auto-pull does **not** fetch the UA — `cf_clearance` is bound to it); the UA and Impersonate profile persist to the platform config directory's `auth.json` across restarts, while the cookie never does. Older `thwiki_auth.json` files remain a read-only compatibility fallback. Re-verify the session in the browser (or re-paste) when a run reports it was re-challenged. Apart from auto-pull there is no automated way past the human check — if neither a pulled nor a pasted cookie is usable, the standalone tagger refuses to run (`ThwikiCookieError`, before any file is touched) rather than continuing with degraded data.

### Touhou Patch Center (thpatch.net)

Behind Cloudflare's JavaScript challenge. Neither `curl`, `urllib`, nor Playwright can bypass it:

| Approach | Result |
|---|---|
| `curl` | Cloudflare JS challenge page (HTML, not JSON) |
| `urllib` | Same Cloudflare challenge |
| Playwright (headless Chromium) | HTTP 403 |

The workaround is to open the API URLs in a real browser, which passes the Cloudflare challenge, and save the JSON responses locally. This is only needed once (or when a new game releases).

---

## Recommended Workflow

### Initial setup

1. Save the two thpatch.net API JSON responses from your browser
2. Run `build_theme_mapping/build_theme_mapping.py` to generate `source/touhou_theme_mapping.json`
3. Keep the generated mapping file in `source/`, next to the standalone tagger modules
4. Install `curl_cffi`, which is what makes a THBWiki browser cookie actually work for the page fetch (the cookie itself is mandatory for every run, not just this library — see "THBWiki page HTML fetch — current approach"). Optionally also install `browser_cookie3` to auto-pull that cookie from your browser instead of pasting it each run, and install the `thwiki_keepalive.user.js` userscript in your browser to keep the session warm:
   ```bash
   pip install --user curl_cffi
   pip install --user browser_cookie3   # optional — cookie auto-pull
   ```
5. Optionally install the romaniser's dependencies to enable `titlesort` writing:
   ```bash
   sudo dnf install mecab mecab-devel      # Fedora
   sudo apt install mecab libmecab-dev     # Debian/Ubuntu
   yay -S mecab                            # Arch (AUR)
   pip install --user mecab-python3 unidic pykakasi
   python -m unidic download
   ```
   `japanese_romanizer.py` and `japanese_romanizer_data.py` are already kept in `source/` next to `touhou_tagger.py` and its companion modules.

### For batch tagging files on disk

1. Double-click `launch.sh`, or run `python source/touhou_tagger.py` with no arguments, to open the GUI; use the CLI form for scripted/headless workflows
2. **Set up THBWiki authentication first — it's mandatory, not optional** (once per session, or whenever a run reports it was re-challenged): open any THBWiki page in your normal browser and pass the "verify you are human" check. If `browser_cookie3` is installed, that's all you normally need — the tagger auto-pulls the live cookie from the browser each run (keep the tab open, ideally with `thwiki_keepalive.user.js` running). Otherwise supply it manually: DevTools (F12) → Network → copy the full `Cookie` header and `User-Agent` from a document request, then paste them into **THBWiki Authentication…** in the Wiki Tagger sidebar and click Save (or `export THWIKI_COOKIE='...'` and `export THWIKI_UA='...'` for the CLI). The User-Agent and Impersonate profile are saved to disk for future sessions; the UA must match the cookie's browser either way. Skipping this entirely (or letting both the pulled and pasted cookie go stale) aborts the run before anything is tagged — see "THBWiki page HTML fetch — current approach" above.
3. **GUI:** drag album folders (or an entire `[Artist]` folder to add all its albums at once) from Dolphin into the window, review the auto-suggested wiki slugs, check "Dry run", and click "Tag All" to verify; the summary dialog's **Changes tab** shows a per-track diff of everything that would be written or overwritten, filterable by tag type, plus any **⚠ title discrepancies** (right-click a row, or use the bulk buttons, to fix a wrong local title from the wiki/TouhouDB value — re-romanising `titlesort` automatically). If a folder is matched to the wrong page the run **pauses** with a Local/TouhouDB/Wiki comparison dialog (Skip / Continue / Cancel). Watch the new **fetch status strip** above the progress bar while it fetches — it fills in one segment per album as each is fetched, turning red for any that fail or aren't found, so you can spot problem albums immediately rather than waiting for the whole batch and reading back through the log; click a red (or any) segment to jump straight to that album's fetched output. **CLI:** run with `--dry-run` to verify track matching (a severe track mismatch is auto-skipped there, with a warning)
3. The script automatically tries the English wiki first, then falls back to THBWiki
4. If the romaniser is set up, `titlesort` tags are written in the same pass — the log shows `[ROMANIZE]` / `[SKIP-RM]` lines interleaved with the `[TAG]` lines
5. Fix any `[NO MATCH]` files manually using **Ex Falso** (bundled with Quod Libet)
6. Uncheck "Dry run" (GUI) or re-run without `--dry-run` (CLI) to apply tags
7. To correct wiki mistakes (wrong date, wrong grouping, etc.) without leaving the GUI, right-click the affected album(s) in the Wiki Tagger tab → **Send to… → Tag Edit**, switch to the Tag Edit tab, make corrections, and click **Save Changes**
8. For albums not on either wiki, use the **Romanise tab** (GUI) or run `japanese_romanizer.py` directly to still get `titlesort` tags, and use Ex Falso to set `grouping` manually

### Romanising albums that aren't on either wiki

Use the standalone romaniser directly — it has no dependency on the wiki tagger:

```bash
python source/japanese_romanizer.py "path/to/SomeAlbum" --dry-run
python source/japanese_romanizer.py "path/to/SomeAlbum"
```

Or use the **Romanise tab** in the `touhou_tagger.py` GUI — drag in album folders and click "Romanise All".

### Updating the theme mapping

When a new Touhou game or music CD is released:

1. Re-save the two thpatch.net API JSON responses from your browser
2. Re-run `build_theme_mapping.py`
3. Replace the old mapping file in both locations
