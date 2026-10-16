# rtlbook roadmap

What's next for the engine. [DESIGN.md](DESIGN.md) describes what is built and why; this file holds what isn't
built yet. When an item ships, its design goes into DESIGN.md and the item is removed from here, so the two
never overlap. Like DESIGN.md, this is about the engine only.

## 1. Phases

Support grows one document type at a time (DESIGN.md §1); each phase is finished, with measured accuracy, before
the next.

| Phase | Scope | Done when |
|---|---|---|
| **1: Exported PDFs, prose** (current) | OCR every page ✅, - document type in `inspect` ✅, low-confidence warning ✅, title pages / TOC pages kept out of the text ✅, Latin footers kept out of the text, chapters ✅, title and author ✅, an exported-PDF regression test ✅ | Every exported prose book converts to an EPUB you'd read without noticing errors, with measured accuracy on sample pages |
| **2: Publishable output** | Front matter, the book's own TOC, footnotes, half-space normalization; checked in Thorium Reader (Readium) | One complete book you'd happily recommend |
| **3: Scans of modern print, then verse** | Deskew, spreads, low-resolution warnings; couplets laid out as verse in the EPUB | Measured accuracy on scanned pages; verse reads correctly |
| **4: Old letterpress** | A modern reader for scans in the reader slot (see the first work item); a second reading (opt-in AI vision), a review step for disagreements | A 1930s book converts with errors only a review can catch |
| Later | Typewriter, other languages | — |

## 2. Work items

Where the engine is weakest, in the order to work on it (2026-10-14):
1. **The reader on scans** (next item): about ten times more letters wrong than a modern reader.
2. **Spacing:** half-spaces and spaces between words (text clean-up, below); every book, exported PDFs too. Words
   run together after a non-joining letter in scans are split since 2026-10-15 (DESIGN.md §4.7, "Joined words").
3. **Scan preprocessing:** deskew, spreads, uneven backgrounds, low resolution (below).
4. **Layout:** two-column verse with a narrow gutter (~46% of words found), footnotes, bold titles.
5. **Readers' marks in scans** (below).
6. **Unusual fonts** (below).

Line finding, text clean-up, structure, the EPUB builder and validation hold up; they wait until the letters are right.

```mermaid
flowchart TD
    A[PDF] --> B[Inspect<br/>type · script]
    B --> P
    subgraph P [Each page]
        direction LR
        C[Render] --> D[Preprocess<br/>3 deskew · spreads] --> F[Find lines<br/>4 verse · footnotes] --> X[Cut lines] --> R[Reader<br/>1 by document type<br/>6 font fallback]
    end
    P --> T
    subgraph T [Text]
        direction LR
        N[Confidence<br/>1 one scale] --> O[Reading order] --> H[Clean-up<br/>2 spacing<br/>5 handwriting]
    end
    T --> K
    subgraph K [Book]
        direction LR
        I[Structure<br/>4 verse · footnotes] --> J[EPUB 3] --> V[epubcheck]
    end
    classDef planned fill:#fff1c2,stroke:#b8860b,color:#000
    classDef slot fill:#fff1c2,stroke:#b8860b,color:#000,stroke-dasharray: 6 4
    class D,H,I,N planned
    class F,R slot
```

Yellow: a change planned, numbered as the list above; dashed: a slot, where parts can be swapped. Plain: built and
holding up (DESIGN.md §3).

### Reader slot and scorecard — current focus (2026-10-14)
- **Problem:** Tesseract's `fas` model caps accuracy on scans: 6–14% of letters wrong on 1932 letterpress. The
  model shrinks each line to 48 pixels high, where the dots that tell ب ت ن ی apart are a pixel or two, and it was
  trained on text rendered in computer fonts (`synth20170629`). Retraining doesn't lift the cap: `fas_print` (`fas`
  fine-tuned on Persian print, tessdata_contrib) still misreads 7–12% of the same lines. On the very line images
  rtlbook cuts, ParisaOCR's model (Apache-2.0; PaddleOCR's PP-OCRv6 recognizer design run by Kraken, 3.1M
  parameters, lines 96 pixels high) misreads 1.3%. Line finding isn't the limit; the reader is.
- **Goal:** the reader chosen by document type: Tesseract for exported PDFs (0.5–0.8%, 1–2 s a page), a modern
  reader for scans; every change measured on the scorecard before it ships.
