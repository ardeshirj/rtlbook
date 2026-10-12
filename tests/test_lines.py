import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rtlbook import __version__, lines
from rtlbook.cli import app
from rtlbook.ocr import Word

TOMORROW = Path(__file__).parents[1] / "input" / "public-domain" / "tomorrow-2006.pdf"  # not committed


def test_page_numbers():
    assert lines.page_numbers("3,7-9,12") == [3, 7, 8, 9, 12]


def test_split_at_gaps_parts_a_running_title_from_the_page_number():
    w = lambda x0, x1: Word("…", x0, x1, 0, 40, 90)  # noqa: E731
    words = [w(900, 1000), w(800, 890), w(100, 140)]  # right to left; the last one far away
    assert [len(p) for p in lines.split_at_gaps(words)] == [2, 1]


def test_prefill_picks_the_closest_checked_line():
    checked = ["سلام دنیا", "روز خوبی بود"]
    assert lines.prefill(checked, "روز خوبي بود") == "روز خوبی بود"
    assert lines.prefill(checked, "چیزی دیگر") is None


def test_options_are_checked(tmp_path):
    words = tmp_path / "words.txt"
    words.write_text("سلام\n", encoding="utf-8")
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    result = CliRunner().invoke(app, ["lines", str(pdf), "--pages", "1", "--split", "both", "--out",
                                      str(tmp_path / "set"), "--common", str(words)])
    assert result.exit_code == 2


@pytest.mark.skipif(not TOMORROW.exists() or not shutil.which("tesseract"), reason="needs the PDF in input/ and Tesseract")
def test_lines_cuts_a_page_and_records_the_engine(tmp_path):
    words = tmp_path / "words.txt"
    words.write_text("و\nکه\nاز\n", encoding="utf-8")
    out = tmp_path / "set"
    result = CliRunner().invoke(app, ["lines", str(TOMORROW), "--pages", "3", "--split", "test", "--out", str(out),
                                      "--common", str(words), "--source", "2006", "--public-domain", "no"])
    assert result.exit_code == 0, result.output
    index = json.loads((out / "lines.json").read_text(encoding="utf-8"))
    assert index["engine"] == __version__ and index["public_domain"] is False and index["source"] == "2006"
    assert index["lines"] and all(ln["split"] == "test" and ln["rules"] == lines.RULES for ln in index["lines"])
    assert all((out / f"{ln['id']}.png").exists() for ln in index["lines"])
