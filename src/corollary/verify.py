"""Deterministic verification of proofs.

Every check here is ordinary code. Nothing asks a model whether an answer is right: arithmetic is
re-executed, rules are replayed, citations are span-matched against the source documents,
validity windows are checked against the clock, and every leaf must trace back to a tool, a
document or a person.

Write your own check by implementing the :class:`Check` protocol and passing it to
:class:`Verifier` (or ``report.verify(checks=[...])``).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .belief import SourceKind, Status, format_value, utcnow, values_equal
from .errors import FormulaError, VerificationError
from .formula import evaluate
from .justification import JustificationKind
from .proof import Proof, ProofStep
from .rules import Rule
from .textmatch import contains_quote, figure_matches, figures_in, numbers_in, value_in_text

if TYPE_CHECKING:
    from .kernel import BeliefBase


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CheckResult:
    check: str
    passed: bool
    message: str
    ref: str | None = None
    severity: Severity = Severity.ERROR

    def __str__(self) -> str:
        mark = "ok  " if self.passed else ("FAIL" if self.severity is Severity.ERROR else "warn")
        where = f"{self.ref}: " if self.ref else ""
        return f"  {mark} {self.check:<12} {where}{self.message}"


@dataclass(frozen=True)
class VerificationContext:
    """What a check may consult besides the proof itself."""

    at: datetime
    kb: BeliefBase | None = None
    documents: Mapping[str, str] = field(default_factory=dict)
    rules: Mapping[str, Rule] = field(default_factory=dict)


@runtime_checkable
class Check(Protocol):
    name: str

    def run(self, proof: Proof, ctx: VerificationContext) -> Iterable[CheckResult]: ...


@dataclass(frozen=True)
class VerificationReport:
    """Outcome of verifying a proof. Truthy when there are no failing *errors*."""

    results: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[CheckResult]:
        return [r for r in self.results if not r.passed and r.severity is Severity.WARNING]

    def __bool__(self) -> bool:
        return self.ok

    def raise_for_errors(self) -> VerificationReport:
        """Raise :class:`VerificationError` if any check failed; return ``self`` otherwise."""
        if not self.ok:
            raise VerificationError("proof failed verification:\n" + "\n".join(str(r) for r in self.errors))
        return self

    def __str__(self) -> str:
        checks = len({r.check for r in self.results})
        verdict = "PASSED" if self.ok else "FAILED"
        head = f"Verification {verdict}: {checks} checks, {len(self.errors)} errors, {len(self.warnings)} warnings"
        return "\n".join([head, *(str(r) for r in self.results)])


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


def _summarize(name: str, failures: list[CheckResult], ok_message: str) -> list[CheckResult]:
    return failures or [CheckResult(name, True, ok_message)]


def _antecedent_steps(step: ProofStep, by_ref: Mapping[str, ProofStep]) -> list[ProofStep]:
    return [by_ref[a] for a in step.antecedents if a in by_ref]


class StructureCheck:
    """Every antecedent is part of the proof, every step was ``IN``, and (given a belief base)
    every step is *still* ``IN``, so a stale answer cannot pass."""

    name = "structure"

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        by_ref = proof.by_ref
        failures = []
        for step in proof:
            for a in step.antecedents:
                if a not in by_ref:
                    failures.append(
                        CheckResult(self.name, False, f"antecedent {a} is missing from the proof", step.ref)
                    )
            if step.status is not Status.IN:
                failures.append(CheckResult(self.name, False, "was OUT when the proof was taken", step.ref))
            elif ctx.kb is not None and step.ref in ctx.kb._nodes and ctx.kb.status(step.ref) is not Status.IN:
                failures.append(
                    CheckResult(self.name, False, f"is no longer believed ({ctx.kb.why_out(step.ref)})", step.ref)
                )
        return _summarize(self.name, failures, f"all {_n(len(proof), 'step')} are well-formed and IN")


class GroundingCheck:
    """Every leaf is grounded in a tool, a document or a person, not in the model's say-so.

    Assumptions produce a warning; model-asserted premises are errors.
    """

    name = "grounding"

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        failures = []
        for step in proof.premises:
            source = (
                step.justification.source if step.justification and step.justification.source else step.belief.source
            )
            if source.grounded:
                continue
            if source.kind is SourceKind.ASSUMPTION:
                failures.append(
                    CheckResult(self.name, False, f"rests on an assumption ({source})", step.ref, Severity.WARNING)
                )
            else:
                failures.append(CheckResult(self.name, False, f"ungrounded premise from {source}", step.ref))
        return _summarize(
            self.name, failures, f"all {_n(len(proof.premises), 'premise')} trace to tools, documents or people"
        )


class ArithmeticCheck:
    """Re-executes every formula and replays every rule against the antecedent values."""

    name = "arithmetic"

    def __init__(self, rel_tol: float = 1e-6) -> None:
        self.rel_tol = rel_tol

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        by_ref = proof.by_ref
        failures: list[CheckResult] = []
        checked = 0
        for step in proof.derived:
            j = step.justification
            assert j is not None
            antecedents = _antecedent_steps(step, by_ref)
            if j.formula:
                checked += 1
                try:
                    computed = evaluate(j.formula, {s.belief.key: s.belief.value for s in antecedents})
                except FormulaError as exc:
                    failures.append(CheckResult(self.name, False, str(exc), step.ref))
                    continue
                if not values_equal(computed, step.belief.value, rel_tol=self.rel_tol, abs_tol=1e-9):
                    failures.append(
                        CheckResult(
                            self.name,
                            False,
                            f"{j.formula} = {format_value(computed)}, "
                            f"but the belief states {format_value(step.belief.value)}",
                            step.ref,
                        )
                    )
            if j.kind is JustificationKind.RULE:
                checked += 1
                rule = ctx.rules.get(j.rule or "")
                if rule is None:
                    failures.append(
                        CheckResult(
                            self.name, False, f"rule {j.rule!r} unavailable; cannot replay", step.ref, Severity.WARNING
                        )
                    )
                    continue
                try:
                    replayed = rule(*(s.belief.value for s in antecedents))
                except Exception as exc:
                    failures.append(
                        CheckResult(self.name, False, f"rule {j.rule!r} raised {exc!r} on replay", step.ref)
                    )
                    continue
                if not values_equal(replayed, step.belief.value, rel_tol=self.rel_tol, abs_tol=1e-9):
                    failures.append(
                        CheckResult(
                            self.name,
                            False,
                            f"rule {j.rule!r} replays to {format_value(replayed)}, "
                            f"not {format_value(step.belief.value)}",
                            step.ref,
                        )
                    )
        return _summarize(self.name, failures, f"{_n(checked, 'computation')} re-executed and matched")


class CitationCheck:
    """Every cited quote appears in its document and states the cited value."""

    name = "citation"

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        failures = []
        checked = 0
        for step in proof.premises:
            j = step.justification
            source = j.source if j is not None and j.source is not None else step.belief.source
            if source.kind is not SourceKind.DOCUMENT:
                continue
            checked += 1
            quote = source.quote
            if not quote or not quote.strip():
                failures.append(
                    CheckResult(self.name, False, f"cites {source.name!r} without a quote", step.ref, Severity.WARNING)
                )
                continue
            text = ctx.documents.get(source.name)
            if text is None:
                failures.append(
                    CheckResult(
                        self.name,
                        False,
                        f"document {source.name!r} is not available to check",
                        step.ref,
                        Severity.WARNING,
                    )
                )
                continue
            if not contains_quote(text, quote):
                failures.append(CheckResult(self.name, False, f"quote not found in {source.name!r}", step.ref))
            elif isinstance(step.belief.value, (int, float, str)) and not value_in_text(step.belief.value, quote):
                failures.append(
                    CheckResult(self.name, False, f"quote does not state {format_value(step.belief.value)}", step.ref)
                )
        return _summarize(self.name, failures, f"{_n(checked, 'citation')} matched their documents")


class TemporalCheck:
    """No step relies on expired evidence, and no conclusion predates the beliefs it uses."""

    name = "temporal"

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        by_ref = proof.by_ref
        failures = []
        for step in proof:
            j = step.justification
            if j is None:
                continue
            if j.valid_until is not None and ctx.at >= j.valid_until:
                failures.append(
                    CheckResult(
                        self.name, False, f"evidence expired at {j.valid_until.isoformat(timespec='seconds')}", step.ref
                    )
                )
            for a in _antecedent_steps(step, by_ref):
                if j.created_at < a.belief.created_at:
                    failures.append(
                        CheckResult(self.name, False, f"justified before its antecedent {a.ref} existed", step.ref)
                    )
        return _summarize(self.name, failures, "all evidence is current and causally ordered")


class NumericProvenanceCheck:
    """Warns when a model-written claim states a number found nowhere in its support.

    This catches the model filling in a figure from its training data instead of from a belief.
    Numbers are matched with rounding, at the scale their unit states ("4.1 billion", "$4.1B" and
    "9.76%" match; "$4 million" does not match 4.3e9). Small integers, years, dates, times and
    ordinals are ignored to keep the check quiet on ordinary prose.
    """

    name = "provenance"

    def __init__(self, ignore_below: float = 13, ignore_years: bool = True) -> None:
        self.ignore_below = ignore_below
        self.ignore_years = ignore_years

    def _ignored(self, number: float, decimals: int) -> bool:
        if decimals == 0 and abs(number) < self.ignore_below:
            return True
        return self.ignore_years and decimals == 0 and 1900 <= number <= 2100

    def run(self, proof: Proof, ctx: VerificationContext) -> list[CheckResult]:
        by_ref = proof.by_ref
        failures = []
        for step in proof.derived:
            j = step.justification
            if j is None or j.kind is not JustificationKind.MODEL:
                continue
            text = step.belief.claim or (step.belief.value if isinstance(step.belief.value, str) else "")
            if not text:
                continue
            antecedents = _antecedent_steps(step, by_ref)
            # The step's own value counts only when a formula computed it; otherwise the model chose
            # it, and a claim restating a number the model made up would vouch for itself.
            values = [s.belief.value for s in antecedents] + ([step.belief.value] if j.formula else [])
            candidates = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
            # Numbers also count as supported when they appear in an antecedent's claim, key or text
            # value: identifiers ("order:1043:status") and names ("iPhone 15") aren't figures.
            context_text = [step.belief.key]
            for s in antecedents:
                context_text += [s.belief.claim, s.belief.key]
                if isinstance(s.belief.value, str):
                    context_text.append(s.belief.value)
            context_numbers = {n for text_part in context_text for n, _ in numbers_in(text_part)}
            for figure in figures_in(str(text), skip_dates=True):
                number = figure.value
                if self._ignored(number, figure.decimals):
                    continue
                if figure_matches(figure, candidates) or number in context_numbers:
                    continue
                failures.append(
                    CheckResult(
                        self.name,
                        False,
                        f"states {number:g}, which does not follow from its antecedents",
                        step.ref,
                        Severity.WARNING,
                    )
                )
        return _summarize(self.name, failures, "every number in model claims traces to its support")


DEFAULT_CHECKS: tuple[type[Check], ...] = (
    StructureCheck,
    GroundingCheck,
    ArithmeticCheck,
    CitationCheck,
    TemporalCheck,
    NumericProvenanceCheck,
)


class Verifier:
    """Runs a list of checks over a proof. With no arguments it runs every built-in check."""

    def __init__(self, checks: Sequence[Check] | None = None) -> None:
        self.checks: list[Check] = list(checks) if checks is not None else [cls() for cls in DEFAULT_CHECKS]

    def verify(self, proof: Proof, *, kb: BeliefBase | None = None, at: datetime | None = None) -> VerificationReport:
        """Run every check. ``at`` is the time to check validity against (default: now). A naive
        ``at`` is taken as UTC, unless the belief base itself runs on a naive clock."""
        if at is not None and at.tzinfo is None and (kb is None or kb.now().tzinfo is not None):
            at = at.replace(tzinfo=timezone.utc)
        ctx = VerificationContext(
            at=at or (kb.now() if kb is not None else utcnow()),
            kb=kb,
            documents=kb.documents if kb is not None else {},
            rules=kb.rules if kb is not None else {},
        )
        results: list[CheckResult] = []
        for check in self.checks:
            results.extend(check.run(proof, ctx))
        return VerificationReport(tuple(results))
