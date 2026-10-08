"""Turn extracted column lines into one structured record per article."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qanun.arabic import clean_display, parse_article_number
from qanun.corpus.pdf_text import Line

LEVELS = ("part", "book", "chapter", "section")
MAX_FORWARD_JUMP = 5  # tolerate a few missing headers, but never accept a far-away cross-reference

# ---------------------------------------------------------------- English ----
EN_HEADER = re.compile(
    r"^A?rticle\s*(\d{1,4})(?:\s+(?P<rest>[A-Z].*))?$"
)  # tolerates source typos: "rticle 452", "Article1022", "Article 277 If ..."
EN_MARKER = re.compile(
    r"^(?P<kind>FIRST PART|SECOND PART|BOOK|CHAPTER|Chapter|SECTION|Section)"
    r"(?:\s+(?P<num>[IVXL]+))?\.?(?:\s+(?P<rest>[A-Z].*))?$"
)
EN_KIND = {"FIRST PART": "part", "SECOND PART": "part", "BOOK": "book", "CHAPTER": "chapter", "SECTION": "section"}
EN_TOPIC = re.compile(r"^\d{1,2}\s*[-–.]\s*(?P<t>\S.{2,80})$")
EN_REPEAL = re.compile(r"Articles?\s+(\d+)\s*(?:-|–|to)\s*(\d+)\s+(?:have been\s+)?repealed", re.I)

# ----------------------------------------------------------------- Arabic ----
AR_HEADER = re.compile(r"^مادة\s*[()]*\s*([٠-٩0-9]{1,4})\s*[()]*$")
AR_MARKER = re.compile(r"^(?P<kind>القسم|الكتاب|الباب|الفصل)\s+(?P<ord>\S+?)\s*\.?(?:\s+(?P<rest>\S.*))?$")
AR_KIND = {"القسم": "part", "الكتاب": "book", "الباب": "chapter", "الفصل": "section"}
AR_ORDINALS = {
    "الأول", "الاول", "الثاني", "الثانى", "الثالث", "الرابع", "الخامس", "السادس",
    "السابع", "الثامن", "التاسع", "العاشر",
}  # fmt: skip
AR_TOPIC = re.compile(r"^[٠-٩0-9]{1,2}\s*[-–.]\s*(?P<t>\S.{2,80})$")
AR_REPEAL_FULL = re.compile(r"^المواد\s+من\s+([٠-٩0-9]+)\s+إلى\s+([٠-٩0-9]+)(?:\s+ملغاة)?$")
AR_REPEAL_NOTE = re.compile(r"ألغيت\s+المواد\s+من\s+([٠-٩0-9]+)\s+إلى\s+([٠-٩0-9]+)")
AR_PARA_START = re.compile(r"^[()]\s*[٠-٩0-9]{1,2}\s*[()]|^[أ-ي]ـ?\s*-\s")

TERMINAL = (".", ";", ":", ")", "،", "؛", "!", "?", "؟")
CONNECTORS = ("and", "of", "or", "the", "in", "to", "for", "on", "by", "with", "its", "a", ",", "و", "في", "من", "على")


@dataclass
class RawArticle:
    number: int
    page: int
    lines: list[str] = field(default_factory=list)
    hierarchy: dict[str, str] = field(default_factory=dict)
    bold_body: bool = False  # a few articles are entirely set in bold in the source; they are not headings


@dataclass
class RepealedRange:
    start: int
    end: int
    page: int
    note_lines: list[str] = field(default_factory=list)
    hierarchy: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedColumn:
    lang: str
    articles: dict[int, RawArticle] = field(default_factory=dict)
    repealed: list[RepealedRange] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _Scanner:
    """State machine over one column's lines.

    In this PDF every heading (part / book / chapter / section / topic / label) is set in a
    bold face and article text and the "Article N" lines are not. That one signal is far
    more reliable than guessing from punctuation or line length.
    """

    def __init__(self, lang: str, lines: list[Line]):
        self.lang = lang
        self.lines = [(p, t.strip(), b) for p, t, b in lines]
        self.out = ParsedColumn(lang=lang)
        self.hier: dict[str, str] = {}
        self.topic = ""
        self.subtopic = ""
        self.expected = 1
        self.current: RawArticle | RepealedRange | None = None
        self.pending_title: str | None = None
        self.last_heading: tuple[str, str] | None = None  # what the previous bold line filled

    # -- classification ------------------------------------------------------
    def _header(self, text: str) -> tuple[int, str] | None:
        pat = EN_HEADER if self.lang == "en" else AR_HEADER
        m = pat.match(text)
        if not m:
            return None
        num = parse_article_number(m.group(1))
        inline = (m.groupdict().get("rest") or "").strip()
        return (num, inline) if num is not None else None

    def _marker(self, text: str) -> tuple[str, str] | None:
        """(level, inline_title) when the bold line opens a hierarchy level."""
        if self.lang == "en":
            m = EN_MARKER.match(text)
            if not m or len(text) > 90:
                return None
            kind = m.group("kind")
            if kind not in ("FIRST PART", "SECOND PART") and not m.group("num"):
                return None
            return EN_KIND[kind.upper()], (m.group("rest") or "").strip()
        m = AR_MARKER.match(text)
        if not m or m.group("ord") not in AR_ORDINALS or len(text) > 90:
            return None
        return AR_KIND[m.group("kind")], (m.group("rest") or "").strip()

    # -- state helpers -------------------------------------------------------
    def _close(self) -> None:
        self.current = None

    def _set_level(self, level: str, title: str) -> None:
        for lower in LEVELS[LEVELS.index(level) :]:
            self.hier.pop(lower, None)
        self.topic = self.subtopic = ""
        self.hier[level] = title
        self.pending_title = None if title else level

    def _register_repeal(self, a: str, b: str, page: int, first_line: str) -> None:
        start, end = parse_article_number(a), parse_article_number(b)
        if start is None or end is None:
            return
        for r in self.out.repealed:
            if (r.start, r.end) == (start, end):
                self.current = r
                r.note_lines.append(first_line)
                return
        rng = RepealedRange(start, end, page, [first_line], dict(self.hier))
        self.out.repealed.append(rng)
        self.expected = max(self.expected, end + 1)
        self.current = rng

    def _current_heading_text(self) -> str:
        kind, level = self.last_heading or ("", "")
        return self.hier.get(level, "") if kind == "level" else self.subtopic if kind == "subtopic" else self.topic

    def _wraps(self, text: str) -> bool:
        """The previous bold heading ended on a connector word, so this line continues it."""
        prev = self._current_heading_text().rstrip().lower()
        return bool(prev) and prev.endswith(CONNECTORS) and not text[:1].isdigit()

    def _append_to_last_heading(self, text: str) -> None:
        kind, level = self.last_heading  # type: ignore[misc]
        if kind == "level":
            self.hier[level] = f"{self.hier[level]} {text}".strip()
        elif kind == "subtopic":
            self.subtopic = f"{self.subtopic} {text}".strip(" :")
        else:
            self.topic = f"{self.topic} {text}".strip(" .:")

    def _pop_trailing_label(self) -> None:
        """A short unpunctuated last line after a finished sentence is a (non-bold) section label."""
        cur = self.current
        if not isinstance(cur, RawArticle):
            return
        body = [ln for ln in cur.lines if ln]
        if len(body) >= 2 and len(body[-1]) <= 40 and not body[-1].endswith(TERMINAL) and body[-2].endswith(TERMINAL):
            label = body[-1]
            idx = max(i for i, ln in enumerate(cur.lines) if ln == label)
            del cur.lines[idx]
            self.subtopic = label.strip(" :")

    def _accept_header(self, num: int, page: int) -> bool:
        if num == self.expected:
            return True
        if self.expected < num <= self.expected + MAX_FORWARD_JUMP:
            self.out.warnings.append(f"{self.lang}: gap before article {num} (expected {self.expected}) on page {page}")
            return True
        return False  # a cross-reference such as "Article 444" that wrapped onto its own line

    def _find_start(self) -> int:
        for idx, (_, t, _b) in enumerate(self.lines):
            if self.lang == "en" and t == "SECTION I":
                self.hier = {"chapter": "Preliminary Chapter: General Provisions"}
                return idx
            if self.lang == "ar" and t.startswith("باب تمهيدي"):
                self.hier = {"chapter": "باب تمهيدي: أحكام عامة"}
                return idx + 2  # skip the "أحكام" title lines that follow
        return 0

    # -- main loop -----------------------------------------------------------
    def run(self) -> ParsedColumn:
        lines = self.lines
        i = self._find_start()
        while i < len(lines):
            page, text, bold = lines[i]
            nxt = lines[i + 1][1] if i + 1 < len(lines) else ""
            i += 1
            if not text:
                if isinstance(self.current, RawArticle):
                    self.current.lines.append("")
                continue

            # 1. repeal notes sit between chapters, outside any article
            if self.lang == "en" and (m := EN_REPEAL.search(text)):
                self._register_repeal(m.group(1), m.group(2), page, text)
                continue
            if self.lang == "ar":
                m = (
                    (AR_REPEAL_FULL.match(text) if (nxt.startswith("ألغيت") or "ملغاة" in text) else None)
                    or AR_REPEAL_NOTE.search(text)
                )  # fmt: skip
                if m:
                    self._register_repeal(m.group(1), m.group(2), page, text)
                    continue

            # 2. bold line == heading (unless the open article is itself set in bold)
            if bold:
                mk = self._marker(text)
                topic = (EN_TOPIC if self.lang == "en" else AR_TOPIC).match(text)
                art = self.current if isinstance(self.current, RawArticle) else None
                if art is not None and not mk and not topic and (art.bold_body or not any(art.lines)):
                    art.bold_body = True
                    art.lines.append(text)
                    continue
                if mk is not None:
                    self._close()
                    self._set_level(*mk)
                    self.last_heading = ("level", mk[0]) if mk[1] else None
                elif self.pending_title:
                    self.hier[self.pending_title] = text
                    self.last_heading = ("level", self.pending_title)
                    self.pending_title = None
                    self._close()
                elif self.last_heading and self._wraps(text):
                    self._append_to_last_heading(text)
                elif topic:
                    self.topic, self.subtopic = topic.group("t").strip(" .:"), ""
                    self.last_heading = ("topic", "")
                    self._close()
                else:
                    self.subtopic = text.strip(" :")
                    self.last_heading = ("subtopic", "")
                    self._close()
                continue
            self.pending_title = None
            self.last_heading = None

            # 3. article header
            if (h := self._header(text)) is not None and self._accept_header(h[0], page):
                num, inline = h
                self._pop_trailing_label()
                self._close()
                self.current = RawArticle(
                    num, page, [inline] if inline else [], {**self.hier, "topic": self.topic, "subtopic": self.subtopic}
                )
                self.out.articles.setdefault(num, self.current)
                self.expected = num + 1
                continue

            # 4. plain text belongs to whatever is open
            if isinstance(self.current, RawArticle):
                self.current.lines.append(text)
            elif isinstance(self.current, RepealedRange):
                self.current.note_lines.append(text)
        return self.out


def _scan(lang: str, lines: list[Line]) -> ParsedColumn:
    return _Scanner(lang, lines).run()


# ---------------------------------------------------------------- assembly ----
def _join_en(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(ln for ln in lines if ln)).strip()


def _join_ar(lines: list[str]) -> str:
    paras: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if not ln:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if buf and AR_PARA_START.match(ln):
            paras.append(" ".join(buf))
            buf = []
        buf.append(ln)
    if buf:
        paras.append(" ".join(buf))
    return "\n".join(clean_display(p) for p in paras if p.strip())


def build_records(en_lines: list[Line], ar_lines: list[Line]) -> tuple[list[dict], dict]:
    en, ar = _scan("en", en_lines), _scan("ar", ar_lines)
    repealed: dict[int, dict] = {}
    for column, key in ((en, "en"), (ar, "ar")):
        for rng in column.repealed:
            note = [ln for ln in rng.note_lines if not (key == "ar" and AR_REPEAL_FULL.match(ln) and "ملغاة" not in ln)]
            text = _join_en(note) if key == "en" else _join_ar(note)
            for n in range(rng.start, rng.end + 1):
                slot = repealed.setdefault(n, {"page": rng.page, "en": "", "ar": "", "hier_en": {}, "hier_ar": {}})
                slot[key] = text
                slot["hier_" + key] = rng.hierarchy
    numbers = sorted(set(en.articles) | set(ar.articles) | set(repealed))
    records: list[dict] = []
    issues: dict[int, list[str]] = {}
    for n in numbers:
        e, a, rep = en.articles.get(n), ar.articles.get(n), repealed.get(n)
        h = rep["hier_en"] if rep else (e.hierarchy if e else {})
        ha = rep["hier_ar"] if rep else (a.hierarchy if a else {})
        if rep:
            text_en = rep["en"] or "This article has been repealed."
            text_ar = rep["ar"] or "هذه المادة ملغاة."
            page = rep["page"]
        else:
            text_en = _join_en(e.lines) if e else ""
            text_ar = _join_ar(a.lines) if a else ""
            page = (a or e).page
            rec_issues = []
            if not text_ar:
                rec_issues.append("arabic_text_missing_in_source")
            if not text_en:
                rec_issues.append("english_text_missing_in_source")
            if rec_issues:
                issues[n] = rec_issues
        records.append(
            {
                "article_number": n,
                "part": h.get("part", ""),
                "book": h.get("book", ""),
                "chapter": h.get("chapter", ""),
                "section": h.get("section", ""),
                "topic": h.get("topic", ""),
                "subtopic": h.get("subtopic", ""),
                "part_ar": ha.get("part", ""),
                "book_ar": ha.get("book", ""),
                "chapter_ar": ha.get("chapter", ""),
                "section_ar": ha.get("section", ""),
                "topic_ar": ha.get("topic", ""),
                "text_ar": text_ar,
                "text_en": text_en,
                "is_repealed": rep is not None,
                "source_page": page,
                "citation": f"Egyptian Civil Code, Article {n}",
                "citation_ar": f"القانون المدني المصري، المادة {n}",
            }
        )
    _normalise_hierarchy(records)
    _fill_missing_hierarchy(records)
    report = {
        "warnings": en.warnings + ar.warnings,
        "source_issues": {str(k): v for k, v in issues.items()},
        "repealed_ranges": sorted({(r.start, r.end) for r in en.repealed + ar.repealed}),
    }
    return records, report


_SMALL = {"of", "and", "or", "the", "in", "to", "for", "on", "by", "with", "a", "an", "from"}


def _titlecase(text: str) -> str:
    """'OBLIGATIONS OR PERSONAL RIGHTS' -> 'Obligations or Personal Rights'; leave mixed case alone."""
    if not text or text != text.upper():
        return text
    words = text.lower().split()
    return " ".join(w if (i and w in _SMALL) else w.capitalize() for i, w in enumerate(words))


# The Arabic column has no "القسم الثاني" heading although the English one has "SECOND PART".
_PART_AR_FALLBACK = {"Real Rights": "الحقوق العينية"}


def _normalise_hierarchy(records: list[dict]) -> None:
    for r in records:
        for key in ("part", "book", "chapter", "section"):
            r[key] = _titlecase(r[key])
        if r["part"] in _PART_AR_FALLBACK:
            r["part_ar"] = _PART_AR_FALLBACK[r["part"]]


def _fill_missing_hierarchy(records: list[dict]) -> None:
    """An article that exists in only one column inherits the other column's hierarchy from its neighbour."""
    en_keys = ("part", "book", "chapter", "section", "topic", "subtopic")
    ar_keys = ("part_ar", "book_ar", "chapter_ar", "section_ar", "topic_ar")
    for i, r in enumerate(records):
        for keys, other in ((en_keys, ar_keys), (ar_keys, en_keys)):
            if any(r[k] for k in keys[:4]) or not any(r[k] for k in other[:4]):
                continue
            for prev in reversed(records[:i]):
                if all(prev[k] == r[k] for k in other[:4]) and any(prev[k] for k in keys[:4]):
                    for k in keys:
                        r[k] = prev[k]
                    break
