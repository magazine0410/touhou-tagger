"""Single source of the application version.

The canonical version lives in the repository-root ``VERSION`` file (see
``docs/RELEASING.md``); this leaf module reads it once at import so every other
module — the CLI ``--version`` flag, the log header, and the outgoing
User-Agent strings — reports the same value without duplicating it.

Leaf module: imports only the standard library, so any module (including the
otherwise import-free ``touhou_wiki.py`` / ``touhoudb.py``) can use it without
creating an import cycle.
"""
import os

# repo root is one level up from this file's directory (source/).
_VERSION_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"
)

# Fallback used only if the VERSION file is missing/unreadable (e.g. an
# unusual packaging layout); the file is the source of truth otherwise.
_FALLBACK_VERSION = "0.0.0"


def get_version() -> str:
    """Return the version string from the root VERSION file (stripped)."""
    try:
        with open(_VERSION_FILE, encoding="utf-8") as fh:
            value = fh.read().strip()
        return value or _FALLBACK_VERSION
    except OSError:
        return _FALLBACK_VERSION


#: Resolved once at import; ``x.y.z`` on a normal checkout.
__version__ = get_version()

#: Shared outgoing User-Agent for the wiki/TouhouDB HTTP clients.  Reflects the
#: real project name and version so remote sites can identify the traffic.
USER_AGENT = f"TouhouTagger/{__version__} (personal music tagging project)"
