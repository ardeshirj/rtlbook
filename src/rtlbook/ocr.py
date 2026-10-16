"""Tesseract OCR engine: the CLI via subprocess (TSV output for line boxes and confidences) for whole pages, and its
C API through ctypes for layout analysis alone and single lines (one model load per process, no program start)."""

from __future__ import annotations

import atexit
import csv
import ctypes
import ctypes.util
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


# ---- The C API (libtesseract, installed with the tesseract-ocr package) ----
_TEXTLINE, _WORD = 2, 3  # TessPageIteratorLevel
BIDI_MARKS = "\u200e\u200f"
_lib = None
_apis: dict[tuple[str, int], int] = {}


def _capi():
    global _lib
    if _lib is None:
        name = ctypes.util.find_library("tesseract")
        if not name:
            raise RuntimeError("libtesseract not found (it comes with the tesseract-ocr package)")
        lib = ctypes.CDLL(name)
        vp, ip = ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
        for fn, args, res in [
            ("TessBaseAPICreate", [], vp), ("TessBaseAPIInit3", [vp, ctypes.c_char_p, ctypes.c_char_p], ctypes.c_int),
            ("TessBaseAPISetPageSegMode", [vp, ctypes.c_int], None),
            ("TessBaseAPISetImage", [vp, ctypes.c_char_p] + [ctypes.c_int] * 4, None),
            ("TessBaseAPIAnalyseLayout", [vp], vp), ("TessBaseAPIGetUTF8Text", [vp], vp),
            ("TessBaseAPIMeanTextConf", [vp], ctypes.c_int), ("TessDeleteText", [vp], None),
            ("TessPageIteratorBoundingBox", [vp, ctypes.c_int, ip, ip, ip, ip], ctypes.c_int),
            ("TessPageIteratorNext", [vp, ctypes.c_int], ctypes.c_int),
            ("TessPageIteratorIsAtBeginningOf", [vp, ctypes.c_int], ctypes.c_int),
            ("TessPageIteratorDelete", [vp], None), ("TessBaseAPIDelete", [vp], None),
        ]:
            f = getattr(lib, fn)
            f.argtypes, f.restype = args, res
        _lib = lib
        atexit.register(lambda: [_lib.TessBaseAPIDelete(api) for api in _apis.values()])
    return _lib


def _api(lang: str, psm: int) -> int:
    lib = _capi()
    if (lang, psm) not in _apis:
        api = lib.TessBaseAPICreate()
        if lib.TessBaseAPIInit3(api, None, lang.encode()) != 0:  # models from TESSDATA_PREFIX
            raise RuntimeError(f"Tesseract couldn't load the language {lang!r}")
        lib.TessBaseAPISetPageSegMode(api, psm)
        _apis[(lang, psm)] = api
    return _apis[(lang, psm)]


def _set_image(api: int, image: Image.Image) -> None:
    img = image.convert("L")
    _capi().TessBaseAPISetImage(api, img.tobytes(), img.width, img.height, 1, img.width)


def layout_words(image: Image.Image, lang: str, psm: int = 4) -> list[list[Word]]:
    """Tesseract's text lines found by layout analysis alone, without reading them (a sixth of the time of
    ocr_words): each a list of word boxes, right to left, with no text. The boxes leave out some of the marks above
    and below the letters that ocr_words' boxes include."""
    lib, api = _capi(), _api(lang, psm)
    _set_image(api, image)
    it = lib.TessBaseAPIAnalyseLayout(api)
    lines: list[list[Word]] = []
    if not it:
        return lines
    box = [ctypes.c_int() for _ in range(4)]

    def bounds(level: int) -> tuple[int, int, int, int] | None:
        ok = lib.TessPageIteratorBoundingBox(it, level, *map(ctypes.byref, box))
        return tuple(b.value for b in box) if ok else None

    line_boxes: list[tuple[int, int, int, int]] = []
    while True:
        if not lines or lib.TessPageIteratorIsAtBeginningOf(it, _TEXTLINE):
            lines.append([])
            line_boxes.append(bounds(_TEXTLINE) or (0, 0, 0, 0))
        lx0, ly0, lx1, ly1 = line_boxes[-1]
        # some words come back with the whole page as their box: only boxes inside their line count
        if (w := bounds(_WORD)) and lx0 <= w[0] and ly0 <= w[1] and w[2] <= lx1 and w[3] <= ly1:
            lines[-1].append(Word("", w[0], w[2], w[1], w[3], 0.0))
        if not lib.TessPageIteratorNext(it, _WORD):
            break
    lib.TessPageIteratorDelete(it)
    out = []
    for words, (x0, y0, x1, y1) in zip(lines, line_boxes):
        if not words and x1 > x0:  # no usable word box: the line as one
            words = [Word("", x0, x1, y0, y1, 0.0)]
        if words:
            out.append(sorted(words, key=lambda w: -w.x1))  # the layout doesn't know the script's direction
    return out


def read_line(image: Image.Image, lang: str) -> tuple[str, float | None]:
    """One line image read as a raw line (`--psm 13`): its text and Tesseract's mean confidence, as the CLI gives
    them (left-to-right marks dropped, as its word list does)."""
    lib, api = _capi(), _api(lang, 13)
    _set_image(api, image)
    p = lib.TessBaseAPIGetUTF8Text(api)
    text = ctypes.string_at(p).decode("utf-8") if p else ""
    if p:
        lib.TessDeleteText(p)
    words = [w for w in text.split() if w.strip(BIDI_MARKS)]
    return " ".join(words), (float(lib.TessBaseAPIMeanTextConf(api)) if words else None)
