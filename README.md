# rtlbook

Convert PDF books in right-to-left languages (Persian first) into reflowable EPUB 3. It handles
born-digital PDFs with broken text layers, scans, and (later) typewritten books. See
[DESIGN.md](DESIGN.md) for the full plan.

> **Note:** This project was designed and written by **Claude Opus 5.5** (Anthropic) in
> [Claude Code](https://claude.com/claude-code). See [Credits](#credits).

## Quick start (Docker)

```bash
docker build -f docker/Dockerfile -t rtlbook:dev .

./rtlbook version                              # first run creates input/ and output/
cp ~/Downloads/book.pdf input/
./rtlbook inspect input/book.pdf               # which pages need OCR?
./rtlbook convert input/book.pdf --title "…" --author "…"   # → output/book.epub
./rtlbook kfx output/book.epub                 # → output/book.kfx (macOS + Kindle Previewer 4)
```

Run `./rtlbook` from the repository root. It runs the CLI in the container with the current
directory mounted at `/work`, so paths must be relative to it and inside it. Your local `src/` is
mounted too, so code changes apply without a rebuild.

## Folders

| Folder | What goes there | In git? |
|---|---|---|
| `input/` | PDFs to convert | No, fully ignored |
| `output/` | Results: `<name>.epub`, `<name>.kfx` (and `<name>.kpf` for Kindle Previewer), plus `<name>.rtlbook/`, the per-book work folder | No, fully ignored |
| `output/<name>.rtlbook/` | OCR cache (`pages/*.json`), `pages.txt`, `paragraphs.txt`, `report.json`, `epubcheck.txt` | No |

`./rtlbook` creates both folders on every run, so they always exist while you use it. Books can be
copyrighted or private, so the folders and everything in them are git-ignored and never committed.
`convert` writes to `output/<pdf name>.epub` unless you pass `-o`. It reuses the OCR cache in
`output/<name>.rtlbook/`, so re-running with different text or EPUB options takes seconds.

Convert a whole folder:

```bash
for pdf in input/*.pdf; do
  name=$(basename "$pdf" .pdf)
  ./rtlbook convert "$pdf" && ./rtlbook kfx "output/$name.epub"
done
```

Useful `convert` options:

| Option | Purpose |
|---|---|
| `--formats epub,azw3` | Outputs (default: `epub`). `azw3` is the older Kindle format. Prefer `kfx` |
| `--digits keep` | Keep digits as printed (default `auto`: Persian ۰–۹ for `fas`) |
| `--pages 1-120` | Convert part of a book |
| `-j 8` | Pages OCR'd in parallel (default: all CPUs) |
| `--crop 0.075` | Cut page frames/borders before OCR |
| `--drop-lines REGEX` | Remove watermark or banner lines |
| `--min-line-conf 40` | Drop OCR lines below this confidence |
| `--force-ocr` | OCR even when the text layer looks usable |
| `-o PATH` | Output EPUB (default `output/<pdf name>.epub`) |
| `--work DIR` | Work/cache folder (default `output/<name>.rtlbook/`). Re-runs reuse per-page OCR results |

What `convert` does automatically:
- **Checks the PDF's text layer** for garbled glyph mappings, reversed (visual) word order, and split words. If it's unusable (so far, every book tested), the pages are OCR'd.
- **Cleans up OCR:** Persian letters and digits, commas read as `»`/`ء`, mirrored parentheses, stray marks, and **running headers/watermarks** repeated on many pages.
- **Rebuilds paragraphs**, including dialogue lines (`سارا- …`, `علی : …`), and joins them across page breaks.
- **Detects chapters** even when OCR misreads the heading (`نصل دو از دهم` → `فصل دوازدهم`). Books without chapters get ~20-page sections.
- **Builds a valid EPUB 3** (epubcheck) with RTL page direction, the Vazirmatn font, cover, and print page list.

Typical real-world run (site credits on the title pages, extra front pages):

```bash
./rtlbook convert input/Gandom.pdf --title "گندم" --author "م. مودب‌پور" \
  --drop-lines 'کتابخانه مجازی|تهیه و تنظیم' --pages 2-557
./rtlbook kfx output/Gandom.epub
```

`output/<name>.rtlbook/` keeps `pages/*.json` (per-page OCR with boxes and confidence),
`pages.txt`, `paragraphs.txt`, `report.json` and `epubcheck.txt` for review.

## Reading the output

- **EPUB:** opens directly in Apple Books, Kobo, PocketBook, Boox, KOReader, and others. Copy it over USB (or with OpenMTP for Boox), or open it on the device.
- **Kindle:** Kindles can't open EPUB. Use **KFX**, Kindle's current format, which is fast and has Persian reflow and real page numbers:
  1. Install **Kindle Previewer 4** (free, from Amazon). It only runs on macOS/Windows, so the
     wrapper runs it on the host. The conversion is local (~1 min).
  2. `./rtlbook kfx book.epub` → `book.kpf` (open it in Previewer to check the layout) and
     `book.kfx`. The container packages the KPF with calibre's KFX Output plugin. `--doc` files it
     under Docs instead of Books.
  3. Copy `book.kfx` into the Kindle's `documents/` folder over USB. Newer USB-C Kindles on macOS need
     [OpenMTP](https://openmtp.ganeshrvel.com/). On macOS, run `dot_clean -m /Volumes/Kindle/documents`
     to remove `._*` files, then eject. Nothing is uploaded to Amazon.
  - AZW3 (`--formats epub,azw3`) also works but renders Persian slowly on the device.
  - Build the image with `--build-arg WITH_CALIBRE=0` to leave Calibre out, which saves about 700 MB. This removes AZW3/KFX support.

## Tests

```bash
docker run --rm -v "$PWD/src":/app/src:ro -v "$PWD/tests":/app/tests:ro -w /app \
  --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests
```

## Credits

- **Code and design:** written by Claude Opus 5.5 (Anthropic) using Claude Code, with the project
  maintainer supplying the test books, checking every output on real devices, and making the product
  decisions (Docker, local-only, KFX for Kindle).
- **Built on:** [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and its
  `tessdata_best` models (Apache-2.0) · [PDFium](https://pdfium.googlesource.com/pdfium/) via
  [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) · [W3C EPUBCheck](https://github.com/w3c/epubcheck)
  · [Vazirmatn](https://github.com/rastikerdar/vazirmatn) font by Saber Rastikerdar (SIL OFL 1.1),
  embedded in the EPUBs · [calibre](https://calibre-ebook.com/) and the
  [KFX Output plugin](https://www.mobileread.com/forums/showthread.php?t=272407) by jhowell ·
  Amazon's Kindle Previewer (installed separately; not bundled).
