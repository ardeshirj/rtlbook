# All Persian sentences below are synthetic, written for these tests (no book text).
from rtlbook.classify import function_word_score
from rtlbook.model import Line, Page
from rtlbook.text import CommaFix, build_paragraphs, detect_comma_misreads, fix_misread_commas, normalize_text

W = 1000  # page width for synthetic OCR lines


def line(text, x0, conf=90.0):
    return Line(text, (x0, 0, 900, 10), conf)


def page(n, *lines):
    return Page(n, "ocr", width=W, height=1400, lines=list(lines))


def test_normalize_arabic_letters():
    assert normalize_text("مي  گويم كه") == "می گویم که"


def test_wrapped_lines_join_and_dialogue_splits():
    pages = [
        page(1,
             line("امروز صبح زود از خانه بیرون رفتم و تا ایستگاه قطار پیاده رفتم. قطار", 100),  # full width
             line("دیر کرد. هوا سرد", 600),
             line("سارا- بیا زودتر برویم. اگر دیر برسیم باید", 100),
             line("خیلی صبر کنیم", 700),
             line("علی- رسیدیم؟", 750),
             line("سارا با لبخند- نگران شدی؟", 700),
             *[line(f"سطر پر شماره {i} ادامه دارد", 100) for i in range(20)]),
    ]
    paras = build_paragraphs(pages)
    texts = [p.text for p in paras]
    assert texts[0].startswith("امروز صبح") and texts[0].endswith("هوا سرد")
    assert texts[1].startswith("سارا- بیا") and texts[1].endswith("خیلی صبر کنیم")
    assert texts[2] == "علی- رسیدیم؟"
    assert texts[3] == "سارا با لبخند- نگران شدی؟"
    assert paras[0].segments[0] == 1  # page marker before first text


def test_paragraph_continues_across_page_break():
    body = [line(f"سطر پر شماره {i} ادامه دارد", 100) for i in range(20)]
    pages = [page(1, *body, line("و او گفت که فردا", 500)), page(2, line("خواهد آمد.", 700))]
    last = build_paragraphs(pages)[-1]
    assert last.text.endswith("و او گفت که فردا خواهد آمد.")
    assert 2 in last.segments


def test_debris_lines_dropped():
    pages = [page(1, line("|", 100, 30.0), line("ی", 100, 26.8), line("متن اصلی.", 500))]
    assert [p.text for p in build_paragraphs(pages)] == ["متن اصلی."]


def test_comma_fix_only_when_book_lacks_real_commas():
    misread = [page(1, *[line(f"دخترم{i}» بیا اینجا ببین چه خبر شده دخترمء ببین", 100) for i in range(6)])]
    fix = detect_comma_misreads(misread)
    assert fix == CommaFix(guillemets=True, hamza=True)
    assert fix_misread_commas("بیا اینجا دخترمء ببین", fix) == "بیا اینجا دخترم، ببین"
    assert fix_misread_commas("دیروز» امروز", fix) == "دیروز، امروز"
    assert fix_misread_commas("اجزاء بدن", fix) == "اجزاء بدن"

    correct = [page(1, *[line("گفت، «بیا» و رفت، سپس برگشت، و گفت.", 100) for _ in range(6)])]
    assert detect_comma_misreads(correct) == CommaFix()


def test_function_word_score_separates_good_and_broken_text():
    good = ("در این شهر کوچک همه یکدیگر را می شناسند. هر روز صبح مردم به بازار می روند و با هم از کار و"
            " زندگی حرف می زنند. این قصه ای است از یک خانواده که در کنار رودخانه زندگی می کرد.")
    # Mis-encoded glyphs, as extracted from a broken ToUnicode map
    broken = ("ػؿ ٥ثم ؿ٦ٍ ػْم ٨ٞ ثـ ىوب ٍؼ٦ُ ٫عب ٌْه ػّؿّ ؿا٥ ٍٚى لؾٌ ؼٌٚ ٌٍٍ ٦ٌػ ٌٍؿ ٞٞٞ ؿٍٍ"
              " ٥ٌٌ ػٍ٦ ؿٌٌ ٨ٌٍ")
    assert function_word_score(good)[0] > 0.2
    assert function_word_score(broken)[0] < 0.05


def test_hamza_edge_cases_and_parens():
    fix = CommaFix(guillemets=True, hamza=True)
    assert fix_misread_commas("نه جانمء‌چه شده", fix) == "نه جانم، چه شده"
    assert fix_misread_commas("خانه ماءفردا می آییم", fix) == "خانه ما، فردا می آییم"
    assert fix_misread_commas("قلم ءکاغذ", fix) == "قلم، کاغذ"
    assert fix_misread_commas("سوء تفاهم و امضاء نامه", fix) == "سوء تفاهم و امضاء نامه"


def test_mirrored_parens_across_lines_and_pages():
    from rtlbook.model import Paragraph
    from rtlbook.text import fix_mirrored_parens

    p = Paragraph(["گفتم (با صدای", " ", 7, "آهسته( و رفتم"])
    fix_mirrored_parens(p)
    assert p.text == "گفتم (با صدای آهسته) و رفتم"
    assert 7 in p.segments
    ok = Paragraph(["(درست) است"])
    fix_mirrored_parens(ok)
    assert ok.text == "(درست) است"


def test_persian_digits_skip_latin_tokens():
    from rtlbook.text import persian_digits

    assert persian_digits("ساعت 20:30 دقیقه") == "ساعت ۲۰:۳۰ دقیقه"
    assert persian_digits("عدد ٤٥ و 7") == "عدد ۴۵ و ۷"
    assert persian_digits("سایت example2024 و A4") == "سایت example2024 و A4"


def test_layer_stats_detect_visual_order_and_split_words():
    from rtlbook.classify import LayerStats

    logical = LayerStats()
    reversed_ = LayerStats()
    for _ in range(30):
        logical.add("معلم ـ امروز درس را تمام کردیم!\nشاگرد ـ فردا امتحان داریم؟")
        reversed_.add("!کردیم تمام را درس امروز ـ معلم\n؟داریم امتحان فردا ـ شاگرد")
    assert logical.problem() is None
    assert reversed_.problem() == "text-visual-order"

    split = LayerStats()
    for _ in range(40):
        split.add("ده ی اب ی م تو ک رد ن یم ی ه")
    assert split.problem() == "text-split-words"


def test_running_headers_removed_and_fuzzy_headings():
    pages = []
    for n in range(1, 11):
        lines = [Line(f"کتاب نمونه- نشر آزمایشی {n}", (500, 50, 900, 90), 90.0)]
        if n == 3:
            lines.append(Line("نصل دوم", (700, 400, 900, 460), 80.0))
        lines += [Line(f"متن صفحه {n} ادامه دارد.", (100, 600 + i * 70, 900, 650 + i * 70), 90.0) for i in range(3)]
        pages.append(Page(n, "ocr", width=1000, height=1400, lines=lines))
    paras = build_paragraphs(pages)
    texts = [p.text for p in paras]
    assert not any("نشر آزمایشی" in t for t in texts)
    heads = [p.text for p in paras if p.heading]
    assert heads == ["فصل دوم"]


def test_screenplay_dialogue_splits():
    pages = [page(1, line("سارا : امروز هوا خیلی خوب است و می خواهم", 100),
                  line("علی : من هم می آیم", 500),
                  *[line(f"سطر پر شماره {i} ادامه دارد", 100) for i in range(20)])]
    texts = [p.text for p in build_paragraphs(pages)]
    assert texts[0].startswith("سارا :") and texts[1].startswith("علی :")
