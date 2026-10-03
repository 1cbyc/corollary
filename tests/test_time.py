from __future__ import annotations

from datetime import timedelta

from corollary import BeliefBase, Status, rule

from .conftest import Clock


def test_ttl_expires_belief_and_dependents(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price:ACME", 101.5, source="tool:quote", ttl=timedelta(minutes=1))
    kb.derive("expensive", rule(lambda p: p > 100, name="gt100"), "price:ACME")
    assert kb.valid_until("expensive") == clock.now + timedelta(minutes=1)
    clock.advance(seconds=30)
    assert kb.refresh() == []
    clock.advance(seconds=31)
    expired = kb.refresh()
    assert [b.key for b in expired] == ["price:ACME"]
    assert kb.status("price:ACME") is Status.OUT
    assert kb.status("expensive") is Status.OUT
    assert kb.why_out("price:ACME") == "expired"
    assert [b.key for b in kb.stale()] == ["price:ACME"]


def test_renewing_same_value_restores_without_new_revision(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("hq", "Austin", source="tool:registry", ttl=timedelta(days=365))
    kb.derive("in_texas", rule(lambda c: c == "Austin", name="is_austin"), "hq")
    kb.changes()
    clock.advance(days=366)
    kb.refresh()
    assert kb.status("in_texas") is Status.OUT
    kb.assert_("hq", "Austin", source="tool:registry", ttl=timedelta(days=365))
    assert kb.latest("hq").revision == 1
    assert kb.status("in_texas") is Status.IN
    assert kb.stale() == []
    assert kb.changes() == [], "expired and renewed: no net change"


def test_valid_until_absolute(kb: BeliefBase, clock: Clock) -> None:
    deadline = clock.now + timedelta(hours=1)
    kb.assert_("x", 1, valid_until=deadline)
    assert kb.valid_until("x") == deadline
    kb.assert_("y", 1)
    assert kb.valid_until("y") is None


def test_propagate_refreshes_expiry(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("x", 1, ttl=timedelta(seconds=5))
    kb.changes()
    clock.advance(seconds=10)
    result = kb.propagate()
    assert [(c.kind.value, c.key, c.reason) for c in result] == [("OUT", "x", "expired")]


def test_new_conclusions_never_rest_on_expired_evidence(kb: BeliefBase, clock: Clock) -> None:
    import pytest

    from corollary import NotBelievedError

    kb.assert_("price", 101.5, source="tool:quote", ttl=timedelta(minutes=1))
    clock.advance(minutes=2)  # nobody called refresh()
    with pytest.raises(NotBelievedError):
        kb.derive("expensive", rule(lambda p: p > 100, name="gt100b"), "price")
    with pytest.raises(NotBelievedError):
        kb.justify("cheap", False, antecedents=["price"], source="model:m")
    assert kb.status("price") is Status.OUT


def test_forgotten_validity_windows_are_dropped(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("price", 1, source="tool:quote", ttl=timedelta(minutes=1))
    kb.assert_("price", 1, source="tool:quote")  # the same source again, now without a window
    clock.advance(minutes=2)  # the old window's time comes; the next scan forgets it
    kb.refresh()
    assert kb._expiring == set()
    assert kb.status("price") is Status.IN


def test_refresh_skips_the_scan_until_something_can_expire(kb: BeliefBase, clock: Clock) -> None:
    kb.assert_("a", 1, source="tool:x", ttl=timedelta(minutes=10))
    kb.assert_("b", 2, source="tool:x", ttl=timedelta(minutes=5))
    clock.advance(minutes=4)
    assert kb.refresh() == []
    clock.advance(minutes=1)  # b's window ends exactly now
    assert [x.key for x in kb.refresh()] == ["b"]
    kb.assert_("c", 3, source="tool:x", ttl=timedelta(minutes=1))  # an earlier window than a's
    clock.advance(minutes=1)
    assert [x.key for x in kb.refresh()] == ["c"]
    clock.advance(minutes=4)
    assert [x.key for x in kb.refresh()] == ["a"]
    assert kb.refresh() == []