- **Where it leads** (DESIGN.md §3 has today's pipeline):

```mermaid
flowchart LR
    D[Page image] --> F[Find lines] --> X[Cut lines] --> R{Reader}
    R -- exported PDF --> T[Tesseract fas<br/>raw line]
    R -- scan --> M[Modern reader<br/>ParisaOCR first]
    T --> C[Confidence<br/>one scale]
    M --> C
    C --> O[Rest of convert<br/>unchanged]
    classDef slot stroke-dasharray: 6 4
    class F,R slot
```

  Dashed: a slot, where parts can be swapped (find lines: Tesseract today, Kraken or PaddleOCR later for verse and
  footnotes; the scan reader: trained further on checked lines later). The scorecard measures every change to one.
- **Approach:**
  1. *Scorecard* (`make bench`): fixed public-domain cases, one number per weak spot, saved per engine version so
     changes compare:
     - the reader alone: the 1932 book's checked test lines as fixed line images; letters wrong;
     - whole pages (line finding + reader + reading order): the same book's five test pages; letters wrong, lines
       lost or merged;
     - spacing, counted apart from letters: spaces and half-spaces;
     - the exported PDF in `tests/data/tomorrow/`: must not get worse;
     - speed and size: seconds a page, memory, image size.

     A case joins when work on its weak spot starts (1960s type, two-column verse), not before.
     **Built (2026-10-14):** `rtlbook bench`, `make bench SET=…`, results in `bench/results.jsonl` and the page
     `bench/README.md`. **Baseline v1 (2026-10-15):** the 1932 book's five test pages, 109 checked lines, their
     spacing rechecked against rule 2, kept as a fixed copy (data `9f4d258f7368`) so every reader is scored on
     the same lines:

     | Reader (each line alone) | Letters wrong | Lines all right | Word gaps wrong | Seconds a line | Memory |
     |---|---|---|---|---|---|
     | ParisaOCR fa-0.1 (ONNX, in rtlbook's image since 2026-10-16) | 0.60% | 93 of 109 | 5.2% | 0.18 | 364 MB |
     | ParisaOCR fa-0.1 (its own reader, PyTorch) | 0.60% | 93 of 109 | 5.2% | 0.52 | 702 MB |
     | Tesseract 5.3.0 `fas` (today) | 8.06% | 15 of 109 | 12.1% | 0.04 | 84 MB |
     | WeightedAI Persian_OCR | 13.18% | 0 of 109 | 11.7% | 0.55 | 1,097 MB |
     | Hezar `crnn-fa-printed-96-long` | 36.77% | 6 of 109 | 8.6% | 0.17 | 577 MB |

     `convert` today on whole pages 30, 54 and 76 (68 lines; 104 and 128 join when their last lines are decided),
     reading a scan with ParisaOCR: 0.32% letters wrong (8.7% before the reader slot, 5.8% with it and Tesseract),
     no line lost or merged and 1 extra, about 5.6 s a page; word gaps wrong 4.0% (11.5% before joined words were
     split and the slot); the exported PDF 0.52%. The first baseline, on 54 of these lines, flattered Tesseract
     (6.4%): the lines checked later are harder for it. The other readers run in their own image (`make readers`,
     `docker/Dockerfile.readers`, 2.7 GB with PyTorch), not rtlbook's.
  2. *Reader slot:* **built (2026-10-15)**, DESIGN.md §4.5: in a scan, Tesseract finds the lines and each cut line is
     read alone, Tesseract behind the slot for now; whole pages 8.7% → 5.8% letters wrong, 1.0 s a page instead of 1.2.
  3. *ParisaOCR as the scan reader:* **built (2026-10-16)**, DESIGN.md §4.5: through ONNX Runtime in rtlbook's
     image (675 MB), its padding computed once (2.2 times faster), its confidence on Tesseract's scale. Still open:
     - *Line finding is now the weak spot:* layout analysis sometimes gives a half-height copy of a line, or a piece
       of one, as a line of its own (pages 65, 124, 134 of the 1932 book), cuts an ornamental page frame into
       "lines" (a 2004 Saadi), and merges two close verse lines into one (a 2002 typesetting, two book pages to a
       PDF page): no reader can read those. ParisaOCR gives fragments and ornaments 0 on Tesseract's scale, real
       lines 80–100, but a few real ones (a verse line, a line in two pieces) fall in the 30s. First a filter by
       confidence or overlap, measured on whole pages; then the line-finding slot (item 4).
     - *Clean-up fixes aimed at Tesseract's habits* (`»` for the Persian comma, `!` read as `ا`): whether they still
       fire, and help, on ParisaOCR's text.
     - *Time on the target machine:* 5.6 s a page on one Apple M2 thread; not yet measured on linux/amd64 hardware
       (only under emulation, which is several times slower). Quantizing to 8 bits is 1.8 times faster at 0.91%
       letters wrong instead of 0.71%, kept in reserve.
     - *The confidence map* (100 − 10 × (100 − c)) rests on 22 of 531 training lines below 96: recheck it when harder
       type (1960s) is checked.
  4. *Later:* continue training the scan reader on checked lines (Kraken's tools); a second slot for line finding
     (Kraken's segmenter, PaddleOCR's layout model) with verse and footnotes; Calamari as another trainable reader
     to measure. Swappable parts, not a plugin framework: a few built-in choices per slot, kept only when they win.
- **Not used:** parts under AGPL or with restricted weights (YOLO-based layout models, Surya); readers measured
  weaker on this type (WeightedAI's Persian_OCR, trained only on rendered lines, and Hezar's CRNN, above); readers
  without Persian (TrOCR, Donut); `fas_print` on the scorecard (an unreviewed pull request to tessdata_contrib,
  fetched from a branch that can change: 4.75% on the first 54 lines, against `fas`'s 6.38%; back if it's merged);
  Kraken's OpenITI Persian model (10.5281/zenodo.7051644), whose output under Kraken 7 is gibberish (its 1.9% in
  DESIGN.md came from an older Kraken).
- **Open:** ParisaOCR on 1960s type has no checked text yet: on a 1963 printing, judged against Tesseract where the
  two disagreed, it was right or closer on all 18 lines a person could decide (Kraken's stock Persian model misread
  20–30% of the same type).

### Letterpress type (1930s–60s) — training set in progress (ahead of phases 3–4)
- **Problem:** Tesseract misreads 6–12% of letters on a 1963 poetry printing and 6–8% on a 1932 prose printing
  (two hand-checked pages each). Most errors are dots (ی→ب, ن→ت, پ→د), گ read as ک, bold titles garbled, and specks
  read as characters. Kraken's stock Persian model does worse on the 1963 type (20–30%), better on the 1932 (2%).
- **Goal:** checked lines of old type: the test set the scorecard measures readers with, and later the data to
  fine-tune the scan reader on (not Tesseract: see the item above).
- **Approach:**
  1. *Line transcription page:* the review page (DESIGN.md §6) for whole lines: the line image, the OCR text
     filled in, and uncertain words (low confidence, or not in a word list) highlighted with suggestions. Its
     output is both ground truth and training data.
  2. *Dot-aware word suggestions:* for a word that isn't in the word list, real words with the same letter shapes
     but other dots (ب پ ت ث ن ی, ج چ ح خ, د ذ, ر ز ژ, س ش, ک گ, …), ranked by how often they occur elsewhere in
     the book. Offered on the review page, not applied automatically, until measured.
  3. *Fine-tuned Tesseract model, dropped (2026-10-14):* Tesseract's model caps the gain (`fas_print`, fine-tuned
     on more lines than one book has, still misreads 7–12%). The checked lines measure readers instead, and train
     a modern one later. Training lines are scans and never go into git; only a model might ship.
- **Not covered here:** layout (next item).
- **Trial (2026-10-07):** the line transcription page was tried on the 1963 printing: 349 lines decided, 324 of
  them checked. The data was then dropped for a clean start; the lessons were kept: settle the rules (with real
  examples) before checking; a routine second look at lines that differ most from OCR (it changed 12 of 21); crops
  must include marks at line edges; keep an append-only history of decisions.
- **Next:** a clean start on a book that is public domain everywhere, the 1932 Hedayat printing in `tests/data/`
  (1930s type; a 1960s book follows). Its lines are checked in a separate tool that reads the set from the private
  bucket (push and pull, [TRAINING-DATA.md](TRAINING-DATA.md)).

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
letters, spacing glitches, brings back per-PDF rules), or opt-in AI vision. Deferred to keep the pipeline simple.

