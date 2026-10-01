from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from corollary import BeliefBase, rule


class Clock:
    """A controllable clock so validity windows can be tested deterministically."""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@rule
def growth(previous: float, current: float) -> float:
    """Percent growth from previous to current."""
    return (current - previous) / previous * 100


@rule
def trend(g: float) -> str:
    return "strong" if g >= 8 else "modest" if g >= 3 else "flat"


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def kb(clock: Clock) -> BeliefBase:
    return BeliefBase(clock=clock)


@pytest.fixture
def revenue_kb(kb: BeliefBase) -> BeliefBase:
    """The README scenario: two quarters, a growth figure, a trend and an independent risk."""
    kb.assert_("revenue:Q2", 4.3e9, source="tool:get_revenue")
    kb.assert_("revenue:Q3", 4.5e9, source="tool:get_revenue")
    kb.assert_("fx:exposure", 0.31, source="tool:fx")
    kb.derive("growth:Q3_vs_Q2", growth, "revenue:Q2", "revenue:Q3")
    kb.derive("trend:Q3", trend, "growth:Q3_vs_Q2")
    kb.derive("risk:fx", rule(lambda e: e > 0.25, name="fx_risk"), "fx:exposure")
    kb.changes()  # start every test from an empty change log
    return kb
