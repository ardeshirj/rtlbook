# rtlbook roadmap

What's next for the engine. [DESIGN.md](DESIGN.md) describes what is built and why; this file holds what isn't
built yet. When an item ships, its design goes into DESIGN.md and the item is removed from here, so the two
never overlap. Like DESIGN.md, this is about the engine only.

## 1. Phases

Support grows one document type at a time (DESIGN.md §1); each phase is finished, with measured accuracy, before
the next.

| Phase | Scope | Done when |
|---|---|---|
| **1: Exported PDFs, prose** (current) | OCR every page ✅, document type in `inspect` ✅, low-confidence warning ✅, title pages / TOC pages kept out of the text ✅, Latin footers kept out of the text, chapters ✅, title and author ✅, an exported-PDF regression test ✅ | Every exported prose book converts to an EPUB/KFX you'd read without noticing errors, with measured accuracy on sample pages |
| **2: Publishable output** | Front matter, the book's own TOC, footnotes, half-space normalization, KEPUB; tested on Kindle, KOReader, Apple Books and an Android reader | One complete book you'd happily recommend |
| **3: Scans of modern print, then verse** | Deskew, spreads, low-resolution warnings; couplets laid out as verse in the EPUB | Measured accuracy on scanned pages; verse reads correctly |
| **4: Old letterpress** | Second engine (Kraken and/or opt-in AI vision), engine choice per book, a review step for disagreements | A 1930s book converts with errors only a review can catch |
| Later | Typewriter, other languages, searchable PDF / Markdown outputs | — |

## 2. Work items

### 1960s letterpress type — in progress (ahead of phases 3–4)
- **Problem:** on a 1963 poetry printing, Tesseract misreads 6–12% of letters (two hand-checked pages). Most
  errors are dots (ی→ب, ن→ت, پ→د), گ read as ک, bold poem titles garbled, and specks read as characters.
  Kraken's stock Persian model does worse on this type (20–30%).
- **Goal:** halve the letter error rate on held-out pages of that book, with no loss on the baselines in
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
- **Notes:** `output/poc/35-period-type/` (git-ignored).

### Verse layout (phase 3)
- Free verse: keep one printed line per line instead of joining lines into prose paragraphs.
- A wide word gap inside one verse line is sometimes split as a column gap; the split should only fire on real
  two-column verse.
- Couplets laid out as verse in the EPUB.

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
- **Outputs:** KEPUB (Kobo's EPUB variant, via `kepubify`); author display order on Kindle (OPF `file-as`).
- **Readers:** test on Apple Books and Kobo/KOReader (Kindle is tested).
- **Repository:** CI that builds the image and runs the tests.

## 3. Later
- Typewritten books (none found yet).
- Arabic, Urdu and Hebrew, as configuration where possible.
- Side outputs: searchable PDF, Markdown/HTML/DOCX, hOCR/ALTO; fixed-layout EPUB as a fallback where reflow fails.
