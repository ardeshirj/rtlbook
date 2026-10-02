# All Persian sentences below are synthetic, written for these tests (no book text).
from rtlbook.evaluate import compare, normalize, read_text, words
from rtlbook.ganjoor import poem_path

REF = "امروز صبح زود پدرم به باغ رفت و درختان سیب را آب داد"


def test_normalize_hides_spelling_conventions():
    assert words("يك روز ۱۲ كتاب مي‌خواند") == words("یک روز 12 کتاب میخواند")
    assert normalize("كِتابِ خانهٔ") == "کتاب خانه"
    assert normalize("كِتاب", keep_marks=True) == "کِتاب"


def test_identical_text_has_no_errors():
    r = compare(REF, REF)
    assert (r.cer, r.wer, r.word_recall_unordered) == (0, 0, 1)


def test_letter_error_is_counted_and_reported():
    r = compare(REF, REF.replace("پدرم", "بدرم"))
    assert r.char_errors == 1 and r.word_errors == 1
    assert r.confusions[("پ", "ب")] == 1
    assert r.mismatches == [("پدرم", "بدرم")]


def test_joined_words_cost_one_letter_and_two_word_errors():
    r = compare("به خانه رفت", "بخانه رفت")
    assert r.char_errors == 1  # letters only: "بهخانه" vs "بخانه" differ by one "ه"
    assert r.word_errors == 2


def test_reading_order_problem_keeps_word_recall():
    left, right = REF.split(" و ")
    r = compare(REF, right + " و " + left)
    assert r.word_recall_unordered == 1
    assert r.wer > 0.5


def test_line_scores_ignore_line_order_and_extra_lines():
    ref = "یک دو سه چهار\nپنج شش هفت هشت\nنه ده یازده"
    ocr = "نه ده یازده\nپنج شش هفت هشت\nیادداشت پایین صفحه\nیک دو سه چهار"
    r = compare(ref, ocr)
    assert r.cer > 0.3 and r.line_cer == 0 and r.extra_ocr_lines == 1
    assert r.line_pairs == 2 and r.line_order == 0  # reversed: no pair in order


def test_line_order_ignores_extra_lines_between():
    ref = "یک دو سه چهار\nپنج شش هفت هشت\nنه ده یازده"
    r = compare(ref, "یک دو سه چهار\nیادداشت\nپنج شش هفت هشت\nنه ده یازده")
    assert r.line_order == 1


def test_misread_words_at_the_page_start_stay_in_the_trimmed_reference():
    before = "این جمله فقط در متن مرجع آمده است و در صفحه نیست " * 5
    garbled_start = "ابن حمله اول صفحه " + REF  # four misread words, then a clean match
    r = compare(before + "این جمله اول صفحه " + REF, garbled_start)
    assert r.trimmed is not None and r.word_errors <= 3 + 5  # misreads + slack, not the page start


def test_long_reference_is_trimmed_to_the_ocr_part():
    before = "این جمله فقط در متن مرجع آمده است و در صفحه نیست " * 5
    after = " و این یکی هم بعد از صفحه آمده است " * 5
    r = compare(before + REF + after, REF)
    assert r.trimmed is not None
    assert r.ref_words < len(words(before + REF + after))
    assert r.word_errors <= 10  # only the slack words around the match


def test_a_few_missed_words_are_errors_not_trimmed():
    r = compare(REF, " ".join(REF.split()[3:]))
    assert r.trimmed is None and r.word_errors == 3


def test_badly_misread_first_line_of_a_short_page_is_not_trimmed():
    ref = "در غروب سرد پاییز\n" + REF
    r = compare(ref, "دد غرودبی آایدک سرف\n" + REF)
    assert r.trimmed is None and r.ref_words == len(words(ref))


def test_read_text_selects_pages_from_pages_txt():
    txt = "\n===== page 1 [ocr conf=80.0, 1.0s] =====\nیک\n\n===== page 2 [ocr conf=80.0, 1.0s] =====\nدو\n"
    assert read_text(txt, {2}).split() == ["دو"]
    assert read_text("## فصل اول\nمتن").split() == ["فصل", "اول", "متن"]


def test_ganjoor_poem_path():
    assert poem_path("https://ganjoor.net/hafez/ghazal/sh16/") == "/hafez/ghazal/sh16"
    assert poem_path("hafez/ghazal/sh16") == "/hafez/ghazal/sh16"
