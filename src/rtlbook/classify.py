"""Decide per page whether the PDF text layer can be trusted or the page needs OCR.

Persian/Arabic PDFs often have a text layer that renders fine but extracts as garbage
(broken ToUnicode maps, presentation forms, visual order). We score the extracted text by
how often common Persian function words occur: normal prose is ~20-35% function words,
mis-encoded text is close to 0.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rtlbook.pdf import PageInfo
from rtlbook.text import normalize_letters

FUNCTION_WORDS = frozenset(
    "و در به از که را این با است می آن برای هم یک تا بود شد من او ما شما هر یا اما اگر نه چه"
    " کرد کرده شده باید هست نیست دیگر خود".split()
)
ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]+")
PRESENTATION_FORMS = re.compile(r"[ﭐ-﷿ﹰ-﻿]")

MIN_WORDS = 20
GOOD_SCORE = 0.12
SENTENCE_END = tuple("!.?؟…")
MAX_ONE_LETTER_WORDS = 0.12  # split glyph runs ("اب کت" for "کتاب") push this to ~15-20%
LETTER = re.compile(r"[\u0621-\u063A\u0641-\u064A\u0671-\u06D3\u06FA-\u06FF]")  # not tatweel/digits


@dataclass
class PageClass:
    number: int
    kind: str  # "text-ok" | "text-broken" | "image-only" | "empty"
    route: str  # "text" | "ocr" | "skip"
    score: float | None
    reversed_: bool = False


def function_word_score(text: str) -> tuple[float | None, bool]:
    """Return (score, reversed) where reversed means words are stored in visual order."""
    text = unicodedata.normalize("NFKC", text) if PRESENTATION_FORMS.search(text) else text
    words = [normalize_letters(w) for w in ARABIC_SCRIPT.findall(text)]
    if len(words) < MIN_WORDS:
        return None, False
    fwd = sum(w in FUNCTION_WORDS for w in words) / len(words)
    rev = sum(w[::-1] in FUNCTION_WORDS for w in words) / len(words)
    return (rev, True) if rev > fwd else (fwd, False)


@dataclass
class LayerStats:
    """Book-level text-layer checks that single pages are too small to judge reliably."""

    lines: int = 0
    punct_start: int = 0  # lines whose first word starts with sentence-final punctuation
    punct_end: int = 0  # lines whose last word ends with it (normal logical order)
    words: int = 0
    one_letter: int = 0

    def add(self, text: str) -> None:
        for ln in text.splitlines():
            toks = ln.split()
            if len(toks) < 3:
                continue
            self.lines += 1
            self.punct_start += toks[0][0] in SENTENCE_END
            self.punct_end += toks[-1][-1] in SENTENCE_END
            ar = [t for t in toks if LETTER.search(t)]  # the dialogue dash "ـ" is not a word
            self.words += len(ar)
            self.one_letter += sum(len(t) == 1 for t in ar)

    @property
    def visual_order(self) -> bool:
        """Words stored right-to-left as displayed (reversed): punctuation lands at line start."""
        return self.punct_start >= 20 and self.punct_start > 3 * self.punct_end

    @property
    def split_words(self) -> bool:
        return self.words >= 200 and self.one_letter / self.words > MAX_ONE_LETTER_WORDS

    def problem(self) -> str | None:
        if self.visual_order:
            return "text-visual-order"
        if self.split_words:
            return "text-split-words"
        return None


def classify(info: PageInfo) -> PageClass:
    if info.chars == 0:
        if info.image_area > 0.05:
            return PageClass(info.number, "image-only", "ocr", None)
        return PageClass(info.number, "empty", "skip", None)
    score, rev = function_word_score(info.text)
    if score is None:
        # Too little text to judge (title pages etc.): OCR is cheap and safe
        return PageClass(info.number, "text-short", "ocr", None)
    if score >= GOOD_SCORE and not rev:
        return PageClass(info.number, "text-ok", "text", score)
    return PageClass(info.number, "text-broken", "ocr", score, rev)
