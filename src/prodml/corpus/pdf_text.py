"""Column-aware, glyph-level text extraction for the bilingual Civil Code PDF.

The source PDF is a two-column layout (English on the left, Arabic on the right)
exported from Word. A naive text dump interleaves the columns and returns Arabic
words with their letters reversed. We therefore:

1. split every page into an English and an Arabic column by x-position;
2. group glyphs into visual lines;
3. for Arabic, reverse each word at *glyph* level (not character level), so that
   lam-alef ligature glyphs such as "لأ" stay intact, then re-reverse digit runs
   and reverse the word order of the line.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pdfplumber

COLUMN_BOUNDARY_X = 297.0  # measured: latin text ends at <=292, arabic starts at >=302
LINE_TOLERANCE = 3.0
_DIGIT = re.compile(r"[٠-٩0-9]")

Line = tuple[int, str, bool]  # (1-based pdf page, text, is_bold) - bold marks headings in this PDF


def _is_mark(text: str) -> bool:
    return bool(text) and all(unicodedata.category(ch) == "Mn" for ch in text)


def _group_lines(chars: list[dict]) -> list[list[dict]]:
    rows: list[dict] = []
    for c in sorted(chars, key=lambda c: (c["top"], c["x0"])):
        if _is_mark(c["text"]) or c["text"] == "":
            continue  # diacritics sit on a different baseline; we drop them on purpose
        for row in rows:
            if abs(row["top"] - c["top"]) <= LINE_TOLERANCE:
                row["chars"].append(c)
                break
        else:
            rows.append({"top": c["top"], "chars": [c]})
    rows.sort(key=lambda r: r["top"])
    return [r["chars"] for r in rows]


def _split_words(chars: list[dict]) -> list[list[dict]]:
    chars = sorted(chars, key=lambda c: c["x0"])
    words: list[list[dict]] = []
    cur: list[dict] = []
    prev: dict | None = None
    for c in chars:
        if c["text"].isspace():
            if cur:
                words.append(cur)
                cur = []
            prev = c
            continue
        if prev is not None and cur and (c["x0"] - prev["x1"]) > 0.22 * max(c["size"], 1) + 0.5:
            words.append(cur)
            cur = []
        cur.append(c)
        prev = c
    if cur:
        words.append(cur)
    return words


def _arabic_word_logical(word: list[dict]) -> str:
    glyphs = [c["text"] for c in reversed(word)]
    out: list[str] = []
    i = 0
    while i < len(glyphs):
        if _DIGIT.search(glyphs[i]):
            j = i
            while j < len(glyphs) and _DIGIT.search(glyphs[j]):
                j += 1
            out.extend(reversed(glyphs[i:j]))  # numbers are displayed left-to-right
            i = j
        else:
            out.append(glyphs[i])
            i += 1
    return "".join(out)


def _arabic_line(chars: list[dict]) -> str:
    words = [_arabic_word_logical(w) for w in _split_words(chars)]
    return " ".join(reversed(words))


def _is_bold(chars: list[dict]) -> bool:
    letters = [c for c in chars if c["text"].strip()]
    return bool(letters) and sum("Bold" in c["fontname"] for c in letters) / len(letters) > 0.5


def _english_line(chars: list[dict]) -> str:
    return " ".join("".join(c["text"] for c in w) for w in _split_words(chars))


def iter_columns(
    pdf_path: str | Path, boundary: float = COLUMN_BOUNDARY_X
) -> Iterator[tuple[int, list[tuple[str, bool]], list[tuple[str, bool]]]]:
    """Yield (page_number, english_lines, arabic_lines) for every page; lines are (text, is_bold)."""
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            en = [c for c in page.chars if (c["x0"] + c["x1"]) / 2 < boundary]
            ar = [c for c in page.chars if (c["x0"] + c["x1"]) / 2 >= boundary]
            yield (
                page_no,
                [(_english_line(r), _is_bold(r)) for r in _group_lines(en)],
                [(_arabic_line(r), _is_bold(r)) for r in _group_lines(ar)],
            )


def extract_lines(pdf_path: str | Path) -> tuple[list[Line], list[Line]]:
    en: list[Line] = []
    ar: list[Line] = []
    for page_no, en_lines, ar_lines in iter_columns(pdf_path):
        en.extend((page_no, t, b) for t, b in en_lines)
        ar.extend((page_no, t, b) for t, b in ar_lines)
    return en, ar
