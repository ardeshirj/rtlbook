# Ground truth: فردا (Tomorrow), Sadegh Hedayat

The whole story, for measuring rtlbook on an **exported PDF** (the main supported type). Every other test uses
made-up sentences; this one and `three-drops/` are the exceptions because the texts are in the public domain.

- **Work:** Sadegh Hedayat, *فردا*, a short story from 1946.
- **Public domain:** Hedayat died in 1951, so the work is free in Iran (life + 50) and in the EU and elsewhere
  with life + 70 (since 2022). Iranian works have no copyright protection in the US.
- **Source:** an 11-page PDF retyped in Word (2006), as circulated online. Page 1 is a title page.

## Files

| File | What it is |
|---|---|
| `reference.txt` | The story's text, pages 2–11, one printed line per line, without the site footer and page numbers. Rebuilt from the PDF's own stored text, so **the letters are exact**; spacing between words and half-spaces may differ from the print in places, which `rtlbook eval`'s letter score ignores |
| `pages.ocr.json` | rtlbook's OCR result for all 11 pages (Tesseract `fas`, `--psm 4`, 300 dpi, binarized), as cached by `convert` |

`tests/test_ground_truth.py` runs the full after-OCR pipeline (reading order, header/footer and junk removal,
paragraphs, comma fixes) on the saved OCR result and fails if the letter error rate rises above the baseline.

Baseline (2026-10-02): CER 0.5% (about 80 of 15,500 letters), WER 3.6%. Most word errors are spacing.
