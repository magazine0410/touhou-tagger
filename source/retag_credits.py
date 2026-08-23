#!/usr/bin/env python3
"""
Repair per-track ``arranger``/``vocalist``/``lyricist`` tags that were
written with the artist's circle instead of the artist.

Until 2026-08-23 the tagger read the second column of THBWiki's Staff
section as a romanization of the first.  That column is the artist's circle
(所属社团), so every credited artist whose row named a circle was replaced by
it: ``3L`` became ``NJK Record``, ``Shibayan`` became ``ShibayanRecords``,
``隣人`` became ``ZYTOKINE``.  A spot check of 30 tagged albums found 12 of
them damaged, 141 wrong credit fields against 206 correct ones.

The damage cannot be undone by reversing that mapping.  It is many-to-one
(``3L``, ``坂上なち`` and ``やまざきさやか`` all collapse onto ``NJK Record``), it
differs per album, and circles are themselves legitimate credits on some
tracks — THBWiki credits ``NJK Record`` as the real arranger of seven
tracks.  So this tool re-fetches each album's page and repairs from the
wiki, inferring nothing.

A tag is rewritten only when **both** hold:

  * it disagrees with the wiki's credit for that track and role, and
  * it is exactly what the bug would have produced — the wiki's names with
    that album's own staff-table circle mapping applied.

Anything else is left untouched: a hand-edited credit, a credit that came
with the rip, an empty field (this tool repairs, it never fills), and a
circle name that the wiki itself credits.

THBWiki's session expires after a few minutes of fetching, which a whole
library outlives many times over.  Two mechanisms cover that.  Every album's
outcome is checkpointed as it completes, so re-running the same command
resumes and finished albums are not re-fetched.  And by default the run does
not end there: it pauses, waits for the challenge to be solved again, and
retries the same album, so one invocation can span several sessions.  Pass
``--no-wait`` (or run without a terminal) to stop instead.

Examples:
    python source/retag_credits.py "path/to/music-library"
    python source/retag_credits.py --apply "path/to/music-library"
    python source/retag_credits.py --apply --limit 50 "path/to/library"
    python source/retag_credits.py --no-wait "path/to/library"
    python source/retag_credits.py --reset "path/to/music-library"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

import availability
from file_scan import (
    DISC_DIR_RE,
    SUPPORTED_EXTENSIONS,
    guess_album_slug,
    scan_music_files,
)
from tag_io import _get_existing_tag, _is_latin_script, _set_tag
try:                                  # optional, like thwiki.py's own import
    import browser_cookie as _browser_cookie
except Exception:                     # noqa: BLE001
    _browser_cookie = None
from thwiki import (
    ThwikiCookieError,
    _fetch_thwiki_page_html,
    _parse_thwiki_html_credits,
    parse_thwiki_staff_circles,
)

# Tag name → the role key _parse_thwiki_html_credits() returns.
CREDIT_ROLES: tuple[tuple[str, str], ...] = (
    ("arranger", "arrange"),
    ("vocalist", "vocal"),
    ("lyricist", "lyric"),
)

_STATE_VERSION = 1

# TouhouDB is rate-limited to one request per second and its cache is
# per-instance.  A migration spans several sessions (the THBWiki cookie
# expires), so the resolved names are persisted and re-seeded on resume;
# without it every session re-queries the same artists.
_NAME_CACHE_FILE = "retag_credits_names.json"


# ---------------------------------------------------------------------------
# Checkpoint state
# ---------------------------------------------------------------------------
def state_path() -> str:
    """Per-user checkpoint file, beside the tagger's other state."""
    return os.path.join(availability.app_config_dir(),
                        "retag_credits_state.json")


def load_state(path: str) -> dict:
    """Read the checkpoint, or return an empty one if it is absent/unusable."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("version") == _STATE_VERSION:
            done = data.get("done")
            if isinstance(done, dict):
                return {"version": _STATE_VERSION, "done": done}
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": _STATE_VERSION, "done": {}}


def save_state(path: str, state: dict) -> None:
    """Write the checkpoint atomically, so an interrupted run stays readable."""
    try:
        availability.ensure_private_directory(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        availability.restrict_private_file(tmp)
        os.replace(tmp, path)
        availability.restrict_private_file(path)
    except OSError as exc:
        print(f"⚠ could not write checkpoint {path}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# TouhouDB romanization (opt-in)
# ---------------------------------------------------------------------------
def name_cache_path() -> str:
    """Where resolved TouhouDB romanizations are kept between sessions."""
    return os.path.join(availability.app_config_dir(), _NAME_CACHE_FILE)


def load_name_cache(client, path: str) -> int:
    """Seed *client* from the persisted romanization cache."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0
    return client.load_name_cache(data) if isinstance(data, dict) else 0


