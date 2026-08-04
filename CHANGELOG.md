# Changelog

All notable changes to Touhou Tagger are documented here.

This project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
New entries are kept under **Unreleased** until a release, then moved into a
dated version heading. Group user-visible changes under Added, Changed, Fixed,
Removed, or Security; do not use this file as a commit-by-commit log.

## Unreleased

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
