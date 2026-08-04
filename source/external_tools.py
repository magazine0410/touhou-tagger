"""Persistent executable discovery and diagnostics for the standalone tagger.

The tagger deliberately keeps its external-command dependencies small, but a
new machine may have them installed outside ``PATH`` (especially on Windows).
This leaf module centralises discovery and stores only user-selected
executable paths; it never stores credentials or command output.
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any

import availability


_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "external_tools.json",
)


# ``aliases`` are tried in order when no explicit override is configured.
# The feature text is intentionally user-facing: it is shown in the GUI's
# diagnostics dialog next to the tool status.
TOOL_SPECS: dict[str, dict[str, Any]] = {
    "curl": {
        "label": "curl",
        "aliases": ("curl",),
        "features": "THBWiki asktrack and TouhouDB HTTP requests",
    },
    "ffmpeg": {
        "label": "FFmpeg",
        "aliases": ("ffmpeg",),
        "features": "CUE image splitting",
    },
    "flac": {
        "label": "FLAC",
        "aliases": ("flac",),
        "features": "CUE split verification",
    },
    "metaflac": {
        "label": "metaflac",
        "aliases": ("metaflac",),
        "features": "Embedded CUESHEET detection",
    },
    "gio": {
        "label": "gio",
        "aliases": ("gio",),
        "features": "Move verified CUE originals to Trash (first fallback)",
    },
    "trash-put": {
        "label": "trash-put",
        "aliases": ("trash-put",),
        "features": "Move verified CUE originals to Trash (fallback)",
    },
    "kioclient": {
        "label": "KDE kioclient",
        "aliases": ("kioclient5", "kioclient"),
        "features": "Move verified CUE originals to Trash (fallback)",
    },
}

_ALIASES = {
    alias: tool_id
    for tool_id, spec in TOOL_SPECS.items()
    for alias in spec["aliases"]
}

_state: dict[str, dict[str, str]] | None = None


def reload() -> None:
    """Forget the in-process cache after a configuration import."""
    global _state
    _state = None


def config_path() -> str:
    """Return the private configuration path used for executable overrides."""
    return _CONFIG_PATH


def _tool_id(name: str) -> str:
    key = str(name).strip().lower()
    if key in TOOL_SPECS:
        return key
    return _ALIASES.get(key, key)


def _ensure_loaded() -> None:
    global _state
    if _state is not None:
        return
    overrides: dict[str, str] = {}
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("overrides", {}) if isinstance(data, dict) else {}
        if isinstance(raw, dict):
            for name, path in raw.items():
                tool_id = _tool_id(name)
                if tool_id in TOOL_SPECS and isinstance(path, str):
                    path = path.strip()
                    if path:
                        overrides[tool_id] = os.path.abspath(
                            os.path.expanduser(path)
                        )
    except (OSError, ValueError):
        pass
    _state = {"overrides": overrides}


def _save() -> None:
    _ensure_loaded()
    assert _state is not None
    try:
        availability.ensure_private_directory(os.path.dirname(_CONFIG_PATH))
        tmp = _CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"overrides": dict(sorted(_state["overrides"].items()))},
                f, ensure_ascii=False, indent=2,
            )
        availability.restrict_private_file(tmp)
        os.replace(tmp, _CONFIG_PATH)
        availability.restrict_private_file(_CONFIG_PATH)
    except OSError:
        # A read-only installation should still be able to use PATH tools.
        pass


def configured_path(name: str) -> str:
    """Return the saved override for *name*, or an empty string."""
    _ensure_loaded()
    assert _state is not None
    return _state["overrides"].get(_tool_id(name), "")


def set_override(name: str, path: str) -> bool:
    """Save an executable override; an empty path clears it.

    Returns ``False`` for an unknown tool and ``True`` when the known tool's
    stored value is updated (including clearing an existing value).
    """
    tool_id = _tool_id(name)
    if tool_id not in TOOL_SPECS:
        return False
    _ensure_loaded()
    assert _state is not None
    value = os.path.abspath(os.path.expanduser(path.strip())) if path else ""
    if value:
        _state["overrides"][tool_id] = value
    else:
        _state["overrides"].pop(tool_id, None)
    _save()
    return True


def _is_executable(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    # Windows uses file extensions rather than POSIX executable bits.
    return os.name == "nt" or os.access(path, os.X_OK)


def resolve_tool(name: str) -> str | None:
    """Resolve a tool using its saved override, then its PATH aliases.

    A configured-but-missing override intentionally does not fall back to
    PATH: the diagnostics dialog should make a broken explicit choice visible
    instead of silently running a different binary.
    """
    tool_id = _tool_id(name)
    spec = TOOL_SPECS.get(tool_id)
    if spec is None:
        return shutil.which(name)
    override = configured_path(tool_id)
    if override:
        return override if _is_executable(override) else None
    for alias in spec["aliases"]:
        found = shutil.which(alias)
        if found:
            return found
    return None


def describe(name: str) -> dict[str, str]:
    """Return non-sensitive status information suitable for a GUI."""
    tool_id = _tool_id(name)
    spec = TOOL_SPECS[tool_id]
    override = configured_path(tool_id)
    path = resolve_tool(tool_id)
    if override and not _is_executable(override):
        status = "configured path missing or not executable"
    elif path:
        status = "available"
    else:
        status = "not found"
    return {
        "id": tool_id,
        "label": spec["label"],
        "features": spec["features"],
        "override": override,
        "path": path or "",
        "status": status,
    }


def diagnostics() -> list[dict[str, str]]:
    """Return statuses for every command known to the standalone tagger."""
    return [describe(tool_id) for tool_id in TOOL_SPECS]
