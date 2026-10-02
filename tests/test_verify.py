from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from corollary import BeliefBase, Proof, Severity, VerificationError
from corollary.verify import (
    ArithmeticCheck,
    CitationCheck,
    GroundingCheck,
    NumericProvenanceCheck,
    StructureCheck,
    TemporalCheck,
)

from .conftest import Clock


def failures(report: object, check: str) -> list[str]:
    return [r.message for r in report.results if r.check == check and not r.passed]  # type: ignore[attr-defined]


def test_clean_proof_passes(revenue_kb: BeliefBase) -> None:
    report = revenue_kb.proof("trend:Q3").verify(revenue_kb)
    assert report.ok and bool(report)
    assert {r.check for r in report.results} == {
        "structure",
        "grounding",
        "arithmetic",
        "citation",
        "temporal",
        "provenance",
    }
    assert "PASSED" in str(report)
    assert report.raise_for_errors() is report


def test_stale_proof_fails_structure(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3")
    revenue_kb.retract("revenue:Q2", reason="restated")
    report = proof.verify(revenue_kb, checks=[StructureCheck()])
    assert not report.ok
    assert any("no longer believed (retracted: restated)" in m for m in failures(report, "structure"))
    with pytest.raises(VerificationError):
        report.raise_for_errors()


def test_structure_detects_missing_antecedent(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("trend:Q3")
    broken = Proof(proof.roots, tuple(s for s in proof.steps if s.belief.key != "revenue:Q3"))
    assert any("missing from the proof" in m for m in failures(broken.verify(checks=[StructureCheck()]), "structure"))


def test_grounding_flags_assumptions_and_model_premises(kb: BeliefBase) -> None:
    kb.assume("market_size", 1e9)
    kb.assert_("guess", 5, source="model:llm")
    kb.derive("both", lambda a, b: a + b, "market_size", "guess")
    report = kb.proof("both").verify(kb, checks=[GroundingCheck()])
    severities = sorted(r.severity.value for r in report.results if not r.passed)
    assert severities == ["error", "warning"]
    assert not report.ok


def test_arithmetic_detects_tampering(kb: BeliefBase) -> None:
    kb.assert_("a", 2)
    kb.assert_("b", 3)
    kb.justify("c", 6, antecedents=["a", "b"], source="model:m", formula="{a} * {b}")
    proof = kb.proof("c")
    tampered_step = replace(proof.steps[-1], belief=replace(proof.steps[-1].belief, value=7))
    tampered = Proof(proof.roots, (*proof.steps[:-1], tampered_step))
    assert ArithmeticCheck().run(proof, _ctx(kb))[0].passed
    report = tampered.verify(kb, checks=[ArithmeticCheck()])
    assert any("but the belief states 7" in m for m in failures(report, "arithmetic"))


def test_arithmetic_replays_rules(revenue_kb: BeliefBase) -> None:
    proof = revenue_kb.proof("growth:Q3_vs_Q2")
    step = proof.steps[-1]
    tampered = Proof(proof.roots, (*proof.steps[:-1], replace(step, belief=replace(step.belief, value=1.0))))
    report = tampered.verify(revenue_kb, checks=[ArithmeticCheck()])
    assert any("replays to" in m for m in failures(report, "arithmetic"))
    # without the rule registry the replay is only a warning
    report = proof.verify(checks=[ArithmeticCheck()])
    assert report.ok and report.warnings


def test_citations(kb: BeliefBase) -> None:
    kb.add_document("10-K", "Revenue was $4.3 billion in Q2.")
    kb.cite("revenue:Q2", 4.3e9, document="10-K", quote="Revenue was $4.3 billion")
    proof = kb.proof("revenue:Q2")
    assert proof.verify(kb, checks=[CitationCheck()]).ok
    # The document changed after the citation was recorded.
    kb.add_document("10-K", "Revenue was restated.")
    assert any("quote not found" in m for m in failures(proof.verify(kb, checks=[CitationCheck()]), "citation"))
    # Without the document the citation cannot be checked: a warning, not an error.
    report = proof.verify(checks=[CitationCheck()])
    assert report.ok and report.warnings[0].severity is Severity.WARNING


def test_temporal_detects_expired_evidence(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 10, ttl=timedelta(minutes=1))
    proof = kb.proof("price")
    assert proof.verify(kb, checks=[TemporalCheck()]).ok
    report = proof.verify(kb, checks=[TemporalCheck()], at=clock.now + timedelta(minutes=2))
    assert any("expired" in m for m in failures(report, "temporal"))


def test_numeric_provenance_warns_on_unsupported_numbers(kb: BeliefBase) -> None:
    kb.assert_("revenue:Q2", 4.3e9, source="tool:t")
    kb.assert_("revenue:Q3", 4.5e9, source="tool:t")
    kb.justify(
        "summary",
        "ok",
        antecedents=["revenue:Q2", "revenue:Q3"],
        source="model:m",
        claim="Revenue rose from $4.3 billion to $4.5 billion in 2026, beating the $4.4 billion consensus.",
    )
    report = kb.proof("summary").verify(kb, checks=[NumericProvenanceCheck()])
    assert report.ok  # warnings only
    assert [w.message for w in report.warnings] == ["states 4.4, which does not follow from its antecedents"]


def test_custom_checks_and_report_text(revenue_kb: BeliefBase) -> None:
    class AlwaysFails:
        name = "custom"

        def run(self, proof, ctx):  # type: ignore[no-untyped-def]
            from corollary import CheckResult

            return [CheckResult(self.name, False, "nope")]

    report = revenue_kb.proof("trend:Q3").verify(revenue_kb, checks=[AlwaysFails()])
    assert not report.ok
    assert "FAILED" in str(report) and "FAIL custom" in str(report)


def _ctx(kb: BeliefBase):  # type: ignore[no-untyped-def]
    from corollary.verify import VerificationContext

    return VerificationContext(at=kb.now(), kb=kb, documents=kb.documents, rules=kb.rules)


def test_numeric_provenance_accepts_identifiers_and_names(kb: BeliefBase) -> None:
    kb.assert_("order:1043:item", "Coffee grinder 4000", source="tool:oms")
    kb.assert_("order:1043:days_left", 13, source="tool:oms")
    kb.justify(
        "answer",
        "ok",
        antecedents=["order:1043:item", "order:1043:days_left"],
        source="model:m",
        claim="Your Coffee grinder 4000 (order 1043) has 13 days left, not 2500.",
    )
    report = kb.proof("answer").verify(kb, checks=[NumericProvenanceCheck()])
    assert [w.message for w in report.warnings] == ["states 2500, which does not follow from its antecedents"]
