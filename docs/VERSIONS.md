# Versions

rtlbook has one version number, which `rtlbook version` prints. Each release is a git tag named `vX.Y.Z`.

## When the version changes

- **A new middle number** (0.5.0 → 0.6.0) for a change in what rtlbook produces or how it's used: a new kind of
  book supported, a change to the EPUB, a command or option added, removed or renamed.
- **A new last number** (0.5.0 → 0.5.1) for a fix that doesn't change any of that.
- **No change** for docs, experiments and the training tools (`tools/transcribe/`).

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

### 0.5.0 (not tagged yet)
The first tagged version.
- **EPUB 3 is the only output**, made for reading systems built on Readium, such as Thorium Reader. The `kfx`
  command and calibre are gone: converting for a device (Kindle, Kobo) is out of scope.
- **Exported Persian PDFs** convert end to end; scans convert with more errors and aren't supported yet.
- The status is early, no longer a proof of concept.
