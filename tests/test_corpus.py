import re

import pytest

from qanun.corpus.parse import build_records
from qanun.corpus.validate import validate_records


def test_real_corpus_is_valid(records):
    report_known = {"1022": ["arabic_text_missing_in_source"]}
    assert validate_records(records, known_issues=report_known) == []


def test_corpus_shape(records):
    nums = [r["article_number"] for r in records]
    assert nums == list(range(1, 1150))
    by = {r["article_number"]: r for r in records}
    assert by[147]["text_ar"].startswith("(١) العقد شريعة المتعاقدين")
    assert "law of the parties" in by[147]["text_en"]
    assert by[147]["chapter"] == "Sources of Obligations"


def test_repealed_ranges(records):
    rep = sorted(r["article_number"] for r in records if r["is_repealed"])
    assert rep == list(range(54, 81)) + list(range(389, 418))
    assert all(not r["is_repealed"] for r in records if r["article_number"] in (53, 81, 388, 418))


def test_no_reversed_arabic(records):
    # extraction regressions show up as reversed words / broken lam-alef ligatures
    text = " ".join(r["text_ar"] for r in records if not r["is_repealed"])
    assert "الأهلية" in text and "ةيلهلأا" not in text
    assert "لا يجوز" in text  # lam-alef ligature must survive
    assert not re.search(r"(?<![\u0600-\u06FF])ال يجوز", text)  # standalone "ال" == a ligature that got reversed


@pytest.mark.parametrize("n", [1, 5, 163, 805, 1149])
def test_every_checked_article_has_both_languages(records, n):
    r = {x["article_number"]: x for x in records}[n]
    assert r["text_ar"].strip() and r["text_en"].strip()


def test_parser_handles_synthetic_two_column_input():
    en = [(2, "SECTION I", True), (2, "Laws", True), (2, "Article 1", False), (2, "First rule.", False),
          (2, "Article 2", False), (2, "Second rule.", False), (2, "Article 3 Third rule.", False)]  # fmt: skip
    ar = [(2, "باب تمهيدي", False), (2, "أحكام", False), (2, "مادة ( ١ (", False), (2, "القاعدة الأولى.", False),
          (2, "مادة ٢", False), (2, "القاعدة الثانية.", False), (2, "مادة ٣", False), (2, "القاعدة الثالثة.", False)]  # fmt: skip
    recs, report = build_records(en, ar)
    assert [r["article_number"] for r in recs] == [1, 2, 3]
    assert recs[2]["text_en"] == "Third rule." and recs[0]["text_ar"] == "القاعدة الأولى."
    assert report["source_issues"] == {}


def test_validator_flags_gaps_and_empty_text():
    recs = [
        {"article_number": 1, "text_ar": "أ", "text_en": "a", "is_repealed": False, "citation": "c", "source_page": 1},
        {"article_number": 3, "text_ar": "", "text_en": "c", "is_repealed": True, "citation": "c", "source_page": 1},
    ]
    errs = validate_records(recs)
    assert any("gaps" in e for e in errs) and any("empty text_ar" in e for e in errs)
