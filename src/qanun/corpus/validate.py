"""Validate the extracted corpus *before* anything is embedded.

A silent parsing bug becomes a hallucination three steps later, so every check
here is cheap and loud.
"""

from __future__ import annotations

MAX_ARTICLE_CHARS = 6000  # a bigger record almost certainly means a failed split
REQUIRED = ("article_number", "text_ar", "text_en", "is_repealed", "citation", "source_page")


def validate_records(records: list[dict], known_issues: dict[str, list[str]] | None = None) -> list[str]:
    """Return a list of human-readable problems (empty list == corpus is valid).

    `known_issues` maps article number (str) to documented source defects, e.g. an
    article missing from the Arabic column of the source PDF. Those are *explained*
    gaps; anything else is an error.
    """
    known_issues = known_issues or {}
    errors: list[str] = []
    if not records:
        return ["corpus is empty"]
    numbers = [r["article_number"] for r in records]
    if len(numbers) != len(set(numbers)):
        errors.append("duplicate article numbers")
    if numbers != sorted(numbers):
        errors.append("articles are not sorted by article_number")
    expected = set(range(min(numbers), max(numbers) + 1))
    missing = sorted(expected - set(numbers))
    if missing:
        errors.append(f"unexplained gaps in article numbers: {missing[:15]}")
    for r in records:
        n = r["article_number"]
        for key in REQUIRED:
            if key not in r:
                errors.append(f"article {n}: missing field {key}")
        if not isinstance(n, int):
            errors.append(f"article {n}: article_number must be int")
        explained = str(n) in known_issues
        if not r.get("text_ar", "").strip() and not explained:
            errors.append(f"article {n}: empty text_ar")
        if not r.get("text_en", "").strip() and not explained:
            errors.append(f"article {n}: empty text_en")
        for key in ("text_ar", "text_en"):
            if len(r.get(key, "")) > MAX_ARTICLE_CHARS:
                errors.append(f"article {n}: {key} is {len(r[key])} chars (failed split?)")
    repealed = {r["article_number"] for r in records if r["is_repealed"]}
    if not repealed:
        errors.append("no repealed articles flagged (expected 54-80 and 389-417)")
    return errors
