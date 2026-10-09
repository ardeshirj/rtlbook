# rtlbook roadmap

What's next for the engine. [DESIGN.md](DESIGN.md) describes what is built and why; this file holds what isn't
built yet. When an item ships, its design goes into DESIGN.md and the item is removed from here, so the two
never overlap. Like DESIGN.md, this is about the engine only.

## 1. Phases

Support grows one document type at a time (DESIGN.md §1); each phase is finished, with measured accuracy, before
the next.

| Phase | Scope | Done when |
|---|---|---|
| **1: Exported PDFs, prose** (current) | OCR every page ✅, document type in `inspect` ✅, low-confidence warning ✅, title pages / TOC pages kept out of the text ✅, Latin footers kept out of the text, chapters ✅, title and author ✅, an exported-PDF regression test ✅ | Every exported prose book converts to an EPUB you'd read without noticing errors, with measured accuracy on sample pages |
| **2: Publishable output** | Front matter, the book's own TOC, footnotes, half-space normalization; checked in Thorium Reader (Readium) | One complete book you'd happily recommend |
| **3: Scans of modern print, then verse** | Deskew, spreads, low-resolution warnings; couplets laid out as verse in the EPUB | Measured accuracy on scanned pages; verse reads correctly |
| **4: Old letterpress** | Second engine (Kraken and/or opt-in AI vision), engine choice per book, a review step for disagreements | A 1930s book converts with errors only a review can catch |
| Later | Typewriter, other languages | — |

## 2. Work items

### Letterpress type (1930s–60s) — trial done; first training set next (ahead of phases 3–4)
- **Problem:** Tesseract misreads 6–12% of letters on a 1963 poetry printing and 6–8% on a 1932 prose printing
  (two hand-checked pages each). Most errors are dots (ی→ب, ن→ت, پ→د), گ read as ک, bold titles garbled, and specks
  read as characters. Kraken's stock Persian model does worse on the 1963 type (20–30%), better on the 1932 (2%).
- **Goal:** halve the letter error rate on held-out pages of the training book, with no loss on the baselines in
  `tests/data/`; then check a second book printed in the same type.
- **Approach:**
  1. *Line transcription page:* the review page (DESIGN.md §6) for whole lines: the line image, the OCR text
     filled in, and uncertain words (low confidence, or not in a word list) highlighted with suggestions. Its
     output is both ground truth and training data.
  2. *Dot-aware word suggestions:* for a word that isn't in the word list, real words with the same letter shapes
     but other dots (ب پ ت ث ن ی, ج چ ح خ, د ذ, ر ز ژ, س ش, ک گ, …), ranked by how often they occur elsewhere in
     the book. Offered on the review page, not applied automatically, until measured.
  3. *Fine-tuned Tesseract model:* continue training `fas` (`tessdata_best`) on the checked lines. A separate
     model chosen per book from a reviewed sample page, not a replacement for `fas`. Training lines are scans and
     never go into git; only the model might ship.
- **Not covered here:** layout (next item).
- **Trial (2026-10-07):** the line transcription page was tried on the 1963 printing: 349 lines decided, 324 of
  them checked. The data was then dropped for a clean start; the lessons were kept: settle the rules (with real
  examples) before checking; a routine second look at lines that differ most from OCR (it changed 12 of 21); crops
  must include marks at line edges; keep an append-only history of decisions.
- **Next:** a clean start on a book that is public domain everywhere, the 1932 Hedayat printing in `tests/data/`
  (1930s type; a 1960s book follows). Its lines are checked in a separate tool that reads the set from the private
  bucket (push and pull, [TRAINING-DATA.md](TRAINING-DATA.md)).
- **Notes:** `output/poc/35-period-type/` (git-ignored).

### Verse layout (phase 3)
- Free verse: keep one printed line per line instead of joining lines into prose paragraphs.
- A wide word gap inside one verse line is sometimes split as a column gap; the split should only fire on real
  two-column verse.
