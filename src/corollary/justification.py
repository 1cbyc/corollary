"""Justifications: the edges of the belief graph."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .belief import Source, utcnow


class JustificationKind(str, enum.Enum):
    """How a justification was produced."""

    PREMISE = "premise"
    """Grounded directly in a source (tool, document, human or assumption). No antecedents."""
    RULE = "rule"
    """Computed by a deterministic Python rule. Re-derivable without a model."""
    MODEL = "model"
    """Proposed by a language model and accepted by the claim contract."""

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Justification:
    """A reason to believe a conclusion.

    A justification is *valid* when every antecedent is ``IN``, every key in ``unless`` has no
    ``IN`` revision, and it has not expired. A belief is ``IN`` exactly when it is not retracted
    and at least one of its justifications is valid.

    Antecedents are pinned to revisions (``revenue:Q2@1``): if ``revenue:Q2`` is later asserted
    with a new value, this justification does not silently start supporting the old conclusion
    again. ``inputs`` keeps the unpinned keys so the conclusion can be re-derived from whatever
    the current revisions are.

    ``confidence`` means the prior confidence in the source for a premise, and the certainty of
    the step for rules and model claims; source reliability and freshness are applied on top by
    :meth:`BeliefBase.confidence`.
    """

    id: str
    conclusion: str
    kind: JustificationKind
    antecedents: tuple[str, ...] = ()
    unless: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    source: Source | None = None
    rule: str | None = None
    formula: str | None = None
    confidence: float = 1.0
    valid_until: datetime | None = None
    half_life: timedelta | None = None
    note: str = ""
    created_at: datetime = field(default_factory=utcnow)

    @property
    def is_premise(self) -> bool:
        return self.kind is JustificationKind.PREMISE

    @property
    def rederivable(self) -> bool:
        """Whether the runtime knows how to recompute the conclusion from ``inputs``."""
        return self.kind in (JustificationKind.RULE, JustificationKind.MODEL)

    def freshness(self, now: datetime) -> float:
        """How much of its confidence this evidence keeps at ``now``: ``0.5 ** (age / half_life)``.

        Always 1.0 without a half-life. Freshness lowers confidence but never changes a belief's
        status; use ``valid_until`` for a hard cutoff.
        """
        if self.half_life is None:
            return 1.0
        age = max(0.0, (now - self.created_at).total_seconds())
        return float(0.5 ** (age / self.half_life.total_seconds()))

    def expired(self, now: datetime) -> bool:
        return self.valid_until is not None and now >= self.valid_until

    def describe(self) -> str:
        """Short label such as ``rule:growth``, ``model:claude`` or ``tool:get_revenue(...)``."""
        if self.kind is JustificationKind.RULE:
            return f"rule:{self.rule}"
        if self.source is not None:
            return str(self.source)
        return str(self.kind.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conclusion": self.conclusion,
            "kind": self.kind.value,
            "antecedents": list(self.antecedents),
            "unless": list(self.unless),
            "inputs": list(self.inputs),
            "source": self.source.to_dict() if self.source else None,
            "rule": self.rule,
            "formula": self.formula,
            "confidence": self.confidence,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "half_life": self.half_life.total_seconds() if self.half_life else None,
            "note": self.note,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Justification:
        return cls(
            id=data["id"],
            conclusion=data["conclusion"],
            kind=JustificationKind(data["kind"]),
            antecedents=tuple(data.get("antecedents", ())),
            unless=tuple(data.get("unless", ())),
            inputs=tuple(data.get("inputs", ())),
            source=Source.from_dict(data["source"]) if data.get("source") else None,
            rule=data.get("rule"),
            formula=data.get("formula"),
            confidence=float(data.get("confidence", 1.0)),
            valid_until=datetime.fromisoformat(data["valid_until"]) if data.get("valid_until") else None,
            half_life=timedelta(seconds=data["half_life"]) if data.get("half_life") else None,
            note=data.get("note", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
