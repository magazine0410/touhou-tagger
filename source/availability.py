"""availability.py — persistent "unavailable on the wikis" marks.

Neither the English Touhou Wiki nor THBWiki covers every album or circle, so
some folders can never be wiki-tagged.  This module lets the user *manually*
flag those as unavailable and have that flag persist across sessions:

* **Albums** flagged here get a warning sign + faint-yellow background in the
  Wiki Tagger tab so they stand out from genuinely-untagged albums.
* **Artists** flagged here become a third (yellow) category in the Statistics
  tab's pie chart, separate from "untagged" (which means "not tagged *yet*").

Both are keyed by absolute directory path and stored in the tagger's
platform-appropriate per-user configuration directory (see
:func:`app_config_dir`)::

    {"albums": ["/abs/path/album", ...], "artists": ["/abs/path/artist", ...]}

A module-level cache is the single in-process source of truth, so a change made
in one tab is immediately visible to the other (both import this module).  The
cache is loaded lazily on first access and re-written on every mutation.

Leaf module: imports nothing from the project (mirrors ``browser_cookie.py``),
so both ``gui.py`` and ``library_stats.py`` can import it without creating a
cycle or dragging PyQt5 onto the CLI path.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

_APP_DIRNAME = "touhou_tagger"


def _normalise_user_dir(path: str) -> str:
    """Expand and absolutise a user-configured storage directory."""
    return os.path.abspath(os.path.expanduser(path))


def _platform_config_dir() -> str:
    """Return the platform default, without applying user overrides."""
    if os.name == "nt":
        base = (
            os.environ.get("APPDATA")
            or os.environ.get("LOCALAPPDATA")
            or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
        )
    elif sys.platform == "darwin":
        base = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support"
        )
    else:
        base = os.environ.get(
            "XDG_CONFIG_HOME",
            os.path.join(os.path.expanduser("~"), ".config"),
        )
    return os.path.join(_normalise_user_dir(base), _APP_DIRNAME)


def _platform_log_dir() -> str:
    """Return the platform default log directory, without overrides."""
    if os.name == "nt":
        base = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        )
        return os.path.join(_normalise_user_dir(base), _APP_DIRNAME, "logs")
    if sys.platform == "darwin":
        return os.path.join(
            os.path.expanduser("~"), "Library", "Logs", _APP_DIRNAME
        )
    base = os.environ.get(
        "XDG_STATE_HOME",
        os.path.join(os.path.expanduser("~"), ".local", "state"),
    )
    return os.path.join(_normalise_user_dir(base), _APP_DIRNAME, "logs")


def _storage_pointer_path() -> str:
    """Return the stable pointer used to remember a GUI-selected location."""
    return os.path.join(_platform_config_dir(), "storage_locations.json")


def _load_storage_pointer() -> dict[str, str]:
    try:
        with open(_storage_pointer_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return {}
        result = {}
        for key in ("config_dir", "log_dir"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                result[key] = _normalise_user_dir(value)
        return result
    except (OSError, ValueError):
        return {}


def default_config_dir() -> str:
    """Return the platform default configuration directory."""
    return _platform_config_dir()


def default_log_dir() -> str:
    """Return the platform default log directory."""
    return _platform_log_dir()


def app_config_dir() -> str:
    """Return the active per-user configuration directory.

    The environment variable remains the highest-priority override for
    portable/managed installs.  Otherwise the GUI may persist a custom
    location in a small pointer under the platform default directory.
    """
    override = os.environ.get("TOUHOU_TAGGER_CONFIG_DIR", "").strip()
    if override:
        return _normalise_user_dir(override)
    return _load_storage_pointer().get("config_dir", _platform_config_dir())


def app_log_dir() -> str:
    """Return the active per-user GUI log directory.

    ``TOUHOU_TAGGER_LOG_DIR`` is the highest-priority override.  If it is not
    set, a GUI-selected path is loaded from the same stable pointer as the
    configuration location.
    """
    override = os.environ.get("TOUHOU_TAGGER_LOG_DIR", "").strip()
    if override:
        return _normalise_user_dir(override)
    return _load_storage_pointer().get("log_dir", _platform_log_dir())


def storage_locations() -> dict[str, str]:
    """Return active, default, and environment-controlled storage paths."""
    return {
        "config_dir": app_config_dir(),
        "log_dir": app_log_dir(),
        "default_config_dir": default_config_dir(),
        "default_log_dir": default_log_dir(),
        "config_env": os.environ.get("TOUHOU_TAGGER_CONFIG_DIR", "").strip(),
        "log_env": os.environ.get("TOUHOU_TAGGER_LOG_DIR", "").strip(),
    }


def _copy_user_files(source: str, target: str) -> None:
    """Copy existing user data to a newly selected directory, non-destructively."""
    if not os.path.isdir(source) or _norm(source) == _norm(target):
        return
    ensure_private_directory(target)
    for name in os.listdir(source):
        src = os.path.join(source, name)
        dst = os.path.join(target, name)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
                restrict_private_file(dst)
            except OSError:
                pass


def set_storage_locations(config_dir: str, log_dir: str) -> bool:
    """Persist custom storage locations and copy existing data safely.

    The pointer is intentionally stored under the platform default config
    directory so it remains discoverable even after the active directory is
    changed.  The running process keeps import-time config paths, so callers
    should restart after a successful change.
    """
    config_dir = _normalise_user_dir(config_dir)
    log_dir = _normalise_user_dir(log_dir)
    current = storage_locations()
    if current["config_env"] or current["log_env"]:
        return False
    try:
        _copy_user_files(current["config_dir"], config_dir)
        _copy_user_files(current["log_dir"], log_dir)
        ensure_private_directory(os.path.dirname(_storage_pointer_path()))
        tmp = _storage_pointer_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"config_dir": config_dir, "log_dir": log_dir}, f,
                      ensure_ascii=False, indent=2)
        restrict_private_file(tmp)
        os.replace(tmp, _storage_pointer_path())
        restrict_private_file(_storage_pointer_path())
        return True
    except OSError:
        return False


def reset_storage_locations() -> bool:
    """Return to platform defaults without deleting custom user data."""
    if (os.environ.get("TOUHOU_TAGGER_CONFIG_DIR", "").strip()
            or os.environ.get("TOUHOU_TAGGER_LOG_DIR", "").strip()):
        return False
    try:
        path = _storage_pointer_path()
        if os.path.exists(path):
            os.remove(path)
        return True
    except OSError:
        return False


def ensure_private_directory(path: str) -> None:
    """Create *path* and restrict it to the current user where supported."""
    os.makedirs(path, mode=0o700, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass


def restrict_private_file(path: str) -> None:
    """Restrict an existing user-data file to the current user if possible."""
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


_CONFIG_PATH = os.path.join(app_config_dir(), "availability.json")

# In-process source of truth: {"albums": set[str], "artists": set[str]}.
# ``None`` until the first access, then loaded from disk once.
_state: dict | None = None


def reload() -> None:
    """Forget the in-process cache after a configuration import."""
    global _state
    _state = None


def _norm(path: str) -> str:
    """Normalise a path to the canonical key form used for storage/lookup.

    ``abspath`` + ``normpath`` collapse trailing separators, ``..`` segments
    and relative paths so the same folder maps to one key whether it arrives
    from drag-and-drop, a file dialog, or ``os.path.join(root, name)``.
    Symlinks are deliberately *not* resolved (no ``realpath``) so the key
    matches the path the user actually sees and supplies.
    """
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def _ensure_loaded() -> None:
    global _state
    if _state is not None:
        return
    albums: set[str] = set()
    artists: set[str] = set()
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            albums = {
                _norm(p) for p in data.get("albums", []) if isinstance(p, str)
            }
            artists = {
                _norm(p) for p in data.get("artists", []) if isinstance(p, str)
            }
    except (OSError, ValueError):
        # Missing or corrupt file → start empty.  Persistence is a
        # convenience; a read-only / malformed config must not break the GUI.
        pass
    _state = {"albums": albums, "artists": artists}


def _save() -> None:
    """Atomically persist the current state (errors swallowed)."""
    _ensure_loaded()
    assert _state is not None
    try:
        ensure_private_directory(os.path.dirname(_CONFIG_PATH))
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "albums": sorted(_state["albums"]),
                    "artists": sorted(_state["artists"]),
                },
                f, ensure_ascii=False, indent=2,
            )
        restrict_private_file(tmp)
        os.replace(tmp, _CONFIG_PATH)
        restrict_private_file(_CONFIG_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def is_album_unavailable(path: str) -> bool:
    _ensure_loaded()
    assert _state is not None
    return _norm(path) in _state["albums"]


def is_artist_unavailable(path: str) -> bool:
    _ensure_loaded()
    assert _state is not None
    return _norm(path) in _state["artists"]


def album_set() -> set[str]:
    """Return a *copy* of the unavailable-album key set."""
    _ensure_loaded()
    assert _state is not None
    return set(_state["albums"])


def artist_set() -> set[str]:
    """Return a *copy* of the unavailable-artist key set."""
    _ensure_loaded()
    assert _state is not None
    return set(_state["artists"])


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def _apply(bucket: str, paths, flag: bool) -> bool:
    """Add/remove ``paths`` in ``_state[bucket]``; persist once if anything
    changed.  Returns whether the set changed."""
    _ensure_loaded()
    assert _state is not None
    target = _state[bucket]
    changed = False
    for path in paths:
        key = _norm(path)
        present = key in target
        if flag and not present:
            target.add(key)
            changed = True
        elif not flag and present:
            target.discard(key)
            changed = True
    if changed:
        _save()
    return changed


def set_album(path: str, flag: bool) -> bool:
    """Mark/unmark a single album as unavailable.  Returns whether changed."""
    return _apply("albums", (path,), flag)


def set_artist(path: str, flag: bool) -> bool:
    """Mark/unmark a single artist as unavailable.  Returns whether changed."""
    return _apply("artists", (path,), flag)


def set_albums(paths, flag: bool) -> bool:
    """Bulk mark/unmark albums (one save for the whole batch)."""
    return _apply("albums", paths, flag)


def set_artists(paths, flag: bool) -> bool:
    """Bulk mark/unmark artists (one save for the whole batch)."""
    return _apply("artists", paths, flag)
