# Changelog

All notable changes to Touhou Tagger are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
New entries are kept under **Unreleased** until a release, then moved into a
dated version heading. Group user-visible changes under Added, Changed, Fixed,
Removed, or Security; do not use this file as a commit-by-commit log.

## Unreleased

### Added

- "Force overwrite staff tags" (GUI checkbox; `--force-credits` on the CLI):
  makes the wiki authoritative for `arranger`, `vocalist`, and `lyricist`
  instead of preserving whatever the file already has, so a re-run can
  correct credits written by an earlier release. A credit the wiki already
  agrees with is still skipped, and a role the wiki does not credit is left
  alone rather than cleared.
  The checkbox is greyed out when no staff tag is selected.
- `source/retag_credits.py`: migration CLI that repairs `arranger`,
  `vocalist`, and `lyricist` tags already written with the artist's circle.
  It re-fetches each album from THBWiki rather than reversing the faulty
  mapping, which is not invertible. Dry run by default, checkpointed per
  album so an expired THBWiki session can be resumed, and it rewrites a tag
  only when the tag both disagrees with the wiki and matches the old bug's
  output exactly.

### Changed

- Per-track `arranger`, `vocalist`, and `lyricist` tags now follow the same
  romanization resolver as the sort fields, so TouhouDB's official name is
  used where it has one. TouhouDB remains opt-in; without it the credits keep
  the wiki's original names.

### Fixed

- Per-track `arranger`, `vocalist`, and `lyricist` tags no longer show the
  artist's circle instead of the artist. THBWiki's Staff section lists
  `[Artist, Circle, Tracks]`, and the second column was being read as a
  romanization of the first, so credits were rewritten to the circle
  (`3L` → `NJK Record`, `Shibayan` → `ShibayanRecords`). Compilation albums
  that draw one track from each of many circles were affected worst. The
  same mapping fed `artistsort` and `albumartistsort`.

## 0.1.0 - 2026-08-05

### Added

- Initial public-release preparation: user documentation, pinned dependency
  groups, offline regression tests, and continuous integration (Linux, with a
  Windows job for regression coverage).
- Touhou album tagging sourced from THBWiki, with optional English Touhou Wiki
  lookup and optional Japanese-title romanisation.
- GUI and command-line workflows, including dry-run previews and optional CUE
  album-image splitting.

### Security

- Manual THBWiki authentication and optional browser-cookie auto-pull are
  documented; browser cookies are not stored in project files or configuration.
