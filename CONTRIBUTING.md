# Contributing to Touhou Tagger

Contributions are welcome. Please keep discussion and reviews respectful and
focused on making the tagger useful for Touhou music owners.

Prefix feature requests clearly, for example by putting "(Feature request)"
at the start.

## Before making a change

- Open an issue first for a substantial feature, a change to wiki/browser
  authentication, or anything that alters tagging policy.
- Keep pull requests focused. Explain the user-visible change, how you tested
  it, and any limitations or follow-up work.
- Add or update tests where practical, and update user-facing documentation
  when behaviour, setup, or limitations change.

## Privacy and safety

- Never include browser cookies, browser profiles, API keys, personal paths,
  real music files, or unredacted diagnostic logs in an issue, commit, or pull
  request. Use synthetic fixtures and placeholders instead.
- Preserve the documented authentication and anti-bot safeguards. Do not
  weaken cookie handling or replace the documented fetch methods without prior
  discussion.
- Treat tagging and CUE-splitting changes carefully: dry-run or use disposable
  test files before proposing changes that can modify a music library.

## Licensing

By submitting a contribution, you agree to license it under the project's
[MIT License](LICENSE).
