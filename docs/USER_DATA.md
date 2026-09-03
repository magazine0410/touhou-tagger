# User data and privacy

Touhou Tagger keeps configuration, scan caches, and diagnostic logs
outside its source/install directory. This makes a clean checkout safe for a
new user, allows read-only installations, and reduces the chance of committing
personal library information.

## Storage locations

### Configuration and scan data

| Platform | Default directory |
| --- | --- |
| Linux and other Unix | `$XDG_CONFIG_HOME/touhou_tagger`, or `~/.config/touhou_tagger` |
| Windows | `%APPDATA%\touhou_tagger` |
| macOS | `~/Library/Application Support/touhou_tagger` |

Set `TOUHOU_TAGGER_CONFIG_DIR` to override the complete directory on any
platform.

The directory contains:

| File | Contents |
| --- | --- |
| `availability.json` | Absolute album and artist paths manually marked unavailable on the wikis. |
| `stats.json` | The last library root selected in the Statistics tab. |
| `stats_cache.json` | Per-file modification times and cached tag/statistics fields. |
| `stats_result.json` | The aggregated result of the last completed Statistics scan. |
| `auth.json` | THBWiki browser choice, auto-pull preference, User-Agent, and `curl_cffi` impersonation profile. It never contains a browser cookie. |
| `external_tools.json` | User-selected executable path overrides for external tools. It contains no credentials or command output. |
| `album_overrides.json` | Reviewed Wiki Slug overrides keyed by normalized absolute album path. |
| `tag_locks.json` | Tag names locked against Wiki Tagger overwrite, keyed by normalized absolute file path. It holds local file paths and tag names; no credentials. Importing a backup replaces the locks wholesale. |
| `retag_credits_names.json` | TouhouDB romanizations resolved by `retag_credits.py --romanize` (a local-only maintenance tool, not part of this repository), cached between sessions so a resumed migration does not re-query them. Public artist names only; no credentials. |
| `retag_credits_state.json` | Per-album progress of the `retag_credits.py` credit-repair migration (a local-only maintenance tool, not part of this repository), so an expired THBWiki session resumes instead of restarting. It holds album paths and per-album outcomes; no credentials. Delete it, or run with `--reset`, to start the migration over. |
| `preferences.json` | Non-secret folder scan depth, CUE original-handling choice, Wiki Tagger field selection, and small GUI state. |
| `storage_locations.json` | A non-secret pointer under the platform default directory for GUI-selected config/log locations. |

The GUI's **Settings → Storage locations…** page shows the active directories,
can open them in the file manager, and can copy existing data to a new pair of
locations. **Reset settings** restores the platform defaults without deleting
files left in a previously selected location. `storage_locations.json` is a
small pointer kept under the platform default configuration directory so a
custom location remains discoverable after a restart. Explicit
`TOUHOU_TAGGER_CONFIG_DIR` and `TOUHOU_TAGGER_LOG_DIR` environment variables
take precedence and make the corresponding GUI change action read-only.

**Settings → Export configuration…** writes an explicit, cookie-free JSON
backup of browser preferences, executable paths, folder-scan/CUE/tag-selection preferences,
album identity overrides, manual tag locks, unavailable-folder marks,
Statistics' library root, and small GUI preferences. Cookies, browser profiles, and other session
secrets are neither exported nor imported. The backup does contain local
library, album, and executable paths, so review it before sharing publicly.
The default `touhou_tagger_backup.json` filename is ignored by the repository.

`thwiki_auth.json` from older releases is read as a compatibility fallback for
the THBWiki User-Agent and impersonation profile; new saves use `auth.json`.

The tagger creates its configuration directory with user-only permissions and
restricts these files to the current user on POSIX systems. Windows access is
controlled by the user's profile permissions.

### Diagnostic logs

| Platform | Default directory |
| --- | --- |
| Linux and other Unix | `$XDG_STATE_HOME/touhou_tagger/logs`, or `~/.local/state/touhou_tagger/logs` |
| Windows | `%LOCALAPPDATA%\touhou_tagger\logs` |
| macOS | `~/Library/Logs/touhou_tagger` |

Set `TOUHOU_TAGGER_LOG_DIR` to override the complete log directory.

The GUI keeps at most 20 timestamped logs. Logs can contain absolute script and
music-library paths, platform/dependency information, album and track names,
tagging decisions, and crash tracebacks. Review a log before sharing it
publicly. The CLI does not create a log file.

Older versions wrote GUI logs to a `logs/` folder beside the scripts. Current
versions no longer do; if such a folder exists from an older run it is not
moved or deleted automatically, but the repository's `.gitignore` prevents it
from being added accidentally.

## Cookies and browser data

For the complete manual-authentication steps and the optional browser-cookie
helper's behavior, see [AUTHENTICATION.md](AUTHENTICATION.md).

- The THBWiki cookie lives only in the current process environment.
  It is never written to a tagger configuration file or normal GUI log.
  Cookie-fetch failures use generic messages rather than printing request
  commands or exception text that could contain headers.
- `auth.json` stores only non-secret browser/authentication preferences and
  User-Agent/impersonation values; it never stores either `Cookie` header.
- When optional automatic cookie loading is enabled, `browser_cookie3` reads
  the selected browser's cookie store in place. The tagger copies only the
  matching cookie header into process memory; it does not copy or package a
  browser profile.
- A manually supplied `THWIKI_COOKIE` should be treated as a
  secret. Do not put it in a tracked shell script, `.env` file, issue, or log.
- The authentication dialog's **Test authentication** action makes a live
  request and reports only missing-cookie, challenge, transport-error, or
  success status; it never displays the Cookie header.
- The tagger has no automatic bug-report or issue-submission feature. GUI logs
  stay local; review them for personal paths and music metadata before sharing.

## Library defaults

The Statistics tab does not contain a developer library path. On first use it
starts from:

1. `TOUHOU_TAGGER_LIBRARY_ROOT`, when set; otherwise
2. the operating system's standard Music folder.

After a successful scan, the selected root is stored in `stats.json`.

## Repository safeguards

The root `.gitignore` excludes:

- generated logs, caches, virtual environments, and build output;
- local assistant/tool settings;
- environment/auth files and common copied browser-profile directories;
- the default configuration-backup filename; and
- audio files and common test-music directories.

No audio or test-music files, persisted cookies, copied browser databases, or
per-user configuration files were present during the 2026-07-30 audit. The
stale local `logs/` directory left over from older in-tree logging was deleted
during that audit; any such directory recreated later is ignored by
`.gitignore`.