- Couplets laid out as verse in the EPUB.

### Readers' marks in scans (open)
- **Problem:** scans of library copies carry earlier readers' handwriting: notes in the margins and between
  lines, underlining, arrows. OCR reads it as Persian-looking nonsense words inside the lines of text, and a note
  written over printed words damages them too. Seen on a 1963 poetry printing (a page of glosses) and in a 1925
  Masnavi scan (pencil notes). Nothing in the pipeline catches it today.
- **Goal:** no handwriting reaches the book as text. Where printed words are lost under it, the book shows a
  visible gap marker instead of a guess or nonsense, the way printed editions mark an unreadable word.
- **Approach (to investigate):**
  1. *Drop margin notes:* printed lines share column edges across the book; words beyond those edges with low
     confidence are notes, not text.
  2. *Mark damaged words:* a word with very low confidence inside an otherwise good line becomes a marker in the
     EPUB (for example `[ناخوانا]`, "illegible"), styled so readers see something is missing. The threshold is
     measured on checked pages so real words aren't replaced.
  3. *Report the pages:* list pages that look marked up in `report.json`, so a person can check them.
  4. *Recover from the print, never from the handwriting:* a note is a reader's gloss or "correction", not the
     printed text. A lost word is filled in only from another source of the same text: a clean scan of another
     copy of the same printing (which rtlbook could OCR and use for just the damaged spots), or else a later
     edition, recorded as such. Until then the gap marker stays.
- **Measure:** on checked pages from both books, nonsense words that reach the text and real words wrongly
  dropped or marked.

### Unusual fonts (open)
Decorative fonts defeat Tesseract. `convert` warns (mean confidence below 70) but has no fallback. Findings on one
book (a handwriting-style font, confidence 55): no Tesseract setting helped (resolution, binarization,
`ara`/`fas+ara`, `--psm 6`: word recall 37–45%); the PDF's own stored text, rebuilt from character positions, had
**every letter right** but stray spaces inside about 1 word in 5. Options: an opt-in text-layer fallback (perfect
letters, spacing glitches, brings back per-PDF rules), or opt-in AI vision. Deferred to keep the pipeline simple;
prototype in `output/poc/31-type-a/geometry.py`, measurements in `output/poc/33-decorative/` (git-ignored).

### Planned, by stage
- **Input:** a folder of page images instead of a PDF, for scans: old books are often only available as page
  images (dropped 2026-10-06, DESIGN.md §4.2).
- **Preprocessing (scans):** deskew, two-page spread splitting (right-hand page first), denoise, adaptive
  binarization, low-resolution warnings.
- **Layout:** footnotes, page furniture in Latin script, multi-column prose.
- **OCR engines (phase 4):** a small engine interface when a second engine is added; choose the engine per book
  from a reviewed sample page; where two engines disagree, a person decides on the review page. An AI vision
  engine would send page images to an outside service: opt-in only, never the default.
- **Document model:** block types (footnote, verse, table), printed page labels.
- **Text clean-up:** half-space (ZWNJ) normalization (`می گویم` → `می‌گویم`); in some bold fonts `!` without a
  following space OCRs as `ا` and merges words, fixable with corpus word statistics.
- **AI correction (opt-in):** correct low-confidence lines with a vision model, compared back to the OCR output;
  large edits are flagged, not accepted. Off by default.
- **Structure:** footnotes (`noteref` → `footnote`); couplets laid out as verse.
- **Review page:** reviewing disagreements between two OCR engines; proofreading a whole book.
- **Readers:** check the EPUBs in Thorium Reader (Readium) and fix what renders wrong there: page direction, the
  embedded font, the page list, the TOC.
- **Repository:** CI that builds the image and runs the tests.

## 3. Later
- Typewritten books (none found yet).
- Arabic, Urdu and Hebrew, as configuration where possible.
- Side outputs: searchable PDF, Markdown/HTML/DOCX, hOCR/ALTO; fixed-layout EPUB as a fallback where reflow fails.
