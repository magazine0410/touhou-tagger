"""Small, non-secret GUI preferences shared by the standalone tagger.

This module intentionally stores only user choices: folder-expansion depth,
CUE post-processing, Wiki Tagger output fields, and a little window state.
Browser cookies and other session credentials do not belong here.
"""
from __future__ import annotations

import json
import os

import availability
from tag_selection import WIKI_TAGS, normalize_selected_tags


DEFAULTS = {
    "scan_depth": 1,
    "cue_post_processing": "trash",
    # All fields stay selected for an existing/first-run installation so the
    # new picker preserves the Wiki Tagger's historical behaviour.
    "wiki_tag_selection": list(WIKI_TAGS),
    "gui": {"width": 1120, "height": 620, "last_tab": 0},
}
SCAN_DEPTHS = (1, 2, 3)
CUE_POST_PROCESSING = ("trash", "keep", "ask")


def config_path() -> str:
    return os.path.join(availability.app_config_dir(), "preferences.json")


def _copy_defaults() -> dict:
    return {
        "scan_depth": DEFAULTS["scan_depth"],
        "cue_post_processing": DEFAULTS["cue_post_processing"],
        "wiki_tag_selection": list(DEFAULTS["wiki_tag_selection"]),
        "gui": dict(DEFAULTS["gui"]),
    }


def load() -> dict:
    result = _copy_defaults()
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return result
    if not isinstance(raw, dict):
        return result
    try:
        depth = int(raw.get("scan_depth", result["scan_depth"]))
    except (TypeError, ValueError):
        depth = result["scan_depth"]
    if depth in SCAN_DEPTHS:
        result["scan_depth"] = depth
    policy = str(raw.get("cue_post_processing", "")).strip().lower()
    if policy in CUE_POST_PROCESSING:
        result["cue_post_processing"] = policy
    selected_tags = normalize_selected_tags(raw.get("wiki_tag_selection"))
    if selected_tags:
        result["wiki_tag_selection"] = list(selected_tags)
    gui = raw.get("gui")
    if isinstance(gui, dict):
        for key in ("width", "height", "last_tab"):
            try:
                value = int(gui.get(key, result["gui"][key]))
            except (TypeError, ValueError):
                continue
            if key == "last_tab":
                result["gui"][key] = max(0, value)
            elif value >= 400:
                result["gui"][key] = value
    return result


def save(data: dict) -> bool:
    """Validate and atomically save the known preference fields."""
    current = _copy_defaults()
    if isinstance(data, dict):
        current.update({
            "scan_depth": data.get("scan_depth", current["scan_depth"]),
            "cue_post_processing": data.get(
                "cue_post_processing", current["cue_post_processing"]
            ),
            "wiki_tag_selection": data.get(
                "wiki_tag_selection", current["wiki_tag_selection"]
            ),
            "gui": data.get("gui", current["gui"]),
        })
    clean = load()
    try:
        depth = int(current["scan_depth"])
        if depth in SCAN_DEPTHS:
            clean["scan_depth"] = depth
    except (TypeError, ValueError):
        pass
    policy = str(current["cue_post_processing"]).strip().lower()
    if policy in CUE_POST_PROCESSING:
        clean["cue_post_processing"] = policy
    selected_tags = normalize_selected_tags(current["wiki_tag_selection"])
    if selected_tags:
        clean["wiki_tag_selection"] = list(selected_tags)
    if isinstance(current.get("gui"), dict):
        for key in ("width", "height", "last_tab"):
            if key in current["gui"]:
                try:
                    value = int(current["gui"][key])
                except (TypeError, ValueError):
                    continue
                if key == "last_tab" and value >= 0:
                    clean["gui"][key] = value
                elif key != "last_tab" and value >= 400:
                    clean["gui"][key] = value
    try:
        availability.ensure_private_directory(os.path.dirname(config_path()))
        tmp = config_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
        availability.restrict_private_file(tmp)
        os.replace(tmp, config_path())
        availability.restrict_private_file(config_path())
        return True
    except OSError:
        return False


def update(**values) -> dict:
    data = load()
    data.update(values)
    save(data)
    return load()


def scan_depth() -> int:
    return int(load()["scan_depth"])


def cue_post_processing() -> str:
    return str(load()["cue_post_processing"])


def wiki_tag_selection() -> tuple[str, ...]:
    """Return the persisted Wiki Tagger output fields in display order."""
    return tuple(load()["wiki_tag_selection"])
