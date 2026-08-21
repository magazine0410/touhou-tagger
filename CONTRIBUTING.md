# Contributing to Touhou Tagger

Touhou Tagger is a solo-maintained project. `magazine0410` is the sole
developer and maintainer. External code contributions are not accepted.
Please do not submit pull requests or patches unless specifically invited.

Issues are welcome for bug reports, feature requests, questions, and other
feedback. Opening an issue does not guarantee that the requested change will
be implemented. Issues are for feedback and discussion, not for submitting
code intended to be merged into the project.

## Issue safety

- Never include browser cookies, browser profiles, API keys, personal paths,
  real music files, or unredacted diagnostic logs in an issue. Use synthetic
  fixtures and placeholders instead.
- Preserve the documented authentication and anti-bot safeguards. Do not
  weaken cookie handling or replace the documented fetch methods without prior
  discussion.
- Treat tagging and CUE-splitting changes carefully: dry-run or use disposable
  test files when describing a problem involving changes to a music library.
