# Core concepts

Corollary has a small vocabulary. Once these terms are clear, the rest of the API follows from them.

## Beliefs

A **belief** is a claim plus everything needed to trust it.

```text
Belief  revenue:Q2@1
├── key          revenue:Q2
├── value        4300000000.0
├── claim        "Q2 revenue"                  (optional natural-language statement)
├── source       tool:get_revenue(quarter='Q2')
├── confidence   0.99                          (the local confidence of this belief)
├── created_at   2026-10-01T14:00:00+00:00
└── metadata     {}
```

`Belief` objects are immutable. What changes over time is their **status**, which the kernel computes.

### Keys and revisions

A **key** names a fact, for example `revenue:Q2`, `growth(Q3/Q2)` or `answer`. Keys are free-form but may
not contain whitespace, `@` or braces.

Each time a key gets a *different* value, the base creates a new **revision** instead of mutating the old
one. A revision is identified by a **ref**: `revenue:Q2@1`, `revenue:Q2@2`. Most methods accept either:

- a **key** means "the currently believed revision";
- a **ref** means "exactly this revision", whatever its status.

Revisions are why proofs stay meaningful: a conclusion derived from `revenue:Q2@1` keeps pointing at the
value it actually used, even after `revenue:Q2@2` exists.

## Justifications

A **justification** is a reason to believe something. It links a set of **antecedents** (refs) to a
**conclusion** (a ref), and records how the link was made:

| Kind | Produced by | Example |
|---|---|---|
| `premise` | `assert_`, `cite`, a tool call | `revenue:Q2` comes from `tool:get_revenue` |
| `rule` | `derive` with a deterministic [rule](guides/belief-base.md#rules) | `growth` = `rule:growth(revenue:Q2, revenue:Q3)` |
| `model` | a claim accepted from a model, or `justify` | `trend` proposed by `model:claude-opus-5-5` |

A justification may also carry:

- **`inputs`**: the antecedent *keys*, used to re-derive the conclusion from whatever the current
  revisions are;
- **`unless`**: keys that must *not* be believed for the justification to hold (a default, or an
  exception), as in "the figures are final unless a restatement is believed";
- **`formula`**: arithmetic over the antecedents that the runtime re-executes;
- **`valid_until`**: when the evidence expires.

A belief can have many justifications. Asserting the same value from a second source *corroborates* the
belief: it adds a justification instead of creating a revision.

## Status: IN and OUT

The kernel labels every revision **`IN`** (believed) or **`OUT`** (not believed). A belief is `IN` exactly
when:

1. it has not been retracted, and
2. at least one of its justifications is valid: every antecedent is `IN`, no `unless` key is believed,
   and it has not expired.

Labels are computed, never set by hand, and they are **well-founded**: beliefs that only support each
other in a cycle are `OUT` unless something outside the cycle supports them. You can't bootstrap belief
out of circular reasoning.

When something changes, only the region downstream of the change is relabeled. The cost of a retraction
scales with how much depends on the retracted belief, not with the size of the base.

## Premises and conclusions

A **premise** is a belief grounded directly in a source, with no antecedents. Sources come in kinds:

| Kind | Grounded? | Typical use |
|---|---|---|
| `tool` | yes | a function the runtime executed |
| `document` | yes | a quoted span of a registered document |
| `human` | yes | a person, e.g. `human:alice` |
| `assumption` | no | a working hypothesis (`kb.assume(...)`) |
| `model` | no | something a model asserted without support |
| `rule` | n/a | reserved for derived beliefs |

The verifier requires every leaf of a proof to be **grounded**: a tool, a document or a person.
Assumptions produce a warning; model-asserted premises fail verification.

A **conclusion** is a belief with at least one rule or model justification.

## Retraction, propagation and repair

**Retracting** a belief (`kb.retract("revenue:Q2")`) makes it `OUT`, and everything that depended on it
goes `OUT` with it, immediately. Nothing is deleted: retracted revisions stay in the base with the reason.

**Propagating** (`kb.propagate()`) re-derives what lost support and reports the diff:

- rule-derived beliefs are recomputed directly from the current inputs;
- model-derived beliefs are re-derived by the model, through `agent.repair()`;
- if a recomputed value equals the old one, the old revision simply gains a new justification and comes
  back `IN`. The cascade stops there (**early cutoff**).

Each entry of the diff is a **`Change`**: `IN`, `OUT`, or `KEPT` (a derived belief that was unaffected),
with a reason such as `lost support: revenue:Q2` or `re-derived: 9.7561`.

## Confidence

Every belief has an **effective confidence**, computed along its current support:

- a premise's confidence comes from the [trust policy](guides/belief-base.md#trust-policy) for its source
  (or an explicit `confidence=`);
- a conclusion's confidence is its step's confidence times the weakest antecedent's.

Steps the runtime can check mechanically (rules, and model claims with a re-executed formula) carry
rule-level trust (1.0 by default). Unchecked model steps carry the model's trust (0.9 by default), scaled by
any confidence the model stated. `OUT` beliefs have confidence 0.

## Validity windows

Evidence can expire. A tool declared with `ttl=timedelta(minutes=1)` produces premises valid for one
minute. After that they go `OUT` (with everything that depends on them) and become **stale**:
`kb.stale()` lists them and `agent.reverify()` re-runs the tool calls behind them. If the refreshed value
is the same, the evidence is renewed in place and nothing downstream needs re-deriving. See
[Time and validity](guides/time.md).

## Conflicts

A **conflict** is a set of `IN` beliefs that can't all hold:

- a **value conflict**: one key has two `IN` revisions with different values (two sources disagree);
- a **constraint conflict**: a registered `Constraint` such as "margin ≤ 100" is violated.

Corollary never silently picks a side. A key in a value conflict is hidden from the model and can't be
used as support until the conflict is resolved, by policy, by source rank, or by a person. Each
`Conflict` carries the full support chain of every side. See [Conflicts and resolution](guides/conflicts.md).

## Proofs

A **proof** is the justification subgraph behind one or more beliefs: every step with its value, status,
confidence and justification, in dependency order. Proofs are snapshots, so they can be exported (JSON,
Mermaid, Graphviz), diffed against later proofs, and **verified** by deterministic checks. See
[Verification](guides/verification.md).

## The agent, the projector and the contract

An **agent** couples a model to a belief base. Three pieces make the guarantees hold:

- the **projector** builds every model context from `IN` beliefs only, so a retracted fact can't leak
  back in;
- the **claim contract** is the only thing the model may say: call a tool, cite a document, make a claim,
  or answer, as JSON;
- the **runtime** validates every action before it touches the base. It executes tools itself, checks
  quotes against documents, re-executes formulas, and rejects claims that depend on beliefs the model
  could not see.

See [Agents](guides/agents.md) and [The claim contract](guides/contract.md).

## The message log is a view

A belief base still has a history (`kb.history`, `kb.transcript()`): every assertion, derivation,
retraction and resolution, in order. It is a *view* derived from the base, never the source of truth,
and it is never shown to the model.
