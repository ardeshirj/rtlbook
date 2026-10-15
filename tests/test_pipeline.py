from rtlbook.pipeline import PAGE, reader_for


def test_reader_by_document_type():
    assert reader_for("auto", "scan") == "tesseract"  # a scan's lines cut and read one by one
    assert reader_for("auto", "exported") == PAGE  # an exported PDF's whole pages in one call
    assert reader_for(PAGE, "scan") == PAGE  # a choice given is kept
    assert reader_for("tesseract", "exported") == "tesseract"
