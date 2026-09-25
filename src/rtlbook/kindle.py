"""Kindle outputs, built locally (nothing is uploaded to Amazon).

Kindle devices cannot open EPUB. Two sideloadable formats:
- AZW3 (KF8): Calibre's ebook-convert. Old rendering engine; laggy for Persian.
- KFX: Kindle's current engine with Persian reflow support. Kindle Previewer (macOS/Windows
  only, so it runs on the host via ./rtlbook) turns the EPUB into a KPF, and the KFX Output
  calibre plugin in this container packages the KPF as a .kfx.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

IMAGE_CALIBRE_CONFIG = Path("/opt/calibre-config")  # plugin installed at image build time


def to_azw3(epub: Path, out: Path) -> tuple[bool, str]:
    exe = shutil.which("ebook-convert")
    if not exe:
        return False, "ebook-convert not found (image built with WITH_CALIBRE=0?)"
    proc = subprocess.run(
        [
            exe, str(epub), str(out),
            "--no-inline-toc",  # the EPUB nav/NCX already provides the Kindle TOC
            "--output-profile", "kindle_pw3",
        ],
        capture_output=True, text=True,
    )
    return proc.returncode == 0 and out.exists(), (proc.stdout + proc.stderr).strip()


def _calibre_env() -> dict[str, str]:
    """calibre writes to its config dir at runtime; use a writable copy of the image's."""
    env = dict(os.environ)
    if "CALIBRE_CONFIG_DIRECTORY" not in env:
        cfg = Path(os.environ.get("HOME", "/tmp")) / "calibre-config"
        if not cfg.exists() and IMAGE_CALIBRE_CONFIG.exists():
            shutil.copytree(IMAGE_CALIBRE_CONFIG, cfg)
        env["CALIBRE_CONFIG_DIRECTORY"] = str(cfg)
    return env


def kpf_to_kfx(kpf: Path, out: Path, book: bool = True) -> tuple[bool, str]:
    exe = shutil.which("calibre-debug")
    if not exe:
        return False, "calibre-debug not found (image built with WITH_CALIBRE=0?)"
    # -b: file under "Books" in the Kindle library; -d: personal document ("Docs")
    cmd = [exe, "-r", "KFX Output", "--", "-b" if book else "-d", str(kpf), str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=_calibre_env())
    log = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0 and out.exists() and "Successfully converted" in log, log
