"""Text matching helpers used for citations and numeric provenance checks."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from typing import Any

_WS = re.compile(r"\s+")
# Matches 4.1, 4,100,000,000, -3.5, 1e9 and similar; the thousands separators are stripped later.
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?")
_SCALES = (1.0, 1e-3, 1e-6, 1e-9, 1e-12, 100.0)


def normalize(text: str) -> str:
    """Lowercase, unify quotes and dashes, and collapse whitespace."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-").replace(" ", " ")
    return _WS.sub(" ", text).strip().lower()


def contains_quote(document: str, quote: str) -> bool:
    """Whether ``quote`` appears in ``document`` after normalization."""
    q = normalize(quote)
    return bool(q) and q in normalize(document)


def numbers_in(text: str) -> list[tuple[float, int]]:
    """Every number in ``text`` as ``(value, decimals)``, where ``decimals`` is the stated precision."""
    found: list[tuple[float, int]] = []
    for match in _NUMBER.finditer(text):
        raw = match.group(0).replace(",", "")
        try:
            value = float(raw)
        except ValueError:  # pragma: no cover - the regex only matches parseable numbers
            continue
        mantissa = raw.lower().split("e")[0]
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        found.append((value, decimals))
    return found


def number_matches(stated: float, decimals: int, candidates: Iterable[float]) -> bool:
    """Whether ``stated`` (written with ``decimals`` places) is a rounding of any candidate.

    Candidates are also tried at common scales, so ``4.1`` matches ``4_100_000_000`` ("4.1 billion")
    and ``9.76`` matches ``0.0976`` ("9.76%").
    """
    tolerance = 0.5 * 10 ** (-decimals) + 1e-9
    for candidate in candidates:
        for scale in _SCALES:
            scaled = candidate * scale
            # Signs are ignored: "revenue fell 3.5%" legitimately states a value of -3.5.
            if math.isfinite(scaled) and abs(abs(scaled) - abs(stated)) <= tolerance:
                return True
    return False


def value_in_text(value: Any, text: str) -> bool:
    """Whether ``value`` is stated in ``text``: as a number (any common scale) or as a substring."""
    if isinstance(value, bool):
        return normalize(str(value)) in normalize(text)
    if isinstance(value, (int, float)):
        return any(number_matches(n, d, [float(value)]) for n, d in numbers_in(text))
    if isinstance(value, str):
        v = normalize(value)
        return bool(v) and v in normalize(text)
    return False
