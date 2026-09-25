"""Persian text normalization and paragraph reconstruction."""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from rtlbook.headings import match_heading
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
    guillemets: bool = False  # "»" -> "،"
    hamza: bool = False  # word-final "ء" -> "،"


def detect_comma_misreads(pages: list[Page]) -> CommaFix:
    """Tesseract (fas) reads the Arabic comma in some fonts (e.g. Arial) as "»" or "ء". Only
    correct when the book has almost no real "،", so correctly OCR'd books are untouched."""
    text = normalize_letters("\n".join(ln.text for p in pages for ln in p.lines))
    closing, opening = text.count("»"), text.count("«")
    hamzas = sum(1 for m in FINAL_HAMZA.finditer(text) if m.group(1) + "ء" not in HAMZA_WORDS)
    suspects = closing + hamzas
    if suspects < 5 or text.count("،") >= 0.1 * suspects:
        return CommaFix()
    return CommaFix(guillemets=closing >= 5 and opening < 0.2 * closing, hamza=hamzas >= 3)


def fix_misread_commas(s: str, fix: CommaFix) -> str:
    if fix.guillemets:
        s = re.sub(r"\s*»\s*", "، ", s)
    if fix.hamza:
        s = FINAL_HAMZA.sub(lambda m: m.group(0) if m.group(1) + "ء" in HAMZA_WORDS else m.group(1) + "، ", s)
    s = re.sub(r"\s*،[\s\u200c]*", "، ", s)  # no space before a comma, one after
    s = re.sub(r"،(?:\s*،)+", "،", s)
    return re.sub(r" {2,}", " ", s).strip()


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
            if ln.bbox and p.width:
                x0s.append(ln.bbox[0] / p.width)
                x1s.append(ln.bbox[2] / p.width)
    if len(x0s) < 20:
        return None
    q0 = statistics.quantiles(x0s, n=20)[0]  # 5th percentile
    q1 = statistics.quantiles(x1s, n=20)[-1]  # 95th percentile
    return q0, q1 - q0


MARGIN_ZONE = 0.15  # top/bottom fraction of the page where running headers/footers live


def _margin_key(text: str) -> str:
    """Compare header/footer lines ignoring page numbers, spacing and punctuation."""
    return re.sub(r"[\d۰-۹٠-٩\W_]+", "", text).lower()


def _in_margin(ln: Line, page: Page) -> bool:
    if not (ln.bbox and page.height):
        return False
    y = (ln.bbox[1] + ln.bbox[3]) / 2 / page.height
    return y < MARGIN_ZONE or y > 1 - MARGIN_ZONE


def running_headers(pages: list[Page], min_share: float = 0.2) -> set[str]:
    """Keys of lines repeated in the top/bottom zone of many pages (site banners, book titles)."""
    seen: dict[str, set[int]] = {}
    for p in pages:
        for ln in p.lines:
            if _in_margin(ln, p) and len(k := _margin_key(ln.text)) >= 3:
                seen.setdefault(k, set()).add(p.number)
    need = max(3, min_share * len(pages))
    return {k for k, nums in seen.items() if len(nums) >= need}


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
    there is an unusually large vertical gap (blank line) before it.
    """
    margins = _margins(pages)
    comma_fix = detect_comma_misreads(pages)
    pitch = _line_pitch(pages)
    headers = running_headers(pages)
    paras: list[Paragraph] = []
    cur: Paragraph | None = None
    prev_full = False
    prev_text = ""
    pending_pages: list[int] = []

    for page in pages:
        pending_pages.append(page.number)
        prev_top = None
        for ln in page.lines:
            text = fix_misread_commas(normalize_text(ln.text), comma_fix)
            if is_debris(ln, text) or (drop and drop.search(text)) or (ln.conf is not None and ln.conf < min_conf):
                continue
            if headers and _in_margin(ln, page) and _margin_key(ln.text) in headers:
                continue
            heading = match_heading(text)
            is_heading = heading is not None
            if heading:
                text = heading
            starts_new = (
                cur is None
                or cur.heading
                or is_heading
                or DIALOGUE.match(text)
                or (not prev_full and prev_text.endswith(TERMINAL))
                or (pitch and ln.bbox and prev_top is not None and ln.bbox[1] - prev_top > 2.2 * pitch)
            )
            if starts_new:
                cur = Paragraph(heading=is_heading)
                paras.append(cur)
            elif cur.segments:
                cur.segments.append(" ")
            cur.segments.extend(pending_pages)
            pending_pages = []
            cur.segments.append(text)

            prev_text = text
            prev_top = ln.bbox[1] if ln.bbox else None
            prev_full = False
            if margins and ln.bbox and page.width:
                left, width = margins
                prev_full = (ln.bbox[0] / page.width - left) < 0.06 * width
    if pending_pages and paras:
        paras[-1].segments.extend(pending_pages)
    for p in paras:
        fix_mirrored_parens(p)
    return paras
