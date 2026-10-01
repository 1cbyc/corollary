"""Trust policy: how much each kind of source is believed."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .belief import Source, SourceKind

_DEFAULT_SOURCES: dict[str, float] = {
    SourceKind.HUMAN.value: 0.99,
    SourceKind.TOOL.value: 0.95,
    SourceKind.DOCUMENT.value: 0.9,
    SourceKind.MODEL.value: 0.9,
    SourceKind.ASSUMPTION.value: 0.6,
    SourceKind.RULE.value: 1.0,
}

_DEFAULT_TOOL_LEVELS: dict[str, float] = {"high": 0.99, "medium": 0.9, "low": 0.7}


@dataclass
class TrustPolicy:
    """Maps sources to confidence and sets the thresholds the runtime enforces.

    Lookup order for :meth:`confidence_for` is: an exact ``"kind:name"`` entry in ``overrides``,
    then the per-kind default in ``sources``.

    Attributes:
        sources: Base confidence per source kind (``"tool"``, ``"human"``, ...).
        tool_levels: Confidence for the symbolic ``trust=`` levels accepted by :func:`corollary.tool`.
        overrides: Exact per-source confidence, e.g. ``{"tool:sec_filings": 0.999, "human:alice": 1.0}``.
        min_confidence: Beliefs whose effective confidence is below this are hidden from the
            model by the projector.
        source_rank: Order used by :class:`~corollary.resolvers.PreferSource`, most trusted first.
    """

    sources: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_SOURCES))
    tool_levels: dict[str, float] = field(default_factory=lambda: dict(_DEFAULT_TOOL_LEVELS))
    overrides: dict[str, float] = field(default_factory=dict)
    min_confidence: float = 0.0
    source_rank: tuple[str, ...] = ("human", "tool", "document", "rule", "model", "assumption")

    def __post_init__(self) -> None:
        for table in (self.sources, self.tool_levels, self.overrides):
            for name, value in table.items():
                if not 0.0 <= value <= 1.0:
                    raise ValueError(f"confidence for {name!r} must be between 0 and 1, got {value}")

    def confidence_for(self, source: Source | str) -> float:
        src = Source.parse(source)
        exact = f"{src.kind.value}:{src.name}"
        if exact in self.overrides:
            return self.overrides[exact]
        return self.sources.get(src.kind.value, 0.5)

    def tool_confidence(self, trust: str | float) -> float:
        """Resolve a tool's ``trust`` setting (a level name or a number) to a confidence."""
        if isinstance(trust, (int, float)):
            if not 0.0 <= float(trust) <= 1.0:
                raise ValueError("tool trust must be between 0 and 1")
            return float(trust)
        try:
            return self.tool_levels[trust]
        except KeyError:
            levels = ", ".join(self.tool_levels)
            raise ValueError(f"unknown tool trust level {trust!r}; expected one of {levels} or a number") from None

    def rank(self, source: Source) -> int:
        """Position of ``source`` in ``source_rank`` (lower is more trusted)."""
        exact = f"{source.kind.value}:{source.name}"
        for i, entry in enumerate(self.source_rank):
            if entry in (exact, source.kind.value):
                return i
        return len(self.source_rank)

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> TrustPolicy:
        """Build a policy from a flat mapping mixing kinds and exact sources.

        >>> TrustPolicy.from_mapping({"tool": 0.9, "human:alice": 1.0}).confidence_for("human:alice")
        1.0
        """
        policy = cls()
        for name, value in data.items():
            (policy.overrides if ":" in name else policy.sources)[name] = value
        policy.__post_init__()
        return policy
