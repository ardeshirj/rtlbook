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


def test_report_puts_readers_on_the_same_lines_side_by_side():
    from rtlbook.bench import report

    def run(reader, data, wrong):
        return {"date": "2026-10-14T00:00:00Z", "engine": "0.6.0", "reader": reader, "commit": "abc",
                "lines": {"set": "s", "data": data, "lines": 50, "letters_wrong": wrong, "exact": 1,
                          "spacing_wrong": 0.1, "seconds_a_line": 0.05}}

    files = report([run("a", "old", 0.5), run("b", "new", 0.06), run("c", "new", 0.01)])
    side = files["README.md"].split("## Every run")[0]
    assert "| c |" in side and "| b |" in side and "| a |" not in side  # a ran on other lines
    assert side.index("| c |") < side.index("| b |")  # fewest letters wrong first
    chart = files["charts/letters-wrong.svg"]
    assert "](charts/letters-wrong.svg)" in side and chart.index(">c<") < chart.index(">b<")
    c_row = chart.split(">c<")[1].split(">b<")[0]
    assert 'fill="#2f6fb0"' in c_row and ">1.00%<" in c_row  # c the best: blue, its value at its bar's end
    assert 'fill="#e07b24"' in chart.split(">b<")[1]  # b the worst: orange
