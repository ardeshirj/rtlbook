# Words below are everyday Persian words, chosen for these tests (no book text).
from rtlbook.halfspace import join, join_pages
from rtlbook.model import Line, Page

Z = "‌"


def test_prefixes_and_endings_get_a_half_space():
    assert join("او می رفت") == (f"او می{Z}رفت", 1)
    assert join("نمی دانم") == (f"نمی{Z}دانم", 1)
    assert join("کتاب ها را دیدم") == (f"کتاب{Z}ها را دیدم", 1)
    assert join("بزرگ تر از خانه") == (f"بزرگ{Z}تر از خانه", 1)
    assert join("خانه ام بی صدا بود") == (f"خانه{Z}ام بی{Z}صدا بود", 2)
    assert join("کتاب های تازه") == (f"کتاب{Z}های تازه", 1)


def test_leaves_the_rest_alone():
    assert join("کتاب ام") == ("کتاب ام", 0)  # -am only after a silent h
    assert join("صاحب خانه") == ("صاحب خانه", 0)  # compounds: word knowledge
    assert join("گفت: می") == ("گفت: می", 0)
    assert join("«می» رفت") == ("«می» رفت", 0)  # punctuation between them: two words
    assert join("می، رفت") == ("می، رفت", 0)
    assert join(f"می{Z}رفت") == (f"می{Z}رفت", 0)  # already right
    assert join("۱۲ ها") == ("۱۲ ها", 0)
    assert join("بی بی خانم") == (f"بی{Z}بی خانم", 1)  # a prefix only as a whole word, not after a join


def test_punctuation_outside_stays():
    assert join("«کتاب ها»،") == (f"«کتاب{Z}ها»،", 1)


def test_join_pages():
    page = Page(1, "ocr", lines=[Line("او می رفت", (0, 0, 10, 10)), Line("کتاب ها", (0, 20, 10, 30))])
    assert join_pages([page]) == 2
    assert page.lines[1].text == f"کتاب{Z}ها"
