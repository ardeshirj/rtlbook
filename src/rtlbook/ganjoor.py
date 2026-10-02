"""Reference texts from Ganjoor (ganjoor.net), the main digital library of Persian poetry, via its
public API. Used as ground truth for `rtlbook eval` on scans of poetry."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

API = "https://api.ganjoor.net/api/ganjoor/page?url="


def poem_path(spec: str) -> str:
    """"https://ganjoor.net/hafez/ghazal/sh16" or "hafez/ghazal/sh16" -> "/hafez/ghazal/sh16"."""
    path = urllib.parse.urlparse(spec).path if "://" in spec else spec
    return "/" + path.strip("/")


def fetch_poem(spec: str, timeout: float = 30) -> dict:
    """{"title", "url", "verses": [half-lines in order], "sources": [printed editions Ganjoor checked]}"""
    url = API + urllib.parse.quote(poem_path(spec))
    req = urllib.request.Request(url, headers={"User-Agent": "rtlbook (OCR evaluation)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        page = json.load(r)
    poem = page.get("poem")
    if not poem:
        raise ValueError(f"Not a poem page on Ganjoor: {spec}")
    verses = sorted(poem.get("verses") or [], key=lambda v: v["vOrder"])
    return {
        "title": poem.get("fullTitle") or poem.get("title"),
        "url": "https://ganjoor.net" + poem["fullUrl"],
        "verses": [v["text"] for v in verses],
        "sources": [im["altText"].split(" » ")[0] for im in poem.get("images") or [] if im.get("isTextOriginalSource")],
    }
