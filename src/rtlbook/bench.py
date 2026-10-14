"""The scorecard (ROADMAP.md "Reader slot and scorecard"): fixed public-domain cases, one number per weak spot, saved
per engine version so that a change shows what it gained or lost.

- lines: a set's checked test lines (docs/TRAINING-DATA.md), each line image read on its own by a reader (readers.py);
- pages: whole pages through `convert`'s own OCR (line finding, reading, reading order) against checked text;
- exported: an exported PDF through everything after OCR (paragraphs) against its reference text;
- speed: seconds a line and a page, peak memory.

Letters wrong ignore spaces and half-spaces (evaluate.compare); spacing is counted on its own (spacing()). Pages and
the exported PDF go through `convert`'s Tesseract whatever the reader, until the slot reaches `convert`.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import resource
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from rtlbook import __version__, evaluate, pdf, pipeline
from rtlbook.layout import reading_order
from rtlbook.readers import Reader

ZWNJ = "\u200c"
PAGE_FILE = re.compile(r"p(\d+)\.txt")


def _gapped(text: str) -> tuple[str, list[str]]:
    """The text's letters (evaluate's normalization) and what follows each: "" (joined), "half" or "space"."""
    letters, gaps = "", []
    for word in text.split():
        first = True
        for part in word.split(ZWNJ):
            if not (ls := "".join(evaluate.words(part))):
                continue
            if gaps:
                gaps[-1] = "space" if first else "half"
            letters += ls
            gaps += [""] * len(ls)
            first = False
    return letters, gaps


def spacing(reference: str, text: str) -> tuple[int, int]:
    """(spacing errors, gaps between words in the reference): where the letters line up, each place where one text
    has a space, a half-space or nothing and the other something else counts once."""
    rl, rg = _gapped(reference)
    hl, hg = _gapped(text)
    errors = sum(rg[a + k] != hg[b + k]
                 for a, b, size in difflib.SequenceMatcher(None, rl, hl, autojunk=False).get_matching_blocks()
                 for k in range(size - 1))
    return errors, sum(bool(g) for g in rg[:-1])


def _decisions(set_dir: Path) -> tuple[list[dict], dict]:
    index = json.loads((set_dir / "lines.json").read_text(encoding="utf-8"))
    review = set_dir / "review.json"
    return index["lines"], json.loads(review.read_text(encoding="utf-8")) if review.exists() else {}


def _checked(set_dir: Path, line_id: str) -> str | None:
    gt = set_dir / f"{line_id}.gt.txt"
    return gt.read_text(encoding="utf-8").strip() if gt.exists() else None


def score_lines(set_dir: Path, reader: Reader) -> dict:
    """The reader on each checked test line of the set, alone."""
    lines, _ = _decisions(set_dir)
    test = [(ln["id"], ref) for ln in lines if ln["split"] == "test" and (ref := _checked(set_dir, ln["id"])) is not None]
    chars = errors = exact = sp_errors = sp_gaps = 0
    seconds = 0.0
    for line_id, ref in test:
        image = Image.open(set_dir / f"{line_id}.png")
        start = time.perf_counter()
        text, _ = reader.read(image)
        seconds += time.perf_counter() - start
        r = evaluate.compare(ref, text, trim=False)
        chars += r.ref_chars
        errors += r.char_errors
        exact += r.char_errors == 0
        e, g = spacing(ref, text)
        sp_errors += e
        sp_gaps += g
    data = "\n".join(f"{i}\t{ref}" for i, ref in sorted(test))
    return {"set": set_dir.name, "data": hashlib.sha256(data.encode()).hexdigest()[:12], "lines": len(test),
            "letters_wrong": round(errors / max(1, chars), 4), "exact": exact,
            "spacing_wrong": round(sp_errors / max(1, sp_gaps), 4),
            "seconds_a_line": round(seconds / max(1, len(test)), 3)}


def page_references(set_dir: Path | None, ref_dir: Path | None) -> dict[int, str]:
    """Checked text of whole pages: `p<N>.txt` files in ref_dir, and the set's test pages whose every line is decided
    (done, or skip: not a line of text), which take precedence."""
    refs = {}
    if ref_dir:
        for f in ref_dir.glob("p*.txt"):
            if m := PAGE_FILE.fullmatch(f.name):
                refs[int(m.group(1))] = f.read_text(encoding="utf-8")
    if set_dir:
        lines, review = _decisions(set_dir)
        by_page: dict[int, list[dict]] = {}
        for ln in lines:
            if ln["split"] == "test":
                by_page.setdefault(ln["page"], []).append(ln)
        for page, lns in by_page.items():
            status = [review.get(ln["id"], {}).get("status") for ln in lns]
            if all(s in ("done", "skip") for s in status) and "done" in status:
                refs[page] = "\n".join(t for ln in sorted(lns, key=lambda ln: ln["id"])
                                       if (t := _checked(set_dir, ln["id"])) is not None)
    return refs


def _ocr(pdf_path: Path, numbers: list[int], jobs: int) -> list:
    with tempfile.TemporaryDirectory() as cache:
        return pipeline.extract_pages(pdf_path, numbers, Path(cache), pipeline.OcrSettings(), jobs)


def score_pages(pdf_path: Path, refs: dict[int, str], jobs: int) -> dict:
    pages = _ocr(pdf_path, sorted(refs), jobs)
    total = {"ref_chars": 0, "char_errors": 0, "line_ref_chars": 0, "line_char_errors": 0, "missing_lines": 0,
             "extra_ocr_lines": 0}
    ref_lines = 0
    for page in pages:
        r = evaluate.compare(refs[page.number], "\n".join(ln.text for ln in reading_order(page.lines)), trim=False)
        for k in total:
            total[k] += getattr(r, k)
        ref_lines += sum(1 for t in refs[page.number].splitlines() if evaluate.words(t))
    return {"pages": sorted(refs), "lines": ref_lines,
            "letters_wrong": round(total["char_errors"] / max(1, total["ref_chars"]), 4),
            "letters_wrong_by_line": round(total["line_char_errors"] / max(1, total["line_ref_chars"]), 4),
            "lines_missing": total["missing_lines"], "lines_extra": total["extra_ocr_lines"],
            "seconds_a_page": round(sum(p.seconds for p in pages) / max(1, len(pages)), 2)}


def score_exported(pdf_path: Path, reference: Path, jobs: int) -> dict:
    from rtlbook.text import build_paragraphs

    pages = _ocr(pdf_path, list(range(1, len(pdf.open_book(pdf_path)) + 1)), jobs)
    for page in pages:
        page.lines = reading_order(page.lines)
    text = "\n".join(p.text for p in build_paragraphs(pages))
    r = evaluate.compare(reference.read_text(encoding="utf-8"), text)
    return {"pdf": pdf_path.name, "pages": len(pages), "letters_wrong": round(r.cer, 4),
            "seconds_a_page": round(sum(p.seconds for p in pages) / max(1, len(pages)), 2)}


def peak_memory_mb() -> int:
    """The largest resident size of this process or any page worker it waited for (Linux reports kB)."""
    kb = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return round(kb / 1024)


def record(reader: Reader, **parts) -> dict:
    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "engine": __version__,
            "reader": reader.name, **{k: v for k, v in parts.items() if v is not None}}
