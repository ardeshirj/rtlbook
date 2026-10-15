"""The scorecard (ROADMAP.md "Reader slot and scorecard"): fixed public-domain cases, one number per weak spot, saved
per engine version so that a change shows what it gained or lost.

- lines: a set's checked test lines (docs/TRAINING-DATA.md), each line image read on its own by a reader (readers.py);
- pages: whole pages through `convert`'s own OCR (line finding, reading, reading order, joined words split in a scan)
  against checked text; the book's words for the splitter come from the scored pages only, not the whole book;
- exported: an exported PDF through everything after OCR (paragraphs) against its reference text;
- speed: seconds a line and a page, peak memory.

Letters wrong ignore spaces and half-spaces (evaluate.compare); spacing is counted on its own (spacing()). Pages and
the exported PDF go through `convert`'s Tesseract whatever the reader, until the slot reaches `convert`.
"""

from __future__ import annotations

import difflib
import hashlib
import html
import json
import re
import resource
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from rtlbook import __version__, evaluate, joined, pdf, pipeline
from rtlbook.doctype import document_type, page_kind
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


def _split_joined(pdf_path: Path, pages: list) -> int | None:
    """As `convert`: joined words split in a scan only (None otherwise, or without the word lists)."""
    doc = pdf.open_book(pdf_path)
    if document_type([page_kind(pdf.page_info(doc, p.number - 1)) for p in pages]).kind != "scan":
        return None
    return joined.split_pages(pages)


def score_pages(pdf_path: Path, refs: dict[int, str], jobs: int) -> dict:
    pages = _ocr(pdf_path, sorted(refs), jobs)
    for page in pages:
        page.lines = reading_order(page.lines)
    split = _split_joined(pdf_path, pages)
    total = {"ref_chars": 0, "char_errors": 0, "line_ref_chars": 0, "line_char_errors": 0, "missing_lines": 0,
             "extra_ocr_lines": 0}
    ref_lines = sp_errors = sp_gaps = 0
    for page in pages:
        text = "\n".join(ln.text for ln in page.lines)
        r = evaluate.compare(refs[page.number], text, trim=False)
        for k in total:
            total[k] += getattr(r, k)
        e, g = spacing(refs[page.number], text)
        sp_errors, sp_gaps = sp_errors + e, sp_gaps + g
        ref_lines += sum(1 for t in refs[page.number].splitlines() if evaluate.words(t))
    return {"pages": sorted(refs), "lines": ref_lines,
            "letters_wrong": round(total["char_errors"] / max(1, total["ref_chars"]), 4),
            "letters_wrong_by_line": round(total["line_char_errors"] / max(1, total["line_ref_chars"]), 4),
            "lines_missing": total["missing_lines"], "lines_extra": total["extra_ocr_lines"],
            "spacing_wrong": round(sp_errors / max(1, sp_gaps), 4), "joined_split": split,
            "seconds_a_page": round(sum(p.seconds for p in pages) / max(1, len(pages)), 2)}


def score_exported(pdf_path: Path, reference: Path, jobs: int) -> dict:
    from rtlbook.text import build_paragraphs

    pages = _ocr(pdf_path, list(range(1, len(pdf.open_book(pdf_path)) + 1)), jobs)
    for page in pages:
        page.lines = reading_order(page.lines)
    split = _split_joined(pdf_path, pages)
    text = "\n".join(p.text for p in build_paragraphs(pages))
    ref = reference.read_text(encoding="utf-8")
    r = evaluate.compare(ref, text)
    e, g = spacing(ref, text)
    return {"pdf": pdf_path.name, "pages": len(pages), "letters_wrong": round(r.cer, 4),
            "spacing_wrong": round(e / max(1, g), 4), "joined_split": split,
            "seconds_a_page": round(sum(p.seconds for p in pages) / max(1, len(pages)), 2)}


