# Training data: checked text lines

The format of rtlbook's training data: line images cut from scanned pages, the OCR's reading of each, and the
text a person checked against the image. It's the ground truth for measuring OCR and for fine-tuning Tesseract
(the [tesstrain](https://github.com/tesseract-ocr/tesstrain) layout: `<id>.png` next to `<id>.gt.txt`).

rtlbook makes the lines (`tools/transcribe/prepare.py`) and trains on the checked ones; it has no checking tool of
its own. Push and pull (`tools/transcribe/bucket`; the bucket and its key in `training.env`, from
`training.env.example`) copy a set to and from an S3 bucket, where any program can be the checking tool: it reads
the files below and writes the decisions. The bucket is private: it keeps sets for checking and training, public
domain or not. Whether a set may also be published is its `public_domain` field, set before the first push.

Format version 1. New fields may be added at any time, so readers must ignore fields they don't know; renaming or
removing a field, or changing what one means, raises the version.

## A set

A set is one folder (or one prefix in a bucket, `<set>/`) of lines from one book. Set names are lowercase letters,
digits and `-`. The book's pages themselves are never part of a set, only the line crops.

| File | Written by | What it is |
|---|---|---|
| `lines.json` | `prepare.py` | the lines: where each was cut, what OCR read, the uncertain words |
| `<id>.png` | `prepare.py` | the line image, cut from the unbinarized page at the render resolution (300 dpi) |
| `examples.json` | a person, optional | crops of this book that illustrate the rules (below) |
| `<id>.gt.txt` | the checking tool | the checked text, only for lines marked `done` |
| decisions | the checking tool | the latest decision per line and every save ever made (below) |

Line IDs are `p<page, 3 digits>-<line on the page, 2 digits>`, e.g. `p028-04`, counted top to bottom in reading
order. Re-preparing a page renumbers its lines; `prepare.py` carries over the decisions by position on the page.

## lines.json

```json
{
  "book": "book.pdf",
  "source": "first printing, Tehran 1932",
  "public_domain": true,
  "lines": [
    {
      "id": "p028-04", "page": 28, "split": "test", "rules": 1,
      "box": [410, 1210, 2160, 1290],
      "ocr": "…", "start": "…", "prefilled": false, "hint": null,
      "words": [
        {"t": "…", "conf": 91, "x0": 1580, "x1": 1734, "y0": 12, "y1": 70, "flag": false, "sugg": []}
      ]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `book` | the source file's name |
| `source` | optional: the edition the scan is of (printing, place, year) |
| `public_domain` | optional: `true` when that edition is public domain everywhere, so the set's lines may be published; `false` or missing: keep the set private |
| `id`, `page` | the line ID; the page number in the PDF, from 1 |
| `split` | `train` or `test`. Test lines measure the OCR and must never be used for training. |
| `rules` | the version of the transcription rules (below) the line is to be checked under |
| `box` | where the crop was cut from the page: `[x0, y0, x1, y1]` in page pixels |
| `ocr` | what OCR read, words joined by spaces |
| `start` | the text the checking tool starts from: the OCR, or a checked transcription that matched (`prefilled`) |
| `prefilled` | `start` came from an earlier checked transcription rather than the OCR |
| `hint` | a checked transcription that matched but has a different number of words: shown, not used as `start`; or `null` |
| `recheck` | optional: the decision saved for this line before its crop changed; check it again |
| `words` | OCR's words, in reading order (right to left) |
| `words[].t` | the word as read, normalized (Persian letters and digits) |
| `words[].conf` | OCR confidence, 0–100 |
| `words[].x0` … `y1` | the word's box in the line image's pixels |
| `words[].flag` | uncertain: low confidence, or not in the word lists |
| `words[].sugg` | for flagged words: real words that look like it (mostly the same letters with other dots), best first |

## examples.json

Optional: real crops that show each rule in this book's type, keyed by the rule's example name.

```json
{"joined-prefix": {"line": "p107-08", "x0": 392, "x1": 563, "type": "…", "dont": "…"}}
```

`line` is the line whose image holds the example, `x0`/`x1` the part to show, `type` and `dont` the right and
wrong way to type it. The names used by rule version 1: `joined-prefix`, `joined-preposition`, `old-spelling`,
`gap`, `joined`, `half-space`, `dash`, `comma`, `question`, `quotes`, `hamza`, `arabic-letters`, `page-number`.

## Decisions

A decision is `{"status", "text", "saved"}`, and optionally `"by"`:

| `status` | Meaning | `<id>.gt.txt` |
|---|---|---|
| `done` | the text is exactly what's printed on the line | written: the text and a newline |
| `unsure` | a best guess; at least one word can't be read for certain | removed |
| `skip` | the image can't be used (not one line of printed text) | removed |

`text` has single spaces between words (half-spaces, U+200C, are kept as typed); `saved` is the time of the save
(ISO 8601: UTC ending in `Z`, or local time in sets checked before this format); `by` names who checked the line,
for a tool used by several people. Only `done` lines go into training or testing. Leave `by` out of a set that is
published.

| File | What it is |
|---|---|
| `review.json` | the latest decision per line: `{"<id>": decision}` |
| `saves.jsonl` (folder) or `saves/<time>-<id>.json` (bucket) | every save, `{"id", …decision}`, never changed: the history. A bucket can't add to a file, so there each save is a file of its own; `<time>` is `saved` as `20261008T093000.000Z`, so the names sort in order. |

`review.json` can always be rebuilt from the history (the last save of each line). A checking tool writes one save
at a time, so `review.json` is never written by two at once.

Push never sends decisions, so whatever was checked in the bucket stays as it is; the exception is the first push of
a set checked before it had a bucket (no `review.json` there yet), which sends its `review.json` and turns
`saves.jsonl` into `saves/`. Pull brings back `review.json` and the `.gt.txt` files (and removes those of lines no
longer `done`), and writes `saves.jsonl` from `saves/`.

## Transcription rules, version 1

Type exactly what is printed on the line:

1. **What is printed on this line, nothing more.** Keep the book's spelling, even old-fashioned or wrong: a joined
   verb prefix (میرفت, not می‌رفت), a preposition joined to its word (بخانه), the old spelling with ئ (جائی), a
   misprint as printed. Don't add words that aren't in the image, such as a page number OCR missed.
2. **Spaces as printed.** A visible gap is a space (سر گردان); letters that connect are typed joined (کتابها); two
   parts close together but not connected get a half-space, U+200C (کتاب‌ها).
3. **Every printed mark, and only those**, in Persian forms: dashes as `-`, three dots as `...`, Persian comma ،,
   question mark ؟ and quotes « », a footnote asterisk where it's printed, a small hamza over ه only where printed
   (خانهٔ), no tanvin unless printed. Persian ی and ک for Arabic-style ي and ك; Persian digits (۱۲, not 12 or ١٢).
4. **Can't use (`skip`)** when the image holds anything other than printed text of this one line: an ornament line,
   a speck read as a letter or digit, a stamp, a reader's notes or underlining, a crop that cuts the line, two
   lines in one image.
5. **Unsure (`unsure`)** when a word can't be read for certain: type the best guess.

A change to these rules that changes what a checked line would contain raises the version; `prepare.py` stamps it
on new lines (`RULES`), so lines checked under different rules can be told apart.
