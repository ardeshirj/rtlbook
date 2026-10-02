"""Document model: OCR'd pages, their lines, and the paragraphs and sections built from them."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Line:
    text: str
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) in pixels of the rendered page, origin top-left
    conf: float | None = None


@dataclass
class Page:
    number: int  # 1-based physical page number in the PDF
    route: str  # always "ocr" (kept in cached pages)
    width: int = 0
    height: int = 0
    lines: list[Line] = field(default_factory=list)
    settings: dict = field(default_factory=dict)  # what produced this result (cache key)
    seconds: float = 0.0

    @property
    def mean_conf(self) -> float | None:
        confs = [ln.conf for ln in self.lines if ln.conf is not None]
        return sum(confs) / len(confs) if confs else None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Page:
        lines = [Line(ln["text"], tuple(ln["bbox"]), ln["conf"]) for ln in d["lines"]]
        return cls(**{**d, "lines": lines})


@dataclass
class Paragraph:
    # Inline segments: text strings, and ints marking where a physical page starts
    segments: list[str | int] = field(default_factory=list)
    heading: bool = False

    @property
    def text(self) -> str:
        return "".join(s for s in self.segments if isinstance(s, str))


@dataclass
class Section:
    title: str
    paragraphs: list[Paragraph]
