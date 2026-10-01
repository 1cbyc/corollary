from __future__ import annotations

import pytest

from corollary import BeliefBase, Proof, Status


def test_proof_structure(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3")
    keys = [s.belief.key for s in proof]
    assert keys == ["revenue:Q2", "revenue:Q3", "growth:Q3_vs_Q2", "trend:Q3"]
    assert proof.roots == ("trend:Q3@1",)
    assert [s.belief.key for s in proof.premises] == ["revenue:Q2", "revenue:Q3"]
    assert [s.belief.key for s in proof.derived] == ["growth:Q3_vs_Q2", "trend:Q3"]
    assert proof.valid
    assert "revenue:Q2" in proof and "revenue:Q2@1" in proof and "fx:exposure" not in proof
    assert proof.step("growth:Q3_vs_Q2").antecedents == ("revenue:Q2@1", "revenue:Q3@1")
    with pytest.raises(KeyError):
        proof.step("nope")


def test_render_tree(revenue_kb: BeliefBase) -> None:
    text = revenue_kb.proof("trend:Q3").render()
    lines = text.splitlines()
    assert lines[0].startswith("trend:Q3 = 'modest'  [IN 0.95]  rule:trend")
    assert lines[1].startswith("└── growth:Q3_vs_Q2")
    assert lines[2].startswith("    ├── revenue:Q2 = 4,300,000,000")
    ascii_text = revenue_kb.proof("trend:Q3").render(ascii=True)
    assert "`-- growth" in ascii_text and "└" not in ascii_text


def test_render_marks_shared_subproofs(kb: BeliefBase) -> None:
    kb.assert_("a", 1)
    kb.derive("b", lambda v: v + 1, "a")
    kb.derive("c", lambda v: v * 2, "b")
    kb.derive("d", lambda x, y: x + y, "b", "c")
    text = kb.proof("d").render(show_sources=False)
    assert "(see above)" in text


def test_multiple_roots(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3", "risk:fx")
    assert len(proof.roots) == 2
    assert {s.belief.key for s in proof.premises} == {"revenue:Q2", "revenue:Q3", "fx:exposure"}


def test_proof_of_out_belief_records_status(revenue_kb: BeliefBase) -> None:
    revenue_kb.retract("revenue:Q2")
    proof = revenue_kb.proof("trend:Q3")
    assert not proof.valid
    assert proof.step("trend:Q3").status is Status.OUT


def test_json_roundtrip(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3")
    again = Proof.from_json(proof.to_json())
    assert again == proof
    assert proof.to_dict()["format"] == "corollary.proof"


def test_mermaid_and_dot(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3")
    mermaid = proof.to_mermaid()
    assert mermaid.startswith("flowchart BT")
    assert '-->|"rule:growth"|' in mermaid
    dot = proof.to_dot()
    assert dot.startswith("digraph proof {") and "->" in dot


def test_diff(revenue_kb: BeliefBase) -> None:
    before = revenue_kb.proof("trend:Q3")
    revenue_kb.retract("revenue:Q2")
    revenue_kb.assert_("revenue:Q2", 4.1e9, source="tool:get_revenue")
    revenue_kb.propagate()
    after = revenue_kb.proof("trend:Q3")
    diff = before.diff(after)
    changed = {k for k, _, _ in diff.changed}
    assert changed == {"revenue:Q2", "growth:Q3_vs_Q2", "trend:Q3"}
    assert not diff.empty and "~ trend:Q3: 'modest' -> 'strong'" in str(diff)
    assert before.diff(before).empty and str(before.diff(before)) == "(identical)"


def test_proof_requires_a_target(kb: BeliefBase) -> None:
    with pytest.raises(ValueError):
        kb.proof()
