# A made-up set: everyday Persian sentences chosen for these tests (no book text).
import json

import pypdfium2 as pdfium

from rtlbook.fromset import pages


def make_set(tmp_path):
    doc = pdfium.PdfDocument.new()
    for _ in range(2):
        doc.new_page(360, 540)  # points: 1500 x 2250 px at 300 dpi
    doc.save(str(tmp_path / "book.pdf"))
    folder = tmp_path / "my-book-v1"
    folder.mkdir()
    line = lambda i, n, ocr: {"id": f"p{n:03d}-{i:02d}", "page": n, "split": "train", "box": [100, 100 * i, 1400, 100 * i + 80], "ocr": ocr}
    (folder / "lines.json").write_text(json.dumps({"book": "book.pdf", "lines": [
        line(1, 1, "او به خانه رفت"), line(2, 1, "کتاب را دید"), line(3, 1, "۰ ٠"), line(4, 1, "نامه را نوشت"),
        line(5, 1, "فردا میآید"), line(1, 2, "در باز شد")]}, ensure_ascii=False), encoding="utf-8")
    (folder / "review.json").write_text(json.dumps({
        "p001-01": {"status": "done", "text": "او بخانه رفت"},
        "p001-03": {"status": "skip", "text": ""},
        "p001-04": {"status": "unsure", "text": "نامه را نوشت؟"}}, ensure_ascii=False), encoding="utf-8")
    (folder / "p001-01.gt.txt").write_text("او بخانه رفت\n", encoding="utf-8")
    (folder / "p001-02.agreed.txt").write_text("کتاب را دید\n", encoding="utf-8")
    return tmp_path / "book.pdf", folder


def test_each_line_takes_the_sets_text_in_its_place(tmp_path):
    pdf_path, folder = make_set(tmp_path)
    got, sources = pages(folder, pdf_path, [1, 2])
    assert [p.number for p in got] == [1, 2] and (got[0].width, got[0].height) == (1500, 2250)
    assert [ln.text for ln in got[0].lines] == ["او بخانه رفت", "کتاب را دید", "نامه را نوشت؟", "فردا میآید"]
    assert got[0].lines[0].bbox == (100, 100, 1400, 180) and got[0].lines[0].conf == 100.0
    assert sources == {"checked": 1, "agreed": 1, "skip": 1, "unsure": 1, "ocr": 2}  # the skipped line is left out
    assert got[0].settings["set"] == "my-book-v1"


def test_only_the_pages_asked_for(tmp_path):
    pdf_path, folder = make_set(tmp_path)
    got, sources = pages(folder, pdf_path, [2])
    assert [ln.text for p in got for ln in p.lines] == ["در باز شد"] and sources == {"ocr": 1}


def test_a_frozen_manifest_has_the_last_word(tmp_path):
    pdf_path, folder = make_set(tmp_path)
    (folder / "manifest.json").write_text(json.dumps({"lines": [
        {"id": "p001-05", "status": "skip", "by": "agreement"}, {"id": "p001-01", "status": "done"}]}), encoding="utf-8")
    got, sources = pages(folder, pdf_path, [1])
    assert [ln.text for ln in got[0].lines] == ["او بخانه رفت", "کتاب را دید", "نامه را نوشت؟"]
    assert sources["skip"] == 2 and sources["checked"] == 1


def test_an_edition_marks_chapter_starts_and_drops_lines(tmp_path):
    pdf_path, folder = make_set(tmp_path)
    got, sources = pages(folder, pdf_path, [1, 2], edition={"chapters": [{"line": "p002-01"}], "drop": ["p001-0[45]"]})
    assert [ln.text for ln in got[0].lines] == ["او بخانه رفت", "کتاب را دید"]
    assert [ln.heading for ln in got[1].lines] == [True] and not got[0].lines[0].heading
    assert sources["dropped"] == 2


def test_an_edition_changes_the_text_not_the_set(tmp_path):
    pdf_path, folder = make_set(tmp_path)
    ed = {"replace": [{"pattern": r"^او\s*", "with": "«او "}, {"pattern": "رفت$", "with": "رفت»"}]}
    got, sources = pages(folder, pdf_path, [1], edition=ed)
    assert got[0].lines[0].text == "«او بخانه رفت»" and sources["replaced"] == 2
    assert (folder / "p001-01.gt.txt").read_text(encoding="utf-8") == "او بخانه رفت\n"  # the set as it was


def test_a_heading_line_starts_a_chapter():
    from rtlbook.model import Line, Page
    from rtlbook.text import build_paragraphs
    page = Page(1, "ocr", 1500, 2250, [Line("در باز شد", (100, 100, 1400, 180), 100.0, True),
                                       Line("او به خانه رفت و کتاب را دید.", (100, 300, 1400, 380), 100.0)])
    paras = build_paragraphs([page])
    assert [p.heading for p in paras] == [True, False]
