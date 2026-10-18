from rtlbook.pipeline import PAGE, reader_for


def test_reader_by_document_type():
    assert reader_for("auto", "scan") == "parisaocr"  # a scan's lines cut and read one by one
    assert reader_for("auto", "exported") == PAGE  # an exported PDF's whole pages in one call
    assert reader_for(PAGE, "scan") == PAGE  # a choice given is kept
    assert reader_for("tesseract", "exported") == "tesseract"
    assert reader_for("auto", "scan", "tesseract") == "tesseract"  # --scan-reader: scans only
    assert reader_for("auto", "exported", "tesseract") == PAGE


def test_a_cover_in_strips_is_the_whole_scan():
    import pypdfium2 as pdfium
    from PIL import Image

    from rtlbook import pdf

    doc = pdfium.PdfDocument.new()
    page = doc.new_page(200, 400)  # the scan in strips fills its top 300 points, white paper under it
    for y, colour in ((100, "red"), (250, "blue")):  # two strips, each half the scan
        img = pdfium.PdfImage.new(doc)
        img.set_bitmap(pdfium.PdfBitmap.from_pil(Image.new("RGB", (200, 150), colour)))
        img.set_matrix(pdfium.PdfMatrix().scale(200, 150).translate(0, y))
        page.insert_obj(img)
    page.gen_content()
    data, kind = pdf.largest_image(doc, 0)
    cover = Image.open(__import__("io").BytesIO(data))
    assert kind == "image/jpeg" and cover.size == (round(200 * pdf.COVER_DPI / 72), round(300 * pdf.COVER_DPI / 72))
    assert cover.getpixel((10, 10))[2] > 200 and cover.getpixel((10, cover.height - 10))[0] > 200  # blue on top (PDF y counts up)
