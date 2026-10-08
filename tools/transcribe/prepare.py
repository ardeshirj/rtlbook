"""Prepare pages of a book for line transcription (ground truth and training lines for fine-tuning Tesseract).

For each page: render, OCR with word boxes, crop every text line from the unbinarized page, and flag words that
are uncertain (low confidence, or not in the word lists) with dot-aware suggestions. Writes <out>/lines.json and
<out>/<id>.png; a checking tool then writes <id>.gt.txt next to each image (the tesstrain layout). The format:
docs/TRAINING-DATA.md. Re-running for a page replaces its OCR and crops; checked text (.gt.txt, review.json) is kept.

Run in the container from the repo root, e.g.:
  python tools/transcribe/prepare.py input/book.pdf --pages 40,86-87 --split test \\
      --out output/poc/35-period-type/lines --common dict/common.txt --more dict/more.txt \\
      --source "first printing, 1963" --public-domain no
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from rtlbook import ocr, pdf, preprocess  # noqa: E402
from rtlbook.suggest import Lexicon, normalize  # noqa: E402
from rtlbook.text import normalize_text, persian_digits  # noqa: E402

RULES = 1  # version of the transcription rules shown on the page (index.html); stored with every line
FLAG_CONF = 60  # words OCR'd below this confidence are flagged even when they are real words
GAP_SPLIT = 2.5  # a gap wider than this many word heights splits a line (page number and running title)
MIN_LINE_H = 12  # px at 300 dpi: shorter "lines" are specks
WORD_CHARS = re.compile(r"[؀-ۿ0-9۰-۹]")


def page_numbers(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += range(int(a), int(b or a) + 1)
    return out


def clean(word: str) -> str:
    return normalize_text(persian_digits(word))


def crop_box(words: list[ocr.Word], width: int, height: int) -> tuple[int, int, int, int]:
    x0, x1 = min(w.x0 for w in words), max(w.x1 for w in words)
    y0, y1 = min(w.y0 for w in words), max(w.y1 for w in words)
    pad_y, pad_x = max(8, (y1 - y0) // 6), 16
    return max(0, x0 - pad_x), max(0, y0 - pad_y), min(width, x1 + pad_x), min(height, y1 + pad_y)


def split_at_gaps(words: list[ocr.Word]) -> list[list[ocr.Word]]:
    """Words are in reading order (right to left): split where the gap to the next word is very wide."""
    height = sorted(w.y1 - w.y0 for w in words)[len(words) // 2]
    parts = [[words[0]]]
    for prev, w in zip(words, words[1:]):
        if prev.x0 - w.x1 > GAP_SPLIT * height:
            parts.append([])
        parts[-1].append(w)
    return parts


def match_key(text: str) -> str:
    return normalize(text) + "".join(c for c in persian_digits(text) if c.isdigit())


def prefill(lines: list[str], text: str) -> str | None:
    """The checked transcription line that best matches an OCR line, if one is close enough."""
    key = match_key(text)
    if not key:
        return None
    best = max(((SequenceMatcher(None, key, match_key(t), autojunk=False).ratio(), t) for t in lines),
               default=(0.0, None))
    return best[1] if best[0] >= 0.6 else None


def overlap(a, b) -> float:
    """Intersection over union of two boxes (x0, y0, x1, y1)."""
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    inter = max(0, w) * max(0, h)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def carry_over(out: Path, old: list[dict], new: list[dict]) -> None:
    """Keep what was already checked on re-prepared pages. Lines are matched by position on the page (their
    numbers may change); a checked line whose crop changed must be checked again, starting from its saved text."""
    review_path = out / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
    saved_old = [o for o in old if o["id"] in review]
    for o in saved_old:  # take them all out, then put back under the new ids
        (out / f"{o['id']}.gt.txt").unlink(missing_ok=True)
    taken, kept, changed = set(), 0, 0
    entries = {o["id"]: review.pop(o["id"]) for o in saved_old}
    for ln in new:
        score, o = max(((overlap(o["box"], ln["box"]), o) for o in saved_old
                        if o["page"] == ln["page"] and o["id"] not in taken), default=(0.0, None), key=lambda t: t[0])
        if score < 0.5:
            continue
        taken.add(o["id"])
        saved = entries[o["id"]]
        if all(abs(a - b) <= 4 for a, b in zip(o["box"], ln["box"])):
            review[ln["id"]] = saved
            if saved["status"] == "done":
                (out / f"{ln['id']}.gt.txt").write_text(saved["text"] + "\n", encoding="utf-8")
            kept += 1
        else:
            ln["recheck"] = saved
            if saved["status"] == "done":
                ln["start"], ln["prefilled"] = saved["text"], False
            changed += 1
    lost = len(saved_old) - kept - changed
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"checked lines: {kept} kept, {changed} to check again (new crop), {lost} with no matching line")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", required=True, help="e.g. 12,20-24")
    ap.add_argument("--split", required=True, choices=["train", "test"], help="test pages never go into training")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--common", type=Path, required=True, help="word list of common words (one per line)")
    ap.add_argument("--more", type=Path, help="a larger word list")
    ap.add_argument("--book", type=Path, help="the book's convert work folder, for word counts")
    ap.add_argument("--prefill", help="checked text per page to start from, e.g. 'gt/p{n}.txt'")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--lang", default="fas")
    ap.add_argument("--psm", type=int, default=4)
    ap.add_argument("--source", help="the edition, e.g. 'first printing, Tehran 1932' (kept once set)")
    ap.add_argument("--public-domain", choices=["yes", "no"],
                    help="whether the source edition is public domain everywhere (kept once set)")
    args = ap.parse_args()

    book_words = []
    if args.book:
        for f in sorted((args.book / "pages").glob("*.json")):
            book_words += [w for ln in json.loads(f.read_text())["lines"] for w in ln["text"].split()]
    more = args.more.read_text(encoding="utf-8").split() if args.more else []
    lex = Lexicon.build(args.common.read_text(encoding="utf-8").split(), more, book_words)

    args.out.mkdir(parents=True, exist_ok=True)
    index_path = args.out / "lines.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {"book": args.pdf.name, "lines": []}
    if args.source:
        index["source"] = args.source
    if args.public_domain:
        index["public_domain"] = args.public_domain == "yes"
    pages = page_numbers(args.pages)
    kept = [ln for ln in index["lines"] if ln["page"] not in pages]
    doc = pdf.open_book(args.pdf)
    new = []
    for n in pages:
        img = pdf.render(doc, n - 1, args.dpi)
        for old_png in args.out.glob(f"p{n:03d}-*.png"):
            old_png.unlink()
        checked = []
        if args.prefill and (p := Path(args.prefill.format(n=n))).exists():
            checked = [t for t in p.read_text(encoding="utf-8").splitlines() if t.strip()]
        found = 0
        segments = []  # keep marks without letters (- « *) so the crop includes them; drop parts with no letters
        for line in ocr.ocr_words(preprocess.prepare(img), args.lang, args.psm):
            segments += [part for part in split_at_gaps(line) if any(WORD_CHARS.search(w.text) for w in part)]
        for words in segments:
            if max(w.y1 for w in words) - min(w.y0 for w in words) < MIN_LINE_H:
                continue
            found += 1
            line_id = f"p{n:03d}-{found:02d}"
            box = crop_box(words, img.width, img.height)
            img.crop(box).save(args.out / f"{line_id}.png")
            items = []
            for w in words:
                t = clean(w.text)
                flag = w.conf < FLAG_CONF or (bool(normalize(t)) and not lex.known(t))
                items.append({"t": t, "conf": round(w.conf), "x0": w.x0 - box[0], "x1": w.x1 - box[0],
                              "y0": w.y0 - box[1], "y1": w.y1 - box[1], "flag": flag,
                              "sugg": lex.suggest(t) if flag else []})
            text = " ".join(it["t"] for it in items)
            start, hint = prefill(checked, text) if checked else None, None
            if start:
                start = " ".join(clean(t) for t in start.split())
                if len(start.split()) != len(items):  # the checked line also covers words OCR missed: hint only
                    start, hint = None, start
            new.append({"id": line_id, "page": n, "split": args.split, "rules": RULES, "box": box,
                        "ocr": text, "start": start or text, "prefilled": bool(start), "hint": hint,
                        "words": items})
        print(f"page {n}: {found} lines, {sum(w['flag'] for ln in new if ln['page'] == n for w in ln['words'])} "
              f"flagged words")
    carry_over(args.out, [ln for ln in index["lines"] if ln["page"] in pages], new)
    index["lines"] = sorted(kept + new, key=lambda ln: (ln["split"] != "test", ln["page"], ln["id"]))
    index = {k: index[k] for k in ("book", "source", "public_domain") if k in index} | {"lines": index["lines"]}
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(index['lines'])} lines in {index_path}")


if __name__ == "__main__":
    main()