def save_name_cache(client, path: str) -> None:
    """Persist the romanization cache, misses included (they cost a query too)."""
    try:
        availability.ensure_private_directory(os.path.dirname(path))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(client.export_name_cache(), f,
                      ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"⚠ could not write name cache {path}: {exc}", file=sys.stderr)


def romanize_names(names: list[str], client) -> list[str]:
    """Romanize *names* through TouhouDB, keeping any that do not resolve.

    Returns the list unchanged when there is no client (``--romanize`` off),
    which is what makes the caller's comparison collapse to a plain repair.
    """
    if client is None:
        return names
    out: list[str] = []
    for name in names:
        if _is_latin_script(name):
            out.append(name)
            continue
        try:
            roman = client.romanize(name)
        except Exception:                             # noqa: BLE001
            roman = None
        out.append(roman if roman and _is_latin_script(roman) else name)
    return out


# ---------------------------------------------------------------------------
# Expired-session pause
# ---------------------------------------------------------------------------
# A whole-library migration outlives several THBWiki sessions.  Exiting on each
# expiry is safe (the checkpoint resumes) but costs a restart and a re-walk of
# the library per session, so by default the run pauses and waits for the
# challenge to be solved again.  Refuse to wait where nobody can answer:
# without a terminal on stdin the prompt would block forever.
_MAX_CONSECUTIVE_EXPIRIES = 5


def can_wait(no_wait: bool) -> bool:
    """True when the run may pause for a human to re-verify the session."""
    if no_wait:
        return False
    try:
        return sys.stdin.isatty()
    except Exception:                                 # noqa: BLE001
        return False


