from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table

from rtlbook import __version__, pdf
from rtlbook.classify import LayerStats, PageClass, classify

DEFAULT_OUTPUT_DIR = Path("output")  # relative to the directory ./rtlbook is run from

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


def classify_pages(pdf_path: Path, pages: str | None, force_ocr: bool = False) -> list[PageClass]:
    doc = pdf.open_pdf(pdf_path)
    classes, stats = [], LayerStats()
    for n in parse_pages(pages, len(doc)):
        info = pdf.page_info(doc, n - 1)
        c = classify(info)
        if c.route == "text":
            stats.add(info.text)
        classes.append(c)
    # Book-level checks: if the "readable" text layer is reversed or split, OCR those pages too
    problem = stats.problem()
    for c in classes:
        if c.route == "text" and (problem or force_ocr):
            c.route = "ocr"
            if problem:
                c.kind = problem
    return classes


def summary_table(classes: list[PageClass]) -> Table:
    t = Table(title="Page classification")
    for col in ("kind", "route", "pages", "example pages", "median score"):
        t.add_column(col)
    groups = collections.defaultdict(list)
    for c in classes:
        groups[(c.kind, c.route)].append(c)
    for (kind, route), cs in sorted(groups.items()):
        scores = sorted(c.score for c in cs if c.score is not None)
        med = f"{scores[len(scores) // 2]:.3f}" if scores else "-"
        t.add_row(kind, route, str(len(cs)), ", ".join(str(c.number) for c in cs[:8]), med)
    return t


@app.command()
def version() -> None:
    """Print the version."""
    print(__version__)


@app.command()
def inspect(
    pdf_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Input PDF")],
    pages: Annotated[Optional[str], typer.Option(help="Page selection, e.g. 1-20,35")] = None,
    json_out: Annotated[Optional[Path], typer.Option("--json", help="Write per-page results as JSON")] = None,
) -> None:
    """Classify each page: usable text layer, broken text layer, image-only, or empty."""
    start = time.perf_counter()
    classes = classify_pages(pdf_path, pages)
    console.print(summary_table(classes))
    console.print(f"[dim]{len(classes)} pages inspected in {time.perf_counter() - start:.1f}s[/]")
    if json_out:
        json_out.write_text(json.dumps([c.__dict__ for c in classes], indent=1), encoding="utf-8")


