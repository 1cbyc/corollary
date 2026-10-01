from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest

from corollary import ContractViolation, Tool, TrustPolicy, tool


@tool(trust="medium", ttl=timedelta(minutes=5))
def quote(symbol: str, venue: Literal["nyse", "nasdaq"] = "nyse", depth: int | None = None) -> float:
    """Latest price for a symbol.

    More details that are not part of the description.
    """
    return 10.0


def test_decorator_options() -> None:
    assert isinstance(quote, Tool)
    assert quote.name == "quote"
    assert quote.description == "Latest price for a symbol."
    assert quote.trust == "medium" and quote.ttl == timedelta(minutes=5)
    assert quote("ACME") == 10.0


def test_bare_decorator_and_overrides() -> None:
    @tool
    def plain(x):  # type: ignore[no-untyped-def]
        return x

    @tool(name="renamed", description="custom")
    def other() -> None: ...

    assert plain.name == "plain" and plain.describe() == "plain(x)"
    assert other.name == "renamed" and other.description == "custom"


def test_schema_from_annotations() -> None:
    schema = quote.parameters_schema()
    assert schema["required"] == ["symbol"]
    assert schema["properties"]["symbol"] == {"type": "string"}
    assert schema["properties"]["venue"] == {"enum": ["nyse", "nasdaq"]}
    assert schema["properties"]["depth"] == {"type": "integer"}


def test_describe() -> None:
    assert quote.describe().startswith("quote(symbol: str, venue: ")
    assert quote.describe().endswith("-> float: Latest price for a symbol.")


def test_bind_validates_and_applies_defaults() -> None:
    assert quote.bind({"symbol": "ACME"}) == {"symbol": "ACME", "venue": "nyse", "depth": None}
    with pytest.raises(ContractViolation, match="invalid arguments"):
        quote.bind({"ticker": "ACME"})


def test_default_key() -> None:
    assert quote.default_key({"symbol": "ACME", "venue": "nyse"}) == "quote:ACME,nyse"
    assert quote.default_key({"symbol": "A B@{c}"}) == "quote:A_B_c_"

    @tool
    def now() -> str:
        return "t"

    assert now.default_key({}) == "now"


def test_trust_levels() -> None:
    trust = TrustPolicy()
    assert trust.tool_confidence("high") == 0.99
    assert trust.tool_confidence(0.5) == 0.5
    with pytest.raises(ValueError):
        trust.tool_confidence("extreme")
    with pytest.raises(ValueError):
        trust.tool_confidence(2.0)


def test_trust_policy_lookup() -> None:
    trust = TrustPolicy.from_mapping({"tool": 0.8, "human:alice": 1.0})
    assert trust.confidence_for("tool:x") == 0.8
    assert trust.confidence_for("human:alice") == 1.0
    assert trust.confidence_for("human:bob") == 0.99
    with pytest.raises(ValueError):
        TrustPolicy(sources={"tool": 1.5})
