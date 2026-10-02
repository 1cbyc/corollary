# Time and validity

A stock price is valid for a minute; a company's headquarters for a year. Corollary lets evidence expire,
so stale facts trigger re-verification instead of silent reuse.

## Validity windows

Validity belongs to the **evidence** (the premise justification), not to the claim. Set it when asserting:

```python
from datetime import timedelta

kb.assert_("price:ACME", 101.5, source="tool:quote", ttl=timedelta(minutes=1))
kb.assert_("hq:ACME", "Austin", source="tool:registry", valid_until=some_datetime)
```

or on a tool, for every result it produces:

```python
@tool(ttl=timedelta(minutes=1))
def quote(symbol: str) -> float: ...
```

`kb.valid_until(key)` returns the earliest expiry along a belief's current support chain. A conclusion is
only as fresh as its stalest input.

## Fading instead of expiring

`ttl` is all or nothing: the evidence is valid, then it isn't. A **half-life** makes it fade gradually
instead. The belief stays `IN`, but its confidence halves every period:

```python
@tool(ttl=timedelta(minutes=5), half_life=timedelta(minutes=1))
def quote(symbol: str) -> float: ...
```

The two combine: the quote loses half its confidence every minute and is invalid after five, whatever
happens. Faded evidence is hidden from the model once it drops below `TrustPolicy.min_confidence`,
`kb.faded()` lists it, and `agent.reverify()` refreshes it. See
[Confidence: freshness](confidence.md#3-freshness-evidence-that-fades) for the numbers.

## Expiry

Expiry is checked against the base's clock:

```python
expired = kb.refresh()  # beliefs that just went OUT because their evidence expired
```

`refresh()` is called automatically by `propagate()`, `derive()` and `justify()`, by the projector before
building every context, and by the agent before every step, so a new conclusion never rests on evidence
that has expired. Expired premises go `OUT` with reason `expired`, and their
dependents go `OUT` with them. Expired evidence is never shown to a model.

## Stale beliefs and re-verification

```python
kb.stale()  # latest revisions OUT only because all their evidence expired
agent.reverify()  # re-run the tool calls behind them, then repair()
```

`reverify()` re-executes each stale (or faded) premise's tool call with its original arguments:

- **Same value:** the evidence is renewed in place. The belief and everything that depended on it come
  back `IN` with no new revisions and no model calls.
- **Different value:** a new revision is created, and `repair()` re-derives the dependents.

You can renew by hand the same way: asserting the same value again for an expired belief renews it.

```python
kb.assert_("hq:ACME", "Austin", source="tool:registry", ttl=timedelta(days=365))
```

## Deterministic time in tests

Inject a clock instead of sleeping:

```python
from datetime import datetime, timedelta, timezone


class Clock:
    def __init__(self):
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


clock = Clock()
kb = BeliefBase(clock=clock)
kb.assert_("x", 1, ttl=timedelta(seconds=5))
clock.now += timedelta(seconds=10)
kb.refresh()  # x is now OUT
```

Use timezone-aware datetimes throughout. The default clock is UTC.

## Verification

`TemporalCheck` fails a proof when any step relies on evidence that has expired at the check time, or when
a justification was recorded before one of its antecedents existed. Check a proof as of another time with
`proof.verify(kb, at=...)`.
