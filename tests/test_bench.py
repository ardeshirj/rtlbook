# All Persian sentences below are synthetic, written for these tests (no book text).
import json

from rtlbook.bench import page_references, spacing

REF = "او می‌گفت که به خانه رفته است"  # 7 gaps: 6 spaces, 1 half-space


def test_same_text_has_no_spacing_errors():
    assert spacing(REF, REF) == (0, 7)


def test_joined_split_and_half_space_each_count_once():
    assert spacing(REF, "او میگفت که به خانه رفته است") == (1, 7)  # half-space lost
    assert spacing(REF, "او می گفت که بهخانه رفته است") == (2, 7)  # half-space as a space; two words joined
    assert spacing(REF, "او می‌گفت که به خا نه رفته است") == (1, 7)  # a word split


def test_letter_errors_dont_count_as_spacing():
    assert spacing(REF, "او می‌گفت که به خانه رفنه است") == (0, 7)
    assert spacing(REF, "او می‌گفت که بخانه رفته است") == (0, 7)  # a letter lost with the space: a letter error


def test_page_references_take_whole_checked_test_pages(tmp_path):
    lines = [{"id": f"p00{p}-0{n}", "page": p, "split": s} for p, s in ((3, "test"), (4, "test"), (5, "train"))
             for n in (1, 2)]
    (tmp_path / "lines.json").write_text(json.dumps({"lines": lines}))
    review = {"p003-01": "done", "p003-02": "skip", "p004-01": "done", "p004-02": "unsure", "p005-01": "done",
              "p005-02": "done"}
    (tmp_path / "review.json").write_text(json.dumps({i: {"status": s} for i, s in review.items()}))
    for i, s in review.items():
        if s == "done":
            (tmp_path / f"{i}.gt.txt").write_text(f"سطر {i}\n", encoding="utf-8")
    texts = tmp_path / "texts"
    texts.mkdir()
    (texts / "p3.txt").write_text("کهنه", encoding="utf-8")
    (texts / "p9.txt").write_text("سطر نهم", encoding="utf-8")
    refs = page_references(tmp_path, texts)
    assert refs == {3: "سطر p003-01", 9: "سطر نهم"}  # the set's page 3 wins; page 4 has an unsure line
