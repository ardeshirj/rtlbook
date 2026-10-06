from rtlbook import pdf
from rtlbook.doctype import document_type, page_kind


def test_column_gaps_split_only_where_they_line_up():
    from rtlbook.ocr import Word, split_columns

    def line(y, *spans):  # spans right to left (reading order): (x0, x1)
        return [Word(f"w{k}", x0, x1, y, y + 40, 90.0) for k, (x0, x1) in enumerate(spans)]

    verse = [line(100 * n, (900, 1000), (780, 880), (300, 400), (180, 280)) for n in range(4)]
    assert [len(part) for part in split_columns(verse)] == [2] * 8  # each couplet -> two half-lines
    prose = [line(100 * n, (900, 1000), (780, 880), (660, 760), (540, 640)) for n in range(4)]
    prose[1] = line(100, (900, 1000), (650, 880), (300, 620), (180, 280))  # one loose line
    assert [len(part) for part in split_columns(prose)] == [4] * 4


def test_document_type_follows_most_pages():
    exported = pdf.PageInfo(1, image_area=0.05, script_chars=1500)
    scanned = pdf.PageInfo(2, image_area=1.0, image_dpi=150)
    dt = document_type([page_kind(exported)] * 3 + [page_kind(scanned)])
    assert dt.kind == "exported" and dt.supported
    dt = document_type([page_kind(exported)] + [page_kind(scanned)] * 9)
    assert dt.kind == "scan" and not dt.supported and dt.dpi == 150
    assert "150 dpi" in dt.message() and "Below 200 dpi" in dt.message()
    strips = pdf.PageInfo(3, image_area=0.45)  # scanned strips pasted into a Word page
    illustrated = pdf.PageInfo(4, image_area=0.45, script_chars=1100)  # exported, with a picture
    english_header = pdf.PageInfo(5, image_area=0.3, script_chars=0)  # Persian only in the images
    assert page_kind(strips).kind == "scan" and page_kind(english_header).kind == "scan"
    assert page_kind(illustrated).kind == "exported"
