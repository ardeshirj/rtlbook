"""OCR accuracy against a reference text: character and word error rates, Persian-aware.

Both texts are normalized the same way first, so spelling conventions that differ between an old
printing and a modern transcription don't count as OCR errors: Arabic ي/ك, tatweel, digits, the
half-space (ZWNJ, removed so "می‌کرد" and "میکرد" match) and, by default, vowel marks.

Alignment is word-level first (difflib), then character-level inside mismatched stretches, which
keeps whole books fast without a native Levenshtein library.
"""

from __future__ import annotations

import collections
import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from rtlbook.text import normalize_letters, persian_digits

MARKS = re.compile("[ً-ٰٟ]")  # harakat, tanwin, shadda, sukun, hamza above/below, superscript alef
_HAMZA_SEATS = str.maketrans({"أ": "ا", "إ": "ا", "ؤ": "و", "ة": "ه"})  # ة: some PDFs encode ۀ (هٔ) as ة
_INVISIBLE = re.compile("[‌‍‎‏‪-‮⁦-⁩﻿]")
WORD = re.compile(r"[^\W_]+(?:[ً-ٰٟ]+[^\W_]*)*")
PAGE_MARKER = re.compile(r"^===== page (\d+)\b.*=====$")
MAX_CHAR_SPAN = 3000  # longer mismatched stretches are counted without a character alignment


def normalize(text: str, keep_marks: bool = False) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = normalize_letters(text).replace("ۀ", "هٔ")
    if not keep_marks:
        text = MARKS.sub("", text).translate(_HAMZA_SEATS)
    text = _INVISIBLE.sub("", text)
    return persian_digits(text)


def words(text: str, keep_marks: bool = False) -> list[str]:
    return WORD.findall(normalize(text, keep_marks))


def read_text(path_text: str, pages: set[int] | None = None) -> str:
    """Plain text, or rtlbook's pages.txt (optionally only some pages). Headings marked "## " in
    paragraphs.txt are read as text."""
    out, keep = [], pages is None
    for line in path_text.splitlines():
        if m := PAGE_MARKER.match(line):
            keep = pages is None or int(m.group(1)) in pages
            continue
        if keep:
            out.append(line[3:] if line.startswith("## ") else line)
    return "\n".join(out)


@dataclass
class Result:
    ref_words: int = 0
    hyp_words: int = 0
    word_errors: int = 0
    ref_chars: int = 0
    char_errors: int = 0
    unordered_hits: int = 0  # reference words found anywhere in the OCR text (ignores reading order)
    trimmed: tuple[int, int] | None = None  # reference word range used, if trimmed
    line_ref_chars: int = 0  # line-matched scoring (ignores reading order); 0 = not computed
    line_char_errors: int = 0
    extra_ocr_lines: int = 0  # OCR lines with no reference line (footnotes, headers, page numbers)
    line_pairs: int = 0  # consecutive reference lines that were both found in the OCR text...
    line_pairs_in_order: int = 0  # ...and also follow each other there
    confusions: collections.Counter = field(default_factory=collections.Counter)
    mismatches: list[tuple[str, str]] = field(default_factory=list)

    @property
    def cer(self) -> float:
        return self.char_errors / max(1, self.ref_chars)

    @property
    def wer(self) -> float:
        return self.word_errors / max(1, self.ref_words)

    @property
    def word_recall_unordered(self) -> float:
        return self.unordered_hits / max(1, self.ref_words)

    @property
    def line_order(self) -> float | None:
        return self.line_pairs_in_order / self.line_pairs if self.line_pairs else None

    @property
    def line_cer(self) -> float | None:
        return self.line_char_errors / self.line_ref_chars if self.line_ref_chars else None

    def to_dict(self, top: int = 20) -> dict:
        return {
            "cer": round(self.cer, 4),
            "wer": round(self.wer, 4),
            "word_recall_unordered": round(self.word_recall_unordered, 4),
            "line_cer": round(self.line_cer, 4) if self.line_cer is not None else None,
            "extra_ocr_lines": self.extra_ocr_lines,
            "line_order": round(self.line_order, 4) if self.line_order is not None else None,
            "ref_chars": self.ref_chars,
            "char_errors": self.char_errors,
            "ref_words": self.ref_words,
            "hyp_words": self.hyp_words,
            "word_errors": self.word_errors,
            "reference_trimmed_to_words": list(self.trimmed) if self.trimmed else None,
            "top_confusions": [
                {"ref": r, "ocr": h, "count": n} for (r, h), n in self.confusions.most_common(top)
            ],
        }


