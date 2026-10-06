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
    work: Annotated[Optional[Path], typer.Option(help="Work/cache dir (default: <output>.rtlbook)")] = None,
    drop_lines: Annotated[Optional[str], typer.Option(help="Regex: drop matching lines (watermarks, site banners)")] = None,
    digits: Annotated[str, typer.Option(help="Digits in the text: auto (Persian ۰-۹ for fas), fa, or keep")] = "auto",
    embed_font: Annotated[bool, typer.Option(help="Embed the Parastoo font (off: use the reader's own font)")] = True,
    min_line_conf: Annotated[float, typer.Option(help="Drop OCR lines below this confidence (0 keeps all)")] = 0.0,
    chunk_pages: Annotated[int, typer.Option(help="Pages per EPUB section when no chapters are found")] = 20,
    progress: Annotated[str, typer.Option(help="Progress output: bar, or json (one JSON line per event on stderr, for other programs)")] = "bar",
    check_script: Annotated[bool, typer.Option(help="Before OCR, check that a few pages are in the OCR language's script")] = True,
) -> None:
    """Convert a PDF into an RTL EPUB 3."""
    from rtlbook import epub, frontmatter, layout, ocr, text
    from rtlbook.pipeline import OcrSettings, extract_pages, split_sections
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
    t0 = time.perf_counter()
    scripts = check_script_of(pdf_path, numbers, lang) if check_script else script.ScriptCheck(None)
    timings["script"] = time.perf_counter() - t0
    if check_script:
        print_script(scripts)
    emit(event="start", pages=len(numbers), document=document_type(kinds).kind,
         script=scripts.found, script_expected=scripts.expected)

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

        page_results = extract_pages(
            pdf_path, numbers, work / "pages", OcrSettings(dpi, lang, psm, binarize, crop), max(1, jobs), done
        )
    timings["extract"] = time.perf_counter() - t0
    for p in page_results:  # side-by-side lines (two-column verse) read row by row, right to left
        p.lines = layout.reading_order(p.lines)

    # Raw per-page text, handy for reviewing OCR output
    with open(work / "pages.txt", "w", encoding="utf-8") as f:
        for p in page_results:
            conf = f" conf={p.mean_conf:.1f}" if p.mean_conf is not None else ""
            f.write(f"\n===== page {p.number} [{p.route}{conf}, {p.seconds}s] =====\n")
            f.write("\n".join(ln.text for ln in p.lines) + "\n")

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
    else:
        cover_img = pdf.largest_image(pdf.open_book(pdf_path), 0)

    digest = pdf.digest(pdf_path)
    fonts_dir = Path(os.environ.get("RTLBOOK_FONTS", "/opt/fonts"))
    meta = epub.BookMeta(
        title=title,
        author=author,
        lang="fa" if lang.startswith("fas") else lang[:2],
        identifier=f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'rtlbook:' + digest)}",
        cover=cover_img,
        fonts=tuple(sorted(fonts_dir.glob("*.ttf"))) if embed_font and fonts_dir.exists() else (),
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
        "ocr_engine": ocr.tesseract_version(),
        "ocr_settings": {"dpi": dpi, "lang": lang, "psm": psm, "binarize": binarize, "crop": crop, "jobs": jobs},
        "ocr_seconds_per_page_single_thread": round(
            sum(p.seconds for p in page_results) / max(1, len(page_results)), 2
        ),
        "mean_confidence": round(sum(confs) / len(confs), 1) if confs else None,
        "low_confidence_pages": low,
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
def kfx(
    kpf: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="KPF from Kindle Previewer (or run ./rtlbook kfx book.epub on the Mac)")],
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output .kfx (default: next to input)")] = None,
    book: Annotated[bool, typer.Option("--book/--doc", help="List under Books (default) or Docs on the Kindle")] = True,
) -> None:
    """Package a Kindle Previewer KPF as a sideloadable .kfx (Kindle's current format)."""
    from rtlbook import kindle

    if kpf.suffix.lower() != ".kpf":
        console.print("[red]Expected a .kpf. Kindle Previewer only runs on macOS/Windows, so convert an EPUB with "
                      "the ./rtlbook wrapper on the Mac: ./rtlbook kfx book.epub[/]")
        raise typer.Exit(2)
    output = output or kpf.with_suffix(".kfx")
    t0 = time.perf_counter()
    ok, log = kindle.kpf_to_kfx(kpf, output, book)
    output.with_suffix(".kfx.log").write_text(log + "\n", encoding="utf-8")
    if not ok:
        console.print(log[-2000:])
        console.print("[red]KFX packaging failed[/]")
        raise typer.Exit(1)
    console.print(f"[green]KFX written:[/] {output} ({output.stat().st_size:,} bytes, {time.perf_counter() - t0:.1f}s)")
    for ln in log.splitlines():
        if ln.startswith(("Features:", "Metadata:")):
            console.print(f"[dim]{ln[:300]}[/]")
