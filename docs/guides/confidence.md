# Confidence

Every belief in Corollary has a **confidence** between 0 and 1: how much the base trusts it right now.
This page explains how it is calculated, where the numbers come from, and how to tune them.

```python
kb.confidence("trend")  # 0.891
```

In short:

1. A **premise** is trusted as much as its source has *proven* to be reliable, and less as its evidence
   gets older.
2. **Independent sources that agree** reinforce each other.
3. A **conclusion** is as trustworthy as its reasoning step, times its weakest input.

## The model at a glance

```text
reliability(source)  = learned from the source's track record, starting from a prior
premise              = reliability(source) × freshness(age)
agreement            = 1 − (1 − c₁)(1 − c₂)…        across independent origins
verified step        = 1.0 × certainty × min(inputs)        rules and re-executed formulas
model step           = reliability(model) × certainty × min(inputs)
belief               = the strongest of its valid justifications
OUT belief           = 0
```

Each part is described below, with the numbers the library actually produces.

## 1. Where premises start: the trust policy

With no history, a source is trusted according to the [trust policy](belief-base.md#trust-policy):

| Source | Prior |
|---|---|
| `human:...` | 0.99 |
| a tool declared `@tool(trust="high")` / `"medium"` / `"low"` | 0.99 / 0.9 / 0.7 |
| `tool:...` asserted directly | 0.95 |
| `document:...` | 0.9 |
| `model:...` | 0.9 |
| `assumption:...` | 0.6 |

These are only **starting points**. The next section replaces them with measurements.

## 2. Learned reliability: the trust ledger

Every time a source is shown to be right or wrong, the outcome is recorded in a `TrustLedger`, and the
source's reliability is re-estimated:

```text
reliability = (prior × n₀ + correct) / (n₀ + total)
```

`n₀` (the ledger's `prior_weight`, 10 by default) is how many observations the prior is worth. With no
recorded outcomes, reliability equals the prior, so nothing changes until evidence comes in. After a few
dozen outcomes, the record dominates.

A scraper with a prior of 0.95 that gets 30 of its 100 facts retracted as wrong:

```text
(0.95 × 10 + 70) / (10 + 100) = 0.7227
```

Every belief from that scraper now carries confidence 0.72, and it loses conflicts against more reliable
sources, without anyone editing a number.

### What counts as an outcome

| Event | Recorded as |
|---|---|
| `kb.retract(key, fault="source")`: the value was wrong when given | wrong, for every source accountable for the belief |
| `kb.retract(key)` (default `fault="none"`): the world changed, e.g. a restatement | nothing |
| A conflict resolved by a person (`AskHuman`, or `kb.resolve(..., learn=True)`) | wrong for the losing sources, right for the winning ones |
| An independent source asserting the same value | right, for both sources |
| A model formula that reproduces its stated value, or doesn't | right / wrong for the model |
| A model citation that checks out, or doesn't | right / wrong for the model |
| `kb.record_outcome(source, correct)`: your own ground truth (an audit, a ticket) | as given |

"Accountable" means the belief's premise sources, or the model behind an *unverified* claim. Rules and
re-executed formulas are never at fault: if they produced a wrong value, an input was wrong, so retract
the input instead. Trying to blame a rule raises `ValueError`.

Conflicts resolved by a **policy** (`PreferHigherConfidence`, `PreferSource`, ...) are *not* learned
from. If they were, the policy would reinforce itself: the more trusted side wins, so it becomes more
trusted.

```python
kb.retract("price:ACME", reason="scraper returned yesterday's price", fault="source")
kb.record_outcome("tool:carrier_api", False, reason="ETA missed by 3 days")
kb.reliability("tool:carrier_api")  # the learned value
kb.ledger.record_of("tool:carrier_api")  # SourceRecord(correct=..., wrong=..., ...)
```

### How the model's reliability is measured

The model is a source like any other. Its unverified judgements can't be checked directly, so the agent
uses its *checkable* work as evidence: every formula and citation the runtime verifies is recorded as a
success or a failure. A model that keeps getting its arithmetic and quotes right earns more trust for its
judgement calls; one that doesn't, loses it. Turn this off with `Agent(learn_from_checks=False)`.

This is a proxy, and it should be read as one: being good at arithmetic is evidence of care, not proof
of good judgement.

### Forgetting: memory half-life

A source that was broken last month and has since been fixed shouldn't be punished forever. With a
memory half-life, each outcome's weight halves every period:

```python
from corollary import BeliefBase, TrustLedger

ledger = TrustLedger(memory_half_life=timedelta(days=30))
kb = BeliefBase(ledger=ledger)
```

A tool with a 0.95 prior that had 20 failures in one bad week, with no outcomes since:

| Days since the outage | Reliability |
|---|---|
| 0 | 0.32 |
| 30 | 0.48 |
| 60 | 0.63 |
| 120 | 0.84 |

As old outcomes fade, a source with no recent history drifts back toward its prior: the honest answer to
"we haven't seen it lately".

### Sharing a ledger

A belief base usually covers one task, customer or session, but a source's reliability should be learned
across all of them. Pass the same ledger to every base:

```python
ledger = TrustLedger.load("trust.json") if Path("trust.json").exists() else TrustLedger()


def handle(customer_id, message):
    kb = load_belief_base(customer_id, ledger=ledger)
    ...
    ledger.save("trust.json")
```

A base that creates its own ledger saves it inside its snapshot. A shared ledger is not part of any one
base's snapshot: save it separately with `ledger.save(...)` and attach it with
`BeliefBase.from_dict(data, ledger=ledger)`. See [Persistence](persistence.md).

## 3. Freshness: evidence that fades

Some facts age: a price is good for a minute, a headquarters address for years. Give the evidence a
half-life and its confidence fades:

```text
freshness(age) = 0.5 ^ (age / half_life)
```

```python
@tool(half_life=timedelta(minutes=1))
def quote(symbol: str) -> float: ...


kb.assert_("price:ACME", 101.5, source="tool:quote", half_life=timedelta(minutes=1))
```

A quote from a tool with reliability 0.95 and a one-minute half-life:

| Age | Confidence |
|---|---|
| 0 s | 0.95 |
| 30 s | 0.67 |
| 1 min | 0.475 |
| 2 min | 0.24 |

Decay **never changes a belief's status**: a faded belief is still `IN`. It changes what the belief is
worth. Its conclusions fade with it (through the `min` in the chain rule), the projector hides it once it
falls below `TrustPolicy.min_confidence`, and it loses conflicts to fresher evidence.

Two settings, two meanings, used together:

- `ttl` is the **hard limit**: past it, the evidence is expired and the belief goes `OUT`;
- `half_life` is the **soft fade**: the belief stays `IN`, but is worth less every minute.

```python
@tool(ttl=timedelta(minutes=5), half_life=timedelta(minutes=1))
def quote(symbol: str) -> float: ...
```

**Refreshing.** `kb.faded()` lists believed premises whose confidence has faded below `min_confidence`
(or a threshold you pass). `agent.reverify()` re-runs the tool calls behind both expired and faded
premises. A refreshed value equal to the old one renews the evidence in place: confidence jumps back up,
and nothing downstream is re-derived.

## 4. Agreement: noisy-OR across independent sources

When several **independent** sources support the same value, the fact is wrong only if all of them are:

```text
confidence = 1 − (1 − c₁)(1 − c₂)…
```

A headquarters city asserted by a registry tool (0.95) and by the annual report (0.9):

```python
kb.assert_("hq", "Austin", source="tool:registry")  # 0.95
kb.assert_("hq", "Austin", source="document:10-K")  # now 0.9959
```

The confirmation also counts as a success for both sources in the ledger, which is why the result is
slightly higher than `1 − 0.05 × 0.1 = 0.995`.

### Origins: what "independent" means

Two tools that read the same database are not independent: if the database is wrong, both are. Declare a
shared **origin**, and sources with the same origin count once (the most confident one):

```python
@tool(origin="sec_database")
def get_revenue(quarter: str) -> float: ...


@tool(origin="sec_database")
def get_filing_figure(name: str) -> float: ...


kb.assert_("x", 1, source="human:alice", origin="finance_team")
```

By default a source's origin is its own name (`tool:get_revenue`), so repeated calls to the same tool
never reinforce themselves. Agreement within an origin is not recorded as a confirmation either, and a
source repeating a value it already gave (a re-read, a refresh) replaces its earlier justification
instead of adding one, so polling a tool doesn't inflate its track record.

To turn agreement off entirely, use `TrustPolicy(corroboration=False)`: each belief then counts only its
most confident source.

## 5. Conclusions: the chain rule

A derived belief is as trustworthy as its reasoning step, times its weakest input:

```text
confidence = step × min(inputs)
```

| Step | Step confidence |
|---|---|
| A rule (`@rule`) | the rule's `confidence` (1.0 by default) |
| A model claim with a formula the runtime re-executed | 1.0 × the claim's certainty |
| A model claim without a formula | the model's learned reliability × the claim's certainty |

A claim's **certainty** is the confidence the model stated (1.0 if it stated none), or the
[self-consistency](#6-self-consistency-asking-more-than-once) score.

Using the *weakest* input means a conclusion never outranks its shakiest ingredient. Along a chain, step
confidences multiply, so long chains of unchecked reasoning lose confidence, as they should.

The worked example from the [getting started](../getting-started.md) analysis:

```text
revenue:Q2   0.99    premise from a "high" trust tool
revenue:Q3   0.99    premise from a "high" trust tool
growth       0.99    1.0 (formula, re-executed)  × min(0.99, 0.99)
trend        0.891   0.9 (model judgement)       × 0.99
answer       0.802   0.9 (model judgement)       × min(0.99, 0.891)
```

The arithmetic step lost nothing because it was checked. Each judgement call cost 10%. Replacing a
judgement with a rule or a formula is the most effective way to raise confidence.

When a belief has several valid justifications (it was derived two different ways, or is both asserted
and derived), the **strongest** one counts.

## 6. Self-consistency: asking more than once

For important unverified claims, the agent can measure the model's certainty instead of assuming it:
ask for the same claim several times, from the same beliefs, and see how often it agrees with itself.

```python
agent = Agent(model, tools=[...], self_consistency=5)
```

With `self_consistency=k`, every claim without a formula is sampled `k − 1` more times. Each sample
sees the same beliefs but neither the original answer nor the claim text. The step's certainty
becomes:

```text
certainty = (agreeing + 1) / (k + 1)
```

| Samples agreeing (k = 5) | Certainty |
|---|---|
| 5 of 5 | 1.0 |
| 4 of 5 | 0.83 |
| 3 of 5 | 0.67 |
| only the original | 0.33 |

Numbers are compared with a small tolerance; text is compared after case and whitespace normalization,
so free-form prose rarely agrees exactly. That is the safe direction to fail in. Formula claims and the
final answer are not sampled.

The cost is `k − 1` extra model calls per unverified claim, so it is off by default (`k = 1`).

## Where confidence is used

| Use | How |
|---|---|
| Hiding weak or faded facts from the model | `TrustPolicy(min_confidence=0.7)` |
| Settling conflicts | `PreferHigherConfidence()` keeps the more confident side |
| Refreshing faded evidence | `kb.faded()`, `agent.reverify()` |
| Telling people how far to trust an answer | every proof shows it: `[IN 0.89]` |

## What it is, and what it isn't

Corollary's confidence is a **trust score built from evidence**: priors, track records, agreement, age
and the structure of the reasoning. It is not a calibrated probability. "0.80" does not mean "right 80%
of the time". It means more solid than 0.6 and less than 0.99, for reasons you can inspect.

It moves toward calibration as the ledger accumulates outcomes, because reliability is then measured
rather than assumed. Early on, it mostly reflects the defaults, so set the priors deliberately for the
sources you know.

Some limits worth knowing:

- **Independence is declared, not discovered.** If two sources secretly share an origin and you don't
  declare it, their agreement is over-counted.
- **The model's reliability is measured on checkable work** (formulas and citations) and applied to its
  judgement calls. That's a proxy.
- **Outcomes depend on honest blame.** `fault="source"` should mean the source was wrong, not that the
  world changed. The default is `"none"` so that nothing is penalized by accident.

## Reference

| API | Purpose |
|---|---|
| `kb.confidence(key)` | Effective confidence of a belief |
| `kb.reliability(source)` | A source's learned reliability, from the policy's prior |
| `kb.record_outcome(source, correct, reason=)` | Feed external ground truth to the ledger |
| `kb.retract(key, fault="source")` | Retract and blame the accountable sources |
| `kb.resolve(conflict, ..., learn=True)` | Resolve a conflict as ground truth |
| `kb.faded(threshold=None)` | Believed premises that have faded below a threshold |
| `assert_(..., half_life=, origin=)` | Decaying evidence; independence group |
| `@tool(half_life=, origin=)` | The same, for every result of a tool |
| `TrustLedger(prior_weight=10, memory_half_life=None, max_history=10_000)` | The ledger |
| `BeliefBase(ledger=...)` | Share a ledger across bases |
| `TrustPolicy(corroboration=True, min_confidence=0.0, ...)` | Priors and thresholds |
| `Agent(self_consistency=1, learn_from_checks=True)` | Agent-side measurement |
| `AskHuman(ask, learn=True)` | Human resolutions teach the ledger |
