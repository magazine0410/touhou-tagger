"""
theme_mapping.py — Translate original theme names from Japanese to English
using the mapping built by build_theme_mapping.py, and inherit original
titles for variant tracks (instrumental, off-vocal, etc.).
"""
import json
import os
import re
import unicodedata
from collections import defaultdict


# ---------------------------------------------------------------------------
# Variant suffix detection
# ---------------------------------------------------------------------------
# Variant descriptors that indicate a track is a version of another track
# (instrumental, piano version, off-vocal, separate, etc.).
_VARIANT_WORDS = (
    r'(?:'
    r'instrumental|inst\.?'
    r'|off[\s\-]*vo(?:cal)?\.?'
    r'|karaoke'
    r'|backing[\s\-]*track'
    r'|(?:piano(?:\s*&\s*vocal)?|vocal)\s*(?:ver(?:sion)?\.?)'
    r'|separate'
    r')'
)
# Matches variant suffixes in track titles regardless of delimiter style.
# Handles parenthesized "(instrumental)", bracketed "[off vocal]",
# full-width "（inst）", and dash-delimited "- Piano Ver. -" or
# "-separate-" forms (space after the leading dash is optional).
# Used to group variant tracks together so that original titles can be
# inherited from whichever variant has them in the wiki's semantic data.
_VARIANT_SUFFIX_RE = re.compile(
    r'(?:'
    # Parenthesized / bracketed
    r'\s*[(\[（]\s*' + _VARIANT_WORDS + r'\s*[)\]）]'
    r'|'
    # Dash-delimited (e.g. "- Piano Ver. -", "-separate-")
    r'\s+-\s*' + _VARIANT_WORDS + r'\s*-?'
    r')\s*$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Title normalization (used for matching)
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    """Fold to a comparison key: NFKC, lowercase, strip, collapse whitespace.

    NFKC folds compatibility-equivalent characters — full-width Latin/digits/
    punctuation to their ASCII forms, the full-width tilde ``～`` (U+FF5E) to
    ``~``, the ideographic space ``　`` (U+3000) to a normal space, etc. — which
    are pure typography/encoding differences common in Touhou titles (e.g.
    ``彼岸帰航　～ Riverside View``) and never semantic.  It does **not** merge
    genuinely different punctuation (a trailing ``?`` or ``!!`` is preserved),
    so distinct titles stay distinct.  Mirrors the ``NFKC`` fold TouhouDB
    already uses for its name matching.
    """
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).lower().strip())


# ---------------------------------------------------------------------------
# Theme mapping
# ---------------------------------------------------------------------------
def _normalize_for_mapping(s: str) -> str:
    """
    Normalize a theme name for mapping lookup (mirrors build_theme_mapping.py).

    Collapses whitespace variants, normalizes tilde glyphs (～/〜) and
    spacing around them, folds case, normalizes fullwidth punctuation, and
    strips trailing periods so that
    THBWiki variants like ``永夜抄　～ Eastern Night.`` match the canonical
    ``永夜抄　～ Eastern Night`` entry.  Themes whose canonical name does
    end in '.' or '...' still match correctly because the normalization
    is applied symmetrically to both sides of the lookup.
    """
    s = re.sub(r'[\s\u3000\u2002-\u200b]+', ' ', s.strip())
    s = s.replace('\uff5e', '~').replace('\u301c', '~')
    s = re.sub(r'\s*~\s*', ' ~ ', s)
    s = s.replace('\uff0c', ',').replace('\uff1f', '?').replace('\uff01', '!')
    s = s.rstrip('.')
    return s.casefold()


def load_theme_mapping(mapping_path: str | None) -> dict | None:
    """
    Load the theme mapping JSON file.  Returns the parsed data dict
    or None if the file doesn't exist or can't be loaded.
    If mapping_path is None, looks for 'touhou_theme_mapping.json' in
    the same directory as this script.

    The ``normalized_keys`` table is rebuilt from the primary ``mapping``
    plus every named entry under ``sections`` using this module's current
    ``_normalize_for_mapping`` function.  The merged mapping is exposed as
    ``mapping`` at runtime for compatibility with existing consumers, while
    the source JSON keeps Len'en and Seihou physically separate.
    """
    if mapping_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mapping_path = os.path.join(script_dir, "touhou_theme_mapping.json")

    if not os.path.isfile(mapping_path):
        return None

    try:
        with open(mapping_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not load theme mapping: {exc}")
        return None

    # Merge named sections and re-derive normalized_keys so this script's
    # _normalize_for_mapping is the single source of truth.  Earlier
    # entries win on collision, matching build_theme_mapping.py's
    # "first occurrence wins" behaviour.
    mapping = dict(data.get("mapping", {}))
    sections = data.get("sections", {})
    if isinstance(sections, dict):
        for section in sections.values():
            if not isinstance(section, dict):
                continue
            section_mapping = section.get("mapping", {})
            if not isinstance(section_mapping, dict):
                continue
            for canonical, english in section_mapping.items():
                mapping.setdefault(canonical, english)
    data["mapping"] = mapping
    norm_keys: dict[str, str] = {}
    for canonical in mapping:
        nk = _normalize_for_mapping(canonical)
        norm_keys.setdefault(nk, canonical)
    data["normalized_keys"] = norm_keys

    return data


def translate_titles(
    tracks: list[dict],
    mapping_data: dict | None,
) -> list[dict]:
    """
    Translate original_titles from Japanese to English using the
    theme mapping.  Modifies the tracks in place and returns them.
    If no mapping is available, titles are left as-is (Japanese/mixed).
    """
    if mapping_data is None:
        return tracks

    for track in tracks:
        track["original_titles"] = [
            translate_title(title, mapping_data)
            for title in track["original_titles"]
        ]

    return tracks


def translate_title(title: str, mapping_data: dict | None) -> str:
    """Return the canonical English mapping for one theme title, if known."""
    if mapping_data is None:
        return title

    mapping = mapping_data.get("mapping", {})
    norm_keys = mapping_data.get("normalized_keys", {})
    raw_key = norm_keys.get(_normalize_for_mapping(title))
    return mapping.get(raw_key, title) if raw_key else title


def _inherit_instrumental_titles(tracks: list[dict]) -> list[dict]:
    """
    Fill in missing ``original_titles`` for variant tracks (instrumental,
    piano version, off-vocal, etc.) by copying from another variant of
    the same song that *does* have original titles.
    THBWiki's semantic store sometimes lacks ``ogmusicname`` for certain
    track variants even when the rendered wiki page shows the data.
    This heuristic strips known variant suffixes (parenthesized like
    "(instrumental)" or dash-delimited like "- Piano Ver. -") to get a
    base title, groups tracks that share the same base, and propagates
    original titles from any track in the group that has them to those
    that don't.
    Modifies the tracks in place and returns them.
    """
    # Group tracks by their normalized base title (suffix stripped)
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in tracks:
        if not t["title"]:
            continue
        base = _VARIANT_SUFFIX_RE.sub("", t["title"])
        groups[normalize(base)].append(t)

    inherited = 0
    for base_title, group in groups.items():
        if len(group) < 2:
            continue

        # Find a donor: the first track in the group with original_titles
        donor_titles = None
        for t in group:
            if t["original_titles"]:
                donor_titles = t["original_titles"]
                break
        if donor_titles is None:
            continue

        # Copy to every track in the group that's missing them
        for t in group:
            if not t["original_titles"]:
                t["original_titles"] = list(donor_titles)
                inherited += 1

    if inherited:
        print(f"  Inherited original titles for {inherited} "
              f"variant track(s)")
    return tracks
