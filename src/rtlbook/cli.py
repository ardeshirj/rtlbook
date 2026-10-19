from __future__ import annotations

import collections
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from rtlbook import __version__, pdf, script
from rtlbook.doctype import PageKind, confidence_message, document_type, page_kind

DEFAULT_OUTPUT_DIR = Path("output")  # relative to the directory ./rtlbook is run from
INPUT_HELP = "Input PDF"

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Convert RTL-language PDF books to EPUB.")
console = Console()


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    pages: set[int] = set()
    for part in spec.split(","):
        a, _, b = part.partition("-")
        pages.update(range(int(a), min(int(b or a), total) + 1))
    return sorted(p for p in pages if 1 <= p <= total)


def page_kinds(pdf_path: Path, numbers: list[int]) -> list[PageKind]:
    doc = pdf.open_book(pdf_path)
    return [page_kind(pdf.page_info(doc, n - 1)) for n in numbers]


def doctype_table(kinds: list[PageKind]) -> Table:
    t = Table(title="Document type")
    for col in ("pages are", "pages", "example pages", "resolution"):
        t.add_column(col)
    groups = collections.defaultdict(list)
    for k in kinds:
        groups[k.kind].append(k)
    for kind, ks in sorted(groups.items()):
        dpis = sorted(k.dpi for k in ks if k.dpi)
        res = f"~{dpis[len(dpis) // 2]} dpi" if dpis else "-"
        t.add_row("exported (text drawn by the PDF)" if kind == "exported" else "scanned (page images)",
                  str(len(ks)), ", ".join(str(k.number) for k in ks[:8]), res)
    return t


def print_doctype(kinds: list[PageKind]) -> None:
    dt = document_type(kinds)
    console.print(doctype_table(kinds))
    console.print(f"[green]{dt.message()}[/]" if dt.supported else f"[yellow]{dt.message()}[/]")


def check_script_of(pdf_path: Path, numbers: list[int], lang: str) -> script.ScriptCheck:
    doc = pdf.open_book(pdf_path)
    return script.check(lambda n: pdf.render(doc, n - 1, 300), numbers, lang, pdf.digest(pdf_path))


def print_script(check: script.ScriptCheck) -> None:
    console.print(f"[yellow]{check.message()}[/]" if check.mismatch else check.message())


@app.command()
def init() -> None:
    """Create the input/ and output/ folders here, and say what to do next."""
    for name in ("input", DEFAULT_OUTPUT_DIR.name):
        folder = Path(name)
        state = "exists" if folder.is_dir() else "created"
        folder.mkdir(exist_ok=True)
        console.print(f"{name}/ {state}")
    console.print("Next: put a PDF in input/, then: [bold]rtlbook convert input/book.pdf[/]")


@app.command()
def version() -> None:
    """Print the version."""
    print(__version__)


@app.command()
def inspect(
    pdf_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help=INPUT_HELP)],
    pages: Annotated[Optional[str], typer.Option(help="Page selection, e.g. 1-20,35")] = None,
    json_out: Annotated[Optional[Path], typer.Option("--json", help="Write per-page results as JSON")] = None,
    lang: Annotated[str, typer.Option(help="OCR language(s) the book should be in; its script is checked on a few pages")] = "fas",
) -> None:
    """Say what kind of document this is (exported PDF or scan), whether it's supported yet, and its script."""
    start = time.perf_counter()
    numbers = parse_pages(pages, len(pdf.open_book(pdf_path)))
    kinds = page_kinds(pdf_path, numbers)
    print_doctype(kinds)
    print_script(check_script_of(pdf_path, numbers, lang))
    console.print(f"[dim]{len(kinds)} pages inspected in {time.perf_counter() - start:.1f}s[/]")
    if json_out:
        json_out.write_text(json.dumps([k.__dict__ for k in kinds], indent=1), encoding="utf-8")


