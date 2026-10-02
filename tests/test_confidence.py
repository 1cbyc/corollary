"""Confidence: learned reliability, corroboration, decay, and how they combine."""

from __future__ import annotations

from datetime import timedelta

import pytest

from corollary import (
    AskHuman,
    BeliefBase,
    PreferHigherConfidence,
    Status,
    TrustLedger,
    TrustPolicy,
    rule,
)

from .conftest import Clock

ident = rule(lambda v: v, name="ident", confidence=0.9)


# -- corroboration -------------------------------------------------------------------------------


def test_independent_sources_combine_by_noisy_or(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")  # 0.95
    assert kb.confidence("x") == pytest.approx(0.95)
    kb.assert_("x", 1, source="human:alice")  # 0.99
    # The confirmation is also a success for both sources: (prior * 10 + 1) / 11 each.
    tool, human = (0.95 * 10 + 1) / 11, (0.99 * 10 + 1) / 11
    assert kb.confidence("x") == pytest.approx(1 - (1 - tool) * (1 - human))


def test_sources_sharing_an_origin_count_once(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a", origin="sec_database")
    kb.assert_("x", 1, source="tool:b", origin="sec_database")
    assert kb.confidence("x") == pytest.approx(0.95)
    assert kb.ledger.sources() == [], "same origin: not an independent confirmation"


def test_same_source_twice_counts_once(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 1, source="tool:a")
    assert kb.confidence("x") == pytest.approx(0.95)


def test_corroboration_can_be_disabled() -> None:
    kb = BeliefBase(trust=TrustPolicy(corroboration=False))
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 1, source="human:alice")
    assert kb.confidence("x") == pytest.approx((0.99 * 10 + 1) / 11), "the best single source"


def test_independent_confirmation_credits_both_sources(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 1, source="human:alice")
    assert kb.ledger.record_of("tool:a").correct == 1
    assert kb.ledger.record_of("human:alice").correct == 1


def test_strongest_derivation_wins(kb: BeliefBase) -> None:
    kb.assume("hunch", 1)  # 0.6
    kb.assert_("fact", 1, source="tool:a")  # 0.95
    kb.derive("c", ident, "hunch")
    assert kb.confidence("c") == pytest.approx(0.9 * 0.6)
    kb.derive("c", ident, "fact")
    assert kb.confidence("c") == pytest.approx(0.9 * 0.95)


@pytest.mark.parametrize("first", ["p", "q"])
def test_support_cycles_do_not_inflate_confidence(kb: BeliefBase, first: str) -> None:
    kb.assert_("seed", 1, source="tool:a")
    kb.derive("p", ident, "seed")
    kb.derive("q", ident, "p")
    kb.derive("p", ident, "q")  # p and q now also support each other
    order = [first, "q" if first == "p" else "p"]
    values = {key: kb.confidence(key) for key in order}
    assert values["p"] == pytest.approx(0.9 * 0.95)
    assert values["q"] == pytest.approx(0.9 * 0.9 * 0.95)


# -- learning from outcomes -------------------------------------------------------------------------


def test_retract_blamed_on_the_source_lowers_its_reliability(kb: BeliefBase) -> None:
    kb.assert_("price:a", 10, source="tool:scraper")
    kb.assert_("price:b", 20, source="tool:scraper")
    kb.retract("price:a", reason="wrong price", fault="source")
    assert kb.ledger.record_of("tool:scraper").wrong == 1
    assert kb.confidence("price:b") == pytest.approx(0.95 * 10 / 11)
    assert kb.reliability("tool:scraper") == pytest.approx(0.95 * 10 / 11)


def test_retract_without_fault_teaches_nothing(kb: BeliefBase) -> None:
    kb.assert_("revenue", 4.3e9, source="tool:sec")
    kb.retract("revenue", reason="restated")
    assert kb.ledger.sources() == []


def test_fault_validation(kb: BeliefBase) -> None:
    kb.assert_("a", 1, source="tool:a")
    kb.derive("b", ident, "a")
    with pytest.raises(ValueError, match="fault must be"):
        kb.retract("a", fault="everyone")
    with pytest.raises(ValueError, match="no source is at fault"):
        kb.retract("b", fault="source")
    kb.justify("c", 1, antecedents=["a"], source="model:m", formula="{a}")
    with pytest.raises(ValueError, match="no source is at fault"):
        kb.retract("c", fault="source")


def test_wrong_model_judgement_lowers_the_model(kb: BeliefBase) -> None:
    kb.assert_("growth", 4.65, source="tool:a")
    kb.justify("trend", "modest", antecedents=["growth"], source="model:m")
    kb.justify("risk", "low", antecedents=["growth"], source="model:m")
    assert kb.confidence("risk") == pytest.approx(0.9 * 0.95)
    kb.retract("trend", fault="source")
    assert kb.ledger.record_of("model:m").wrong == 1
    assert kb.confidence("risk") == pytest.approx(0.9 * 10 / 11 * 0.95)


def test_stated_certainty_scales_model_steps(kb: BeliefBase) -> None:
    kb.assert_("g", 1, source="tool:a")
    kb.justify("t", "x", antecedents=["g"], source="model:m", confidence=0.5)
    assert kb.confidence("t") == pytest.approx(0.9 * 0.5 * 0.95)


def test_authoritative_resolution_teaches_the_ledger(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:b")
    (conflict,) = kb.conflicts()
    kb.resolve(conflict, keep="x@2", learn=True)
    assert kb.ledger.record_of("tool:a").wrong == 1
    assert kb.ledger.record_of("tool:b").correct == 1


def test_policy_resolution_does_not_learn(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="human:alice")
    kb.resolve_conflicts(PreferHigherConfidence())
    assert kb.ledger.sources() == []


def test_ask_human_teaches_the_ledger(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.assert_("x", 2, source="tool:b")
    kb.resolve_conflicts(AskHuman(lambda c: "x@1"))
    assert kb.ledger.record_of("tool:b").wrong == 1
    assert kb.ledger.record_of("tool:a").correct == 1
    kb2 = BeliefBase()
    kb2.assert_("x", 1, source="tool:a")
    kb2.assert_("x", 2, source="tool:b")
    kb2.resolve_conflicts(AskHuman(lambda c: "x@1", learn=False))
    assert kb2.ledger.sources() == []


def test_external_outcomes(kb: BeliefBase) -> None:
    kb.assert_("eta", "Tuesday", source="tool:carrier")
    for _ in range(10):
        kb.record_outcome("tool:carrier", False, reason="late delivery")
    assert kb.confidence("eta") == pytest.approx(0.95 * 10 / 20)


def test_a_shared_ledger_learns_across_belief_bases() -> None:
    ledger = TrustLedger()
    alice, bob = BeliefBase(ledger=ledger), BeliefBase(ledger=ledger)
    alice.assert_("order:1", "shipped", source="tool:orders")
    bob.assert_("order:2", "shipped", source="tool:orders")
    alice.retract("order:1", fault="source")
    assert bob.confidence("order:2") == pytest.approx(0.95 * 10 / 11)


# -- decay --------------------------------------------------------------------------------------------


def test_evidence_fades_with_its_half_life(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 101.5, source="tool:quote", half_life=timedelta(minutes=1))
    kb.derive("expensive", rule(lambda p: p > 100, name="gt100"), "price")
    assert kb.confidence("price") == pytest.approx(0.95)
    clock.advance(seconds=30)
    assert kb.confidence("price") == pytest.approx(0.95 * 0.5**0.5)
    clock.advance(seconds=30)
    assert kb.confidence("price") == pytest.approx(0.475)
    assert kb.confidence("expensive") == pytest.approx(0.475), "conclusions are only as fresh as their inputs"
    assert kb.status("price") is Status.IN, "decay never changes status"
    assert "half-life" in kb.explain("price")


def test_renewal_restores_freshness(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 10, source="tool:quote", half_life=timedelta(minutes=1))
    clock.advance(minutes=2)
    assert kb.confidence("price") == pytest.approx(0.95 / 4)
    kb.assert_("price", 10, source="tool:quote", half_life=timedelta(minutes=1))
    assert kb.confidence("price") == pytest.approx(0.95)
    assert kb.latest("price").revision == 1


def test_faded_lists_beliefs_below_the_threshold(clock: Clock) -> None:
    kb = BeliefBase(clock=clock, trust=TrustPolicy(min_confidence=0.5))
    kb.assert_("price", 10, source="tool:quote", half_life=timedelta(minutes=1))
    kb.assert_("hq", "Austin", source="tool:registry")
    assert kb.faded() == []
    clock.advance(seconds=70)
    assert [b.key for b in kb.faded()] == ["price"]
    assert kb.faded(threshold=0.1) == []


def test_half_life_validation(kb: BeliefBase) -> None:
    with pytest.raises(ValueError, match="half_life"):
        kb.assert_("x", 1, half_life=timedelta(0))


def test_decay_and_learning_combine(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 10, source="tool:quote", half_life=timedelta(minutes=1))
    kb.record_outcome("tool:quote", False)
    clock.advance(minutes=1)
    assert kb.confidence("price") == pytest.approx(0.95 * 10 / 11 * 0.5)


# -- caching and persistence -----------------------------------------------------------------------


def test_cache_tracks_graph_ledger_and_time_changes(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("a", 1, source="tool:a")
    kb.derive("b", ident, "a")
    assert kb.confidence("b") == pytest.approx(0.9 * 0.95)
    kb.record_outcome("tool:a", False)
    assert kb.confidence("b") == pytest.approx(0.9 * 0.95 * 10 / 11)
    kb.assert_("a", 1, source="human:alice")
    assert kb.confidence("b") > 0.9 * 0.95 * 10 / 11
    kb.retract("a")
    assert kb.confidence("b") == 0.0


def test_owned_ledger_is_saved_with_the_base(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="tool:a")
    kb.record_outcome("tool:a", False)
    loaded = BeliefBase.from_dict(kb.to_dict())
    assert loaded.ledger.record_of("tool:a").wrong == 1
    assert loaded.confidence("x") == pytest.approx(kb.confidence("x"))


def test_shared_ledger_is_not_saved_with_the_base() -> None:
    ledger = TrustLedger()
    kb = BeliefBase(ledger=ledger)
    kb.assert_("x", 1, source="tool:a")
    data = kb.to_dict()
    assert "ledger" not in data
    assert BeliefBase.from_dict(data, ledger=ledger).ledger is ledger


def test_half_life_survives_persistence(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 10, source="tool:quote", half_life=timedelta(minutes=1))
    loaded = BeliefBase.from_dict(kb.to_dict(), clock=clock)
    clock.advance(minutes=1)
    assert loaded.confidence("price") == pytest.approx(0.475)


def test_version_1_snapshots_are_migrated(kb: BeliefBase) -> None:
    kb.assert_("g", 1, source="tool:a")
    kb.justify("t", "x", antecedents=["g"], source="model:m", confidence=0.5)
    kb.justify("h", 1, antecedents=["g"], source="model:m", formula="{g}")
    data = kb.to_dict()
    data["version"] = 1
    data.pop("ledger")
    for j in data["justifications"]:  # version 1 folded the model's trust into confidence
        if j["kind"] == "model" and not j["formula"]:
            j["confidence"] *= 0.9
    loaded = BeliefBase.from_dict(data)
    assert loaded.confidence("t") == pytest.approx(kb.confidence("t"))
    assert loaded.confidence("h") == pytest.approx(kb.confidence("h"))


# -- caching ---------------------------------------------------------------------------------------


def test_editing_the_trust_policy_in_place_updates_confidence(kb: BeliefBase) -> None:
    kb.assert_("x", 1, source="human:alice")
    kb.justify("y", 2, antecedents=["x"], source="model:m")  # model steps read the policy live
    assert kb.confidence("y") == pytest.approx(0.9 * 0.99)
    kb.trust.overrides["model:m"] = 0.5
    assert kb.confidence("y") == pytest.approx(0.5 * 0.99)


def test_a_forgetting_ledger_updates_confidence_as_time_passes(clock: Clock) -> None:
    kb = BeliefBase(clock=clock, ledger=TrustLedger(memory_half_life=timedelta(days=1)))
    kb.assert_("x", 1, source="tool:a")
    kb.retract("x", fault="source")
    kb.assert_("y", 1, source="tool:a")
    shaken = kb.confidence("y")
    assert shaken < 0.95
    clock.advance(days=30)  # the mistake is all but forgotten
    assert kb.confidence("y") == pytest.approx(0.95, abs=1e-6)
    assert kb.reliability("tool:a") == pytest.approx(kb.confidence("y"))


def test_the_ledger_cache_stays_small_and_fresh(clock: Clock) -> None:
    ledger = TrustLedger(memory_half_life=timedelta(days=1))
    ledger.record("tool:a", False, at=clock())
    for _ in range(100):
        clock.advance(hours=1)
        ledger.reliability("tool:a", prior=0.9, at=clock())
    assert len(ledger._cache) == 1
    first = ledger.reliability("tool:a", prior=0.9)  # at=None means now, so never cached
    assert ledger.reliability("tool:a", prior=0.9) == pytest.approx(first)


def test_confidence_of_a_long_chain_is_linear(kb: BeliefBase, monkeypatch: pytest.MonkeyPatch) -> None:
    kb.assert_("n0", 1, source="tool:a")
    kb.assert_("n1", 1, source="tool:a")
    for i in range(2, 1000):  # every node depends on the previous two
        kb.derive(f"n{i}", lambda a, b: 1, f"n{i - 1}", f"n{i - 2}")
    calls = 0
    original = kb._node_confidence

    def counting(*args: object) -> float:
        nonlocal calls
        calls += 1
        return original(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(kb, "_node_confidence", counting)
    kb.confidence("n999")
    assert calls <= 2 * 1000
