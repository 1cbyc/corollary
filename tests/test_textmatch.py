from __future__ import annotations

import pytest

from corollary.textmatch import contains_quote, normalize, numbers_in, value_in_text


def test_normalize() -> None:
    assert normalize("  It’s   “Q2” — up ") == 'it\'s "q2" - up'


def test_contains_quote_ignores_case_and_spacing() -> None:
    doc = "Total revenue\nfor the quarter was $4.3 billion."
    assert contains_quote(doc, "total revenue for the   quarter")
    assert not contains_quote(doc, "net revenue")
    assert not contains_quote(doc, "   ")


def test_numbers_in() -> None:
    assert numbers_in("Revenue of 4,100,000,000 grew 9.76% in Q3 of 2026, from -3.5 and 1e9") == [
        (4100000000.0, 0),
        (9.76, 2),
        (2026.0, 0),
        (-3.5, 1),
        (1e9, 0),
    ]


@pytest.mark.parametrize(
    ("value", "text", "expected"),
    [
        (4.1e9, "revenue was $4.1 billion", True),
        (4.1e9, "revenue was 4,100,000,000", True),
        (0.0976, "grew 9.76%", True),
        (9.7561, "grew 9.76%", True),
        (9.7561, "grew 9.8%", True),
        (9.7561, "grew 9.70%", False),
        (-3.5, "fell 3.5%", True),
        (4.3e9, "revenue was $4.1 billion", False),
        ("Austin", "Headquartered in austin, TX", True),
        ("Boston", "Headquartered in Austin", False),
        (True, "Flag: true", True),
        ([1], "1", False),
    ],
)
def test_value_in_text(value: object, text: str, expected: bool) -> None:
    assert value_in_text(value, text) is expected
