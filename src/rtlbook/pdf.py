"""Book input: PDFs (rendering, text layer, embedded images via PDFium, Apache/BSD licensed) or
folders of page images, one file per page (e.g. an Internet Archive JP2 ZIP, unpacked)."""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

ARABIC_SCRIPT = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2"})


@dataclass
class PageInfo:
    number: int
    image_area: float  # fraction of the page covered by embedded images (upper bound)
    image_dpi: int | None = None  # resolution of the largest image, e.g. a scanned page
    script_chars: int = 0  # Arabic-script letters in the text layer (Persian text drawn by the PDF)


class ImageFolder:
    """Page images in natural file-name order (page2 before page10). Scans have no text layer."""

    def __init__(self, path: Path):
        self.files = sorted(
            (f for f in path.iterdir() if f.suffix.lower() in IMAGE_SUFFIXES and not f.name.startswith(".")),
            key=lambda f: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", f.name)],
        )
        if not self.files:
            raise ValueError(f"No page images ({', '.join(sorted(IMAGE_SUFFIXES))}) in {path}")

    def __len__(self) -> int:
        return len(self.files)

    def image(self, index: int) -> Image.Image:
        with Image.open(self.files[index]) as img:
            return ImageOps.exif_transpose(img)  # phone photos store rotation in EXIF


Book = pdfium.PdfDocument | ImageFolder


def open_book(path: Path) -> Book:
    return ImageFolder(path) if path.is_dir() else pdfium.PdfDocument(str(path))


def digest(path: Path) -> str:
    """Content hash of a PDF, or of a folder's page images (names and bytes, in page order)."""
    h = hashlib.sha256()
    if not path.is_dir():
        h.update(path.read_bytes())
        return h.hexdigest()
    for f in ImageFolder(path).files:
        h.update(f.name.encode() + b"\0" + f.read_bytes())
    return h.hexdigest()


def page_info(doc: Book, index: int) -> PageInfo:
    if isinstance(doc, ImageFolder):
        return PageInfo(index + 1, 1.0)
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
    """Page as a grayscale image. Page images are used at their own resolution (dpi is ignored)."""
    if isinstance(doc, ImageFolder):
        return doc.image(index).convert("L")
    return doc[index].render(scale=dpi / 72, grayscale=True).to_pil()


def largest_image(doc: Book, index: int) -> tuple[bytes, str] | None:
    """Return the biggest embedded image on a page as (bytes, media type), e.g. for a cover.
    For page images, that's the whole page, scaled to at most 1600x2560 (Kindle's cover size)."""
    if isinstance(doc, ImageFolder):
        img = doc.image(index).convert("RGB")
        img.thumbnail((1600, 2560))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        return buf.getvalue(), "image/jpeg"
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
