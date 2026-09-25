"""Per-page extraction with caching and process-level parallelism."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rtlbook import ocr, pdf, preprocess
from rtlbook.classify import PageClass
from rtlbook.model import Line, Page, Paragraph, Section
from rtlbook.text import normalize_text

_DOC = None  # PDF handle opened once per worker process


@dataclass(frozen=True)
class OcrSettings:
    dpi: int = 300
    lang: str = "fas"
    psm: int = 3
    binarize: bool = True
    crop: float = 0.0


def _init_worker(pdf_path: str) -> None:
    global _DOC
    _DOC = pdf.open_pdf(Path(pdf_path))


def _process_page(number: int, route: str, settings: dict) -> dict:
    start = time.perf_counter()
    page = Page(number, route, settings=settings)
    if route == "ocr":
        img = pdf.render(_DOC, number - 1, settings["dpi"])
        img = preprocess.prepare(img, binarize_=settings["binarize"], crop=settings["crop"])
        page.width, page.height = img.size
        page.lines = ocr.ocr_lines(img, settings["lang"], settings["psm"])
    elif route == "text":
        info = pdf.page_info(_DOC, number - 1)
        page.lines = [Line(normalize_text(t)) for t in info.text.splitlines() if t.strip()]
    page.seconds = round(time.perf_counter() - start, 2)
    return page.to_dict()


def extract_pages(
    pdf_path: Path,
    classes: list[PageClass],
    cache_dir: Path,
    settings: OcrSettings,
    jobs: int,
    on_done: Callable[[Page, bool], None] | None = None,
) -> list[Page]:
    """Extract every page, reusing cached results produced with identical settings."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, Page] = {}
    todo: list[tuple[int, str, dict]] = []

    for c in classes:
        s = {"route": c.route}
        if c.route == "ocr":
            s |= {"dpi": settings.dpi, "lang": settings.lang, "psm": settings.psm,
                  "binarize": settings.binarize, "crop": settings.crop}
        f = cache_dir / f"{c.number:04d}.json"
        if f.exists():
            cached = Page.from_dict(json.loads(f.read_text(encoding="utf-8")))
            if cached.settings == s:
                results[c.number] = cached
                if on_done:
                    on_done(cached, True)
                continue
        todo.append((c.number, c.route, s))

    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_worker, initargs=(str(pdf_path),)) as ex:
        futures = [ex.submit(_process_page, n, r, s) for n, r, s in todo]
        for fut in futures:
            page = Page.from_dict(fut.result())
            (cache_dir / f"{page.number:04d}.json").write_text(
                json.dumps(page.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            results[page.number] = page
            if on_done:
                on_done(page, False)

    return [results[c.number] for c in classes]


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
