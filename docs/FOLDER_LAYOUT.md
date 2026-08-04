# Folder layouts and naming

Touhou Tagger does not require one exact music-library layout. Select an
album folder directly whenever possible; this is the most reliable option.

## Minimum layout for tagging

An album folder is usable when it contains at least one supported audio file
directly:

```text
Any music folder/
└── Album Title/
    ├── 01 Track.flac
    └── 02 Track.flac
```

Supported tagging formats are MP3, FLAC, OGG, M4A, and Opus. The folder may
live anywhere, and its name may be only the album title. A leading track
number is recommended for matching, but is not required when the audio tags
already contain track numbers.

Multi-disc albums may put audio in recognised disc subfolders:

```text
Artist/
└── Album Title/
    ├── Disc 1/
    │   └── 01 Track.flac
    └── Disc 2/
        └── 01 Track.flac
```

`Disc 1`, `DISC2`, `Disk 01`, and `CD 2` are recognised. The same
`Album Title/Disc N/` structure also works without an artist folder when the
album itself is selected.

## Adding several albums at once

The GUI expands container folders down to album folders. By default it searches
**one** level, which is ideal for the usual layout:

```text
Library/
└── Artist or circle/
    ├── Album One/
    └── Album Two/
```

Drag the artist/circle folder to add both immediate album folders. Brackets
are optional: `[Example Circle]` is displayed as `Example Circle`, while
`Example Circle` is used unchanged.

The depth is configurable in the GUI settings under **Folder scan depth**
(1, 2, or 3 container levels; default 1), so a deeper tree can be expanded
automatically. For example, at depth 2 the GUI reaches `Deep Album` below:

```text
Artist/
└── Archive/
    └── Deep Album/
```

At the default depth of 1 the same layout is added by selecting the immediate
container (`Archive`) or the album (`Deep Album`) itself.

With the default depth of 1, dragging the outer `Artist` folder does **not**
search through `Archive`; this avoids silently adding an unexpected collection
of folders. Increase the scan depth when that deeper expansion is wanted.

The Statistics tab is designed for `Library/Artist/Album/` and treats the
chosen root's immediate subdirectories as artists. Directly selecting an
album still works in the Wiki Tagger, Romanise, and Tag Edit tabs.

## Recommended naming convention

The following is convenient, but none of the date, catalogue, event, or
bracket components are required:

```text
Library/
└── [Circle]/
    └── 2024.05.03_[ABC-001]_Album Title_[Event]/
```

When no embedded `album` tag is available, the tagger makes a wiki-slug
suggestion from the folder name. It removes a leading date and bracketed
segments, then replaces spaces with underscores. For example:

```text
2024.05.03_[ABC-001]_Album Title_[Event]
→ Album_Title
```

Each component may be omitted. An album named simply `Album Title` therefore
suggests `Album_Title`.

## Review inferred values before tagging

Folder-derived information is a convenience, not an authority.

| Value | How it is inferred | What uses it | Safeguard |
| --- | --- | --- | --- |
| Wiki slug | `album` tag first; otherwise the cleaned folder name | Wiki lookup | The GUI shows the suggestion in the editable **Wiki Slug** column; double-click it to replace it. The CLI always requires an explicit slug. Use **Dry run** before writes. |
| Artist/circle | `albumartist` tag first; otherwise the parent folder name | Copy-to-clipboard convenience and display | It is not used to select a wiki page or write tags. Fetched wiki data remains the source of tagged album artists. |

After a fetch, the GUI exposes track discrepancies and a severe mismatch
dialog with **Skip**, **Continue**, and **Cancel** choices. The command line
skips a severe mismatch rather than writing automatically. These are safety
nets, not a substitute for reviewing the suggested slug.

## Album images and CUE sheets

For one whole-album FLAC image, add an external `.cue` file beside it or embed
a CUESHEET in the FLAC. The CUE-splitting recovery can then split it into
tracks after its pre-flight checks. A plausible image without usable CUE timing
is never split. For a multi-disc image set, use distinct disc names and a CUE
for every image; all discs must validate before the multi-disc split begins.

See [EXTERNAL_TOOLS.md](EXTERNAL_TOOLS.md) for the FFmpeg/FLAC requirements of
CUE splitting.