def _char_edits(ref: str, hyp: str) -> tuple[int, list[tuple[str, str]]]:
    """Levenshtein distance with the edits: (ref char, hyp char), "" for insertions/deletions."""
    n, m = len(ref), len(hyp)
    if n * m > MAX_CHAR_SPAN * MAX_CHAR_SPAN // 4:
        return max(n, m), []
    prev = list(range(m + 1))
    rows = [prev]
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ref[i - 1] != hyp[j - 1]))
        rows.append(cur)
        prev = cur
    edits, i, j = [], n, m
    while i or j:
        if i and j and rows[i][j] == rows[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            if ref[i - 1] != hyp[j - 1]:
                edits.append((ref[i - 1], hyp[j - 1]))
            i, j = i - 1, j - 1
        elif i and rows[i][j] == rows[i - 1][j] + 1:
            edits.append((ref[i - 1], ""))
            i -= 1
        else:
            edits.append(("", hyp[j - 1]))
            j -= 1
    return rows[n][m], edits


def _trim_reference(ref: list[str], hyp: list[str], slack: int = 0, reach: int = 30) -> tuple[int, int]:
    """Word range of the reference that the OCR text covers (for a reference longer than the pages).

    Anchored on matches of 3+ words, then widened over nearby 2-word matches, so misread words at
    the start or end of the pages stay in, but OCR text that isn't in the reference at all (a
    footnote, a page header) doesn't pull in more reference."""
    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    blocks = [b for b in sm.get_matching_blocks() if b.size >= 2]
    anchors = [b for b in blocks if b.size >= 3]
    if not anchors:
        return 0, len(ref)
    first, last = anchors[0], anchors[-1]
    a = min(b.a for b in blocks if first.a - reach <= b.a <= first.a and first.b - reach <= b.b <= first.b)
    b_end = max(b.a + b.size for b in blocks
                if last.a <= b.a <= last.a + last.size + reach and last.b <= b.b <= last.b + last.size + reach)
    return max(0, a - slack), min(len(ref), b_end + slack)


MAX_LINE_PAIRS = 250_000  # line matching compares every pair, so only for page-sized texts


def _line_scores(ref_lines: list[str], hyp_lines: list[str], res: Result) -> None:
    """Match each reference line to its most similar OCR line (one-to-one, greedy), so text read in
    the wrong order still scores by how well its letters were recognized."""
    if not ref_lines or len(ref_lines) * max(1, len(hyp_lines)) > MAX_LINE_PAIRS:
        return
    pairs = sorted(
        ((difflib.SequenceMatcher(None, r, h, autojunk=False).ratio(), i, j)
         for i, r in enumerate(ref_lines) for j, h in enumerate(hyp_lines)),
        reverse=True,
    )
    match: dict[int, int] = {}
    used: set[int] = set()
    for score, i, j in pairs:
        if score < 0.3:
            break
        if i not in match and j not in used:
            match[i] = j
            used.add(j)
    res.line_ref_chars = sum(len(r) for r in ref_lines)
    res.line_char_errors = sum(
        _char_edits(r, hyp_lines[match[i]])[0] if i in match else len(r) for i, r in enumerate(ref_lines)
    )
    res.extra_ocr_lines = len(hyp_lines) - len(used)
    # Reading order: does the next reference line also come next among the matched OCR lines?
    rank = {j: k for k, j in enumerate(sorted(used))}
    for i in range(len(ref_lines) - 1):
        if i in match and i + 1 in match:
            res.line_pairs += 1
            res.line_pairs_in_order += rank[match[i + 1]] == rank[match[i]] + 1


def _letter_lines(text: str, keep_marks: bool) -> list[list[str]]:
    return [ws for line in text.splitlines() if (ws := words(line, keep_marks))]


def compare(reference: str, ocr: str, keep_marks: bool = False, trim: bool | None = None) -> Result:
    """trim: None = automatically when the reference is clearly longer than the OCR text (by 20%+)
    and 10+ of its words lie outside what the OCR covers, e.g. a whole poem for a page that shows
    only its end. A reference of the same length is never trimmed: badly misread lines at the
    start or end of a page would otherwise look like extra reference text."""
    ref, hyp = words(reference, keep_marks), words(ocr, keep_marks)
    res = Result(hyp_words=len(hyp))
    if trim is not False:
        a, b = _trim_reference(ref, hyp)
        cut = len(ref) - (b - a)
        if cut and (trim or (cut >= 10 and len(ref) > 1.2 * len(hyp))):
            res.trimmed = (a, b)
            ref = ref[a:b]
    # Lines of the reference inside the (possibly trimmed) word range, as letters without spaces
    ref_lines, pos = [], 0
    a, b = res.trimmed or (0, len(ref))
    for ws in _letter_lines(reference, keep_marks):
        if pos < b and pos + len(ws) > a:
            ref_lines.append("".join(ws))
        pos += len(ws)
    _line_scores(ref_lines, ["".join(ws) for ws in _letter_lines(ocr, keep_marks)], res)
    res.ref_words = len(ref)
    res.ref_chars = sum(len(w) for w in ref)
    pool = collections.Counter(hyp)
    for w in ref:
        if pool[w]:
            pool[w] -= 1
            res.unordered_hits += 1

    sm = difflib.SequenceMatcher(None, ref, hyp, autojunk=False)
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op == "equal":
            continue
        res.word_errors += max(a2 - a1, b2 - b1)
        # Characters only, no spaces: word splits/joins differ between editions and transcriptions
        dist, edits = _char_edits("".join(ref[a1:a2]), "".join(hyp[b1:b2]))
        res.char_errors += dist
        res.confusions.update(edits)
        res.mismatches.append((" ".join(ref[a1:a2]), " ".join(hyp[b1:b2])))
    return res
