"""Persian text normalization and paragraph reconstruction."""

from __future__ import annotations

import difflib
import re
import statistics
from dataclasses import dataclass

from rtlbook.headings import match_heading, numbered_title
from rtlbook.model import Line, Page, Paragraph

_LETTER_MAP = str.maketrans({
    "ي": "ی",  # Arabic yeh -> Persian yeh
    "ى": "ی",  # alef maksura -> Persian yeh
    "ك": "ک",  # Arabic kaf -> keheh
    "ـ": None,  # tatweel
})

TERMINAL = tuple(".!?؟:…»\"'")
# Dialogue line: "سارا- ..." / "من-..." / "سارا با لبخند- ..." / "- ..." / screenplay "علی : ..."
DIALOGUE = re.compile(r"^(?:[-–—ـ]|[\u0600-\u06FF\u200c]+(?: [\u0600-\u06FF\u200c]+){0,2}\s?(?:[-–—ـ]|:\s))")
LETTERS = re.compile(r"[^\W\d_]")
# Real words ending in a bare hamza; other word-final "ء" in a comma-misread book is a comma
HAMZA_WORDS = frozenset(
    "جزء شیء سوء بطیء کفء اجزاء اعضاء انشاء املاء ابتداء انتهاء علماء فقهاء شعراء اولیاء"
    " انبیاء اشیاء احیاء امضاء استثناء اقتضاء اطباء ادباء حکماء خلفاء رؤساء وزراء اغنیاء"
    " فقراء سماء هواء دعاء بناء".split()
)
FINAL_HAMZA = re.compile(r"([\u0600-\u06FF]*)ء(?=\s|[\u0600-\u06FF\u200c]|$)")


_TO_PERSIAN_DIGITS = str.maketrans("0123456789٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹" * 2)
LATIN_LETTER = re.compile(r"[A-Za-z]")


def persian_digits(s: str) -> str:
    """Latin and Arabic-Indic digits -> Persian digits, except in tokens with Latin letters
    (URLs, model names like "A4", English words)."""
    return "".join(
        tok if LATIN_LETTER.search(tok) else tok.translate(_TO_PERSIAN_DIGITS)
        for tok in re.split(r"(\s+)", s)
    )


def apply_digits(paras: list[Paragraph], style: str) -> None:
    """style: "fa" (Persian digits) or "keep" (as printed)."""
    if style != "fa":
        return
    for p in paras:
        p.segments = [persian_digits(seg) if isinstance(seg, str) else seg for seg in p.segments]


def normalize_letters(s: str) -> str:
    return s.translate(_LETTER_MAP)


def normalize_text(s: str) -> str:
    s = normalize_letters(s)
    s = re.sub(r"[ \t ]+", " ", s)
    return s.strip()


@dataclass(frozen=True)
class CommaFix:
    hamza: bool = False  # word-final "ء" -> "،" ("»" is handled per paragraph: fix_unopened_guillemets)


def detect_comma_misreads(pages: list[Page]) -> CommaFix:
    """Tesseract (fas) reads the Arabic comma in some fonts (e.g. Arial) as "»" or "ء". Only
    correct when the book has almost no real "،", so correctly OCR'd books are untouched."""
    text = normalize_letters("\n".join(ln.text for p in pages for ln in p.lines))
    closing = text.count("»")
    hamzas = sum(1 for m in FINAL_HAMZA.finditer(text) if m.group(1) + "ء" not in HAMZA_WORDS)
    suspects = closing + hamzas
    if suspects < 5 or text.count("،") >= 0.1 * suspects:
        return CommaFix()
    return CommaFix(hamza=hamzas >= 3)


def fix_misread_commas(s: str, fix: CommaFix) -> str:
    if fix.hamza:
        s = FINAL_HAMZA.sub(lambda m: m.group(0) if m.group(1) + "ء" in HAMZA_WORDS else m.group(1) + "، ", s)
    s = re.sub(r"\s*،[\s\u200c]*", "، ", s)  # no space before a comma, one after
    s = re.sub(r"،(?:\s*،)+", "،", s)
    return re.sub(r" {2,}", " ", s).strip()


