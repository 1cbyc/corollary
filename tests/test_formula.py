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
        ("abs((-4) ** 0.5)", "real number"),
        ("9" * 400, "cannot evaluate"),
        ("(((9 ** 64) ** 64) ** 64) ** 64", "cannot evaluate"),
        ("-" * 1500 + "1", "deeper than"),
        ("1e309", "finite"),
        ("0 * 1e309", "finite"),
        ("_v0 + {n}", "unknown name '_v0'"),
    ],
)
def test_rejects(formula: str, message: str) -> None:
    with pytest.raises(FormulaError, match=message):
        evaluate(formula, VALUES)


def test_formula_keys_in_order_without_duplicates() -> None:
    assert formula_keys("{b} + {a} * {b}") == ["b", "a"]
    assert formula_keys("1 + 2") == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 10**400])
def test_rejects_values_that_are_not_finite_floats(value: float) -> None:
    with pytest.raises(FormulaError, match=r"finite|too large"):
        evaluate("{x} * 2", {"x": value})


def test_placeholder_keys_may_look_like_internal_names() -> None:
    assert evaluate("{x_v1} + 1", {"x_v1": 2}) == 3
