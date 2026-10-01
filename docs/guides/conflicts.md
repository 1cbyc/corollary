# Conflicts and resolution

When evidence disagrees, Corollary raises a `Conflict` instead of letting anything pick a side silently.

## Value conflicts

Two `IN` revisions of the same key with different values form a value conflict:

```python
kb.assert_("revenue:Q2", 4.3e9, source="document:press_release")
kb.assert_("revenue:Q2", 4.1e9, source="tool:sec_filings")

(conflict,) = kb.conflicts()
print(conflict)
# Conflict(value: revenue:Q2) 2 incompatible values (4,300,000,000, 4,100,000,000): ...
print(conflict.explain())  # every side with its full support chain
```

While the conflict is open:

- `kb.value("revenue:Q2")` and `kb["revenue:Q2"]` raise `UnresolvedConflictError`;
- `derive` and `justify` refuse to use the key as an antecedent;
- the projector hides the key from the model and lists it under `# Conflicts`;
- `kb.conflicted_keys()` includes it.

Nothing downstream can be built on a disputed fact.

## Constraint conflicts

A `Constraint` is an invariant over the current values of some keys:

```python
kb.add_constraint(
    "margin<=100",
    ["gross_margin"],
    lambda m: m <= 100,
    description="gross margin above 100%",
)

kb.add_constraint("cash>=0", ["cash"], lambda c: c >= 0)
```

The predicate receives the current values, in order, whenever every key has exactly one believed value.
If it returns `False`, or raises, the constraint becomes a `Conflict` of kind `constraint`. Constraint
conflicts are reported but don't block usage of the keys. Resolve them to restore consistency.

## Resolving by hand

```python
kb.resolve(conflict, keep="revenue:Q2@2")  # retract every other side
kb.resolve(conflict, retract="revenue:Q2@1")  # or name what to retract
kb.resolve(conflict, keep=belief, reason="SEC filing is authoritative")
```

Resolution is a retraction with a reason. The losing revision stays in the base, `OUT`, and anything that
depended on it cascades as usual.

## Resolving by policy

A resolver is any callable `(conflict, kb) -> Resolution | None`. Returning `None` leaves the conflict
open, which is always safe.

```python
from corollary import PreferHigherConfidence, PreferNewest, PreferSource, AskHuman

kb.resolve_conflicts(PreferSource(["human", "tool:sec_filings", "tool", "document"]))
```

| Resolver | Value conflicts | Constraint conflicts |
|---|---|---|
| `PreferHigherConfidence(margin=0.0)` | keep the most confident side; leave it open if the top two are within `margin` | retract the least confident belief |
| `PreferNewest()` | keep the most recent side | retract the oldest belief |
| `PreferSource(order=None)` | keep the highest-ranked source; ties stay open. Defaults to `TrustPolicy.source_rank` | retract the lowest-ranked |
| `AskHuman(ask)` | `ask(conflict)` returns the side to keep, or `None` | `ask(conflict)` returns the belief to retract |

`AskHuman` connects conflicts to a person, through a CLI prompt, a review queue or a chat message:

```python
def ask(conflict):
    print(conflict.explain())
    choice = input(f"Keep which of {conflict.refs}? (blank to skip) ")
    return choice or None


kb.resolve_conflicts(AskHuman(ask))
```

With an agent, pass the resolver to the constructor and it runs before every step:

```python
agent = Agent(model, tools=[...], resolver=PreferHigherConfidence(margin=0.05))
```

## Writing a resolver

```python
from corollary import Resolution


def prefer_audited(conflict, kb):
    audited = [b for b in conflict.beliefs if b.metadata.get("audited")]
    if len(audited) != 1:
        return None
    keep = audited[0]
    return Resolution(conflict.id, tuple(r for r in conflict.refs if r != keep.ref), "audited source wins")
```
