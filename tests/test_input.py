from PIL import Image

from rtlbook import pdf
from rtlbook.classify import classify


def make_folder(tmp_path, names):
    for i, name in enumerate(names):
        Image.new("RGB", (60 + i, 80), "white").save(tmp_path / name)
    return tmp_path


def test_image_folder_natural_order_and_filtering(tmp_path):
    make_folder(tmp_path, ["p10.png", "p2.jpg", "p1.tif", "._p3.png"])
    (tmp_path / "notes.txt").write_text("not a page")
    doc = pdf.open_book(tmp_path)
    assert [f.name for f in doc.files] == ["p1.tif", "p2.jpg", "p10.png"]
    assert len(doc) == 3


def test_image_pages_are_routed_to_ocr_as_grayscale(tmp_path):
    doc = pdf.open_book(make_folder(tmp_path, ["1.png", "2.png"]))
    info = pdf.page_info(doc, 1)
    assert info.number == 2 and info.chars == 0
    assert classify(info).route == "ocr"
    img = pdf.render(doc, 0, dpi=300)
    assert img.mode == "L" and img.size == (60, 80)  # own resolution, dpi ignored


def test_cover_is_first_page_as_jpeg(tmp_path):
    data, media = pdf.largest_image(pdf.open_book(make_folder(tmp_path, ["1.png"])), 0)
    assert media == "image/jpeg" and data[:2] == b"\xff\xd8"


def test_digest_tracks_page_content(tmp_path):
    make_folder(tmp_path, ["1.png", "2.png"])
    before = pdf.digest(tmp_path)
    assert pdf.digest(tmp_path) == before
    Image.new("RGB", (60, 80), "black").save(tmp_path / "2.png")
    assert pdf.digest(tmp_path) != before


def test_empty_folder_is_an_error(tmp_path):
    try:
        pdf.open_book(tmp_path)
    except ValueError as e:
        assert "No page images" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_column_gaps_split_only_where_they_line_up():
    from rtlbook.ocr import Word, split_columns

    def line(y, *spans):  # spans right to left (reading order): (x0, x1)
        return [Word(f"w{k}", x0, x1, y, y + 40, 90.0) for k, (x0, x1) in enumerate(spans)]

    verse = [line(100 * n, (900, 1000), (780, 880), (300, 400), (180, 280)) for n in range(4)]
    assert [len(part) for part in split_columns(verse)] == [2] * 8  # each couplet -> two half-lines
    prose = [line(100 * n, (900, 1000), (780, 880), (660, 760), (540, 640)) for n in range(4)]
    prose[1] = line(100, (900, 1000), (650, 880), (300, 620), (180, 280))  # one loose line
    assert [len(part) for part in split_columns(prose)] == [4] * 4
