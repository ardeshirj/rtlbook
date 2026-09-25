"""Chapter heading detection that tolerates OCR errors.

Persian novels mark chapters as "فصل <ordinal>" (or بخش/قسمت). OCR mangles these in predictable
ways: a lost dot turns فصل into نصل/قصل, "اول" becomes "اآول", "یازدهم" becomes "بازدهم", and
"دوازدهم" is split into "دو از دهم". We accept a keyword within edit distance 1 and an ordinal
within a small edit distance (spaces ignored), and emit the canonical spelling.
"""

from __future__ import annotations

import re

KEYWORDS = ("فصل", "بخش", "قسمت")
_UNITS = ["یکم", "دوم", "سوم", "چهارم", "پنجم", "ششم", "هفتم", "هشتم", "نهم"]
_TEENS = ["دهم", "یازدهم", "دوازدهم", "سیزدهم", "چهاردهم", "پانزدهم", "شانزدهم", "هفدهم", "هجدهم", "نوزدهم"]
_TENS = {"بیست": "بیستم", "سی": "سی‌ام", "چهل": "چهلم", "پنجاه": "پنجاهم"}


def _ordinals() -> dict[str, int]:
    words = {"اول": 1, "نخست": 1, "یکم": 1, "هیجدهم": 18}
    for i, w in enumerate(_UNITS[1:], 2):
        words[w] = i
    for i, w in enumerate(_TEENS, 10):
        words[w] = i
    for t, (stem, final) in enumerate(_TENS.items(), 2):
        words[final] = t * 10
        for u, unit in enumerate(_UNITS, 1):
            words[f"{stem} و {unit}"] = t * 10 + u
    return words


ORDINALS = _ordinals()
_ORDINALS_NOSPACE = {k.replace(" ", "").replace("‌", ""): (k, v) for k, v in ORDINALS.items()}
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def _edit_distance(a: str, b: str, limit: int) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def match_heading(text: str) -> str | None:
    """Return the canonical heading ("فصل دوازدهم", "فصل ۳") or None."""
    text = re.sub(r"[\s‌:.\-–—ـ]+$", "", text.strip())
    toks = text.split()
    if not 2 <= len(toks) <= 5 or re.search(r"[!?؟«»،,]", text):
        return None
    keyword = next((k for k in KEYWORDS if _edit_distance(toks[0], k, 1) <= (1 if k == "فصل" else 0)), None)
    if not keyword:
        return None
    rest = "".join(toks[1:]).replace("‌", "")
    if rest.translate(_DIGITS).isdigit():
        return f"{keyword} {rest}"
    best, best_d = None, 99
    for key, (canon, _) in _ORDINALS_NOSPACE.items():
        d = _edit_distance(rest, key, 2)
        if d < best_d:
            best, best_d = canon, d
    # Short ordinals ("دوم") must be exact or 1 edit; long ones allow 2
    if best and best_d <= (1 if len(rest) <= 5 else 2):
        return f"{keyword} {best}"
    return None
