from __future__ import annotations

import pytest

from corollary import Belief, InvalidKeyError, Source, SourceKind
from corollary.belief import format_value, make_ref, parse_ref, validate_key, values_equal


@pytest.mark.parametrize("key", ["revenue:Q2", "growth(Q3/Q2)", "a", "answer:2", "x.y-z_w"])
def test_valid_keys(key: str) -> None:
    assert validate_key(key) == key


@pytest.mark.parametrize("key", ["", "has space", "a@b", "{x}", "tab\there", "new\nline"])
def test_invalid_keys(key: str) -> None:
    with pytest.raises(InvalidKeyError):
        validate_key(key)


def test_refs_roundtrip() -> None:
    assert make_ref("revenue:Q2", 3) == "revenue:Q2@3"
    assert parse_ref("revenue:Q2@3") == ("revenue:Q2", 3)
    assert parse_ref("revenue:Q2") == ("revenue:Q2", None)
    assert parse_ref("weird@") == ("weird@", None)


def test_source_parse_and_str() -> None:
    src = Source.parse("tool:sec_filings")
    assert src.kind is SourceKind.TOOL and src.name == "sec_filings" and src.grounded
    assert str(Source.tool("get_revenue", {"quarter": "Q2"})) == "tool:get_revenue(quarter='Q2')"
    assert str(Source.parse("human:alice")) == "human:alice"
    assert not Source.model("claude").grounded
    assert Source.parse(src) is src


@pytest.mark.parametrize("bad", ["nocolon", "alien:thing", "tool:"])
def test_source_parse_rejects(bad: str) -> None:
    with pytest.raises(ValueError):
        Source.parse(bad)


def test_source_equality_includes_detail() -> None:
    assert Source.tool("t", {"a": 1}) == Source.tool("t", {"a": 1})
    assert Source.tool("t", {"a": 1}) != Source.tool("t", {"a": 2})
    assert Source.document("doc", quote="q").quote == "q"


def test_values_equal_tolerates_float_noise() -> None:
    assert values_equal(0.1 + 0.2, 0.3)
    assert not values_equal(1.0, 1.001)
    assert values_equal("a", "a") and not values_equal("a", "b")
    assert values_equal(1, 1.0)


@pytest.mark.parametrize(
    ("value", "text"),
    [(4.1e9, "4,100,000,000"), (9.756097, "9.7561"), (3, "3"), ("x", "'x'"), (True, "True"), (None, "None")],
)
def test_format_value(value: object, text: str) -> None:
    assert format_value(value) == text


def test_belief_serialization_roundtrip() -> None:
    belief = Belief("k", 1.5, Source.tool("t", {"q": 1}), revision=2, claim="c", confidence=0.7, metadata={"m": 1})
    again = Belief.from_dict(belief.to_dict())
    assert again == belief
    assert belief.ref == "k@2"
    assert belief.text == "c"
    assert Belief("k", 2, Source.human()).text == "k = 2"
