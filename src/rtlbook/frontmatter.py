"""Title and author from a book's title page (the first page with little text).

PDF metadata isn't used: in exported Persian PDFs it is usually wrong or junk (another book's title, a website,
"Me"). On the title page, the title is the topmost line in large type; the author is a line such as
"نوشته: …" / "اثر …", or else the next large line or the short line right below the title. Credit lines
(e-book makers, websites, publishers, prizes) are skipped. A guess can be wrong, so convert reports it.
"""

from __future__ import annotations

import re
import statistics

from rtlbook.model import Line, Page
from rtlbook.text import normalize_text, sparse_pages

CREDITS = re.compile(r"الکترونیک|وب ?لاگ|وب ?گاه|اهتمام|تهیه|توسط|نشر|ناشر|چاپ|جایزه|کتابخانه|سایت|تایپ|تنظیم|"
                     r"تبدیل|کاری از|صفحه ?آرایی|ویراست|www|http|\.com", re.I)
TITLE_MARK = re.compile(r"^(?:نام کتاب|عنوان(?: کتاب)?)\s*[:：]\s*(.+)$")
AUTHOR_MARK = re.compile(r"^(?:نوشته(?:‌?ی|ٔ)?|نویسنده|اثر|به قلم|سروده(?:‌?ی)?)\s*[:：]?\s*(.+)$")
INITIAL_NAME = re.compile(r"^[\u0621-\u064A\u067E-\u06D3]\s*\.\s*\S")  # "م. مودب‌پور": a pen name, not a title
LARGE = 1.5  # times the book's usual line height
MIN_CONF = 40
PERSIAN = re.compile(r"[ء-يپ-ۓ]")


def _clean(text: str) -> str:
    text = normalize_text(text).strip(" «»\"'()[]-–—ـ:،.")
    text = re.sub(r"\s*[۰-۹0-9]{4}$", "", text).strip()  # a trailing year
    if text.count("(") != text.count(")"):  # "ماندانا معینی (مودب پور" -> keep it readable
        text = text.replace("(", "").replace(")", "").strip()
    return text


def _usable(ln: Line, max_words: int) -> bool:
    text = _clean(ln.text)
    return (bool(text) and len(PERSIAN.findall(text)) >= 2 and len(text.split()) <= max_words
            and (ln.conf or 0) >= MIN_CONF and not CREDITS.search(ln.text))


def guess_title_author(pages: list[Page]) -> tuple[str | None, str | None]:
    """(title, author) from the title page, or None where nothing convincing is found."""
    heights = [ln.bbox[3] - ln.bbox[1] for p in pages for ln in p.lines]
    if not heights:
        return None, None
    line_h = statistics.median(heights)
    sparse = sparse_pages(pages)
    front = next((p for p in pages[:5] if p.number in sparse and p.lines), None)
    if front is None:
        return None, None
    lines = sorted(front.lines, key=lambda ln: ln.bbox[1])

    def marked(pattern: re.Pattern) -> tuple[str | None, Line | None]:
        for ln in lines:
            if (m := pattern.match(normalize_text(ln.text))) and (ln.conf or 0) >= MIN_CONF:
                return _clean(m.group(1)) or None, ln
        return None, None

    title, _ = marked(TITLE_MARK)  # "نام کتاب : گندم"
    author, author_line = marked(AUTHOR_MARK)  # "نویسنده : م. مودب‌پور"
    if title:
        return title, author
    if author_line is not None:  # the title is usually the line right above "نویسنده: …"
        above = [ln for ln in lines if ln.bbox[3] <= author_line.bbox[1]]
        if above and _usable(above[-1], 6) and (above[-1].conf or 0) >= 60:
            return _clean(above[-1].text), author

    large = [ln for ln in lines if ln.bbox[3] - ln.bbox[1] >= LARGE * line_h and _usable(ln, 8)]
    names = [ln for ln in large if INITIAL_NAME.match(_clean(ln.text))]
    large = [ln for ln in large if ln not in names]
    if author is None and names:
        author = _clean(names[0].text)
    if not large:
        return None, author
    title_line = large[0]
    title = _clean(title_line.text)
    if author is None:
        below = [ln for ln in lines if ln.bbox[1] > title_line.bbox[3]]
        nxt = next((ln for ln in large[1:] if _usable(ln, 4)), None) or next(
            (ln for ln in below[:1] if _usable(ln, 4)), None)
        if nxt is not None:
            author = _clean(nxt.text)
    return title, author
