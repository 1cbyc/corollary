"""Text matching helpers used for citations and numeric provenance checks."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

_WS = re.compile(r"\s+")
# Matches 4.1, 4,100,000,000, -3.5, .5, 1e9 and similar; the thousands separators are stripped later.
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")
# A unit right after a number says how the number is scaled: "4.1 billion", "$4.1B", "9.76%".
_UNIT = re.compile(
    r"\s?(%|per\s?cent\b|pct\b|thousand\b|k\b|million\b|mn\b|mm\b|m\b|billion\b|bn\b|b\b|trillion\b|tn\b|t\b)",
    re.IGNORECASE,
)
_UNIT_SCALES: dict[str, float] = {
    "%": 100.0,
    "percent": 100.0,
    "per cent": 100.0,
    "pct": 100.0,
    "thousand": 1e-3,
    "k": 1e-3,
    "million": 1e-6,
    "mn": 1e-6,
    "mm": 1e-6,
    "m": 1e-6,
    "billion": 1e-9,
    "bn": 1e-9,
    "b": 1e-9,
    "trillion": 1e-12,
    "tn": 1e-12,
    "t": 1e-12,
}
# Without a unit, a number may still be scaled by a table header ("in millions"), so magnitudes are
# allowed; a percentage needs a percent sign or word.
_BARE_SCALES = (1.0, 1e-3, 1e-6, 1e-9, 1e-12)
_SCALES = (*_BARE_SCALES, 100.0)
# Dates, times and ordinals contain digits that aren't figures: "2026-03-25", "10:45", "15th".
_NOT_FIGURES = re.compile(
    r"\b\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b"
    r"|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b"
    r"|\b\d{1,2}:\d{2}(?::\d{2})?\b"
    r"|\b\d+(?:st|nd|rd|th)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Figure:
    """A number found in text, with its stated precision and the scales its unit allows."""

    value: float
    decimals: int
    scales: tuple[float, ...] = _BARE_SCALES


def normalize(text: str) -> str:
    """Lowercase, unify quotes, dashes and minus signs, and collapse whitespace."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace("−", "-").replace(" ", " ")
    return _WS.sub(" ", text).strip().lower()


def contains_quote(document: str, quote: str) -> bool:
    """Whether ``quote`` appears in ``document`` after normalization."""
    q = normalize(quote)
    return bool(q) and q in normalize(document)


def figures_in(text: str, *, skip_dates: bool = False) -> list[Figure]:
    """Every number in ``text``, with the scales its unit allows ("4.1 billion" -> 1e-9).

    With ``skip_dates``, dates, times and ordinals are left out.
    """
    text = text.replace("−", "-")
    if skip_dates:
        text = _NOT_FIGURES.sub(" ", text)
    found: list[Figure] = []
    for match in _NUMBER.finditer(text):
        raw = match.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:  # pragma: no cover - the regex only matches parseable numbers
            continue
        mantissa = raw.lower().split("e")[0]
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        unit = _UNIT.match(text, match.end())
        if unit is not None:
            name = _WS.sub(" ", unit.group(1).lower())
            found.append(Figure(value, decimals, (1.0, _UNIT_SCALES[name])))
        else:
            found.append(Figure(value, decimals))
    return found


def numbers_in(text: str) -> list[tuple[float, int]]:
    """Every number in ``text`` as ``(value, decimals)``, where ``decimals`` is the stated precision."""
    return [(f.value, f.decimals) for f in figures_in(text)]


def number_matches(
    stated: float, decimals: int, candidates: Iterable[float], scales: Iterable[float] = _SCALES
) -> bool:
    """Whether ``stated`` (written with ``decimals`` places) is a rounding of any candidate at any
    of ``scales``, so ``4.1`` matches ``4_100_000_000`` at ``1e-9`` ("4.1 billion")."""
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    scales = tuple(scales)
    for candidate in candidates:
        for scale in scales:
            scaled = candidate * scale
            # Signs are ignored: "revenue fell 3.5%" legitimately states a value of -3.5.
            if math.isfinite(scaled) and abs(abs(scaled) - abs(stated)) <= tolerance:
                return True
    return False


def figure_matches(figure: Figure, candidates: Iterable[float]) -> bool:
    """Whether ``figure`` states one of ``candidates``, at a scale its unit allows."""
    return number_matches(figure.value, figure.decimals, candidates, figure.scales)


def value_in_text(value: Any, text: str) -> bool:
    """Whether ``value`` is stated in ``text``: as a number (at a scale its unit allows), or as a
    word or phrase."""
    if isinstance(value, bool):
        return _contains_phrase(text, str(value))
    if isinstance(value, (int, float)):
        return any(figure_matches(f, [float(value)]) for f in figures_in(text))
    if isinstance(value, str):
        return _contains_phrase(text, value)
    return False


def _contains_phrase(text: str, phrase: str) -> bool:
    """``phrase`` in ``text`` after normalization, not as part of a longer word ("false" is not in
    "falsehood")."""
    p = normalize(phrase)
    if not p:
        return False
    return re.search(rf"(?<!\w){re.escape(p)}(?!\w)", normalize(text)) is not None
