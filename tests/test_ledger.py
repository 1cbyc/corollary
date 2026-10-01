from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from corollary import Source, TrustLedger
from corollary.ledger import source_id

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_no_history_means_the_prior() -> None:
    ledger = TrustLedger()
    assert ledger.reliability("tool:api", prior=0.95) == 0.95
    assert ledger.weighted("tool:api") == (0.0, 0.0)


def test_reliability_follows_the_track_record() -> None:
    ledger = TrustLedger()  # prior weight 10
    for i in range(100):
        ledger.record("tool:api", correct=i >= 5, at=T0)
    assert ledger.reliability("tool:api", prior=0.9, at=T0) == pytest.approx((9 + 95) / 110)
    flaky = TrustLedger()
    for i in range(100):
        flaky.record("tool:scraper", correct=i >= 30, at=T0)
    assert flaky.reliability("tool:scraper", prior=0.9, at=T0) == pytest.approx((9 + 70) / 110)


def test_prior_weight_controls_how_fast_history_wins() -> None:
    slow, fast = TrustLedger(prior_weight=100), TrustLedger(prior_weight=1)
    for ledger in (slow, fast):
        for _ in range(5):
            ledger.record("tool:x", False, at=T0)
    assert slow.reliability("tool:x", prior=0.9) == pytest.approx(90 / 105)
    assert fast.reliability("tool:x", prior=0.9) == pytest.approx(0.9 / 6)


def test_memory_half_life_forgives_old_outcomes() -> None:
    ledger = TrustLedger(memory_half_life=timedelta(days=30))
    ledger.record("tool:x", False, at=T0)
    assert ledger.weighted("tool:x", at=T0) == (0.0, pytest.approx(1.0))
    assert ledger.weighted("tool:x", at=T0 + timedelta(days=60))[1] == pytest.approx(0.25)
    recent = ledger.reliability("tool:x", prior=0.9, at=T0)
    later = ledger.reliability("tool:x", prior=0.9, at=T0 + timedelta(days=60))
    assert recent < later < 0.9
    # Outcomes in the "future" relative to the query time count fully, never more.
    assert ledger.weighted("tool:x", at=T0 - timedelta(days=1))[1] == pytest.approx(1.0)


def test_sources_are_tracked_without_call_arguments() -> None:
    ledger = TrustLedger()
    ledger.record(Source.tool("get_revenue", {"quarter": "Q2"}), False)
    ledger.record("tool:get_revenue", True)
    record = ledger.record_of(Source.tool("get_revenue", {"quarter": "Q3"}))
    assert (record.source, record.correct, record.wrong, record.total) == ("tool:get_revenue", 1, 1, 2)
    assert record.last_outcome is not None
    assert source_id(Source.human("alice")) == "human:alice"
    assert ledger.sources() == ["tool:get_revenue"]
    assert [o.correct for o in ledger.outcomes("tool:get_revenue")] == [False, True]


def test_version_changes_and_reset() -> None:
    ledger = TrustLedger()
    v0 = ledger.version
    ledger.record("tool:a", True)
    ledger.record("tool:b", False)
    assert ledger.version == v0 + 2
    ledger.reset("tool:a")
    assert ledger.sources() == ["tool:b"]
    ledger.reset()
    assert ledger.sources() == []
    assert "TrustLedger" in repr(ledger)


def test_history_is_capped() -> None:
    ledger = TrustLedger(max_history=3)
    for i in range(5):
        ledger.record("tool:a", i % 2 == 0, reason=str(i))
    assert [o.reason for o in ledger.outcomes("tool:a")] == ["2", "3", "4"]


def test_roundtrip(tmp_path: Path) -> None:
    ledger = TrustLedger(prior_weight=5, memory_half_life=timedelta(days=7), max_history=50)
    ledger.record("tool:a", True, at=T0, reason="confirmed")
    ledger.record("model:m", False, at=T0, reason="formula")
    path = tmp_path / "trust.json"
    ledger.save(path)
    again = TrustLedger.load(path)
    assert again.to_dict() == ledger.to_dict()
    assert again.reliability("model:m", prior=0.9, at=T0) == ledger.reliability("model:m", prior=0.9, at=T0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"prior_weight": 0}, "prior_weight"),
        ({"memory_half_life": timedelta(0)}, "memory_half_life"),
        ({"max_history": 0}, "max_history"),
    ],
)
def test_validation(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        TrustLedger(**kwargs)  # type: ignore[arg-type]


def test_rejects_bad_priors_and_snapshots() -> None:
    with pytest.raises(ValueError):
        TrustLedger().reliability("tool:a", prior=1.5)
    with pytest.raises(ValueError, match="not a Corollary trust ledger"):
        TrustLedger.from_dict({"format": "x"})
    with pytest.raises(ValueError, match="newer"):
        TrustLedger.from_dict({"format": "corollary.trustledger", "version": 99})
