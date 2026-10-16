# Words below are everyday Persian words, chosen for these tests (no book text).
import os
from pathlib import Path

import pytest
from PIL import Image

from rtlbook.bidi import get_display
from rtlbook.readers import ParisaOCR, _canonical, _reading_order_words

ZWNJ, PLACEHOLDER = "‌", "¦"


def display(text: str) -> str:
    """A line as a line reader sees it, left to right, with ZWNJ written as the model writes it."""
    return get_display(text.replace(ZWNJ, PLACEHOLDER), base_dir="R")


def test_display_order_back_to_reading_order():
    line = "من به خانه رفتم"
    words = _reading_order_words(display(line), [0.9] * len(line), PLACEHOLDER)
    assert " ".join(w for w, _ in words) == line
    assert all(c == 90.0 for _, c in words)


def test_numbers_latin_and_half_spaces_keep_their_order():
    # a line with more Latin than Persian letters reads left to right (ParisaOCR's rule): here Persian leads
    for line in ("سال ۱۳۱۱ بود", "این کتاب خوب (Hedayat) را دیدم", "می" + ZWNJ + "رفتم"):
        assert " ".join(w for w, _ in _reading_order_words(display(line), [1.0] * len(line), PLACEHOLDER)) == line
    assert _reading_order_words("Page 12", [1.0] * 7, PLACEHOLDER) == [("Page", 100.0), ("12", 100.0)]


def test_word_confidence_is_its_letters_mean():
    line = "از در"
    confs = [0.5, 1.0, 1.0, 1.0, 1.0]  # display order: the last word read first, left to right
    words = _reading_order_words(display(line), confs, PLACEHOLDER)
    assert [w for w, _ in words] == ["از", "در"]
    assert words[1][1] == 75.0


def test_canonical_letters():
    assert _canonical("كتاب علي") == "کتاب علی"  # Arabic kaf and yeh
    assert _canonical("سال ١٣١١") == "سال ۱۳۱۱"  # Arabic-Indic digits
    assert _canonical("  خانه" + ZWNJ + " ") == "خانه"


def test_confidence_on_tesseracts_scale():
    assert ParisaOCR.tesseract_scale(99.0) == 90.0
    assert ParisaOCR.tesseract_scale(97.0) == 70.0
    assert ParisaOCR.tesseract_scale(80.0) == 0.0


MODEL = Path(os.environ.get("RTLBOOK_MODELS", "/opt/models")) / "parisaocr" / "parisaocr.onnx"


@pytest.mark.skipif(not MODEL.exists(), reason="ParisaOCR's model is in rtlbook's image")
def test_a_blank_line_reads_as_nothing():
    reader = ParisaOCR()
    assert reader.read(Image.new("L", (600, 60), 255)) == ("", None)
    assert reader.read(Image.new("L", (1, 400), 255)) == ("", None)  # too narrow to scale
