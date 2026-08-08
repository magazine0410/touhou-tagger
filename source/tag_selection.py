"""Shared, Qt-free model for Wiki Tagger output-tag selection.

The ordered keys are used for preference storage, the Settings dialog, and
stable log output.  Keep this module free of project imports so both the GUI
and the local tagging pipeline can depend on it without creating a cycle.
"""
from __future__ import annotations

from collections.abc import Iterable


WIKI_TAGS: tuple[str, ...] = (
    "grouping",
    "album",
    "albumartist",
    "albumartistsort",
    "catalognumber",
    "date",
    "year",
    "genre",
    "arranger",
    "vocalist",
    "lyricist",
    "artist",
    "artistsort",
    "titlesort",
)
WIKI_TAG_SET = frozenset(WIKI_TAGS)

WIKI_TAG_LABELS: dict[str, str] = {
    "grouping": "Grouping",
    "album": "Album",
    "albumartist": "Album Artist",
    "albumartistsort": "Album Artist Sort",
    "catalognumber": "Catalog Number",
    "date": "Date",
    "year": "Year",
    "genre": "Genre",
    "arranger": "Arranger",
    "vocalist": "Vocalist",
    "lyricist": "Lyricist",
    "artist": "Artist",
    "artistsort": "Artist Sort",
    "titlesort": "Title Sort",
}


def normalize_selected_tags(tags: Iterable[object] | None) -> tuple[str, ...]:
    """Return known tags in canonical order, or ``()`` for invalid input.

    Preference files are JSON, so a valid persisted selection must be a list
    or tuple of strings.  Other callers may pass a set or other iterable; an
    empty result deliberately represents no valid selection and lets the
    preference layer restore its all-tags default.
    """
    if tags is None or isinstance(tags, (str, bytes, dict)):
        return ()
    try:
        selected = set(tags)
    except TypeError:
        return ()
    if not all(isinstance(tag, str) for tag in selected):
        return ()
    return tuple(tag for tag in WIKI_TAGS if tag in selected)


def format_tag_selection(tags: Iterable[object] | None) -> str:
    """Return the stable, user-visible tag-selection log line."""
    selected = normalize_selected_tags(tags)
    return "Tag selection: " + (", ".join(selected) or "(none)")
