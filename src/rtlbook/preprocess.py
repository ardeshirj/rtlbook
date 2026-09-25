"""Page image cleanup before OCR."""

from __future__ import annotations

from PIL import Image


def otsu_threshold(img: Image.Image) -> int:
    hist = img.histogram()[:256]
    total = sum(hist)
    sum_all = sum(i * h for i, h in enumerate(hist))
    w_bg = sum_bg = 0
    best, thr = 0.0, 128
    for t in range(256):
        w_bg += hist[t]
        if w_bg == 0 or w_bg == total:
            continue
        sum_bg += t * hist[t]
        m_bg, m_fg = sum_bg / w_bg, (sum_all - sum_bg) / (total - w_bg)
        var = w_bg * (total - w_bg) * (m_bg - m_fg) ** 2
        if var > best:
            best, thr = var, t
    return thr


def binarize(img: Image.Image) -> Image.Image:
    """Global Otsu binarization. Tinted page backgrounds otherwise confuse Tesseract's own
    thresholding on some lines (seen as garbage lines at ~25% confidence)."""
    img = img.convert("L")
    thr = otsu_threshold(img)
    return img.point(lambda v: 255 if v > thr else 0)


def crop_margins(img: Image.Image, frac: float) -> Image.Image:
    """Cut a fixed fraction off each edge, e.g. to drop decorative page frames."""
    if frac <= 0:
        return img
    w, h = img.size
    dx, dy = int(w * frac), int(h * frac * 0.8)
    return img.crop((dx, dy, w - dx, h - dy))


def prepare(img: Image.Image, *, binarize_: bool = True, crop: float = 0.0) -> Image.Image:
    img = crop_margins(img, crop)
    return binarize(img) if binarize_ else img
