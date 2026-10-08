"""Arabic text helpers: digit mapping, display cleanup, and search normalisation."""

from __future__ import annotations

import re
import unicodedata

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TATWEEL = "\u0640"
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def to_western_digits(text: str) -> str:
    """Map Arabic-Indic and Persian digits to ASCII digits (١٤٧ -> 147)."""
    return text.translate(_AR_DIGITS)


def parse_article_number(text: str) -> int | None:
    """Return the integer found in `text` (Arabic-Indic or Western digits), else None."""
    m = re.search(r"\d+", to_western_digits(text))
    return int(m.group()) if m else None


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text))


# harakat, tanween, shadda, sukun, superscript alef and Quranic marks. We list the code points
# explicitly: NFKD would also split أ إ آ ئ ؤ into base + combining hamza and silently drop the hamza.
_DIACRITICS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06dc\u06df-\u06e8\u06ea-\u06ed]")


def strip_diacritics(text: str) -> str:
    """Remove harakat/tanween/shadda and tatweel without touching hamza carriers."""
    return _DIACRITICS.sub("", text.replace(_TATWEEL, ""))


def clean_display(text: str) -> str:
    """Light, reversible-looking cleanup for text we show to users.

    Fixes the paren/apostrophe artefacts that Word -> PDF export leaves behind
    without changing wording or spelling.
    """
    text = unicodedata.normalize("NFKC", text)
    text = strip_diacritics(text)
    # "(١(" / ")١(" / "( ٢ (" -> "(١)"
    text = re.sub(r"[()]\s*([٠-٩0-9]{1,2})\s*[()]", r"(\1)", text)
    # the export turned the Arabic comma into an ASCII apostrophe
    text = re.sub(r"(?<=[\u0600-\u06FF])'(?=\s)", "،", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([،.؛:])", r"\1", text)
    return text.strip()


def normalize_for_search(text: str) -> str:
    """Aggressive normalisation applied identically at index and query time.

    - strip diacritics / tatweel
    - unify alef variants (أ إ آ ٱ -> ا), ى -> ي, ة -> ه, ؤ -> و, ئ -> ي
    - Arabic-Indic digits -> ASCII
    - collapse whitespace
    Without this the same word embeds as several different tokens.
    """
    text = unicodedata.normalize("NFKC", text)
    text = strip_diacritics(to_western_digits(text))
    text = re.sub("[أإآٱ]", "ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
_AR_SUFFIXES = ("ات", "ان", "ين", "ون", "ها", "هم", "ه", "ي")


def light_stem(token: str) -> str:
    """Very light Arabic stemmer (strip one clitic prefix and one suffix); no-op for Latin tokens."""
    if not _ARABIC_RE.search(token):
        return token[:-1] if len(token) > 4 and token.endswith("s") else token
    for pre in _AR_PREFIXES:
        if token.startswith(pre) and len(token) - len(pre) >= 3:
            token = token[len(pre) :]
            break
    for suf in _AR_SUFFIXES:
        if token.endswith(suf) and len(token) - len(suf) >= 3:
            token = token[: -len(suf)]
            break
    return token
