"""A book's pages from a checked set of lines (docs/TRAINING-DATA.md) instead of OCR: `convert --lines SET`. Each line
keeps its place on the page (its box) and takes the set's text: a checked line's `<id>.gt.txt`, else the text two
independent readings agreed on (`<id>.agreed.txt`, in a frozen version), else an unsure line's best guess; a line
marked skip (not printed text) is left out, and a line nobody decided keeps what OCR read. A frozen version's manifest
(`manifest.json` beside lines.json, docs/TRAINING-DATA.md "Frozen versions") has the last word on each line's status:
it also holds what was decided at freeze, such as a line skipped by agreement. Everything after reading
(reading order, page numbers and running titles, paragraphs, chapters) then runs as for OCR (DESIGN.md §4.11).
"""

from __future__ import annotations

import fnmatch
import json
from collections import Counter
from pathlib import Path

from rtlbook import pdf
from rtlbook.model import Line, Page

CHECKED_CONF = 100.0  # a line's confidence: the text is a person's, or two readings that agree


def line_text(folder: Path, line: dict, decision: dict | None) -> tuple[str | None, str]:
    """The text a line takes (None: leave it out) and where it came from: checked, agreed, unsure, skip or ocr."""
    status = (decision or {}).get("status")
    gt, agreed = folder / f"{line['id']}.gt.txt", folder / f"{line['id']}.agreed.txt"
    if status == "skip":
        return None, "skip"
    if status == "done":
        return (gt.read_text(encoding="utf-8") if gt.exists() else decision.get("text", "")).strip(), "checked"
    if agreed.exists():
        return agreed.read_text(encoding="utf-8").strip(), "agreed"
    if status == "unsure":
        return (decision.get("text") or line.get("ocr", "")).strip(), "unsure"
    return line.get("ocr", "").strip(), "ocr"


def pages(folder: Path, pdf_path: Path, numbers: list[int], dpi: int = 300,
          edition: dict | None = None) -> tuple[list[Page], Counter]:
    """The PDF's pages `numbers` with the set's lines, and how many lines took each source. The set's boxes are in
    pixels of the page rendered at `dpi` (rtlbook lines' default, 300). An edition (convert --edition) names the lines
    that start chapters (`chapters`: [{"line": id}]) and the lines to leave out (`drop`: ids, or patterns like
    "p152-*"), by the set's line ids."""
    edition = edition or {}
    starts = {c["line"] for c in edition.get("chapters", [])}
    drop = edition.get("drop", [])
    index = json.loads((folder / "lines.json").read_text(encoding="utf-8"))
    review_file, manifest_file = folder / "review.json", folder / "manifest.json"
    review = json.loads(review_file.read_text(encoding="utf-8")) if review_file.exists() else {}
    if manifest_file.exists():  # a status decided at freeze (agreed, or skip by agreement) is in the manifest only
        for e in json.loads(manifest_file.read_text(encoding="utf-8")).get("lines", []):
            review[e["id"]] = {**review.get(e["id"], {}), "status": e["status"]}
    doc = pdf.open_book(pdf_path)
    by_page: dict[int, list[Line]] = {n: [] for n in numbers}
    sources: Counter = Counter()
    for ln in sorted(index["lines"], key=lambda ln: ln["id"]):
        if ln["page"] not in by_page:
            continue
        if any(fnmatch.fnmatchcase(ln["id"], d) for d in drop):
            sources["dropped"] += 1
            continue
        text, source = line_text(folder, ln, review.get(ln["id"]))
        sources[source] += 1
        if text:
            by_page[ln["page"]].append(Line(text, tuple(ln["box"]), CHECKED_CONF, ln["id"] in starts))
    out = []
    for n in numbers:
        w, h = doc[n - 1].get_size()
        out.append(Page(n, "ocr", round(w * dpi / 72), round(h * dpi / 72), by_page[n],
                        {"route": "set", "set": folder.name, "dpi": dpi}))
    return out, sources
