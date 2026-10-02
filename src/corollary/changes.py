"""Change records produced when the belief base is relabeled."""

from __future__ import annotations

import enum
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, overload

from .belief import Belief

if TYPE_CHECKING:
    from .conflict import Conflict


class ChangeKind(str, enum.Enum):
    IN = "IN"
    """The belief became believed (asserted, derived, re-derived or restored)."""
    OUT = "OUT"
    """The belief stopped being believed (retracted, lost support, expired or defeated)."""
    KEPT = "KEPT"
    """A derived belief that survived unaffected. Reported only with ``include_kept=True``."""

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Change:
    """One entry in a propagation diff."""

    kind: ChangeKind
    belief: Belief
    reason: str

    @property
    def key(self) -> str:
        return self.belief.key

    @property
    def ref(self) -> str:
        return self.belief.ref

    def __str__(self) -> str:
        return f"{self.kind.value:<4} {self.belief.key:<24} ({self.reason})"


@dataclass(frozen=True)
class Pending:
    """A derived belief that is ``OUT`` and could not be re-derived yet, with the reason."""

    belief: Belief
    reason: str

    def __str__(self) -> str:
        return f"PEND {self.belief.key:<24} ({self.reason})"


@dataclass
class Propagation(Sequence[Change]):
    """Result of :meth:`BeliefBase.propagate`: what changed, what is waiting, what conflicts.

    Iterating yields :class:`Change` objects in the order they happened, so the classic usage is::

        for change in kb.propagate():
            print(change)

    Like any sequence, it is falsy when there are no changes, even if beliefs are still pending or
    conflicts are open; check :attr:`settled` for that.
    """

    changes: list[Change] = field(default_factory=list)
    pending: list[Pending] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    rederived: list[Belief] = field(default_factory=list)

    @overload
    def __getitem__(self, index: int) -> Change: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Change]: ...

    def __getitem__(self, index: int | slice) -> Change | Sequence[Change]:
        return self.changes[index]

    def __len__(self) -> int:
        return len(self.changes)

    def __iter__(self) -> Iterator[Change]:
        return iter(self.changes)

    def of_kind(self, kind: ChangeKind) -> list[Change]:
        return [c for c in self.changes if c.kind is kind]

    @property
    def retracted(self) -> list[Change]:
        """Changes of kind ``OUT``."""
        return self.of_kind(ChangeKind.OUT)

    @property
    def added(self) -> list[Change]:
        """Changes of kind ``IN``."""
        return self.of_kind(ChangeKind.IN)

    @property
    def kept(self) -> list[Change]:
        return self.of_kind(ChangeKind.KEPT)

    @property
    def settled(self) -> bool:
        """True when nothing is waiting to be re-derived and no conflict is open."""
        return not self.pending and not self.conflicts

    def __str__(self) -> str:
        lines = [str(c) for c in self.changes]
        lines += [str(p) for p in self.pending]
        lines += [f"CONF {c.subject:<24} ({c.description})" for c in self.conflicts]
        return "\n".join(lines) if lines else "(no changes)"
