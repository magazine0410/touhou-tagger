# Releasing Touhou Tagger

This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the tagger is before 1.0, use `0.MINOR.PATCH`: increment PATCH for
compatible fixes, MINOR for compatible features, and make any breaking change
explicit in the changelog. After 1.0, use the usual MAJOR.MINOR.PATCH meaning.

`VERSION` in the repository root is the single source of the release version.
It must match the Git tag apart from the tag's `v` prefix: for example,
`VERSION` containing `0.1.0` is released as tag `v0.1.0`.

## Release checklist

Before creating a release:

- [ ] Decide the next version according to the versioning policy.
- [ ] Update `VERSION`.
- [ ] Move the completed items from `CHANGELOG.md`'s **Unreleased** section to
  a dated `## VERSION - YYYY-MM-DD` section, and add a new empty
  **Unreleased** heading.
- [ ] Review the README, dependency files, and user documentation for accuracy.
- [ ] Run the offline verification locally:

  ```bash
  python -m unittest discover -s tests -v
  python -c "import pathlib, py_compile; [py_compile.compile(str(path), doraise=True) for path in pathlib.Path('source').glob('*.py')]"
  ```

- [ ] Confirm the GitHub Actions Linux/Windows test matrix is green.
- [ ] Review the exact files to be committed for cookies, browser data,
  personal paths, logs, test music, and other private material. Do this again
  immediately before the first public push.
- [ ] Test a dry run on a copy or small test album. If CUE splitting changed,
  test it separately and consider a backup of valued music.
- [ ] Commit the release changes, create the matching annotated Git tag (for
  example `v0.1.0`), and push the commit and tag.
- [ ] Create the GitHub release from that tag, using a concise adaptation of
  the matching changelog section as its release notes.

After publishing, verify the repository's rendered README, documentation
links, licence, and release download/source view as an unauthenticated visitor.
