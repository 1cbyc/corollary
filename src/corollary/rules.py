"""Deterministic rules: derivations that the runtime can recompute without a model."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, overload


@dataclass(frozen=True)
class Rule:
    """A named, pure function from antecedent values to a derived value.

    Rules are the cheapest kind of justification: when an input changes, :meth:`BeliefBase.propagate`
    re-runs them automatically, and the verifier replays them to check a proof.

    Rules must be deterministic and side-effect free. Their *name* is what gets stored in the
    belief graph, so a persisted belief base can be reloaded and re-linked to the same rules.
    """

    name: str
    fn: Callable[..., Any]
    confidence: float = 1.0
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a rule needs a name")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"rule confidence must be between 0 and 1, got {self.confidence}")

    def __call__(self, *args: Any) -> Any:
        return self.fn(*args)


@overload
def rule(fn: Callable[..., Any], /) -> Rule: ...


@overload
def rule(
    *, name: str | None = None, confidence: float = 1.0, description: str | None = None
) -> Callable[[Callable[..., Any]], Rule]: ...


def rule(
    fn: Callable[..., Any] | None = None,
    /,
    *,
    name: str | None = None,
    confidence: float = 1.0,
    description: str | None = None,
) -> Rule | Callable[[Callable[..., Any]], Rule]:
    """Turn a function into a :class:`Rule`.

    Usable bare (``@rule``) or with options (``@rule(name="growth", confidence=0.99)``). The
    decorated object stays callable.

    >>> @rule
    ... def growth(previous: float, current: float) -> float:
    ...     return (current - previous) / previous * 100
    >>> growth(100.0, 125.0)
    25.0
    """

    def wrap(func: Callable[..., Any]) -> Rule:
        doc = description if description is not None else (func.__doc__ or "").strip().split("\n")[0]
        return Rule(name=name or func.__name__, fn=func, confidence=confidence, description=doc)

    return wrap(fn) if fn is not None else wrap