def peak_memory_mb() -> int:
    """The largest resident size of this process or any page worker it waited for (Linux reports kB)."""
    kb = max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    return round(kb / 1024)


def record(reader: Reader, **parts) -> dict:
    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "engine": __version__,
            "reader": reader.name, **{k: v for k, v in parts.items() if v is not None}}


BEST, WORST, REST = "#2f6fb0", "#e07b24", "#9a9a9a"  # bar colours


def _chart(title: str, labels: list[str], values: list[float], show) -> str:
    """A horizontal bar chart as SVG, fewer is better: the lowest bar blue and the highest orange when one reader
    alone holds it, each value at its bar's end. Drawn here, not in Mermaid: its bars start a little before the
    axis's zero, and its values on bars all shrink to fit the shortest bar."""
    width, left, row, top = 640, 230, 28, 32
    span = (width - left - 80) / (max(values + [0]) or 1)
    best = min(values) if values.count(min(values)) == 1 and len(set(values)) > 1 else None
    worst = max(values) if values.count(max(values)) == 1 and len(set(values)) > 1 else None
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{top + row * len(values) + 4}" '
           'font-family="-apple-system, Segoe UI, Helvetica, Arial, sans-serif" font-size="13">',
           "<style>text { fill: #1f2328 } .label { fill: #59636e } @media (prefers-color-scheme: dark) "
           "{ text { fill: #e6edf3 } .label { fill: #9198a1 } }</style>",
           f'<text x="0" y="18" font-size="14" font-weight="600">{html.escape(title)}</text>']
    for k, (label, v) in enumerate(zip(labels, values)):
        y, w = top + row * k, round(v * span, 1)
        colour = BEST if v == best else WORST if v == worst else REST
        out += [f'<text class="label" x="{left - 10}" y="{y + row / 2}" dy="0.35em" text-anchor="end">'
                f"{html.escape(label)}</text>",
                f'<rect x="{left}" y="{y + 5}" width="{w}" height="{row - 10}" rx="2" fill="{colour}"/>',
                f'<text x="{left + w + 6}" y="{y + row / 2}" dy="0.35em">{html.escape(show(v))}</text>']
    out.append(f'<line x1="{left}" x2="{left}" y1="{top}" y2="{top + row * len(values)}" stroke="#8c959f"/>')
    return "\n".join(out + ["</svg>"]) + "\n"


