"""PDF access: rendering, text layer, embedded images (PDFium, Apache/BSD licensed)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


@dataclass
class PageInfo:
    number: int
    chars: int
    text: str
    image_area: float  # fraction of the page covered by embedded images (upper bound)


def open_pdf(path: Path) -> pdfium.PdfDocument:
    return pdfium.PdfDocument(str(path))


def page_info(doc: pdfium.PdfDocument, index: int) -> PageInfo:
    page = doc[index]
    w, h = page.get_size()
    tp = page.get_textpage()
    area = 0.0
    for obj in page.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            area += max(0.0, right - left) * max(0.0, top - bottom)
    return PageInfo(index + 1, tp.count_chars(), tp.get_text_range(), min(1.0, area / (w * h)))


def render(doc: pdfium.PdfDocument, index: int, dpi: int) -> Image.Image:
    return doc[index].render(scale=dpi / 72, grayscale=True).to_pil()


def largest_image(doc: pdfium.PdfDocument, index: int) -> tuple[bytes, str] | None:
    """Return the biggest embedded image on a page as (bytes, media type), e.g. for a cover."""
    best, best_area = None, 0.0
    for obj in doc[index].get_objects():
        if obj.type != pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            continue
        left, bottom, right, top = obj.get_bounds()
        if (area := (right - left) * (top - bottom)) > best_area:
            best, best_area = obj, area
    if best is None:
        return None
    img = best.get_bitmap(render=False).to_pil().convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"