### Planned, by stage
- **Input:** a folder of page images instead of a PDF, for scans: old books are often only available as page
  images (dropped 2026-10-06, DESIGN.md §4.2).
- **Preprocessing (scans):** deskew, two-page spread splitting (right-hand page first), denoise, adaptive
  binarization, low-resolution warnings.
- **Layout:** footnotes, page furniture in Latin script, multi-column prose.
- **OCR engines (phase 4):** the reader slot is now the current focus (above). Still planned: choose the engine per book
  from a reviewed sample page; where two engines disagree, a person decides on the review page. An AI vision
  engine would send page images to an outside service: opt-in only, never the default.
- **Document model:** block types (footnote, verse, table), printed page labels.
- **Text clean-up:** half-space (ZWNJ) normalization (`می گویم` → `می‌گویم`), and spaces read as half-spaces
  (`داشته‌بود` for `داشته بود`); joined words from the whole book's words in the scorecard too (it takes them from the
  scored pages); in some bold fonts `!` without a
  following space OCRs as `ا` and merges words, fixable with corpus word statistics.
- **AI correction (opt-in):** correct low-confidence lines with a vision model, compared back to the OCR output;
  large edits are flagged, not accepted. Off by default.
- **Structure:** footnotes (`noteref` → `footnote`); couplets laid out as verse.
- **Review page:** reviewing disagreements between two OCR engines; proofreading a whole book.
- **Readers:** check the EPUBs in Thorium Reader (Readium) and fix what renders wrong there: page direction, the
  embedded font, the page list, the TOC.

## 3. Later
- Typewritten books (none found yet).
- Arabic, Urdu and Hebrew, as configuration where possible.
- Side outputs: searchable PDF, Markdown/HTML/DOCX, hOCR/ALTO; fixed-layout EPUB as a fallback where reflow fails.
- Narrated EPUBs (EPUB 3 media overlays): audio synced to the text, sentence by sentence, so the book reads aloud
  with the text highlighted even where the device has no Farsi voice (Thorium plays them). The audio comes from a
  Farsi TTS voice (Azure's neural voices) or aligned from a recording. Farsi doesn't write short vowels or the
  ezafe, so a voice misreads some words; verse needs vowel marks or a pronunciation list. Try first: DAISY
  Pipeline 2's EPUB 3 enhancer (TTS), Storyteller (aligns a recording with Whisper).
