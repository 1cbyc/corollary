"""Beliefs, their sources, and the small value helpers shared across the package."""

from __future__ import annotations

import enum
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .errors import InvalidKeyError

_KEY_PATTERN = re.compile(r"^[^\s@{}]+$")


def utcnow() -> datetime:
    """Timezone-aware current time in UTC. The default clock of a :class:`BeliefBase`."""
    return datetime.now(timezone.utc)


def validate_key(key: str) -> str:
    """Return ``key`` unchanged if it is a valid belief key, otherwise raise :class:`InvalidKeyError`.

    Keys are free-form identifiers such as ``revenue:Q2`` or ``growth(Q3/Q2)``. They may not be
    empty or contain whitespace, ``@`` (reserved for revision references) or braces (reserved for
    formula placeholders).
    """
    if not isinstance(key, str) or not _KEY_PATTERN.match(key):
        raise InvalidKeyError(
            f"invalid belief key {key!r}: keys must be non-empty and contain no whitespace, '@', '{{' or '}}'"
        )
    return key


def make_ref(key: str, revision: int) -> str:
    """Build the reference string ``key@revision`` that identifies one revision of a belief."""
    return f"{key}@{revision}"


def parse_ref(text: str) -> tuple[str, int | None]:
    """Split ``"key@3"`` into ``("key", 3)``; a bare key returns ``(key, None)``."""
    key, sep, rev = text.rpartition("@")
    if sep and rev.isdigit() and key:
        return key, int(rev)
    return text, None


def values_equal(a: Any, b: Any, *, rel_tol: float = 1e-9, abs_tol: float = 1e-12) -> bool:
    """Equality used to decide whether a re-derived value "changed".

    Numbers compare with a tight tolerance so floating-point noise does not cause spurious
    cascades; everything else compares with ``==``.
    """
    if _is_number(a) and _is_number(b):
        return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=abs_tol)
    try:
        return bool(a == b)
    except Exception:  # pragma: no cover - exotic objects with broken __eq__
        return False


