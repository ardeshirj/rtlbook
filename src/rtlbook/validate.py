"""EPUB validation via W3C epubcheck."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def epubcheck(path: Path) -> tuple[bool, str]:
    jar = os.environ.get("EPUBCHECK_JAR")
    if not jar or not Path(jar).exists():
        return False, "epubcheck not available (set EPUBCHECK_JAR)"
    proc = subprocess.run(["java", "-Duser.home=/tmp", "-jar", jar, str(path)], capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()
