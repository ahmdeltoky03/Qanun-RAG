from qanun.arabic import (
    clean_display,
    light_stem,
    normalize_for_search,
    parse_article_number,
    strip_diacritics,
    to_western_digits,
)


def test_digits():
    assert to_western_digits("المادة ١٤٧") == "المادة 147"
    assert parse_article_number("مادة ( ٣٢ )") == 32


def test_diacritics_keep_hamza():
    assert strip_diacritics("مُسْؤُولًا") == "مسؤولا"
    assert "أ" in strip_diacritics("أَنْ") and "إ" in strip_diacritics("إِلَى")


def test_normalize_unifies_variants():
    assert normalize_for_search("الإِيجَار") == normalize_for_search("الايجار")
    assert normalize_for_search("المسئولية") == normalize_for_search("المسيولية")
    assert normalize_for_search("مدرسة") == normalize_for_search("مدرسه")


def test_clean_display_fixes_parens_and_comma():
    assert clean_display("(١( يسري القانون' بما") == "(١) يسري القانون، بما"
    assert clean_display(")٢ ( على أنه") == "(٢) على أنه"


def test_light_stem():
    assert light_stem("والعقود") == "عقود"
    assert light_stem("contracts") == "contract"
