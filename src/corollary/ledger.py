"""The trust ledger: how reliable each source has actually been.

Default confidences ("a tool is 0.95") are guesses. The ledger replaces them with measurements.
Every time a source is shown to be right or wrong (a retraction blamed on it, a conflict a person
settled, an independent confirmation, a model's formula that did or did not check out), the outcome
is recorded here, and the source's reliability is re-estimated:

    reliability = (prior * prior_weight + weighted correct) / (prior_weight + weighted total)

With no recorded outcomes, reliability equals the prior, so a fresh ledger changes nothing. With
``memory_half_life`` set, older outcomes weigh less, so a source that was fixed is gradually
forgiven, and a source not seen in a while drifts back toward its prior.

A ledger can be shared by many belief bases (for example, one per customer), because how reliable
an API is should be learned across all of them.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .belief import Source, utcnow

_FORMAT = "corollary.trustledger"
_FORMAT_VERSION = 1


def source_id(source: Source | str) -> str:
    """The identity reliability is tracked under: ``kind:name``, without call arguments."""
    if isinstance(source, Source):
        return f"{source.kind.value}:{source.name}"
    src = Source.parse(source)
    return f"{src.kind.value}:{src.name}"


@dataclass(frozen=True)
class Outcome:
    """One observation of a source being right or wrong."""

    at: datetime
    correct: bool
    reason: str = ""


@dataclass(frozen=True)
class SourceRecord:
    """Summary of a source's track record at a point in time."""

    source: str
    correct: int
    wrong: int
    weighted_correct: float
    weighted_total: float
    last_outcome: datetime | None

    @property
    def total(self) -> int:
        return self.correct + self.wrong


class TrustLedger:
    """Learns how reliable each source is from recorded outcomes.

    Args:
        prior_weight: How many observations the prior is worth. With the default of 10, a source
            needs a few dozen outcomes before its history clearly outweighs the default.
        memory_half_life: If set, an outcome's weight halves every ``memory_half_life``, so old
            mistakes (and old successes) gradually stop counting.
        max_history: Outcomes kept per source; the oldest are dropped beyond this.
    """

    def __init__(
        self,
        *,
        prior_weight: float = 10.0,
        memory_half_life: timedelta | None = None,
        max_history: int = 10_000,
    ) -> None:
        if prior_weight <= 0:
            raise ValueError("prior_weight must be positive")
        if memory_half_life is not None and memory_half_life.total_seconds() <= 0:
            raise ValueError("memory_half_life must be positive")
        if max_history < 1:
            raise ValueError("max_history must be at least 1")
        self.prior_weight = float(prior_weight)
        self.memory_half_life = memory_half_life
        self.max_history = max_history
        self._outcomes: dict[str, list[Outcome]] = {}
        self._cache: dict[tuple[str, datetime | None], tuple[float, float]] = {}
        self.version = 0
        """Incremented on every change, so callers can invalidate derived caches."""

    # -- recording -------------------------------------------------------------------------

    def record(self, source: Source | str, correct: bool, *, at: datetime | None = None, reason: str = "") -> None:
        """Record that ``source`` was right (``correct=True``) or wrong."""
        sid = source_id(source)
        history = self._outcomes.setdefault(sid, [])
        history.append(Outcome(at or utcnow(), bool(correct), reason))
        if len(history) > self.max_history:
            del history[: len(history) - self.max_history]
        self._changed()

    def reset(self, source: Source | str | None = None) -> None:
        """Forget the history of one source, or of every source."""
        if source is None:
            self._outcomes.clear()
        else:
            self._outcomes.pop(source_id(source), None)
        self._changed()

    def _changed(self) -> None:
        self._cache.clear()
        self.version += 1

    # -- querying --------------------------------------------------------------------------

    def weighted(self, source: Source | str, *, at: datetime | None = None) -> tuple[float, float]:
        """``(weighted correct, weighted total)`` for a source, with memory decay applied."""
        sid = source_id(source)
        history = self._outcomes.get(sid)
        if not history:
            return 0.0, 0.0
        key = (sid, at if self.memory_half_life is not None else None)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        now = at or utcnow()
        correct = total = 0.0
        for outcome in history:
            weight = self._weight(outcome, now)
            total += weight
            if outcome.correct:
                correct += weight
        self._cache[key] = (correct, total)
        return correct, total

    def _weight(self, outcome: Outcome, now: datetime) -> float:
        if self.memory_half_life is None:
            return 1.0
        age = max(0.0, (now - outcome.at).total_seconds())
        return float(0.5 ** (age / self.memory_half_life.total_seconds()))

    def reliability(self, source: Source | str, prior: float, *, at: datetime | None = None) -> float:
        """Estimated probability that ``source`` is right, starting from ``prior``."""
        if not 0.0 <= prior <= 1.0:
            raise ValueError(f"prior must be between 0 and 1, got {prior}")
        correct, total = self.weighted(source, at=at)
        if total == 0:
            return prior
        return (prior * self.prior_weight + correct) / (self.prior_weight + total)

    def record_of(self, source: Source | str, *, at: datetime | None = None) -> SourceRecord:
        sid = source_id(source)
        history = self._outcomes.get(sid, [])
        weighted_correct, weighted_total = self.weighted(sid, at=at)
        right = sum(1 for o in history if o.correct)
        return SourceRecord(
            source=sid,
            correct=right,
            wrong=len(history) - right,
            weighted_correct=weighted_correct,
            weighted_total=weighted_total,
            last_outcome=history[-1].at if history else None,
        )

    def outcomes(self, source: Source | str) -> list[Outcome]:
        return list(self._outcomes.get(source_id(source), []))

    def sources(self) -> list[str]:
        return list(self._outcomes)

    def __repr__(self) -> str:
        total = sum(len(h) for h in self._outcomes.values())
        return f"<TrustLedger {len(self._outcomes)} sources, {total} outcomes>"

    # -- persistence -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": _FORMAT,
            "version": _FORMAT_VERSION,
            "prior_weight": self.prior_weight,
            "memory_half_life": self.memory_half_life.total_seconds() if self.memory_half_life else None,
            "max_history": self.max_history,
            "outcomes": {
                sid: [[o.at.isoformat(), o.correct, o.reason] for o in history]
                for sid, history in self._outcomes.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TrustLedger:
        if data.get("format") != _FORMAT:
            raise ValueError("not a Corollary trust ledger snapshot")
        if int(data.get("version", 0)) > _FORMAT_VERSION:
            raise ValueError(f"ledger snapshot version {data['version']} is newer than this library supports")
        half_life = data.get("memory_half_life")
        ledger = cls(
            prior_weight=float(data.get("prior_weight", 10.0)),
            memory_half_life=timedelta(seconds=half_life) if half_life else None,
            max_history=int(data.get("max_history", 10_000)),
        )
        for sid, history in data.get("outcomes", {}).items():
            ledger._outcomes[sid] = [
                Outcome(datetime.fromisoformat(at), bool(ok), reason) for at, ok, reason in history
            ]
        return ledger

    def save(self, path: str | os.PathLike[str]) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> TrustLedger:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
