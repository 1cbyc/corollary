from __future__ import annotations

from corollary import BeliefBase, Projector, TrustPolicy, tool


@tool
def lookup(name: str, limit: int = 3) -> list[str]:
    """Find things."""
    return [name] * limit


def test_only_in_beliefs_are_visible(revenue_kb: BeliefBase) -> None:
    revenue_kb.retract("revenue:Q2", reason="restated")
    projection = Projector().project(revenue_kb, task="Assess growth")
    assert set(projection.keys) == {"revenue:Q3", "fx:exposure", "risk:fx"}
    assert "revenue:Q2" not in projection.text, "a retracted fact must be absent, not flagged"
    assert "4300000000" not in projection.text
    assert projection.belief("revenue:Q3") is not None and projection.belief("nope") is None
    assert len(projection.refs) == 3


def test_values_are_rendered_exactly(revenue_kb: BeliefBase) -> None:
    text = Projector().project(revenue_kb, task="t").text
    assert "- growth:Q3_vs_Q2 = 4.651162790697675" in text
    assert "source: tool:get_revenue" in text
    assert "source:" not in Projector(show_sources=False).project(revenue_kb, task="t").text


def test_conflicted_keys_are_hidden_and_listed(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:b")
    kb.assert_("y", 3)
    projection = Projector().project(kb, task="t")
    assert projection.keys == ("y",)
    assert "# Conflicts" in projection.text and "- x: 2 incompatible values" in projection.text


def test_low_confidence_beliefs_are_hidden() -> None:
    kb = BeliefBase(trust=TrustPolicy(min_confidence=0.7))
    kb.assume("hunch", 1)  # assumption confidence 0.6
    kb.assert_("fact", 2, source="tool:t")
    assert Projector().project(kb, task="t").keys == ("fact",)
    assert set(Projector(min_confidence=0.0).project(kb, task="t").keys) == {"hunch", "fact"}


def test_scope_and_limits(revenue_kb: BeliefBase) -> None:
    scoped = Projector().project(revenue_kb, task="t", scope=["revenue:Q2"])
    assert scoped.keys == ("revenue:Q2",)
    limited = Projector(max_beliefs=2).project(revenue_kb, task="t")
    assert len(limited.visible) == 2


def test_sections(kb: BeliefBase) -> None:
    kb.add_document("memo", "x" * 100)
    projection = Projector(max_document_chars=10).project(
        kb, task="Do it", tools=[lookup], feedback=["claim 'z' rejected"], instructions="Be brief."
    )
    text = projection.text
    assert text.startswith("# Task\nDo it")
    assert "# Instructions\nBe brief." in text
    assert "# Beliefs\n(none yet)" in text
    assert "- lookup(name: str, limit: int = 3) -> list[str]: Find things." in text
    assert "## memo\nxxxxxxxxxx\n[... truncated at 10 characters]" in text
    assert "# Runtime feedback" in text and "claim 'z' rejected" in text
    assert "# Documents" not in Projector().project(kb, task="t", include_documents=False).text
