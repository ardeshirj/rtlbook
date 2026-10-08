# Words below are everyday Persian words, chosen for these tests (no book text).
from rtlbook.suggest import Lexicon, normalize, skeleton


def test_normalize_and_skeleton():
    assert normalize("كتاب‌ها،") == "کتابها"  # Arabic ك, half-space and comma dropped
    assert normalize("خانهٔ") == "خانه"
    # Letters that differ only in dots share a shape
    assert skeleton("بیت") == skeleton("نیت") == skeleton("تبت")
    assert skeleton("گل") == skeleton("کل")
    assert skeleton("دست") != skeleton("رست")


def test_wrong_dots_suggest_the_real_word():
    lex = Lexicon.build(["زیبا", "کتاب", "نان"], ["گفتن"])
    assert lex.suggest("ریبا")[0] == "زیبا"  # ز read as ر
    assert lex.suggest("کتات")[0] == "کتاب"  # ب read as ت
    assert lex.suggest("کفتن")[0] == "گفتن"  # گ read as ک


def test_one_shape_added_dropped_or_changed():
    lex = Lexicon.build(["کتاب"])
    assert "کتاب" in lex.suggest("کتب")  # a tooth missing
    assert "کتاب" in lex.suggest("کتابب")  # an extra tooth
    assert lex.suggest("کتاب") == []  # a known word doesn't suggest itself
    assert lex.suggest("،") == []  # no letters


def test_common_words_and_the_books_words_rank_first():
    # بار and نار share a shape: the common one first, then the one the book uses often
    assert Lexicon.build(["بار"], ["نار"]).suggest("تار")[0] == "بار"
    book = ["نار"] * 2 + ["بار"]
    assert Lexicon.build([], ["بار", "نار"], book).suggest("تار")[0] == "نار"
    # Seen often enough in the book, a word counts as known even when no list has it
    assert Lexicon.build([], [], ["شهرزاد"] * 3).known("شهرزاد")


def test_known_joined_words():
    lex = Lexicon.build(["از", "یک", "خانه"])
    assert lex.known("ازیک")  # two common words printed joined
    assert lex.known("بخانه")  # ب joined to its word
    assert not lex.known("ازیکی")
