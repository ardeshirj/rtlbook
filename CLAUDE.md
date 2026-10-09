# rtlbook — notes for AI assistants and contributors

rtlbook converts PDF books in right-to-left languages (Persian first) into EPUB 3, its only output, made for
reading systems built on Readium (such as Thorium Reader); device formats (Kindle, Kobo) are out of scope. See
`README.md` for usage; in `docs/`: `DESIGN.md` for the engine's design and dated decisions, `ROADMAP.md` for phases
and planned work, and `LESSONS.md` for troubleshooting.

## Running things
- Everything runs in Docker: build with `make build` (`docker build -f docker/Dockerfile -t rtlbook:dev .`; `make`
  lists the rest: `core`, `core-amd64`, `test`); use the `./rtlbook`
  wrapper (it only shares this repository folder with the container, so inputs go in `input/`).
- Tests: `docker run --rm -v "$PWD":/app -w /app --entrypoint python rtlbook:dev -m pytest -q -p no:cacheprovider tests`
  (with the whole repo mounted, tests that need PDFs in `input/` also run; otherwise they're skipped).

## Conventions
- **No book text in git.** `input/` and `output/` are git-ignored. Tests use made-up Persian sentences. The only real
  book text is public-domain ground truth in `tests/data/`, added only after checking the work is public domain
  everywhere (author died 70+ years ago), and never scans or PDFs.
- **Measure changes to OCR or text handling** with `rtlbook eval` and the ground-truth tests
  (`tests/test_ground_truth.py`); keep or improve the baselines noted in `tests/data/*/README.md`.
- Experiments and their notes go in `output/poc/<NN>-<name>/` (git-ignored); record outcomes worth keeping in
  `DESIGN.md` (engine decisions) or `LESSONS.md` (practical lessons).
- `DESIGN.md` is about the engine only, and only what is built (or dropped). Plans go in `ROADMAP.md`; when an item
  ships, its design moves to `DESIGN.md` and the item leaves the roadmap. Both are public: no service or library plans.
- Prefer simple, general rules over per-PDF special cases; every page is OCR'd (the PDF's own text layer isn't used).
- Small commits with a clear message explaining why.
- **Versions:** one number, in `pyproject.toml` (also `__init__.py` and `uv.lock`; `make bump V=X.Y.Z` sets all
  three). A change in what the engine produces or how it's used gets a new middle number (0.6.0), a fix the last
  one; docs, experiments and the training tools need none. Commit the bump, then `make tag` (tag `vX.Y.Z` with the
  commits since the last tag) and push the tag with the commit.