def fix_unopened_guillemets(p: Paragraph) -> None:
    """Tesseract often reads the Persian comma "،" as "»". A "»" with no open "«" before it in the
    paragraph can't be a closing quotation mark, so it's a comma. Works per paragraph, because a
    quotation can open on one line and close on the next."""
    open_ = 0
    for i, seg in enumerate(p.segments):
        if not isinstance(seg, str) or not ("»" in seg or "«" in seg):
            continue
        out = []
        for ch in seg:
            if ch == "«":
                open_ += 1
            elif ch == "»":
                if open_:
                    open_ -= 1
                else:
                    ch = "،"
            out.append(ch)
        seg = re.sub(r"[ \t]+،", "،", "".join(out))  # no space before a comma...
        p.segments[i] = re.sub(r"،[ \t\u200c]*(?=\S)", "، ", seg)  # ...one after


def fix_mirrored_parens(p: Paragraph) -> None:
    """RTL OCR often emits the closing parenthesis as "(" (its visual shape), and
    parentheticals often span lines: "(با صدای آهسته(" -> "(با صدای آهسته)".
    Only paragraphs with more "(" than ")" are touched."""
    text = p.text
    if text.count("(") <= text.count(")"):
        return
    open_ = False
    for i, seg in enumerate(p.segments):
        if not isinstance(seg, str):
            continue
        chars = list(seg)
        for j, ch in enumerate(chars):
            if ch == "(":
                if open_:
                    chars[j] = ")"
                open_ = not open_
            elif ch == ")":
                open_ = False
        p.segments[i] = "".join(chars)


def is_debris(ln: Line, text: str) -> bool:
    """Page-border fragments and stray marks: no letters, or a lone low-confidence letter."""
    n = len(LETTERS.findall(text))
    return n == 0 or (n <= 1 and (ln.conf or 100) < 50)


def _margins(pages: list[Page]) -> tuple[float, float] | None:
    """Left margin and text width, as fractions of page width, over all OCR lines."""
    x0s, x1s = [], []
    for p in pages:
        for ln in p.lines:
            if p.width:
                x0s.append(ln.bbox[0] / p.width)
                x1s.append(ln.bbox[2] / p.width)
    if len(x0s) < 20:
        return None
    q0 = statistics.quantiles(x0s, n=20)[0]  # 5th percentile
    q1 = statistics.quantiles(x1s, n=20)[-1]  # 95th percentile
    return q0, q1 - q0


MARGIN_ZONE = 0.15  # top/bottom fraction of the page where running headers/footers live
MARGIN_MIN_CONF = 50  # margin lines OCR'd below this are page furniture read as junk (e.g. a footer in Latin)
SPARSE_PAGE = 0.25  # a page with less than this share of the book's typical word count: title, credits, contents
BIG_TYPE = 1.6  # a short line this many times the book's usual line height is a heading...
BIG_TYPE_DENSITY = 1.6  # ...if its letters are big too: few letters per line-height of width (body text ~2.5;
                        # two body lines merged into one tall box keep the body density)
HEADING_MIN_CONF = 60  # large-type headings read below this are usually OCR of an illustration
NUMBERED_MIN_CONF = 40


def _margin_key(text: str) -> str:
    """Compare header/footer lines ignoring page numbers, spacing and punctuation."""
    return re.sub(r"[\d۰-۹٠-٩\W_]+", "", text).lower()


def _in_margin(ln: Line, page: Page) -> bool:
    if not page.height:
        return False
    y = (ln.bbox[1] + ln.bbox[3]) / 2 / page.height
    return y < MARGIN_ZONE or y > 1 - MARGIN_ZONE


def _is_running_header(key: str, headers: set[str]) -> bool:
    """A margin line that is a running header, allowing for OCR variants: the same text read slightly
    differently ("رکسائنا"), or only part of it ("رکسانا- کتابخانه مجازی" of "تک سایت رکسانا- …")."""
    if not headers or len(key) < 3:
        return False
    if key in headers:
        return True
    return len(key) >= 6 and any(
        key in h or h in key or difflib.SequenceMatcher(None, key, h, autojunk=False).ratio() >= 0.8 for h in headers
    )