@app.command()
def convert(
    pdf_path: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Input PDF")],
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output .epub (default: output/<pdf name>.epub)")] = None,
    title: Annotated[Optional[str], typer.Option(help="Book title (default: file name)")] = None,
    author: Annotated[str, typer.Option(help="Author")] = "",
    lang: Annotated[str, typer.Option(help="Tesseract language(s), e.g. fas or fas+ara")] = "fas",
    pages: Annotated[Optional[str], typer.Option(help="Page selection, e.g. 1-20")] = None,
    dpi: Annotated[int, typer.Option(help="Render resolution for OCR")] = 300,
    psm: Annotated[int, typer.Option(help="Tesseract page segmentation mode")] = 3,
    binarize: Annotated[bool, typer.Option(help="Otsu-binarize pages before OCR")] = True,
    crop: Annotated[float, typer.Option(help="Fraction to cut off each page edge (e.g. 0.075 for framed pages)")] = 0.0,
    jobs: Annotated[int, typer.Option("-j", "--jobs", help="Parallel pages")] = os.cpu_count() or 4,
    cover: Annotated[Optional[Path], typer.Option(help="Cover image (default: largest image on page 1)")] = None,
    work: Annotated[Optional[Path], typer.Option(help="Work/cache dir (default: <output>.rtlbook)")] = None,
    force_ocr: Annotated[bool, typer.Option(help="OCR every page even if its text layer looks fine")] = False,
    drop_lines: Annotated[Optional[str], typer.Option(help="Regex: drop matching lines (watermarks, site banners)")] = None,
    digits: Annotated[str, typer.Option(help="Digits in the text: auto (Persian ۰-۹ for fas), fa, or keep")] = "auto",
    embed_font: Annotated[bool, typer.Option(help="Embed the Vazirmatn font (off: use the reader's own font)")] = True,
    formats: Annotated[str, typer.Option(help="Outputs: epub, azw3 (old Kindle format), comma-separated. For KFX use `rtlbook kfx`")] = "epub",
    min_line_conf: Annotated[float, typer.Option(help="Drop OCR lines below this confidence (0 keeps all)")] = 0.0,
    chunk_pages: Annotated[int, typer.Option(help="Pages per EPUB section when no chapters are found")] = 20,
) -> None:
    """Convert a PDF into an RTL EPUB 3."""
    from rtlbook import epub, kindle, ocr, text
    from rtlbook.pipeline import OcrSettings, extract_pages, split_sections
    from rtlbook.validate import epubcheck

    timings: dict[str, float] = {}
    output = output or DEFAULT_OUTPUT_DIR / f"{pdf_path.stem}.epub"
    work = work or output.with_name(output.stem + ".rtlbook")
    work.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    classes = classify_pages(pdf_path, pages, force_ocr)
    timings["classify"] = time.perf_counter() - t0
    console.print(summary_table(classes))

    t0 = time.perf_counter()
    cached = 0
    with Progress(TextColumn("extract"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console) as prog:
        task = prog.add_task("pages", total=len(classes))

        def done(_page, from_cache: bool) -> None:
            nonlocal cached
            cached += from_cache
            prog.advance(task)

        page_results = extract_pages(
            pdf_path, classes, work / "pages", OcrSettings(dpi, lang, psm, binarize, crop), max(1, jobs), done
        )
    timings["extract"] = time.perf_counter() - t0

    # Raw per-page text, handy for reviewing OCR output
    with open(work / "pages.txt", "w", encoding="utf-8") as f:
        for p in page_results:
            conf = f" conf={p.mean_conf:.1f}" if p.mean_conf is not None else ""
            f.write(f"\n===== page {p.number} [{p.route}{conf}, {p.seconds}s] =====\n")
            f.write("\n".join(ln.text for ln in p.lines) + "\n")

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
        cover_img = pdf.largest_image(pdf.open_pdf(pdf_path), 0)

    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    fonts_dir = Path(os.environ.get("RTLBOOK_FONTS", "/opt/fonts"))
    meta = epub.BookMeta(
        title=title or pdf_path.stem,
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

    azw3_path = None
    wanted = {f.strip().lower() for f in formats.split(",")}
    if "azw3" in wanted:
        t0 = time.perf_counter()
        azw3_path = output.with_suffix(".azw3")
        azw3_ok, log = kindle.to_azw3(output, azw3_path)
        timings["azw3"] = time.perf_counter() - t0
        (work / "azw3.log").write_text(log + "\n", encoding="utf-8")
        if not azw3_ok:
            console.print(f"[yellow]AZW3 not created: {log.splitlines()[-1] if log else 'unknown error'}[/]")
            azw3_path = None

    confs = [p.mean_conf for p in page_results if p.mean_conf is not None]
    low = [p.number for p in page_results if p.mean_conf is not None and p.mean_conf < 80]
    stats = {
        "pdf": str(pdf_path),
        "pages": len(page_results),
        "routes": dict(collections.Counter(p.route for p in page_results)),
        "pages_from_cache": cached,
        "ocr_engine": ocr.tesseract_version() if any(p.route == "ocr" for p in page_results) else None,
        "ocr_settings": {"dpi": dpi, "lang": lang, "psm": psm, "binarize": binarize, "crop": crop, "jobs": jobs},
        "ocr_seconds_per_page_single_thread": round(
            sum(p.seconds for p in page_results) / max(1, len(page_results)), 2
        ),
        "mean_confidence": round(sum(confs) / len(confs), 1) if confs else None,
        "low_confidence_pages": low,
        "paragraphs": len(paras),
        "headings": sum(p.heading for p in paras),
        "sections": len(sections),
        "epub": str(output),
        "epub_bytes": output.stat().st_size,
        "epubcheck_ok": ok,
        "azw3": str(azw3_path) if azw3_path else None,
        "azw3_bytes": azw3_path.stat().st_size if azw3_path else None,
        "timings_seconds": {k: round(v, 1) for k, v in timings.items()},
    }
    (work / "report.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    console.print_json(data=stats)
    console.print(("[green]epubcheck: valid[/]" if ok else "[red]epubcheck: FAILED[/]") + f" (see {work / 'epubcheck.txt'})")
    if not ok:
        raise typer.Exit(1)


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
