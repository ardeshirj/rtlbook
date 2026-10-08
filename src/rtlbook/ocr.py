"""Tesseract OCR engine (CLI via subprocess, TSV output for line boxes and confidences)."""

from __future__ import annotations

import csv
import io
import subprocess
from collections import defaultdict
from dataclasses import dataclass

from PIL import Image

from rtlbook.model import Line


def tesseract_version() -> str:
    out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()[0]


def ocr_lines(image: Image.Image, lang: str, psm: int = 3) -> list[Line]:
    lines = []
    for part in split_columns(ocr_words(image, lang, psm)):
        text = " ".join(wd.text for wd in part)
        conf = sum(wd.conf for wd in part) / len(part)
        box = (min(wd.x0 for wd in part), min(wd.y0 for wd in part), max(wd.x1 for wd in part), max(wd.y1 for wd in part))
        lines.append(Line(text, box, round(conf, 1)))
    return lines


def ocr_words(image: Image.Image, lang: str, psm: int = 3) -> list[list[Word]]:
    """Tesseract's text lines, top to bottom, each a list of words in reading order with boxes and confidences."""
    buf = io.BytesIO()
    image.save(buf, "PNG")
    # TSV via -c variables: the "tsv" config file is not found when TESSDATA_PREFIX points at
    # a models-only directory (tessdata_best)
    proc = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", lang, "--psm", str(psm),
         "-c", "tessedit_create_tsv=1", "-c", "tessedit_create_txt=0"],
        input=buf.getvalue(), capture_output=True, check=True,
    )
    rows = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8")), delimiter="\t", quoting=csv.QUOTE_NONE)

    words: dict[tuple, list[Word]] = defaultdict(list)
    order: list[tuple] = []
    for r in rows:
        key = (r["block_num"], r["par_num"], r["line_num"])
        left, top, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
        if r["level"] == "4":
            order.append(key)
        elif r["level"] == "5" and (t := (r["text"] or "").strip()):
            words[key].append(Word(t, left, left + w, top, top + h, float(r["conf"])))
    return [words[k] for k in order if words.get(k)]


@dataclass(frozen=True)
class Word:
    text: str
    x0: int
    x1: int
    y0: int
    y1: int
    conf: float


MIN_GUTTER_LINES = 3  # a column gap must line up on at least this many lines...
MIN_GUTTER_SHARE = 0.2  # ...and on this share of the page's lines


def _wide_gaps(line: list[Word]) -> list[tuple[int, int, int]]:
    """(gap x0, gap x1, split index in reading order) for gaps much wider than the line's usual
    word spacing. Words are in reading order (right to left), so a gap lies between word i-1 (right)
    and word i (left)."""
    gaps = [(b.x1, a.x0, i) for i, (a, b) in enumerate(zip(line, line[1:]), start=1) if a.x0 > b.x1]
    if len(gaps) < 2:
        return gaps if gaps and gaps[0][1] - gaps[0][0] > 2 * (line[0].y1 - line[0].y0) else []
    widths = sorted(x1 - x0 for x0, x1, _ in gaps)
    typical = widths[len(widths) // 2]
    return [g for g in gaps if g[1] - g[0] > max(2.5 * typical, 20)]


def split_columns(lines: list[list[Word]]) -> list[list[Word]]:
    """Split lines at column gaps, e.g. Tesseract's single-column mode (psm 4) reads the two
    half-lines of two-column verse as one line. A wide gap counts as a column gap only where wide
    gaps line up across several lines: wide spaces in prose fall at random places."""
    cands = [(n, g) for n, line in enumerate(lines) for g in _wide_gaps(line)]
    need = max(MIN_GUTTER_LINES, MIN_GUTTER_SHARE * len(lines))
    cuts: dict[int, list[int]] = defaultdict(list)
    for n, (x0, x1, i) in cands:
        aligned = {m for m, (y0, y1, _) in cands if min(x1, y1) > max(x0, y0)}
        if len(aligned) >= need:
            cuts[n].append(i)
    out = []
    for n, line in enumerate(lines):
        start = 0
        for i in sorted(cuts.get(n, [])):
            out.append(line[start:i])
            start = i
        out.append(line[start:])
    return out
