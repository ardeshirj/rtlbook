"""Word suggestions for OCR review: real words that look like a misread one.

Most OCR misreads of Persian type keep a word's letter shapes (its skeleton) and get the dots wrong: ی read as
ب, ن as ت, گ as ک. So a word that isn't in the word list is looked up by skeleton, and also with one letter
shape added, dropped or changed (an extra or missing tooth). Candidates are ranked by how close they are, whether
they are common words, and how often they occur elsewhere in the book.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Letters that differ only in dots (or the گ/ک stroke) share one skeleton class
SHAPES = {
    **dict.fromkeys("بپتثنیئيى", "b"), **dict.fromkeys("جچحخ", "h"), **dict.fromkeys("دذ", "d"),
    **dict.fromkeys("رزژ", "r"), **dict.fromkeys("سش", "s"), **dict.fromkeys("صض", "c"),
    **dict.fromkeys("طظ", "t"), **dict.fromkeys("عغ", "e"), **dict.fromkeys("فق", "f"),
    **dict.fromkeys("کگك", "k"), **dict.fromkeys("اآأإ", "a"), **dict.fromkeys("هةۀ", "o"),
    **dict.fromkeys("وؤ", "w"), "ل": "l", "م": "m",
}
MARKS = re.compile("[ً-ٰٟـ‌‍]")  # vowel marks, hamza above, tatweel, ZWNJ/ZWJ
NOT_LETTERS = re.compile(r"[^ء-غف-يپچژکگیۀ]")


def normalize(word: str) -> str:
    """Comparison form: Persian ی/ک, no vowel marks, half-spaces or punctuation."""
    word = word.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
    return NOT_LETTERS.sub("", MARKS.sub("", word))


def skeleton(word: str) -> str:
    return "".join(SHAPES.get(c, c) for c in normalize(word))


def _deletes(s: str) -> set[str]:
    return {s[:i] + s[i + 1:] for i in range(len(s))}


@dataclass
class Lexicon:
    """Known words indexed by skeleton: a large word list, a smaller list of common words, and the book's own
    words."""

    words: set[str] = field(default_factory=set)
    common: set[str] = field(default_factory=set)
    counts: Counter = field(default_factory=Counter)  # occurrences in the book's OCR text
    by_skeleton: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    by_delete: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def build(cls, common: list[str], more: list[str] = (), book_words: list[str] = (),
              min_book_count: int = 3) -> Lexicon:
        """`common`: everyday words (rank first, may join); `more`: a large list (inflections, rarer words);
        `book_words` count toward ranking, and those seen `min_book_count`+ times count as common."""
        lex = cls()
        lex.counts.update(w for w in (normalize(x) for x in book_words) if w)
        lex.common = ({normalize(w) for w in common} | {w for w, n in lex.counts.items() if n >= min_book_count}) - {""}
        for w in lex.common | {normalize(w) for w in more} - {""}:
            lex.add(w)
        return lex

    def add(self, word: str) -> None:
        self.words.add(word)
        sk = skeleton(word)
        self.by_skeleton[sk].add(word)
        for d in _deletes(sk):
            self.by_delete[d].add(word)

    def known(self, word: str) -> bool:
        """In the lexicon, or two common words printed joined (برخطوط, ازیک; و/ب may join as one letter)."""
        w = normalize(word)
        if w in self.words:
            return True
        return any(
            w[i:] in self.common and (w[:i] in self.common if i > 1 else w[:i] in "وب")
            for i in range(1, len(w) - 1)
        )

    def suggest(self, word: str, limit: int = 5) -> list[str]:
        """Known words that look like `word`, best first: same letter shapes, then one shape added, dropped or
        changed. Ties go to common words, then to the word seen more often in the book, then to the fewest
        changed letters."""
        w = normalize(word)
        sk = skeleton(w)
        if not sk:
            return []
        tiers: dict[str, int] = {}
        for c in self.by_skeleton.get(sk, ()):
            tiers[c] = 0
        near = set(self.by_delete.get(sk, ()))  # word is missing a shape
        for d in _deletes(sk):
            near |= self.by_skeleton.get(d, set())  # word has an extra shape
            near |= self.by_delete.get(d, set())  # one shape changed
        for c in near:
            tiers.setdefault(c, 1)
        tiers.pop(w, None)

        def rank(c: str) -> tuple:
            letters = SequenceMatcher(None, w, c, autojunk=False).ratio()
            return (tiers[c], c not in self.common, -math.log1p(self.counts[c]), -letters)

        return sorted(tiers, key=rank)[:limit]
