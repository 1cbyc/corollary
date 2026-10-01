from __future__ import annotations

import pytest

from corollary import AskHuman, BeliefBase, PreferHigherConfidence, PreferNewest, PreferSource, TrustPolicy


def disputed(kb: BeliefBase) -> None:
    kb.assert_("revenue", 4.3e9, source="document:press_release")
    kb.assert_("revenue", 4.1e9, source="tool:sec_filings")


def test_prefer_higher_confidence(kb: BeliefBase) -> None:
    disputed(kb)
    (resolution,) = kb.resolve_conflicts(PreferHigherConfidence())
    assert resolution.retract == ("revenue@1",)
    assert kb.value("revenue") == 4.1e9


def test_prefer_higher_confidence_leaves_close_calls_open(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:b")
    assert kb.resolve_conflicts(PreferHigherConfidence(margin=0.01)) == []
    assert len(kb.conflicts()) == 1


def test_prefer_newest(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:a")
    kb.resolve_conflicts(PreferNewest())
    assert kb.value("x") == 2


def test_prefer_source_order(kb: BeliefBase) -> None:
    disputed(kb)
    kb.resolve_conflicts(PreferSource(["document", "tool"]))
    assert kb.value("revenue") == 4.3e9


def test_prefer_source_uses_trust_rank_by_default() -> None:
    kb = BeliefBase(trust=TrustPolicy(source_rank=("human", "tool:sec_filings", "tool", "document")))
    disputed(kb)
    kb.resolve_conflicts(PreferSource())
    assert kb.value("revenue") == 4.1e9


def test_prefer_source_tie_is_left_open(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:b")
    assert kb.resolve_conflicts(PreferSource()) == []


def test_ask_human(kb: BeliefBase) -> None:
    disputed(kb)
    seen = []

    def ask(conflict):  # type: ignore[no-untyped-def]
        seen.append(conflict.id)
        return "revenue@1"

    kb.resolve_conflicts(AskHuman(ask))
    assert seen == ["value:revenue"]
    assert kb.value("revenue") == 4.3e9


def test_ask_human_can_decline_and_validates(kb: BeliefBase) -> None:
    disputed(kb)
    assert kb.resolve_conflicts(AskHuman(lambda c: None)) == []
    with pytest.raises(ValueError):
        kb.resolve_conflicts(AskHuman(lambda c: "other"))


def test_constraint_resolution_retracts_weakest(kb: BeliefBase) -> None:
    kb.assert_("cost", 120, source="assumption:analyst")
    kb.assert_("price", 100, source="tool:pricing")
    kb.add_constraint("price>=cost", ["price", "cost"], lambda p, c: p >= c)
    (resolution,) = kb.resolve_conflicts(PreferHigherConfidence())
    assert resolution.retract == ("cost@1",)
    assert kb.conflicts() == []
