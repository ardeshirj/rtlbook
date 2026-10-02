# Ground truth: سه قطره خون (Three Drops of Blood), pages 76–77

Real book text for measuring OCR accuracy. Every other test uses made-up sentences; these two pages are
the exception because the book is in the public domain.

- **Book:** Sadegh Hedayat, *سه قطره خون*, first edition, Tehran 1311 (1932), مطبعهٔ روشنائی.
- **Public domain:** Hedayat died in 1951, so the work is free in Iran (life + 50) and in the EU and
  elsewhere with life + 70 (since 2022). Iranian works have no copyright protection in the US.
- **Pages:** 76–77 of the PDF scan (printed page numbers ۷۳–۷۴).

## Files

| File | What it is |
|---|---|
| `p76.txt`, `p77.txt` | The text exactly as printed, one printed line per line. Transcribed from the scan and checked by a person, line by line. Typos in the book are kept, except `بیشتر` on p77, where the print is ambiguous |
| `p76.ocr.json`, `p77.ocr.json` | rtlbook's OCR result for the same pages (Tesseract `fas`, 300 dpi, binarized): each line's text, box and confidence, as cached by `convert` |

No scans are included. `tests/test_ground_truth.py` runs everything after OCR (reading order, then
`rtlbook eval`) on the saved OCR result, and fails if accuracy drops below the baseline. To also re-run
OCR itself, put the scan in `input/Three-Drops-of-Blood.pdf` and run the tests with the whole repo mounted:

```bash
docker run --rm -v "$PWD":/app -w /app --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests
```

Baseline (2026-10-01): CER 6.3% / 8.1%, WER 24% / 27%, line order 100%.
