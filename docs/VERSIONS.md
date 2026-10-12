# Versions

rtlbook has one version number, which `rtlbook version` prints. Each release is a git tag named `vX.Y.Z`.

## When the version changes

- **A new middle number** (0.5.0 → 0.6.0) for a change in what rtlbook produces or how it's used: a new kind of
  book supported, a change to the EPUB, a command or option added, removed or renamed.
- **A new last number** (0.5.0 → 0.5.1) for a fix that doesn't change any of that.
- **No change** for docs and experiments.

While the version is below 1.0, any release may break how rtlbook is used; the history below says how.

## Where the number is

Three files carry it, and they must agree:

| File | What it's for |
|---|---|
| `pyproject.toml` | The package version, and the one the tag is named from |
| `src/rtlbook/__init__.py` | `__version__`, what `rtlbook version` prints |
| `uv.lock` | The lock file's entry for rtlbook itself; uv rewrites it on the next lock if it disagrees |

`make bump` sets all three, and `make tag` refuses to tag when they differ. Reading the version from the installed
package instead would leave one place to edit, but uv runs only inside the Docker build, so three copies set by one
command are simpler.

## How to release

```bash
make bump V=0.6.0                  # set the version in the three files
# add the version to the history below
git commit -am "…"                 # commit both
make tag NOTE="What changed"       # tag v0.6.0: the note, then the commits since the last tag
git push origin main v0.6.0
```

`make tag` (`tools/release`) only tags a clean `main` with no tag for that version yet, and never pushes.

## History

### 0.6.0 (2026-10-12)
- **`rtlbook lines`** cuts a book's pages into training lines for checking (`docs/TRAINING-DATA.md`): what
  `tools/transcribe/prepare.py` did, now a command released with rtlbook's versions, so a set can be cut by a known
  version. `lines.json` records it (`engine`). `tools/transcribe/prepare.py` is gone.
- **Suggestions come in one order on every run:** words that rank the same are listed alphabetically (they followed
  an order that could change between runs).
- **Transcription rules version 2:** two words printed with no gap get a space (version 1 read as a half-space); the
  aim comes first: type what the ink shows. New lines are stamped `rules: 2`.

### 0.5.0 (2026-10-08)
The first tagged version.
- **EPUB 3 is the only output**, made for reading systems built on Readium, such as Thorium Reader. The `kfx`
  command and calibre are gone: converting for a device (Kindle, Kobo) is out of scope.
- **Exported Persian PDFs** convert end to end; scans convert with more errors and aren't supported yet.
- The status is early, no longer a proof of concept.
