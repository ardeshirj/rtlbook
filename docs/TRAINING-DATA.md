# Training data: checked text lines

The format of rtlbook's training data: line images cut from scanned pages, the OCR's reading of each, and the
text a person checked against the image. It's the ground truth for measuring OCR and for fine-tuning Tesseract
(the [tesstrain](https://github.com/tesseract-ocr/tesstrain) layout: `<id>.png` next to `<id>.gt.txt`).

rtlbook makes the lines (`rtlbook lines`) and trains on the checked ones, from folders; it has no
checking tool of its own, and no tool to copy sets anywhere. A set can also be kept in an S3 bucket, one prefix per
set laid out as below, where any program can be the checking tool: it reads the files below and writes the
decisions. Keep such a bucket private, since it holds sets for checking and training, public domain or not. Whether
a set may also be published is its `public_domain` field, set before the set is first shared.

Format version 1. New fields may be added at any time, so readers must ignore fields they don't know; renaming or
removing a field, or changing what one means, raises the version.

## A set

A set is one folder (or one prefix in a bucket, `<set>/`) of lines from one book. Set names are lowercase letters,
digits and `-`. The book's pages themselves are never part of a set, only the line crops.

| File | Written by | What it is |
|---|---|---|
| `lines.json` | `rtlbook lines` | the lines: where each was cut, what OCR read, the uncertain words |
| `<id>.png` | `rtlbook lines` | the line image, cut from the unbinarized page at the render resolution (300 dpi) |
| `<id>.gt.txt` | the checking tool | the checked text, only for lines marked `done` |
| `<id>.agreed.txt` | freeze, in a version only | the text two independent readings agreed on, for a line nobody checked (status `agreed`, below) |
| decisions | the checking tool | the latest decision per line and every save ever made (below) |
| `.pulled` | pull, in a folder only | the fingerprint of the bucket's decisions at the last pull, so push can tell whether the folder is up to date (below) |
| `summary.json` | the bucket tool, in a bucket, optional | what a list of sets needs, so it doesn't read every `lines.json`: `book`, `source`, `public_domain`, `lines` (how many), `test` (how many in the test split), `recheck` (the ids with a `recheck` field), `rules` (the rules' versions its lines are stamped with, oldest first), and optionally `title`, `title_en`, `author`, `edition` from a record of the book kept with the set; written again with every `lines.json`. Decisions aren't counted here: they're in `review.json` |
| `index.json`, `pages/p<NNN>.json` | the bucket tool, in a bucket, optional | for a checking tool that loads a set a page at a time: `index.json` has every line in brief (`id`, `page`, `split`, `recheck`, and how readers of the line compared, if any), `pages/` each page's lines in full as in `lines.json`, with any readings of them; built from `lines.json` and written again with it. Training and testing never read them |
| `frozen.json`, `versions/` | freeze, in a bucket | a finished set's numbered versions, and while `frozen.json` is there, read-only ("Frozen versions", below) |

Line IDs are `p<page, 3 digits>-<line on the page, 2 digits>`, e.g. `p028-04`, counted top to bottom in reading
order. Cutting a page again renumbers its lines; `rtlbook lines` carries over the decisions by position on the page.

## lines.json

```json
{
  "book": "book.pdf",
  "source": "first printing, Tehran 1932",
  "public_domain": true,
  "engine": "0.6.0",
  "lines": [
    {
      "id": "p028-04", "page": 28, "split": "test", "rules": 2,
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
| `engine` | the rtlbook version that cut the lines last (`rtlbook version`); missing in sets cut before 0.6.0 |
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

## Decisions

A decision is `{"status", "text", "saved"}`, and optionally `"by"`:

| `status` | Meaning | `<id>.gt.txt` |
|---|---|---|
| `done` | the text is exactly what's printed on the line | written: the text and a newline |
| `unsure` | a best guess; at least one word can't be read for certain | removed |
| `skip` | the image can't be used (not one line of printed text) | removed |
| `agreed` | not checked by a person: two independent readings agreed (only in a frozen version, `"by": "agreement"`) | none; the text is in `<id>.agreed.txt` |

`text` has single spaces between words (half-spaces, U+200C, are kept as typed); `saved` is the time of the save
(ISO 8601: UTC ending in `Z`, or local time in sets checked before this format); `by` names who checked the line,
for a tool used by several people. Only `done` lines go into training or testing, unless a training run chooses
to add `agreed` ones (never testing: test lines are always checked by a person). Leave `by` out of a set that is
published.

| File | What it is |
|---|---|
| `review.json` | the latest decision per line: `{"<id>": decision}` |
| `saves.jsonl` (folder) or `saves/<time>-<id>.json` (bucket) | every save, `{"id", …decision}`, never changed: the history. A bucket can't add to a file, so there each save is a file of its own; `<time>` is `saved` as `20261008T093000.000Z`, so the names sort in order. |

`review.json` can always be rebuilt from the history (the last save of each line). A checking tool writes one save
at a time, so `review.json` is never written by two at once.

A tool that copies sets between a folder and a bucket should work like this, so nothing checked is lost. Pull
brings back `review.json` and the `.gt.txt` files (and removes those of lines no longer `done`), writes
`saves.jsonl` from `saves/`, and leaves the bucket's `review.json` fingerprint (its sha256) in the folder's `.pulled`.
Push refuses a folder whose `.pulled` doesn't match the bucket's decisions (lines were checked since its last pull,
or it was never pulled): nothing is sent, so nothing checked is lost. When it matches, push sends the folder's
decisions with the lines, since they're the current ones (`rtlbook lines` renumbers re-cut pages and carries the checked
text over); the history keeps the old numbers. A set's first push sends the folder's decisions too, if it has some
(a set checked before it had a bucket), turning `saves.jsonl` into `saves/`.

## Frozen versions

A finished set (every line decided; a training line two independent readings agreed on, as recorded in `index.json`,
counts as decided and is frozen as `agreed`) is frozen: training and testing use a numbered version of it, never the working
set, so a result can always be traced to exact data. In the bucket:

| File | What it is |
|---|---|
| `versions/v<N>.tar.gz` | the whole set as frozen (lines, images, `.gt.txt`, decisions, history), in a folder `<set>-v<N>/`; the same files give the same bytes |
| `versions/v<N>.manifest.json` | set, version, time, book, source, `public_domain`, rules versions, counts, and per line: `id`, `split`, `rules`, `status`, `by` (`"agreement"` for a line decided at freeze by agreeing readings), and sha256 of its image (`png`) and, when done, its text (`gt`), or when agreed, its `agreed` text |
| `frozen.json` | `{"version", "sha256" (of the archive), "frozen", "counts"}`: the set is frozen at that version |

While `frozen.json` is there the set is read-only: a checking tool must refuse saves, and push refuses the set.
A version never changes: reopening a set removes `frozen.json` so it can be checked again, toward `v<N+1>`, while
`v<N>` stays as it was. Freezing and reopening are the bucket tool's to do.

## Transcription rules, version 3

The aim is to teach OCR to read what's on the page: type what the ink shows, letter by letter, not what the sentence
should say, what's correct today, or what you expect to read. When the print and the "right" word disagree, the
print wins: that's the very case OCR has to learn. Type exactly what is printed on the line:

1. **What is printed on this line, nothing more.** Keep the book's spelling, even old-fashioned or wrong: a joined
   verb prefix (میرفت, not می‌رفت), a preposition joined to its word (بخانه), the old spelling with ئ (جائی), a
   misprint as printed. Don't add words that aren't in the image, such as a page number OCR missed.
2. **Spaces: first the letters, then the words.** Letters that connect are typed joined, even across two words
   (بخانه, کتابها). Where they don't connect, two words always get a space, even when printed with no gap: touching
   isn't joining. ا د ذ ر ز ژ و never join the letter after them, so a word printed right against them is still a new
   word, most often a short one such as با، تا، از، و، را (تا صبح, او را, not تاصبح, اورا; در خانه, not درخانه or
   در‌خانه); when in doubt whether it's one word or two, it's two.
   Within one word (a prefix such as می, a suffix such as ها or تر, the parts of a compound), follow the print: a
   letter that could connect but is printed apart without a gap gets a half-space, U+200C (کتاب‌ها); a letter that
   never connects needs nothing (دیوارها); a clear gap is a space (می رفت).
3. **Every printed mark, and only those**, in Persian forms: dashes as `-`, three dots as `...`, Persian comma ،,
   question mark ؟ and quotes « », a footnote asterisk where it's printed, a small hamza over ه only where printed
   (خانهٔ), no tanvin unless printed. Persian ی and ک for Arabic-style ي and ك; Persian digits (۱۲, not 12 or ١٢).
   A mark sits against its word, whatever gap the type leaves: no space before `.` `،` `؛` `:` `؟` `!` `»` or a dash
   that breaks a word at the line's end (می-), none after `«`, and a speech dash against the `:` or `«` before it
   (`گفت:- نه`, `«- نه`). A gap there is typesetting, not spelling. A dash between words inside a line keeps the
   print's spacing (`منیژه - اینهم`).
4. **Can't use (`skip`)** when the image holds no print worth keeping: an ornament line, a speck read as a letter or
   digit, a stamp, a reader's notes or underlining. Nothing is typed, and the line is used nowhere.
5. **Unsure (`unsure`)** when there is print worth keeping but not one line read for certain: a word that can't be
   read for certain (type the best guess), or a crop that holds two lines or cuts a line (type the print it shows, in
   reading order). An unsure line stays out of training and testing; a book built from the set keeps its text.

A change to these rules that changes what a checked line would contain raises the version; `rtlbook lines` stamps it
on new lines (`RULES` in `src/rtlbook/lines.py`), so lines checked under different rules can be told apart.

Since 2026-10-19, a crop with two lines or a cut line that holds print is unsure, with its print typed, not can't use
(rules 4 and 5): neither is trained on, and a book built from the set keeps the print. No line's training text
changes, so the version stays.

Version 3 (2026-10-19) placed the marks: old type often leaves a gap before a mark, and lines had been typed both
ways. Lines already checked were brought to it by removing that space, which changes no letter.

Version 2 (2026-10-12) made rule 2 precise: version 1's "two parts close together but not connected get a
half-space" read as a half-space between two words printed with no gap; they now get a space, and a suffix after a
letter that never connects gets nothing.
