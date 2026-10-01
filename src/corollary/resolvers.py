"""Built-in conflict resolution policies.

A resolver is any callable ``(conflict, kb) -> Resolution | None``. Pass one to
:meth:`BeliefBase.resolve_conflicts` or to ``Agent(resolver=...)``. Returning ``None`` leaves the
conflict open, which is always a safe choice: a conflicted key is simply unusable until resolved.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from .belief import Belief
from .conflict import Conflict, ConflictKind, Resolution

if TYPE_CHECKING:
    from .kernel import BeliefBase


def _keep_one(conflict: Conflict, keep: Belief, reason: str) -> Resolution:
    return Resolution(conflict.id, tuple(b.ref for b in conflict.beliefs if b.ref != keep.ref), reason)


class PreferHigherConfidence:
    """Keep the side with the highest effective confidence; ties go to the newest revision.

    For constraint conflicts, retract the least confident of the constrained beliefs. Returns
    ``None`` if the best two sides are within ``margin`` of each other, leaving close calls open.
    """

    def __init__(self, margin: float = 0.0) -> None:
        self.margin = margin

    def __call__(self, conflict: Conflict, kb: BeliefBase) -> Resolution | None:
        ranked = sorted(conflict.beliefs, key=lambda b: (kb.confidence(b.ref), b.created_at, b.revision), reverse=True)
        if len(ranked) > 1 and kb.confidence(ranked[0].ref) - kb.confidence(ranked[1].ref) < self.margin:
            return None
        if conflict.kind is ConflictKind.CONSTRAINT:
            weakest = ranked[-1]
            return Resolution(conflict.id, (weakest.ref,), f"least confident side of {conflict.id}")
        return _keep_one(conflict, ranked[0], f"kept the most confident side of {conflict.id}")


class PreferNewest:
    """Keep the most recently created belief (useful when sources report a moving value)."""

    def __call__(self, conflict: Conflict, kb: BeliefBase) -> Resolution | None:
        ranked = sorted(conflict.beliefs, key=lambda b: (b.created_at, b.revision), reverse=True)
        if conflict.kind is ConflictKind.CONSTRAINT:
            return Resolution(conflict.id, (ranked[-1].ref,), f"oldest side of {conflict.id}")
        return _keep_one(conflict, ranked[0], f"kept the newest side of {conflict.id}")


class PreferSource:
    """Keep the side whose source ranks highest.

    ``order`` lists source kinds or exact sources, most trusted first, e.g.
    ``["human", "tool:sec_filings", "tool", "document"]``. Defaults to the belief base's
    ``TrustPolicy.source_rank``. Returns ``None`` when the top two sides rank equally.
    """

    def __init__(self, order: Sequence[str] | None = None) -> None:
        self.order = tuple(order) if order is not None else None

    def _rank(self, belief: Belief, kb: BeliefBase) -> int:
        if self.order is None:
            return kb.trust.rank(belief.source)
        exact = f"{belief.source.kind.value}:{belief.source.name}"
        for i, entry in enumerate(self.order):
            if entry in (exact, belief.source.kind.value):
                return i
        return len(self.order)

    def __call__(self, conflict: Conflict, kb: BeliefBase) -> Resolution | None:
        ranked = sorted(conflict.beliefs, key=lambda b: self._rank(b, kb))
        if len(ranked) > 1 and self._rank(ranked[0], kb) == self._rank(ranked[1], kb):
            return None
        if conflict.kind is ConflictKind.CONSTRAINT:
            return Resolution(conflict.id, (ranked[-1].ref,), f"lowest-ranked source in {conflict.id}")
        return _keep_one(conflict, ranked[0], f"kept the highest-ranked source in {conflict.id}")


class AskHuman:
    """Delegate the decision to a callback, e.g. a CLI prompt or a review queue.

    The callback receives the conflict and returns the belief (or ref) to *keep*, or ``None`` to
    leave the conflict open. For constraint conflicts it should return the belief to *retract*.
    """

    def __init__(self, ask: Callable[[Conflict], Belief | str | None]) -> None:
        self.ask = ask

    def __call__(self, conflict: Conflict, kb: BeliefBase) -> Resolution | None:
        choice = self.ask(conflict)
        if choice is None:
            return None
        ref = choice.ref if isinstance(choice, Belief) else choice
        if ref not in conflict.refs:
            matches = [b.ref for b in conflict.beliefs if b.key == ref]
            if len(matches) != 1:
                raise ValueError(f"{ref!r} does not identify one side of {conflict.id}")
            ref = matches[0]
        if conflict.kind is ConflictKind.CONSTRAINT:
            return Resolution(conflict.id, (ref,), f"retracted by human decision on {conflict.id}")
        return Resolution(conflict.id, tuple(r for r in conflict.refs if r != ref), f"human decision on {conflict.id}")
