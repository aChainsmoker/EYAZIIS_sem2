from __future__ import annotations

import os

import fitz


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 56
LINE_HEIGHT = 18


def _font_file() -> str | None:
    candidates = (
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    )
    return next((path for path in candidates if os.path.exists(path)), None)


def _new_page(document: fitz.Document) -> tuple[fitz.Page, float]:
    return document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT), MARGIN


def _write_text(
    document: fitz.Document,
    page: fitz.Page,
    y: float,
    text: str,
    fontsize: float,
    fontname: str,
    fontfile: str | None,
) -> tuple[fitz.Page, float]:
    font = fitz.Font(fontname=fontname, fontfile=fontfile)
    max_width = PAGE_WIDTH - 2 * MARGIN
    words = text.split()
    lines: list[str] = []
    current = ""

    for word in words:
        candidate = f"{current} {word}".strip()
        if current and font.text_length(candidate, fontsize=fontsize) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if not lines:
        lines = [""]

    for line in lines:
        if y + LINE_HEIGHT > PAGE_HEIGHT - MARGIN:
            page, y = _new_page(document)
        page.insert_text(
            (MARGIN, y),
            line,
            fontsize=fontsize,
            fontname=fontname,
            fontfile=fontfile,
            color=(0, 0, 0),
        )
        y += LINE_HEIGHT
    return page, y


def build_text_pdf(text: str) -> bytes:
    """Create a printable PDF from the exact text stored as the S3 TXT object."""
    document = fitz.open()
    fontfile = _font_file()
    fontname = "F0" if fontfile else "helv"
    page, y = _new_page(document)

    for line in text.splitlines() or [""]:
        page, y = _write_text(document, page, y, line, 11, fontname, fontfile)

    data = document.tobytes()
    document.close()
    return data
