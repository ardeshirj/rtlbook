# Lessons learned

Practical findings from building and testing rtlbook, starting with the first prototype on 8 Persian novels
(3,231 pages, 2026-09-24).
This complements [DESIGN.md §11](DESIGN.md#11-decisions-and-poc-results-2026-09-24),
which records the decisions and results. Book text is deliberately not quoted here.

## PDFs and text layers

- **Don't trust a Persian text layer just because it renders.** Across 8 books, none had a usable one
  (3 more in October: same story). Outcome: rtlbook now OCRs every page and ignores the text layer:
  - **Garbled glyph maps:** Word 2007/2010 exports. Every letter maps to the wrong Unicode code point, and the
    substitution depends on the letter's contextual form.
  - **Visual (reversed) word order:** pdfFactory, iText, Nitro and PScript exports. Letters within a word are
    correct, but words run right-to-left as displayed. A per-page "are common words present?" score *passes*
    these pages. Only a line-level check catches them: in reversed text, sentence punctuation starts a line
    instead of ending it (28–52% vs ≤4%). (These checks ran per book until the text layer was dropped.)
  - **Split words** at glyph boundaries, where the share of one-letter words is 15–20% instead of <10%.
  - **Odd code points:** `ھ` (U+06BE) instead of `ه`, and a Cyrillic `ѧ` used as justification stretching.
- **Some headers exist only in the text layer** (invisible), so OCR never sees them. Others are real text on
  every page and need removing (`running_headers` in `text.py`).

## OCR (Tesseract 5, `fas`, tessdata_best)

- **Binarize first.** Tinted page backgrounds make Tesseract's own thresholding fail on some lines, which
  produces garbage at ~25% confidence. Otsu binarization fixed this, and a fixed threshold works equally well.
- **300 DPI is enough** for born-digital pages. 400 DPI was slower, with no gain.
- **Use `--psm 4`, not the automatic layout (`--psm 3`).** The automatic layout silently dropped lines set in
  larger type. `--psm 4` merges two-column verse into one line, which rtlbook splits again at aligned gaps.
- **Decorative fonts defeat Tesseract** (confidence ~55%, dots dropped). Check the mean confidence in
  `report.json`: 80–87 is normal for exported PDFs. No Tesseract setting fixed it, but the PDF's stored text
  had every letter right (scrambled order, spacing glitches): a possible fallback, not built yet.
- **Measure, don't eyeball.** Misread Persian words often look like real words: a first hand-correction pass
  of OCR text missed about half the errors. Compare against a checked reference with `rtlbook eval`.
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
- **Layout analysis alone** (`TessBaseAPIAnalyseLayout`, C API only: the command line always reads) finds the same
  lines in a sixth of the time, but some word boxes come back as the whole page: take only word boxes inside their
  line's box (`ocr.layout_words`), or a line is lost (two dialogue lines on one page of the 1932 book). Its boxes are
  ~4 pixels tighter above and below than a reading's, so cut lines need a little more padding.
- **Tesseract 5.5.0 (Debian trixie) finds fewer lines than 5.3.0** (2026-10-16): the same model reads the same,
  but it dropped 5 of 301 lines of an exported story (0.52% → 2.08% letters wrong) and a line of the 1932 test pages
  (0.32% → 1.26%), while finding fewer junk and merged lines on hard scans. The image stays on bookworm's 5.3.0.
- **A cut line reads better than the same line on the page** for Tesseract on old type (1932: 8.7% → 5.8% letters
  wrong on whole pages), but not on an exported PDF (0.52% either way). Choose its padding on many lines: on 68 test
  lines each padding tried gave a different "best".
- **Confidence averages mislead.** Most low-confidence lines are page numbers, stamps and headers, which are
  removed before the EPUB is built.

## Neural line readers (ParisaOCR's model)

- **Read a model's training code before trimming its input.** ParisaOCR's model was trained on lines padded to 2560
  columns, and its squeeze-and-excitation blocks average over that whole width, padding included. Padding to 2048
  instead took letters wrong from 0.68% to 18%; to the line's own width, 57%. Keeping the averages right (the line
  plus a 128-column margin, the rest added by calculation) keeps the output identical.
- **`torch.onnx.export` freezes Python numbers.** Sizes computed in Python (`x.shape[2]` in a pooling kernel,
  `w_out / w_in` and `clamp(max=w_out)` for the output lengths) become constants of the sample's width, and longer
  lines were silently cut. Compute them from `torch._shape_as_tensor(x)`, and check the file at several widths.
- **Equal confidences aren't equal across readers.** ParisaOCR's sits near 100 even on poor lines (below 96 it is
  already bad); map it to the scale the thresholds were tuned on, by errors, not by rank: ranking its values onto
  Tesseract's spread would call a well-read book poor.
- **A bidi round trip isn't exact.** ParisaOCR's model reads display order, turned into reading order with a line's
  own base direction; a line with more Latin than Persian letters is taken as left to right, so its Persian words
  come out in the wrong order. Rare in Persian books; test with lines that are mostly Persian.

## EPUB

- **epubcheck forbids the CSS `direction` property.** RTL must come from `dir="rtl"` on `html`/`body`, plus
  `page-progression-direction="rtl"` on the spine.
- **An empty `<dc:creator>` is invalid.** Omit it when there's no author.
- Our EPUBs passed epubcheck with 0 errors and 0 warnings. Embedding the font (Parastoo, OFL; Vazirmatn at the
  time) makes rendering consistent on readers without good Arabic-script fonts.

## Docker and macOS gotchas

- **Build for arm64 on Apple Silicon.** amd64 images run emulated and 2–5× slower.
- **The container runs as your UID** (`--user`) so output files aren't owned by root. That UID has no home in
  the container, so set `HOME=/tmp`. Java also needs `-Duser.home=/tmp`, or epubcheck writes its cache to a
  directory literally named `?` in the mounted repo.
- **`TESSDATA_PREFIX` pointing at a models-only directory** hides Tesseract's `tsv` config, and output silently
  becomes plain text. Request TSV with `-c tessedit_create_tsv=1` instead.
- **macOS ships bash 3.2:** `"${arr[@]}"` on an empty array fails under `set -u`. Use `${arr[@]+"${arr[@]}"}`.
- **pypdfium2 v5** renamed `PdfObject.get_pos()` to `get_bounds()`.
- **PyTorch ignores `OMP_THREAD_LIMIT`.** rtlbook's image sets it to 1 (pages run side by side, one Tesseract
  thread each); PyTorch still starts a thread per CPU, and they wait on each other: a model loaded in seconds and
  then never finished its first line (an hour at 100% of one CPU). `readers.py` sets PyTorch's threads to the limit.
  Kraken's OpenITI model hanging while it loaded was most likely the same.

## How quality was judged (no ground truth yet)

- **OCR confidence:** mean confidence, plus the share of lines below 60.
- **Common-word rate:** readable Persian is about 0.2–0.35, and garbled text about 0.
- **Word order:** the share of paragraphs *ending* versus *starting* with sentence punctuation.
- **Validity:** epubcheck, and reading the result on a device.

These are proxies. The next step is a small hand-corrected set, to measure the actual character error rate.
