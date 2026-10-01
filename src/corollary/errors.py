"""Exception hierarchy. Every error Corollary raises derives from :class:`CorollaryError`."""

from __future__ import annotations

from collections.abc import Iterable


class CorollaryError(Exception):
    """Base class for all Corollary errors."""


class InvalidKeyError(CorollaryError, ValueError):
    """A belief key is empty or contains a reserved character (whitespace, ``@``, ``{``, ``}``)."""


class UnknownBeliefError(CorollaryError, KeyError):
    """No belief exists for the given key or reference."""

    def __str__(self) -> str:  # KeyError quotes its argument; keep the message readable.
        return str(self.args[0]) if self.args else "unknown belief"


class NotBelievedError(CorollaryError, LookupError):
    """The belief exists but is currently ``OUT``, so it cannot be used as support."""


class UnresolvedConflictError(CorollaryError, LookupError):
    """A key has several incompatible ``IN`` values; resolve the conflict before using it."""


class CircularDefeatError(CorollaryError):
    """A justification would make a belief depend on its own absence (an odd loop).

    Such a graph has no stable labeling, so the justification is rejected.
    """


class CitationError(CorollaryError, ValueError):
    """A cited quote does not appear in the referenced document."""


class FormulaError(CorollaryError, ValueError):
    """A formula is malformed, uses a forbidden construct, or cannot be evaluated."""


class RuleError(CorollaryError):
    """A rule is unknown, or raised while computing a derived value."""


class ContractViolation(CorollaryError):
    """A model response broke the claim contract. ``errors`` lists every problem found."""

    def __init__(self, errors: str | Iterable[str]) -> None:
        self.errors: list[str] = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


class ModelError(CorollaryError):
    """A model adapter failed to produce a usable response."""


class ModelRefusalError(ModelError):
    """The model declined the request (for example ``stop_reason == "refusal"``)."""


class VerificationError(CorollaryError):
    """Raised by :meth:`VerificationReport.raise_for_errors` when a proof fails verification."""
