"""Book input: PDFs (rendering, text layer, embedded images via PDFium, Apache/BSD licensed)."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

ARABIC_SCRIPT = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")


@dataclass
class PageInfo:
    number: int
    image_area: float  # fraction of the page covered by embedded images (upper bound)
    image_dpi: int | None = None  # resolution of the largest image, e.g. a scanned page
    script_chars: int = 0  # Arabic-script letters in the text layer (Persian text drawn by the PDF)


Book = pdfium.PdfDocument


def open_book(path: Path) -> Book:
    return pdfium.PdfDocument(str(path))


def digest(path: Path) -> str:
    """Content hash of a PDF."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_info(doc: Book, index: int) -> PageInfo:
    page = doc[index]
    w, h = page.get_size()
    area, dpi, largest = 0.0, None, 0.0
    for obj in page.get_objects():
        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            left, bottom, right, top = obj.get_bounds()
            a = max(0.0, right - left) * max(0.0, top - bottom)
            area += a
            if a > largest and right > left:
                largest, dpi = a, round(obj.get_px_size()[0] / ((right - left) / 72))
    tp = page.get_textpage()
    script = len(ARABIC_SCRIPT.findall(tp.get_text_range()))
    return PageInfo(index + 1, min(1.0, area / (w * h)), dpi, script)


def render(doc: Book, index: int, dpi: int) -> Image.Image:
    """Page as a grayscale image."""
    return doc[index].render(scale=dpi / 72, grayscale=True).to_pil()


COVER_DPI = 150  # a page rendered as the cover: about 1,200 px wide for a book page


def largest_image(doc: Book, index: int) -> tuple[bytes, str] | None:
    """Return the biggest embedded image on a page as (bytes, media type), e.g. for a cover. When it covers less than
    most of the area all the page's images cover together (a scan stored in strips), that whole area instead, cut from
    the page rendered in colour: the scan, without the page's empty margins around it."""
    best, best_area, union = None, 0.0, None
    for obj in doc[index].get_objects():
        if obj.type != pdfium.raw.FPDF_PAGEOBJ_IMAGE:
            continue
        left, bottom, right, top = obj.get_bounds()
        union = (left, bottom, right, top) if union is None else \
            (min(union[0], left), min(union[1], bottom), max(union[2], right), max(union[3], top))
        if (area := (right - left) * (top - bottom)) > best_area:
            best, best_area = obj, area
    if best is None:
        return None
    left, bottom, right, top = union
    if best_area < 0.9 * (right - left) * (top - bottom):
        scale = COVER_DPI / 72
        page_h = doc[index].get_size()[1]
        img = doc[index].render(scale=scale).to_pil().convert("RGB")
        img = img.crop((round(left * scale), round((page_h - top) * scale), round(right * scale), round((page_h - bottom) * scale)))
    else:
        img = best.get_bitmap(render=False).to_pil().convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"
