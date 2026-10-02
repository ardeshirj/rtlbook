# Real, public-domain book text: see tests/data/*/README.md. Fails if accuracy gets worse.
import json
import shutil
from pathlib import Path

import pytest

from rtlbook.evaluate import compare
from rtlbook.layout import reading_order
from rtlbook.model import Page

DATA = Path(__file__).parent / "data" / "three-drops"
SCAN = Path(__file__).parents[1] / "input" / "Three-Drops-of-Blood.pdf"
# Baseline CER per page (2026-10-01) plus a little slack. Lower these when OCR gets better.
MAX_CER = {76: 0.07, 77: 0.09}


def ocr_text(page: Page) -> str:
    return "\n".join(ln.text for ln in reading_order(page.lines))


@pytest.mark.parametrize("number", sorted(MAX_CER))
def test_saved_ocr_meets_baseline(number):
    page = Page.from_dict(json.loads((DATA / f"p{number}.ocr.json").read_text(encoding="utf-8")))
    r = compare((DATA / f"p{number}.txt").read_text(encoding="utf-8"), ocr_text(page))
    assert r.trimmed is None
    assert r.cer <= MAX_CER[number], f"CER {r.cer:.1%} > {MAX_CER[number]:.0%}"
    assert r.line_order == 1


@pytest.mark.skipif(not SCAN.exists() or not shutil.which("tesseract"), reason="needs the scan in input/ and Tesseract")
@pytest.mark.parametrize("number", sorted(MAX_CER))
def test_fresh_ocr_meets_baseline(number):
    from rtlbook import ocr, pdf, preprocess

    saved = Page.from_dict(json.loads((DATA / f"p{number}.ocr.json").read_text(encoding="utf-8")))
    s = saved.settings
    img = pdf.render(pdf.open_book(SCAN), number - 1, s["dpi"])
    img = preprocess.prepare(img, binarize_=s["binarize"], crop=s["crop"])
    page = Page(number, "ocr", *img.size, lines=ocr.ocr_lines(img, s["lang"], s["psm"]))
    r = compare((DATA / f"p{number}.txt").read_text(encoding="utf-8"), ocr_text(page))
    assert r.cer <= MAX_CER[number], f"CER {r.cer:.1%} > {MAX_CER[number]:.0%}"


TOMORROW = Path(__file__).parent / "data" / "tomorrow"
TOMORROW_MAX_CER = 0.007  # baseline 0.5% (2026-10-02)


def test_exported_pdf_full_pipeline_meets_baseline():
    from rtlbook.text import build_paragraphs

    pages = [Page.from_dict(d) for d in json.loads((TOMORROW / "pages.ocr.json").read_text(encoding="utf-8"))]
    for page in pages:
        page.lines = reading_order(page.lines)
    text = "\n".join(p.text for p in build_paragraphs(pages))
    r = compare((TOMORROW / "reference.txt").read_text(encoding="utf-8"), text)
    assert r.trimmed is None
    assert r.cer <= TOMORROW_MAX_CER, f"CER {r.cer:.2%} > {TOMORROW_MAX_CER:.1%}"
    assert "mihanblog" not in text and "جیوه" not in text  # the site footer, read as junk, is gone
