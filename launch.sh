#!/usr/bin/env bash
#
# Touhou Tagger launcher.
#
# Normally this just starts the GUI.  On first run, if the required Python
# packages aren't installed yet, it offers to install them (into a project-local
# .venv, so your system Python is left untouched) via a small interactive menu.
#
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$script_dir"

VENV_DIR="$script_dir/.venv"
ENTRY="$script_dir/source/touhou_tagger.py"

# --- choose an interpreter: prefer the project venv, else system python3 ------
if [ -x "$VENV_DIR/bin/python" ]; then
    PY="$VENV_DIR/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
else
    echo "Error: python3 was not found. Please install Python 3.10 or newer." >&2
    exit 1
fi

# --- require Python 3.10+ -----------------------------------------------------
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Error: Python 3.10 or newer is required to run Touhou Tagger." >&2
    "$PY" --version >&2 || true
    exit 1
fi

# --- launch helper ------------------------------------------------------------
launch() { exec "$PY" "$ENTRY"; }

# --- detect the minimum needed to open the GUI --------------------------------
# core (bs4/mutagen/curl_cffi) + PyQt5, since this launcher opens the GUI.
deps_ok() {
    "$1" - <<'PYEOF' >/dev/null 2>&1
import importlib.util as u
mods = ("bs4", "mutagen", "curl_cffi", "PyQt5")
raise SystemExit(1 if any(u.find_spec(m) is None for m in mods) else 0)
PYEOF
}

# Everything already present -> just start the tagger.
if deps_ok "$PY"; then
    launch
fi

# --- some dependencies are missing from here on -------------------------------

# The install menu needs an interactive terminal.
if [ ! -t 0 ] || [ ! -t 1 ]; then
    echo "Touhou Tagger's Python dependencies are not installed yet." >&2
    echo "Run this launcher from a terminal to install them:" >&2
    echo "    \"$script_dir/launch.sh\"" >&2
    exit 1
fi

clear_screen() { command -v clear >/dev/null 2>&1 && clear || printf '\n\n'; }

# Distro-specific system-tool command for CUE splitting (printed, never run).
ffmpeg_flac_hint() (
    id=""; like=""
    if [ -r /etc/os-release ]; then
        # Sourced in this subshell so its variables don't leak to the caller.
        # shellcheck disable=SC1091
        . /etc/os-release
        id="${ID:-}"; like="${ID_LIKE:-}"
    fi
    case " $id $like " in
        *" fedora "*|*" rhel "*|*" centos "*) echo "sudo dnf install ffmpeg flac" ;;
        *" debian "*|*" ubuntu "*)            echo "sudo apt install ffmpeg flac" ;;
        *" arch "*)                            echo "sudo pacman -S ffmpeg flac" ;;
        *) echo "install 'ffmpeg' and 'flac' with your system package manager" ;;
    esac
)

# Create the project venv on demand and point PY at it.
ensure_venv() {
    if [ ! -x "$VENV_DIR/bin/python" ]; then
        echo "Creating a virtual environment in .venv ..."
        if ! python3 -m venv "$VENV_DIR"; then
            echo "Error: could not create the .venv virtual environment." >&2
            echo "On Debian/Ubuntu you may first need: sudo apt install python3-venv" >&2
            exit 1
        fi
    fi
    PY="$VENV_DIR/bin/python"
    "$PY" -m pip install --upgrade pip
}

install_minimal() {
    ensure_venv
    "$PY" -m pip install -r requirements.txt -r requirements/gui.txt
}

install_all() {
    ensure_venv
    "$PY" -m pip install -r requirements/all.txt
    "$PY" -m playwright install chromium
    "$PY" -m unidic download
}

# Ask Y/N until a valid answer is given; returns 0 for yes, 1 for no.
confirm() {
    local ans
    while true; do
        printf "Continue? [Y/N] "
        read -r ans || return 1
        case "$ans" in
            [Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo])     return 1 ;;
            *) echo "Please answer Y or N." ;;
        esac
    done
}

show_minimal_details() {
    clear_screen
    cat <<EOF
============================================================
 Minimal install — enough to run the Touhou Tagger GUI
============================================================

  beautifulsoup4   Parses the wiki HTML pages the tagger reads.
  mutagen          Reads and writes your audio files' tags.
  curl_cffi        Reaches THBWiki past its anti-bot protection.
                   THBWiki is the tagger's mandatory data source, so
                   this is required even for basic tagging.
  PyQt5            The graphical interface this launcher opens.

These install into a local ".venv" folder inside the project; your
system Python is not modified.

EOF
}

show_all_details() {
    clear_screen
    cat <<EOF
============================================================
 Full install — the GUI plus every optional feature
============================================================

  beautifulsoup4   Parses the wiki HTML pages the tagger reads.
  mutagen          Reads and writes your audio files' tags.
  curl_cffi        Reaches THBWiki (the mandatory data source) past
                   its anti-bot protection.
  PyQt5            The graphical interface this launcher opens.
  playwright       Fetches the English Touhou Wiki, an optional extra
    (+ Chromium)   source; it downloads a Chromium browser separately.
  browser_cookie3  Auto-pulls the THBWiki cookie from your browser, so
                   you don't have to paste it each session (optional).
  mecab-python3 \\
  unidic         > Romanise Japanese titles into the "titlesort" tag
  pykakasi      /  (UniDic is a dictionary downloaded after install).

These install into a local ".venv" folder inside the project; your
system Python is not modified.

Note: CUE-based FLAC splitting also needs the system tools "ffmpeg"
and "flac", which pip cannot install. To enable it later, run:
  $(ffmpeg_flac_hint)

EOF
}

# --- interactive menu ---------------------------------------------------------
while true; do
    clear_screen
    cat <<EOF
Touhou Tagger — some Python dependencies are not installed yet.

  1) Minimal   core packages + GUI (enough to run the tagger)
  2) Full      everything, including all optional features
  3) Cancel    don't install anything

EOF
    printf "Enter 1, 2, or 3: "
    read -r choice || { echo; exit 1; }
    case "$choice" in
        1) show_minimal_details; if confirm; then install_minimal; break; fi ;;
        2) show_all_details;     if confirm; then install_all;     break; fi ;;
        3)
            echo
            echo "No changes made. Touhou Tagger needs its dependencies to start."
            exit 0
            ;;
        *) echo "Please enter 1, 2, or 3."; sleep 1 ;;
    esac
done

echo
echo "Dependencies installed. Starting Touhou Tagger..."
launch
