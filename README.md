# rtlbook

> **Status: early (0.5).** Exported Persian PDFs convert end to end to EPUB; scanned books aren't supported
> yet. Expect breaking changes between versions. See [Status](#status).

Convert PDF books in right-to-left languages (Persian first) into reflowable EPUB 3. EPUB is the only output,
made for reading apps built on [Readium](https://readium.org/), such as
[Thorium Reader](https://thorium.edrlab.org/). Converting to a device's own format (Kindle, Kobo) is out of scope.
So far it supports PDFs exported from a word processor (born-digital). Scanned and typewritten books
are planned: they convert, but with more errors. `inspect` tells you which kind you have, and checks the book
is in the right script (not English, say). See
[docs/DESIGN.md](docs/DESIGN.md) for how it works and [docs/ROADMAP.md](docs/ROADMAP.md) for what's next.

> **Note:** This project was designed and written by **Claude Opus 5.5** (Anthropic) in
> [Claude Code](https://claude.com/claude-code). See [Credits](#credits).

## Quick start (Docker)

```bash
# Build the Docker image (make build; `make` lists the other commands)
docker build -f docker/Dockerfile -t rtlbook:dev .

# Create input/ and output/, then put your PDF in input/
./rtlbook init

# Exported PDF or scan? Right script?
./rtlbook inspect input/book.pdf

# Convert to EPUB → output/book.epub
./rtlbook convert input/book.pdf --title "…" --author "…"
```

`./rtlbook` runs the CLI in Docker. **Only this repository folder is shared with the container**,
so the tool can't see or change anything else on your machine. Input PDFs must therefore be inside the
repo. Copy them into `input/`, since a path like `~/Downloads/book.pdf` isn't visible to it. Paths work
the same inside and outside the container, relative or absolute, including when you run from a
subfolder. Running it from outside the repo stops with an error. Your local `src/` is mounted too, so
code changes apply without a rebuild.

## Status

rtlbook is **early (version 0.5)**: it does one kind of book well and is being extended one document type at a
time (see the [roadmap](docs/ROADMAP.md)). `rtlbook version` prints the version.

What has been verified:
- 8 Persian novels (3,231 pages, born-digital PDFs from Word, pdfFactory, iText and others) converted to
  EPUB 3 that passes epubcheck.
- Apple Silicon Mac (M2) with Docker Desktop.

Not yet done or known to be weak:
- **Scanned and typewritten books** aren't supported yet. They convert, but on a 1932 letterpress scan
  6–8% of letters were misread, against under 1% on an exported PDF (measured with `rtlbook eval`).
- **Accuracy is measured on few books so far:** one exported story against its own stored text, and two
  hand-checked pages of a scanned book (`tests/data/`).
- **Persian only:** Arabic, Urdu and Hebrew are on the [roadmap](docs/ROADMAP.md), not built.
- **Known OCR quirks:** in some bold fonts, `!` without a following space is read as `ا`, which merges
  words. Front pages (catalogue records, site banners) can come out as junk text.
- **Titles and authors** are read from the title page when it has them in text; check what `convert`
  reports and pass `--title`/`--author` when it's wrong or missing.
- **No web app yet.** The CLI is the only interface.

See [DESIGN.md](docs/DESIGN.md) §11–13 for the dated decisions and measurements, and
[ROADMAP.md](docs/ROADMAP.md) for what's next.
Practical lessons and troubleshooting (OCR, EPUB, Docker on macOS) are in [LESSONS.md](docs/LESSONS.md).

## Folders

| Folder | What goes there | In git? |
|---|---|---|
| `input/` | PDFs to convert. Copy them here, because the container can only see the repo folder | No, fully ignored |
| `output/` | Results: `<name>.epub`, plus `<name>.rtlbook/`, the per-book work folder | No, fully ignored |
| `output/<name>.rtlbook/` | OCR cache (`pages/*.json`), `pages.txt`, `paragraphs.txt`, `report.json`, `epubcheck.txt` | No |

`./rtlbook init` creates both folders (`convert` also creates `output/` if it's missing). Books can be
copyrighted or private, so the folders and everything in them are git-ignored and never committed.
`convert` writes to `output/<pdf name>.epub` unless you pass `-o`. It reuses the OCR cache in
`output/<name>.rtlbook/`, so re-running with different text or EPUB options takes seconds.

Convert a whole folder:

```bash
for pdf in input/*.pdf; do
  ./rtlbook convert "$pdf"
done
```

Useful `convert` options:

| Option | Purpose |
|---|---|
| `--digits keep` | Keep digits as printed (default `auto`: Persian ۰–۹ for `fas`) |
| `--pages 1-120` | Convert part of a book |
| `-j 8` | Pages OCR'd in parallel (default: all CPUs) |
| `--progress json` | Progress as JSON lines on stderr (`start`, one `page` per page, `done`), for other programs |
| `--crop 0.075` | Cut page frames/borders before OCR |
| `--drop-lines REGEX` | Remove watermark or banner lines |
| `--min-line-conf 40` | Drop OCR lines below this confidence |
| `-o PATH` | Output EPUB (default `output/<pdf name>.epub`) |
| `--work DIR` | Work/cache folder (default `output/<name>.rtlbook/`). Re-runs reuse per-page OCR results |

What `convert` does automatically:
- **OCRs every page.** The text stored inside Persian PDFs is rarely usable as is: wrong character codes, words in reversed (visual) order, missing spaces. On an exported story whose stored text could be rebuilt, OCR still got over 99% of letters right.
- **Cleans up OCR:** Persian letters and digits, commas read as `»`/`ء`, mirrored parentheses, stray marks, and **running headers/watermarks** repeated on many pages.
- **Rebuilds paragraphs**, including dialogue lines (`سارا- …`, `علی : …`), and joins them across page breaks.
- **Detects chapters** even when OCR misreads the heading (`نصل دو از دهم` → `فصل دوازدهم`). Books without chapters get ~20-page sections.
- **Builds a valid EPUB 3** (epubcheck) with RTL page direction, the Parastoo font, cover, and print page list.

Typical real-world run (site credits on the title pages, extra front pages):

```bash
./rtlbook convert input/Gandom.pdf --title "گندم" --author "م. مودب‌پور" \
  --drop-lines 'کتابخانه مجازی|تهیه و تنظیم' --pages 2-557
```

`output/<name>.rtlbook/` keeps `pages/*.json` (per-page OCR with boxes and confidence),
`pages.txt`, `paragraphs.txt`, `report.json` and `epubcheck.txt` for review.

## Measuring OCR accuracy

`eval` compares OCR output with a correct text of the same pages, e.g. hand-corrected. Spelling conventions that differ between
an old printing and a modern transcription (Arabic `ي`/`ك`, digits, half-spaces, vowel marks) count as
equal.

```bash
./rtlbook eval output/book.rtlbook output/ref.txt --pages 24 --diff output/diff.txt
```

It reports the character error rate (CER, spaces ignored), the word error rate (WER), how many reference
words appear anywhere in the OCR text, and a CER that matches each reference line to its closest OCR line.
When the last two are much better than the first, the words were read correctly but in the wrong order,
which is a layout problem (e.g. two-column verse) rather than misread letters. A reference longer than
the pages (a whole chapter for a page that shows only its end) is trimmed to the part the OCR covers.

## Reading the output

Open the EPUB in [Thorium Reader](https://thorium.edrlab.org/) (Windows, macOS, Linux) or another app built on
Readium: that is what rtlbook's output is made for. Other reading apps may also open it, but they
aren't targets, and turning the EPUB into a device's own format (Kindle's KFX or AZW3, Kobo's KEPUB) is out of
scope.

## Tests

`make test`, or:

```bash
docker run --rm -v "$PWD/src":/app/src:ro -v "$PWD/tests":/app/tests:ro -w /app \
  --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests
```

## Versions

`rtlbook version` prints the version; releases are git tags named `vX.Y.Z`. When the version changes, how to
release, and what changed in each version: [docs/VERSIONS.md](docs/VERSIONS.md).

## Credits

- **Code and design:** written by Claude Opus 5.5 (Anthropic) using Claude Code, with the project
  maintainer supplying the test books, checking the outputs, and making the product decisions (Docker,
  local-only, EPUB only).
- **Built on:** [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and its
  `tessdata_best` models (Apache-2.0) · [PDFium](https://pdfium.googlesource.com/pdfium/) via
  [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) · [W3C EPUBCheck](https://github.com/w3c/epubcheck)
  · [Parastoo](https://github.com/rastikerdar/parastoo-font) font by Saber Rastikerdar (SIL OFL 1.1),
  embedded in the EPUBs.

## License

[Apache-2.0](LICENSE). The public-domain ground-truth texts in `tests/data/` are not ours and not covered by the
license (see the README in each folder). The tools rtlbook runs (Tesseract and its models, epubcheck) and the
Parastoo font keep their own licenses; none of them is stored in this
repository.
