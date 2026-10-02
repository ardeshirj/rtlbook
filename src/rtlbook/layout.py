"""Reading order of OCR lines on a page.

Tesseract reads a page block by block, so two-column verse (the two half-lines of each couplet side
by side) comes out column by column: all right half-lines, then all left ones. Here lines that sit
side by side are grouped into one row; rows are read top to bottom, and each row right to left.
Single-column prose keeps its order.

Not handled: two-column prose (newspaper style), where text flows down each column.
"""

from __future__ import annotations

from rtlbook.model import Line

MIN_V_OVERLAP = 0.5  # side by side: vertical overlap of at least half the shorter line's height


def _side_by_side(a: Line, b: Line) -> bool:
    ax0, ay0, ax1, ay1 = a.bbox
    bx0, by0, bx1, by1 = b.bbox
    v = min(ay1, by1) - max(ay0, by0)
    h = min(ax1, bx1) - max(ax0, bx0)
    return v >= MIN_V_OVERLAP * min(ay1 - ay0, by1 - by0) and h <= 0


def rows(lines: list[Line]) -> list[list[Line]]:
    """Lines grouped into rows, top to bottom; each row right to left."""
    if len(lines) < 2:
        return [[ln] for ln in lines]
    out: list[list[Line]] = []
    for ln in sorted(lines, key=lambda l: (l.bbox[1], -l.bbox[2])):
        for row in reversed(out[-3:]):  # only rows close above can share a line's height
            if all(_side_by_side(ln, other) for other in row):
                row.append(ln)
                break
        else:
            out.append([ln])
    for row in out:
        row.sort(key=lambda l: -l.bbox[2])
    out.sort(key=lambda r: min(l.bbox[1] for l in r))
    return out


def reading_order(lines: list[Line]) -> list[Line]:
    return [ln for row in rows(lines) for ln in row]
