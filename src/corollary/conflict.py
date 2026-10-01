"""Conflicts between beliefs, the constraints that detect them, and resolutions."""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .belief import Belief, format_value

if TYPE_CHECKING:
    from .proof import Proof


class ConflictKind(str, enum.Enum):
    VALUE = "value"
    """One key has two or more ``IN`` revisions with different values."""
    CONSTRAINT = "constraint"
    """A registered :class:`Constraint` is violated by the current ``IN`` values."""

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Constraint:
    """An invariant over the current values of several keys.

    ``predicate`` receives the current values of ``keys`` in order and returns ``True`` when they
    are consistent. It is only evaluated when every key has exactly one believed value.

    >>> Constraint("margin-bounded", ("gross_margin",), lambda m: 0 <= m <= 100)  # doctest: +ELLIPSIS
    Constraint(name='margin-bounded', ...)
    """

    name: str
    keys: tuple[str, ...]
    predicate: Callable[..., bool]
    description: str = ""


@dataclass(frozen=True)
class Conflict:
    """Two or more ``IN`` beliefs that cannot all hold, with the support chain behind each.

    Corollary never picks a side silently. A conflicted key is hidden from the model and cannot
    be used as support until the conflict is resolved, by :meth:`BeliefBase.resolve`, a
    resolver policy, or a human.
    """

    id: str
    kind: ConflictKind
    subject: str
    beliefs: tuple[Belief, ...]
    description: str
    proofs: tuple[Proof, ...] = field(default=(), compare=False, repr=False)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(b.key for b in self.beliefs))

    @property
    def refs(self) -> tuple[str, ...]:
        return tuple(b.ref for b in self.beliefs)

    def __str__(self) -> str:
        sides = "; ".join(f"{b.ref} = {format_value(b.value)} [{b.source}]" for b in self.beliefs)
        return f"Conflict({self.kind.value}: {self.subject}) {self.description}: {sides}"

    def explain(self) -> str:
        """Every side of the conflict with its full support chain."""
        parts = [str(self)]
        for proof in self.proofs:
            parts.append(proof.render())
        return "\n\n".join(parts)


@dataclass(frozen=True)
class Resolution:
    """What a resolver decided: which belief revisions to retract, and why.

    ``authoritative`` marks a decision as ground truth (a person checked it), so the trust ledger
    learns from it: retracted sides count as wrong, kept sides as right.
    """

    conflict_id: str
    retract: tuple[str, ...]
    reason: str
    authoritative: bool = False


Resolver = Callable[["Conflict", Any], "Resolution | None"]
"""A resolver receives a conflict and the belief base and returns a :class:`Resolution`, or
``None`` to leave the conflict open."""


def describe_values(beliefs: Sequence[Belief]) -> str:
    return ", ".join(format_value(b.value) for b in beliefs)