def wait_for_new_cookie(album_name: str, remaining: int) -> bool:
    """Ask for a re-verified THBWiki session.  True to retry, False to stop.

    Re-pulls the cookie from the browser afterwards so the retry uses the new
    session rather than the value cached moments ago.
    """
    print()
    print("  ⚠ The THBWiki session expired.")
    print(f"    Open THBWiki in your browser and pass the "
          f"\"verify you are human\" check, then press Enter to carry on "
          f"with {album_name!r} ({remaining:,} album(s) left).")
    print("    Press q then Enter, or Ctrl-C, to stop and resume later.")
    try:
        answer = input("    > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    if answer.startswith("q"):
        return False
    if _browser_cookie is not None:
        # Bypass the helper's short TTL cache; the whole point is that the
        # cookie changed while we were waiting.
        try:
            _browser_cookie.refresh_env(force=True, announce=True)
        except Exception:                             # noqa: BLE001
            pass
    return True


# ---------------------------------------------------------------------------
# Album discovery
# ---------------------------------------------------------------------------
def find_album_dirs(paths: list[str]) -> list[str]:
    """Return every album directory under *paths*.

    A directory holding supported audio files directly is an album, except a
    ``Disc N`` subdirectory — that belongs to its parent, which is the album
    the wiki has a page for.
    """
    albums: set[str] = set()
    for path in paths:
        if not os.path.isdir(path):
            print(f"⚠ Not a directory, skipping: {path}", file=sys.stderr)
            continue
        for dirpath, _dirs, files in os.walk(path):
            if not any(os.path.splitext(n)[1].lower() in SUPPORTED_EXTENSIONS
                       for n in files):
                continue
            if DISC_DIR_RE.match(os.path.basename(dirpath)):
                dirpath = os.path.dirname(dirpath)
            albums.add(os.path.abspath(dirpath))
    return sorted(albums)


def reviewed_slugs() -> dict[str, str]:
    """The GUI's path-keyed reviewed Wiki Slug overrides, or ``{}``."""
    path = os.path.join(availability.app_config_dir(), "album_overrides.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    slugs = data.get("slugs") if isinstance(data, dict) else None
    return slugs if isinstance(slugs, dict) else {}


# ---------------------------------------------------------------------------
# Per-album repair
# ---------------------------------------------------------------------------
def collect_current_credits(album_dir: str) -> list[dict]:
    """Scan one album and read the three credit tags from every track.

    Returns one record per file that carries at least one credit tag and a
    usable track number — the only files this tool can act on.
    """
    records: list[dict] = []
    for entry in scan_music_files(album_dir):
        if entry.get("number") is None:
            continue
        credits = {
            tag: (_get_existing_tag(entry["path"], tag) or "")
            for tag, _role in CREDIT_ROLES
        }
        if not any(credits.values()):
            continue
        records.append({
            "path": entry["path"],
            "key": (entry["disc"], entry["number"]),
            "credits": credits,
        })
    return records


def plan_album_fixes(
    records: list[dict],
    wiki_credits: dict,
    circles: dict[str, str],
    tdb_client=None,
) -> tuple[list[dict], Counter]:
    """Decide, per file and role, which credits need rewriting.

    Two separate operations share this walk:

    * **repair** — the tag is exactly the bug's output (the wiki's names with
      this album's circle mapping applied), so it is replaced with the wiki's
      names.  This runs always.
    * **romanize** — with *tdb_client* set, the target is the TouhouDB
      romanization of the wiki's names, so a tag that merely holds the wiki's
      original Japanese is rewritten too.  That is a naming-policy change, not
      a bug fix: it touches albums the bug never damaged, and it is counted
      separately so a dry run shows the two apart.

    Anything matching neither the wiki's names nor the bug's output is left
    alone in both modes.  Returns ``(fixes, counts)``; each fix is
    ``{"path", "tag", "old", "new", "kind"}``.  Nothing is written here.
    """
    fixes: list[dict] = []
    counts: Counter = Counter()

    for record in records:
        wiki_row = wiki_credits.get(record["key"])
        if not wiki_row:
            counts["track not on page"] += 1
            continue
        for tag, role in CREDIT_ROLES:
            wiki_names = wiki_row.get(role) or []
            if not wiki_names:
                continue
            have = record["credits"][tag]
            if not have:
                # Repair only; filling empty credits is the tagger's job.
                counts["empty (left alone)"] += 1
                continue
            wiki_value = "; ".join(wiki_names)
            # With --romanize the target is the romanized form; without it
            # romanize_names() is the identity and target == wiki_value.
            target = "; ".join(romanize_names(wiki_names, tdb_client))
            if have == target:
                counts["already correct"] += 1
                continue
            # The bug's exact output: the wiki's names, each replaced by the
            # circle this album's Staff section gives for them.  Always
            # compared against the un-romanized names — that is what the old
            # code wrote.
            as_bug = "; ".join(circles.get(n, n) for n in wiki_names)
            if as_bug != wiki_value and have == as_bug:
                kind = "repaired"
            elif have == wiki_value:
                # Not damaged; the wiki's own name, differing from the target
                # only because romanization is on.
                kind = "romanized"
            else:
                counts["differs (left alone)"] += 1
                continue
            counts[kind] += 1
            fixes.append({
                "path": record["path"], "tag": tag,
                "old": have, "new": target, "kind": kind,
            })

    return fixes, counts


def process_album(
    album_dir: str,
    *,
    slug: str,
    apply: bool,
    verbose: bool,
    tdb_client=None,
) -> dict:
    """Fetch one album's page and repair its credits.

    Returns a result dict for the checkpoint.  Raises ``ThwikiCookieError``
    unchanged — an expired session is fatal to the batch, not to one album.
    """
    records = collect_current_credits(album_dir)
    if not records:
        return {"result": "no credit tags", "repaired": 0}

    # The tagger's own page fetch: one call, tries the slug's full-width and
    # half-width variants, and raises ThwikiCookieError on a challenge.
    soup = _fetch_thwiki_page_html(slug)
    if soup is None:
        return {"result": "no page", "repaired": 0, "slug": slug}

    wiki_credits = _parse_thwiki_html_credits(soup)
    if not wiki_credits:
        return {"result": "no credits on page", "repaired": 0, "slug": slug}

    circles = parse_thwiki_staff_circles(soup)
    fixes, counts = plan_album_fixes(records, wiki_credits, circles,
                                     tdb_client=tdb_client)

    written = 0
    errors = 0
    for fix in fixes:
        if verbose or not apply:
            prefix = "" if apply else "[dry] "
            mark = "" if fix["kind"] == "repaired" else " [romanize]"
            print(f"  {prefix}{os.path.basename(fix['path'])}  {fix['tag']}: "
                  f"{fix['old']}  →  {fix['new']}{mark}")
        if not apply:
            continue
        try:
            _set_tag(fix["path"], fix["tag"], fix["new"])
            written += 1
        except Exception as exc:                      # noqa: BLE001
            errors += 1
            print(f"⚠ write failed: {fix['path']}: {exc}", file=sys.stderr)

    return {
        "result": "checked",
        "slug": slug,
        "repaired": counts["repaired"],
        "romanized": counts["romanized"],
        "changes": len(fixes),
        "written": written,
        "errors": errors,
        "counts": dict(counts),
    }


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
def run(
    paths: list[str],
    *,
    apply: bool,
    limit: int | None,
    delay: float,
    reviewed_only: bool,
    state_file: str,
    verbose: bool,
    tdb_client=None,
    name_cache_file: str | None = None,
    no_wait: bool = False,
) -> dict:
    """Walk every album under *paths*, checkpointing after each one.

    On an expired THBWiki session the run pauses for the challenge to be
    solved again and retries the same album, so one invocation can span
    several sessions.  ``no_wait`` (and any run without a terminal) stops
    instead, leaving the checkpoint to resume from.
    """
    state = load_state(state_file)
    done = state["done"]
    overrides = reviewed_slugs()

    albums = find_album_dirs(paths)
    # A dry run checkpoints too, so a long preview can resume across cookie
    # expiries like a real run.  But a dry-run record must not let the later
    # --apply run skip that album — nothing was written for it.  So a record
    # satisfies a dry run either way, and only an applied record satisfies
    # an --apply run.
    pending = [
        d for d in albums
        if not (done.get(d, {}).get("applied", False) or not apply
                and d in done)
    ]
    print(f"Albums found: {len(albums):,}  "
          f"(already {'written' if apply else 'checkpointed'}: "
          f"{len(albums) - len(pending):,})")
    if limit is not None:
        pending = pending[:limit]
        print(f"Limited to {len(pending):,} album(s) this run.")
    if not apply:
        print("Dry run — no tags will be written.  Add --apply to write.")
    print()

    waiting = can_wait(no_wait)
    if waiting:
        print("On an expired THBWiki session this run will pause and wait "
              "for you to re-verify, rather than stopping.")
        print()

    totals: Counter = Counter()
    stopped = None

    for index, album_dir in enumerate(pending, 1):
        slug = overrides.get(album_dir) or ""
        if not slug:
            if reviewed_only:
                done[album_dir] = {"result": "no reviewed slug",
                                   "repaired": 0, "applied": apply}
                totals["no reviewed slug"] += 1
                save_state(state_file, state)
                continue
            slug = guess_album_slug(album_dir)

        # Retry the *same* album after a pause: the expiry means it was never
        # fetched, so it must not be skipped or checkpointed.
        expiries = 0
        while True:
            try:
                result = process_album(album_dir, slug=slug, apply=apply,
                                       verbose=verbose, tdb_client=tdb_client)
                break
            except ThwikiCookieError as exc:
                expiries += 1
                if not waiting:
                    stopped = str(exc)
                elif expiries >= _MAX_CONSECUTIVE_EXPIRIES:
                    stopped = (f"the session expired "
                               f"{_MAX_CONSECUTIVE_EXPIRIES} times in a row "
                               f"on this album — {exc}")
                elif wait_for_new_cookie(os.path.basename(album_dir),
                                         len(pending) - index + 1):
                    continue
                else:
                    stopped = "stopped at the session prompt"
                result = None
                break
            except KeyboardInterrupt:
                stopped = "interrupted"
                result = None
                break
            except Exception as exc:                  # noqa: BLE001
                result = {"result": f"error: {type(exc).__name__}",
                          "repaired": 0}
                break
        if result is None:
            break

        # Checkpoint immediately: the session can die on the next album.
        result["applied"] = apply
        done[album_dir] = result
        save_state(state_file, state)

        # Names resolved for this album are worth keeping even if the run
        # stops on the next one — each cost a rate-limited request.
        if tdb_client is not None and name_cache_file:
            save_name_cache(tdb_client, name_cache_file)

        totals[result["result"]] += 1
        totals["repaired"] += result.get("repaired", 0)
        totals["romanized"] += result.get("romanized", 0)
        totals["written"] += result.get("written", 0)
        totals["errors"] += result.get("errors", 0)
        if result.get("repaired"):
            totals["albums with damage"] += 1

        if verbose or result.get("changes"):
            print(f"[{index}/{len(pending)}] {os.path.basename(album_dir)} "
                  f"— {result['result']}, {result.get('repaired', 0)} "
                  f"to repair, {result.get('romanized', 0)} to romanize")

        if delay and index < len(pending):
            time.sleep(delay)

    if tdb_client is not None and name_cache_file:
        save_name_cache(tdb_client, name_cache_file)
    return {"totals": totals, "stopped": stopped, "pending": len(pending)}


def print_summary(summary: dict, *, apply: bool, state_file: str) -> None:
    totals = summary["totals"]
    print("\n=== Summary ===")
    print(f"  albums checked        {totals['checked']:,}")
    print(f"  albums with damage    {totals['albums with damage']:,}")
    for key in ("no page", "no credits on page", "no credit tags",
                "no reviewed slug"):
        if totals[key]:
            print(f"  {key:<21} {totals[key]:,}")
    for key in sorted(k for k in totals if k.startswith("error:")):
        print(f"  {key:<21} {totals[key]:,}")

    print(f"\n  credit fields repaired  {totals['repaired']:,}")
    if totals["romanized"]:
        print(f"  credit fields romanized {totals['romanized']:,}")
    if apply:
        print(f"  tags written            {totals['written']:,}")
        if totals["errors"]:
            print(f"  write errors            {totals['errors']:,}")
    else:
        print("  (dry run — nothing written)")

    if summary["stopped"]:
        print(f"\n⚠ Stopped early: {summary['stopped']}")
        print("  Finished albums are checkpointed, and the album that was "
              "interrupted is not among them. Pass the challenge again in "
              "your browser, then re-run the same command to resume.")
        print(f"  Checkpoint: {state_file}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair arranger/vocalist/lyricist tags that were "
                    "written with the artist's circle instead of the artist.",
    )
    parser.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="Library root(s) or album folder(s). Walked recursively.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the repairs. Without it the run is a dry run — the "
             "opposite default to the offline translate_* tools, because "
             "this one re-fetches every album from THBWiki.",
    )
    parser.add_argument(
        "--limit", type=int, metavar="N",
        help="Process at most N albums this run (the rest stay pending).",
    )
    parser.add_argument(
        "--delay", type=float, default=1.0, metavar="SECONDS",
        help="Pause between album fetches (default: 1.0).",
    )
    parser.add_argument(
        "--romanize", action="store_true",
        help="Also rewrite credits that merely hold the wiki's Japanese "
             "name, using TouhouDB's official romanization. This is a "
             "naming-policy change, not a bug fix: it touches albums the "
             "circle bug never damaged. Dry-run it on its own first.",
    )
    parser.add_argument(
        "--no-wait", action="store_true",
        help="Stop when the THBWiki session expires instead of pausing for "
             "you to re-verify it. The checkpoint still resumes on the next "
             "run. Implied when stdin is not a terminal, so unattended runs "
             "never hang on the prompt.",
    )
    parser.add_argument(
        "--reviewed-only", action="store_true",
        help="Only process albums with a reviewed Wiki Slug override; skip "
             "the ones whose slug would have to be guessed from the folder.",
    )
    parser.add_argument(
        "--state", metavar="PATH",
        help="Checkpoint file (default: beside the tagger's other state).",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Discard the checkpoint and start over.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print every album, not only the ones with repairs.",
    )
    args = parser.parse_args(argv)

    state_file = args.state or state_path()
    if args.reset:
        try:
            os.remove(state_file)
            print(f"Checkpoint discarded: {state_file}")
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"Error: could not remove {state_file}: {exc}",
                  file=sys.stderr)
            return 2

    tdb_client = None
    cache_file = None
    if args.romanize:
        import touhoudb
        tdb_client = touhoudb.TouhouDBClient()
        cache_file = name_cache_path()
        seeded = load_name_cache(tdb_client, cache_file)
        print(f"TouhouDB romanization on "
              f"({seeded:,} name(s) from the persisted cache).")

    summary = run(
        args.paths, apply=args.apply, limit=args.limit, delay=args.delay,
        reviewed_only=args.reviewed_only, state_file=state_file,
        verbose=args.verbose, tdb_client=tdb_client,
        name_cache_file=cache_file, no_wait=args.no_wait,
    )
    print_summary(summary, apply=args.apply, state_file=state_file)
    return 1 if summary["totals"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
