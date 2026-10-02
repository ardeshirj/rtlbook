"""What kind of document a PDF is: exported from a word processor (text drawn by the PDF) or a scan
(each page is a picture). rtlbook OCRs every page either way; scans aren't supported yet (old print
needs other engines), so convert warns about them."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from rtlbook.pdf import PageInfo

SCAN_COVER = 0.6  # a page mostly covered by pictures is a scan...
PART_COVER = 0.2  # ...and so is one partly covered by pictures (scanned strips pasted into Word)...
FEW_LETTERS = 200  # ...whose text layer has almost no Persian letters (at most a header or footer)
LOW_DPI = 200  # below this, letters and their dots get lost


@dataclass
class PageKind:
    number: int
    kind: str  # "exported" | "scan"
    dpi: int | None = None


def page_kind(info: PageInfo) -> PageKind:
    if info.image_area >= SCAN_COVER or (info.image_area >= PART_COVER and info.script_chars < FEW_LETTERS):
        return PageKind(info.number, "scan", info.image_dpi)
    return PageKind(info.number, "exported")


@dataclass
class DocType:
    kind: str  # "exported" | "scan"
    pages: int
    scan_pages: int
    dpi: int | None  # median resolution of scanned pages

    @property
    def supported(self) -> bool:
        return self.kind == "exported"

    def message(self) -> str:
        if self.supported:
            return f"Exported PDF ({self.pages} pages): supported."
        dpi = f", about {self.dpi} dpi" if self.dpi else ""
        low = f" Below {LOW_DPI} dpi, expect many misread letters." if self.dpi and self.dpi < LOW_DPI else ""
        return (f"Scanned book ({self.scan_pages} of {self.pages} pages are page images{dpi}). Scans aren't "
                f"supported yet: OCR works, but expect more errors, especially in older print.{low}")


def document_type(kinds: list[PageKind]) -> DocType:
    scans = [k for k in kinds if k.kind == "scan"]
    dpis = [k.dpi for k in scans if k.dpi]
    kind = "scan" if len(scans) >= len(kinds) / 2 else "exported"
    return DocType(kind, len(kinds), len(scans), int(statistics.median(dpis)) if dpis else None)
