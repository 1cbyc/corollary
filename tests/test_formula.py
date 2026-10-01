from __future__ import annotations

import pytest

from corollary import FormulaError
from corollary.formula import evaluate, formula_keys

VALUES = {"revenue:Q2": 4.3e9, "revenue:Q3": 4.5e9, "n": 4, "label": "text", "flag": True}


def test_evaluates_placeholders() -> None:
    result = evaluate("({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100", VALUES)
    assert result == pytest.approx(4.651162790697675)


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("2 ** 3", 8),
        ("-{n} + 1", -3),
        ("{n} // 3 + {n} % 3", 2),
        ("abs(-2) + max(1, {n}) + min(3, 4)", 9),
        ("round(3.14159, 2)", 3.14),
        ("sqrt(16) + exp(0) + log(1)", 5),
    ],
)
def test_arithmetic(formula: str, expected: float) -> None:
    assert evaluate(formula, VALUES) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("formula", "message"),
    [
        ("{missing} + 1", "not available"),
        ("{label} + 1", "non-numeric"),
        ("{flag} + 1", "non-numeric"),
        ("__import__('os')", "only these functions"),
        ("(1).real", "unsupported syntax"),
        ("[1, 2]", "unsupported syntax"),
        ("x + 1", "unknown name"),
        ("'a' * 3", "numeric literals"),
        ("2 ** 1000", "exponent"),
        ("1 / 0", "cannot evaluate"),
        ("1 +", "invalid formula"),
        ("max(a=1)", "only these functions"),
        ("1" * 3000, "longer than"),
        ("(-8) ** 0.5", "real number"),
    ],
)
def test_rejects(formula: str, message: str) -> None:
    with pytest.raises(FormulaError, match=message):
        evaluate(formula, VALUES)


def test_formula_keys_in_order_without_duplicates() -> None:
    assert formula_keys("{b} + {a} * {b}") == ["b", "a"]
    assert formula_keys("1 + 2") == []
