"""Persistent per-album identity overrides used by the GUI.

Only the reviewed Wiki Slug is stored.  The mapping is keyed by the same
normalised absolute path convention used by :mod:`availability`, so a folder
selected through a dialog and the same folder found during a refresh share one
override.  This module is deliberately independent of Qt and network code.
"""
from __future__ import annotations

import json
import os

import availability


_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "album_overrides.json",
)
_state: dict[str, str] | None = None


def reload() -> None:
    """Forget the in-process cache after a configuration import."""
    global _state
    _state = None


def config_path() -> str:
    return _CONFIG_PATH


def _ensure_loaded() -> None:
    global _state
    if _state is not None:
        return
    overrides: dict[str, str] = {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("slugs", {}) if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            for path, slug in raw.items():
                if isinstance(path, str) and isinstance(slug, str):
                    path = availability._norm(path)
                    slug = slug.strip()
                    if slug:
                        overrides[path] = slug
    except (OSError, ValueError):
        pass
    _state = overrides


def _save() -> None:
    _ensure_loaded()
    assert _state is not None
    try:
        availability.ensure_private_directory(os.path.dirname(_CONFIG_PATH))
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"slugs": dict(sorted(_state.items()))},
                f, ensure_ascii=False, indent=2,
            )
        availability.restrict_private_file(tmp)
        os.replace(tmp, _CONFIG_PATH)
        availability.restrict_private_file(_CONFIG_PATH)
    except OSError:
        pass


def get_slug(path: str) -> str:
    """Return the saved Wiki Slug override for *path*, or ``""``."""
    _ensure_loaded()
    assert _state is not None
    return _state.get(availability._norm(path), "")


def set_slug(path: str, slug: str) -> bool:
    """Store a non-empty reviewed Wiki Slug for *path*."""
    value = slug.strip()
    if not value:
        return clear_slug(path)
    _ensure_loaded()
    assert _state is not None
    key = availability._norm(path)
    changed = _state.get(key) != value
    _state[key] = value
    if changed:
        _save()
    return changed


def clear_slug(path: str) -> bool:
    """Remove a saved Wiki Slug override for *path*."""
    _ensure_loaded()
    assert _state is not None
    key = availability._norm(path)
    if key not in _state:
        return False
    del _state[key]
    _save()
    return True