def format_value(value: Any) -> str:
    """Human-friendly rendering used in change logs, proofs and explanations."""
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and abs(value) < 1e15:
            return f"{int(value):,}"
        return f"{value:.6g}"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, str):
        return repr(value) if len(value) <= 80 else repr(value[:77] + "...")
    return repr(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class Status(str, enum.Enum):
    """Label computed by the kernel for every belief."""

    IN = "IN"
    """The belief has at least one currently valid justification."""
    OUT = "OUT"
    """The belief has no valid justification, was retracted, or has expired."""

    def __str__(self) -> str:
        return self.value


class SourceKind(str, enum.Enum):
    """Where a belief came from. Tool, document and human sources are *grounded*."""

    TOOL = "tool"
    DOCUMENT = "document"
    HUMAN = "human"
    MODEL = "model"
    RULE = "rule"
    ASSUMPTION = "assumption"

    def __str__(self) -> str:
        return self.value


GROUNDED_KINDS = frozenset({SourceKind.TOOL, SourceKind.DOCUMENT, SourceKind.HUMAN})


@dataclass(frozen=True, eq=True)
class Source:
    """Provenance of a belief or justification.

    ``detail`` carries kind-specific data: tool call arguments (``args``) or a cited quote
    (``quote``). Construct with the helpers (``Source.tool(...)``) or parse a string such as
    ``"tool:sec_filings"`` or ``"human:alice"`` with :meth:`Source.parse`.
    """

    kind: SourceKind
    name: str
    detail: Mapping[str, Any] = field(default_factory=dict, compare=True, hash=False)

    # -- constructors ---------------------------------------------------------------------

    @classmethod
    def tool(cls, name: str, args: Mapping[str, Any] | None = None, *, origin: str | None = None) -> Source:
        detail: dict[str, Any] = {}
        if args:
            detail["args"] = dict(args)
        if origin:
            detail["origin"] = origin
        return cls(SourceKind.TOOL, name, detail)

    @classmethod
    def document(cls, name: str, quote: str | None = None, *, origin: str | None = None) -> Source:
        detail: dict[str, Any] = {}
        if quote:
            detail["quote"] = quote
        if origin:
            detail["origin"] = origin
        return cls(SourceKind.DOCUMENT, name, detail)

    @classmethod
    def human(cls, name: str = "user") -> Source:
        return cls(SourceKind.HUMAN, name)

    @classmethod
    def model(cls, name: str) -> Source:
        return cls(SourceKind.MODEL, name)

    @classmethod
    def rule(cls, name: str) -> Source:
        return cls(SourceKind.RULE, name)

    @classmethod
    def assumption(cls, name: str = "user") -> Source:
        return cls(SourceKind.ASSUMPTION, name)

    @classmethod
    def parse(cls, value: str | Source) -> Source:
        """Accept a :class:`Source` or a ``"kind:name"`` string."""
        if isinstance(value, Source):
            return value
        kind, sep, name = str(value).partition(":")
        if not sep or not name:
            raise ValueError(f"invalid source {value!r}: expected 'kind:name', e.g. 'tool:get_revenue'")
        try:
            return cls(SourceKind(kind.strip().lower()), name.strip())
        except ValueError:
            kinds = ", ".join(k.value for k in SourceKind)
            raise ValueError(f"invalid source kind {kind!r}: expected one of {kinds}") from None

    # -- properties -----------------------------------------------------------------------

    @property
    def grounded(self) -> bool:
        """True for tools, documents and humans: sources outside the model."""
        return self.kind in GROUNDED_KINDS

    @property
    def id(self) -> str:
        """``kind:name``: the identity under which a source's reliability is learned."""
        return f"{self.kind.value}:{self.name}"

    @property
    def origin(self) -> str:
        """Independence group. Sources with the same origin share an underlying origin of truth
        (two tools reading the same database), so their agreement counts once. Defaults to ``id``."""
        origin = self.detail.get("origin")
        return str(origin) if origin else self.id

    def with_origin(self, origin: str | None) -> Source:
        """A copy of this source declaring an independence group."""
        if not origin:
            return self
        return Source(self.kind, self.name, {**self.detail, "origin": origin})

    @property
    def args(self) -> dict[str, Any]:
        return dict(self.detail.get("args", {}))

    @property
    def quote(self) -> str | None:
        quote = self.detail.get("quote")
        return str(quote) if quote is not None else None

    def __str__(self) -> str:
        if self.kind is SourceKind.TOOL and self.detail.get("args"):
            args = ", ".join(f"{k}={v!r}" for k, v in self.detail["args"].items())
            return f"tool:{self.name}({args})"
        return f"{self.kind.value}:{self.name}"

    # -- serialization --------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "name": self.name, "detail": dict(self.detail)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Source:
        return cls(SourceKind(data["kind"]), data["name"], dict(data.get("detail", {})))


@dataclass(frozen=True)
class Belief:
    """One revision of a claim. Immutable.

    A belief's *status*, effective confidence and validity are not stored here: they are
    computed by the :class:`~corollary.BeliefBase` from the justification graph. Asserting a
    different value for an existing key creates a new revision (``key@2``) rather than mutating
    the old one, so proofs always point at exactly the values they used.
    """

    key: str
    value: Any
    source: Source
    revision: int = 1
    claim: str = ""
    confidence: float = 1.0
    created_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict, hash=False)

    @property
    def ref(self) -> str:
        """Unique reference to this revision, e.g. ``revenue:Q2@2``."""
        return make_ref(self.key, self.revision)

    @property
    def text(self) -> str:
        """The natural-language claim, or ``key = value`` when no claim text was given."""
        return self.claim or f"{self.key} = {format_value(self.value)}"

    def __str__(self) -> str:
        return f"{self.ref} = {format_value(self.value)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "revision": self.revision,
            "value": self.value,
            "claim": self.claim,
            "source": self.source.to_dict(),
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Belief:
        return cls(
            key=data["key"],
            value=data["value"],
            source=Source.from_dict(data["source"]),
            revision=int(data.get("revision", 1)),
            claim=data.get("claim", ""),
            confidence=float(data.get("confidence", 1.0)),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=dict(data.get("metadata", {})),
        )
