# Persistence

A belief base can be saved to a JSON snapshot and loaded later, in another process or session. A new
session then inherits verified beliefs with their proofs attached, not raw transcripts.

```python
kb.save("acme.beliefs.json")

from corollary import BeliefBase

kb = BeliefBase.load("acme.beliefs.json", rules=[growth, trend])
```

## What is saved

- every revision of every belief, including retracted ones and their reasons;
- every justification, with its antecedents, `unless` keys, recipe inputs, formula, source, confidence and
  validity window;
- registered documents;
- the change reasons and the event history.

Labels (`IN` / `OUT`) are **not** stored: they are recomputed on load from the graph, so a snapshot can't
contain an inconsistent labeling. Loading a snapshot doesn't count as a change, so `kb.changes()` is
empty right after `load`.

## What is not saved

- **Rules and constraints**, which are Python callables. Rules are referenced by name. Pass the same
  rules to `load(..., rules=[...])` and constraints to `constraints=[...]`. If a rule is missing, the
  beliefs it derived still load correctly, but they can't be re-derived automatically
  (`propagate()` reports them as pending with `rule ... is not registered`), and the verifier can't
  replay them (a warning).
- **The trust policy and clock**: pass `trust=` and `clock=` to `load` if you don't want the defaults.

Give rules explicit, stable names (`@rule(name="growth")`) for anything you persist. Anonymous lambdas get
generated names that won't match across processes.

## Values must be JSON

Belief values and tool arguments are stored as JSON. Numbers, strings, booleans, `None`, lists and dicts
round-trip exactly. Convert other types (dates, decimals, dataclasses) to one of those before asserting
them, or keep them out of beliefs you intend to persist.

## In-memory snapshots

```python
data = kb.to_dict()  # JSON-compatible dict
copy = BeliefBase.from_dict(data, rules=[growth])
```

The snapshot format is versioned (`"format": "corollary.beliefbase"`, `"version": 1`). Loading a
snapshot from a newer format version raises `ValueError`.

## Roadmap

SQLite and Postgres stores, incremental writes, and cross-session inheritance policies (for example,
inheriting only beliefs that pass verification) are planned for v0.3.
