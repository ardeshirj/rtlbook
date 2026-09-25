"""Tesseract OCR engine (CLI via subprocess, TSV output for line boxes and confidences)."""

from __future__ import annotations

import csv
import io
import subprocess
from collections import defaultdict

from PIL import Image

from rtlbook.model import Line


def tesseract_version() -> str:
    out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()[0]


def ocr_lines(image: Image.Image, lang: str, psm: int = 3) -> list[Line]:
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

    boxes: dict[tuple, tuple[int, int, int, int]] = {}
    words: dict[tuple, list[tuple[str, float]]] = defaultdict(list)
    order: list[tuple] = []
    for r in rows:
        key = (r["block_num"], r["par_num"], r["line_num"])
        if r["level"] == "4":
            left, top, w, h = (int(r[k]) for k in ("left", "top", "width", "height"))
            boxes[key] = (left, top, left + w, top + h)
            order.append(key)
        elif r["level"] == "5" and (t := (r["text"] or "").strip()):
            words[key].append((t, float(r["conf"])))

    lines = []
    for key in order:
        if ws := words.get(key):
            text = " ".join(t for t, _ in ws)
            conf = sum(c for _, c in ws) / len(ws)
            lines.append(Line(text, boxes[key], round(conf, 1)))
    return lines
