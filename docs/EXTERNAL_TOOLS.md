# External tools

Touhou Tagger launches a small number of external programs. This page
lists every executable referenced by the standalone tagger, what needs it, and
what happens when it is unavailable.

Python packages such as `mutagen`, `curl_cffi`, and `browser_cookie3` are not
external commands; their pinned versions and optional groups are listed in
[DEPENDENCIES.md](DEPENDENCIES.md).

## Required for normal wiki tagging

### `curl`

Used for:

- THBWiki's `asktrack` API, which supplies THBWiki track data and per-track
  credits.
- Optional TouhouDB verification.
- A last-resort plain-HTTP fallback for rendered THBWiki pages when
  `curl_cffi` is unavailable. This fallback usually cannot pass the site's
  browser challenge; `curl_cffi` plus a matching browser cookie remains the
  supported rendered-page path.

Installation:

| Platform | Example |
| --- | --- |
| Fedora | `sudo dnf install curl` |
| Debian/Ubuntu | `sudo apt install curl` |
| Arch | `sudo pacman -S curl` |
| macOS | The system normally includes it; `brew install curl` installs a newer copy. |
| Windows 10/11 | Included with Windows. Older systems can use the packages from [curl's official download page](https://curl.se/download.html). |

The executable must be named `curl` and available on `PATH`, or configured
with an absolute path in **Settings → External tools…** in the GUI. The
override is shared by the CLI and GUI because it is stored in the per-user
configuration directory.

If it is missing:

- THBWiki API requests print a clear error and return no API tracks or
  credits. An English-wiki album may still have its primary track list, but
  THBWiki fallback matching and API-sourced credits cannot work.
- TouhouDB prints that verification was skipped and returns without retrying.
- The plain-curl THBWiki page fallback reports the transport error and
  returns no page. It does not crash the process.

## Managed browser executable

### Playwright Chromium

The English Touhou Wiki fetch uses the Chromium binary managed by the Python
`playwright` package. It is not searched for on `PATH`; Playwright maintains
its own version-matched browser installation.

Install it after installing the Python package:

```bash
python -m playwright install chromium
```

On supported Linux distributions, Playwright can also install required system
libraries:

```bash
python -m playwright install --with-deps chromium
```

See the [official Playwright browser documentation](https://playwright.dev/python/docs/browsers).
Playwright browser versions are tied to the installed Python package, so rerun
the install command after upgrading Playwright if it requests a newer browser.

If Chromium is missing or cannot launch, the English-wiki attempt reports its
exception and the album lookup falls back to THBWiki. It does not prevent
THBWiki-only operation.

## CUE splitting

### `ffmpeg`

Required only for **Split via CUE sheet**. It cuts a whole-album FLAC image at
the CUE index points and re-encodes the resulting tracks as FLAC.

Install with:

| Platform | Example |
| --- | --- |
| Fedora | `sudo dnf install ffmpeg` |
| Debian/Ubuntu | `sudo apt install ffmpeg` |
| Arch | `sudo pacman -S ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | Install a build linked from [FFmpeg's official download page](https://ffmpeg.org/download.html) and add its `bin` directory to `PATH`. |

If it is missing, the GUI does not offer the CUE-splitting button. A direct
call to the splitting API returns a `no_tools` result with installation
instructions. Ordinary scanning and tagging are unaffected.

### `flac`

Required only for **Split via CUE sheet**. After FFmpeg creates each track,
`flac -t` verifies that the output decodes without errors before the original
album image can be moved to Trash.

The same FLAC package normally installs both `flac` and `metaflac`:

| Platform | Example |
| --- | --- |
| Fedora | `sudo dnf install flac` |
| Debian/Ubuntu | `sudo apt install flac` |
| Arch | `sudo pacman -S flac` |
| macOS | `brew install flac` |
| Windows | Download the Windows command-line tools from [Xiph's official FLAC downloads](https://xiph.org/flac/download.html) and add their directory to `PATH`. |

If `flac` is missing, CUE splitting is disabled in the same way as for a
missing `ffmpeg`. If verification runs but fails, the split is aborted and the
original image is kept.

### `metaflac`

Optional CUE-detection helper. It reads a `CUESHEET` Vorbis comment or binary
FLAC CUESHEET metadata block embedded in an album image. It comes with the
FLAC command-line tools described above.

If it is missing or fails, embedded CUE data is unavailable. External `.cue`
files can still be detected and used, and all non-splitting features continue
normally. No separate warning is shown merely because an embedded CUE could
not be inspected.

### Trash backends: `gio`, `trash-put`, `kioclient5` / `kioclient`

After a split has been created, tagged, and decode-verified, the tagger tries
these recoverable Trash operations in order when the selected post-processing
choice is **Move original to Trash**:

1. `gio trash`
2. `trash-put`
3. `kioclient5 move ... trash:/`, falling back to the executable name
   `kioclient`

Only one working backend is needed. Common installation routes are:

| Command | Common source |
| --- | --- |
| `gio` | GLib/GIO tools: `sudo dnf install glib2`, `sudo apt install libglib2.0-bin`, `sudo pacman -S glib2`, or `brew install glib`. |
| `trash-put` | The `trash-cli` package: `sudo dnf install trash-cli`, `sudo apt install trash-cli`, `sudo pacman -S trash-cli`, or install it in an isolated Python environment such as `pipx`. |
| `kioclient5` / `kioclient` | KDE KIO command-line tools, normally already present with a KDE desktop; package names vary by distribution. |

These are Unix/freedesktop-oriented backends. The current implementation has
no native Windows Trash command; that limitation is tracked separately in the
Windows-compatibility checklist.

If none is installed, or every attempted Trash operation fails, the split
still succeeds but the original whole-album image is deliberately left beside
the new tracks. The log says that no working Trash backend was found. Nothing
is permanently deleted.

The tagger does **not** invoke `shnsplit`, `shntool`, or `cuetag`.

The GUI's **Settings → General preferences…** menu controls what happens after
those mandatory checks pass: move the original to recoverable Trash (the
default), keep it beside the new tracks, or ask on each split. Permanent
deletion is not offered. The same preferences dialog controls folder expansion
depth for dropped/selected containers (one, two, or three levels).

### External-tool path overrides

The GUI's **Settings → External tools…** dialog checks every command used by
the standalone tagger and shows which feature needs it. It can save an
absolute executable path for `curl`, `ffmpeg`, `flac`, `metaflac`, or each Trash
backend. A saved but missing override is reported as unavailable instead of
silently falling back to a different executable; clear the override to return
to normal `PATH` lookup. The settings file contains paths only, not cookies,
command output, or browser data.

## Not external commands

- MeCab is loaded through the optional `mecab-python3` extension; the tagger
  does not execute a `mecab` program. If MeCab or UniDic is missing, only
  romanisation is disabled.
- `curl_cffi` performs requests inside Python and does not use the `curl`
  executable. Plain `curl` is still independently needed for THBWiki's
  `asktrack` API.
- `browser_cookie3` reads a configured browser's cookie database; the tagger
  does not launch Chrome, Brave, Firefox, or another personal browser.
- Folder opening uses Qt's operating-system service API rather than calling a
  named file-manager command.

## Quick check

On Linux or macOS, the named commands can be located with:

```bash
command -v curl ffmpeg flac metaflac gio trash-put kioclient5 kioclient
python -m playwright install --list
```

On Windows, use `where.exe` for individual commands, for example:

```powershell
where.exe curl
where.exe ffmpeg
where.exe flac
python -m playwright install --list
```
