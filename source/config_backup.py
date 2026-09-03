"""Cookie-free configuration export/import for the standalone tagger.

The backup format is an explicit allow-list rather than a dump of the whole
configuration directory.  In particular, Cookie headers are never exported
and are ignored if they appear in a hand-edited import file.  It can contain
local library, album, and executable paths, so it should be reviewed before
sharing publicly.
"""
from __future__ import annotations

import json
import os

import availability
import preferences


FORMAT_VERSION = 1
_AUTH_FIELDS = {"user_agent", "impersonate", "browser", "auto_pull"}


def _path(name: str) -> str:
    return os.path.join(availability.app_config_dir(), name)


def _read(name: str) -> dict:
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _safe_auth() -> dict:
    raw = _read("auth.json")
    if "thwiki" not in raw:
        legacy = _read("thwiki_auth.json")
        if legacy:
            raw["thwiki"] = legacy
    result = {}
    for site, data in raw.items():
        if site != "thwiki" or not isinstance(data, dict):
            continue
        result[site] = {
            key: data[key] for key in _AUTH_FIELDS if key in data
        }
    return result


def build_payload() -> dict:
    """Return only the documented, non-secret preferences."""
    tools = _read("external_tools.json")
    overrides = tools.get("overrides", {})
    if not isinstance(overrides, dict):
        overrides = {}
    overrides = {
        str(name): str(path) for name, path in overrides.items()
        if isinstance(name, str) and isinstance(path, str) and path.strip()
    }
    albums = _read("album_overrides.json").get("slugs", {})
    if not isinstance(albums, dict):
        albums = {}
    albums = {
        str(path): str(slug) for path, slug in albums.items()
        if isinstance(path, str) and isinstance(slug, str) and slug.strip()
    }
    locks = _read("tag_locks.json").get("locks", {})
    if not isinstance(locks, dict):
        locks = {}
    locks = {
        str(path): sorted(
            t for t in tags if isinstance(t, str) and t.strip()
        )
        for path, tags in locks.items()
        if isinstance(path, str) and isinstance(tags, list)
    }
    locks = {path: tags for path, tags in locks.items() if tags}
    unavailable = _read("availability.json")
    stats = _read("stats.json")
    return {
        "format": FORMAT_VERSION,
        "application": "touhou_tagger",
        "preferences": preferences.load(),
        "auth": _safe_auth(),
        "external_tools": {"overrides": overrides},
        "album_overrides": {"slugs": albums},
        "tag_locks": {"locks": locks},
        "availability": {
            "albums": unavailable.get("albums", [])
            if isinstance(unavailable.get("albums", []), list) else [],
            "artists": unavailable.get("artists", [])
            if isinstance(unavailable.get("artists", []), list) else [],
        },
        "statistics": {
            "library_root": stats.get("library_root", "")
            if isinstance(stats.get("library_root", ""), str) else "",
        },
    }


def export_file(path: str) -> None:
    """Write a UTF-8 JSON backup to *path*."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_payload(), f, ensure_ascii=False, indent=2)


def _write(name: str, data: dict) -> None:
    availability.ensure_private_directory(availability.app_config_dir())
    target = _path(name)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    availability.restrict_private_file(tmp)
    os.replace(tmp, target)
    availability.restrict_private_file(target)


def import_file(path: str) -> list[str]:
    """Import allow-listed settings and return a human-readable change list."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict) or raw.get("format") != FORMAT_VERSION:
        raise ValueError("Unsupported or invalid Touhou Tagger backup format.")
    changed: list[str] = []
    prefs = raw.get("preferences")
    if isinstance(prefs, dict):
        if not preferences.save(prefs):
            raise OSError("Could not save imported preferences.")
        changed.append("general preferences")
    auth = raw.get("auth")
    if isinstance(auth, dict):
        clean_auth = {}
        for site, data in auth.items():
            if site == "thwiki" and isinstance(data, dict):
                clean_auth[site] = {
                    key: data[key] for key in _AUTH_FIELDS if key in data
                }
        _write("auth.json", clean_auth)
        changed.append("browser authentication preferences (cookies excluded)")
    tools = raw.get("external_tools")
    if isinstance(tools, dict):
        overrides = tools.get("overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        _write("external_tools.json", {"overrides": {
            str(k): str(v) for k, v in overrides.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }})
        changed.append("external-tool paths")
    albums = raw.get("album_overrides")
    if isinstance(albums, dict):
        slugs = albums.get("slugs", {})
        if not isinstance(slugs, dict):
            slugs = {}
        _write("album_overrides.json", {"slugs": {
            str(k): str(v) for k, v in slugs.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }})
        changed.append("album identity overrides")
    locks = raw.get("tag_locks")
    if isinstance(locks, dict):
        entries = locks.get("locks", {})
        if not isinstance(entries, dict):
            entries = {}
        clean = {}
        for path, tags in entries.items():
            if not isinstance(path, str) or not isinstance(tags, list):
                continue
            names = sorted({
                t.strip() for t in tags if isinstance(t, str) and t.strip()
            })
            if names:
                clean[path] = names
        _write("tag_locks.json", {"locks": clean})
        changed.append("manual tag locks")
    unavailable = raw.get("availability")
    if isinstance(unavailable, dict):
        _write("availability.json", {
            "albums": [x for x in unavailable.get("albums", [])
                       if isinstance(x, str)],
            "artists": [x for x in unavailable.get("artists", [])
                        if isinstance(x, str)],
        })
        changed.append("unavailable-folder marks")
    stats = raw.get("statistics")
    if isinstance(stats, dict):
        _write("stats.json", {
            "library_root": stats.get("library_root", "")
            if isinstance(stats.get("library_root", ""), str) else "",
        })
        changed.append("Statistics library location")
    return changed
