"""Minimal EPUB 3 writer with correct RTL settings (hand-rolled to avoid AGPL dependencies)."""

from __future__ import annotations

import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from rtlbook.model import Paragraph, Section

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


@dataclass
class BookMeta:
    title: str
    author: str
    lang: str = "fa"
    identifier: str = ""  # stable id, e.g. derived from the source PDF hash
    cover: tuple[bytes, str] | None = None  # (bytes, media type)
    fonts: tuple[Path, ...] = ()


CSS = """\
{font_faces}
body {{
  font-family: {font_family}serif;
  line-height: 1.9;
  text-align: justify;
  margin: 0 0.5em;
}}
p {{ margin: 0 0 0.5em 0; text-indent: 0; }}
h1, h2 {{ text-align: center; font-weight: bold; margin: 1.5em 0 1em 0; }}
h1 {{ font-size: 1.5em; }}
h2 {{ font-size: 1.25em; }}
.title-page {{ text-align: center; margin-top: 30%; }}
.cover {{ text-align: center; margin: 0; padding: 0; }}
.cover img {{ max-width: 100%; max-height: 100%; }}
"""


def _xhtml(title: str, body: str, lang: str, css: str = "css/book.css") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}" dir="rtl">
<head>
<meta charset="utf-8"/>
<title>{escape(title)}</title>
<link rel="stylesheet" type="text/css" href="{css}"/>
</head>
<body dir="rtl">
{body}
</body>
</html>
"""


def _para_html(p: Paragraph) -> str:
    out = []
    for seg in p.segments:
        if isinstance(seg, int):
            out.append(f'<span epub:type="pagebreak" role="doc-pagebreak" id="page{seg}" aria-label="{seg}"></span>')
        else:
            out.append(escape(seg, quote=False))
    tag = "h2" if p.heading else "p"
    return f"<{tag}>{''.join(out)}</{tag}>"


def write_epub(path: Path, meta: BookMeta, sections: list[Section]) -> None:
    lang = meta.lang
    book_id = meta.identifier or f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    files: dict[str, str | bytes] = {}
    manifest: list[str] = []
    spine: list[str] = []

    # Fonts + CSS
    faces, family = [], ""
    for i, f in enumerate(meta.fonts):
        weight = "bold" if "bold" in f.name.lower() else "normal"
        files[f"OEBPS/fonts/{f.name}"] = f.read_bytes()
        manifest.append(f'<item id="font{i}" href="fonts/{f.name}" media-type="font/ttf"/>')
        faces.append(
            f'@font-face {{ font-family: "BookFont"; font-weight: {weight}; font-style: normal;'
            f' src: url("../fonts/{f.name}"); }}'
        )
        family = '"BookFont", '
    files["OEBPS/css/book.css"] = CSS.format(font_faces="\n".join(faces), font_family=family)
    manifest.append('<item id="css" href="css/book.css" media-type="text/css"/>')

    # Cover
    if meta.cover:
        data, media = meta.cover
        ext = "jpg" if media == "image/jpeg" else "png"
        files[f"OEBPS/images/cover.{ext}"] = data
        manifest.append(f'<item id="cover-image" href="images/cover.{ext}" media-type="{media}" properties="cover-image"/>')
        files["OEBPS/cover.xhtml"] = _xhtml(
            meta.title, f'<div class="cover"><img src="images/cover.{ext}" alt="{escape(meta.title)}"/></div>', lang, "css/book.css"
        )
        manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover" linear="yes"/>')

    # Title page
    files["OEBPS/title.xhtml"] = _xhtml(
        meta.title, f'<div class="title-page"><h1>{escape(meta.title)}</h1><p>{escape(meta.author)}</p></div>', lang
    )
    manifest.append('<item id="titlepage" href="title.xhtml" media-type="application/xhtml+xml"/>')
    spine.append('<itemref idref="titlepage"/>')

    # Content sections
    toc_items, page_items = [], []
    for i, sec in enumerate(sections, 1):
        name = f"text/sec{i:03d}.xhtml"
        body = "\n".join(_para_html(p) for p in sec.paragraphs)
        files[f"OEBPS/{name}"] = _xhtml(sec.title, body, lang, "../css/book.css")
        manifest.append(f'<item id="sec{i:03d}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="sec{i:03d}"/>')
        toc_items.append((sec.title, name))
        for p in sec.paragraphs:
            page_items += [(seg, f"{name}#page{seg}") for seg in p.segments if isinstance(seg, int)]

    # Navigation document (TOC + page list + landmarks)
    toc_li = "\n".join(f'<li><a href="{h}">{escape(t)}</a></li>' for t, h in toc_items)
    page_li = "\n".join(f'<li><a href="{h}">{str(n).translate(FA_DIGITS)}</a></li>' for n, h in page_items)
    first = toc_items[0][1] if toc_items else "title.xhtml"
    nav_body = f"""<nav epub:type="toc" id="toc"><h1>فهرست</h1><ol>
{toc_li}
</ol></nav>
<nav epub:type="page-list" hidden=""><ol>
{page_li}
</ol></nav>
<nav epub:type="landmarks" hidden=""><ol>
<li><a epub:type="bodymatter" href="{first}">متن</a></li>
</ol></nav>"""
    files["OEBPS/nav.xhtml"] = _xhtml("فهرست", nav_body, lang)
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

    # NCX for EPUB 2 reading systems
    ncx_points = "\n".join(
        f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{escape(t)}</text></navLabel><content src="{h}"/></navPoint>'
        for i, (t, h) in enumerate(toc_items, 1)
    )
    files["OEBPS/toc.ncx"] = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="{lang}">
<head><meta name="dtb:uid" content="{escape(book_id)}"/></head>
<docTitle><text>{escape(meta.title)}</text></docTitle>
<navMap>
{ncx_points}
</navMap>
</ncx>
"""
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')

    creator = f"<dc:creator>{escape(meta.author)}</dc:creator>\n" if meta.author.strip() else ""
    cover_meta = '<meta name="cover" content="cover-image"/>' if meta.cover else ""
    # Kindle conversion hint for RTL books (Amazon Kindle Publishing Guidelines)
    cover_meta += '\n<meta name="primary-writing-mode" content="horizontal-rl"/>'
    files["OEBPS/content.opf"] = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}" dir="rtl">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{escape(book_id)}</dc:identifier>
<dc:title>{escape(meta.title)}</dc:title>
{creator}<dc:language>{lang}</dc:language>
<meta property="dcterms:modified">{modified}</meta>
{cover_meta}
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx" page-progression-direction="rtl">
{chr(10).join(spine)}
</spine>
</package>
"""
    files["META-INF/container.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
