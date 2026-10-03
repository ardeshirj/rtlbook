# All Persian sentences below are synthetic, written for these tests (no book text).
from rtlbook.model import Line, Page
from rtlbook.model import Paragraph
from rtlbook.text import (
    CommaFix, build_paragraphs, detect_comma_misreads, fix_misread_commas, fix_unopened_guillemets, normalize_text,
)

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
    assert fix == CommaFix(hamza=True)
    assert fix_misread_commas("بیا اینجا دخترمء ببین", fix) == "بیا اینجا دخترم، ببین"
    assert fix_misread_commas("اجزاء بدن", fix) == "اجزاء بدن"

    correct = [page(1, *[line("گفت، «بیا» و رفت، سپس برگشت، و گفت.", 100) for _ in range(6)])]
    assert detect_comma_misreads(correct) == CommaFix()


def test_hamza_edge_cases_and_parens():
    fix = CommaFix(hamza=True)
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


def test_unopened_closing_guillemet_is_a_comma():
    def fixed(*segments):
        p = Paragraph(list(segments))
        fix_unopened_guillemets(p)
        return p.text

    assert fixed("نه» ای دوست» امروز آمد") == "نه، ای دوست، امروز آمد"
    assert fixed("گفت: «نه، تو پیری» و رفت") == "گفت: «نه، تو پیری» و رفت"
    assert fixed("«سلام» گفت و رفت» بعد برگشت") == "«سلام» گفت و رفت، بعد برگشت"
    # a quotation that opens on one line and closes on the next stays a quotation
    assert fixed("گفت: «فردا", " ", 12, "می آیم» و رفت") == "گفت: «فردا می آیم» و رفت"


def _page_of(n, texts, *, conf=90.0, top=200, extra=()):
    from rtlbook.model import Line, Page

    lines = [Line(t, (100, top + 60 * i, 900, top + 60 * i + 40), conf) for i, t in enumerate(texts)]
    return Page(n, "ocr", width=1000, height=1400, lines=lines + list(extra))


def test_title_page_lines_stand_alone_and_dont_join_the_next_page():
    from rtlbook.text import sparse_pages

    body = "این سطری است که تا انتهای خط ادامه دارد و جمله هنوز تمام نشده"
    title = _page_of(1, ["نام کتاب", "نام نویسنده", "تهیه شده برای نشر در وبگاه"])
    pages = [title] + [_page_of(n, [body] * 12) for n in (2, 3, 4)]
    assert sparse_pages(pages) == {1}
    texts = [p.text for p in build_paragraphs(pages)]
    assert texts[:3] == ["نام کتاب", "نام نویسنده", "تهیه شده برای نشر در وبگاه"]
    assert texts[3].startswith(body)  # the credits line didn't swallow the first paragraph


def test_low_confidence_junk_in_the_margin_is_dropped():
    from rtlbook.model import Line

    body = "این سطری است که تا انتهای خط ادامه دارد و جمله هنوز تمام نشده"
    footer = Line("ط0ع .102 معط ناه جیوه", (300, 1330, 700, 1360), 29.0)  # a Latin footer read as Persian
    low_body = Line("سطر کم‌رنگ وسط صفحه", (100, 700, 900, 740), 35.0)  # mid-page: kept
    pages = [_page_of(n, [body] * 10, extra=(footer, low_body)) for n in (1, 2, 3)]
    text = " ".join(p.text for p in build_paragraphs(pages))
    assert "جیوه" not in text and "کم‌رنگ" in text


def test_low_confidence_warning():
    from rtlbook.doctype import confidence_message

    assert confidence_message(84.4) is None and confidence_message(None) is None
    assert "Low OCR confidence (55" in confidence_message(54.6)


def test_numbered_titles():
    from rtlbook.headings import numbered_title

    assert numbered_title("۲ـ غلام") == "۲- غلام"
    assert numbered_title("۲غلام") == "۲- غلام"
    assert numbered_title("ا-مهدی زاغی") == "۱- مهدی زاغی"  # a lone ۱ read as ا
    assert numbered_title("3: طرح یک بیماری") == "۳- طرح یک بیماری"
    assert numbered_title("۲. سپس به خانه رفتیم.") is None  # a list item: a sentence
    assert numbered_title("اسب سفید") is None  # ا without a separator is a letter
    assert numbered_title("۲- ها") is None and numbered_title("۴- ۰ مر ۴ ۰") is None  # OCR junk
    assert numbered_title("۱۲ سال بعد از آن روز که با هم به سفر رفتیم و برگشتیم") is None  # too long


