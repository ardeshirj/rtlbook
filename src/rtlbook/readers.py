"""Line readers: one printed line's image in, its text and confidence out (ROADMAP.md "Reader slot and scorecard").

Only the scorecard (`rtlbook bench`) reads through this slot so far; `convert` still reads whole pages with Tesseract
(`ocr.ocr_lines`), which finds the lines and reads them in one call.
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from rtlbook import ocr, preprocess


class Reader(Protocol):
    name: str

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        """The line's text, words in reading order, and a confidence (0–100, the reader's own scale) or None."""
        ...


class Tesseract:
    """Tesseract on one line as a raw line (`--psm 13`), the image binarized as `convert` does with whole pages. On the
    1932 book's checked test lines: 6.4% letters wrong, against 19.8% with `--psm 7` (one line, but with Tesseract's
    own line handling, which the crop's bits of the neighbouring lines confuse) and 9.6% reading whole pages."""

    def __init__(self, lang: str = "fas"):
        self.lang = lang
        self.name = f"tesseract {lang}"

    def read(self, image: Image.Image) -> tuple[str, float | None]:
        words = [w for line in ocr.ocr_words(preprocess.prepare(image), self.lang, psm=13) for w in line]
        if not words:
            return "", None
        return " ".join(w.text for w in words), round(sum(w.conf for w in words) / len(words), 1)


READERS = {"tesseract": Tesseract}


def get(name: str) -> Reader:
    if name not in READERS:
        raise ValueError(f"unknown reader {name!r}: one of {', '.join(READERS)}")
    return READERS[name]()
