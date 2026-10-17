"""Half-spaces where today's spelling has them (DESIGN.md §4.7, "Half-spaces"): a full space between a word and a
prefix or ending that belongs to it becomes a half-space (ZWNJ), so a reading system keeps the word whole when it
breaks lines, searches or looks a word up. Readers mostly read a half-space as a space, and older type often sets
these with a visible gap. Five patterns only, each checked against a proofread text: the plural ها and its forms,
تر/ترین, the endings ام/ای/اش/ایم/اید/اند after a silent ه, the verb prefixes می/نمی, and بی. Compound words are
left alone: which of them take a half-space is word knowledge, and spellings differ.
"""

from __future__ import annotations

import re

from rtlbook.model import Page
from rtlbook.suggest import normalize

ZWNJ = "‌"
PLURAL = frozenset("ها های هایی هایم هایت هایش هایمان هایتان هایشان".split())
COMPARATIVE = frozenset("تر ترین تری".split())
AFTER_SILENT_H = frozenset("ام ای اش ایم اید اند".split())
PREFIXES = frozenset("می نمی بی".split())
EDGES = re.compile(r"^(\W*)(.*?)(\W*)$", re.S)  # punctuation around a word: «می» or ها،


def _belongs(word: str, after: str) -> bool:
    """Whether `after` is an ending of `word`, or `word` a prefix of `after` (both bare, in comparison form; `word`
    whole, so the end of a word with a half-space is never taken for a prefix: بی‌بی خانم stays two words)."""
    if not word or not after:
        return False
    last = word.split(ZWNJ)[-1]
    return (after in PLURAL or after in COMPARATIVE or (after in AFTER_SILENT_H and last.endswith("ه"))
            or word in PREFIXES)


def join(text: str) -> tuple[str, int]:
    """The text with those spaces made half-spaces, and how many."""
    out, n = [], 0
    for tok in text.split(" "):
        if out:
            _, word, trail = EDGES.match(out[-1]).groups()
            lead, after, _ = EDGES.match(tok).groups()
            if not trail and not lead and word.replace(ZWNJ, "").isalpha() and after.replace(ZWNJ, "").isalpha() \
                    and _belongs(ZWNJ.join(normalize(x) for x in word.split(ZWNJ)), normalize(after.split(ZWNJ)[0])):
                out[-1] += ZWNJ + tok
                n += 1
                continue
        out.append(tok)
    return " ".join(out), n


def join_pages(pages: list[Page]) -> int:
    """Half-spaces put in the pages' lines: how many."""
    count = 0
    for p in pages:
        for ln in p.lines:
            ln.text, n = join(ln.text)
            count += n
    return count
