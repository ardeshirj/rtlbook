"""Per-page extraction with caching and process-level parallelism."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rtlbook import ocr, pdf, preprocess, readers
from rtlbook.model import Line, Page, Paragraph, Section

_DOC = None  # the PDF, opened once per worker process
_READERS: dict = {}  # line readers, made once per worker process
PAGE = "page"  # the reader setting for whole pages read in Tesseract's one call
LINE_PAD = (6, 12)  # pixels above and below, and at each end, around a cut line at 300 dpi (DESIGN.md §4.5)


@dataclass(frozen=True)
class OcrSettings:
    dpi: int = 300
    lang: str = "fas"
    psm: int = 4
    binarize: bool = True
    crop: float = 0.0
    reader: str = PAGE  # PAGE, or a line reader (readers.READERS) for lines cut from the page


def _init_worker(pdf_path: str) -> None:
    global _DOC
    _DOC = pdf.open_book(Path(pdf_path))


def _process_page(number: int, settings: dict) -> dict:
    start = time.perf_counter()
    page = Page(number, "ocr", settings=settings)
    gray = preprocess.crop_margins(pdf.render(_DOC, number - 1, settings["dpi"]), settings["crop"])
    img = preprocess.binarize(gray) if settings["binarize"] else gray
    page.width, page.height = img.size
    if settings.get("reader", PAGE) == PAGE:
        page.lines = ocr.ocr_lines(img, settings["lang"], settings["psm"])
    else:
        page.lines = read_lines(gray, img, settings)
    page.seconds = round(time.perf_counter() - start, 2)
    return page.to_dict()


def read_lines(gray, img, settings: dict) -> list[Line]:
    """Tesseract finds the lines (and column gaps) on the page; each line is cut from the unbinarized page with a
    little padding and read alone by the line reader. Lines it reads as nothing are dropped."""
    name = settings["reader"]
    if name not in _READERS:  # Tesseract in the book's language(s), e.g. fas+ara
        _READERS[name] = readers.Tesseract(settings["lang"]) if name == "tesseract" else readers.get(name)
    reader = _READERS[name]
    py, px = (round(p * settings["dpi"] / 300) for p in LINE_PAD)
    lines = []
    for words in ocr.split_columns(ocr.ocr_words(img, settings["lang"], settings["psm"])):
        x0, x1 = min(w.x0 for w in words), max(w.x1 for w in words)
        y0, y1 = min(w.y0 for w in words), max(w.y1 for w in words)
        text, conf = reader.read(gray.crop((max(0, x0 - px), max(0, y0 - py), min(gray.width, x1 + px),
                                            min(gray.height, y1 + py))))
        if text.strip():
            lines.append(Line(text, (x0, y0, x1, y1), conf))
    return lines


def reader_for(choice: str, document: str) -> str:
    """The reader setting for --reader `choice` ("auto", PAGE or a line reader) and the document type: auto reads a
    scan's lines one by one with Tesseract (fewer letters wrong, twice the time) and an exported PDF's whole pages
    (no gain from cut lines there)."""
    if choice != "auto":
        return choice
    return "tesseract" if document == "scan" else PAGE


def extract_pages(
    pdf_path: Path,
    numbers: list[int],
    cache_dir: Path,
    settings: OcrSettings,
    jobs: int,
    on_done: Callable[[Page, bool], None] | None = None,
) -> list[Page]:
    """OCR every page, reusing cached results produced with identical settings."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, Page] = {}
    todo: list[int] = []
    s = {"route": "ocr", "dpi": settings.dpi, "lang": settings.lang, "psm": settings.psm,
         "binarize": settings.binarize, "crop": settings.crop}
    if settings.reader != PAGE:  # pages cached before the slot existed stay valid for PAGE
        s["reader"] = settings.reader

    for number in numbers:
        f = cache_dir / f"{number:04d}.json"
        if f.exists():
            cached = Page.from_dict(json.loads(f.read_text(encoding="utf-8")))
            if cached.settings == s:
                results[number] = cached
                if on_done:
                    on_done(cached, True)
                continue
        todo.append(number)

    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(str(pdf_path),)) as ex:
        futures = [ex.submit(_process_page, n, s) for n in todo]
        for fut in futures:
            page = Page.from_dict(fut.result())
            (cache_dir / f"{page.number:04d}.json").write_text(
                json.dumps(page.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            results[page.number] = page
            if on_done:
                on_done(page, False)

    return [results[n] for n in numbers]


def split_sections(paras: list[Paragraph], chunk_pages: int = 20) -> list[Section]:
    """Split at detected headings; without headings, chunk every ~N pages at a paragraph boundary."""
    from rtlbook.epub import FA_DIGITS

    if sum(p.heading for p in paras) >= 2:
        sections: list[Section] = []
        for p in paras:
            if p.heading or not sections:
                sections.append(Section(p.text if p.heading else "آغاز", []))
            sections[-1].paragraphs.append(p)
        return sections

    sections = []
    current: list[Paragraph] = []
    start_page = None
    for p in paras:
        pages = [s for s in p.segments if isinstance(s, int)]
        if start_page is None and pages:
            start_page = pages[0]
        if current and pages and start_page is not None and pages[0] - start_page >= chunk_pages:
            sections.append(Section(f"صفحهٔ {str(start_page).translate(FA_DIGITS)}", current))
            current, start_page = [], pages[0]
        current.append(p)
    if current:
        sections.append(Section(f"صفحهٔ {str(start_page or 1).translate(FA_DIGITS)}", current))
    return sections