def running_headers(pages: list[Page], min_share: float = 0.2) -> set[str]:
    """Keys of lines repeated in the top/bottom zone of many pages (site banners, book titles)."""
    seen: dict[str, set[int]] = {}
    for p in pages:
        for ln in p.lines:
            if _in_margin(ln, p) and len(k := _margin_key(ln.text)) >= 3:
                seen.setdefault(k, set()).add(p.number)
    need = max(3, min_share * len(pages))
    return {k for k, nums in seen.items() if len(nums) >= need}


def _layout_heading(ln: Line, text: str, gap: float | None, line_h: float, page: Page,
                    margins: tuple[float, float] | None, after_break: bool = True) -> str | None:
    """A heading recognised by layout: large type, or a short numbered title with space above it that
    follows a finished sentence (a title never interrupts one)."""
    if not line_h:
        return None
    width = max(1, ln.bbox[2] - ln.bbox[0])
    conf = ln.conf if ln.conf is not None else 100
    if (ln.bbox[3] - ln.bbox[1] >= BIG_TYPE * line_h and len(text.split()) <= 12
            and len(text) * line_h / width < BIG_TYPE_DENSITY and conf >= HEADING_MIN_CONF):
        return text
    short = margins is None or not page.width or width / page.width < 0.6 * margins[1]
    if short and after_break and (gap is None or gap >= 2 * line_h) and conf >= NUMBERED_MIN_CONF:
        return numbered_title(text)
    return None


