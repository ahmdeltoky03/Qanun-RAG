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


# CJK radicals/ideographs/compatibility ideographs + CJK & fullwidth punctuation. Small models
# occasionally leak Chinese runs into Arabic answers; these characters can never be legitimate.
_CJK_RE = re.compile(r"[\u2e80-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
# a run of bare list numbers left behind once foreign text is removed ("1. 2. 3.")
_BARE_LIST_RE = re.compile(r"\d+\.(?:\s*\d+\.)+")


def drop_foreign_runs(text: str, ar: bool) -> str:
    """Remove characters of scripts that cannot belong to an answer in language `ar`.

    Character-level only (whitespace untouched) so it is safe to apply per streamed token.
    """
    text = _CJK_RE.sub("", text)
    return _LATIN_WORD_RE.sub("", text) if ar else _ARABIC_RE.sub("", text)


def strip_foreign_scripts(text: str, ar: bool) -> str:
    """Full cleanup of a finished answer: drop foreign scripts and the debris they leave."""
    text = drop_foreign_runs(text, ar)
    text = _BARE_LIST_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"^\W+$", "", text, flags=re.M)  # lines reduced to stray punctuation
    text = re.sub(r"[ \t]+([.,;:،؛])", r"\1", text)  # removal debris left a space before punctuation
    text = re.sub(r"(?m)^[ \t]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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
