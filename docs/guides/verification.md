# Verification

Every answer in Corollary ships with a proof: the graph of beliefs it follows from. The verifier checks
that proof with ordinary code. No check asks a model whether the answer is right.

```python
report = agent.run("...")
result = report.verify()
print(result)
```

```text
Verification PASSED: 6 checks, 0 errors, 0 warnings
  ok   structure    all 5 steps are well-formed and IN
  ok   grounding    all 2 premises trace to tools, documents or people
  ok   arithmetic   1 computation re-executed and matched
  ok   citation     0 citations matched their documents
  ok   temporal     all evidence is current and causally ordered
  ok   provenance   every number in model claims traces to its support
```

Any proof can be verified, not only agent answers:

```python
proof = kb.proof("outlook")
proof.verify(kb)  # all built-in checks, with the base as context
proof.verify(kb, checks=[...])  # a chosen set of checks
proof.verify(kb, at=some_datetime)  # check validity windows at another time
proof.verify()  # without a base: no rules, documents or live status
```

## Proofs

A `Proof` is a snapshot of the support behind one or more beliefs, in dependency order:

```python
proof = kb.proof("trend:Q3")  # or kb.proof("a", "b") for several roots
proof.roots  # ('trend:Q3@2',)
proof.steps  # ProofStep(belief, status, confidence, justification)
proof.premises  # the leaves
proof.derived  # everything else
proof.valid  # were all steps IN when it was taken?
print(proof)  # tree rendering (ASCII on consoles without Unicode)
proof.render(show_sources=False, ascii=True)
proof.to_mermaid()  # paste into a Markdown file or mermaid.live
proof.to_dot()  # Graphviz
proof.to_json()
Proof.from_json(text)  # export and import
before.diff(after)  # ProofDiff(added, removed, changed)
```

Because a proof is a snapshot, verifying an old proof against the current base detects that it went
stale.

## Built-in checks

| Check | Fails (error) when | Warns when |
|---|---|---|
| `StructureCheck` | an antecedent is missing from the proof; a step was `OUT`; a step is no longer `IN` in the base | |
| `GroundingCheck` | a leaf is a model-asserted premise | a leaf is an assumption |
| `ArithmeticCheck` | a formula or a replayed rule doesn't reproduce the stated value | a rule isn't available to replay |
| `CitationCheck` | a quote is not in its document; the quote doesn't state the value | the document isn't available; a citation has no quote |
| `TemporalCheck` | evidence expired at the check time; a justification predates its antecedent | |
| `NumericProvenanceCheck` | | a model claim states a number found nowhere in its support |

All checks live in `corollary.verify`. `ArithmeticCheck(rel_tol=1e-6)` and
`NumericProvenanceCheck(ignore_below=13, ignore_years=True)` take options.

### Numeric provenance

The projector controls what a model *sees*, but not what it already *knows*. A model can still write a
figure from its training data into a claim. `NumericProvenanceCheck` catches the visible part of that:
every number in a model-written claim must match one of its antecedents' values (or its own value, when a
formula computed it), after rounding and at the scale its unit states (`4.1 billion`, `$4.1B`, `9.76%`).
Small integers, years, dates, times and ordinals are ignored to keep it quiet on ordinary prose. It warns
rather than fails, because prose legitimately contains numbers.

## The report

```python
result.ok  # no failing errors (warnings don't fail)
bool(result)  # same as ok
result.errors  # failing CheckResults with severity "error"
result.warnings  # failing CheckResults with severity "warning"
result.results  # everything, including passes
result.raise_for_errors()  # raises VerificationError if not ok; returns the report otherwise
```

## Writing a check

A check is any object with a `name` and a `run(proof, ctx)` method returning `CheckResult`s:

```python
from corollary import CheckResult, Severity
from corollary.verify import VerificationContext


class PositiveRevenue:
    """Revenue figures must be positive."""

    name = "positive-revenue"

    def run(self, proof, ctx: VerificationContext):
        failures = [
            CheckResult(self.name, False, "revenue must be positive", step.ref)
            for step in proof
            if step.belief.key.startswith("revenue:") and step.belief.value <= 0
        ]
        return failures or [CheckResult(self.name, True, "all revenue figures are positive")]


from corollary import Verifier
from corollary.verify import DEFAULT_CHECKS

verifier = Verifier([cls() for cls in DEFAULT_CHECKS] + [PositiveRevenue()])
verifier.verify(proof, kb=kb)
```

`ctx` provides `at` (the check time), `kb` (or `None`), `documents` and `rules`. Use
`Severity.WARNING` for findings that should not fail verification.

Verifiers are among the most valuable contributions to Corollary. Unit consistency, date arithmetic and
table lookups would all make good checks. See
[CONTRIBUTING.md](https://github.com/gabe-santana/corollary/blob/main/CONTRIBUTING.md).
