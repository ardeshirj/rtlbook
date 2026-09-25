# rtlbook

Convert PDF books in right-to-left languages (Persian first) into reflowable EPUB 3. It handles
born-digital PDFs with broken text layers, scans, and (later) typewritten books. See
[DESIGN.md](DESIGN.md) for the full plan.

## Quick start (Docker)

```bash
docker build -f docker/Dockerfile -t rtlbook:dev .

./rtlbook inspect book.pdf                     # which pages need OCR?
./rtlbook convert book.pdf -o book.epub --title "…" --author "…"
./rtlbook kfx book.epub                        # Kindle version (macOS + Kindle Previewer 4)
```

`./rtlbook` runs the CLI in the container, with the current directory mounted at `/work`.
Paths must be relative to it and inside it. Your local `src/` is mounted too, so code changes
apply without a rebuild.

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
| `--work DIR` | Cache directory. Re-runs reuse per-page OCR results |

What `convert` does automatically:
- **Checks the PDF's text layer** for garbled glyph mappings, reversed (visual) word order, and split words. If it's unusable (so far, every book tested), the pages are OCR'd.
- **Cleans up OCR:** Persian letters and digits, commas read as `»`/`ء`, mirrored parentheses, stray marks, and **running headers/watermarks** repeated on many pages.
- **Rebuilds paragraphs**, including dialogue lines (`سارا- …`, `علی : …`), and joins them across page breaks.
- **Detects chapters** even when OCR misreads the heading (`نصل دو از دهم` → `فصل دوازدهم`). Books without chapters get ~20-page sections.
- **Builds a valid EPUB 3** (epubcheck) with RTL page direction, the Vazirmatn font, cover, and print page list.

Typical real-world run (site credits on the title pages, extra front pages):

```bash
./rtlbook convert samples/Gandom.pdf -o out/Gandom.epub --title "گندم" --author "م. مودب‌پور" \
  --drop-lines 'کتابخانه مجازی|تهیه و تنظیم' --pages 2-557
./rtlbook kfx out/Gandom.epub
```

The work directory (`<output>.rtlbook/`) keeps `pages/*.json` (per-page OCR with boxes and
confidence), `pages.txt`, `paragraphs.txt`, `report.json` and `epubcheck.txt` for review.

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
