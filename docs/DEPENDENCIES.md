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
| `requirements/romanisation.txt` | MeCab, UniDic, pykakasi | Optional Japanese-title romanisation / `titlesort`. The dictionary is a separate download; see [Romanisation dictionary](#romanisation-dictionary). |
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

`python -m unidic download` fetches the full romanisation dictionary. The
smaller `unidic-lite` dictionary needs no download and can be used instead; see
[Romanisation dictionary](#romanisation-dictionary).

## Romanisation dictionary

Romanisation needs a UniDic dictionary for MeCab. When
`source/japanese_romanizer.py` is imported it tries two packages in this order
and uses the first one that loads:

1. **`unidic`, the full dictionary.** The `unidic` package pinned in
   `requirements/romanisation.txt` is only a downloader. Run
   `python -m unidic download` once to fetch the dictionary itself (UniDic
   3.1.0 when this was written, 29 features per word). Until then the package
   has no dictionary and the romaniser skips it.
2. **`unidic-lite`, the smaller fallback.** It contains UniDic 2.1.2, an older
   release with 26 features per word, so it works right after
   `python -m pip install unidic-lite` with no download step. It is used when
   `unidic` is not installed or its dictionary was never downloaded.

The full dictionary is preferred: when both packages are installed, `unidic` is
used and `unidic-lite` is ignored. Both are supported, but they do not always
read a title the same way, so `titlesort` values written with `unidic-lite` can
differ from the full dictionary's. An existing `titlesort` is not overwritten
unless **Force overwrite existing titlesort** (CLI: `--force-titlesort`) is
used, so tags written under the fallback are kept after you install the full
dictionary until you re-run with that option.

`unidic-lite` is not in `requirements/romanisation.txt` or any other
requirements file, so the repository does not pin it. Listing it there would
install a second dictionary that goes unused once the full one is downloaded.
Install it yourself where it is wanted. If neither dictionary loads, the
romaniser is disabled and everything else keeps working.

The dictionary's folder path may contain spaces. The path is quoted when it is
passed to MeCab, so a project-local `.venv` created by `launch.sh` inside a
folder such as `My Music/Touhou Tagger` works with either dictionary.

To see which dictionary loaded, run this from the `source/` folder:

```bash
python -c "import japanese_romanizer as r; print(r.get_install_hint())"
```

`Romaniser ready.` means the full dictionary is in use. A `Romaniser ready`
message that mentions the `unidic-lite` fallback means the smaller one is. A
`Romaniser disabled` message means MeCab or both dictionaries failed to load;
it lists the install steps and the last import error. Without `pykakasi`
installed, a ready message also carries an optional note about that package.

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
