# Lessons learned (POC, 2026-09-24)

Practical findings from building and testing the proof of concept on 8 Persian novels (3,231 pages)
and a real Kindle. This complements [DESIGN.md §11](../DESIGN.md#11-decisions-and-poc-results-2026-09-24),
which records the decisions and results. Book text is deliberately not quoted here.

## PDFs and text layers

- **Don't trust a Persian text layer just because it renders.** Across 8 books, none had a usable one:
  - **Garbled glyph maps:** Word 2007/2010 exports. Every letter maps to the wrong Unicode code point, and the
    substitution depends on the letter's contextual form.
  - **Visual (reversed) word order:** pdfFactory, iText, Nitro and PScript exports. Letters within a word are
    correct, but words run right-to-left as displayed. A per-page "are common words present?" score *passes*
    these pages. Only a line-level check catches them: in reversed text, sentence punctuation starts a line
    instead of ending it (28–52% vs ≤4%). That's why the checks run per book (`LayerStats` in `classify.py`).
  - **Split words** at glyph boundaries, where the share of one-letter words is 15–20% instead of <10%.
  - **Odd code points:** `ھ` (U+06BE) instead of `ه`, and a Cyrillic `ѧ` used as justification stretching.
- **Some headers exist only in the text layer** (invisible), so OCR never sees them. Others are real text on
  every page and need removing (`running_headers` in `text.py`).

## OCR (Tesseract 5, `fas`, tessdata_best)

- **Binarize first.** Tinted page backgrounds make Tesseract's own thresholding fail on some lines, which
  produces garbage at ~25% confidence. Otsu binarization fixed this, and a fixed threshold works equally well.
- **300 DPI is enough** for born-digital pages. 400 DPI was slower, with no gain.
- **One thread per page, several pages in parallel** (`OMP_THREAD_LIMIT=1`). About 2 s per page on one M2 core,
  and ~2 min for a 500-page book with 8 workers.
- **Font-specific misreads** are consistent within a book, so fix them at the book level, and only when the
  evidence is clear:
  - The Arial Persian comma `،` is never recognized. It comes out as `»` or as a word-final `ء`. It's fixed only
    when the book has almost no real `،`.
  - Closing parentheses come out mirrored, `(…(`, often across line breaks, so they're fixed per paragraph.
  - In a bold font, `!` with no following space reads as `ا`, merging two words. Not fixed yet.
  - `فصل` is often read as `نصل`, and ordinals get mangled or split (`دو از دهم`). Heading detection uses edit
    distance against keywords and ordinals.
- **Confidence averages mislead.** Most low-confidence lines are page numbers, stamps and headers, which are
  removed before the EPUB is built.

## EPUB

- **epubcheck forbids the CSS `direction` property.** RTL must come from `dir="rtl"` on `html`/`body`, plus
  `page-progression-direction="rtl"` on the spine.
- **An empty `<dc:creator>` is invalid.** Omit it when there's no author.
- Our EPUBs passed epubcheck with 0 errors and 0 warnings. Embedding Vazirmatn (OFL) makes rendering consistent
  on readers without good Arabic-script fonts.

## Kindle

- **Kindles can't open EPUB.** Sideloading needs AZW3 or KFX, and conversion always happens somewhere. Send to
  Kindle converts on Amazon's servers. Everything here converts locally.
- **AZW3 (calibre) renders Persian with heavy lag and repeated screen refreshes** on current firmware. Smaller
  sections and removing the embedded font didn't help. **KFX is much faster**, with Persian reflow
  (`fa-reflow-language-1`) and real page numbers taken from the EPUB page list.
- **KFX pipeline:**
  - Kindle Previewer 4 (macOS/Windows only) converts EPUB to **KPF**. KPF is the KDP upload format and can't be
    sideloaded.
  - calibre's **KFX Output** plugin packages KPF into KFX. The plugin runs in the Linux container. Previewer does
    not, so `./rtlbook kfx` calls Previewer on the host.
- **Library placement:** personal documents (PDOC) appear under **Docs**, not Books. `kfx` marks files as books
  (EBOK) by default.
- **Page direction:** in an RTL book, "next page" is a tap on the **left** side.
- **The Kindle's own screens** (page N of M, progress) use the device's language for digits, whatever the book
  uses.
- **Author order:** KFX tools store the author surname-first ("Surname, Initial").
- **Copying from macOS to a USB-mounted Kindle** creates `._*` AppleDouble files. Some Kindles list them as
  broken books. Remove them with `dot_clean -m /Volumes/Kindle/documents`, then eject.
- **Mounting:** older Kindles mount as a drive in Finder. Newer USB-C models use MTP and need OpenMTP.
- **Reading data:** each book gets a `.sdr` folder (reading position, highlights). Deleting a book file doesn't
  delete its `.sdr`, so remove both.

## Docker and macOS gotchas

- **Build for arm64 on Apple Silicon.** amd64 images run emulated and 2–5× slower.
- **The container runs as your UID** (`--user`) so output files aren't owned by root. That UID has no home in
  the container, so set `HOME=/tmp`. Java also needs `-Duser.home=/tmp`, or epubcheck writes its cache to a
  directory literally named `?` in the mounted repo.
- **`TESSDATA_PREFIX` pointing at a models-only directory** hides Tesseract's `tsv` config, and output silently
  becomes plain text. Request TSV with `-c tessedit_create_tsv=1` instead.
- **calibre's plugin server uses a self-signed certificate** that calibre pins. Download plugins with calibre's
  own `get_https_resource_securely`. Don't turn off TLS verification.
- **macOS ships bash 3.2:** `"${arr[@]}"` on an empty array fails under `set -u`. Use `${arr[@]+"${arr[@]}"}`.
- **pypdfium2 v5** renamed `PdfObject.get_pos()` to `get_bounds()`.

## How quality was judged (no ground truth yet)

- **OCR confidence:** mean confidence, plus the share of lines below 60.
- **Common-word rate:** readable Persian is about 0.2–0.35, and garbled text about 0.
- **Word order:** the share of paragraphs *ending* versus *starting* with sentence punctuation.
- **Validity:** epubcheck, and an on-device check (Kindle).

These are proxies. The next step is a small hand-corrected set, to measure the actual character error rate.