def report(entries: list[dict]) -> dict[str, str]:
    """bench/README.md (the readers side by side on the newest checked lines, convert's own numbers, and every run)
    and its charts in charts/, by path."""
    out = ["# Scorecard", "",
           "Written by `make bench` from [`results.jsonl`](results.jsonl) after every run: don't edit by hand. What each "
           "number means: `src/rtlbook/bench.py` and docs/ROADMAP.md (\"Reader slot and scorecard\").", ""]
    charts = {}
    with_lines = [e for e in entries if e.get("lines")]
    if with_lines:
        data = with_lines[-1]["lines"]["data"]
        latest = {}
        for e in with_lines:
            if e["lines"]["data"] == data:
                latest[e["reader"]] = e
        rows = sorted(latest.values(), key=lambda e: e["lines"]["letters_wrong"])
        ln = rows[0]["lines"]
        out += ["## Line readers on the same checked lines", "",
                f"Each reader reads the {ln['lines']} checked test lines of `{ln['set']}` (data `{data}`) one line "
                "image at a time, cut by rtlbook. Letters wrong ignore spaces and half-spaces; word gaps wrong count "
                "only those. Fewer is better. Image size: rtlbook's own image for Tesseract `fas`, the readers image "
                "(all the other readers together) for the rest.", "",
                "| Reader | Letters wrong | Lines all right | Word gaps wrong | Seconds a line | Memory, MB | Image, MB "
                "| Run |", "|---|---|---|---|---|---|---|---|"]
        for e in rows:
            ln = e["lines"]
            out.append(f"| {e['reader']} | {ln['letters_wrong']:.2%} | {ln['exact']} of {ln['lines']} | "
                       f"{ln['spacing_wrong']:.1%} | {ln['seconds_a_line']} | {e.get('memory_mb', '')} | "
                       f"{e.get('image_mb', '')} | {e['date'][:10]}, `{e.get('commit', '')}` |")
        names = [e["reader"] for e in rows]
        charts = {
            "charts/letters-wrong.svg": _chart("Letters wrong", names, [100 * e["lines"]["letters_wrong"] for e in rows],
                                               lambda v: f"{v:.2f}%"),
            "charts/word-gaps-wrong.svg": _chart("Word gaps wrong", names,
                                                 [100 * e["lines"]["spacing_wrong"] for e in rows], lambda v: f"{v:.1f}%"),
            "charts/time.svg": _chart("Milliseconds a line", names, [1000 * e["lines"]["seconds_a_line"] for e in rows],
                                      lambda v: f"{v:.0f} ms"),
            "charts/memory.svg": _chart("Memory", names, [e.get("memory_mb", 0) for e in rows], lambda v: f"{v} MB"),
        }
        out += ["", "Fewer is better in all four: the best blue, the worst orange. The first two: how well each reads; "
                "the last two: what it costs to run, one CPU thread.", "",
                *(f"![{path.split('/')[-1].removesuffix('.svg').replace('-', ' ')}]({path})\n" for path in charts)]
    with_pages = [e for e in entries if e.get("pages") or e.get("exported")]
    if with_pages:
        e = with_pages[-1]
        out += ["## Whole pages and an exported PDF, through `convert`", "",
                "`convert`'s own OCR (Tesseract finds and reads the lines in one call, whatever the reader above).", "",
                "| Case | Letters wrong | Word gaps wrong | More | Seconds a page |", "|---|---|---|---|---|"]
        gaps = lambda d: f"{d['spacing_wrong']:.1%}" if "spacing_wrong" in d else ""
        split = lambda d: f"words split: {d['joined_split']}" if d.get("joined_split") is not None else ""
        if pg := e.get("pages"):
            out.append(f"| Pages {', '.join(map(str, pg['pages']))} ({pg['lines']} lines) | {pg['letters_wrong']:.2%} "
                       f"| {gaps(pg)} | lines lost or merged: {pg['lines_missing']}, extra: {pg['lines_extra']}"
                       f"{', ' + split(pg) if split(pg) else ''} | {pg['seconds_a_page']} |")
        if ex := e.get("exported"):
            out.append(f"| Exported PDF, `{ex['pdf']}` ({ex['pages']} pages) | {ex['letters_wrong']:.2%} | {gaps(ex)} | "
                       f"{split(ex)} | {ex['seconds_a_page']} |")
        out += ["", f"From the run of {e['date'][:10]} (`{e.get('commit', '')}`, rtlbook {e['engine']}).", ""]
    out += ["## Every run", "", "Newest first. Lines and pages compare only between runs on the same data.", "",
            "| Date | Commit | rtlbook | Reader | Lines (data) | Letters wrong | Word gaps wrong | Pages, letters wrong "
            "| Exported, letters wrong |", "|---|---|---|---|---|---|---|---|---|"]
    for e in reversed(entries):
        x, pg, ex = e.get("lines") or {}, e.get("pages") or {}, e.get("exported") or {}
        pct = lambda d, k, f=".2%": format(d[k], f) if k in d else ""
        out.append(f"| {e['date'][:16].replace('T', ' ')} | `{e.get('commit', '')}` | {e['engine']} | {e['reader']} | "
                   f"{x.get('lines', '')} (`{x.get('data', '')}`) | {pct(x, 'letters_wrong')} | "
                   f"{pct(x, 'spacing_wrong', '.1%')} | {pct(pg, 'letters_wrong')} | {pct(ex, 'letters_wrong')} |")
    return {"README.md": "\n".join(out) + "\n", **charts}