def test_headings_from_layout():
    from rtlbook.model import Line, Page

    body = "این سطری است که تا انتهای خط ادامه دارد و جمله هنوز تمام نشده"

    def page(n, lines):
        return Page(n, "ocr", width=1000, height=1400, lines=lines)

    def row(text, y, *, x0=100, h=40):
        return Line(text, (x0, y, 900, y + h), 90.0)

    pages = [
        page(1, [row("ا-مهدی زاغی", 200, x0=700)] + [row(body, 300 + 60 * i) for i in range(12)]),
        page(2, [row(body, 200 + 60 * i) for i in range(5)]
             + [row("۲ـ غلام", 620, x0=800)]  # space above, short, numbered
             + [row(body, 720 + 60 * i) for i in range(6)]),
        page(3, [row("طرح یک", 200, h=100), row("بیماری", 310, h=100)]  # large type, wrapped
             + [row(body, 450 + 60 * i) for i in range(10)]
             + [row("۲ سال بعد از آن روز همه چیز تغییر کرده بود و ما هم دیگر آن آدم‌ها نبودیم", 1060)]
             + [row("دو سطر متن که در یک کادر بلند خوانده شده‌اند و پر از حرف هستند", 1120, h=100)]),
    ]
    heads = [p.text for p in build_paragraphs(pages) if p.heading]
    assert heads == ["۱- مهدی زاغی", "۲- غلام", "طرح یک بیماری"]


def _row(text, y, *, x0=100, h=40, conf=90.0):
    from rtlbook.model import Line

    return Line(text, (x0, y, 900, y + h), conf)


BODY = "این سطری است که تا انتهای خط ادامه دارد و جمله هنوز تمام نشده"


def _book(first_page_lines, body_pages=3, extra=None):
    from rtlbook.model import Page

    pages = [Page(1, "ocr", width=1000, height=1400, lines=first_page_lines)]
    for n in range(2, 2 + body_pages):
        lines = [_row(BODY, 200 + 60 * i) for i in range(12)]
        if extra and n in extra:
            lines = extra[n] + [_row(BODY, 400 + 60 * i) for i in range(12)]
        lines.append(_row("و تمام شد.", lines[-1].bbox[3] + 20, x0=650))  # a chapter-like ending
        pages.append(Page(n, "ocr", width=1000, height=1400, lines=lines))
    return pages


def test_title_and_author_from_the_title_page():
    from rtlbook.frontmatter import guess_title_author

    plain = _book([_row("نام کتاب", 300, h=160), _row("نام نویسنده", 520),
                   _row("تهیه برای نشر الکترونیک توسط یک نفر", 700)])
    assert guess_title_author(plain) == ("نام کتاب", "نام نویسنده")
    marked = _book([_row("«نام کتاب»", 300, h=120), _row("نوشته: نام نویسنده ۱۳۴۷", 900)])
    assert guess_title_author(marked) == ("نام کتاب", "نام نویسنده")
    credits_only = _book([_row("الکترونیک: وب لاگ یک سایت", 600, h=120)])
    assert guess_title_author(credits_only) == (None, None)


def test_contents_page_fixes_garbled_headings_and_finds_plain_ones():
    contents = [_row(f"{n}: {t}", 200 + 70 * i, conf=90.0) for i, (n, t) in
                enumerate([("۱", "شانزده تن"), ("۲", "پیش در آمد"), ("۳", "طرح یک بیماری"), ("۴", "راه شکستن طلسم")])]
    pages = _book(contents, body_pages=3, extra={
        2: [_row("راه شکست. ما", 200, h=120, conf=60.0)],  # large type, garbled
        3: [_row("پیش در آمد", 200, x0=700)],  # not set apart: a plain short line
    })
    heads = [p.text for p in build_paragraphs(pages) if p.heading]
    assert heads == ["راه شکستن طلسم", "پیش در آمد"]
