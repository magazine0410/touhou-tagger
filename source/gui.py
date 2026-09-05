"""
gui.py — PyQt5 GUI for interactive Touhou album tagging, romanisation,
and manual tag editing.

Launched when touhou_tagger.py is run with no CLI arguments.  Provides
drag-and-drop album loading, editable wiki slugs, a log pane, a
standalone romanisation tab, and a tag-editing tab for manual corrections.
"""
import json
import logging
import os
import sys
import threading
import traceback

# Faint translucent-yellow RGBA used to tint a changed/discrepant value
# (overwrites in the Summary "Changes" tab; disagreeing cells in the
# severe-mismatch confirmation dialog).  Built into a QtGui.QColor at each use
# site since PyQt5 is only imported inside gui_main().
_YELLOW_TINT_RGBA = (255, 220, 50, 55)

from touhou_tagger import (
    _setup_gui_logging,
    process_albums,
    ThwikiCookieError,
    ROMANIZER_AVAILABLE,
    ROMANIZER_IMPORT_OK,
    PYKAKASI_HINT_NEEDED,
    japanese_romanizer,
    LOGGER_NAME,
    _MAX_LOG_FILES,
)
from file_scan import (
    guess_album_slug,
    guess_album_artist,
    _expand_to_album_dirs,
    scan_album_for_view,
    _format_track_label,
    _format_track_number,
    scan_music_files,
    album_dir_for_file,
    SUPPORTED_EXTENSIONS,
)
from tag_io import (
    EDITABLE_TAGS,
    read_all_tags,
    read_genres,
    _set_tag,
    _delete_tag,
)
from theme_mapping import normalize
# GENRE_TRANSLATIONS-derived vocabulary for the "Skip genre-tagged on add"
# option.  thwiki is already loaded via touhou_tagger's import chain, so this
# adds no new dependency and creates no cycle (thwiki never imports gui).
from thwiki import tagger_genre_vocabulary

# Persistent "unavailable on the wikis" marks, shared with the Statistics tab.
# Qt-free leaf module (like browser_cookie), safe to import at gui.py's top.
import availability
import album_overrides
import external_tools
import preferences
import tag_locks
import config_backup
from tag_selection import (
    STAFF_TAGS as _STAFF_TAGS,
    WIKI_TAGS,
    WIKI_TAG_LABELS,
    format_tag_selection,
)

_FORCE_CREDITS_TOOLTIP = (
    "Replace existing 'arranger', 'vocalist', and 'lyricist' tags with "
    "the wiki's credits.  Default is to preserve them, which means a "
    "re-run cannot correct a credit an earlier release wrote.  A credit "
    "the wiki already agrees with is left alone either way."
)

# Optional helper that pulls the live THBWiki cookie from a local browser so it
# doesn't have to be pasted by hand.  Soft import: absent => manual paste only.
try:
    import browser_cookie as _browser_cookie
except ImportError:
    _browser_cookie = None

# Optional helper that splits an un-split whole-album FLAC image via its CUE.
# Qt-free leaf module; soft import so the GUI still works if it's absent (the
# mismatch dialog's "Split via CUE sheet" button is simply hidden).
try:
    import cue_split as _cue_split
except ImportError:
    _cue_split = None
if _cue_split is not None:
    _cue_split.set_tool_resolver(external_tools.resolve_tool)


# ---------------------------------------------------------------------------
# Browser authentication configuration persistence
# ---------------------------------------------------------------------------
# THBWiki reads its active cookie from the process environment.  Cookies are
# deliberately excluded from this file; browser choice, auto-pull preference,
# User-Agent, and impersonation profile are non-secret settings that can
# safely be remembered.
_AUTH_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "auth.json",
)
_LEGACY_THWIKI_AUTH_CONFIG_PATH = os.path.join(
    availability.app_config_dir(), "thwiki_auth.json",
)
_AUTH_SITE_INFO = {
    "thwiki": {
        "label": "THBWiki",
        "prefix": "THWIKI",
        "profile_name": "THWIKI",
    },
}
_AUTH_BROWSERS = [
    "chrome", "brave", "chromium", "firefox", "edge", "opera",
    "vivaldi", "librewolf", "safari",
]


