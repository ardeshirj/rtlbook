# Versions

rtlbook has one version number, which `rtlbook version` prints. Each release is a git tag named `vX.Y.Z`.

## When the version changes

- **A new middle number** (0.5.0 → 0.6.0) for a change in what rtlbook produces or how it's used: a new kind of
  book supported, a change to the EPUB, a command or option added, removed or renamed.
- **A new last number** (0.5.0 → 0.5.1) for a fix that doesn't change any of that.
- **No change** for docs and experiments.

While the version is below 1.0, any release may break how rtlbook is used; the history below says how.

## Where the number is

Three files carry it, and they must agree:

| File | What it's for |
|---|---|
| `pyproject.toml` | The package version, and the one the tag is named from |
| `src/rtlbook/__init__.py` | `__version__`, what `rtlbook version` prints |
| `uv.lock` | The lock file's entry for rtlbook itself; uv rewrites it on the next lock if it disagrees |

`make bump` sets all three, and `make tag` refuses to tag when they differ. Reading the version from the installed
package instead would leave one place to edit, but uv runs only inside the Docker build, so three copies set by one
command are simpler.

## How to release

```bash
make bump V=0.6.0                  # set the version in the three files
# add the version to the history below
git commit -am "…"                 # commit both
make tag NOTE="What changed"       # tag v0.6.0: the note, then the commits since the last tag
git push origin main v0.6.0
```

`make tag` (`tools/release`) only tags a clean `main` with no tag for that version yet, and never pushes.

## History

### 0.11.1 (2026-10-21)
- **A fine-tuned ParisaOCR model reads under its own name:** the export (`docker/parisaocr_onnx.py OUT_DIR MODEL
  NAME`) writes the name into the model file's metadata, and results (`report.json`, `rtlbook:read-by`, a
  scorecard) carry it; before, any model in `RTLBOOK_MODELS` was named as the stock one.

### 0.11.0 (2026-10-20)
- **A verb broken at a line's end is whole again in the EPUB:** a line ending in `می-` or `نمی-` (the print breaking
  a verb after its prefix) joins the next line without the dash, with a half-space, instead of keeping the dash and
  a space.

### 0.10.0 (2026-10-19)
- **Books from checked lines trust their text:** no OCR clean-ups (a real closing » was turned into a comma when its
  « was in an earlier paragraph), and a dialogue line opened mid-sentence at a line break no longer starts a
  paragraph.
- **Editions:** `"quotes": "paired"` keeps only quotes that open and close in one paragraph; a chapter can bring its
  `title` where the printed one isn't a usable line.
- **Training data:** rules 4 and 5 reworded (no new version): a crop with two lines or a cut line that holds print
  is unsure, with the print typed, so a book keeps it; can't use is for no print worth keeping.

### 0.9.0 (2026-10-19)
- **An edition can change the book's text** (`replace` in `--edition`: regex patterns and what each becomes, applied
  to each line), for editorial choices such as an old typesetting of dialogue; the set keeps the print.
  `report.json` counts the changes (`lines_from_set`: `replaced`).
- **No space between a comma and a closing mark:** 0.8.0's comma fix added one back where a paragraph has quotes
  (`،»` became `، »`).

### 0.8.0 (2026-10-19)
- **`convert --lines SET` builds a book from a checked set of lines** instead of OCR: each line keeps its box and
  takes the set's text (checked, else agreed, else an unsure best guess; skipped lines left out), and everything
  after reading runs as for OCR. `--edition` names the lines that start chapters and the lines to leave out;
  `--no-cover` leaves the cover out, and a cover from a scan stored in strips now fits the screen.
- **Half-spaces as Farsi is spelled today** before five endings and after mi-/nemi-/bi- (`--no-half-spaces` turns
  it off; `report.json`: `half_spaces_made`).
- **Marks against their words:** no space before `. ؛ : ؟ ! »`, none after `«`, also across a line break. Old type
  often sets a gap there; in the EPUB it was a stray space where a line could break.
- **Training data:** the transcription rules' version 3 (marks against their words, whatever gap the type leaves),
  which `rtlbook lines` stamps on new lines; a line can be `agreed` (two independent readings, in a frozen version);
  `summary.json` lists its lines' rules versions; `examples.json` (per-book crops for the rules) is no longer part of
  the format.

### 0.7.0 (2026-10-16)
- **Scans are read by ParisaOCR's model** (Apache-2.0), run by ONNX Runtime inside the image (675 MB, from 550; no
  PyTorch). On the 1932 test pages 0.3% of letters are wrong, against 8.7% in 0.6.0; on a 1963 printing and three
  modern editions it was judged right far more often than Tesseract. About five times slower than Tesseract on a
  scan (5–6 s a page on one core). `--scan-reader tesseract` keeps scans on Tesseract.
- **A scan's lines are found by Tesseract's layout analysis and read one by one** (the reader slot, `--reader`,
  default `auto`): exported PDFs keep Tesseract's whole-page call, unchanged. `--reader page` reads a scan's whole
  pages as 0.6.0 did.
- **Words run together in scans are split** after a letter that never joins the next, with word lists built into the
  image (Tesseract's own and Lilak's); `--no-split-joined` turns it off, and `report.json` counts them.
- **The EPUB says how it was made:** `rtlbook:version`, `rtlbook:document`, `rtlbook:lines-found-by` and
  `rtlbook:read-by` in its package metadata.
- **`report.json`: `engine`** (rtlbook's version, scan or exported, what found and what read the lines) replaces
  `ocr_engine`, which named Tesseract whatever read the book. ParisaOCR's confidence is put on Tesseract's scale,
  so `mean_confidence`, the low-confidence warning and `--min-line-conf` mean the same as before.
- **`rtlbook bench`**, the scorecard: line readers on a set's checked lines, whole pages and an exported PDF, saved
  per run to `bench/` (`make bench`; the other readers in `make readers`).

### 0.6.0 (2026-10-12)
- **`rtlbook lines`** cuts a book's pages into training lines for checking (`docs/TRAINING-DATA.md`): what
  `tools/transcribe/prepare.py` did, now a command released with rtlbook's versions, so a set can be cut by a known
  version. `lines.json` records it (`engine`). `tools/transcribe/prepare.py` is gone.
- **Suggestions come in one order on every run:** words that rank the same are listed alphabetically (they followed
  an order that could change between runs).
- **Transcription rules version 2:** two words printed with no gap get a space (version 1 read as a half-space); the
  aim comes first: type what the ink shows. New lines are stamped `rules: 2`.

### 0.5.0 (2026-10-08)
The first tagged version.
- **EPUB 3 is the only output**, made for reading systems built on Readium, such as Thorium Reader. The `kfx`
  command and calibre are gone: converting for a device (Kindle, Kobo) is out of scope.
- **Exported Persian PDFs** convert end to end; scans convert with more errors and aren't supported yet.
- The status is early, no longer a proof of concept.