def sparse_pages(pages: list[Page]) -> set[int]:
    """Pages with far fewer words than the book's typical page: title, credits, contents, chapter
    title pages. Their lines aren't joined into paragraphs, nor into the next page's text."""
    counts = {p.number: sum(len(ln.text.split()) for ln in p.lines) for p in pages}
    full = sorted(c for c in counts.values() if c)
    if len(full) < 3:
        return set()
    typical = full[len(full) // 2]
    return {n for n, c in counts.items() if c < SPARSE_PAGE * typical}


def _line_pitch(pages: list[Page]) -> float | None:
    """Median distance between tops of consecutive OCR lines on a page."""
    gaps = [
        b.bbox[1] - a.bbox[1]
        for p in pages
        for a, b in zip(p.lines, p.lines[1:])
        if a.bbox and b.bbox and b.bbox[1] > a.bbox[1]
    ]
    return statistics.median(gaps) if len(gaps) >= 20 else None


def build_paragraphs(
    pages: list[Page], drop: re.Pattern | None = None, min_conf: float = 0.0
) -> list[Paragraph]:
    """Join visual lines into paragraphs, across page breaks.

    A line continues the previous one unless it starts a dialogue turn or a heading, or the
    previous line ended a sentence without running to the left margin (RTL line end), or
    there is an unusually large vertical gap (blank line) before it. Lines on sparse pages
    (title, credits, contents) stand alone.

    Headings: "فصل" + ordinal, a short line in large type, or a short numbered title ("۲ـ غلام")
    with space above it. A large-type title that wraps stays one heading.
    """
    margins = _margins(pages)
    sparse = sparse_pages(pages)
    prev_sparse = False
    comma_fix = detect_comma_misreads(pages)
    pitch = _line_pitch(pages)
    headers = running_headers(pages)
    heights = [ln.bbox[3] - ln.bbox[1] for p in pages for ln in p.lines]
    line_h = statistics.median(heights) if heights else 0
    paras: list[Paragraph] = []
    cur: Paragraph | None = None
    prev_full = False
    prev_text = ""
    pending_pages: list[int] = []

    for page in pages:
        pending_pages.append(page.number)
        prev_top = prev_bottom = None
        page_sparse = page.number in sparse
        first_on_page = True
        for ln in page.lines:
            text = fix_misread_commas(normalize_text(ln.text), comma_fix)
            if is_debris(ln, text) or (drop and drop.search(text)) or (ln.conf is not None and ln.conf < min_conf):
                continue
            if _in_margin(ln, page) and (
                _is_running_header(_margin_key(ln.text), headers) or (ln.conf is not None and ln.conf < MARGIN_MIN_CONF)
            ):
                continue
            gap = ln.bbox[1] - prev_bottom if prev_bottom is not None else None
            after_break = cur is None or cur.heading or prev_sparse and first_on_page or prev_text.endswith(TERMINAL)
            heading = match_heading(text) or (
                None if page_sparse else _layout_heading(ln, text, gap, line_h, page, margins, after_break))
            is_heading = heading is not None
            if heading:
                text = heading
            continues_heading = (
                is_heading and cur is not None and cur.heading and gap is not None and gap < 1.5 * line_h
            )
            starts_new = not continues_heading and (
                cur is None
                or page_sparse
                or (first_on_page and prev_sparse)
                or cur.heading
                or is_heading
                or DIALOGUE.match(text)
                or (not prev_full and prev_text.endswith(TERMINAL))
                or (pitch and prev_top is not None and ln.bbox[1] - prev_top > 2.2 * pitch)
            )
            if starts_new:
                cur = Paragraph(heading=is_heading, sparse=page_sparse)
                paras.append(cur)
            elif cur.segments:
                cur.segments.append(" ")
            cur.segments.extend(pending_pages)
            pending_pages = []
            cur.segments.append(text)
            if ln.conf is not None:
                cur.confs.append(ln.conf)

            prev_text = text
            first_on_page = False
            prev_top, prev_bottom = ln.bbox[1], ln.bbox[3]
            prev_full = False
            if margins and page.width:
                left, width = margins
                prev_full = (ln.bbox[0] / page.width - left) < 0.06 * width
        if not first_on_page:  # the page had text
            prev_sparse = page_sparse
    if pending_pages and paras:
        paras[-1].segments.extend(pending_pages)
    for p in paras:
        fix_mirrored_parens(p)
        fix_unopened_guillemets(p)
    apply_contents(paras)
    return paras


CONTENTS_ENTRY = re.compile(r"^\s*(?:[۰-۹0-9]{1,3}|ا)?\s*[-–—ـ:.)]?\s*(.*?)[\s.…_ـ]*[۰-۹0-9]*\s*$")


def _letters(text: str) -> str:
    return "".join(re.findall(r"[\u0621-\u064A\u067E-\u06D3]", normalize_letters(text)))


def contents_entries(paras: list[Paragraph]) -> list[tuple[str, float]]:
    """(entry, confidence) from the book's contents page: a sparse page (title, credits, contents) with
    at least 4 numbered lines. Numbers and page numbers are stripped."""
    entries = []
    for p in paras:
        if not p.sparse or p.heading:
            continue
        numbered = bool(re.match(r"^\s*(?:[۰-۹0-9]{1,3}|ا)\s*[-–—ـ:.)]?\s*\S", p.text)) or bool(re.search(r"[۰-۹0-9]+\s*$", p.text))
        m = CONTENTS_ENTRY.match(p.text)
        entry = m.group(1).strip(" :.") if m else ""
        if numbered and len(_letters(entry)) >= 3 and len(entry.split()) <= 10:
            entries.append((entry, p.conf or 0.0))
    return entries if len(entries) >= 4 else []


def apply_contents(paras: list[Paragraph], fix_ratio: float = 0.6, promote_ratio: float = 0.85) -> None:
    """Use the book's contents page: a chapter heading OCR'd worse than its contents entry takes the entry's
    text ("راه شکست. ما" -> "راه شکستن طلسم"), and a short standalone line in the text that matches an
    entry becomes a heading (titles that aren't set apart by size or numbering)."""
    entries = contents_entries(paras)
    if not entries:
        return
    keyed = [(e, c, _letters(e)) for e, c in entries]

    def best(text: str) -> tuple[float, str, float]:
        k = _letters(text)
        return max(((difflib.SequenceMatcher(None, k, ek, autojunk=False).ratio(), e, c) for e, c, ek in keyed),
                   default=(0.0, "", 0.0))

    for p in paras:
        if p.sparse:
            continue
        if p.heading:
            ratio, entry, conf = best(p.text)
            if ratio >= fix_ratio and conf > (p.conf or 0):
                p.segments = [s for s in p.segments if isinstance(s, int)] + [entry]
        elif len(p.text.split()) <= 10 and best(p.text)[0] >= promote_ratio:
            p.heading = True
