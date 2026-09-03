"""Persistent per-file tag locks used by the GUI.

A lock records that the user set a tag by hand and that the Wiki Tagger must
never change it again.  Locks are keyed by the same normalised absolute path
convention used by :mod:`availability`, so a file reached through drag-and-drop
and the same file found by a folder scan share one entry.  This module is
deliberately independent of Qt, network and mutagen code.

Tag names are stored verbatim: they are only ever used in ``tag in set`` tests,
so an unknown or future name is inert rather than an error, and the file needs
no migration when the editable-tag vocabulary grows.  Validating against
:data:`tag_io.EDITABLE_TAGS` would drag mutagen into a configuration leaf.

Locks are path-keyed, so renaming or moving a file orphans its locks — the same
accepted limitation :mod:`availability` and :mod:`album_overrides` have.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable

import availability


_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "tag_locks.json",
)
# Values are frozensets, not sets: the Wiki Tagger worker thread reads
# locked_tags() while the GUI thread writes from a padlock click, and replacing
# a whole frozenset can never expose a half-mutated value to the reader.
_state: dict[str, frozenset[str]] | None = None


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
    locks: dict[str, frozenset[str]] = {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("locks", {}) if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            for path, tags in raw.items():
                if not isinstance(path, str) or not isinstance(tags, list):
                    continue
                names = frozenset(
                    t.strip() for t in tags
                    if isinstance(t, str) and t.strip()
                )
                if names:
                    locks[availability._norm(path)] = names
    except (OSError, ValueError):
        # Missing or corrupt file → start empty.  Persistence is a
        # convenience; a read-only / malformed config must not break the GUI.
        pass
    _state = locks


def _save() -> None:
    """Atomically persist the current state (errors swallowed)."""
    _ensure_loaded()
    assert _state is not None
    try:
        availability.ensure_private_directory(os.path.dirname(_CONFIG_PATH))
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "locks": {
                        path: sorted(tags)
                        for path, tags in sorted(_state.items())
                    },
                },
                f, ensure_ascii=False, indent=2,
            )
        availability.restrict_private_file(tmp)
        os.replace(tmp, _CONFIG_PATH)
        availability.restrict_private_file(_CONFIG_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def locked_tags(path: str) -> frozenset[str]:
    """Return the tag names locked on *path* (empty when none are)."""
    _ensure_loaded()
    assert _state is not None
    return _state.get(availability._norm(path), frozenset())


def is_locked(path: str, tag: str) -> bool:
    """True when *tag* is locked on *path*."""
    return tag in locked_tags(path)


def locked_files() -> list[str]:
    """Every path that currently holds at least one lock."""
    _ensure_loaded()
    assert _state is not None
    return sorted(_state)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def set_locks(items: Iterable[tuple[str, str]], flag: bool) -> bool:
    """Lock/unlock ``(path, tag)`` pairs; persist once if anything changed.

    Pairs rather than a paths x tags product because that is the shape the Tag
    Edit tab's dirty set already has.  Returns whether the state changed.
    """
    _ensure_loaded()
    assert _state is not None
    changed = False
    for path, tag in items:
        tag = tag.strip()
        if not tag:
            continue
        key = availability._norm(path)
        current = _state.get(key, frozenset())
        if flag:
            updated = current | {tag}
        else:
            updated = current - {tag}
        if updated == current:
            continue
        if updated:
            _state[key] = updated
        else:
            del _state[key]
        changed = True
    if changed:
        _save()
    return changed


def set_lock(path: str, tag: str, flag: bool) -> bool:
    """Lock/unlock a single tag on a single file.  Returns whether changed."""
    return set_locks(((path, tag),), flag)


def clear_file(path: str) -> bool:
    """Remove every lock on *path*.  Returns whether anything was removed."""
    _ensure_loaded()
    assert _state is not None
    key = availability._norm(path)
    if key not in _state:
        return False
    del _state[key]
    _save()
    return True


def prune_missing() -> int:
    """Drop locks for files that no longer exist.  Returns how many went.

    An entry whose *parent directory* is also missing is deliberately kept: the
    music library may live on a removable or network mount, and an unmounted
    drive must never silently erase the record of every hand edit.  Never call
    this automatically — it is an explicit user action.
    """
    _ensure_loaded()
    assert _state is not None
    stale = [
        path for path in _state
        if not os.path.exists(path) and os.path.isdir(os.path.dirname(path))
    ]
    for path in stale:
        del _state[path]
    if stale:
        _save()
    return len(stale)
