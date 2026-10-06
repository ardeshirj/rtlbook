"""Which writing system a book is in, checked before OCR: Tesseract's orientation and script detection (OSD,
--psm 0) on a few pages picked at random from the body of the book. OSD looks at the shapes on the page, not at the
PDF's text layer, so it works on scans and on PDFs whose text layer is garbled (old Persian fonts often are). It
names the script (Arabic covers Persian, Arabic, Urdu...), not the language; its confidence number varies too much
to use, so only the name counts, by majority."""

from __future__ import annotations

import io
import random
import subprocess
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image

# The script each OCR language is written in, as OSD names it. Languages OSD can't tell apart (or not listed)
# skip the check.
LANG_SCRIPTS = {
    "fas": "Arabic", "ara": "Arabic", "urd": "Arabic", "pus": "Arabic", "snd": "Arabic", "uig": "Arabic",
    "heb": "Hebrew", "yid": "Hebrew",
}
SAMPLE = 3  # pages with an answer needed
TRIES = 6  # pages tried at most (blank pages and pictures give no answer)


def expected_script(lang: str) -> str | None:
    """The script of a Tesseract language list ("fas+ara"), or None when they differ or aren't known."""
    scripts = {LANG_SCRIPTS.get(code) for code in lang.split("+")}
    return scripts.pop() if len(scripts) == 1 else None


def sample_pages(numbers: list[int], seed: str, tries: int = TRIES) -> list[int]:
    """Up to `tries` pages in random order, from the body of the book: the first and last tenth (cover, title page,
    index) are left out when there's enough left. The same seed (the book's hash) picks the same pages."""
    skip = len(numbers) // 10
    body = numbers[skip:len(numbers) - skip] or numbers
    return random.Random(seed).sample(body, min(tries, len(body)))


def osd(image: Image.Image) -> str | None:
    """The script Tesseract sees on a page, or None (too little text: a blank page, a picture)."""
    buf = io.BytesIO()
    image.save(buf, "PNG", dpi=(300, 300))
    proc = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "0"], input=buf.getvalue(), capture_output=True)
    return parse_osd(proc.stdout.decode("utf-8", "replace")) if proc.returncode == 0 else None


def parse_osd(output: str) -> str | None:
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Script":
            return value.strip() or None
    return None


@dataclass
class ScriptCheck:
    expected: str | None  # from the OCR language; None: not checked
    seen: dict[int, str | None] = field(default_factory=dict)  # page number → script (None: no answer)

    @property
    def found(self) -> str | None:
        """The script most sampled pages show, or None without a majority of answers."""
        answers = [s for s in self.seen.values() if s]
        if not answers:
            return None
        script, n = Counter(answers).most_common(1)[0]
        return script if n > len(answers) / 2 else None

    @property
    def mismatch(self) -> bool:
        """The book is clearly in another script than the OCR language's."""
        return self.expected is not None and self.found is not None and self.found != self.expected

    def message(self) -> str:
        pages = ", ".join(f"{n}: {s or '-'}" for n, s in sorted(self.seen.items()))
        if self.expected is None:
            return "Script check skipped (no known script for this OCR language)."
        if self.found is None:
            return f"Script: no clear answer (pages {pages})."
        if self.mismatch:
            return (f"Script: {self.found}, but the OCR language expects {self.expected} (pages {pages}). "
                    "This book is probably in another language: OCR would produce nonsense.")
        return f"Script: {self.found} (pages {pages})."


def check(render, numbers: list[int], lang: str, seed: str) -> ScriptCheck:
    """OSD on sampled pages until SAMPLE have answered. `render(n)` gives page n as an image."""
    result = ScriptCheck(expected_script(lang))
    if result.expected is None:
        return result
    for n in sample_pages(numbers, seed):
        result.seen[n] = osd(render(n))
        answers = Counter(s for s in result.seen.values() if s)
        if answers.total() >= SAMPLE or max(answers.values(), default=0) > SAMPLE / 2:  # decided: stop early
            break
    return result
