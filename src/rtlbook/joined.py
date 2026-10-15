"""Words run together after a letter that never joins the next (ا د ذ ر ز ژ و): in old type the gap there can be
tiny, and the reader misses the space. A word the word lists don't know is split, only after such a letter, into the
fewest pieces that are all known (DESIGN.md §4.7, "Joined words"). Scans only: an exported PDF's gaps are the ones typed.

Pieces are three letters or more from the everyday list (Tesseract's own Farsi word list) or the book's frequent
words, or one of a few short words; an ending never stands alone. A word in the large list (Lilak) is never split.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rtlbook.model import Page
from rtlbook.suggest import normalize

NONJOIN = frozenset("اآأإدذرزژوؤةء")
ZWNJ = "‌"
SHORT = frozenset("و از در بر با تا را هر دو سه چه که به او تو ما من یک نه هم پس چو اگر".split())
ENDINGS = frozenset("ها های هایی هایش هایم هایت هایشان ترین تر اند ایم اید ام اش ات ان ون ید یم ند ی گر گری"
                    " شان مان تان هام هات هاش".split())
PUNCTUATION = "«»،.؛:!؟()\"'-"
WORDS_DIR = Path(os.environ.get("RTLBOOK_WORDS", "/opt/words"))


@dataclass(eq=False)  # compared and hashed by identity: _best caches by splitter
class Splitter:
    known: set[str] = field(default_factory=set)  # never split
    pieces: set[str] = field(default_factory=set)  # may be cut out (with SHORT)

    @classmethod
    def build(cls, common: list[str], more: list[str] = (), book_words: list[str] = (),
              min_book_count: int = 3) -> Splitter:
        """`common`: everyday words; `more`: a large list; `book_words`: the book's own, those seen `min_book_count`+
        times count as everyday words."""
        counts = Counter(w for w in (normalize(x) for x in book_words) if w)
        common_set = {normalize(w) for w in common} | {w for w, n in counts.items() if n >= min_book_count}
        common_set.discard("")
        known = common_set | {normalize(w) for w in more}
        known.discard("")
        return cls(known, {w for w in common_set if len(w) > 2 and w not in ENDINGS})

    def _piece(self, w: str) -> bool:
        n = normalize(w)
        return n in SHORT or n in self.pieces

    def split_word(self, word: str) -> tuple[str, ...] | None:
        """The fewest pieces `word` splits into, ties to fewer short pieces, then more everyday ones; None if none."""
        return _best(self, word)

    def fix(self, text: str) -> tuple[str, int]:
        """The text with joined words split, and how many words were split."""
        out, n = [], 0
        for tok in text.split(" "):
            if ZWNJ in tok or normalize(tok) in self.known or not any(c in NONJOIN for c in tok[:-1]):
                out.append(tok)
                continue
            core = tok.strip(PUNCTUATION)
            if not core or normalize(core) in self.known:
                out.append(tok)
                continue
            parts = self.split_word(core)
            if parts and len(parts) > 1:
                tok, n = tok.replace(core, " ".join(parts)), n + 1
            out.append(tok)
        return " ".join(out), n


@lru_cache(maxsize=200_000)
def _best(sp: Splitter, w: str) -> tuple[str, ...] | None:
    if sp._piece(w):
        return (w,)
    options = []
    for i in range(1, len(w)):
        if w[i - 1] not in NONJOIN or not sp._piece(head := w[:i]):
            continue
        if rest := _best(sp, w[i:]):
            options.append((head,) + rest)
    if not options:
        return None
    return min(options, key=lambda p: (len(p), sum(len(normalize(x)) < 3 for x in p),
                                       -sum(normalize(x) in sp.pieces for x in p)))


def load(book_words: list[str], words_dir: Path = WORDS_DIR) -> Splitter | None:
    """A splitter from the image's word lists (`words.txt`, everyday; `lilak-words.txt`, large) and the book's words;
    None without the everyday list."""
    common = words_dir / "words.txt"
    if not common.exists():
        return None
    more = words_dir / "lilak-words.txt"
    return Splitter.build(common.read_text(encoding="utf-8").split(),
                          more.read_text(encoding="utf-8").split() if more.exists() else [], book_words)


def split_pages(pages: list[Page], words_dir: Path = WORDS_DIR) -> int | None:
    """Split joined words in the pages' lines, the book's words taken from the pages themselves: how many were split;
    None without the word lists."""
    splitter = load([w for p in pages for ln in p.lines for w in ln.text.split()], words_dir)
    if splitter is None:
        return None
    count = 0
    for p in pages:
        for ln in p.lines:
            ln.text, n = splitter.fix(ln.text)
            count += n
    return count
