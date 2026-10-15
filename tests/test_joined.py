# Words below are everyday Persian words, chosen for these tests (no book text).
from rtlbook.joined import Splitter, split_pages
from rtlbook.model import Line, Page

COMMON = ["رفتم", "خانه", "کتاب", "دیدم", "بود", "مدرسه", "پنجره"]


def test_splits_after_a_letter_that_never_joins():
    sp = Splitter.build(COMMON)
    assert sp.fix("ورفتم به خانه") == ("و رفتم به خانه", 1)
    assert sp.fix("کتاب رادیدم") == ("کتاب را دیدم", 1)
    assert sp.fix("«ازمدرسه»،") == ("«از مدرسه»،", 1)  # punctuation stays outside


def test_never_splits_a_known_word_or_inside_a_joined_letter():
    sp = Splitter.build(COMMON + ["دار"], ["دارو"])
    assert sp.fix("دارو") == ("دارو", 0)  # in the large list: never split, though دار + و would be pieces
    assert sp.fix("کتابخانه") == ("کتابخانه", 0)  # ب joins خ: no space can be missing there
    assert sp.fix("می‌رفتم") == ("می‌رفتم", 0)  # a half-space: the reader saw a word with parts


def test_pieces_short_words_and_endings():
    sp = Splitter.build(COMMON + ["دیدار", "ها"])
    assert sp.split_word("دیدارها") is None  # an ending never stands alone, even in the everyday list
    assert sp.split_word("ودر") == ("و", "در")  # short words only from the list of little words
    assert sp.split_word("بودزد") is None  # زد: two letters, not a little word
    assert sp.split_word("بودپنجره") == ("بود", "پنجره")


def test_the_books_frequent_words_are_pieces():
    assert Splitter.build(COMMON).split_word("وشهرزاد") is None
    sp = Splitter.build(COMMON, book_words=["شهرزاد"] * 3)
    assert sp.split_word("وشهرزاد") == ("و", "شهرزاد")
    assert sp.fix("شهرزاد") == ("شهرزاد", 0)


def test_split_pages(tmp_path):
    (tmp_path / "words.txt").write_text("\n".join(COMMON), encoding="utf-8")
    page = Page(1, "ocr", lines=[Line("ورفتم به خانه", (0, 0, 10, 10)), Line("کتاب رادیدم", (0, 20, 10, 30))])
    assert split_pages([page], tmp_path) == 2
    assert [ln.text for ln in page.lines] == ["و رفتم به خانه", "کتاب را دیدم"]
    assert split_pages([page], tmp_path / "none") is None  # no word lists: nothing done
