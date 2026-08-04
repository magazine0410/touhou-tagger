# Python dependencies

Touhou Tagger supports **CPython 3.10 through 3.14**. Its direct Python
dependencies are pinned to exact versions in the repository so a fresh install
does not silently pick up a newer incompatible release. `pip` still resolves
the compatible transitive dependencies required by those packages.

## Dependency groups

| File | Installs | Needed for |
| --- | --- | --- |
| `requirements.txt` | Beautiful Soup, Mutagen, curl_cffi | Core CLI tagging and THBWiki access. |
| `requirements/gui.txt` | PyQt5 | The graphical interface and `./launch.sh`. |
| `requirements/browser-fetch.txt` | Playwright | Optional English Touhou Wiki fetching. Install Playwright Chromium separately. Without it, English-wiki lookups are skipped and the mandatory THBWiki source is used. |
| `requirements/cookie-auto-pull.txt` | browser-cookie3 | Optional local-browser THBWiki-cookie auto-pull. Manual cookies work without it. |
| `requirements/romanisation.txt` | MeCab, UniDic, pykakasi | Optional Japanese-title romanisation / `titlesort`. |
| `requirements/cue-splitting.txt` | No Python packages | Notes the system tools used by optional CUE splitting. |
| `requirements/all.txt` | Core and every Python-based optional group | A convenience install for all Python features. |

## Install examples

Core command-line tagging, using a manually supplied THBWiki cookie:

```bash
python -m pip install -r requirements.txt
```

The usual graphical installation, including the optional English-wiki fetcher:

```bash
python -m pip install -r requirements.txt \
  -r requirements/gui.txt \
  -r requirements/browser-fetch.txt
python -m playwright install chromium
```

Install an extra feature group whenever it is wanted:

```bash
python -m pip install -r requirements/cookie-auto-pull.txt
python -m pip install -r requirements/romanisation.txt
python -m unidic download
```

Or install all Python feature groups at once:

```bash
python -m pip install -r requirements/all.txt
python -m playwright install chromium
python -m unidic download
```

## Non-Python dependencies

`curl` is required for THBWiki's track/credit API. CUE splitting additionally
needs `ffmpeg` and `flac`; `metaflac` improves embedded-CUE detection. These
are operating-system packages, not `pip` packages. Their installation routes,
optional Trash integration, and missing-tool behaviour are documented in
[EXTERNAL_TOOLS.md](EXTERNAL_TOOLS.md).

After changing the Playwright pin, run `python -m playwright install chromium`
again: Playwright's browser binary must match its Python package version.

## Running the offline tests

The regression suite uses Python's built-in `unittest` runner and the core
dependencies; it does not contact either wiki, require a browser cookie, or
use real music files:

```bash
python -m unittest discover -s tests -v
```

Live network checks are intentionally not part of this command. If they are
added later, they must be explicitly opted into and must never use committed
or hard-coded cookies.
