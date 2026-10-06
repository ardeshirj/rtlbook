from rtlbook import script
from rtlbook.script import ScriptCheck, check, expected_script, parse_osd, sample_pages

OSD_OUTPUT = """Page number: 0
Orientation in degrees: 0
Rotate: 0
Orientation confidence: 12.34
Script: Latin
Script confidence: 5.28
"""


def test_expected_script():
    assert expected_script("fas") == "Arabic"
    assert expected_script("fas+ara") == "Arabic"
    assert expected_script("heb") == "Hebrew"
    assert expected_script("fas+heb") is None  # two scripts: nothing to check against
    assert expected_script("xyz") is None


def test_parse_osd():
    assert parse_osd(OSD_OUTPUT) == "Latin"
    assert parse_osd("") is None


def test_sample_pages_skip_the_ends_and_repeat_for_the_same_book():
    pages = sample_pages(list(range(1, 201)), "abc")
    assert len(pages) == script.TRIES and len(set(pages)) == len(pages)
    assert all(21 <= n <= 180 for n in pages)  # not the first or last tenth
    assert sample_pages(list(range(1, 201)), "abc") == pages
    assert sorted(sample_pages([1, 2, 3], "abc")) == [1, 2, 3]  # short books: every page


def test_majority_and_mismatch():
    assert ScriptCheck("Arabic", {5: "Latin", 9: "Latin", 12: "Arabic"}).mismatch
    assert not ScriptCheck("Arabic", {5: "Arabic", 9: "Latin", 12: "Arabic"}).mismatch
    assert ScriptCheck("Arabic", {5: "Latin", 9: "Arabic"}).found is None  # a tie is no answer
    assert ScriptCheck("Arabic", {5: None, 9: None}).found is None  # blank pages
    assert not ScriptCheck(None, {5: "Latin"}).mismatch  # nothing expected: never a mismatch


def test_check_stops_once_decided_and_skips_pages_without_an_answer(monkeypatch):
    answers = iter([None, "Latin", "Latin", "Arabic"])
    monkeypatch.setattr(script, "osd", lambda image: next(answers))
    result = check(lambda n: None, list(range(1, 101)), "fas", "abc")
    assert list(result.seen.values()) == [None, "Latin", "Latin"]  # two of three agree: the third can't change it
    assert result.found == "Latin" and result.mismatch


def test_check_skipped_for_unknown_scripts(monkeypatch):
    monkeypatch.setattr(script, "osd", lambda image: 1 / 0)  # never called
    assert check(lambda n: None, [1, 2, 3], "xyz", "abc").seen == {}
