import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rtlbook.cli import app

TOMORROW = Path(__file__).parents[1] / "input" / "Hedayat-Tomorrow.pdf"  # public domain; not committed


@pytest.mark.skipif(not TOMORROW.exists() or not shutil.which("tesseract"), reason="needs the PDF in input/ and Tesseract")
def test_convert_reports_progress_as_json_lines(tmp_path):
    result = CliRunner().invoke(app, ["convert", str(TOMORROW), "--pages", "2-3", "--progress", "json",
                                      "-o", str(tmp_path / "book.epub"), "-j", "2"])
    events = [json.loads(line) for line in result.stderr.splitlines() if line.startswith("{")]
    assert events[0] == {"event": "start", "pages": 2, "document": "exported"}
    pages = [e for e in events if e["event"] == "page"]
    assert [e["done"] for e in pages] == [1, 2] and {e["page"] for e in pages} == {2, 3}
    assert all(e["total"] == 2 for e in pages)
    assert events[-1]["event"] == "done" and events[-1]["ok"] is True
    assert Path(events[-1]["epub"]).exists()