@app.command()
def convert(
    pdf_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help=INPUT_HELP)],
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output .epub (default: output/<pdf name>.epub)")] = None,
    title: Annotated[Optional[str], typer.Option(help="Book title (default: from the title page, else the file name)")] = None,
    author: Annotated[Optional[str], typer.Option(help="Author (default: from the title page)")] = None,
    lang: Annotated[str, typer.Option(help="Tesseract language(s), e.g. fas or fas+ara")] = "fas",
    pages: Annotated[Optional[str], typer.Option(help="Page selection, e.g. 1-20")] = None,
    dpi: Annotated[int, typer.Option(help="Render resolution for OCR")] = 300,
    psm: Annotated[int, typer.Option(help="Tesseract page segmentation mode (4: one column of lines of any size; column gaps are split afterwards)")] = 4,
    binarize: Annotated[bool, typer.Option(help="Otsu-binarize pages before OCR")] = True,
    crop: Annotated[float, typer.Option(help="Fraction to cut off each page edge (e.g. 0.075 for framed pages)")] = 0.0,
    jobs: Annotated[int, typer.Option("-j", "--jobs", help="Parallel pages")] = os.cpu_count() or 4,
    cover: Annotated[Optional[Path], typer.Option(help="Cover image (default: largest image on page 1)")] = None,
    no_cover: Annotated[bool, typer.Option("--no-cover", help="No cover page or cover image")] = False,
    work: Annotated[Optional[Path], typer.Option(help="Work/cache dir (default: <output>.rtlbook)")] = None,
    drop_lines: Annotated[Optional[str], typer.Option(help="Regex: drop matching lines (watermarks, site banners)")] = None,
    digits: Annotated[str, typer.Option(help="Digits in the text: auto (Persian ۰-۹ for fas), fa, or keep")] = "auto",
    embed_font: Annotated[bool, typer.Option(help="Embed the Parastoo font (off: use the reader's own font)")] = True,
    min_line_conf: Annotated[float, typer.Option(help="Drop OCR lines below this confidence (0 keeps all)")] = 0.0,
    chunk_pages: Annotated[int, typer.Option(help="Pages per EPUB section when no chapters are found")] = 20,
    progress: Annotated[str, typer.Option(help="Progress output: bar, or json (one JSON line per event on stderr, for other programs)")] = "bar",
    check_script: Annotated[bool, typer.Option(help="Before OCR, check that a few pages are in the OCR language's script")] = True,
    reader: Annotated[str, typer.Option(help="How lines are read: auto (a scan's lines cut and read one by one by ParisaOCR, an exported PDF's whole pages by Tesseract), page (Tesseract reads whole pages in one call), or a line reader: parisaocr, tesseract")] = "auto",
    scan_reader: Annotated[str, typer.Option(help="With --reader auto, the line reader for a scan's lines: parisaocr (fewer letters wrong) or tesseract (five times faster)")] = "parisaocr",
    split_joined: Annotated[bool, typer.Option(help="Split words run together after a letter that never joins the next (Farsi scans; the image's word lists)")] = True,
    lines: Annotated[Optional[Path], typer.Option("--lines", help="Build from a checked set of lines (rtlbook lines' format, docs/TRAINING-DATA.md) instead of OCR: its text, each line in its place on the page")] = None,
    edition: Annotated[Optional[Path], typer.Option(help="With --lines: a JSON file naming the lines that start chapters (chapters: [{line: id}]) and lines to leave out (drop: ids or patterns), editorial changes to the text (replace: [{pattern: regex, with: text}]), and the book's title and author")] = None,
    half_spaces: Annotated[bool, typer.Option(help="Make the space before an ending (the plural -ha, -tar) or after a prefix (mi-, bi-) a half-space, as Farsi is spelled today")] = True,
) -> None:
    """Convert a PDF into an RTL EPUB 3."""
    from rtlbook import epub, fromset, frontmatter, halfspace, joined, layout, readers, text
    from rtlbook.pipeline import OcrSettings, extract_pages, reader_for, split_sections
    from rtlbook.validate import epubcheck

    timings: dict[str, float] = {}
    output = output or DEFAULT_OUTPUT_DIR / f"{pdf_path.stem}.epub"
    work = work or output.with_name(output.stem + ".rtlbook")
    work.mkdir(parents=True, exist_ok=True)

    def emit(**event) -> None:
        if progress == "json":
            print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)

    numbers = parse_pages(pages, len(pdf.open_book(pdf_path)))
    kinds = page_kinds(pdf_path, numbers)
    print_doctype(kinds)
    check_script = check_script and not lines  # a set's text has been read already
    t0 = time.perf_counter()
    scripts = check_script_of(pdf_path, numbers, lang) if check_script else script.ScriptCheck(None)
    timings["script"] = time.perf_counter() - t0
    if check_script:
        print_script(scripts)
    emit(event="start", pages=len(numbers), document=document_type(kinds).kind,
         script=scripts.found, script_expected=scripts.expected)

    read_with = reader_for(reader, document_type(kinds).kind, scan_reader)
    t0 = time.perf_counter()
    cached = 0
    finished = 0
    with Progress(TextColumn("OCR"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console,
                  disable=progress == "json") as prog:
        task = prog.add_task("pages", total=len(numbers))

        def done(page, from_cache: bool) -> None:
            nonlocal cached, finished
            cached += from_cache
            finished += 1
            prog.advance(task)
            emit(event="page", page=page.number, done=finished, total=len(numbers), cached=from_cache)

        if lines:
            ed = json.loads(edition.read_text(encoding="utf-8")) if edition else {}
            title, author = title or ed.get("title"), author or ed.get("author")
            page_results, from_set = fromset.pages(lines, pdf_path, numbers, dpi, ed)
            for p in page_results:
                done(p, False)
            console.print("Lines from the set " + lines.name + ": " +
                          ", ".join(f"{n} {k}" for k, n in from_set.most_common()) + " (no OCR)")
        else:
            page_results = extract_pages(
                pdf_path, numbers, work / "pages", OcrSettings(dpi, lang, psm, binarize, crop, read_with), max(1, jobs),
                done)
    timings["extract"] = time.perf_counter() - t0
    for p in page_results:  # side-by-side lines (two-column verse) read row by row, right to left
        p.lines = layout.reading_order(p.lines)

    # Raw per-page text, handy for reviewing OCR output
    with open(work / "pages.txt", "w", encoding="utf-8") as f:
        for p in page_results:
            conf = f" conf={p.mean_conf:.1f}" if p.mean_conf is not None else ""
            f.write(f"\n===== page {p.number} [{p.route}{conf}, {p.seconds}s] =====\n")
            f.write("\n".join(ln.text for ln in p.lines) + "\n")

    t0 = time.perf_counter()
    scan = document_type(kinds).kind == "scan"  # an exported PDF's gaps are the ones typed
    split = joined.split_pages(page_results) if split_joined and scan and not lines and lang.startswith("fas") else None
    timings["joined"] = time.perf_counter() - t0
    halves = halfspace.join_pages(page_results) if half_spaces and lang.startswith("fas") else None

    found_title, found_author = frontmatter.guess_title_author(page_results)
    title_from = "--title" if title else "title page" if found_title else "file name"
    author_from = "--author" if author else "title page" if found_author else "none"
    title = title or found_title or pdf_path.stem
    author = author or found_author or ""
    console.print(f"Title: [bold]{title}[/] [dim]({title_from})[/] · Author: [bold]{author or '-'}[/] [dim]({author_from})[/]"
                  + ("" if title_from == "--title" and author_from == "--author" else " [dim]Use --title/--author to change.[/]"))

    t0 = time.perf_counter()
    paras = text.build_paragraphs(page_results, re.compile(drop_lines) if drop_lines else None, min_line_conf)
    text.apply_digits(paras, ("fa" if lang.startswith("fas") else "keep") if digits == "auto" else digits)
    sections = split_sections(paras, chunk_pages)
    with open(work / "paragraphs.txt", "w", encoding="utf-8") as f:
        for p in paras:
            f.write(("## " if p.heading else "") + p.text + "\n\n")

    cover_img = None
    if cover:
        cover_img = (cover.read_bytes(), "image/png" if cover.suffix.lower() == ".png" else "image/jpeg")
    elif not no_cover:
        cover_img = pdf.largest_image(pdf.open_book(pdf_path), 0)

    found = {"lines_found_by": f"set {lines.name}", "read_by": f"set {lines.name}"} if lines else readers.describe(read_with, lang)
    engine = {"rtlbook": __version__, "document": document_type(kinds).kind, **found}
    digest = pdf.digest(pdf_path)
    fonts_dir = Path(os.environ.get("RTLBOOK_FONTS", "/opt/fonts"))
    meta = epub.BookMeta(
        title=title,
        author=author,
        lang="fa" if lang.startswith("fas") else lang[:2],
        identifier=f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'rtlbook:' + digest)}",
        cover=cover_img,
        fonts=tuple(sorted(fonts_dir.glob("*.ttf"))) if embed_font and fonts_dir.exists() else (),
        engine={"version" if k == "rtlbook" else k: v for k, v in engine.items()},
    )
    epub.write_epub(output, meta, sections)
    timings["build"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    ok, report = epubcheck(output)
    timings["epubcheck"] = time.perf_counter() - t0
    (work / "epubcheck.txt").write_text(report + "\n", encoding="utf-8")

    confs = [p.mean_conf for p in page_results if p.mean_conf is not None]
    low = [p.number for p in page_results if p.mean_conf is not None and p.mean_conf < 80]
    stats = {
        "pdf": str(pdf_path),
        "title": title,
        "title_from": title_from,
        "author": author,
        "author_from": author_from,
        "pages": len(page_results),
        "pages_from_cache": cached,
        "engine": engine,
        "ocr_settings": {"dpi": dpi, "lang": lang, "psm": psm, "binarize": binarize, "crop": crop, "jobs": jobs,
                         "reader": read_with},
        "ocr_seconds_per_page_single_thread": round(
            sum(p.seconds for p in page_results) / max(1, len(page_results)), 2
        ),
        "mean_confidence": round(sum(confs) / len(confs), 1) if confs else None,
        "low_confidence_pages": low,
        "joined_words_split": split,
        "half_spaces_made": halves,
        "lines_from_set": dict(from_set) if lines else None,
        "script": {"expected": scripts.expected, "found": scripts.found, "pages": scripts.seen} if check_script else None,
        "warning": confidence_message(round(sum(confs) / len(confs), 1) if confs else None),
        "paragraphs": len(paras),
        "headings": sum(p.heading for p in paras),
        "sections": len(sections),
        "epub": str(output),
        "epub_bytes": output.stat().st_size,
        "epubcheck_ok": ok,
        "timings_seconds": {k: round(v, 1) for k, v in timings.items()},
    }
    (work / "report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    emit(event="done", ok=ok, epub=str(output), report=str(work / "report.json"), title=title, author=author,
         warning=stats["warning"])
    console.print_json(data=stats)
    if warning := confidence_message(stats["mean_confidence"]):
        console.print(f"[yellow]{warning}[/]")
    console.print(("[green]epubcheck: valid[/]" if ok else "[red]epubcheck: FAILED[/]") + f" (see {work / 'epubcheck.txt'})")
    if not ok:
        raise typer.Exit(1)


@app.command("eval")
def eval_cmd(
    ocr: Annotated[Path, typer.Argument(exists=True, help="OCR text: a convert work folder (<name>.rtlbook), its pages.txt/paragraphs.txt, or any text file")],
    reference: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Correct text of the same pages (e.g. hand-corrected)")],
    pages: Annotated[Optional[str], typer.Option(help="Only these pages of pages.txt, e.g. 76-77")] = None,
    raw: Annotated[bool, typer.Option(help="For a work folder: use raw OCR (pages.txt) instead of the cleaned-up paragraphs.txt")] = False,
    keep_marks: Annotated[bool, typer.Option(help="Count vowel marks (harakat) as characters")] = False,
    trim: Annotated[Optional[bool], typer.Option("--trim/--no-trim", help="Cut the reference to the part the OCR text covers (default: when the reference is clearly longer)")] = None,
    json_out: Annotated[Optional[Path], typer.Option("--json", help="Write the results as JSON")] = None,
    diff: Annotated[Optional[Path], typer.Option(help="Write every mismatch (reference → OCR) to this file")] = None,
) -> None:
    """Measure OCR accuracy against a correct text: character and word error rates."""
    from rtlbook import evaluate

    if ocr.is_dir():
        ocr = ocr / ("pages.txt" if raw or pages else "paragraphs.txt")
    wanted = set(parse_pages(pages, 100_000)) if pages else None
    if wanted and not ocr.read_text(encoding="utf-8").lstrip().startswith("====="):
        console.print("[red]--pages needs rtlbook's pages.txt (it has page markers)[/]")
        raise typer.Exit(2)
    res = evaluate.compare(
        reference.read_text(encoding="utf-8"),
        evaluate.read_text(ocr.read_text(encoding="utf-8"), wanted),
        keep_marks, trim,
    )
    t = Table(title=f"OCR accuracy: {ocr.name} vs {reference.name}")
    t.add_column("metric")
    t.add_column("value", justify="right")
    t.add_column("meaning")
    t.add_row("CER", f"{res.cer:.1%}", f"{res.char_errors:,} of {res.ref_chars:,} letters wrong (spaces ignored)")
    t.add_row("WER", f"{res.wer:.1%}", f"{res.word_errors:,} of {res.ref_words:,} words wrong")
    t.add_row("word recall", f"{res.word_recall_unordered:.1%}", "reference words found anywhere, ignoring order")
    if res.line_cer is not None:
        t.add_row("CER by line", f"{res.line_cer:.1%}",
                  f"each reference line vs its closest OCR line, ignoring order ({res.extra_ocr_lines} extra OCR lines not counted)")
    if res.line_order is not None:
        t.add_row("line order", f"{res.line_order:.1%}",
                  f"{res.line_pairs_in_order} of {res.line_pairs} consecutive reference lines also consecutive in the OCR text")
    console.print(t)
    if res.trimmed:
        console.print(f"[dim]Reference trimmed to words {res.trimmed[0]}–{res.trimmed[1]} (the part the OCR covers)[/]")
    if res.word_recall_unordered - (1 - res.wer) > 0.2 or (res.line_cer is not None and res.cer - res.line_cer > 0.2):
        console.print("[yellow]Many words are right but out of order: likely a reading-order/layout problem "
                      "(e.g. two-column verse)[/]")
    if res.confusions:
        c = Table(title="Most common character errors")
        for col in ("reference", "OCR", "count"):
            c.add_column(col)
        for (r, h), n in res.confusions.most_common(12):
            c.add_row(r or "∅ (extra)", h or "∅ (missing)", str(n))
        console.print(c)
    if json_out:
        json_out.write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    if diff:
        diff.write_text("".join(f"{r or '∅'}\n  → {h or '∅'}\n\n" for r, h in res.mismatches), encoding="utf-8")


@app.command()
def bench(
    reader: Annotated[str, typer.Option(help="The line reader to score: tesseract, parisaocr (in rtlbook's image), hezar-crnn, weightedai (the readers image)")] = "tesseract",
    set_dir: Annotated[Optional[Path], typer.Option("--set", file_okay=False, help="A training set's folder (docs/TRAINING-DATA.md): its checked test lines")] = None,
    scan: Annotated[Path, typer.Option(help="The scan the set and the page texts are from")] = Path("input/public-domain/three-drops-1932.pdf"),
    page_texts: Annotated[Path, typer.Option(help="Checked whole pages, p<N>.txt, used without --set (the set's pages follow its spacing rules; these may not)")] = Path("tests/data/three-drops"),
    exported: Annotated[Path, typer.Option(help="An exported PDF")] = Path("input/public-domain/tomorrow-2006.pdf"),
    exported_text: Annotated[Path, typer.Option(help="Its reference text")] = Path("tests/data/tomorrow/reference.txt"),
    save: Annotated[Optional[Path], typer.Option(help="Add the results to this file (JSON lines), compare with its last entry for this reader, and write README.md beside it")] = None,
    image_mb: Annotated[Optional[int], typer.Option(help="The image's size, measured outside it")] = None,
    commit: Annotated[Optional[str], typer.Option(help="The source's commit, recorded with the results")] = None,
    jobs: int = 2,
) -> None:
    """The scorecard: the reader alone on checked lines, whole pages, an exported PDF, speed (ROADMAP.md)."""
    from rtlbook import bench as scorecard, readers

    r = readers.get(reader)
    skipped = []
    lines_score = pages_score = exported_score = None
    if set_dir and (set_dir / "lines.json").exists():
        console.print(f"Reading the checked test lines of {set_dir.name} with {r.name}…")
        lines_score = scorecard.score_lines(set_dir, r)
    else:
        skipped.append("lines (no --set)")
    refs = scorecard.page_references(set_dir, None if set_dir or not page_texts.is_dir() else page_texts)
    if scan.exists() and refs:
        console.print(f"Whole pages {', '.join(map(str, sorted(refs)))} of {scan.name}…")
        pages_score = scorecard.score_pages(scan, refs, jobs)
    else:
        skipped.append(f"pages ({scan} missing)" if not scan.exists() else "pages (no checked pages)")
    if exported.exists() and exported_text.exists():
        console.print(f"The exported PDF {exported.name}…")
        exported_score = scorecard.score_exported(exported, exported_text, jobs)
    else:
        skipped.append(f"exported ({exported} missing)")
    rec = scorecard.record(r, commit=commit, lines=lines_score, pages=pages_score, exported=exported_score,
                           memory_mb=scorecard.peak_memory_mb(), image_mb=image_mb)

    entries = []
    if save and save.exists():
        entries = [json.loads(x) for x in save.read_text(encoding="utf-8").splitlines() if x.strip()]
    last = next((e for e in reversed(entries) if e["reader"] == r.name), None)
    t = Table(title=f"Scorecard: rtlbook {__version__}, {r.name}")
    for col in ("case", "measure", "this run"):
        t.add_column(col, justify="right" if col == "this run" else "left")
    if last:
        t.add_column(f"last saved ({last['reader']}, {last['date'][:10]})", justify="right")
    pct = lambda v: f"{v:.2%}"
    rows = [
        ("lines", "letters_wrong", "Reader alone: letters wrong", pct),
        ("lines", "exact", "Reader alone: lines with every letter right", str),
        ("lines", "spacing_wrong", "Reader alone: word gaps wrong (space, half-space)", pct),
        ("lines", "seconds_a_line", "Reader alone: seconds a line", str),
        ("pages", "letters_wrong", "Whole pages: letters wrong", pct),
        ("pages", "letters_wrong_by_line", "Whole pages: letters wrong, line by line", pct),
        ("pages", "lines_missing", "Whole pages: lines lost or merged", str),
        ("pages", "lines_extra", "Whole pages: extra lines", str),
        ("pages", "spacing_wrong", "Whole pages: word gaps wrong", pct),
        ("pages", "joined_split", "Whole pages: joined words split", str),
        ("pages", "seconds_a_page", "Whole pages: seconds a page", str),
        ("exported", "letters_wrong", "Exported PDF: letters wrong", pct),
        ("exported", "spacing_wrong", "Exported PDF: word gaps wrong", pct),
        ("exported", "joined_split", "Exported PDF: joined words split", str),
        ("exported", "seconds_a_page", "Exported PDF: seconds a page", str),
        (None, "memory_mb", "Peak memory, MB", str),
        (None, "image_mb", "Image size, MB", str),
    ]
    for case, key, label, fmt in rows:
        now = (rec.get(case) or {}).get(key) if case else rec.get(key)
        if now is None:
            continue
        cells = [case or "", label, fmt(now)]
        if last:
            before = (last.get(case) or {}).get(key) if case else last.get(key)
            cells.append(fmt(before) if before is not None else "")
        t.add_row(*cells)
    console.print(t)
    if lines_score:
        console.print(f"[dim]Lines: {lines_score['lines']} checked test lines of {lines_score['set']} "
                      f"(data {lines_score['data']}: compare only runs on the same data)[/]")
    if pages_score:
        console.print(f"[dim]Pages: {', '.join(map(str, pages_score['pages']))}, {pages_score['lines']} lines, "
                      "through convert's own OCR[/]")
    if last and last.get("lines", {}).get("data") != (lines_score or {}).get("data"):
        console.print("[yellow]The checked lines changed since the last saved run: their numbers don't compare[/]")
    if last and last.get("pages", {}).get("pages") != (pages_score or {}).get("pages"):
        console.print("[yellow]The checked pages changed since the last saved run: their numbers don't compare[/]")
    for s in skipped:
        console.print(f"[dim]Skipped: {s}[/]")
    if save:
        save.parent.mkdir(parents=True, exist_ok=True)
        with save.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        for path, text in scorecard.report(entries + [rec]).items():
            (save.parent / path).parent.mkdir(parents=True, exist_ok=True)
            (save.parent / path).write_text(text, encoding="utf-8")
        console.print(f"Saved to {save}, and the page {save.parent / 'README.md'}")


@app.command()
def lines(
    pdf_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help=INPUT_HELP)],
    pages: Annotated[str, typer.Option(help="Pages to cut into lines, e.g. 12,20-24")],
    split: Annotated[str, typer.Option(help="train or test: test pages never go into training")],
    out: Annotated[Path, typer.Option(help="The set's folder: lines.json and the line images go here")],
    common: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Word list of common words, one per line")],
    more: Annotated[Optional[Path], typer.Option(exists=True, dir_okay=False, help="A larger word list")] = None,
    book: Annotated[Optional[Path], typer.Option(exists=True, file_okay=False, help="The book's convert work folder, for word counts")] = None,
    prefill: Annotated[Optional[str], typer.Option(help="Checked text per page to start from, e.g. 'gt/p{n}.txt'")] = None,
    dpi: int = 300,
    lang: str = "fas",
    psm: int = 4,
    source: Annotated[Optional[str], typer.Option(help="The edition, e.g. 'first printing, Tehran 1932' (kept once set)")] = None,
    public_domain: Annotated[Optional[str], typer.Option(help="yes or no: whether the source edition is public domain everywhere (kept once set)")] = None,
) -> None:
    """Cut pages into training lines for checking (docs/TRAINING-DATA.md): lines.json and an image per line."""
    from rtlbook import lines as training_lines

    if split not in ("train", "test") or public_domain not in (None, "yes", "no"):
        console.print("[red]--split is train or test, --public-domain yes or no[/]")
        raise typer.Exit(2)
    n = training_lines.prepare(pdf_path, pages, split, out, common, more, book, prefill, dpi, lang, psm, source,
                               None if public_domain is None else public_domain == "yes")
    console.print(f"{n} lines in {out / 'lines.json'}")