def _load_auth_config() -> dict:
    """Return persisted non-secret auth settings, or ``{}`` if unreadable.

    Older releases stored the THBWiki User-Agent and impersonation profile in
    ``thwiki_auth.json``.  Read that file as a compatibility fallback, but
    write new settings to the site-aware ``auth.json`` format.
    """
    data: dict = {}
    try:
        with open(_AUTH_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data = raw
    except (OSError, json.JSONDecodeError):
        pass
    if "thwiki" not in data:
        try:
            with open(_LEGACY_THWIKI_AUTH_CONFIG_PATH, "r",
                      encoding="utf-8") as f:
                legacy = json.load(f)
            if isinstance(legacy, dict):
                data["thwiki"] = legacy
        except (OSError, json.JSONDecodeError):
            pass
    return data


def _save_auth_config(
    site: str,
    user_agent: str,
    impersonate: str,
    browser: str,
    auto_pull: bool,
) -> None:
    """Persist non-secret settings for one site, never its cookie."""
    if site not in _AUTH_SITE_INFO:
        return
    try:
        data = _load_auth_config()
        data[site] = {
            "user_agent": user_agent,
            "impersonate": impersonate,
            "browser": browser,
            "auto_pull": bool(auto_pull),
        }
        availability.ensure_private_directory(os.path.dirname(_AUTH_CONFIG_PATH))
        tmp = _AUTH_CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        availability.restrict_private_file(tmp)
        os.replace(tmp, _AUTH_CONFIG_PATH)
        availability.restrict_private_file(_AUTH_CONFIG_PATH)
    except OSError:
        pass


def _apply_auth_config_to_env() -> None:
    """Load saved non-secret auth settings into the environment at startup.

    A value already present in the environment (e.g. exported in the shell)
    takes precedence and is left untouched.  Cookies are never persisted, so
    they are not touched here.
    """
    cfg = _load_auth_config()
    for site, info in _AUTH_SITE_INFO.items():
        saved = cfg.get(site, {})
        if not isinstance(saved, dict):
            continue
        prefix = info["prefix"]
        for key, env_name in (
            ("user_agent", f"{prefix}_UA"),
            ("impersonate", f"{prefix}_IMPERSONATE"),
            ("browser", f"{prefix}_COOKIE_BROWSER"),
        ):
            value = str(saved.get(key) or "").strip()
            if value and not os.environ.get(env_name, "").strip():
                os.environ[env_name] = value
        if (
            "auto_pull" in saved
            and not os.environ.get(f"{prefix}_COOKIE_AUTO", "").strip()
        ):
            os.environ[f"{prefix}_COOKIE_AUTO"] = (
                "1" if bool(saved.get("auto_pull")) else "0"
            )


# Backwards-compatible helper name for code or local scripts that imported it.
def _apply_thwiki_auth_config_to_env() -> None:
    _apply_auth_config_to_env()


def _auth_profile(site: str):
    """Return the browser_cookie site profile, if the helper provides it."""
    if _browser_cookie is None:
        return None
    return getattr(_browser_cookie, _AUTH_SITE_INFO[site]["profile_name"], None)


def _refresh_auth_cookie(site: str, *, force: bool = False) -> bool:
    """Best-effort site-specific cookie refresh with old-helper tolerance."""
    if _browser_cookie is None:
        return False
    profile = _auth_profile(site)
    try:
        if profile is None:
            if site != "thwiki":
                return False
            return bool(_browser_cookie.refresh_env(
                force=force, announce=False,
            ))
        return bool(_browser_cookie.refresh_env(
            site=profile, force=force, announce=False,
        ))
    except TypeError:
        # A stale local helper may only know the old THBWiki signature.
        if site != "thwiki":
            return False
        return bool(_browser_cookie.refresh_env(
            force=force, announce=False,
        ))


def _auth_status_text(site: str) -> str:
    if _browser_cookie is None:
        return "auto-pull unavailable (browser_cookie.py missing)"
    profile = _auth_profile(site)
    if profile is None:
        if site == "thwiki" and hasattr(_browser_cookie, "status_text"):
            return _browser_cookie.status_text()
        return "auto-pull unavailable (site profile missing)"
    return _browser_cookie.status_text(profile)


def _auth_pull_available(site: str) -> bool:
    if _browser_cookie is None:
        return False
    profile = _auth_profile(site)
    if profile is None:
        if site != "thwiki":
            return False
        return not bool(getattr(_browser_cookie, "disabled_reason", lambda: "")())
    try:
        return not bool(_browser_cookie.disabled_reason(profile))
    except TypeError:
        return site == "thwiki" and not bool(
            _browser_cookie.disabled_reason()
        )


def gui_main() -> None:
    """Launch the PyQt5 GUI for interactive tagging.

    The window is split into tabs:
      * "Wiki Tagger" — the original drag-and-drop wiki workflow,
        optionally with auto-romanisation when the romaniser is ready.
      * "Romanise" — standalone romanisation for albums that aren't on
        either wiki.  Only shown when ``japanese_romanizer.is_ready()``
        is True; otherwise a status-bar hint explains how to enable it.
      * "Tag Edit" — manual per-track tag editing for quick corrections
        after a wiki tagging run.  Always shown.

    Crash logging: every GUI session writes a fresh timestamped log file in
    the platform-appropriate per-user log directory, capturing an environment
    snapshot, the contents of the in-app log pane, and full tracebacks for any
    uncaught exception in either the GUI thread or a worker QThread.  See
    ``_setup_gui_logging``.
    """
    # Set up file logging first thing so even an import error in the
    # PyQt5 line below is captured before the process dies.
    logger, log_path = _setup_gui_logging()

    # Load persisted non-secret THBWiki auth settings into the
    # environment so browser selection, auto-pull, User-Agent, and TLS
    # impersonation survive a restart.  Cookies are never loaded from disk.
    _apply_auth_config_to_env()

    # Pre-pull the live THBWiki cookie from the browser now, at launch.  The
    # user is most likely starting the GUI in order to tag, so having the
    # cookie ready up front (and the auth dialog pre-filled) — rather than
    # waiting for the first run or a dialog open — is the natural default.
    # Best-effort: a no-op without the helper / browser_cookie3, and it never
    # clears a manual cookie.  Wrapped so a pull problem can't block launch.
    if _browser_cookie is not None:
        try:
            _refresh_auth_cookie("thwiki")
            logger.info("THBWiki cookie auto-pull at startup: %s",
                        _auth_status_text("thwiki"))
        except Exception:
            # Do not log an unexpected helper exception verbatim: a third-
            # party browser/keyring error must never expose a cookie value.
            logger.warning("THBWiki cookie auto-pull at startup failed")

    from PyQt5 import QtCore, QtGui, QtWidgets

    # Route Qt's own messages (warnings, criticals, fatal assertions)
    # into the log file too.  Qt fatals in particular precede crashes
    # of native code, where Python's excepthook never gets a chance
    # to fire, so this is often the only on-disk trace of those.
    _qt_msg_levels = {
        QtCore.QtDebugMsg:    logging.DEBUG,
        QtCore.QtInfoMsg:     logging.INFO,
        QtCore.QtWarningMsg:  logging.WARNING,
        QtCore.QtCriticalMsg: logging.ERROR,
        QtCore.QtFatalMsg:    logging.CRITICAL,
    }

    def _qt_message_handler(msg_type, context, message):
        level = _qt_msg_levels.get(msg_type, logging.INFO)
        location = ""
        # context.file and context.line are populated for messages
        # emitted from C++; pure-Python qWarning() calls leave them empty.
        if context is not None and getattr(context, "file", None):
            location = f" ({context.file}:{context.line})"
        logger.log(level, "Qt: %s%s", message, location)

    QtCore.qInstallMessageHandler(_qt_message_handler)

    def _has_write_errors(result: dict) -> bool:
        """True when an album finished but some of its writes failed.

        The album-level ``error`` field only reports a whole-album failure
        (no directory, nothing on the wikis).  Individual file writes are
        counted instead, in ``errors`` for the tagging pass and ``rm_errors``
        for the romanisation pass, so a half-tagged album looks perfectly
        successful unless both counters are consulted.
        """
        return bool(result.get("errors") or result.get("rm_errors"))

    class _WriteGuard:
        """One tag writer at a time, across every tab.

        The Wiki Tagger, the Romanise tab and Tag Edit all do their own
        read-modify-write on the same files, and each used to check only its
        own worker.  Two overlapping runs then raced: whichever saved last
        wrote back tags it had read before the other's changes landed,
        silently dropping them.  The guard is plain GUI-thread state — every
        acquire and release happens in a slot on that thread, so no lock is
        needed — and names its owner so the refusal can say who is busy.
        """

        def __init__(self) -> None:
            self._owner: str | None = None

        @property
        def owner(self) -> "str | None":
            return self._owner

        def acquire(self, name: str) -> bool:
            """Take the guard for ``name``; False when someone else holds it."""
            if self._owner is not None:
                return False
            self._owner = name
            return True

        def release(self, name: str) -> None:
            """Give the guard back.  A no-op unless ``name`` holds it."""
            if self._owner == name:
                self._owner = None

    _write_guard = _WriteGuard()
    # Guard owner names — also what the refusal message calls them.
    _WIKI_WRITER = "Wiki Tagger"
    _ROMANIZE_WRITER = "Romanise tab"
    _TAG_EDIT_WRITER = "Tag Edit tab"

    def _refuse_if_writing(parent, what: str) -> bool:
        """Warn and return True when another tab is writing tags right now."""
        owner = _write_guard.owner
        if owner is None:
            return False
        QtWidgets.QMessageBox.warning(
            parent, "Another run is writing tags",
            f"The {owner} is writing tags right now.\n\n"
            f"Wait for it to finish before you {what} — two passes over the "
            "same files can overwrite each other's changes."
        )
        return True

    # =====================================================================
    # Widgets
    # =====================================================================
    class _StayOpenMenu(QtWidgets.QMenu):
        """A QMenu that stays open when a checkable action is clicked, so a
        multi-select filter can have several entries toggled without reopening
        the menu after each one."""

        def mouseReleaseEvent(self, event):  # noqa: N802 (Qt override)
            action = self.activeAction()
            if (action is not None and action.isEnabled()
                    and action.isCheckable()):
                # Toggle in place and keep the menu open.
                action.trigger()
                return
            super().mouseReleaseEvent(event)

    class _FetchStatusBar(QtWidgets.QWidget):
        """A thin, segmented, colour-coded status strip for the fetch phase.

        One segment per album, laid out left→right in album order (leftmost =
        first album).  Segments start in a muted "pending" colour and fill in
        as each album is fetched: the palette highlight colour for a
        successful fetch, red for one that wasn't found / failed — so failed
        fetches stand out at a glance.  Each segment is clickable; clicking
        emits :pyattr:`segmentClicked` with its 0-based index so the GUI can
        jump to that album in the output log.
        """

        segmentClicked = QtCore.pyqtSignal(int)

        _PENDING = 0
        _OK      = 1
        _FAIL    = 2

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._count = 0
            self._statuses: list[int] = []
            self._names: list[str] = []
            self._hover = -1
            self.setMouseTracking(True)
            self.setFixedHeight(16)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Fixed,
            )
            self.setCursor(QtCore.Qt.PointingHandCursor)

        # --- public API ---
        def count(self) -> int:
            return self._count

        def setCount(self, n: int) -> None:
            """Re-initialise with ``n`` pending segments."""
            self._count = max(0, int(n))
            self._statuses = [self._PENDING] * self._count
            self._hover = -1
            self.update()

        def setNames(self, names: list[str]) -> None:
            """Supply per-album display names (album order) for the tooltips."""
            self._names = list(names)

        def setStatus(self, index: int, ok: bool) -> None:
            """Mark segment ``index`` as a success (``ok``) or failure."""
            if 0 <= index < self._count:
                self._statuses[index] = self._OK if ok else self._FAIL
                self.update()

        # --- geometry ---
        def _segment_at(self, x: int) -> int:
            if self._count <= 0:
                return -1
            w = self.width()
            if w <= 0 or x < 0 or x >= w:
                return -1
            return min(int(x * self._count / w), self._count - 1)

        # --- painting ---
        def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
            if self._count <= 0:
                return
            painter = QtGui.QPainter(self)
            pal = self.palette()
            ok_color      = pal.color(QtGui.QPalette.Highlight)
            fail_color    = QtGui.QColor("#c0392b")
            pending_color = pal.color(QtGui.QPalette.Mid)
            sep_color     = pal.color(QtGui.QPalette.Base)

            w = self.width()
            h = self.height()
            n = self._count
            for i in range(n):
                # Integer boundaries so the segments tile the full width
                # exactly, with no rounding gap or overhang.
                x0 = round(i * w / n)
                x1 = round((i + 1) * w / n)
                st = self._statuses[i]
                if st == self._OK:
                    color = ok_color
                elif st == self._FAIL:
                    color = fail_color
                else:
                    color = pending_color
                if i == self._hover:
                    color = color.lighter(125)
                painter.fillRect(
                    QtCore.QRect(x0, 0, max(1, x1 - x0), h), color,
                )
                if i < n - 1:  # thin separator between segments
                    painter.fillRect(QtCore.QRect(x1 - 1, 0, 1, h), sep_color)
            painter.end()

        # --- interaction ---
        def mouseMoveEvent(self, event) -> None:  # noqa: N802
            idx = self._segment_at(event.x())
            if idx != self._hover:
                self._hover = idx
                self.update()
            if idx >= 0:
                name = self._names[idx] if idx < len(self._names) else ""
                if name:
                    label = f"Album {idx + 1}: {name} (out of {self._count})"
                else:
                    label = f"Album {idx + 1} of {self._count}"
                self.setToolTip(label + " — click to view it in the log")
            super().mouseMoveEvent(event)

        def leaveEvent(self, event) -> None:  # noqa: N802
            if self._hover != -1:
                self._hover = -1
                self.update()
            super().leaveEvent(event)

        def mousePressEvent(self, event) -> None:  # noqa: N802
            if event.button() == QtCore.Qt.LeftButton:
                idx = self._segment_at(event.x())
                if idx >= 0:
                    self.segmentClicked.emit(idx)
            super().mousePressEvent(event)

    # =====================================================================
    # Workers
    # =====================================================================
    class _WikiWorker(QtCore.QThread):
        """Runs the two-phase tagging batch (fetch all, then tag) off the GUI thread."""
        log_message = QtCore.pyqtSignal(str)
        album_done  = QtCore.pyqtSignal(dict)
        fetch_progress = QtCore.pyqtSignal(int, bool)
        cookie_error = QtCore.pyqtSignal(str)
        # Emitted (worker thread) when an album looks wholesale wrong and needs
        # the user's call.  The GUI thread shows a modal dialog, then calls
        # resolve_confirm() with the decision; the worker blocks meanwhile.
        confirm_needed = QtCore.pyqtSignal(dict)
        all_done    = QtCore.pyqtSignal()

        def __init__(
            self,
            jobs: list[tuple[str, str, bool]],
            *,
            dry_run: bool,
            thwiki_only: bool,
            mapping_path: str | None,
            romanize: bool,
            force_titlesort: bool,
            force_credits: bool,
            fetch_metadata: bool = True,
            fetch_credits: bool = True,
            use_touhoudb: bool = False,
            touhoudb_add_missing: bool = False,
            selected_tags: tuple[str, ...] = WIKI_TAGS,
        ) -> None:
            super().__init__()
            self._jobs            = jobs
            self._dry_run         = dry_run
            self._thwiki_only     = thwiki_only
            self._mapping_path    = mapping_path
            self._romanize        = romanize
            self._force_titlesort = force_titlesort
            self._force_credits   = force_credits
            self._fetch_metadata  = fetch_metadata
            self._fetch_credits   = fetch_credits
            self._use_touhoudb        = use_touhoudb
            self._touhoudb_add_missing = touhoudb_add_missing
            self._selected_tags       = selected_tags
            # Set by the GUI thread when the user clicks Cancel; read
            # between albums so the in-progress album finishes cleanly
            # before the loop exits.  A bare bool is fine here — the GIL
            # makes attribute reads/writes atomic, and we only sample it
            # at well-defined boundaries, so no mutex is needed.
            self._cancel_requested = False
            # Cross-thread handshake for the severe-mismatch confirmation:
            # the worker emits confirm_needed, then blocks on this Event until
            # the GUI thread calls resolve_confirm() with the decision.
            self._confirm_event = threading.Event()
            self._confirm_result: str | None = None

        def request_cancel(self) -> None:
            """Ask the worker to stop after the current album finishes.
            Safe to call from the GUI thread."""
            self._cancel_requested = True
            # Unblock any in-flight confirmation wait so a Cancel during the
            # dialog doesn't leave the worker parked on the Event.
            self._confirm_result = "cancel"
            self._confirm_event.set()

        def _request_confirm(self, context: dict) -> str:
            """on_confirm callback (runs on the worker thread): ask the GUI to
            show the mismatch dialog and block until it answers.

            Returns ``"skip"``, ``"continue"``, or ``"cancel"``.  Polls the
            cancel flag while waiting so a hard Cancel can't deadlock it.
            """
            self._confirm_result = None
            self._confirm_event.clear()
            self.confirm_needed.emit(context)
            while not self._confirm_event.wait(timeout=0.2):
                if self._cancel_requested:
                    return "cancel"
            return self._confirm_result or "continue"

        def resolve_confirm(self, decision: str) -> None:
            """Deliver the user's mismatch decision (called on the GUI thread)."""
            self._confirm_result = decision
            if decision == "cancel":
                self._cancel_requested = True
            self._confirm_event.set()

        def run(self) -> None:
            import builtins
            original_print = builtins.print

            def _gui_print(*args, **kwargs):
                self.log_message.emit(" ".join(str(a) for a in args))
            builtins.print = _gui_print
            try:
                try:
                    # Two-phase batch: process_albums validates the (now
                    # mandatory) THBWiki cookie, fetches every album while it's
                    # fresh, then tags from the in-memory cache.  A cookie
                    # problem at any point before tagging raises
                    # ThwikiCookieError and aborts the batch with nothing
                    # written, so it's handled separately from a real crash.
                    process_albums(
                        self._jobs,
                        dry_run=self._dry_run,
                        thwiki_only=self._thwiki_only,
                        mapping_path=self._mapping_path,
                        romanize=self._romanize,
                        force_titlesort=self._force_titlesort,
                        force_credits=self._force_credits,
                        fetch_metadata=self._fetch_metadata,
                        fetch_credits=self._fetch_credits,
                        use_touhoudb=self._use_touhoudb,
                        touhoudb_add_missing=self._touhoudb_add_missing,
                        selected_tags=self._selected_tags,
                        on_result=lambda r: self.album_done.emit(r),
                        on_plan=lambda idx, plan: self.fetch_progress.emit(
                            idx, plan.error is None,
                        ),
                        on_confirm=self._request_confirm,
                        cancel_requested=lambda: self._cancel_requested,
                    )
                except ThwikiCookieError as exc:
                    # Expected, recoverable: surface a clear message and let
                    # the GUI prompt the user to refresh the cookie.  No
                    # files were tagged.
                    self.log_message.emit(
                        "\n⚠ THBWiki cookie error — aborted before tagging:\n"
                        f"  {exc}"
                    )
                    self.cookie_error.emit(str(exc))
                except Exception:
                    # Reaching here means something genuinely unexpected
                    # fired — a bug in the tagger itself, a torn-down
                    # Playwright session, or similar.  Log the full traceback
                    # so the user can share it, and surface a short summary in
                    # the GUI log pane.  The outer finally still emits
                    # all_done so the buttons re-enable.
                    logger = logging.getLogger(LOGGER_NAME)
                    logger.critical(
                        "Wiki worker thread crashed:", exc_info=True,
                    )
                    tb_text = traceback.format_exc()
                    self.log_message.emit(
                        "\n💥 Wiki worker crashed — see the session log shown "
                        "in the status bar for the full traceback.\n" + tb_text
                    )
            finally:
                builtins.print = original_print
                self.all_done.emit()

    class _RomanizeWorker(QtCore.QThread):
        """Runs japanese_romanizer.process_album_romanize() per directory."""
        log_message = QtCore.pyqtSignal(str)
        album_done  = QtCore.pyqtSignal(dict)
        all_done    = QtCore.pyqtSignal()

        def __init__(
            self,
            directories: list[str],
            *,
            dry_run: bool,
            force_titlesort: bool,
        ) -> None:
            super().__init__()
            self._dirs            = directories
            self._dry_run         = dry_run
            self._force_titlesort = force_titlesort
            # See _WikiWorker for rationale.
            self._cancel_requested = False

        def request_cancel(self) -> None:
            """Ask the worker to stop after the current album finishes.
            Safe to call from the GUI thread."""
            self._cancel_requested = True

        def run(self) -> None:
            import builtins
            original_print = builtins.print

            def _gui_print(*args, **kwargs):
                self.log_message.emit(" ".join(str(a) for a in args))
            builtins.print = _gui_print
            try:
                try:
                    for directory in self._dirs:
                        result = japanese_romanizer.process_album_romanize(
                            directory,
                            dry_run=self._dry_run,
                            force_titlesort=self._force_titlesort,
                            # A titlesort the user set by hand in the Tag Edit
                            # tab wins over the romaniser, "Force overwrite"
                            # included.  Injected as a predicate so
                            # japanese_romanizer stays configuration-free and
                            # its CLI keeps working without any lock store.
                            is_locked=lambda p: tag_locks.is_locked(
                                p, "titlesort"),
                        )
                        self.album_done.emit(result)
                        if self._cancel_requested:
                            break
                except Exception:
                    # See _WikiWorker.run for rationale.  An unhandled
                    # exception here means a bug in the romaniser, not
                    # the per-album errors process_album_romanize
                    # already encodes in its result dict.
                    logger = logging.getLogger(LOGGER_NAME)
                    logger.critical(
                        "Romanise worker thread crashed:", exc_info=True,
                    )
                    tb_text = traceback.format_exc()
                    self.log_message.emit(
                        "\n💥 Romanise worker crashed — see the session log "
                        "shown in the status bar for the full traceback.\n"
                        + tb_text
                    )
            finally:
                builtins.print = original_print
                self.all_done.emit()

    class _CueSplitWorker(QtCore.QThread):
        """Runs cue_split.split_plan() off the GUI thread.

        Used by the mismatch dialog's "Split via CUE sheet" button: the FLAC
        decode can take many seconds (times the disc count, for a multi-disc
        plan), so it can't run on the GUI thread.  Logs stream to
        ``log_message`` (mirrored into the main log pane) and the final
        ``cue_split.SplitResult`` is delivered via ``done``.
        """
        log_message = QtCore.pyqtSignal(str)
        done        = QtCore.pyqtSignal(object)   # cue_split.SplitResult

        def __init__(self, plan, *, original_policy: str = "trash") -> None:
            super().__init__()
            self._plan = plan
            self._original_policy = original_policy

        def run(self) -> None:
            try:
                res = _cue_split.split_plan(
                    self._plan,
                    original_policy=self._original_policy,
                    log=lambda m: self.log_message.emit(str(m)),
                )
            except Exception as exc:                # never crash the GUI
                logging.getLogger(LOGGER_NAME).critical(
                    "CUE split worker crashed:", exc_info=True)
                res = _cue_split.SplitResult(
                    ok=False, reason="crash",
                    message=f"Split crashed: {exc}")
            self.done.emit(res)

    class _AuthTestWorker(QtCore.QThread):
        """Run a site cookie check without blocking the GUI."""
        done = QtCore.pyqtSignal(str, str)

        def __init__(self, site: str) -> None:
            super().__init__()
            self._site = site

        def run(self) -> None:
            try:
                from thwiki import validate_thwiki_cookie
                validate_thwiki_cookie()
            except ThwikiCookieError as exc:
                text = str(exc).lower()
                if "no " in text and "cookie" in text:
                    result = "Cookie missing."
                elif "challenge" in text or "re-challenged" in text:
                    result = "Challenge returned — cookie or User-Agent was rejected."
                else:
                    result = "Authentication could not be confirmed: network or transport error."
                self.done.emit("fail", result)
            except Exception:
                # Never pass exception text through: HTTP clients can include
                # request details, and this dialog's promise is that it does
                # not expose cookie contents.
                self.done.emit(
                    "fail",
                    "Authentication could not be confirmed: network or transport error.",
                )
            else:
                self.done.emit("ok", "Authentication successful — the site returned a normal page.")

    # =====================================================================
    # Wiki Tagger tab
    # =====================================================================
    class WikiTaggerTab(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setAcceptDrops(True)
            self._worker: _WikiWorker | None = None
            self._results: list[dict] = []
            self._jobs: list[tuple[str, str, bool]] = []
            # Set by the main window while it waits for a cancelled run to
            # finish at close time: the run still ends cleanly, it just
            # doesn't pop its summary dialog in front of a closing window.
            self._shutting_down = False
            self._suppress_slug_persistence = False
            self._active_wiki_tags: set[str] = set(
                preferences.wiki_tag_selection()
            )
            self._syncing_tag_selection = False
            # Known English theme names, loaded lazily the first time an album
            # is marked unavailable (so the artist auto-mark can tell which of
            # an artist's albums already carry a theme).  None until then.
            self._known_themes: set | None = None
            # True when the user clicked Cancel during a run; consumed
            # by _on_all_done to prepend a cancellation note to the
            # summary, and reset at the start of each new run.
            self._was_cancelled: bool = False

            # Outer horizontal layout splits the tab into main content
            # (left) and a settings sidebar (right).  A QSplitter lets
            # the user drag the divider if they want more room for the
            # tree/log; setChildrenCollapsible(False) keeps the sidebar
            # from being dragged out of existence.  The main content's
            # own QVBoxLayout (still named ``layout``) is reparented to
            # ``main_widget`` so the rest of this method works unchanged.
            outer = QtWidgets.QHBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            splitter.setChildrenCollapsible(False)
            outer.addWidget(splitter)

            main_widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(main_widget)

            # --- Album tree ---
            layout.addWidget(QtWidgets.QLabel(
                "Drop album folders here, or use File → Add Folders.  "
                "Expand an album row to see its tracks and any "
                "existing 'grouping' tags."
            ))
            self._tree = QtWidgets.QTreeWidget()
            self._tree.setColumnCount(4)
            self._tree.setHeaderLabels(
                ["Directory", "Album", "Wiki Slug", "Grouping"]
            )
            self._tree.headerItem().setToolTip(
                2,
                "Auto-suggested from the album tag or folder name. Review it "
                "before tagging; double-click to edit.",
            )
            header = self._tree.header()
            header.setStretchLastSection(False)
            # Interactive resize mode lets the user drag column
            # boundaries.  We seed each column with a reasonable
            # default width so file paths, album names, slugs, and
            # grouping values are mostly visible at the default window
            # size — the user can drag any boundary (or resize the
            # window) from there.  A horizontal scrollbar appears
            # automatically if the columns sum to wider than the tree.
            for col, width in enumerate((280, 180, 180, 220)):
                header.setSectionResizeMode(
                    col, QtWidgets.QHeaderView.Interactive,
                )
                header.resizeSection(col, width)
            self._tree.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            # ExtendedSelection enables the standard multi-select
            # gestures: Ctrl+Click toggles individual rows, Shift+Click
            # selects a contiguous range, and click-drag rubber-bands.
            # _remove_selected already iterates over every selected
            # item and dedupes up to the top-level album, so removing
            # multiple albums at once works without further changes.
            self._tree.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection
            )
            self._tree.setUniformRowHeights(True)
            self._tree.setAcceptDrops(False)
            # Click any column header to sort.  Insertions in
            # _add_directory temporarily disable this so the new item
            # can be fully populated before Qt re-sorts.
            self._tree.setSortingEnabled(True)
            self._tree.sortByColumn(0, QtCore.Qt.AscendingOrder)
            # Per-column editability isn't a thing in QTreeWidget
            # (flags are item-level, not cell-level).  Instead we turn
            # off all automatic edit triggers and start an editor
            # explicitly when the user double-clicks the Wiki Slug
            # column on a top-level item — see _on_item_double_clicked.
            self._tree.setEditTriggers(
                QtWidgets.QAbstractItemView.NoEditTriggers
            )
            self._tree.itemDoubleClicked.connect(
                self._on_item_double_clicked
            )
            self._tree.itemChanged.connect(self._on_slug_changed)
            # Right-click context menu for "Send to…" cross-tab transfer.
            self._tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self._tree.customContextMenuRequested.connect(
                self._show_context_menu
            )
            layout.addWidget(self._tree, stretch=2)

            # Cross-tab "Send to…" targets — populated by TaggerWindow
            # after all tabs are constructed.  Each entry is (label, tab).
            self._send_targets: list = []
            self._tab_widget: QtWidgets.QTabWidget | None = None

            # --- Buttons row ---
            # Add Folders / Remove Selected / Clear All / Refresh live
            # in the window's File menu (see TaggerWindow), which
            # dispatches to this tab's _add_folders/_remove_selected/
            # _clear_all/_refresh_queue when it is the active tab.
            btn_row = QtWidgets.QHBoxLayout()
            expand_btn = QtWidgets.QPushButton("&Expand All")
            expand_btn.clicked.connect(self._tree.expandAll)
            btn_row.addWidget(expand_btn)

            collapse_btn = QtWidgets.QPushButton("&Collapse All")
            collapse_btn.clicked.connect(self._tree.collapseAll)
            btn_row.addWidget(collapse_btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)

            # --- Tag / Cancel row ---
            # The Tag button keeps its full visual weight via the
            # layout's stretch factor; Cancel sits at the right at a
            # natural button width and is disabled while no run is in
            # flight.  Both share the same minimum height so the row
            # reads as a single action band.
            action_row = QtWidgets.QHBoxLayout()
            self._tag_btn = QtWidgets.QPushButton("&Tag All")
            self._tag_btn.setMinimumHeight(36)
            font = self._tag_btn.font()
            font.setPointSize(font.pointSize() + 1)
            font.setBold(True)
            self._tag_btn.setFont(font)
            self._tag_btn.clicked.connect(self._start_tagging)
            action_row.addWidget(self._tag_btn, stretch=1)

            self._cancel_btn = QtWidgets.QPushButton("Ca&ncel")
            self._cancel_btn.setMinimumHeight(36)
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setToolTip(
                "Stop after the current album finishes processing "
                "(shortcut: Esc).  Already-tagged albums are kept; "
                "the summary will show what was processed before "
                "cancellation."
            )
            self._cancel_btn.clicked.connect(self._cancel_tagging)
            action_row.addWidget(self._cancel_btn)
            layout.addLayout(action_row)

            # --- Progress area (fetch status strip + tagging bar) ---
            # The segmented strip fills in during the fetch (pre-cache) phase,
            # one clickable segment per album; the bar below tracks tagging.
            self._fetch_bar = _FetchStatusBar()
            self._fetch_bar.setVisible(False)
            self._fetch_bar.segmentClicked.connect(
                self._jump_to_fetch_section
            )
            layout.addSpacing(2)
            layout.addWidget(self._fetch_bar)
            layout.addSpacing(4)

            # --- Progress bar (hidden until first run) ---
            self._progress = QtWidgets.QProgressBar()
            self._progress.setRange(0, 1)
            self._progress.setValue(0)
            self._progress.setFormat("%v / %m albums  (%p%)")
            self._progress.setVisible(False)
            layout.addWidget(self._progress)
            layout.addSpacing(2)

            # --- Log area ---
            self._log = QtWidgets.QPlainTextEdit()
            self._log.setReadOnly(True)
            self._log.setMaximumBlockCount(5000)
            layout.addWidget(self._log, stretch=1)

            # --- Right side: settings sidebar ----------------------
            # Settings are kept in strict alphabetical order.  Note
            # that ``Auto-romanise titles`` and ``Force overwrite
            # existing titlesort`` were originally laid out together
            # on their own row, because the latter only makes sense
            # when the former is on (and is auto-greyed via
            # _sync_romanize_ui below).  Alphabetical ordering breaks
            # that visual locality, which is acceptable at the
            # current setting count — the grey-out still telegraphs
            # the dependency.  If more settings are added later it
            # may be worth introducing section headers in the sidebar
            # (e.g. "Tagging" and "Romanisation") and ordering
            # alphabetically within each section.
            sidebar = QtWidgets.QGroupBox("Settings")
            # A touch wider so the longest labels (e.g. "Force overwrite
            # existing titlesort") aren't clipped at the default size.
            sidebar.setMinimumWidth(260)
            sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
            sidebar_layout.setAlignment(QtCore.Qt.AlignTop)

            # 1. Auto-clear done
            self._auto_clear_cb = QtWidgets.QCheckBox(
                "Auto-&clear done"
            )
            self._auto_clear_cb.setToolTip(
                "Remove successfully tagged albums from the list "
                "after tagging completes"
            )
            sidebar_layout.addWidget(self._auto_clear_cb)

            # 2. Auto-romanise titles  (only when romaniser is ready)
            if ROMANIZER_AVAILABLE:
                self._romanize_cb = QtWidgets.QCheckBox(
                    "Auto-&romanise titles"
                )
                self._romanize_cb.setChecked(True)
                self._romanize_cb.setToolTip(
                    "Also write Hepburn romaji to the 'titlesort' tag "
                    "for tracks whose 'title' contains Japanese "
                    "characters."
                )
                self._romanize_cb.toggled.connect(
                    self._on_romanize_toggled
                )
                sidebar_layout.addWidget(self._romanize_cb)
            else:
                # Sentinel so _start_tagging can read it safely
                self._romanize_cb = None

            # 3. Dry run
            self._dry_run_cb = QtWidgets.QCheckBox("&Dry run")
            self._dry_run_cb.setToolTip(
                "Show what would be tagged without writing to disk"
            )
            sidebar_layout.addWidget(self._dry_run_cb)

            # 4. Force overwrite existing titlesort
            #    (only when romaniser is ready)
            if ROMANIZER_AVAILABLE:
                self._force_ts_cb = QtWidgets.QCheckBox(
                    "&Force overwrite existing titlesort"
                )
                self._force_ts_cb.setToolTip(
                    "Replace existing 'titlesort' tags.  Default is "
                    "to preserve them and only show what would have "
                    "been written."
                )
                sidebar_layout.addWidget(self._force_ts_cb)
            else:
                # Sentinel so _start_tagging can read it safely
                self._force_ts_cb = None

            # 5. Force overwrite existing staff (credit) tags
            self._force_credits_cb = QtWidgets.QCheckBox(
                "Force o&verwrite staff tags"
            )
            self._force_credits_cb.setToolTip(_FORCE_CREDITS_TOOLTIP)
            sidebar_layout.addWidget(self._force_credits_cb)

            # 6. Skip fully-tagged on add
            self._skip_done_cb = QtWidgets.QCheckBox(
                "Skip fully-&tagged on add"
            )
            self._skip_done_cb.setToolTip(
                "When adding folders, omit albums where a majority "
                "of tracks already have a 'grouping' tag (e.g. 7/12 "
                "or 8/15).  Albums whose tracks couldn't be read are "
                "kept."
            )
            sidebar_layout.addWidget(self._skip_done_cb)

            # 5b. Skip genre-tagged on add
            self._skip_genre_cb = QtWidgets.QCheckBox(
                "Skip &genre-tagged on add"
            )
            self._skip_genre_cb.setToolTip(
                "When adding folders, omit albums that already carry any "
                "genre the wiki tagger writes — one of its translated "
                "musical-style values (Metal, Rock, Trance, …).  Lets you "
                "search for albums still missing wiki genres after tagging a "
                "collection before the genre feature existed.  Only the "
                "tagger's own vocabulary counts; provenance labels it keeps "
                "but doesn't fetch as a style (Touhou / Touhou Arrange / "
                "Indie) are ignored, so common pre-existing doujin tags "
                "don't trigger a skip.  A stray pre-existing musical genre "
                "(e.g. a hand-set 'Metal') is an unavoidable false positive. "
                "Reads each track's genre only when this is on."
            )
            sidebar_layout.addWidget(self._skip_genre_cb)

            # 7. THBWiki only
            self._thwiki_cb = QtWidgets.QCheckBox("TH&BWiki only")
            self._thwiki_cb.setToolTip(
                "Skip the English wiki and use THBWiki directly"
            )
            sidebar_layout.addWidget(self._thwiki_cb)

            # 6b. THBWiki authentication (cookie reuse for Cloudflare)
            self._thwiki_auth_btn = QtWidgets.QPushButton(
                "THBWiki A&uthentication…"
            )
            self._thwiki_auth_btn.setToolTip(
                "Provide a browser cookie (cf_clearance) and User-Agent so "
                "THBWiki pages can be fetched past Cloudflare's challenge "
                "without driving a browser.  Choose the browser source and "
                "auto-pull policy here, or paste a session cookie manually. "
                "Cookies are never persisted."
            )
            self._thwiki_auth_btn.clicked.connect(
                self._open_thwiki_auth_dialog
            )
            sidebar_layout.addWidget(self._thwiki_auth_btn)

            # Separator: the settings above are general tagging options; those
            # below are verification / cross-check sources (TouhouDB),
            # a distinctly different concern.  A centered "Verification" caption
            # sits between two lines to label the section below it.
            _verify_sep_row = QtWidgets.QHBoxLayout()
            _verify_sep_row.setContentsMargins(0, 4, 0, 0)

            def _make_hline():
                _line = QtWidgets.QFrame()
                _line.setFrameShape(QtWidgets.QFrame.HLine)
                _line.setFrameShadow(QtWidgets.QFrame.Sunken)
                return _line

            _verify_label = QtWidgets.QLabel("Verification")
            _verify_label.setAlignment(QtCore.Qt.AlignCenter)
            _verify_sep_row.addWidget(_make_hline(), 1)
            _verify_sep_row.addWidget(_verify_label, 0)
            _verify_sep_row.addWidget(_make_hline(), 1)
            sidebar_layout.addLayout(_verify_sep_row)

            # 8. Verify with TouhouDB
            self._touhoudb_cb = QtWidgets.QCheckBox("Verify with Touhou&DB")
            self._touhoudb_cb.setToolTip(
                "Use TouhouDB (touhoudb.com) as a verification source: "
                "check the wiki's staff against TouhouDB, prefer TouhouDB "
                "official romanizations for the artist / artistsort / "
                "albumartist tags, and cross-check the release date and "
                "catalog number (differences are reported, never written)."
            )
            self._touhoudb_cb.toggled.connect(self._sync_touhoudb_ui)
            sidebar_layout.addWidget(self._touhoudb_cb)

            # 9. Add missing TouhouDB members (depends on #8)
            self._tdb_add_missing_cb = QtWidgets.QCheckBox(
                "Add &missing TouhouDB members"
            )
            self._tdb_add_missing_cb.setToolTip(
                "When TouhouDB credits a staff member that the source wiki "
                "doesn't, add them to the per-track 'artist' field using "
                "TouhouDB's per-song credits (one extra rate-limited request "
                "per track).  Off by default; otherwise missing members are "
                "only reported in the summary."
            )
            sidebar_layout.addWidget(self._tdb_add_missing_cb)

            sidebar_layout.addStretch()

            # Sync the add-missing checkbox's enabled state to the
            # verify checkbox (it's meaningless without verification on).
            self._sync_touhoudb_ui(self._touhoudb_cb.isChecked())

            # Sync the force-overwrite checkbox's enabled state to
            # match the auto-romanise checkbox's initial value.  Must
            # happen after both widgets exist.
            if ROMANIZER_AVAILABLE:
                self._sync_titlesort_selection_ui()
            self._sync_force_credits_ui()

            # --- Wire both panes into the splitter ----------------
            # The main pane absorbs all extra horizontal space when
            # the window grows; the sidebar stays at its minimum
            # width (220 px) unless the user drags it wider.
            splitter.addWidget(main_widget)
            splitter.addWidget(sidebar)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
            splitter.setSizes([900, 220])

            # --- Keyboard shortcuts -------------------------------
            # Del removes whatever's selected in the album tree.
            # Scoped to the tree (WidgetShortcut) so it doesn't fire
            # when focus is in a slug editor (where Del should delete
            # a character) or in the log pane.
            del_sc = QtWidgets.QShortcut(
                QtGui.QKeySequence(QtCore.Qt.Key_Delete), self._tree
            )
            del_sc.setContext(QtCore.Qt.WidgetShortcut)
            del_sc.activated.connect(self._remove_selected)

            # Return and Enter (numpad) start tagging from anywhere
            # in the tab.  WidgetWithChildrenShortcut means the
            # shortcut fires regardless of which sub-widget has focus,
            # which is what you want for a "primary action" key — but
            # the slot guards against firing while a cell editor is
            # open so committing a slug edit doesn't immediately kick
            # off a run.  _start_tagging itself already no-ops when a
            # worker is already running.
            for key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
                sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
                sc.activated.connect(self._handle_return_shortcut)

            # Esc cancels the in-flight tagging job.  Stored as an
            # instance attribute (rather than a local like the others)
            # because we toggle its enabled state with the worker's
            # lifetime — kept off when no run is in flight so it
            # doesn't intercept Esc that would otherwise cancel a slug
            # edit or close a popup.  WidgetWithChildrenShortcut
            # already excludes top-level children (file dialog, summary
            # dialog) per Qt's docs, so those handle Esc themselves.
            self._esc_shortcut = QtWidgets.QShortcut(
                QtGui.QKeySequence(QtCore.Qt.Key_Escape), self
            )
            self._esc_shortcut.setContext(
                QtCore.Qt.WidgetWithChildrenShortcut
            )
            self._esc_shortcut.setEnabled(False)
            self._esc_shortcut.activated.connect(self._cancel_tagging)

        def _handle_return_shortcut(self) -> None:
            # If a slug cell is currently being edited, the editor
            # owns Enter — committing the edit takes precedence over
            # starting a run.  In a few PyQt versions the shortcut
            # still fires even when the editor consumes the key, so
            # we double-check explicitly here.
            if (
                self._tree.state()
                == QtWidgets.QAbstractItemView.EditingState
            ):
                return
            self._start_tagging()

        # --- UI sync ---
        def _selected_wiki_tags(self) -> tuple[str, ...]:
            """Return the active tag selection in its stable display order."""
            return tuple(tag for tag in WIKI_TAGS if tag in self._active_wiki_tags)

        def _on_romanize_toggled(self, on: bool) -> None:
            """Keep the session's titlesort selection mirrored with its toggle."""
            if not self._syncing_tag_selection:
                if on:
                    self._active_wiki_tags.add("titlesort")
                else:
                    self._active_wiki_tags.discard("titlesort")
            self._sync_romanize_ui(on)

        def _sync_titlesort_selection_ui(self) -> None:
            """Apply the selected titlesort state to Auto-romanise titles."""
            if self._romanize_cb is None:
                return
            selected = "titlesort" in self._active_wiki_tags
            self._syncing_tag_selection = True
            try:
                self._romanize_cb.setEnabled(selected)
                self._romanize_cb.setChecked(selected)
            finally:
                self._syncing_tag_selection = False
            self._sync_romanize_ui(selected)

        def _sync_romanize_ui(self, on: bool) -> None:
            if self._force_ts_cb is not None:
                self._force_ts_cb.setEnabled(on)

        def _sync_force_credits_ui(self) -> None:
            """Grey out "Force overwrite staff tags" when no staff tag is
            selected — the option has nothing to act on, since the write loop
            skips any credit tag the selection excludes."""
            selected = bool(self._active_wiki_tags & _STAFF_TAGS)
            self._force_credits_cb.setEnabled(selected)
            self._force_credits_cb.setToolTip(
                _FORCE_CREDITS_TOOLTIP if selected else
                _FORCE_CREDITS_TOOLTIP + "\n\nUnavailable: none of Arranger, "
                "Vocalist, or Lyricist is in the current tag selection."
            )

        def _sync_touhoudb_ui(self, on: bool) -> None:
            # "Add missing members" is only meaningful when TouhouDB
            # verification is enabled; grey it out otherwise.
            self._tdb_add_missing_cb.setEnabled(on)

        def _open_tag_selection_dialog(self) -> None:
            """Select the individual fields the Wiki Tagger may write."""
            previous = set(self._active_wiki_tags)
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Wiki Tag Selection")
            dlg.setModal(True)
            layout = QtWidgets.QVBoxLayout(dlg)

            intro = QtWidgets.QLabel(
                "Choose the Wiki Tagger fields to fetch and apply. "
                "At least one field must remain selected."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            group = QtWidgets.QGroupBox("Tags")
            grid = QtWidgets.QGridLayout(group)
            boxes: dict[str, QtWidgets.QCheckBox] = {}
            for index, tag in enumerate(WIKI_TAGS):
                box = QtWidgets.QCheckBox(
                    f"{WIKI_TAG_LABELS[tag]}  ({tag})"
                )
                box.setChecked(tag in previous)
                boxes[tag] = box
                grid.addWidget(box, index // 2, index % 2)
            layout.addWidget(group)

            note = QtWidgets.QLabel(
                "Selecting Artist or Artist Sort enables Verify with TouhouDB. "
                "Title Sort and Auto-romanise titles are kept in sync."
            )
            note.setWordWrap(True)
            layout.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Save
                | QtWidgets.QDialogButtonBox.Cancel
            )

            def save_selection() -> None:
                selected = {
                    tag for tag, box in boxes.items() if box.isChecked()
                }
                if not selected:
                    QtWidgets.QMessageBox.warning(
                        dlg, "Tag selection", "Select at least one tag."
                    )
                    return
                ordered = tuple(tag for tag in WIKI_TAGS if tag in selected)
                data = preferences.load()
                data["wiki_tag_selection"] = list(ordered)
                if not preferences.save(data):
                    QtWidgets.QMessageBox.warning(
                        dlg, "Tag selection",
                        "Could not save the tag selection."
                    )
                    return
                self._active_wiki_tags = selected
                self._sync_titlesort_selection_ui()
                self._sync_force_credits_ui()
                if ((selected - previous) & {"artist", "artistsort"}):
                    self._touhoudb_cb.setChecked(True)
                if selected != previous:
                    self._append_log(format_tag_selection(ordered))
                dlg.accept()

            buttons.accepted.connect(save_selection)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec_()

        # --- "Unavailable on the wikis" marking ---
        def _apply_unavailable_style(
            self, album_item: "QtWidgets.QTreeWidgetItem", unavailable: bool
        ) -> None:
            """Tint a top-level album row (+ warning icon) when unavailable.

            The directory key in column 0 is never altered — the warning is a
            decoration (icon) and a background tint across all columns, so the
            many callers that read ``item.text(0)`` keep working.  The faint
            translucent yellow matches the overwrite tint the summary dialog's
            Changes tab uses, so the two read as the same "attention" colour.
            """
            cols = self._tree.columnCount()
            if unavailable:
                brush = QtGui.QBrush(QtGui.QColor(*_YELLOW_TINT_RGBA))
                icon = self.style().standardIcon(
                    QtWidgets.QStyle.SP_MessageBoxWarning
                )
                album_item.setIcon(0, icon)
                album_item.setToolTip(
                    0, "Marked as unavailable on both wikis"
                )
                for c in range(cols):
                    album_item.setBackground(c, brush)
            else:
                album_item.setIcon(0, QtGui.QIcon())
                album_item.setToolTip(0, "")
                empty = QtGui.QBrush()
                for c in range(cols):
                    album_item.setBackground(c, empty)

        def _refresh_all_unavailable_styles(self) -> None:
            """Re-apply unavailable styling to every album row from the store.

            Called on tab show so marks made in the Statistics tab (which can
            flag an artist's albums) appear here without re-adding the rows.
            """
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                self._apply_unavailable_style(
                    item, availability.is_album_unavailable(item.text(0))
                )

        def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
            super().showEvent(event)
            self._refresh_all_unavailable_styles()

        def _mark_unavailable(self, dirs: list[str], flag: bool) -> None:
            """Mark/unmark the given album folders as unavailable on the wikis.

            On *mark*, after flagging the albums, each affected artist (the
            album's parent folder) is auto-marked too only if it is *genuinely*
            absent from both wikis — i.e. it has no wiki-tagged album and every
            one of its albums is flagged missing.  An artist with any tagged
            album stays "tagged" (the Statistics panel shows it with a partial-
            coverage warning instead).  On *unmark*, the artist is always
            cleared, since an available album means it isn't fully unavailable.
            """
            availability.set_albums(dirs, flag)

            # Resolve the affected artists (parent folders) and, for marking,
            # work out which should be auto-marked.  Needs the known-theme set
            # and the per-album theme classification from library_stats.
            import library_stats as _ls
            if self._known_themes is None:
                self._known_themes = _ls.load_known_themes()
            cache = _ls._load_stats_cache()

            artist_dirs = {
                os.path.dirname(os.path.normpath(d)) for d in dirs
            }
            to_mark: list[str] = []
            to_unmark: list[str] = []
            try:
                for artist in artist_dirs:
                    if not flag:
                        to_unmark.append(artist)
                        continue
                    albums = _ls.classify_artist_albums(
                        artist, self._known_themes, cache=cache
                    )
                    if albums and all(
                        not has_theme and availability.is_album_unavailable(a)
                        for a, has_theme in albums
                    ):
                        to_mark.append(artist)
            finally:
                _ls._save_stats_cache(cache)

            if to_mark:
                availability.set_artists(to_mark, True)
            if to_unmark:
                availability.set_artists(to_unmark, False)

            self._refresh_all_unavailable_styles()

        # --- Context menu (copy name / mark unavailable / Send to…) ---
        def _show_context_menu(self, position) -> None:
            """Right-click on album rows → copy name / mark unavailable / 'Send to…'."""
            # Collect selected albums' directory paths and album-name cells
            # (dedupe via parent walk, same logic as _remove_selected).
            dirs = []
            album_names = []
            seen = set()
            for item in self._tree.selectedItems():
                parent = item
                while parent.parent() is not None:
                    parent = parent.parent()
                path = parent.text(0)
                if path not in seen:
                    seen.add(path)
                    dirs.append(path)
                    album_names.append(parent.text(1))
            if not dirs:
                return

            menu = QtWidgets.QMenu(self)
            n = len(dirs)

            # Copy the artist (albumartist tag, else bracket-stripped parent
            # folder) and the album name (the spaced display value, not the
            # underscore slug) to the clipboard — handy for pasting straight
            # into a wiki search box.
            menu.addAction(
                "Copy artist name" if n == 1
                else f"Copy {n} artist names",
                lambda _d=list(dirs): self._copy_artist_names(_d),
            )
            menu.addAction(
                "Copy album name" if n == 1
                else f"Copy {n} album names",
                lambda _names=list(album_names): self._copy_album_names(
                    _names
                ),
            )
            menu.addAction(
                "Open folder" if n == 1 else f"Open {n} folders",
                lambda _d=list(dirs): self._open_album_folders(_d),
            )
            menu.addSeparator()

            # Mark / unmark as unavailable on the wikis.
            any_unmarked = any(
                not availability.is_album_unavailable(d) for d in dirs
            )
            any_marked = any(
                availability.is_album_unavailable(d) for d in dirs
            )
            if any_unmarked:
                menu.addAction(
                    "Mark as unavailable" if n == 1
                    else f"Mark {n} albums as unavailable",
                    lambda _d=list(dirs): self._mark_unavailable(_d, True),
                )
            if any_marked:
                menu.addAction(
                    "Unmark as unavailable" if n == 1
                    else f"Unmark {n} albums as unavailable",
                    lambda _d=list(dirs): self._mark_unavailable(_d, False),
                )

            override_dirs = [d for d in dirs if album_overrides.get_slug(d)]
            if override_dirs:
                menu.addAction(
                    "Reset saved Wiki Slug override" if len(override_dirs) == 1
                    else f"Reset {len(override_dirs)} saved Wiki Slug overrides",
                    lambda _d=list(override_dirs):
                    self._clear_slug_overrides(_d),
                )

            if self._send_targets:
                if not menu.isEmpty():
                    menu.addSeparator()
                send_menu = menu.addMenu("Send to…")
                for label, tab in self._send_targets:
                    # Capture tab in the lambda's default argument so
                    # each action closes over its own tab reference.
                    send_menu.addAction(
                        label,
                        lambda _dirs=dirs, _tab=tab: self._send_to_tab(
                            _tab, _dirs
                        ),
                    )

            if not menu.isEmpty():
                menu.exec_(
                    self._tree.viewport().mapToGlobal(position)
                )

        def _send_to_tab(self, tab, dirs: list[str]) -> None:
            """Add directories to another tab and switch to it."""
            for d in dirs:
                tab.add_directory(d)
            if self._tab_widget is not None:
                self._tab_widget.setCurrentWidget(tab)

        @staticmethod
        def _copy_lines(values: list[str]) -> None:
            """Put the non-empty *values* on the clipboard, one per line."""
            lines = [v.strip() for v in values if v and v.strip()]
            if lines:
                QtWidgets.QApplication.clipboard().setText("\n".join(lines))

        def _copy_artist_names(self, dirs: list[str]) -> None:
            """Copy each album's artist (albumartist tag, else parent
            folder) to the clipboard, one per line."""
            self._copy_lines([guess_album_artist(d) for d in dirs])

        def _copy_album_names(self, names: list[str]) -> None:
            """Copy the album-name display values to the clipboard, one
            per line (spaced form, not the underscore wiki slug)."""
            self._copy_lines(names)

        @staticmethod
        def _open_album_folders(dirs: list[str]) -> None:
            """Ask the operating system's file manager to show each album."""
            for path in dirs:
                if os.path.isdir(path):
                    QtGui.QDesktopServices.openUrl(
                        QtCore.QUrl.fromLocalFile(path)
                    )

        # --- Drag & drop ---
        def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event: QtGui.QDropEvent) -> None:
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    for album_path in _expand_to_album_dirs(
                            path, max_depth=preferences.scan_depth()):
                        self._add_directory(album_path)

        # --- Tree manipulation ---
        def add_directory(self, path: str) -> None:
            """Public entry point for cross-tab 'Send to…' transfers."""
            self._add_directory(path)

        def _add_directory(self, path: str) -> None:
            # De-dup against existing top-level items.
            for i in range(self._tree.topLevelItemCount()):
                if self._tree.topLevelItem(i).text(0) == path:
                    return

            inferred_slug = guess_album_slug(path)
            saved_slug = album_overrides.get_slug(path)
            slug = saved_slug or inferred_slug
            album_name = slug.replace("_", " ")
            try:
                tracks = scan_album_for_view(path)
            except Exception:
                tracks = []

            # If "Skip fully-tagged on add" is on, short-circuit
            # albums where a majority of tracks already have a
            # grouping tag (more than half — e.g. 7/12 or 8/15).
            # This tolerates a few untaggable originals scattered
            # throughout.  Empty/unreadable folders (tracks == []) fall
            # through so the user still sees them.
            if self._skip_done_cb.isChecked() and tracks:
                tagged = sum(1 for t in tracks if t.get("grouping"))
                if tagged > len(tracks) // 2:
                    self._append_log(
                        f"⏭  Skipping mostly-tagged album "
                        f"({tagged}/{len(tracks)} tracks): {path}"
                    )
                    return

            # If "Skip genre-tagged on add" is on, omit albums that already
            # carry any genre the wiki tagger writes — one of its translated
            # musical-style values (Metal, Rock, …) — so a search after adding
            # surfaces only albums still missing wiki genres.  Provenance /
            # release labels the tagger keeps but doesn't fetch as a style
            # (Touhou / Touhou Arrange / Indie) are excluded from the
            # vocabulary, so the common pre-existing doujin tags don't trigger
            # a skip; a stray pre-existing musical genre is an unavoidable
            # false positive.  Genres are read only when the toggle is on, so
            # the default add path keeps its single open per track.
            if self._skip_genre_cb.isChecked() and tracks:
                vocab = tagger_genre_vocabulary()
                if any(g.casefold() in vocab
                       for t in tracks
                       for g in read_genres(t["path"])):
                    self._append_log(
                        f"⏭  Skipping album that already has wiki "
                        f"genre tags: {path}"
                    )
                    return

            multi_disc = (
                len({t["disc"] for t in tracks}) > 1 if tracks else False
            )

            # Sorting must be off while we build a multi-cell item plus
            # its children — otherwise Qt may re-sort partway through.
            was_sorted = self._tree.isSortingEnabled()
            self._tree.setSortingEnabled(False)
            try:
                album_item = QtWidgets.QTreeWidgetItem(
                    [path, album_name, slug, ""]
                )
                # Editable flag is required for QTreeWidget.editItem()
                # in _on_item_double_clicked to actually open an
                # editor.  Edit triggers are NoEditTriggers so the
                # flag never causes accidental edits on its own; only
                # column 2 + double-click will start editing.
                album_item.setFlags(
                    album_item.flags() | QtCore.Qt.ItemIsEditable
                )
                # Keep the current inferred value separately from the
                # reviewed value.  This lets refresh pick up folder/tag
                # changes without overwriting a saved identity override.
                album_item.setData(2, QtCore.Qt.UserRole, inferred_slug)
                album_item.setData(
                    2, QtCore.Qt.UserRole + 1, bool(saved_slug)
                )
                album_item.setToolTip(
                    2,
                    (
                        "Saved Wiki Slug override. Right-click to reset it."
                        if saved_slug else
                        "Review this suggested wiki slug before tagging. "
                        "Double-click to edit it."
                    ),
                )
                for t in tracks:
                    label = _format_track_label(t, multi_disc)
                    grouping = t.get("grouping") or ""
                    child = QtWidgets.QTreeWidgetItem(
                        [label, "", "", grouping]
                    )
                    child.setFlags(
                        child.flags() & ~QtCore.Qt.ItemIsEditable
                    )
                    album_item.addChild(child)
                self._tree.addTopLevelItem(album_item)
                # Reflect any persisted "unavailable" mark on this album.
                self._apply_unavailable_style(
                    album_item, availability.is_album_unavailable(path)
                )
            finally:
                self._tree.setSortingEnabled(was_sorted)

        def _open_thwiki_auth_dialog(self) -> None:
            self._open_auth_dialog("thwiki")

        def _open_auth_dialog(self, site: str) -> None:
            """Edit one site's browser source and session auth settings."""
            info = _AUTH_SITE_INFO[site]
            prefix = info["prefix"]
            label = info["label"]
            cfg = _load_auth_config()
            saved = cfg.get(site, {})
            if not isinstance(saved, dict):
                saved = {}
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle(f"{label} Authentication")
            dlg.setModal(True)
            dlg.setMinimumWidth(560)

            layout = QtWidgets.QVBoxLayout(dlg)

            intro = QtWidgets.QLabel(
                f"{label} sits behind a browser verification challenge that "
                "automated clients can't reliably pass. Solve it once in "
                "your normal browser; when browser_cookie3 is installed, "
                "the tagger can read that browser's cookie automatically.\n\n"
                "If auto-pull is unavailable, paste the cookie manually: open "
                "the site, pass the \"verify you are human\" check, then "
                "DevTools (F12) → Network → reload → click the document "
                "request → copy the full Cookie header value and the "
                "User-Agent from Request Headers."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            form = QtWidgets.QFormLayout()

            # Cookie — multi-line, since the header is long.
            cookie_edit = QtWidgets.QPlainTextEdit()
            cookie_edit.setPlaceholderText(
                "cf_clearance=…; (the rest of the Cookie header)"
            )
            # Pull the live cookie from the browser first (if available) so the
            # box reflects what a run would actually use, instead of looking
            # empty until a run starts and triggers the first fetch.
            if _browser_cookie is not None:
                try:
                    _refresh_auth_cookie(site)
                except Exception:
                    pass
            cookie_env = f"{prefix}_COOKIE"
            ua_env = f"{prefix}_UA"
            imp_env = f"{prefix}_IMPERSONATE"
            browser_env = f"{prefix}_COOKIE_BROWSER"
            auto_env = f"{prefix}_COOKIE_AUTO"
            cookie_edit.setPlainText(os.environ.get(cookie_env, ""))
            cookie_edit.setFixedHeight(80)
            cookie_edit.setToolTip(
                "The verbatim Cookie request header from a browser that "
                "has passed the challenge.  It must contain cf_clearance. "
                "It is kept in memory only."
            )
            form.addRow("&Cookie:", cookie_edit)

            # User-Agent — single line, must match the cookie's browser.
            ua_edit = QtWidgets.QLineEdit()
            ua_edit.setPlaceholderText(
                "Mozilla/5.0 (…) … — the exact User-Agent from your browser"
            )
            ua_edit.setText(os.environ.get(ua_env, ""))
            ua_edit.setToolTip(
                "The exact User-Agent of the browser that obtained the "
                "cookie.  cf_clearance is bound to it, so a mismatch causes "
                "a re-challenge."
            )
            form.addRow("&User-Agent:", ua_edit)

            # Impersonate profile — curl_cffi TLS fingerprint family.
            impersonate_combo = QtWidgets.QComboBox()
            impersonate_combo.setEditable(True)
            impersonate_combo.addItems(
                ["chrome", "firefox", "safari", "edge", "brave"]
            )
            current_imp = os.environ.get(imp_env, "").strip()
            if current_imp:
                impersonate_combo.setCurrentText(current_imp)
            else:
                impersonate_combo.setCurrentText("chrome")
            impersonate_combo.setToolTip(
                "Which browser's TLS fingerprint curl_cffi should "
                "impersonate.  Match the family of the browser you copied "
                "the cookie from."
            )
            form.addRow("&Impersonate:", impersonate_combo)

            browser_combo = QtWidgets.QComboBox()
            browser_combo.addItems(_AUTH_BROWSERS)
            current_browser = (
                os.environ.get(browser_env, "").strip()
                or str(saved.get("browser") or "chrome").strip()
                or "chrome"
            ).lower()
            if current_browser not in _AUTH_BROWSERS:
                browser_combo.addItem(current_browser)
            browser_combo.setCurrentText(current_browser)
            browser_combo.setToolTip(
                "The browser whose cookie store should be read. Choose the "
                "browser in which you passed the site's challenge."
            )
            form.addRow("&Browser source:", browser_combo)

            auto_default = bool(saved.get("auto_pull", True))
            auto_env_value = os.environ.get(auto_env, "").strip().lower()
            if auto_env_value:
                auto_default = auto_env_value not in {"0", "false", "no", "off"}
            auto_cb = QtWidgets.QCheckBox("Enable browser cookie auto-pull")
            auto_cb.setChecked(auto_default)
            auto_cb.setToolTip(
                "Read the selected browser's live cookie store when the "
                "tagger starts or retries a challenged request. Disable this "
                "to use the manually supplied session cookie only."
            )
            form.addRow("&Auto-pull:", auto_cb)

            layout.addLayout(form)

            note = QtWidgets.QLabel(
                "The browser, auto-pull choice, User-Agent, and impersonation "
                "profile are remembered between sessions; the cookie is not "
                "(it expires and is tied to your browser/network), so re-paste "
                "it when a run reports it was re-challenged.  "
                "Requires the curl_cffi package "
                "(pip install --user curl_cffi)."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(text);")
            layout.addWidget(note)

            # Status of whether auth is currently active.
            status = QtWidgets.QLabel()

            def _refresh_status() -> None:
                auto = _auth_status_text(site)
                if os.environ.get(cookie_env, "").strip():
                    status.setText(f"Status: cookie set — used for {label} "
                                   f"page fetches.  [{auto}]")
                else:
                    status.setText(f"Status: no cookie set.  [{auto}]")
            _refresh_status()
            layout.addWidget(status)

            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Save
                | QtWidgets.QDialogButtonBox.Cancel
            )
            # A "Clear" button to wipe stored auth without hunting through
            # the fields.
            clear_btn = buttons.addButton(
                "Clear", QtWidgets.QDialogButtonBox.ResetRole
            )
            # A button to re-read the live cookie straight from the browser,
            # for when it has rotated while the dialog is open.
            pull_btn = buttons.addButton(
                "Pull from browser", QtWidgets.QDialogButtonBox.ActionRole
            )
            pull_btn.setToolTip(
                f"Read the current {label} cookie straight from your browser "
                "and fill it in here."
            )
            if not _auth_pull_available(site):
                pull_btn.setEnabled(False)

            test_btn = buttons.addButton(
                "Test authentication", QtWidgets.QDialogButtonBox.ActionRole
            )
            test_btn.setToolTip(
                "Make a live request using the current cookie and User-Agent. "
                "The cookie value is never shown in the result or log."
            )
            test_worker: dict[str, object | None] = {"thread": None}
            layout.addWidget(buttons)

            def _apply_env(
                cookie: str, ua: str, imp: str,
                browser: str, auto_pull: bool,
            ) -> None:
                for key, val in (
                    (cookie_env, cookie),
                    (ua_env, ua),
                    (imp_env, imp),
                    (browser_env, browser),
                    (auto_env, "1" if auto_pull else "0"),
                ):
                    if val:
                        os.environ[key] = val
                    else:
                        os.environ.pop(key, None)

            def _on_save() -> None:
                cookie = cookie_edit.toPlainText().strip()
                ua = ua_edit.text().strip()
                imp = impersonate_combo.currentText().strip()
                browser = browser_combo.currentText().strip().lower()
                auto_pull = auto_cb.isChecked()
                # UA and impersonate are stable, so set them in the env for
                # this session and persist all non-secret choices to disk.
                # The cookie is per-session: set it in the env but never
                # write it to disk.
                _apply_env(cookie, ua, imp, browser, auto_pull)
                _save_auth_config(site, ua, imp, browser, auto_pull)
                if cookie and "cf_clearance" not in cookie:
                    QtWidgets.QMessageBox.warning(
                        dlg, f"{label} Authentication",
                        "The cookie you entered doesn't contain "
                        "'cf_clearance'.  It was saved anyway, but the "
                        "fetch will likely be re-challenged without it.",
                    )
                dlg.accept()

            def _on_test_done(kind: str, message: str) -> None:
                status.setText(f"Test: {message}")
                status.setStyleSheet(
                    "color: #287a3e;" if kind == "ok" else "color: #a33;"
                )
                test_btn.setEnabled(True)
                test_worker["thread"] = None

            def _on_test() -> None:
                cookie = cookie_edit.toPlainText().strip()
                ua = ua_edit.text().strip()
                imp = impersonate_combo.currentText().strip()
                browser = browser_combo.currentText().strip().lower()
                auto_pull = auto_cb.isChecked()
                _apply_env(cookie, ua, imp, browser, auto_pull)
                _save_auth_config(site, ua, imp, browser, auto_pull)
                status.setStyleSheet("color: palette(text);")
                status.setText("Test: contacting the site…")
                test_btn.setEnabled(False)
                worker = _AuthTestWorker(site)
                test_worker["thread"] = worker
                worker.done.connect(_on_test_done)
                worker.finished.connect(worker.deleteLater)
                worker.start()

            def _on_clear() -> None:
                cookie_edit.clear()
                ua_edit.clear()
                impersonate_combo.setCurrentText("chrome")
                browser_combo.setCurrentText("chrome")
                auto_cb.setChecked(True)
                _apply_env("", "", "", "chrome", True)
                _save_auth_config(site, "", "", "chrome", True)
                _refresh_status()

            def _on_pull() -> None:
                if _browser_cookie is None:
                    return
                # Force a fresh read past the TTL cache and reflect it.
                try:
                    _refresh_auth_cookie(site, force=True)
                except Exception:
                    pass
                cookie_edit.setPlainText(os.environ.get(cookie_env, ""))
                _refresh_status()

            buttons.accepted.connect(_on_save)
            buttons.rejected.connect(dlg.reject)
            clear_btn.clicked.connect(_on_clear)
            pull_btn.clicked.connect(_on_pull)
            test_btn.clicked.connect(_on_test)

            dlg.exec_()

        def _add_folders(self) -> None:
            dlg = QtWidgets.QFileDialog(self, "Select Album Folders")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
            file_view = dlg.findChild(QtWidgets.QListView, "listView")
            if file_view:
                file_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            tree_view = dlg.findChild(QtWidgets.QTreeView)
            if tree_view:
                tree_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                for path in dlg.selectedFiles():
                    if os.path.isdir(path):
                        for album_path in _expand_to_album_dirs(
                                path, max_depth=preferences.scan_depth()):
                            self._add_directory(album_path)

        def _remove_selected(self) -> None:
            # Selecting a track row should remove its parent album,
            # not just that one track — the whole album is the unit
            # of work.  Walk every selected item up to its top-level
            # ancestor, dedupe, and remove those.
            to_remove_ids = set()
            for item in self._tree.selectedItems():
                parent = item
                while parent.parent() is not None:
                    parent = parent.parent()
                to_remove_ids.add(id(parent))
            indices = sorted(
                (
                    i for i in range(self._tree.topLevelItemCount())
                    if id(self._tree.topLevelItem(i)) in to_remove_ids
                ),
                reverse=True,
            )
            for i in indices:
                self._tree.takeTopLevelItem(i)

        def _clear_all(self) -> None:
            self._tree.clear()

        def _clear_slug_overrides(self, dirs: list[str]) -> None:
            """Forget saved slugs and immediately restore inferred values."""
            changed = 0
            self._suppress_slug_persistence = True
            try:
                for directory in dirs:
                    if album_overrides.clear_slug(directory):
                        changed += 1
                    for i in range(self._tree.topLevelItemCount()):
                        item = self._tree.topLevelItem(i)
                        if item.text(0) != directory:
                            continue
                        inferred = guess_album_slug(directory)
                        item.setText(1, inferred.replace("_", " "))
                        item.setText(2, inferred)
                        item.setData(2, QtCore.Qt.UserRole, inferred)
                        item.setData(2, QtCore.Qt.UserRole + 1, False)
                        item.setToolTip(
                            2,
                            "Review this suggested wiki slug before tagging. "
                            "Double-click to edit it.",
                        )
                        break
            finally:
                self._suppress_slug_persistence = False
            if changed:
                self._append_log(
                    f"↺  Reset {changed} saved Wiki Slug override(s)."
                )

        def _refresh_queue(self) -> None:
            """Re-check every queued album folder against the disk
            (File → Refresh).  Folders that no longer exist are removed
            from the queue; the rest get their track rows re-scanned
            (picking up structure changes such as a FLAC image split
            outside the program) and their auto-suggested slug/album
            name re-guessed from the current tags.  A hand-edited slug
            (one that no longer matches the auto-guess stored at add
            time) is preserved."""
            refreshed = 0
            was_sorted = self._tree.isSortingEnabled()
            self._tree.setSortingEnabled(False)
            try:
                for i in reversed(range(self._tree.topLevelItemCount())):
                    item = self._tree.topLevelItem(i)
                    directory = item.text(0)
                    if not os.path.isdir(directory):
                        self._tree.takeTopLevelItem(i)
                        self._append_log(
                            f"✖  Removed missing folder: {directory}"
                        )
                        continue
                    fresh_slug = guess_album_slug(directory)
                    saved_slug = album_overrides.get_slug(directory)
                    auto_slug = item.data(2, QtCore.Qt.UserRole)
                    current_slug = item.text(2).strip()
                    manual_session_slug = (
                        not saved_slug
                        and auto_slug is not None
                        and current_slug != str(auto_slug).strip()
                    )
                    self._suppress_slug_persistence = True
                    try:
                        if saved_slug:
                            item.setText(2, saved_slug)
                            item.setText(1, saved_slug.replace("_", " "))
                        elif not manual_session_slug:
                            item.setText(2, fresh_slug)
                            item.setText(1, fresh_slug.replace("_", " "))
                        item.setData(2, QtCore.Qt.UserRole, fresh_slug)
                        item.setData(
                            2, QtCore.Qt.UserRole + 1,
                            bool(saved_slug or manual_session_slug),
                        )
                        item.setToolTip(
                            2,
                            (
                                "Saved Wiki Slug override. Right-click to "
                                "reset it."
                                if saved_slug or manual_session_slug else
                                "Review this suggested wiki slug before "
                                "tagging. Double-click to edit it."
                            ),
                        )
                    finally:
                        self._suppress_slug_persistence = False
                    refreshed += 1
            finally:
                self._tree.setSortingEnabled(was_sorted)
            dirs = {
                self._tree.topLevelItem(i).text(0)
                for i in range(self._tree.topLevelItemCount())
            }
            self._refresh_grouping_for_dirs(dirs)
            self._refresh_all_unavailable_styles()
            self._append_log(f"↻  Refreshed {refreshed} album folder(s).")

        # Open an editor on column 2 (Wiki Slug) when the user
        # double-clicks it on an album row.  All other double-clicks
        # fall through to the tree's default behaviour (toggling
        # expand/collapse).
        def _on_item_double_clicked(
            self, item: "QtWidgets.QTreeWidgetItem", column: int
        ) -> None:
            if column == 2 and item.parent() is None:
                self._tree.editItem(item, column)

        def _on_slug_changed(
            self, item: "QtWidgets.QTreeWidgetItem", column: int
        ) -> None:
            """Persist a user-edited top-level Wiki Slug immediately."""
            if self._suppress_slug_persistence or column != 2:
                return
            if item.parent() is not None:
                return
            directory = item.text(0).strip()
            if not directory:
                return
            slug = item.text(2).strip()
            if slug:
                album_overrides.set_slug(directory, slug)
            else:
                album_overrides.clear_slug(directory)
            inferred = guess_album_slug(directory)
            self._suppress_slug_persistence = True
            try:
                if slug:
                    item.setText(1, slug.replace("_", " "))
                item.setData(2, QtCore.Qt.UserRole, inferred)
                item.setData(2, QtCore.Qt.UserRole + 1, bool(slug))
                item.setToolTip(
                    2,
                    (
                        "Saved Wiki Slug override. Right-click to reset it."
                        if slug else
                        "Review this suggested wiki slug before tagging. "
                        "Double-click to edit it."
                    ),
                )
            finally:
                self._suppress_slug_persistence = False

        # --- Tagging ---
        def _start_tagging(self) -> None:
            if self._worker is not None and self._worker.isRunning():
                return
            if _refuse_if_writing(self, "tag these albums"):
                return

            jobs = []
            job_names = []
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                directory = item.text(0).strip()
                slug = item.text(2).strip()
                if slug and directory:
                    # Only an inferred slug may use the capitalization retry
                    # helper.  A saved or session-edited override is used
                    # exactly as reviewed, even if it happens to equal the
                    # current inferred value.
                    auto_guess = (
                        item.data(2, QtCore.Qt.UserRole) or ""
                    ).strip()
                    override = item.data(2, QtCore.Qt.UserRole + 1)
                    slug_is_auto = (
                        slug == auto_guess if override is None else not bool(override)
                    )
                    jobs.append((slug, directory, slug_is_auto))
                    # Album name for the fetch-strip tooltip: prefer the Album
                    # column, fall back to the directory's basename.
                    name = item.text(1).strip() or os.path.basename(
                        directory.rstrip("/\\"))
                    job_names.append(name)

            if not jobs:
                QtWidgets.QMessageBox.information(
                    self, "Nothing to do",
                    "Add at least one album folder first."
                )
                return

            self._tag_btn.setEnabled(False)
            self._tag_btn.setText("Tagging…")
            self._cancel_btn.setEnabled(True)
            self._esc_shortcut.setEnabled(True)
            self._was_cancelled = False
            self._log.clear()
            selected_tags = self._selected_wiki_tags()
            self._append_log(format_tag_selection(selected_tags))
            self._results = []
            # Stash jobs so _on_all_done's auto-clear / refresh pass
            # can match successful results back to tree rows by
            # directory path, which stays correct even if the user
            # re-sorts the tree during or after the run.
            self._jobs = jobs
            # Reset progress bar for this run.
            self._progress.setRange(0, len(jobs))
            self._progress.setValue(0)
            self._progress.setVisible(True)
            # Reset the per-album fetch status strip (one segment per album).
            self._fetch_bar.setCount(len(jobs))
            self._fetch_bar.setNames(job_names)
            self._fetch_bar.setVisible(True)

            do_romanize = (
                ROMANIZER_AVAILABLE
                and self._romanize_cb is not None
                and self._romanize_cb.isChecked()
            )
            force_ts = (
                self._force_ts_cb is not None
                and self._force_ts_cb.isChecked()
            )

            self._worker = _WikiWorker(
                jobs,
                dry_run=self._dry_run_cb.isChecked(),
                thwiki_only=self._thwiki_cb.isChecked(),
                mapping_path=None,
                romanize=do_romanize,
                force_titlesort=force_ts,
                force_credits=self._force_credits_cb.isChecked(),
                fetch_metadata=True,
                fetch_credits=True,
                use_touhoudb=self._touhoudb_cb.isChecked(),
                touhoudb_add_missing=(
                    self._tdb_add_missing_cb.isChecked()
                    and self._touhoudb_cb.isChecked()
                ),
                selected_tags=selected_tags,
            )
            self._worker.log_message.connect(self._append_log)
            self._worker.album_done.connect(self._on_album_done)
            self._worker.fetch_progress.connect(self._on_fetch_progress)
            self._worker.cookie_error.connect(self._on_cookie_error)
            self._worker.confirm_needed.connect(self._on_confirm_needed)
            self._worker.all_done.connect(self._on_all_done)
            _write_guard.acquire(_WIKI_WRITER)
            self._worker.start()

        def _on_cookie_error(self, message: str) -> None:
            # The mandatory THBWiki cookie is missing or stale, so the run
            # was aborted before any file was tagged.  Point the user at the
            # auth dialog so they can paste a fresh cookie and re-run.  This
            # runs on the GUI thread (queued from the worker), so it's safe
            # to show a modal dialog here.
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Critical)
            box.setWindowTitle("THBWiki cookie required")
            box.setText(
                "Tagging was aborted before any files were changed because "
                "a valid THBWiki cookie is required for every run."
            )
            box.setInformativeText(
                f"{message}\n\nOpen \"THBWiki Authentication…\", paste a "
                "fresh cookie (and matching User-Agent) from your browser, "
                "then run again."
            )
            box.setStandardButtons(QtWidgets.QMessageBox.Ok)
            box.exec_()

        @QtCore.pyqtSlot(dict)
        def _on_confirm_needed(self, context: dict) -> None:
            # Runs on the GUI thread (queued from the worker).  Show the modal
            # mismatch dialog, then hand the decision back so the blocked worker
            # can continue.  If the worker vanished, there's nothing to resolve.
            decision = self._build_mismatch_dialog(context)
            if self._worker is not None:
                self._worker.resolve_confirm(decision)

        def _build_mismatch_dialog(self, context: dict) -> str:
            """Show the severe-mismatch confirmation dialog (modal, GUI thread).

            Renders a Local / TouhouDB / Wiki value view of every tag
            (an ``Album`` node plus one node per local track, then any tracks
            missing locally), tinting disagreeing rows the faint yellow.  The
            TouhouDB column is hidden when its verify toggle is off.

            Returns ``"skip"``, ``"continue"``, or ``"cancel"``.  Closing the
            dialog without choosing defaults to ``"skip"`` (never tag a
            wrong-looking album by accident).
            """
            use_tdb = bool(context.get("use_touhoudb"))
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle(
                f"Possible wrong album — {context.get('album', '')}")
            dlg.setMinimumSize(720, 520)
            dlg.resize(900, 640)
            layout = QtWidgets.QVBoxLayout(dlg)

            rate = context.get("match_rate", 0.0) * 100
            lc = context.get("local_count", 0)
            fc = context.get("fetched_count", 0)
            warn = QtWidgets.QLabel(
                "⚠ This album's local tracks don't line up with the fetched "
                f"data — only {rate:.0f}% of {lc} local track(s) match the "
                f"{fc} fetched track(s). It may be matched to the wrong wiki "
                "page. Review below, then choose what to do."
            )
            warn.setWordWrap(True)
            layout.addWidget(warn)

            path_lbl = QtWidgets.QLabel(context.get("music_dir", ""))
            path_lbl.setTextInteractionFlags(
                QtCore.Qt.TextSelectableByMouse)
            path_lbl.setStyleSheet("color: palette(text);")
            layout.addWidget(path_lbl)

            tree = QtWidgets.QTreeWidget()
            tree.setHeaderLabels(
                ["Tag", "Local", "TouhouDB", "Wiki"])
            tree.setAlternatingRowColors(True)
            tree.setUniformRowHeights(False)
            header = tree.header()
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeToContents)
            for col in (1, 2, 3):
                header.setSectionResizeMode(
                    col, QtWidgets.QHeaderView.Stretch)
            if not use_tdb:
                tree.setColumnHidden(2, True)
            layout.addWidget(tree, stretch=1)

            yellow = QtGui.QBrush(QtGui.QColor(*_YELLOW_TINT_RGBA))

            def _add_rows(parent, rows):
                for r in rows:
                    item = QtWidgets.QTreeWidgetItem(
                        parent,
                        [r["tag"], r["local"], r["tdb"], r["wiki"]],
                    )
                    if r.get("diff"):
                        for c in range(4):
                            item.setBackground(c, yellow)

            album_node = QtWidgets.QTreeWidgetItem(
                tree, ["Album", "", "", ""])
            af = album_node.font(0)
            af.setBold(True)
            album_node.setFont(0, af)
            _add_rows(album_node, context.get("album_rows", []))
            album_node.setExpanded(True)

            for tr in context.get("tracks", []):
                node = QtWidgets.QTreeWidgetItem(
                    tree, [tr["label"], "", "", ""])
                # Flag the track header itself when any of its rows disagree,
                # so a collapsed track still shows the discrepancy.
                if any(row.get("diff") for row in tr["rows"]):
                    node.setBackground(0, yellow)
                _add_rows(node, tr["rows"])
                node.setExpanded(True)

            missing = context.get("missing", [])
            if missing:
                mnode = QtWidgets.QTreeWidgetItem(
                    tree, ["Missing locally", "", "", ""])
                mf = mnode.font(0)
                mf.setBold(True)
                mnode.setFont(0, mf)
                for d in missing:
                    label = f"track {d['number']}"
                    if d.get("disc", 1) != 1:
                        label = f"disc {d['disc']} {label}"
                    item = QtWidgets.QTreeWidgetItem(
                        mnode, [label, "", d.get("tdb", ""), d.get("wiki", "")])
                    for c in range(4):
                        item.setBackground(c, yellow)
                mnode.setExpanded(True)

            result = {"decision": "skip"}

            def _choose(decision: str) -> None:
                result["decision"] = decision
                dlg.accept()

            skip_btn = QtWidgets.QPushButton("&Skip album")
            cont_btn = QtWidgets.QPushButton("&Continue tagging")
            cancel_btn = QtWidgets.QPushButton("Cancel &run")
            cont_btn.setDefault(True)
            skip_btn.clicked.connect(lambda: _choose("skip"))
            cont_btn.clicked.connect(lambda: _choose("continue"))
            cancel_btn.clicked.connect(lambda: _choose("cancel"))

            btn_row = QtWidgets.QHBoxLayout()

            # "Split via CUE sheet" recovery: when the folder is un-split
            # album image(s) — one lone FLAC, or one disc-named FLAC per disc —
            # offer to split, then re-check.  Multi-disc images are first moved
            # into "Disc N" subfolders and split there.  The button is shown
            # whenever the folder *looks* like a whole-album/disc image
            # (looks_splittable: a disc-named set, or a lone FLAC ≥ 10 min),
            # even before a CUE is confirmed — if none is found, clicking
            # reports that.  A resolved plan (detect_split) is used when
            # available for a precise tooltip and the actual split.
            music_dir = context.get("music_dir", "")
            cue_plan = None
            show_split = False
            mismatch_split_hint = False
            try:
                local_audio = scan_music_files(music_dir)
                has_flac = any(
                    str(t.get("path", "")).lower().endswith(".flac")
                    for t in local_audio
                )
                mismatch_split_hint = (
                    1 <= len(local_audio) <= 3
                    and int(context.get("fetched_count", 0)) >= 6
                    and has_flac
                )
            except Exception:
                pass
            if (_cue_split is not None and music_dir
                    and _cue_split.cue_tools_available()):
                try:
                    cue_plan = _cue_split.detect_split(
                        music_dir, allow_ambiguous=mismatch_split_hint
                    )
                except Exception:
                    cue_plan = None
                try:
                    show_split = (cue_plan is not None
                                  or _cue_split.looks_splittable(music_dir))
                except Exception:
                    show_split = cue_plan is not None
                # A short local file count is often an incomplete view of a
                # whole-album image.  When the fetched wiki tracklist is much
                # larger, expose the recovery action even if the image is
                # shorter than the normal duration heuristic or the folder has
                # two/three ambiguous FLACs.  The actual CUE detector and all
                # verification gates still decide whether anything can happen.
                show_split = show_split or mismatch_split_hint
            if show_split:
                split_btn = QtWidgets.QPushButton("Split via &CUE sheet…")
                if cue_plan is None:
                    split_btn.setToolTip(
                        "Check whether this album image can be split by a CUE "
                        "sheet (external or embedded in the FLAC), then "
                        "re-check. This option is also shown when the local "
                        "track count is much smaller than the fetched wiki "
                        "tracklist.")
                elif cue_plan.multi_disc:
                    total = sum(len(s.tracks) for s in cue_plan.sources)
                    subs = ", ".join(
                        f"Disc {s.disc_no}" for s in cue_plan.sources)
                    split_btn.setToolTip(
                        f"Move the {len(cue_plan.sources)} disc images into "
                        f"{subs} subfolders and split them into {total} "
                        "track(s) using their CUE sheets, then re-check.")
                else:
                    total = sum(len(s.tracks) for s in cue_plan.sources)
                    split_btn.setToolTip(
                        f"Split the single album FLAC into {total} track(s) "
                        f"using its {cue_plan.sources[0].source_kind} CUE "
                        "sheet, then re-check.")
                split_btn.clicked.connect(
                    lambda: self._run_cue_split(dlg, cue_plan, _choose))
                btn_row.addWidget(split_btn)

            btn_row.addWidget(skip_btn)
            btn_row.addStretch()
            btn_row.addWidget(cancel_btn)
            btn_row.addWidget(cont_btn)
            layout.addLayout(btn_row)

            dlg.exec_()
            return result["decision"]

        def _run_cue_split(self, dlg, plan, choose) -> None:
            """Run cue_split.split_plan off-thread with a busy dialog.

            On a verified-clean split, the original image(s) are already in
            Trash; we close the mismatch dialog with a ``"rescan"`` decision so
            the worker re-scans the now-split folder and re-runs the
            comparison.  On failure the mismatch dialog stays open
            (Skip/Continue/Cancel still available).

            ``plan`` is None when the button was shown on a size/duration hunch
            (``looks_splittable``) but no usable CUE was actually found — say
            so plainly rather than doing nothing.
            """
            if plan is None:
                QtWidgets.QMessageBox.warning(
                    self, "Nothing to split",
                    "No usable CUE sheet was found for this album image — an "
                    "external .cue file or one embedded in the FLAC is needed "
                    "to know where the tracks are. Nothing was changed.")
                return
            policy = preferences.cue_post_processing()
            if policy == "ask":
                choice = QtWidgets.QMessageBox(dlg)
                choice.setIcon(QtWidgets.QMessageBox.Question)
                choice.setWindowTitle("CUE original handling")
                choice.setText(
                    "The split will first pass the existing title, filename, "
                    "FFmpeg, and FLAC verification checks. What should happen "
                    "to the verified original image afterward?"
                )
                trash_btn = choice.addButton(
                    "Move original to Trash", QtWidgets.QMessageBox.AcceptRole
                )
                keep_btn = choice.addButton(
                    "Keep original", QtWidgets.QMessageBox.ActionRole
                )
                choice.addButton(
                    "Cancel", QtWidgets.QMessageBox.RejectRole
                )
                choice.exec_()
                clicked = choice.clickedButton()
                if clicked is trash_btn:
                    policy = "trash"
                elif clicked is keep_btn:
                    policy = "keep"
                else:
                    return

            label = ("Splitting disc images via CUE sheets…"
                     if plan.multi_disc
                     else "Splitting album via CUE sheet…")
            prog = QtWidgets.QProgressDialog(label, "", 0, 0, dlg)
            prog.setWindowTitle("Splitting…")
            prog.setWindowModality(QtCore.Qt.WindowModal)
            prog.setCancelButton(None)            # the split isn't cancellable
            prog.setMinimumDuration(0)
            prog.setAutoClose(False)
            prog.setAutoReset(False)

            worker = _CueSplitWorker(plan, original_policy=policy)
            holder: dict = {}
            worker.log_message.connect(self._append_log)
            worker.done.connect(lambda res: holder.__setitem__("res", res))
            worker.done.connect(prog.close)
            worker.start()
            prog.exec_()                          # blocks until worker emits done
            worker.wait()

            res = holder.get("res")
            if res is not None and res.ok:
                detail = res.message
                if res.trashed:
                    detail += ("\nThe original disc images were moved to "
                               "Trash." if plan.multi_disc else
                               "\nThe original album file was moved to "
                               "Trash.")
                detail += "\n\nRe-checking the folder…"
                QtWidgets.QMessageBox.information(
                    dlg, "Split complete", detail)
                choose("rescan")
            else:
                msg = res.message if res is not None else "The split failed."
                QtWidgets.QMessageBox.warning(dlg, "Split failed", msg)

        def _cancel_tagging(self) -> None:
            # Defensive — the button is disabled outside a run, but
            # the shortcut/programmatic paths could still reach this.
            if self._worker is None or not self._worker.isRunning():
                return
            # Esc can be tapped repeatedly while the current album is
            # still wrapping up; the flag short-circuits the second
            # press onwards so we don't spam the log.
            if self._was_cancelled:
                return
            self._was_cancelled = True
            self._worker.request_cancel()
            # Lock the Cancel button so the user can't double-click it,
            # and surface what's about to happen in both the button
            # labels and the log.
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling…")
            self._tag_btn.setText("Cancelling — finishing current album…")
            self._append_log(
                "\n⏸  Cancel requested — finishing current album, "
                "then stopping."
            )

        @QtCore.pyqtSlot(str)
        def _append_log(self, text: str) -> None:
            self._log.appendPlainText(text)
            # Mirror the GUI log pane to the session log file so a
            # crash report carries the run's full context.  Tagged as
            # ``gui`` so file readers can distinguish it from
            # structured logger.info()/critical() entries.
            logging.getLogger(LOGGER_NAME + ".gui").info(text)

        @QtCore.pyqtSlot(dict)
        def _on_album_done(self, result: dict) -> None:
            self._results.append(result)
            self._progress.setValue(self._progress.value() + 1)

        @QtCore.pyqtSlot(int, bool)
        def _on_fetch_progress(self, index: int, ok: bool) -> None:
            # Colour the album's segment as each fetch completes: highlight
            # for a successful fetch, red for one that wasn't found / failed.
            self._fetch_bar.setStatus(index, ok)

        @QtCore.pyqtSlot(int)
        def _jump_to_fetch_section(self, index: int) -> None:
            # Clicking a segment scrolls the log to that album's
            # ``[fetch i/N]`` marker so its fetched data is easy to review.
            count = self._fetch_bar.count()
            if count <= 0:
                return
            marker = f"[fetch {index + 1}/{count}]"
            cursor = self._log.document().find(marker)
            if cursor.isNull():
                # Marker not present (fetch hasn't reached it yet, or it
                # scrolled out of the bounded log buffer) — nothing to do.
                return
            cursor.movePosition(QtGui.QTextCursor.StartOfBlock)
            # Bias the marker toward the top of the viewport: jump to the end
            # first so the move only has to scroll up, landing the album near
            # the top with its fetched output visible below.
            end = self._log.textCursor()
            end.movePosition(QtGui.QTextCursor.End)
            self._log.setTextCursor(end)
            self._log.setTextCursor(cursor)
            self._log.ensureCursorVisible()

        @QtCore.pyqtSlot()
        def _on_all_done(self) -> None:
            _write_guard.release(_WIKI_WRITER)
            self._tag_btn.setEnabled(True)
            self._tag_btn.setText("&Tag All")
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Ca&ncel")
            self._esc_shortcut.setEnabled(False)
            self._worker = None

            lines = []
            dry = self._dry_run_cb.isChecked()
            do_romanize = (
                ROMANIZER_AVAILABLE
                and self._romanize_cb is not None
                and self._romanize_cb.isChecked()
            )
            use_touhoudb = self._touhoudb_cb.isChecked()
            # mismatch-skipped albums (severe track mismatch, user/CLI chose
            # not to tag) are reported in their own section, not as successes.
            # A "Cancel run" choice in the mismatch dialog produces a zeroed
            # cancel_batch result that likewise isn't a success.
            cancelled_batch = any(
                r.get("cancel_batch") for r in self._results)
            skipped_mismatch = [r for r in self._results
                                if r.get("mismatch_skipped")]
            # An album that ran to the end but had individual write failures
            # is *not* a success: its files are half-tagged, so it must stay
            # in the queue for a retry rather than being auto-cleared.  The
            # album-level `error` field only covers a fetch/scan failure, so
            # the per-file counters have to be checked too.
            completed = [r for r in self._results
                         if not r["error"]
                         and not r.get("mismatch_skipped")
                         and not r.get("cancel_batch")]
            succeeded = [r for r in completed if not _has_write_errors(r)]
            partial = [r for r in completed if _has_write_errors(r)]
            failed = [r for r in self._results if r["error"]]

            # When the run was cancelled, lead with that fact so the
            # numbers below are read in the right context.  Use the
            # stashed _jobs (the queue as it was at run start) for the
            # denominator so re-sorting/removing tree rows mid-run
            # doesn't skew it.
            if self._was_cancelled or cancelled_batch:
                processed = len(self._results)
                total = len(self._jobs)
                lines.append(
                    f"⏹  Cancelled — processed {processed} of {total} "
                    "album(s) before stopping.\n"
                )

            def _album_lines(r: dict, bullet: str) -> None:
                """Append one album's detail block to the summary."""
                action = "Would tag" if dry else "Tagged"
                clear_action = "Would clear" if dry else "Cleared"
                lines.append(
                    f"  {bullet} {r['album']}  ({r['source']})\n"
                    f"      {action}: {r['tagged']}  |  "
                    f"{clear_action}: {r.get('cleared', 0)}  |  "
                    f"Skipped: {r['skipped']}  |  "
                    f"Errors: {r['errors']}"
                )
                if do_romanize:
                    rm_action = "Would romanise" if dry else "Romanised"
                    lines.append(
                        f"      {rm_action}: {r.get('romanized', 0)}"
                        f" new, {r.get('overwritten', 0)} overwritten"
                        f"  |  RM-skipped: {r.get('rm_skipped', 0)}"
                        f"  |  RM-errors: {r.get('rm_errors', 0)}"
                    )
                if use_touhoudb:
                    if r.get("artist_wrote") or r.get("artist_skipped"):
                        a_action = "Would write" if dry else "Wrote"
                        lines.append(
                            f"      {a_action} artist: "
                            f"{r.get('artist_wrote', 0)} new, "
                            f"{r.get('artist_skipped', 0)} skipped"
                        )
                    if r.get("missing_members"):
                        lines.append(
                            "      ⚠ Missing members: "
                            + ", ".join(r["missing_members"])
                        )
                    if r.get("date_mismatch"):
                        d = r["date_mismatch"]
                        lines.append(
                            f"      ⚠ Date — wiki: {d[0]}  |  "
                            f"TouhouDB: {d[1]}"
                        )
                    if r.get("catalog_mismatch"):
                        c = r["catalog_mismatch"]
                        lines.append(
                            f"      ⚠ Catalog — wiki: {c[0]}  |  "
                            f"TouhouDB: {c[1]}"
                        )
                if r.get("title_discrepancies"):
                    kinds: dict[str, int] = {}
                    for d in r["title_discrepancies"]:
                        kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
                    lines.append(
                        "      ⚠ Track discrepancies: "
                        + ", ".join(f"{v} {k}" for k, v in kinds.items())
                        + " (see the Changes tab)"
                    )

            if succeeded:
                lines.append(
                    f"Successfully processed {len(succeeded)} album(s):\n"
                )
                for r in succeeded:
                    _album_lines(r, "✓")

            if partial:
                if succeeded:
                    lines.append("")
                lines.append(
                    f"⚠  Finished with write errors — {len(partial)} "
                    "album(s) are only partly tagged and stay in the "
                    "queue:\n"
                )
                for r in partial:
                    _album_lines(r, "⚠")

            if skipped_mismatch:
                if succeeded or partial:
                    lines.append("")
                lines.append(
                    f"⏭  Skipped {len(skipped_mismatch)} album(s) "
                    "(severe track mismatch — not tagged):\n"
                )
                for r in skipped_mismatch:
                    lines.append(
                        f"  ⏭ {r['album']}  ({r.get('music_dir', '')})"
                    )

            if failed:
                if succeeded or partial or skipped_mismatch:
                    lines.append("")
                lines.append(
                    f"Failed to process {len(failed)} album(s):\n"
                )
                for r in failed:
                    lines.append(f"  ✗ {r['album']}  — {r['error']}")

            total_t  = sum(r["tagged"] for r in self._results)
            total_c  = sum(r.get("cleared", 0) for r in self._results)
            total_s  = sum(r["skipped"] for r in self._results)
            total_e  = sum(r["errors"] for r in self._results)
            action = "Would tag" if dry else "Tagged"
            clear_action = "Would clear" if dry else "Cleared"
            footer = (
                f"\nTotals — {action}: {total_t}  |  "
                f"{clear_action}: {total_c}  |  "
                f"Skipped: {total_s}  |  Errors: {total_e}"
            )
            if do_romanize:
                total_r  = sum(r.get("romanized", 0)   for r in self._results)
                total_ow = sum(r.get("overwritten", 0) for r in self._results)
                total_rs = sum(r.get("rm_skipped", 0)  for r in self._results)
                rm_action = "Would romanise" if dry else "Romanised"
                footer += (
                    f"  ||  {rm_action}: {total_r} new, "
                    f"{total_ow} overwritten  |  RM-skipped: {total_rs}"
                )
            total_locked = sum(
                r.get("locked_skipped", 0) for r in self._results
            )
            if total_locked:
                footer += (
                    f"  ||  🔒 Locked: {total_locked} tag(s) left "
                    f"untouched (see the Changes tab)"
                )
            lines.append(footer)
            if dry and (total_t > 0 or any(
                r.get("romanized", 0) for r in self._results
            )):
                lines.append(
                    "\nThis was a dry run — uncheck 'Dry run' "
                    "and tag again to apply."
                )

            summary = "\n".join(lines)
            self._log.appendPlainText(f"\n{'=' * 60}")
            self._log.appendPlainText(summary)

            if not self._shutting_down:
                self._show_summary_dialog(summary)

            # Build the set of directories that tagged successfully so
            # we can either remove their rows (auto-clear) or refresh
            # their displayed grouping values in place.  Mismatch-skipped
            # albums are excluded — nothing was written, and the user likely
            # wants to keep them in the queue to fix the slug and retry.
            # Albums with per-file write errors are excluded here as well:
            # nothing that still needs a retry may be cleared from the queue.
            success_dirs = {
                self._jobs[i][1]
                for i, r in enumerate(self._results)
                if not r["error"]
                and not r.get("mismatch_skipped")
                and not r.get("cancel_batch")
                and not _has_write_errors(r)
            }

            if self._auto_clear_cb.isChecked() and succeeded:
                # Match by directory path, not by row index — the user
                # may have re-sorted the tree since tagging started,
                # so positional indices from `enumerate(self._results)`
                # no longer line up with tree position.
                indices = sorted(
                    (
                        i for i in range(self._tree.topLevelItemCount())
                        if self._tree.topLevelItem(i).text(0)
                        in success_dirs
                    ),
                    reverse=True,
                )
                for i in indices:
                    self._tree.takeTopLevelItem(i)
            elif not dry and success_dirs:
                # Rows are staying — refresh their grouping column so
                # the user sees the values that were just written
                # rather than the now-stale pre-tag values.  Skipped
                # in dry-run mode (nothing was written) and skipped
                # when auto-clear is on (rows are about to vanish).
                self._refresh_grouping_for_dirs(success_dirs)

        def _refresh_grouping_for_dirs(self, dirs: set) -> None:
            """Re-read 'grouping' for every track in each album whose
            directory is in ``dirs`` and rebuild that album's child
            rows in place.  The album's expanded state is preserved
            because only its children are replaced."""
            was_sorted = self._tree.isSortingEnabled()
            self._tree.setSortingEnabled(False)
            try:
                for i in range(self._tree.topLevelItemCount()):
                    album_item = self._tree.topLevelItem(i)
                    directory = album_item.text(0)
                    if directory not in dirs:
                        continue
                    try:
                        tracks = scan_album_for_view(directory)
                    except Exception:
                        continue
                    album_item.takeChildren()
                    multi_disc = (
                        len({t["disc"] for t in tracks}) > 1
                        if tracks else False
                    )
                    for t in tracks:
                        label = _format_track_label(t, multi_disc)
                        grouping = t.get("grouping") or ""
                        child = QtWidgets.QTreeWidgetItem(
                            [label, "", "", grouping]
                        )
                        child.setFlags(
                            child.flags() & ~QtCore.Qt.ItemIsEditable
                        )
                        album_item.addChild(child)
            finally:
                self._tree.setSortingEnabled(was_sorted)

        def _show_summary_dialog(self, summary: str) -> None:
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Touhou Tagger — Summary")
            dlg.setMinimumSize(600, 400)
            dlg.resize(780, 520)
            dlg_layout = QtWidgets.QVBoxLayout(dlg)

            tabs = QtWidgets.QTabWidget()
            dlg_layout.addWidget(tabs, stretch=1)

            # --- Tab 1: Summary (unchanged text view) ---
            summary_tab = QtWidgets.QWidget()
            summary_layout = QtWidgets.QVBoxLayout(summary_tab)
            summary_layout.setContentsMargins(0, 0, 0, 0)
            text_edit = QtWidgets.QPlainTextEdit(summary)
            text_edit.setReadOnly(True)
            text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            summary_layout.addWidget(text_edit)
            tabs.addTab(summary_tab, "&Summary")

            # --- Tab 2: Changes (per-track diff tree with filter bar) ---
            changes_widget = self._build_changes_tree()
            if changes_widget is not None:
                tabs.addTab(changes_widget, "&Changes")

            close_btn = QtWidgets.QPushButton("&Close")
            close_btn.setDefault(True)
            close_btn.clicked.connect(dlg.accept)
            btn_layout = QtWidgets.QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(close_btn)
            dlg_layout.addLayout(btn_layout)
            dlg.exec_()

        def _build_changes_tree(self) -> "QtWidgets.QWidget | None":
            """Build a widget with a filter bar and a QTreeWidget showing
            per-track tag diffs grouped by album.  Returns ``None`` when
            no album has any changes or TouhouDB mismatches to display.

            The filter bar contains one checkbox per tag type present in
            the results.  When no checkboxes are active, all changes are
            shown.  When one or more are active, only tracks containing
            changes for those tag types are visible.
            """
            from collections import OrderedDict

            # Discrepancy (⚠ row) type labels.  The title-discrepancy kinds map
            # through _DISC_KIND_LABEL; the album-level mismatches use a fixed
            # label each.  These are the entries that populate the "Filter
            # discrepancies" dropdown and tag every ⚠ row's DISC_TYPE_ROLE.
            _DISC_KIND_LABEL = {
                "title_mismatch":     "Title differs",
                "wrong_track_number": "Wrong track #",
                "missing_local":      "Missing locally",
                "no_fetch_match":     "No wiki/TDB match",
            }

            # Gather albums that have at least one change or mismatch.
            albums_with_changes: list[dict] = []
            all_tag_names: OrderedDict[str, None] = OrderedDict()
            # Ordered set of every ⚠ discrepancy type actually present, used to
            # build the discrepancy-filter dropdown.
            present_disc_types: OrderedDict[str, None] = OrderedDict()
            any_mismatch = False
            any_locked = False
            for r in self._results:
                has_changes = bool(r.get("tag_changes"))
                has_mismatch = (r.get("date_mismatch")
                                or r.get("catalog_mismatch")
                                or r.get("missing_members")
                                or r.get("title_discrepancies"))
                if has_mismatch:
                    any_mismatch = True
                if has_changes or has_mismatch:
                    albums_with_changes.append(r)
                for ch in r.get("tag_changes", []):
                    all_tag_names[ch["tag"]] = None
                    if ch.get("locked"):
                        any_locked = True
                if r.get("date_mismatch"):
                    present_disc_types["Date mismatch"] = None
                if r.get("catalog_mismatch"):
                    present_disc_types["Catalog mismatch"] = None
                if r.get("missing_members"):
                    present_disc_types["Missing members"] = None
                for d in r.get("title_discrepancies", []):
                    present_disc_types[
                        _DISC_KIND_LABEL.get(d["kind"], d["kind"])] = None

            if not albums_with_changes:
                return None

            # --- Container widget ---
            container = QtWidgets.QWidget()
            container_layout = QtWidgets.QVBoxLayout(container)
            container_layout.setContentsMargins(0, 0, 0, 0)

            # --- Filter bar (two rows) ---
            filter_bar = QtWidgets.QWidget()
            filter_outer = QtWidgets.QVBoxLayout(filter_bar)
            filter_outer.setContentsMargins(4, 4, 4, 2)
            filter_outer.setSpacing(2)

            # Top row: the per-tag checkboxes (this row is already crowded, so
            # the discrepancy toggle goes on its own row below).
            tag_row = QtWidgets.QHBoxLayout()
            tag_row.addWidget(QtWidgets.QLabel("Filter by tag:"))
            tag_checkboxes: dict[str, QtWidgets.QCheckBox] = {}
            # Lock the per-tag checkboxes into a stable alphabetical order so a
            # given tag (e.g. "grouping") always sits in the same spot run to
            # run, rather than wherever discovery order happened to place it.
            for tag_name in sorted(all_tag_names):
                cb = QtWidgets.QCheckBox(tag_name)
                cb.setChecked(False)
                tag_row.addWidget(cb)
                tag_checkboxes[tag_name] = cb
            tag_row.addStretch()
            filter_outer.addLayout(tag_row)

            # Second row: discrepancy (⚠ row) filtering.  "Only discrepancies"
            # isolates the ⚠ rows (title mismatches and TouhouDB
            # date/catalog/missing-member flags), hiding every normal tag-change
            # row so the things needing attention are easy to find across a
            # multi-album batch.  Alongside it, a "Filter discrepancies"
            # dropdown lists each ⚠ type present, each a checkable entry; when
            # any are checked it acts as a whitelist for which ⚠ types show (see
            # _apply_filters).  Both are only offered when there's at least one
            # ⚠ row; when "Only discrepancies" is on, the per-tag checkboxes are
            # moot and disabled.
            only_disc_cb = QtWidgets.QCheckBox("⚠ Only discrepancies")
            only_disc_cb.setChecked(False)
            only_disc_cb.setVisible(any_mismatch)

            disc_type_actions: "dict[str, QtWidgets.QAction]" = {}
            disc_filter_btn = QtWidgets.QToolButton()
            disc_filter_btn.setText("Filter discrepancies")
            disc_filter_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
            disc_filter_btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
            disc_filter_btn.setVisible(any_mismatch)
            disc_menu = _StayOpenMenu(disc_filter_btn)
            # Same rationale as the per-tag checkboxes above: alphabetical so
            # the discrepancy types keep a stable position between runs.
            for _dtype in sorted(present_disc_types):
                _act = disc_menu.addAction(_dtype)
                _act.setCheckable(True)
                _act.setChecked(False)
                disc_type_actions[_dtype] = _act
            disc_filter_btn.setMenu(disc_menu)

            only_locked_cb = QtWidgets.QCheckBox("🔒 Only locked")
            only_locked_cb.setChecked(False)
            only_locked_cb.setVisible(any_locked)

            disc_row = QtWidgets.QHBoxLayout()
            disc_row.addWidget(only_disc_cb)
            disc_row.addWidget(disc_filter_btn)
            disc_row.addWidget(only_locked_cb)
            disc_row.addStretch()
            filter_outer.addLayout(disc_row)

            container_layout.addWidget(filter_bar)

            # --- Tree ---
            tree = QtWidgets.QTreeWidget()
            tree.setHeaderLabels(["Tag", "Old value", "New value"])
            tree.setRootIsDecorated(True)
            tree.setAlternatingRowColors(True)
            tree.setUniformRowHeights(False)
            # ExtendedSelection gives the usual Ctrl-click (toggle one row) and
            # Shift-click (select the whole range) gestures, so several ⚠ rows
            # can be hand-picked and overwritten together.
            tree.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection)

            header = tree.header()
            header.setStretchLastSection(True)
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeToContents,
            )
            header.setSectionResizeMode(
                1, QtWidgets.QHeaderView.Stretch,
            )
            header.setSectionResizeMode(
                2, QtWidgets.QHeaderView.Stretch,
            )

            # Build the full tree and keep references for filtering.
            # Each entry in track_list is (track_item, [child_items]).
            # Each entry in album_list is (album_item, [child_items]).
            # Tag names are stored on leaf items via Qt.UserRole so the
            # filter can read them back without a dict lookup.
            TAG_ROLE = QtCore.Qt.UserRole
            # Each ⚠ row carries its discrepancy-type label here so the
            # discrepancy filter can read it back (UserRole+1 is _disc_data_role).
            DISC_TYPE_ROLE = QtCore.Qt.UserRole + 2
            # True on locked-tag change items for the filter toggle.
            LOCKED_ROLE = QtCore.Qt.UserRole + 3
            _LOCK_TINT_RGBA = (100, 160, 255, 45)
            track_list: list[tuple] = []   # (track_item, [change_items])
            album_list: list[tuple] = []   # (album_item, [child_items])

            def _reg_mismatch(mi, album_children, disc_type: str) -> None:
                """Register a ⚠ row: tag it with its discrepancy type (so the
                filter can show/hide it by type) and add it to the album's
                children."""
                mi.setData(0, DISC_TYPE_ROLE, disc_type)
                album_children.append(mi)
            # Title-discrepancy rows the user can act on (overwrite the local
            # title from the wiki/TouhouDB value).  Each entry is
            # (tree_item, discrepancy_dict); the dict is also stashed on the
            # item via _disc_data_role for the context menu.  Reset per build.
            self._changes_tree = tree
            self._disc_data_role = QtCore.Qt.UserRole + 1
            self._disc_items: list[tuple] = []
            tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            tree.customContextMenuRequested.connect(
                self._on_changes_context_menu)

            def _attach_action(mi, action: dict) -> None:
                """Mark a ⚠ row as overwritable: stash an action dict on it and
                register it so the context menu / bulk buttons can act on it.
                An action describes which tag to write, the candidate value per
                source ('wiki'/'tdb'), and where to write it."""
                mi.setData(0, self._disc_data_role, action)
                self._disc_items.append((mi, action))

            for r in albums_with_changes:
                music_dir = r.get("music_dir", "")
                album_label = (
                    os.path.basename(music_dir) if music_dir
                    else r.get("album", "(unknown)")
                )
                album_item = QtWidgets.QTreeWidgetItem(
                    tree, [album_label, "", ""]
                )
                album_item.setExpanded(True)
                font = album_item.font(0)
                font.setBold(True)
                album_item.setFont(0, font)
                album_children: list[QtWidgets.QTreeWidgetItem] = []

                # Group tag changes by file path, preserving order.  Two
                # discs of one album routinely hold the same basename
                # ("01 - Intro.flac"); grouping on that alone would merge
                # them into one ambiguous track row.  The label keeps the
                # disc subfolder when there is one, so the rows stay
                # distinguishable.
                changes = r.get("tag_changes", [])
                tracks: OrderedDict[str, list[dict]] = OrderedDict()
                labels: dict[str, str] = {}
                for ch in changes:
                    path = ch.get("path") or ch["filename"]
                    tracks.setdefault(path, []).append(ch)
                    labels.setdefault(
                        path, self._change_track_label(ch, music_dir))

                for path, file_changes in tracks.items():
                    track_item = QtWidgets.QTreeWidgetItem(
                        album_item, [labels[path], "", ""]
                    )
                    track_item.setExpanded(True)
                    album_children.append(track_item)
                    tag_children: list[QtWidgets.QTreeWidgetItem] = []

                    for ch in file_changes:
                        is_locked = ch.get("locked", False)
                        old_disp = ch["old"] if ch["old"] else "(none)"
                        if is_locked:
                            new_disp = (
                                ch["new"] if ch["new"]
                                else "(would clear)"
                            )
                            tag_label = f"🔒 {ch['tag']}"
                        else:
                            new_disp = (
                                ch["new"] if ch["new"]
                                else "(cleared)"
                            )
                            tag_label = ch["tag"]
                        change_item = QtWidgets.QTreeWidgetItem(
                            track_item,
                            [tag_label, old_disp, new_disp],
                        )
                        if is_locked:
                            tint = QtGui.QColor(*_LOCK_TINT_RGBA)
                            for col in range(3):
                                change_item.setBackground(
                                    col, QtGui.QBrush(tint),
                                )
                            change_item.setData(
                                0, LOCKED_ROLE, True)
                        elif ch["old"]:
                            highlight = QtGui.QColor(*_YELLOW_TINT_RGBA)
                            for col in range(3):
                                change_item.setBackground(
                                    col, QtGui.QBrush(highlight),
                                )
                        tag_children.append(change_item)
                        change_item.setData(0, TAG_ROLE, ch["tag"])

                    track_list.append((track_item, tag_children))

                # TouhouDB mismatches (album-level, shown after tracks).
                if r.get("date_mismatch"):
                    d = r["date_mismatch"]
                    mi = QtWidgets.QTreeWidgetItem(
                        album_item,
                        ["⚠ Date mismatch",
                         f"wiki: {d[0]}", f"TouhouDB: {d[1]}"],
                    )
                    _reg_mismatch(mi, album_children, "Date mismatch")
                    if music_dir and d[1]:
                        _attach_action(mi, {
                            "tag": "date", "label": "date",
                            "scope": "album", "music_dir": music_dir,
                            "current": d[0] or "",
                            "wiki": d[0], "tdb": d[1], "also_year": True,
                        })
                if r.get("catalog_mismatch"):
                    c = r["catalog_mismatch"]
                    mi = QtWidgets.QTreeWidgetItem(
                        album_item,
                        ["⚠ Catalog mismatch",
                         f"wiki: {c[0]}", f"TouhouDB: {c[1]}"],
                    )
                    _reg_mismatch(mi, album_children, "Catalog mismatch")
                    if music_dir and c[1]:
                        _attach_action(mi, {
                            "tag": "catalognumber", "label": "catalog number",
                            "scope": "album", "music_dir": music_dir,
                            "current": c[0] or "",
                            "wiki": c[0], "tdb": c[1],
                        })
                if r.get("missing_members"):
                    mi = QtWidgets.QTreeWidgetItem(
                        album_item,
                        ["⚠ Missing members",
                         ", ".join(r["missing_members"]), ""],
                    )
                    _reg_mismatch(mi, album_children, "Missing members")

                for d in r.get("title_discrepancies", []):
                    no = d.get("number")
                    where = f"track {no}" if no else "track ?"
                    if d.get("disc", 1) != 1:
                        where = f"disc {d['disc']} {where}"
                    label = _DISC_KIND_LABEL.get(d["kind"], d["kind"])
                    old_col = f"local: {d['local']}" if d.get("local") else ""
                    new_parts = []
                    if d.get("wiki"):
                        new_parts.append(f"wiki: {d['wiki']}")
                    if d.get("tdb"):
                        new_parts.append(f"TouhouDB: {d['tdb']}")
                    # Show each source's title on its own line (wiki, then
                    # TouhouDB) so they're easy to compare at a glance rather
                    # than running together on one line.
                    mi = QtWidgets.QTreeWidgetItem(
                        album_item,
                        [f"⚠ {label} ({where})", old_col, "\n".join(new_parts)],
                    )
                    _reg_mismatch(mi, album_children, label)
                    # A title row is actionable when a local file exists and at
                    # least one source (wiki/TouhouDB) offers a title —
                    # the user can overwrite the local title from it.
                    if d.get("path") and (d.get("wiki") or d.get("tdb")):
                        _attach_action(mi, {
                            "tag": "title", "label": "title",
                            "scope": "track", "path": d["path"],
                            "current": d.get("local") or "",
                            "wiki": d.get("wiki"), "tdb": d.get("tdb"),
                            "romanize": True,
                        })

                album_list.append((album_item, album_children))

            container_layout.addWidget(tree, stretch=1)

            # --- Overwrite action bar (only when there's something to do) ---
            # One split button per source (Wiki / TouhouDB).  Its menu
            # offers a per-tag bulk set (the safe, granular choice — each source
            # can hold wrong data for a given tag) plus a bold-red, confirmation
            # -gated "Set all mismatches" entry that overwrites every kind at
            # once.  Covers every actionable ⚠ row — title, date, catalog.
            if self._disc_items:
                _TAG_ORDER = ["title", "date", "catalognumber"]

                # Per source, the tags that actually have an actionable
                # discrepancy (label kept for the menu text).
                src_tags: "dict[str, OrderedDict[str, str]]" = {
                    "wiki": OrderedDict(), "tdb": OrderedDict(),
                }
                for _, a in self._disc_items:
                    for src in ("wiki", "tdb"):
                        if self._overwrite_target(a, src):
                            src_tags[src].setdefault(
                                a["tag"], a.get("label") or a["tag"])

                def _danger_menu_action(menu, text, callback):
                    """Add a bold red menu entry (potentially destructive)."""
                    wa = QtWidgets.QWidgetAction(menu)
                    lbl = QtWidgets.QLabel(text)
                    lbl.setStyleSheet(
                        "color: #d33; font-weight: bold; padding: 4px 22px;")
                    lbl.setCursor(QtCore.Qt.PointingHandCursor)
                    wa.setDefaultWidget(lbl)

                    def _click(_ev, _cb=callback, _m=menu):
                        _m.close()
                        _cb()
                    lbl.mousePressEvent = _click
                    menu.addAction(wa)
                    return wa

                action_bar = QtWidgets.QHBoxLayout()
                action_bar.setContentsMargins(4, 2, 4, 4)
                hint = QtWidgets.QLabel(
                    "Fix mismatched tags (right-click a ⚠ row for one):")
                action_bar.addWidget(hint)
                action_bar.addStretch()

                _SRC_BTN = [
                    ("wiki", "Set from &Wiki"),
                    ("tdb", "Set from &TouhouDB"),
                ]
                for src, btn_text in _SRC_BTN:
                    tags = src_tags[src]
                    if not tags:
                        # No actionable value from this source (e.g. "wiki" on a
                        # date/catalog row is a no-op) — skip its button.
                        continue
                    disp = self._src_display(src)
                    btn = QtWidgets.QToolButton()
                    btn.setText(btn_text)
                    btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
                    btn.setPopupMode(QtWidgets.QToolButton.InstantPopup)
                    menu = QtWidgets.QMenu(btn)
                    for tag in _TAG_ORDER:
                        if tag not in tags:
                            continue
                        label_plural = tags[tag] + "s"
                        act = menu.addAction(
                            f"Set all {label_plural} from {disp}")
                        act.triggered.connect(
                            lambda _checked=False, s=src, t=tag:
                            self._overwrite_all(s, t))
                    menu.addSeparator()
                    _danger_menu_action(
                        menu, f"Set all mismatches from {disp}",
                        lambda s=src: self._overwrite_all(s, None))
                    btn.setMenu(menu)
                    action_bar.addWidget(btn)

                container_layout.addLayout(action_bar)

            # --- Filter logic ---
            # The Changes tab has three filter controls that compose:
            #   * per-tag checkboxes — whitelist for normal tag-change rows;
            #   * "Filter discrepancies" dropdown — whitelist for ⚠ rows by type;
            #   * "⚠ Only discrepancies" — additionally hides all normal rows.
            # With nothing selected anywhere, everything shows.  As soon as any
            # filter is active the view is a whitelist: a normal tag row shows
            # only if its tag is checked, and a ⚠ row only if its type is
            # checked.  So filtering to e.g. "grouping" hides the ⚠ rows (they
            # are no longer forced always-visible), and selecting a discrepancy
            # type shows only that type.
            def _apply_filters() -> None:
                only_disc = only_disc_cb.isChecked()
                only_locked = only_locked_cb.isChecked()
                # The per-tag checkboxes are moot in only-discrepancies
                # or only-locked mode.
                for cb in tag_checkboxes.values():
                    cb.setEnabled(not only_disc and not only_locked)
                active_tags = {name for name, cb in tag_checkboxes.items()
                               if cb.isChecked()}
                active_discs = {name for name, act in disc_type_actions.items()
                                if act.isChecked()}
                disc_filtering = bool(active_discs)
                any_filtering = (bool(active_tags) or disc_filtering
                                 or only_disc or only_locked)

                def _disc_visible(disc_type) -> bool:
                    if only_locked:
                        return False  # ⚠ rows are never locked
                    if only_disc:
                        # One-click "show the discrepancies"; still honour the
                        # dropdown whitelist when the user has narrowed it.
                        return ((disc_type in active_discs)
                                if disc_filtering else True)
                    if not any_filtering:
                        return True
                    # Some filter is active: a ⚠ row shows only when its type is
                    # explicitly selected — so filtering to a normal tag hides
                    # the ⚠ rows instead of leaving them visible.
                    return disc_type in active_discs

                for t_item, children in track_list:
                    if only_disc:
                        # Hide every normal track + tag-change row; only the
                        # ⚠ mismatch rows (handled below) stay visible.
                        for child in children:
                            child.setHidden(True)
                        t_item.setHidden(True)
                        continue
                    any_visible = False
                    for child in children:
                        tag_name = child.data(0, TAG_ROLE)
                        is_lck = child.data(0, LOCKED_ROLE)
                        if only_locked:
                            visible = bool(is_lck)
                        elif not any_filtering:
                            visible = True
                        else:
                            visible = tag_name in active_tags
                        child.setHidden(not visible)
                        if visible:
                            any_visible = True
                    t_item.setHidden(not any_visible)

                for a_item, children in album_list:
                    any_visible = False
                    for child in children:
                        disc_type = child.data(0, DISC_TYPE_ROLE)
                        if disc_type is not None:
                            # A ⚠ mismatch row — visibility by its type.
                            vis = _disc_visible(disc_type)
                            child.setHidden(not vis)
                            if vis:
                                any_visible = True
                        elif not child.isHidden():
                            any_visible = True
                    a_item.setHidden(not any_visible)

            for cb in tag_checkboxes.values():
                cb.toggled.connect(_apply_filters)
            only_disc_cb.toggled.connect(_apply_filters)
            only_locked_cb.toggled.connect(_apply_filters)
            for act in disc_type_actions.values():
                act.toggled.connect(_apply_filters)

            return container

        # --- Tag-overwrite actions on the Changes tab ---
        # An "action" describes an overwritable ⚠ row: which tag to write, the
        # candidate value per source ('wiki'/'tdb'), and where to write
        # it.  Title rows are per-track (one file); date/catalog rows are
        # album-level (every file in the album).
        @staticmethod
        def _change_track_label(change: dict, music_dir: str) -> str:
            """Row label for one track in the Changes tree.

            The bare filename for a flat album; the disc subfolder plus the
            filename ("Disc 2/01 - Intro.flac") when the file sits below the
            album directory, so two discs sharing a basename stay apart.
            """
            path = change.get("path") or ""
            name = change.get("filename") or os.path.basename(path)
            if not path or not music_dir:
                return name
            try:
                rel = os.path.relpath(path, music_dir)
            except ValueError:          # different drives (Windows)
                return name
            if rel.startswith(".."):    # outside the album dir — stay literal
                return name
            return rel

        @staticmethod
        def _src_display(source: str) -> str:
            """Human-readable name for an overwrite source key."""
            return {"wiki": "the wiki",
                    "tdb": "TouhouDB"}.get(source, source)

        def _overwrite_target(self, action: dict, source: str):
            """Return the source ('wiki'/'tdb') value to write for an
            action, or None when there's nothing to do (no value for that
            source, or it already matches the current value)."""
            value = (action.get(source) or "").strip()
            if not value:
                return None
            if normalize(value) == normalize(action.get("current") or ""):
                return None
            return value

        def _resolve_action_paths(self, action: dict) -> list:
            """Resolve the local file path(s) an action writes to: the single
            track file for a per-track action, or every audio file in the
            album for an album-level (date/catalog) action."""
            if action.get("scope") == "album":
                music_dir = action.get("music_dir")
                if not music_dir:
                    return []
                return [f["path"] for f in scan_music_files(music_dir)]
            path = action.get("path")
            return [path] if path else []

        def _on_changes_context_menu(self, pos) -> None:
            tree = getattr(self, "_changes_tree", None)
            if tree is None:
                return
            role = self._disc_data_role
            # Act on every selected actionable row (multi-select across mixed
            # tag types works); fall back to the row under the cursor if the
            # selection has none.
            entries = [
                (it, it.data(0, role))
                for it in tree.selectedItems() if it.data(0, role)
            ]
            if not entries:
                it = tree.itemAt(pos)
                if it is not None and it.data(0, role):
                    entries = [(it, it.data(0, role))]
            if not entries:
                return
            menu = QtWidgets.QMenu(tree)
            act_wiki = menu.addAction("Set selected from Wiki")
            act_wiki.setEnabled(any(
                self._overwrite_target(a, "wiki") for _, a in entries))
            act_tdb = menu.addAction("Set selected from TouhouDB")
            act_tdb.setEnabled(any(
                self._overwrite_target(a, "tdb") for _, a in entries))
            chosen = menu.exec_(tree.viewport().mapToGlobal(pos))
            if chosen is act_wiki:
                self._overwrite_entries(entries, "wiki")
            elif chosen is act_tdb:
                self._overwrite_entries(entries, "tdb")

        def _overwrite_all(self, source: str, tag: "str | None" = None) -> None:
            """Bulk-overwrite from one source.  ``tag=None`` is the catch-all
            'all mismatches' path (every actionable kind at once, guarded by a
            stronger confirmation); a specific tag scopes it to that kind."""
            entries = [
                (it, a) for it, a in getattr(self, "_disc_items", [])
                if self._overwrite_target(a, source)
                and (tag is None or a.get("tag") == tag)
            ]
            src_name = self._src_display(source)
            if not entries:
                what = "mismatched tags" if tag is None else f"{tag} tags"
                QtWidgets.QMessageBox.information(
                    self, "Nothing to do",
                    f"No {what} to set from {src_name}.")
                return
            romanize_note = (" (and re-romanises titlesort for titles)."
                             if ROMANIZER_AVAILABLE else ".")
            if tag is None:
                # Overwrites every kind of mismatch at once — potentially
                # destructive, so spell out the risk and default to Cancel.
                box = QtWidgets.QMessageBox(self)
                box.setIcon(QtWidgets.QMessageBox.Warning)
                box.setWindowTitle("Overwrite all mismatches")
                box.setText(
                    "Are you sure you want to overwrite all mismatches?")
                box.setInformativeText(
                    f"This overwrites {len(entries)} mismatched tag(s) of all "
                    f"kinds from {src_name} and writes to disk" + romanize_note
                    + "\n\nEach source can hold wrong data for some tags; "
                    "consider setting one tag kind at a time instead.")
                box.setStandardButtons(
                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
                box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
                reply = box.exec_()
            else:
                label = next((a.get("label") or tag for _, a in entries), tag)
                reply = QtWidgets.QMessageBox.question(
                    self, "Overwrite tags",
                    f"Overwrite {len(entries)} {label} tag(s) from "
                    f"{src_name}?\n\nThis writes to disk" + romanize_note,
                    QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel,
                )
            if reply == QtWidgets.QMessageBox.Ok:
                self._overwrite_entries(entries, source)

        def _overwrite_entries(self, entries, source: str) -> None:
            """Write the chosen source value to each entry's tag, update the
            rows, and report a summary.

            Per-track title rows write one file and re-romanise its titlesort;
            album-level date/catalog rows write the value to every file in the
            album (date rows also derive the ``year`` tag).  Writes for real
            regardless of the run's dry-run setting — it is an explicit,
            after-the-fact correction.
            """
            if _refuse_if_writing(self, "apply these corrections"):
                return
            written = 0          # rows applied
            files_written = 0    # files actually touched
            romanized = 0
            errors: list[str] = []
            role = self._disc_data_role
            _write_guard.acquire(_TAG_EDIT_WRITER)
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            try:
                for item, a in entries:
                    value = self._overwrite_target(a, source)
                    if not value:
                        continue
                    tag = a.get("tag")
                    try:
                        paths = self._resolve_action_paths(a)
                        if not paths:
                            raise RuntimeError("no local files found")
                        for path in paths:
                            _set_tag(path, tag, value, dry_run=False)
                            if tag == "date" and a.get("also_year"):
                                _set_tag(path, "year", value[:4],
                                         dry_run=False)
                            files_written += 1
                            if (a.get("romanize") and ROMANIZER_AVAILABLE
                                    and japanese_romanizer is not None):
                                rm = japanese_romanizer.romanize_file(
                                    path, force_titlesort=True, dry_run=False,
                                    fallback_title=value)
                                if rm.get("status") in (
                                        "romanized", "overwritten"):
                                    romanized += 1
                        written += 1
                        # Reflect the applied change and stop it being reapplied.
                        a["current"] = value
                        if a.get("scope") != "album":
                            item.setText(1, f"local: {value}")
                        if not item.text(0).startswith("✓"):
                            item.setText(0, "✓ " + item.text(0))
                        item.setData(0, role, None)
                    except Exception as exc:
                        label = a.get("label") or tag
                        where = (os.path.basename(a.get("music_dir", ""))
                                 if a.get("scope") == "album"
                                 else os.path.basename(a.get("path", "")))
                        errors.append(f"{label} ({where}): {exc}")
            finally:
                _write_guard.release(_TAG_EDIT_WRITER)
                QtWidgets.QApplication.restoreOverrideCursor()

            # Drop applied rows from the actionable set.
            self._disc_items = [
                (it, a) for it, a in getattr(self, "_disc_items", [])
                if it.data(0, role)
            ]

            src_name = self._src_display(source)
            msg = (f"Set {written} tag(s) from {src_name} "
                   f"({files_written} file(s) written).")
            if ROMANIZER_AVAILABLE and romanized:
                msg += f"  Re-romanised {romanized} titlesort tag(s)."
            if errors:
                msg += "\n\nErrors:\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    msg += f"\n…and {len(errors) - 10} more."
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Warning if errors
                        else QtWidgets.QMessageBox.Information)
            box.setWindowTitle("Tags updated")
            box.setText(msg)
            box.exec_()
            self._append_log("\n" + msg.replace("\n", " "))

    # =====================================================================
    # Romanise tab (only added when ROMANIZER_AVAILABLE)
    # =====================================================================
    class RomanizeTab(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setAcceptDrops(True)
            self._worker: _RomanizeWorker | None = None
            self._results: list[dict] = []
            self._dirs: list[str] = []
            # See WikiTaggerTab.
            self._shutting_down = False
            # See WikiTaggerTab for rationale.
            self._was_cancelled: bool = False

            # Outer horizontal layout splits the tab into main content
            # (left) and a settings sidebar (right); see WikiTaggerTab
            # for the rationale.  This mirrors that structure.
            outer = QtWidgets.QHBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            splitter.setChildrenCollapsible(False)
            outer.addWidget(splitter)

            main_widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(main_widget)

            layout.addWidget(QtWidgets.QLabel(
                "Drop album folders here to romanise their Japanese "
                "titles into the 'titlesort' tag.  The 'title' tag is "
                "left untouched."
            ))

            # --- Folder table (no slug column needed) ---
            self._table = QtWidgets.QTableWidget(0, 2)
            self._table.setHorizontalHeaderLabels(["Directory", "Album"])
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(
                1, QtWidgets.QHeaderView.ResizeToContents,
            )
            self._table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            # ExtendedSelection enables the standard multi-select
            # gestures: Ctrl+Click toggles individual rows, Shift+Click
            # selects a contiguous range, and click-drag rubber-bands.
            # _remove_selected already collects all selected row indices,
            # so removing multiple albums at once works without further
            # changes.
            self._table.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection
            )
            self._table.setAcceptDrops(False)
            # Click any column header to sort alphabetically.  Insertions
            # in _add_directory temporarily disable this so row indices
            # stay stable during multi-call setItem().
            self._table.setSortingEnabled(True)
            layout.addWidget(self._table, stretch=2)

            # Add Folders / Remove Selected / Clear All / Refresh live
            # in the window's File menu (see TaggerWindow), which
            # dispatches to this tab's _add_folders/_remove_selected/
            # _clear_all/_refresh_queue when it is the active tab.

            # --- Run / Cancel row ---
            # Same layout pattern as WikiTaggerTab — see that class for
            # the reasoning behind the stretch factor and disabled
            # initial state.
            action_row = QtWidgets.QHBoxLayout()
            self._run_btn = QtWidgets.QPushButton("&Romanise All")
            self._run_btn.setMinimumHeight(36)
            font = self._run_btn.font()
            font.setPointSize(font.pointSize() + 1)
            font.setBold(True)
            self._run_btn.setFont(font)
            self._run_btn.clicked.connect(self._start_romanizing)
            action_row.addWidget(self._run_btn, stretch=1)

            self._cancel_btn = QtWidgets.QPushButton("Ca&ncel")
            self._cancel_btn.setMinimumHeight(36)
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setToolTip(
                "Stop after the current album finishes processing "
                "(shortcut: Esc).  Already-processed albums are kept; "
                "the summary will show what was processed before "
                "cancellation."
            )
            self._cancel_btn.clicked.connect(self._cancel_romanizing)
            action_row.addWidget(self._cancel_btn)
            layout.addLayout(action_row)

            # --- Progress bar (hidden until first run) ---
            self._progress = QtWidgets.QProgressBar()
            self._progress.setRange(0, 1)
            self._progress.setValue(0)
            self._progress.setFormat("%v / %m albums  (%p%)")
            self._progress.setVisible(False)
            layout.addWidget(self._progress)

            # --- Log ---
            self._log = QtWidgets.QPlainTextEdit()
            self._log.setReadOnly(True)
            self._log.setMaximumBlockCount(5000)
            layout.addWidget(self._log, stretch=1)

            # --- Right side: settings sidebar ----------------------
            # Settings are kept in strict alphabetical order — the
            # Romanise tab currently has only three settings so the
            # grouping question discussed in WikiTaggerTab doesn't
            # arise here, but if more settings land later, consider
            # the same section-header approach.
            sidebar = QtWidgets.QGroupBox("Settings")
            sidebar.setMinimumWidth(220)
            sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
            sidebar_layout.setAlignment(QtCore.Qt.AlignTop)

            # 1. Auto-clear done
            self._auto_clear_cb = QtWidgets.QCheckBox(
                "Auto-&clear done"
            )
            self._auto_clear_cb.setToolTip(
                "Remove successfully processed albums from the list."
            )
            sidebar_layout.addWidget(self._auto_clear_cb)

            # 2. Dry run
            self._dry_run_cb = QtWidgets.QCheckBox("&Dry run")
            self._dry_run_cb.setToolTip(
                "Show what would be written without modifying files."
            )
            sidebar_layout.addWidget(self._dry_run_cb)

            # 3. Force overwrite existing titlesort
            self._force_ts_cb = QtWidgets.QCheckBox(
                "&Force overwrite existing titlesort"
            )
            self._force_ts_cb.setToolTip(
                "Replace existing 'titlesort' tags.  Default is to "
                "preserve them; the log will show both the current "
                "and the would-be values for skipped tracks."
            )
            sidebar_layout.addWidget(self._force_ts_cb)

            sidebar_layout.addStretch()

            # --- Wire both panes into the splitter ----------------
            splitter.addWidget(main_widget)
            splitter.addWidget(sidebar)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
            splitter.setSizes([900, 220])

            # --- Keyboard shortcuts -------------------------------
            # See WikiTaggerTab for the rationale on contexts; this
            # tab's table doesn't allow cell editing, so the
            # editing-state check in _handle_return_shortcut is
            # belt-and-braces.
            del_sc = QtWidgets.QShortcut(
                QtGui.QKeySequence(QtCore.Qt.Key_Delete), self._table
            )
            del_sc.setContext(QtCore.Qt.WidgetShortcut)
            del_sc.activated.connect(self._remove_selected)

            for key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                sc = QtWidgets.QShortcut(QtGui.QKeySequence(key), self)
                sc.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
                sc.activated.connect(self._handle_return_shortcut)

            # See WikiTaggerTab for the Esc shortcut's lifecycle.
            self._esc_shortcut = QtWidgets.QShortcut(
                QtGui.QKeySequence(QtCore.Qt.Key_Escape), self
            )
            self._esc_shortcut.setContext(
                QtCore.Qt.WidgetWithChildrenShortcut
            )
            self._esc_shortcut.setEnabled(False)
            self._esc_shortcut.activated.connect(self._cancel_romanizing)

        def _handle_return_shortcut(self) -> None:
            if (
                self._table.state()
                == QtWidgets.QAbstractItemView.EditingState
            ):
                return
            self._start_romanizing()

        # --- Drag & drop ---
        def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event: QtGui.QDropEvent) -> None:
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if path and os.path.isdir(path):
                    for album_path in _expand_to_album_dirs(
                            path, max_depth=preferences.scan_depth()):
                        self._add_directory(album_path)

        # --- Table ---
        def add_directory(self, path: str) -> None:
            """Public entry point for cross-tab 'Send to…' transfers."""
            self._add_directory(path)

        def _add_directory(self, path: str) -> None:
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.text() == path:
                    return

            album_name = guess_album_slug(path).replace("_", " ")

            # See WikiTaggerTab._add_directory — sorting must be off
            # while the row's columns are being populated, otherwise Qt
            # may re-sort mid-build and invalidate the row index.
            was_sorted = self._table.isSortingEnabled()
            self._table.setSortingEnabled(False)
            try:
                row = self._table.rowCount()
                self._table.insertRow(row)

                dir_item = QtWidgets.QTableWidgetItem(path)
                dir_item.setFlags(dir_item.flags() & ~QtCore.Qt.ItemIsEditable)
                self._table.setItem(row, 0, dir_item)

                album_item = QtWidgets.QTableWidgetItem(album_name)
                album_item.setFlags(
                    album_item.flags() & ~QtCore.Qt.ItemIsEditable
                )
                self._table.setItem(row, 1, album_item)
            finally:
                self._table.setSortingEnabled(was_sorted)

        def _add_folders(self) -> None:
            dlg = QtWidgets.QFileDialog(self, "Select Album Folders")
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(QtWidgets.QFileDialog.ShowDirsOnly, True)
            dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
            file_view = dlg.findChild(QtWidgets.QListView, "listView")
            if file_view:
                file_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            tree_view = dlg.findChild(QtWidgets.QTreeView)
            if tree_view:
                tree_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                for path in dlg.selectedFiles():
                    if os.path.isdir(path):
                        for album_path in _expand_to_album_dirs(
                                path, max_depth=preferences.scan_depth()):
                            self._add_directory(album_path)

        def _remove_selected(self) -> None:
            rows = sorted(
                {idx.row() for idx in self._table.selectedIndexes()},
                reverse=True,
            )
            for row in rows:
                self._table.removeRow(row)

        def _clear_all(self) -> None:
            self._table.setRowCount(0)

        def _refresh_queue(self) -> None:
            """Re-check every queued folder against the disk
            (File → Refresh): drop rows whose directory no longer
            exists and re-guess each remaining album name from the
            folder's current tags."""
            refreshed = 0
            was_sorted = self._table.isSortingEnabled()
            self._table.setSortingEnabled(False)
            try:
                for row in reversed(range(self._table.rowCount())):
                    dir_item = self._table.item(row, 0)
                    directory = dir_item.text() if dir_item else ""
                    if not directory or not os.path.isdir(directory):
                        self._table.removeRow(row)
                        self._append_log(
                            f"✖  Removed missing folder: {directory}"
                        )
                        continue
                    album_item = self._table.item(row, 1)
                    if album_item:
                        album_item.setText(
                            guess_album_slug(directory).replace("_", " ")
                        )
                    refreshed += 1
            finally:
                self._table.setSortingEnabled(was_sorted)
            self._append_log(f"↻  Refreshed {refreshed} album folder(s).")

        # --- Run ---
        def _start_romanizing(self) -> None:
            if self._worker is not None and self._worker.isRunning():
                return
            if _refuse_if_writing(self, "romanise these albums"):
                return

            dirs: list[str] = []
            for row in range(self._table.rowCount()):
                dir_item = self._table.item(row, 0)
                if dir_item:
                    d = dir_item.text().strip()
                    if d:
                        dirs.append(d)

            if not dirs:
                QtWidgets.QMessageBox.information(
                    self, "Nothing to do",
                    "Add at least one album folder first."
                )
                return

            self._run_btn.setEnabled(False)
            self._run_btn.setText("Romanising…")
            self._cancel_btn.setEnabled(True)
            self._esc_shortcut.setEnabled(True)
            self._was_cancelled = False
            self._log.clear()
            self._results = []
            # Stash dirs so _on_all_done's auto-clear can match
            # successful results back to table rows by directory path,
            # which stays correct even if the user re-sorts the table
            # during or after the run.
            self._dirs = dirs
            # Reset progress bar for this run.
            self._progress.setRange(0, len(dirs))
            self._progress.setValue(0)
            self._progress.setVisible(True)

            self._worker = _RomanizeWorker(
                dirs,
                dry_run=self._dry_run_cb.isChecked(),
                force_titlesort=self._force_ts_cb.isChecked(),
            )
            self._worker.log_message.connect(self._append_log)
            self._worker.album_done.connect(self._on_album_done)
            self._worker.all_done.connect(self._on_all_done)
            _write_guard.acquire(_ROMANIZE_WRITER)
            self._worker.start()

        def _cancel_romanizing(self) -> None:
            # See WikiTaggerTab._cancel_tagging.
            if self._worker is None or not self._worker.isRunning():
                return
            if self._was_cancelled:
                return
            self._was_cancelled = True
            self._worker.request_cancel()
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling…")
            self._run_btn.setText("Cancelling — finishing current album…")
            self._append_log(
                "\n⏸  Cancel requested — finishing current album, "
                "then stopping."
            )

        @QtCore.pyqtSlot(str)
        def _append_log(self, text: str) -> None:
            self._log.appendPlainText(text)
            # Mirror to the session log file — see
            # WikiTaggerTab._append_log for rationale.
            logging.getLogger(LOGGER_NAME + ".gui").info(text)

        @QtCore.pyqtSlot(dict)
        def _on_album_done(self, result: dict) -> None:
            self._results.append(result)
            self._progress.setValue(self._progress.value() + 1)

        def _show_summary_dialog(self, summary: str) -> None:
            """Show the romanisation summary in a modal dialog."""
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Romaniser — Summary")
            dlg.setMinimumSize(520, 320)
            dlg.resize(640, 460)
            dlg_layout = QtWidgets.QVBoxLayout(dlg)
            text_edit = QtWidgets.QPlainTextEdit(summary)
            text_edit.setReadOnly(True)
            text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
            dlg_layout.addWidget(text_edit, stretch=1)
            close_btn = QtWidgets.QPushButton("&Close")
            close_btn.setDefault(True)
            close_btn.clicked.connect(dlg.accept)
            btn_layout = QtWidgets.QHBoxLayout()
            btn_layout.addStretch()
            btn_layout.addWidget(close_btn)
            dlg_layout.addLayout(btn_layout)
            dlg.exec_()

        @QtCore.pyqtSlot()
        def _on_all_done(self) -> None:
            _write_guard.release(_ROMANIZE_WRITER)
            self._run_btn.setEnabled(True)
            self._run_btn.setText("&Romanise All")
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Ca&ncel")
            self._esc_shortcut.setEnabled(False)
            self._worker = None

            dry = self._dry_run_cb.isChecked()
            completed = [r for r in self._results if not r["error"]]
            succeeded = [r for r in completed if not _has_write_errors(r)]
            partial = [r for r in completed if _has_write_errors(r)]
            failed    = [r for r in self._results if r["error"]]

            lines = []
            # See WikiTaggerTab._on_all_done for the cancel-header
            # placement rationale.
            if self._was_cancelled:
                processed = len(self._results)
                total = len(self._dirs)
                lines.append(
                    f"⏹  Cancelled — processed {processed} of {total} "
                    "album(s) before stopping.\n"
                )
            for albums, bullet, heading in (
                (succeeded, "✓",
                 f"Successfully processed {len(succeeded)} album(s):\n"),
                (partial, "⚠",
                 f"Finished with write errors — {len(partial)} album(s) "
                 "stay in the queue for a retry:\n"),
            ):
                if not albums:
                    continue
                if lines:
                    lines.append("")
                lines.append(heading)
                rm_action = "Would write" if dry else "Wrote"
                for r in albums:
                    lines.append(
                        f"  {bullet} {r['album']}\n"
                        f"      {rm_action}: {r['romanized']} new, "
                        f"{r['overwritten']} overwritten  |  "
                        f"Skipped: {r['skipped']}  |  "
                        f"No title: {r['no_title']}  |  "
                        f"Errors: {r['errors']}"
                    )

            if failed:
                if succeeded or partial:
                    lines.append("")
                lines.append(
                    f"Failed to process {len(failed)} album(s):\n"
                )
                for r in failed:
                    lines.append(f"  ✗ {r['album']}  — {r['error']}")

            total_r  = sum(r["romanized"]   for r in self._results)
            total_ow = sum(r["overwritten"] for r in self._results)
            total_s  = sum(r["skipped"]     for r in self._results)
            total_nt = sum(r["no_title"]    for r in self._results)
            total_e  = sum(r["errors"]      for r in self._results)
            action = "Would write" if dry else "Wrote"
            lines.append(
                f"\nTotals — {action}: {total_r} new, "
                f"{total_ow} overwritten  |  Skipped: {total_s}  |  "
                f"No title: {total_nt}  |  Errors: {total_e}"
            )
            if dry and total_r + total_ow > 0:
                lines.append(
                    "\nThis was a dry run — uncheck 'Dry run' "
                    "and run again to apply."
                )

            summary = "\n".join(lines)
            self._log.appendPlainText(f"\n{'=' * 60}")
            self._log.appendPlainText(summary)

            if not self._shutting_down:
                self._show_summary_dialog(summary)

            if self._auto_clear_cb.isChecked() and succeeded:
                # Match successful results to table rows by directory
                # path, not by index — see WikiTaggerTab._on_all_done
                # for rationale.  `self._dirs[i]` holds the directory
                # for result `self._results[i]`.
                # Albums whose individual writes failed are kept in the
                # queue for a retry — see _has_write_errors.
                success_dirs = {
                    self._dirs[i]
                    for i, r in enumerate(self._results)
                    if not r["error"] and not _has_write_errors(r)
                }
                rows_to_remove = sorted(
                    (
                        row for row in range(self._table.rowCount())
                        if (item := self._table.item(row, 0))
                        and item.text() in success_dirs
                    ),
                    reverse=True,
                )
                for row in rows_to_remove:
                    self._table.removeRow(row)

    # =====================================================================
    # Tag Edit tab — manual per-track tag editing
    # =====================================================================
    # Human-readable column headers for the editable tag fields.
    _TAG_DISPLAY = {
        "grouping":        "Grouping",
        "title":           "Title",
        "titlesort":       "Title Sort",
        "album":           "Album",
        "albumartist":     "Album Artist",
        "albumartistsort": "Album Artist Sort",
        "artist":          "Artist",
        "artistsort":      "Artist Sort",
        "arranger":        "Arranger",
        "vocalist":        "Vocalist",
        "lyricist":        "Lyricist",
        "catalognumber":   "Catalog No.",
        "date":            "Date",
        "year":            "Year",
    }

    # Padlock gutter geometry for the Tag Edit table.  One helper serves the
    # delegate's paint, the click hit-test and the elision measurement, so the
    # three can never drift apart.
    _LOCK_W = 14
    _LOCK_PAD = 2
    _LOCK_MIN_TEXT_W = 24

    def _lock_rect(rect: "QtCore.QRect") -> "QtCore.QRect":
        """The padlock's paint *and* hit rect inside a cell rect.

        Returns a null rect when the column is too narrow to give the icon a
        strip without hiding the value: the failure mode for a hand-narrowed
        column is then no lock UI at all, never an invisible hot zone that
        swallows clicks meant for the cell.
        """
        side = min(_LOCK_W, rect.height() - 2 * _LOCK_PAD)
        if (side < 8
                or rect.width() < side + 2 * _LOCK_PAD + _LOCK_MIN_TEXT_W):
            return QtCore.QRect()
        top = rect.top() + (rect.height() - side) // 2
        return QtCore.QRect(rect.left() + _LOCK_PAD, top, side, side)

    def _lock_strip(rect: "QtCore.QRect") -> int:
        """Horizontal space the padlock takes from the cell's text."""
        r = _lock_rect(rect)
        return 0 if r.isNull() else r.width() + 2 * _LOCK_PAD

    class _LockDelegate(QtWidgets.QStyledItemDelegate):
        """Paints a padlock in a narrow gutter of each tag cell, and toggles
        it on click.

        Installed per column (1..N) via setItemDelegateForColumn, so it never
        sees an album header row: headers are spanned from column 0 and are
        therefore painted by column 0's delegate.
        """

        def __init__(self, table: "QtWidgets.QTableWidget") -> None:
            super().__init__(table)
            self._table = table

        def paint(self, painter, option, index) -> None:
            rect = _lock_rect(option.rect)
            if rect.isNull():
                super().paint(painter, option, index)
                return

            # 1. Full-width background and selection highlight with no text,
            #    so the gutter is not an unhighlighted notch on a selected row.
            bg = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(bg, index)
            bg.text = ""
            widget = bg.widget
            style = (widget.style() if widget is not None
                     else QtWidgets.QApplication.style())
            style.drawControl(
                QtWidgets.QStyle.CE_ItemViewItem, bg, painter, widget
            )

            # 2. Qt's own text layout and elision, shrunk by the gutter.
            opt = QtWidgets.QStyleOptionViewItem(option)
            opt.rect = option.rect.adjusted(
                _lock_strip(option.rect), 0, 0, 0
            )
            super().paint(painter, opt, index)

            # 3. The padlock: solid when locked, a faint hint under the
            #    cursor so an unlocked cell still advertises the click target.
            locked = self._table.is_locked_cell(index)
            hovered = bool(bg.state & QtWidgets.QStyle.State_MouseOver)
            if locked or hovered:
                self._paint_padlock(painter, rect, bg, locked=locked)

        def sizeHint(self, option, index):
            size = super().sizeHint(option, index)
            size.setWidth(size.width() + _LOCK_W + 2 * _LOCK_PAD)
            return size

        def editorEvent(self, event, model, option, index) -> bool:
            """Toggle the lock when the padlock itself is clicked.

            Qt's own check indicators are handled here rather than in the
            view's mousePressEvent, and for the same two reasons: this hook
            gets the exact rect paint() was given (no viewport-offset or
            hidden-column arithmetic), and it runs before the edit trigger, so
            consuming the press stops an editor from opening over the icon.
            """
            if event.type() not in (
                    QtCore.QEvent.MouseButtonPress,
                    QtCore.QEvent.MouseButtonRelease,
                    QtCore.QEvent.MouseButtonDblClick):
                return super().editorEvent(event, model, option, index)
            if event.button() != QtCore.Qt.LeftButton:
                return False
            rect = _lock_rect(option.rect)
            if rect.isNull() or not rect.contains(event.pos()):
                return False
            # Consume press and double-click; act on release, matching
            # QStyledItemDelegate's own check-indicator behaviour.
            if event.type() == QtCore.QEvent.MouseButtonRelease:
                self._table.toggle_lock(index)
            return True

        @staticmethod
        def _paint_padlock(painter, rect, opt, *, locked: bool) -> None:
            """Draw a padlock with QPainter.

            Drawn rather than loaded: QIcon.fromTheme is null without an icon
            theme and carries a fixed hue that fights a dark palette, and an
            emoji glyph renders as a colour bitmap that ignores the pen.  A
            painted lock takes its colour from the palette, so light/dark and
            selected-row correctness come for free.
            """
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            color = opt.palette.color(
                QtGui.QPalette.HighlightedText
                if opt.state & QtWidgets.QStyle.State_Selected
                else QtGui.QPalette.Text
            )
            if not locked:
                color.setAlpha(90)
            w, h = rect.width(), rect.height()
            stroke = max(1.0, w * 0.11)
            body = QtCore.QRectF(
                rect.left() + w * 0.12, rect.top() + h * 0.46,
                w * 0.76, h * 0.46,
            )
            shackle = QtCore.QRectF(
                rect.left() + w * 0.28, rect.top() + h * 0.10,
                w * 0.44, h * 0.48,
            )

            painter.setPen(QtGui.QPen(
                color, stroke, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap
            ))
            painter.setBrush(QtCore.Qt.NoBrush)
            # Angles are in 1/16th degrees: the shackle's top half.
            painter.drawArc(shackle, 0, 180 * 16)
            painter.drawLine(
                QtCore.QPointF(shackle.left(), shackle.center().y()),
                QtCore.QPointF(shackle.left(), body.top()),
            )
            if locked:
                # Closed: both legs reach the body.
                painter.drawLine(
                    QtCore.QPointF(shackle.right(), shackle.center().y()),
                    QtCore.QPointF(shackle.right(), body.top()),
                )
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(body, w * 0.12, w * 0.12)
            else:
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRoundedRect(
                    body.adjusted(
                        stroke / 2, stroke / 2, -stroke / 2, -stroke / 2
                    ),
                    w * 0.12, w * 0.12,
                )
            painter.restore()

    class _TagEditTable(QtWidgets.QTableWidget):
        """QTableWidget that shows a tooltip with the full cell value
        only when the text is too wide for its column and is being
        rendered with an ellipsis.

        Qt's default item-view tooltip would require keeping each
        cell's ``toolTip`` in sync with edits; instead we compute
        elision on demand in the ToolTip event, so it stays correct
        for free as columns are resized and values are edited.
        """

        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            # Locks are read from the tab's snapshot dict, shared by reference
            # so a paint costs one lookup and never re-normalises a path.  Own
            # dict per instance until set_lock_source replaces it.
            self._locks: "dict[str, frozenset[str]]" = {}

        def set_lock_source(
            self, locks: "dict[str, frozenset[str]]"
        ) -> None:
            self._locks = locks

        def _cell_lock_key(
            self, index: "QtCore.QModelIndex"
        ) -> "tuple[str, str] | None":
            """The (filepath, tag) a cell locks, or None for a non-tag cell."""
            col = index.column()
            if col < 1 or col > len(EDITABLE_TAGS):
                return None
            item = self.item(index.row(), 0)
            if item is None:
                return None
            data = item.data(QtCore.Qt.UserRole)
            if not data or data == "header":
                return None
            return data, EDITABLE_TAGS[col - 1]

        def is_locked_cell(self, index: "QtCore.QModelIndex") -> bool:
            key = self._cell_lock_key(index)
            if key is None:
                return False
            filepath, tag_name = key
            return tag_name in self._locks.get(filepath, frozenset())

        def toggle_lock(self, index: "QtCore.QModelIndex") -> None:
            """Lock or unlock one tag on one file, and repaint that cell."""
            key = self._cell_lock_key(index)
            if key is None:
                return
            filepath, tag_name = key
            locked = tag_name in self._locks.get(filepath, frozenset())
            tag_locks.set_lock(filepath, tag_name, not locked)
            self._locks[filepath] = tag_locks.locked_tags(filepath)
            self.viewport().update(self.visualRect(index))

        def viewportEvent(self, event: QtCore.QEvent) -> bool:
            if event.type() == QtCore.QEvent.ToolTip:
                index = self.indexAt(event.pos())
                if index.isValid():
                    # The padlock only shows a hint under the cursor, so its
                    # tooltip is what makes the feature discoverable at all.
                    if (self._cell_lock_key(index) is not None
                            and _lock_rect(self.visualRect(index))
                            .contains(event.pos())):
                        QtWidgets.QToolTip.showText(
                            event.globalPos(),
                            "Locked — the Wiki Tagger will not change this "
                            "tag.\nClick to unlock."
                            if self.is_locked_cell(index) else
                            "Click to lock this tag against the Wiki Tagger.",
                            self.viewport(),
                        )
                        return True
                    text = index.data(QtCore.Qt.DisplayRole)
                    if text and self._is_elided(index, str(text)):
                        QtWidgets.QToolTip.showText(
                            event.globalPos(), str(text), self.viewport()
                        )
                    else:
                        QtWidgets.QToolTip.hideText()
                    return True
                QtWidgets.QToolTip.hideText()
                return True
            return super().viewportEvent(event)

        def _is_elided(
            self, index: "QtCore.QModelIndex", text: str
        ) -> bool:
            """True when ``text`` doesn't fit the column's content width."""
            item = self.item(index.row(), index.column())
            font = item.font() if item is not None else self.font()
            fm = QtGui.QFontMetrics(font)
            try:
                text_w = fm.horizontalAdvance(text)
            except AttributeError:  # Qt < 5.11
                text_w = fm.width(text)
            # Leave room for the cell's left/right text margins, and for the
            # padlock gutter the delegate takes out of the same width, so a
            # value that only just fits isn't flagged as elided.
            avail = (self.columnWidth(index.column()) - 8
                     - _lock_strip(self.visualRect(index)))
            return text_w > avail

    class TagEditTab(QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.setAcceptDrops(True)

            # Dirty tracking — keyed by (filepath, tag_name) so row
            # reordering never invalidates entries.
            self._original_values: dict[tuple[str, str], str] = {}
            self._dirty: set[tuple[str, str]] = set()
            self._batch_updating: bool = False

            # Painting snapshot of the persistent tag locks, keyed by the raw
            # filepath string as stored in the table so the padlock delegate
            # needs one dict lookup and never re-normalises a path per paint.
            self._locks: dict[str, frozenset[str]] = {}

            # --- Layout: splitter (main | sidebar) --------------------
            outer = QtWidgets.QHBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            splitter.setChildrenCollapsible(False)
            outer.addWidget(splitter)

            main_widget = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(main_widget)

            layout.addWidget(QtWidgets.QLabel(
                "Edit tags on the albums below.  Select multiple "
                "tracks and edit a cell to batch-apply the value "
                "across the selection.  Saving an edit locks that tag "
                "against the Wiki Tagger; click the padlock in a cell to "
                "lock or unlock it by hand."
            ))

            # --- Tag table -------------------------------------------
            ncols = 1 + len(EDITABLE_TAGS)
            self._table = _TagEditTable(0, ncols)
            headers = ["Track #"] + [
                _TAG_DISPLAY.get(t, t) for t in EDITABLE_TAGS
            ]
            self._table.setHorizontalHeaderLabels(headers)
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeToContents,
            )
            for i in range(1, ncols):
                header.setSectionResizeMode(
                    i, QtWidgets.QHeaderView.Interactive,
                )
                header.resizeSection(i, 120)
            self._table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            self._table.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection
            )
            self._table.setAcceptDrops(False)
            self._table.cellChanged.connect(self._on_cell_changed)
            # Padlock gutter.  Per-column so the delegate never sees a spanned
            # album header row, and mouse tracking so QAbstractItemView keeps
            # State_MouseOver current — that is the whole hover mechanism; a
            # hand-rolled hover index would repaint the entire table on every
            # mouse move.
            self._table.set_lock_source(self._locks)
            self._lock_delegate = _LockDelegate(self._table)
            for col in range(1, ncols):
                self._table.setItemDelegateForColumn(
                    col, self._lock_delegate
                )
            self._table.setMouseTracking(True)
            self._table.viewport().setMouseTracking(True)
            layout.addWidget(self._table, stretch=2)

            # Add Folders / Remove Selected / Clear All / Refresh live
            # in the window's File menu (see TaggerWindow), which
            # dispatches to this tab's _add_folders/_remove_selected/
            # _clear_all/_refresh_queue when it is the active tab.

            # --- Save row --------------------------------------------
            save_row = QtWidgets.QHBoxLayout()
            self._save_btn = QtWidgets.QPushButton("&Save Changes")
            self._save_btn.setMinimumHeight(36)
            font = self._save_btn.font()
            font.setPointSize(font.pointSize() + 1)
            font.setBold(True)
            self._save_btn.setFont(font)
            self._save_btn.clicked.connect(self._save_changes)
            save_row.addWidget(self._save_btn, stretch=1)
            layout.addLayout(save_row)

            # --- Status label ----------------------------------------
            self._status_label = QtWidgets.QLabel("No changes.")
            layout.addWidget(self._status_label)

            # --- Right side: column visibility toggles ----------------
            sidebar = QtWidgets.QGroupBox("Visible Columns")
            sidebar.setMinimumWidth(220)
            sidebar_layout = QtWidgets.QVBoxLayout(sidebar)
            sidebar_layout.setAlignment(QtCore.Qt.AlignTop)

            self._col_checkboxes: list[QtWidgets.QCheckBox] = []
            for i, tag in enumerate(EDITABLE_TAGS):
                label = _TAG_DISPLAY.get(tag, tag)
                cb = QtWidgets.QCheckBox(label)
                cb.setChecked(True)
                col_idx = i + 1  # Column 0 is Track
                cb.toggled.connect(
                    lambda on, c=col_idx:
                        self._table.setColumnHidden(c, not on)
                )
                sidebar_layout.addWidget(cb)
                self._col_checkboxes.append(cb)

            sidebar_layout.addStretch()

            # --- Wire both panes into the splitter --------------------
            splitter.addWidget(main_widget)
            splitter.addWidget(sidebar)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
            splitter.setSizes([900, 220])

            # --- Context menu (right-click Replace…) ----------------------
            self._table.setContextMenuPolicy(
                QtCore.Qt.CustomContextMenu
            )
            self._table.customContextMenuRequested.connect(
                self._show_context_menu
            )

            # --- Keyboard shortcuts -----------------------------------
            del_sc = QtWidgets.QShortcut(
                QtGui.QKeySequence(QtCore.Qt.Key_Delete), self._table
            )
            del_sc.setContext(QtCore.Qt.WidgetShortcut)
            del_sc.activated.connect(self._remove_selected)

        # --- Public API (used by "Send to…" and TaggerWindow) ---
        def add_directory(self, path: str) -> None:
            """Public entry point for cross-tab 'Send to…' transfers
            and direct drag-and-drop."""
            self._add_directory(path)

        def has_unsaved_changes(self) -> bool:
            """True when there are edits not yet written to disk."""
            return bool(self._dirty)

        def reload_locks(self) -> None:
            """Re-read every queued file's locks and repaint the padlocks.

            Called after a configuration import replaces the lock store
            wholesale; the in-table snapshot would otherwise stay stale.
            """
            for filepath in list(self._locks):
                self._locks[filepath] = tag_locks.locked_tags(filepath)
            self._table.viewport().update()

        # --- Drag & drop ---
        def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()

        def dropEvent(self, event: QtGui.QDropEvent) -> None:
            """Accept whole folders and individual music files.

            Dropping files shows only those tracks, under one header for the
            album that owns them; dropping the folder later merges the rest
            of the album into the same block.
            """
            dirs: list[str] = []
            by_album: dict[str, list[str]] = {}
            ignored = 0
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if not path:
                    continue
                if os.path.isdir(path):
                    dirs.extend(_expand_to_album_dirs(
                        path, max_depth=preferences.scan_depth()))
                elif (os.path.splitext(path)[1].lower()
                        in SUPPORTED_EXTENSIONS):
                    by_album.setdefault(
                        album_dir_for_file(path), []
                    ).append(os.path.abspath(path))
                else:
                    ignored += 1

            # Whole folders first, so a drop holding both a folder and one of
            # its files ends up showing the full album rather than one track.
            for album_path in dirs:
                self._add_tracks(album_path)
            for album_path, files in by_album.items():
                self._add_tracks(album_path, files)
            if ignored:
                self._status_label.setText(
                    f"Ignored {ignored} unsupported file(s)."
                )

        # --- Table population ---
        def _add_directory(self, path: str) -> None:
            """Show every track in *path* (the whole-folder entry point)."""
            self._add_tracks(path)

        def _add_tracks(
            self, album_path: str, wanted: "list[str] | None" = None
        ) -> None:
            """Show tracks from *album_path*, creating or extending its block.

            ``wanted`` limits the display to those filepaths (a partial drop);
            ``None`` means the whole folder.  Both the ordering walk and
            ``multi_disc`` come from the *full* folder scan, never from the
            subset: that is what puts a merged track in its album position
            rather than at the top of the block, and what makes a partial
            block's labels identical to the ones the whole folder would
            produce, so a later merge needs no relabelling.
            """
            album_key = os.path.normpath(os.path.abspath(album_path))
            tracks = scan_music_files(album_key)
            if not tracks:
                return
            multi_disc = len({t["disc"] for t in tracks}) > 1

            # The full track list is kept even for a partial add: it is what
            # gives every insert its correct position within the album's own
            # order.  `keep` only decides which of them actually get a row.
            keep = (None if wanted is None
                    else {os.path.abspath(p) for p in wanted})
            if keep is not None and not any(
                    os.path.abspath(t["path"]) in keep for t in tracks):
                return

            self._batch_updating = True
            was_sorted = self._table.isSortingEnabled()
            self._table.setSortingEnabled(False)
            try:
                header_row = self._find_header_row(album_key)
                if header_row is None:
                    header_row = self._append_header_row(
                        album_key, is_full=wanted is None
                    )
                elif wanted is None:
                    # A whole-folder add promotes the block permanently, so
                    # File → Refresh keeps re-expanding it.
                    self._table.item(header_row, 0).setData(
                        QtCore.Qt.UserRole + 2, True
                    )

                # Walk the album's own track order and insert whatever is
                # missing directly after the previous track that is present.
                # The insertion point is re-derived from the table on every
                # iteration, so no cached row index can go stale as earlier
                # inserts shift the rows below them.  header_row itself never
                # moves: every insert is strictly below it.
                prev_row = header_row
                for t in tracks:
                    row = self._find_row_in_block(header_row, t["path"])
                    if row is not None:
                        prev_row = row
                        continue
                    if (keep is not None
                            and os.path.abspath(t["path"]) not in keep):
                        # Not asked for: leave the gap, and keep prev_row on
                        # the last row that *is* shown so the next wanted
                        # track still lands in album order.
                        continue
                    self._insert_track_row(prev_row + 1, t, multi_disc)
                    prev_row += 1
                self._reapply_header_spans()
            finally:
                self._table.setSortingEnabled(was_sorted)
                self._batch_updating = False

        def _append_header_row(self, album_key: str, *, is_full: bool) -> int:
            """Add an album header row at the end of the table; return it."""
            album_name = guess_album_slug(album_key).replace("_", " ")
            header_row = self._table.rowCount()
            self._table.insertRow(header_row)
            header_item = QtWidgets.QTableWidgetItem(
                f"\U0001F4C1 {album_name}  —  {album_key}"
            )
            header_item.setData(QtCore.Qt.UserRole, "header")
            header_item.setData(QtCore.Qt.UserRole + 1, album_key)
            # Whether this block shows the whole folder or only the files the
            # user dropped.  _refresh_queue needs the difference: a full block
            # must re-expand to whatever is on disk now, a partial one must
            # stay partial.
            header_item.setData(QtCore.Qt.UserRole + 2, is_full)
            header_item.setFlags(
                header_item.flags()
                & ~QtCore.Qt.ItemIsEditable
            )
            hfont = header_item.font()
            hfont.setBold(True)
            header_item.setFont(hfont)
            # Tint the header row so albums are visually distinct.
            is_dark = (
                self.palette().window().color().lightness() < 128
            )
            bg = (QtGui.QColor(60, 60, 80) if is_dark
                  else QtGui.QColor(220, 225, 235))
            header_item.setBackground(bg)
            self._table.setItem(header_row, 0, header_item)
            # Fill remaining header columns (non-editable).
            for col in range(1, self._table.columnCount()):
                spacer = QtWidgets.QTableWidgetItem("")
                spacer.setFlags(
                    spacer.flags()
                    & ~QtCore.Qt.ItemIsEditable
                    & ~QtCore.Qt.ItemIsSelectable
                )
                spacer.setBackground(bg)
                self._table.setItem(header_row, col, spacer)
            return header_row

        def _insert_track_row(
            self, row: int, track: dict, multi_disc: bool
        ) -> None:
            """Insert one track row at *row* and record its baseline values."""
            filepath = track["path"]
            all_tags = read_all_tags(filepath)
            self._table.insertRow(row)

            # Column 0: track label (non-editable, stores path)
            track_item = QtWidgets.QTableWidgetItem(
                _format_track_number(track, multi_disc)
            )
            track_item.setData(QtCore.Qt.UserRole, filepath)
            track_item.setFlags(
                track_item.flags()
                & ~QtCore.Qt.ItemIsEditable
            )
            self._table.setItem(row, 0, track_item)

            # Columns 1..N: editable tag fields
            for i, tag_name in enumerate(EDITABLE_TAGS):
                value = all_tags.get(tag_name) or ""
                cell = QtWidgets.QTableWidgetItem(value)
                self._table.setItem(row, i + 1, cell)
                self._original_values[(filepath, tag_name)] = value
            self._locks[filepath] = tag_locks.locked_tags(filepath)

        def _find_header_row(self, album_key: str) -> int | None:
            """Row of the header for *album_key*, or None when absent."""
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if (item
                        and item.data(QtCore.Qt.UserRole) == "header"
                        and item.data(QtCore.Qt.UserRole + 1) == album_key):
                    return row
            return None

        def _find_row_in_block(
            self, header_row: int, filepath: str
        ) -> int | None:
            """Row holding *filepath* inside one album block, or None.

            Block-scoped on purpose: the table-wide _find_row_for_filepath
            could return a row under a *different* header if the same file
            ever appeared twice, which would send an insert outside the block.
            """
            for row in range(header_row + 1, self._table.rowCount()):
                item = self._table.item(row, 0)
                if not item:
                    continue
                data = item.data(QtCore.Qt.UserRole)
                if data == "header":
                    return None
                if data == filepath:
                    return row
            return None

        def _reapply_header_spans(self) -> None:
            """Re-issue every header row's full-width span.

            Idempotent, and cheap (one call per album).  Rows inserted into
            the middle of the table shift the spans below them, so rather
            than reason about Qt's span bookkeeping we simply restate it.
            """
            ncols = self._table.columnCount()
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.data(QtCore.Qt.UserRole) == "header":
                    self._table.setSpan(row, 0, 1, ncols)

        def _add_folders(self) -> None:
            dlg = QtWidgets.QFileDialog(
                self, "Select Album Folders"
            )
            dlg.setFileMode(QtWidgets.QFileDialog.Directory)
            dlg.setOption(
                QtWidgets.QFileDialog.ShowDirsOnly, True
            )
            dlg.setOption(
                QtWidgets.QFileDialog.DontUseNativeDialog, True
            )
            file_view = dlg.findChild(
                QtWidgets.QListView, "listView"
            )
            if file_view:
                file_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            tree_view = dlg.findChild(QtWidgets.QTreeView)
            if tree_view:
                tree_view.setSelectionMode(
                    QtWidgets.QAbstractItemView.ExtendedSelection
                )
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                for path in dlg.selectedFiles():
                    if os.path.isdir(path):
                        for album_path in _expand_to_album_dirs(
                                path, max_depth=preferences.scan_depth()):
                            self._add_directory(album_path)

        def _remove_selected(self) -> None:
            """Remove entire album blocks for any selected row."""
            selected_rows = sorted(
                {idx.row() for idx in self._table.selectedIndexes()}
            )
            if not selected_rows:
                return

            # Walk each selected row up to its album header.
            headers_to_remove: set[int] = set()
            for row in selected_rows:
                item = self._table.item(row, 0)
                if not item:
                    continue
                if item.data(QtCore.Qt.UserRole) == "header":
                    headers_to_remove.add(row)
                else:
                    for r in range(row - 1, -1, -1):
                        h = self._table.item(r, 0)
                        if (h and h.data(QtCore.Qt.UserRole)
                                == "header"):
                            headers_to_remove.add(r)
                            break

            # For each header, collect it + all track rows below it
            # until the next header (or end of table).
            rows_to_remove: set[int] = set()
            for hr in headers_to_remove:
                rows_to_remove.add(hr)
                for r in range(hr + 1, self._table.rowCount()):
                    item = self._table.item(r, 0)
                    if not item:
                        continue
                    if item.data(QtCore.Qt.UserRole) == "header":
                        break
                    filepath = item.data(QtCore.Qt.UserRole)
                    rows_to_remove.add(r)
                    # Clean up tracking dicts
                    if filepath:
                        self._locks.pop(filepath, None)
                        for tag_name in EDITABLE_TAGS:
                            key = (filepath, tag_name)
                            self._original_values.pop(key, None)
                            self._dirty.discard(key)

            for row in sorted(rows_to_remove, reverse=True):
                # Clear span before removing so Qt doesn't get
                # confused by spanned rows disappearing.
                self._table.setSpan(row, 0, 1, 1)
                self._table.removeRow(row)
            self._update_status()

        def _clear_all(self) -> None:
            if self._dirty:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Unsaved changes",
                    "You have unsaved changes.  Clear anyway?",
                    QtWidgets.QMessageBox.Ok
                    | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel,
                )
                if reply != QtWidgets.QMessageBox.Ok:
                    return
            self._batch_updating = True
            self._table.setRowCount(0)
            self._batch_updating = False
            self._original_values.clear()
            self._dirty.clear()
            self._locks.clear()
            self._update_status()

        def _refresh_queue(self) -> None:
            """Re-load every queued album from disk (File → Refresh),
            picking up tag or structure changes made outside the
            program.  All rows are rebuilt from the current on-disk
            tags, so unsaved edits would be lost — confirm first.
            Folders that no longer exist (or no longer contain audio)
            drop out of the table."""
            # Capture each block's identity *and* whether it shows the whole
            # folder before the table is cleared: a full block must re-expand
            # to whatever is on disk now (refresh's whole purpose), while a
            # block built from dropped files must stay limited to them.
            blocks: list[tuple[str, bool, list[str]]] = []
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if not item:
                    continue
                data = item.data(QtCore.Qt.UserRole)
                if data == "header":
                    blocks.append((
                        item.data(QtCore.Qt.UserRole + 1),
                        bool(item.data(QtCore.Qt.UserRole + 2)),
                        [],
                    ))
                elif blocks and data:
                    blocks[-1][2].append(data)
            if not blocks:
                return
            if self._dirty:
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Unsaved changes",
                    "You have unsaved changes.  Refreshing re-reads "
                    "all tags from disk and will discard them.  "
                    "Refresh anyway?",
                    QtWidgets.QMessageBox.Ok
                    | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel,
                )
                if reply != QtWidgets.QMessageBox.Ok:
                    return
            self._batch_updating = True
            self._table.setRowCount(0)
            self._batch_updating = False
            self._original_values.clear()
            self._dirty.clear()
            self._locks.clear()
            for path, is_full, files in blocks:
                if os.path.isdir(path):
                    self._add_tracks(path, None if is_full else files)
            self._update_status()

        # --- Cell editing & batch propagation ---
        def _on_cell_changed(self, row: int, col: int) -> None:
            if self._batch_updating or col == 0:
                return

            track_item = self._table.item(row, 0)
            if not track_item:
                return
            role_data = track_item.data(QtCore.Qt.UserRole)
            if role_data is None or role_data == "header":
                return

            filepath = role_data
            tag_name = EDITABLE_TAGS[col - 1]
            cell = self._table.item(row, col)
            new_value = cell.text().strip() if cell else ""
            original = self._original_values.get(
                (filepath, tag_name), ""
            )

            if new_value != original:
                self._dirty.add((filepath, tag_name))
            else:
                self._dirty.discard((filepath, tag_name))

            # Batch edit: propagate to all other selected track rows.
            selected_rows = {
                idx.row()
                for idx in self._table.selectedIndexes()
            }
            if len(selected_rows) > 1 and row in selected_rows:
                self._batch_updating = True
                try:
                    for sel_row in selected_rows:
                        if sel_row == row:
                            continue
                        item = self._table.item(sel_row, 0)
                        if not item:
                            continue
                        sel_role = item.data(QtCore.Qt.UserRole)
                        if sel_role is None or sel_role == "header":
                            continue

                        sel_fp = sel_role
                        sel_cell = self._table.item(sel_row, col)
                        if sel_cell is None:
                            sel_cell = QtWidgets.QTableWidgetItem("")
                            self._table.setItem(
                                sel_row, col, sel_cell
                            )
                        sel_cell.setText(new_value)

                        sel_orig = self._original_values.get(
                            (sel_fp, tag_name), ""
                        )
                        if new_value != sel_orig:
                            self._dirty.add((sel_fp, tag_name))
                        else:
                            self._dirty.discard((sel_fp, tag_name))
                finally:
                    self._batch_updating = False

            self._update_status()

        def _update_status(self) -> None:
            n = len(self._dirty)
            if n == 0:
                self._status_label.setText("No changes.")
            else:
                s = "s" if n != 1 else ""
                self._status_label.setText(
                    f"{n} unsaved change{s}."
                )

        # --- Save to disk ---
        def _save_changes(self) -> None:
            if not self._dirty:
                QtWidgets.QMessageBox.information(
                    self, "Save", "Nothing to save."
                )
                return
            if _refuse_if_writing(self, "save these edits"):
                return
            _write_guard.acquire(_TAG_EDIT_WRITER)

            errors: list[str] = []
            saved = 0
            # Every cell that reaches disk is locked, so the Wiki Tagger never
            # undoes a hand edit.  Collected from successful writes only — a
            # failed write must not leave a lock behind — and applied in one
            # batch so the lock store is saved once.
            to_lock: list[tuple[str, str]] = []
            for filepath, tag_name in list(self._dirty):
                row = self._find_row_for_filepath(filepath)
                if row is None:
                    # The row went away (removed from the queue) — there is
                    # no edit left to write, so drop it rather than leaving
                    # a pending change Save can never resolve.
                    self._dirty.discard((filepath, tag_name))
                    continue
                col = EDITABLE_TAGS.index(tag_name) + 1
                cell = self._table.item(row, col)
                value = cell.text().strip() if cell else ""

                try:
                    if value:
                        _set_tag(filepath, tag_name, value)
                    else:
                        _delete_tag(filepath, tag_name)
                    self._original_values[
                        (filepath, tag_name)
                    ] = value
                    to_lock.append((filepath, tag_name))
                    # Only a write that reached disk stops being pending.
                    # Clearing the whole dirty set would drop the failures
                    # too: Save could no longer retry them, and the
                    # close-time warning would no longer mention them.
                    self._dirty.discard((filepath, tag_name))
                    saved += 1
                except Exception as e:
                    errors.append(
                        f"{os.path.basename(filepath)} "
                        f"[{tag_name}]: {e}"
                    )
            _write_guard.release(_TAG_EDIT_WRITER)

            if to_lock:
                tag_locks.set_locks(to_lock, True)
                for filepath in {fp for fp, _ in to_lock}:
                    self._locks[filepath] = tag_locks.locked_tags(filepath)
                self._table.viewport().update()

            self._update_status()

            msg = (
                f"Saved {saved} tag "
                f"change{'s' if saved != 1 else ''}."
            )
            if to_lock:
                msg += (
                    f"\n\nLocked {len(to_lock)} tag(s) against the Wiki "
                    f"Tagger.  Click a padlock to unlock one."
                )
            if errors:
                msg += (
                    f"\n\n{len(errors)} error(s) — still unsaved, "
                    f"Save will retry them:\n"
                    + "\n".join(errors)
                )
                QtWidgets.QMessageBox.warning(self, "Save", msg)
                return
            QtWidgets.QMessageBox.information(self, "Save", msg)

        # --- Context menu (batch Replace…) ---
        def _show_context_menu(self, position) -> None:
            """Right-click on selected tracks → Replace… for the clicked column."""
            idx = self._table.indexAt(position)
            col = idx.column()
            if col < 1 or col > len(EDITABLE_TAGS):
                return

            tag_name = EDITABLE_TAGS[col - 1]
            display = _TAG_DISPLAY.get(tag_name, tag_name)

            # Collect selected track rows, skip headers.
            track_rows: list[int] = []
            for sel_idx in self._table.selectedIndexes():
                r = sel_idx.row()
                if r in (rr for rr in track_rows):
                    continue
                item = self._table.item(r, 0)
                if not item:
                    continue
                if item.data(QtCore.Qt.UserRole) == "header":
                    continue
                track_rows.append(r)
            # Deduplicate (selectedIndexes yields one per column per row).
            track_rows = sorted(set(track_rows))
            if not track_rows:
                return

            menu = QtWidgets.QMenu(self)
            n = len(track_rows)
            label = (
                f"Replace {display}…"
                if n == 1
                else f"Replace {display} across {n} tracks…"
            )
            menu.addAction(
                label,
                lambda _col=col, _tag=tag_name, _rows=list(track_rows):
                    self._replace_tag_values(_col, _tag, _rows),
            )
            menu.exec_(
                self._table.viewport().mapToGlobal(position)
            )

        def _replace_tag_values(
            self, col: int, tag_name: str, rows: list[int]
        ) -> None:
            """Show a Find → Replace dialog and apply to matching cells."""
            display = _TAG_DISPLAY.get(tag_name, tag_name)

            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle(f"Replace {display}")
            form = QtWidgets.QFormLayout(dlg)

            find_edit = QtWidgets.QLineEdit()
            find_edit.setPlaceholderText("Find (leave empty to match all)")
            form.addRow("&Find:", find_edit)

            replace_edit = QtWidgets.QLineEdit()
            replace_edit.setPlaceholderText("Replace with")
            form.addRow("&Replace:", replace_edit)

            case_cb = QtWidgets.QCheckBox("Case-sensitive")
            form.addRow(case_cb)

            btn_box = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok
                | QtWidgets.QDialogButtonBox.Cancel
            )
            btn_box.button(
                QtWidgets.QDialogButtonBox.Ok
            ).setText("Replace")
            btn_box.accepted.connect(dlg.accept)
            btn_box.rejected.connect(dlg.reject)
            form.addRow(btn_box)

            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                return

            find_text = find_edit.text()
            replace_text = replace_edit.text()
            case_sensitive = case_cb.isChecked()

            replaced = 0
            self._batch_updating = True
            try:
                for row in rows:
                    cell = self._table.item(row, col)
                    if cell is None:
                        cell = QtWidgets.QTableWidgetItem("")
                        self._table.setItem(row, col, cell)
                    old_val = cell.text()

                    # Compute new value.
                    if not find_text:
                        # Empty find → replace entire value.
                        new_val = replace_text
                    elif case_sensitive:
                        new_val = old_val.replace(
                            find_text, replace_text
                        )
                    else:
                        # Case-insensitive substring replace.
                        lower = old_val.lower()
                        needle = find_text.lower()
                        parts: list[str] = []
                        start = 0
                        while True:
                            idx = lower.find(needle, start)
                            if idx == -1:
                                parts.append(old_val[start:])
                                break
                            parts.append(old_val[start:idx])
                            parts.append(replace_text)
                            start = idx + len(needle)
                        new_val = "".join(parts)

                    if new_val == old_val:
                        continue

                    cell.setText(new_val)

                    # Dirty tracking.
                    track_item = self._table.item(row, 0)
                    if track_item:
                        filepath = track_item.data(
                            QtCore.Qt.UserRole
                        )
                        if filepath and filepath != "header":
                            orig = self._original_values.get(
                                (filepath, tag_name), ""
                            )
                            if new_val.strip() != orig:
                                self._dirty.add(
                                    (filepath, tag_name)
                                )
                            else:
                                self._dirty.discard(
                                    (filepath, tag_name)
                                )
                    replaced += 1
            finally:
                self._batch_updating = False

            self._update_status()
            if replaced:
                QtWidgets.QMessageBox.information(
                    self, "Replace",
                    f"Replaced {replaced} "
                    f"cell{'s' if replaced != 1 else ''}."
                )

        def _find_row_for_filepath(
            self, filepath: str
        ) -> int | None:
            """Return the table row whose column-0 UserRole stores
            *filepath*, or ``None`` if it's no longer in the table."""
            for row in range(self._table.rowCount()):
                item = self._table.item(row, 0)
                if item and item.data(QtCore.Qt.UserRole) == filepath:
                    return row
            return None

    # =====================================================================
    # Main window — hosts all tabs
    # =====================================================================
    class TaggerWindow(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Touhou Tagger")
            self.setMinimumSize(1020, 540)
            saved_gui = preferences.load().get("gui", {})
            self.resize(
                int(saved_gui.get("width", 1120)),
                int(saved_gui.get("height", 620)),
            )

            tabs = QtWidgets.QTabWidget()

            # --- Create tabs and store references --------------------
            wiki_tab = WikiTaggerTab()
            tabs.addTab(wiki_tab, "&Wiki Tagger")

            romanize_tab: RomanizeTab | None = None
            if ROMANIZER_AVAILABLE:
                romanize_tab = RomanizeTab()
                tabs.addTab(romanize_tab, "&Romanise")

            tag_edit_tab = TagEditTab()
            tabs.addTab(tag_edit_tab, "Tag &Edit")

            # Statistics tab — self-contained module.  Imported lazily here
            # (not at gui.py's top) so the CLI path never pulls in PyQt5.
            from library_stats import StatisticsTab
            stats_tab = StatisticsTab()
            tabs.addTab(stats_tab, "&Statistics")

            self._tag_edit_tab = tag_edit_tab
            self._tabs = tabs
            self._wiki_tab = wiki_tab
            self._romanize_tab = romanize_tab
            self._stats_tab = stats_tab
            # True once the close handler has told the workers to stop, so a
            # second close attempt while they finish doesn't re-ask.
            self._closing = False

            # --- File menu -------------------------------------------
            # Queue management (Add Folders / Remove Selected / Clear
            # All / Refresh) lives here rather than as per-tab buttons.
            # Each action dispatches to the *active* tab's handler; the
            # queue actions are enabled only on tabs that have a queue
            # (Wiki Tagger, Romanise, and Tag Edit).  Exit always works.
            file_menu = self.menuBar().addMenu("&File")

            self._act_add = file_menu.addAction("&Add Folders…")
            self._act_add.setShortcut(QtGui.QKeySequence.Open)
            self._act_add.triggered.connect(
                lambda: self._file_menu_call("_add_folders")
            )

            self._act_remove = file_menu.addAction("&Remove Selected")
            self._act_remove.triggered.connect(
                lambda: self._file_menu_call("_remove_selected")
            )

            self._act_clear = file_menu.addAction("C&lear All")
            self._act_clear.triggered.connect(
                lambda: self._file_menu_call("_clear_all")
            )

            file_menu.addSeparator()

            self._act_refresh = file_menu.addAction("Re&fresh")
            self._act_refresh.setShortcut(QtGui.QKeySequence.Refresh)
            self._act_refresh.setToolTip(
                "Re-check the queued folders for metadata or structure "
                "changes made outside the program (e.g. a split FLAC "
                "image)."
            )
            self._act_refresh.triggered.connect(
                lambda: self._file_menu_call("_refresh_queue")
            )

            file_menu.addSeparator()

            exit_act = file_menu.addAction("E&xit")
            exit_act.setShortcut(QtGui.QKeySequence.Quit)
            # close() routes through closeEvent, so the Tag Edit
            # unsaved-changes warning still applies.
            exit_act.triggered.connect(self.close)

            # --- Settings menu --------------------------------------
            settings_menu = self.menuBar().addMenu("&Settings")
            tools_act = settings_menu.addAction("&External tools…")
            tools_act.setToolTip(
                "Check external commands and configure executable paths"
            )
            tools_act.triggered.connect(self._open_external_tools_dialog)
            tag_selection_act = settings_menu.addAction("&Tag selection…")
            tag_selection_act.setToolTip(
                "Choose which Wiki Tagger fields are fetched and applied"
            )
            tag_selection_act.triggered.connect(
                wiki_tab._open_tag_selection_dialog
            )
            settings_menu.addSeparator()
            thwiki_auth_act = settings_menu.addAction(
                "THBWiki browser authentication…"
            )
            thwiki_auth_act.triggered.connect(
                wiki_tab._open_thwiki_auth_dialog
            )
            settings_menu.addSeparator()
            storage_act = settings_menu.addAction("Storage locations…")
            storage_act.setToolTip(
                "Show or change the per-user configuration and log folders"
            )
            storage_act.triggered.connect(self._open_storage_dialog)
            prefs_act = settings_menu.addAction("General preferences…")
            prefs_act.triggered.connect(self._open_preferences_dialog)
            backup_act = settings_menu.addAction("Export configuration…")
            backup_act.triggered.connect(self._export_configuration)
            import_act = settings_menu.addAction("Import configuration…")
            import_act.triggered.connect(self._import_configuration)

            tabs.currentChanged.connect(self._update_file_menu)
            last_tab = int(saved_gui.get("last_tab", 0))
            if 0 <= last_tab < tabs.count():
                tabs.setCurrentIndex(last_tab)
            self._update_file_menu()

            # --- Wire cross-tab "Send to…" targets -------------------
            wiki_tab._tab_widget = tabs
            wiki_tab._send_targets = []
            wiki_tab._send_targets.append(
                ("Tag Edit", tag_edit_tab)
            )
            if romanize_tab is not None:
                wiki_tab._send_targets.append(
                    ("Romanise", romanize_tab)
                )

            # Statistics tab can send artists to any of the other tabs.
            stats_tab._tab_widget = tabs
            stats_tab._send_targets = [
                ("Wiki Tagger", wiki_tab),
                ("Tag Edit", tag_edit_tab),
            ]
            if romanize_tab is not None:
                stats_tab._send_targets.insert(1, ("Romanise", romanize_tab))

            self.setCentralWidget(tabs)

            # Status bar: explain what's missing if the romaniser
            # didn't load (but only when the user might care — i.e.
            # they have the module file but not its deps).
            if ROMANIZER_AVAILABLE:
                if PYKAKASI_HINT_NEEDED:
                    self.statusBar().showMessage(
                        "Romaniser ready.  (Optional: pip install --user "
                        "pykakasi for better rare-kanji coverage.)"
                    )
            elif ROMANIZER_IMPORT_OK:
                # Module imported but is_ready() returned False —
                # MeCab or UniDic missing.
                self.statusBar().showMessage(
                    "Romanise tab disabled — install MeCab + UniDic to "
                    "enable.  See status: pip install --user "
                    "mecab-python3 unidic && python -m unidic download"
                )
            else:
                # Module file isn't even alongside the script.
                self.statusBar().showMessage(
                    "Romanise tab disabled — japanese_romanizer.py not "
                    "found alongside this script."
                )

            # Permanent right-side widget on the status bar showing
            # where this session's log file lives.  Permanent widgets
            # are not replaced by showMessage() calls above, so the
            # romaniser hint and the log location can coexist.
            # Skipped when file logging couldn't be set up at all.
            if log_path:
                log_label = QtWidgets.QLabel(f"Log: {log_path}")
                log_label.setToolTip(
                    "Path to this session's log file.  Share it when "
                    "reporting a crash.  Old logs are rotated; only "
                    f"the most recent {_MAX_LOG_FILES} are kept."
                )
                log_label.setStyleSheet("color: palette(text);")
                self.statusBar().addPermanentWidget(log_label)

        @staticmethod
        def _open_storage_path(path: str, parent) -> None:
            """Open a storage directory with the platform file manager."""
            try:
                availability.ensure_private_directory(path)
                ok = QtGui.QDesktopServices.openUrl(
                    QtCore.QUrl.fromLocalFile(path)
                )
            except OSError:
                ok = False
            if not ok:
                QtWidgets.QMessageBox.warning(
                    parent, "Open folder",
                    f"Could not open this folder:\n{path}",
                )

        def _open_storage_dialog(self) -> None:
            """Show and manage the active per-user config and log folders."""
            loc = availability.storage_locations()
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("Storage Locations")
            dlg.setModal(True)
            dlg.setMinimumWidth(760)
            layout = QtWidgets.QVBoxLayout(dlg)
            intro = QtWidgets.QLabel(
                "These are the folders used for the tagger's per-user settings "
                "and GUI logs. Changing them copies existing files without "
                "overwriting anything already in the destination. Restart the "
                "tagger after applying a change."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            form = QtWidgets.QFormLayout()
            config_edit = QtWidgets.QLineEdit(loc["config_dir"])
            log_edit = QtWidgets.QLineEdit(loc["log_dir"])
            for edit in (config_edit, log_edit):
                edit.setReadOnly(True)
                edit.setCursorPosition(0)

            def add_storage_row(label, edit, key):
                cell = QtWidgets.QWidget()
                row = QtWidgets.QHBoxLayout(cell)
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(edit, stretch=1)
                open_btn = QtWidgets.QPushButton("Open folder")
                open_btn.clicked.connect(
                    lambda _checked=False, _key=key:
                    self._open_storage_path(
                        (config_edit if _key == "config_dir" else log_edit).text(),
                        dlg,
                    )
                )
                row.addWidget(open_btn)
                change_btn = QtWidgets.QPushButton("Change location")
                change_btn.setEnabled(not bool(loc[key.replace("_dir", "_env")]))

                def choose(_checked=False, _edit=edit):
                    chosen = QtWidgets.QFileDialog.getExistingDirectory(
                        dlg, "Choose storage folder", _edit.text()
                    )
                    if chosen:
                        _edit.setText(os.path.abspath(chosen))

                change_btn.clicked.connect(choose)
                row.addWidget(change_btn)
                form.addRow(label, cell)

            add_storage_row("Configuration:", config_edit, "config_dir")
            add_storage_row("Logs:", log_edit, "log_dir")
            layout.addLayout(form)

            env_notes = []
            if loc["config_env"]:
                env_notes.append(
                    "Configuration is controlled by TOUHOU_TAGGER_CONFIG_DIR."
                )
            if loc["log_env"]:
                env_notes.append(
                    "Logs are controlled by TOUHOU_TAGGER_LOG_DIR."
                )
            note_text = (
                "Environment-variable locations cannot be changed from the GUI."
                if env_notes else
                "Reset settings returns both locations to platform defaults; "
                "it does not delete files from the old folders."
            )
            note = QtWidgets.QLabel(
                note_text + ("\n" + "\n".join(env_notes) if env_notes else "")
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(text);")
            layout.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Close
            )
            apply_btn = buttons.addButton(
                "Apply changes", QtWidgets.QDialogButtonBox.ApplyRole
            )
            reset_btn = buttons.addButton(
                "Reset settings", QtWidgets.QDialogButtonBox.ResetRole
            )

            def apply_locations() -> None:
                if (config_edit.text() == loc["config_dir"]
                        and log_edit.text() == loc["log_dir"]):
                    return
                if not availability.set_storage_locations(
                        config_edit.text(), log_edit.text()):
                    QtWidgets.QMessageBox.warning(
                        dlg, "Storage Locations",
                        "The locations could not be saved. Check whether an "
                        "environment variable controls one of them or whether "
                        "the destination is writable.",
                    )
                    return
                QtWidgets.QMessageBox.information(
                    dlg, "Storage Locations",
                    "The new locations are saved. Restart Touhou Tagger for "
                    "all settings and logging to use them.",
                )
                loc.update({
                    "config_dir": config_edit.text(),
                    "log_dir": log_edit.text(),
                })

            def reset_locations() -> None:
                reply = QtWidgets.QMessageBox.question(
                    dlg, "Reset storage settings",
                    "Return configuration and log storage to the platform "
                    "defaults? Existing files in the current folders will not "
                    "be deleted.",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )
                if reply != QtWidgets.QMessageBox.Yes:
                    return
                if not availability.reset_storage_locations():
                    QtWidgets.QMessageBox.warning(
                        dlg, "Storage Locations",
                        "The locations are controlled by environment variables "
                        "or could not be reset.",
                    )
                    return
                config_edit.setText(loc["default_config_dir"])
                log_edit.setText(loc["default_log_dir"])
                QtWidgets.QMessageBox.information(
                    dlg, "Storage Locations",
                    "Platform-default locations restored. Restart Touhou "
                    "Tagger for the change to take effect.",
                )

            apply_btn.clicked.connect(apply_locations)
            reset_btn.clicked.connect(reset_locations)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec_()

        def _open_preferences_dialog(self) -> None:
            """Edit general non-secret behavior preferences."""
            current = preferences.load()
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("General Preferences")
            dlg.setModal(True)
            layout = QtWidgets.QVBoxLayout(dlg)
            form = QtWidgets.QFormLayout()

            depth = QtWidgets.QComboBox()
            depth.addItem("1 level (artist → album)", 1)
            depth.addItem("2 levels", 2)
            depth.addItem("3 levels", 3)
            depth.setCurrentIndex(max(0, depth.findData(current["scan_depth"])))
            depth.setToolTip(
                "How many container-folder levels Add Folders and drag-and-drop "
                "may search before returning album folders."
            )
            form.addRow("Folder scan depth:", depth)

            cue_policy = QtWidgets.QComboBox()
            cue_policy.addItem("Move original to Trash (default)", "trash")
            cue_policy.addItem("Keep original", "keep")
            cue_policy.addItem("Ask every time", "ask")
            cue_policy.setCurrentIndex(
                max(0, cue_policy.findData(current["cue_post_processing"]))
            )
            cue_policy.setToolTip(
                "Applied only after every split output passes the existing "
                "decode and filename safety checks. Permanent deletion is not "
                "an available option."
            )
            form.addRow("CUE original handling:", cue_policy)
            layout.addLayout(form)

            note = QtWidgets.QLabel(
                "CUE splitting still requires a usable CUE, safe title decoding, "
                "successful FFmpeg output, and FLAC decode verification. The "
                "folder scan depth affects only how dropped/selected containers "
                "are expanded into album rows."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(text);")
            layout.addWidget(note)
            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Save
                | QtWidgets.QDialogButtonBox.Cancel
            )

            def save_preferences() -> None:
                preferences.update(
                    scan_depth=int(depth.currentData()),
                    cue_post_processing=str(cue_policy.currentData()),
                )
                dlg.accept()

            buttons.accepted.connect(save_preferences)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec_()

        def _export_configuration(self) -> None:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export Touhou Tagger configuration", "touhou_tagger_backup.json",
                "JSON files (*.json);;All files (*)",
            )
            if not path:
                return
            try:
                config_backup.export_file(path)
            except (OSError, ValueError) as exc:
                QtWidgets.QMessageBox.warning(
                    self, "Export configuration", f"Could not export settings: {exc}"
                )
                return
            QtWidgets.QMessageBox.information(
                self, "Export configuration",
                "Cookie-free settings exported. Cookie headers were not included.\n\n"
                "The backup can contain local library, album, and executable "
                "paths; review it before sharing publicly.",
            )

        def _import_configuration(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Import Touhou Tagger configuration", "",
                "JSON files (*.json);;All files (*)",
            )
            if not path:
                return
            reply = QtWidgets.QMessageBox.question(
                self, "Import configuration",
                "Import the non-secret preferences from this file? Existing "
                "values in those categories will be replaced. Cookies are "
                "never imported.",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
            try:
                changed = config_backup.import_file(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                QtWidgets.QMessageBox.warning(
                    self, "Import configuration", f"Could not import settings: {exc}"
                )
                return
            external_tools.reload()
            album_overrides.reload()
            availability.reload()
            tag_locks.reload()
            # Clearing the module cache is not enough: the Tag Edit tab holds
            # its own lock snapshot for painting, so its padlocks would still
            # show the pre-import state.
            self._tag_edit_tab.reload_locks()
            QtWidgets.QMessageBox.information(
                self, "Import configuration",
                "Imported: " + (", ".join(changed) if changed else "nothing")
                + ".\n\nRestart Touhou Tagger to apply GUI and authentication preferences.",
            )

        def _open_external_tools_dialog(self) -> None:
            """Show external-command status and save optional path overrides."""
            dlg = QtWidgets.QDialog(self)
            dlg.setWindowTitle("External Tools")
            dlg.setModal(True)
            dlg.setMinimumSize(780, 480)
            layout = QtWidgets.QVBoxLayout(dlg)

            intro = QtWidgets.QLabel(
                "The tagger normally finds these commands through PATH. "
                "Use Browse when a tool is installed elsewhere. Overrides "
                "are stored in the per-user configuration directory and "
                "contain no cookies or command output."
            )
            intro.setWordWrap(True)
            layout.addWidget(intro)

            table = QtWidgets.QTableWidget(len(external_tools.TOOL_SPECS), 4)
            table.setHorizontalHeaderLabels(
                ["Tool", "Used by", "Status", "Saved path override"]
            )
            table.setEditTriggers(
                QtWidgets.QAbstractItemView.NoEditTriggers
            )
            table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            table.verticalHeader().setVisible(False)
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
            layout.addWidget(table, stretch=1)

            rows: dict[str, tuple[QtWidgets.QLabel, QtWidgets.QLineEdit]] = {}

            def refresh() -> None:
                for row, tool_id in enumerate(external_tools.TOOL_SPECS):
                    info = external_tools.describe(tool_id)
                    status_label, path_edit = rows[tool_id]
                    detail = info["status"]
                    if info["path"]:
                        detail += f" — {info['path']}"
                    status_label.setText(detail)
                    status_label.setToolTip(detail)
                    if path_edit.text() != info["override"]:
                        path_edit.setText(info["override"])
                    item = table.item(row, 0)
                    if item:
                        item.setToolTip(info["features"])

            def save_path(tool_id: str, edit: QtWidgets.QLineEdit) -> None:
                external_tools.set_override(tool_id, edit.text().strip())
                refresh()

            for row, tool_id in enumerate(external_tools.TOOL_SPECS):
                info = external_tools.describe(tool_id)
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(info["label"]))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(info["features"]))

                status_label = QtWidgets.QLabel()
                status_label.setWordWrap(True)
                table.setCellWidget(row, 2, status_label)

                path_cell = QtWidgets.QWidget()
                path_layout = QtWidgets.QHBoxLayout(path_cell)
                path_layout.setContentsMargins(2, 2, 2, 2)
                path_edit = QtWidgets.QLineEdit(info["override"])
                path_edit.setPlaceholderText("Use PATH")
                path_edit.setToolTip(
                    "Optional absolute executable path. Leave empty to use PATH."
                )
                path_layout.addWidget(path_edit, stretch=1)
                browse_btn = QtWidgets.QPushButton("Browse…")
                browse_btn.clicked.connect(
                    lambda _checked=False, _id=tool_id, _edit=path_edit:
                    self._browse_external_tool(_id, _edit, dlg, save_path)
                )
                path_layout.addWidget(browse_btn)
                clear_btn = QtWidgets.QPushButton("Clear")
                clear_btn.clicked.connect(
                    lambda _checked=False, _id=tool_id, _edit=path_edit:
                    self._clear_external_tool(_id, _edit, save_path)
                )
                path_layout.addWidget(clear_btn)
                path_edit.editingFinished.connect(
                    lambda _id=tool_id, _edit=path_edit:
                    save_path(_id, _edit)
                )
                table.setCellWidget(row, 3, path_cell)
                rows[tool_id] = (status_label, path_edit)

            refresh()
            note = QtWidgets.QLabel(
                f"Configuration: {external_tools.config_path()}"
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: palette(text);")
            layout.addWidget(note)

            buttons = QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Close
            )
            refresh_btn = buttons.addButton(
                "Refresh diagnostics", QtWidgets.QDialogButtonBox.ActionRole
            )
            refresh_btn.clicked.connect(refresh)
            buttons.rejected.connect(dlg.reject)
            layout.addWidget(buttons)
            dlg.exec_()

        @staticmethod
        def _browse_external_tool(
            tool_id: str,
            edit,
            parent,
            save_callback,
        ) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                parent,
                f"Select {external_tools.TOOL_SPECS[tool_id]['label']}",
                edit.text().strip() or "",
            )
            if path:
                edit.setText(path)
                save_callback(tool_id, edit)

        @staticmethod
        def _clear_external_tool(tool_id: str, edit, save_callback) -> None:
            edit.clear()
            save_callback(tool_id, edit)

        # --- File menu dispatch -----------------------------------
        def _file_menu_queue_target(self):
            """The active tab, when it is one the queue actions apply
            to (Wiki Tagger / Romanise / Tag Edit); None otherwise."""
            current = self._tabs.currentWidget()
            if current in (self._wiki_tab, self._romanize_tab,
                           self._tag_edit_tab):
                return current
            return None

        def _file_menu_call(self, method_name: str) -> None:
            target = self._file_menu_queue_target()
            if target is not None:
                getattr(target, method_name)()

        def _update_file_menu(self, _index: int = 0) -> None:
            enabled = self._file_menu_queue_target() is not None
            for act in (self._act_add, self._act_remove,
                        self._act_clear, self._act_refresh):
                act.setEnabled(enabled)

        def _running_workers(self) -> list:
            """Every background worker still running, with a display name.

            Returns ``[(name, tab, worker), …]``.  Each queue tab keeps its
            worker in ``_worker`` and clears it when the run ends, so a
            live thread here means real work is still in flight.
            """
            candidates = [
                ("Wiki Tagger", self._wiki_tab),
                ("Romanise", self._romanize_tab),
                ("Statistics", self._stats_tab),
            ]
            running = []
            for name, tab in candidates:
                worker = getattr(tab, "_worker", None) if tab else None
                if worker is not None and worker.isRunning():
                    running.append((name, tab, worker))
            return running

        def _finish_workers(self, running: list) -> None:
            """Ask the running workers to stop and wait for them to do it.

            A tagging worker is mid-write on someone's music files; letting
            the interpreter tear its thread down at exit can leave a file
            half-written.  Each worker already stops cleanly at the next
            album boundary, so cancel them all and keep the GUI thread
            pumping events (the workers reach the GUI through queued
            signals) until every thread has actually returned.
            """
            for _name, tab, worker in running:
                # The run still finishes its current album and reports into
                # the log; it just skips its summary dialog.
                if hasattr(tab, "_shutting_down"):
                    tab._shutting_down = True
                worker.request_cancel()
            dialog = QtWidgets.QProgressDialog(
                "Finishing the current album before closing…",
                "", 0, 0, self,
            )
            dialog.setWindowTitle("Closing")
            dialog.setWindowModality(QtCore.Qt.ApplicationModal)
            dialog.setCancelButton(None)
            dialog.show()
            try:
                while any(w.isRunning() for _n, _t, w in running):
                    QtWidgets.QApplication.processEvents(
                        QtCore.QEventLoop.AllEvents, 100,
                    )
                    for _name, _tab, worker in running:
                        worker.wait(50)
            finally:
                dialog.close()

        def closeEvent(
            self, event: QtGui.QCloseEvent   # type: ignore[override]
        ) -> None:
            """Warn before closing while work is unfinished — a running
            worker or unsaved Tag Edit changes — regardless of which tab
            is currently active."""
            running = self._running_workers()
            if running:
                if self._closing:
                    # Already cancelling from an earlier close; just wait.
                    event.ignore()
                    return
                names = ", ".join(name for name, _t, _w in running)
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "Still running",
                    f"{names} still running.\n\n"
                    "Stop after the current album and close?  Closing now "
                    "would cut a tag write off half-finished.",
                    QtWidgets.QMessageBox.Ok
                    | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel,
                )
                if reply != QtWidgets.QMessageBox.Ok:
                    event.ignore()
                    return
                self._closing = True
                try:
                    self._finish_workers(running)
                finally:
                    self._closing = False
            if self._tag_edit_tab.has_unsaved_changes():
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "Unsaved changes",
                    "The Tag Edit tab has unsaved changes.\n\n"
                    "Close without saving?",
                    QtWidgets.QMessageBox.Ok
                    | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Cancel,
                )
                if reply != QtWidgets.QMessageBox.Ok:
                    # The workers stopped, but the user chose to keep the
                    # window open. Future runs must show their summaries.
                    for _name, tab, _worker in running:
                        if hasattr(tab, "_shutting_down"):
                            tab._shutting_down = False
                    event.ignore()
                    return
            preferences.update(
                gui={
                    "width": self.width(),
                    "height": self.height(),
                    "last_tab": self._tabs.currentIndex(),
                }
            )
            super().closeEvent(event)

    app = QtWidgets.QApplication(sys.argv)
    window = TaggerWindow()
    window.show()
    sys.exit(app.exec_())
