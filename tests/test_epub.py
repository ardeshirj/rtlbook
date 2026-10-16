# Made-up Persian text (no book text).
import zipfile

from rtlbook.epub import ENGINE_VOCAB, BookMeta, write_epub
from rtlbook.model import Paragraph, Section


def opf(path):
    with zipfile.ZipFile(path) as z:
        return z.read("OEBPS/content.opf").decode("utf-8")


def test_the_package_says_how_the_book_was_made(tmp_path):
    sections = [Section("فصل یک", [Paragraph(["من به خانه رفتم."])])]
    engine = {"version": "0.7.0", "document": "scan", "lines_found_by": "tesseract 5.3.0 fas",
              "read_by": "parisaocr fa-0.1 onnx"}
    write_epub(tmp_path / "a.epub", BookMeta("کتاب", "نویسنده", engine=engine), sections)
    text = opf(tmp_path / "a.epub")
    assert f'prefix="rtlbook: {ENGINE_VOCAB}"' in text
    assert '<meta property="rtlbook:read-by">parisaocr fa-0.1 onnx</meta>' in text
    assert '<meta property="rtlbook:lines-found-by">tesseract 5.3.0 fas</meta>' in text

    write_epub(tmp_path / "b.epub", BookMeta("کتاب", "نویسنده"), sections)
    assert "rtlbook:" not in opf(tmp_path / "b.epub")  # nothing said, no prefix declared
