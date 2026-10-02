# Agents

An `Agent` couples a model to a belief base. The model proposes; the runtime decides.

```python
from corollary import Agent, AnthropicModel, tool


@tool(trust="high")
def get_revenue(quarter: str) -> float:
    """Quarterly revenue in USD from SEC filings."""
    ...


agent = Agent(AnthropicModel("claude-opus-5-5"), tools=[get_revenue])
report = agent.run("Compare Q2 and Q3 revenue and assess the growth trend.")
```

## Constructor

| Argument | Default | Meaning |
|---|---|---|
| `model` | required | A [model](models.md), or a string like `"anthropic:claude-opus-5-5"` |
| `beliefs` | new `BeliefBase` | The base the agent reads and writes; share one across agents or sessions |
| `tools` | `()` | `Tool`s, or plain functions (wrapped with `@tool` defaults) |
| `documents` | `None` | `{name: text}` the model may cite |
| `rules` | `()` | Rules to register on the base |
| `trust` | `None` | A `TrustPolicy` for the base |
| `projector` | `Projector()` | Builds model contexts; see [below](#what-the-model-sees) |
| `dependencies` | `"conservative"` | How claim dependencies are recorded; see [below](#dependency-policies) |
| `resolver` | `None` | Applied to open conflicts before each step; see [Conflicts](conflicts.md) |
| `max_steps` | `12` | Model calls per `run()` |
| `repair_attempts` | `2` | Model calls per belief during `repair()` |
| `self_consistency` | `1` | Samples per unverified claim; see [self-consistency](confidence.md#6-self-consistency-asking-more-than-once) |
| `learn_from_checks` | `True` | Record verified formulas and citations in the trust ledger as the model's track record |
| `instructions` | `""` | Domain guidance shown on every step and every re-derivation (house style, language, ...) |
| `system_prompt` | `SYSTEM_PROMPT` | The contract instructions; override with care. Prefer `instructions` for guidance |

## The run loop

Each step of `agent.run(task)`:

1. **Refresh.** Expired evidence goes `OUT`. If a resolver is configured, open conflicts are resolved.
2. **Project.** The projector renders the task, the `IN` beliefs, open conflicts, the tools, the
   documents, and the previous step's rejections into a single prompt. There is no chat history.
3. **Propose.** The model returns one JSON response in the [claim contract](contract.md).
4. **Validate and apply.** Each action is checked against the base and either applied or rejected:
   - `call_tool`: the runtime executes the tool and records the result as a premise;
   - `cite`: the quote must appear in the document and state the value;
   - `claim`: dependencies must have been visible this step, and any formula must reproduce the value;
   - `answer`: recorded as a belief (key `answer`, then `answer:2`, ...), and the run ends.
5. **Feed back.** Rejections are shown to the model on the next step.

The run ends at the first accepted answer, or when `max_steps` is reached (`report.completed` is then
`False`). If the model fails (a refusal, a truncated response, an API error), the run stops and
`report.error` holds the `ModelError`. Tool results and claims accepted before that stay in the belief
base, so running the task again continues from them.

## The report

`Report` reads the belief base live. After a correction and `repair()`, the same report object shows the
repaired answer.

```python
report.answer  # the believed answer text, or None
report.belief  # the answer's Belief
report.completed  # did the model answer within the step budget?
report.error  # the ModelError that ended the run early, if any
report.stale  # answered, but the answer has since lost its support
report.proof  # the graph of beliefs the answer follows from
report.verify()  # deterministic checks; verify(raise_on_error=True) raises on failure
report.rejections  # every rejected action, with the reason
report.changes  # everything that became IN or OUT during the run
report.steps  # StepRecord(index, prompt, response, accepted, rejected) per model call
```

`report.steps` is how you debug an agent: each record holds the exact prompt the model saw and its raw
response.

### Logging

The agent logs to the `corollary` logger and configures no handlers. Warnings cover model failures, tools
that raise (with the traceback, which the model never sees) and tools that fail during `reverify()`.
Each step's accepted and rejected actions are logged at `DEBUG`.

```python
import logging

logging.basicConfig()
logging.getLogger("corollary").setLevel(logging.DEBUG)
```

## Tools

```python
from datetime import timedelta
from corollary import tool


@tool(trust="high", ttl=timedelta(minutes=1))
def quote(symbol: str) -> float:
    """Latest price for a ticker symbol."""
    ...
```

- **The docstring's first paragraph** is the description shown to the model, along with the signature.
- **`trust`** is a level from the trust policy (`"high"`, `"medium"`, `"low"`) or a number in [0, 1].
- **`ttl`** sets how long each result stays valid. See [Time and validity](time.md).
- **Arguments are validated** against the function signature before the call. Arguments annotated
  `str`, `int`, `float` or `bool` (or `X | None`) are type-checked, and unambiguous values are coerced:
  `"3"` becomes `3` for an `int`, `"true"` becomes `True` for a `bool`. Unknown tools, bad arguments and
  exceptions raised by the tool are rejected and reported to the model.
- **`async def` tools work too.** The runtime runs them to completion, on a worker thread with its own
  event loop if it is itself called from inside one.
- **`half_life`** makes each result's confidence fade, and **`origin`** declares an independence group
  (tools reading the same database). See [Confidence](confidence.md).
- **The result becomes a premise** with source `tool:quote(symbol='ACME')`, stored under the key the model
  chose, or `quote:ACME` by default.
- **Calling the same tool with the same arguments again** supersedes the previous result instead of
  creating a conflict. Two *different* sources disagreeing still produce a conflict.

> **Tools are not sandboxed.** They run in your process with your permissions. Validate inputs inside any
> tool that touches the filesystem, network or shell.

## What the model sees

The `Projector` renders only beliefs that are `IN`, not part of a value conflict, and at or above the
trust policy's `min_confidence`. A retracted or expired fact is **absent** from the context, not flagged.

```python
from corollary import Projector

agent = Agent(
    model,
    projector=Projector(
        max_beliefs=500,  # most confident first when over the limit
        min_confidence=None,  # default: the trust policy's min_confidence
        max_document_chars=50_000,  # per document; truncation is announced in the prompt
        show_sources=True,
    ),
)
```

## Dependency policies

When a model makes a claim, the runtime has to record what the claim depends on. Corollary offers two
policies:

**`"conservative"` (default).** A claim depends on *every* belief that was visible in the context it was
generated from, plus earlier claims from the same response. The projector guarantees the model could not
have used anything else, so this is sound by construction: **a retracted fact can never survive in a
conclusion**. The cost is over-retraction. Retracting any visible belief invalidates the claim, even one
the model ignored.

**`"declared"`.** A claim depends on the keys it lists in `follows_from`, plus any keys in its formula.
Cascades are sharper, but you are trusting the model's account of what it used.

```python
agent = Agent(model, tools=[...], dependencies="declared")
```

A middle path is to run conservatively and then **narrow** important beliefs by ablation, as described
below.

## Repairing after a correction

```python
agent.kb.retract("revenue:Q2", reason="restated in 10-K/A")
agent.kb.assert_("revenue:Q2", 4.1e9, source="tool:get_revenue")

result = agent.repair()
for change in result:
    print(change)
```

`repair()` is `kb.propagate()` with the agent as re-deriver:

- rule-derived beliefs are recomputed without the model;
- each model-derived belief that lost support is re-derived by **one model call** whose context contains
  only the current values of that belief's inputs. The retracted value is never shown again;
- the re-derived claim goes through the same validation as during `run()`, and is retried up to
  `repair_attempts` times with feedback;
- unchanged values stop the cascade (early cutoff);
- the answer is a belief like any other, so it is re-derived too.

Anything that can't be re-derived is listed in `result.pending` with the reason.

## Re-verifying stale evidence

```python
result = agent.reverify()
```

For every premise that is `OUT` because its evidence expired (`ttl`), or still `IN` but faded below
`TrustPolicy.min_confidence` (`half_life`), `reverify()` re-runs the tool call that produced it, with the
same arguments, then calls `repair()`. A refreshed value equal to the old one renews the evidence in place,
so its dependents come back without any model calls.

## Narrowing dependencies by ablation

```python
result = agent.narrow("trend")
result.kept  # ('growth:Q3_vs_Q2',)
result.pruned  # ('revenue:Q2', 'revenue:Q3', 'weather')
result.calls  # model calls spent: one per original antecedent
```

For each antecedent of a model-derived belief, `narrow` asks the model to derive the belief again with that
antecedent removed from its context. If the value is unchanged, the antecedent was not needed. The result
is recorded as an *additional*, narrower justification. Retracting a pruned belief no longer cascades into
the narrowed one, while the original conservative justification remains as history.

Narrowing relies on the model producing the same value with less context. For numbers that's
well-defined. For free text, values are compared after whitespace and case normalization, so prose rarely
narrows. That's the safe direction to fail in.

## Conflicts during a run

Keys involved in a value conflict are hidden from the model and listed under `# Conflicts` in its context.
To resolve conflicts automatically before every step, pass a resolver:

```python
from corollary import PreferSource

agent = Agent(model, tools=[...], resolver=PreferSource(["human", "tool:sec_filings", "tool", "document"]))
```

## Cost

Each `run()` step is one model call. `repair()` costs one call per re-derived model belief (rules are
free), and `narrow()` one call per antecedent. Keep claims atomic and prefer formulas and rules for
anything computable: they make repairs cheaper and verification stronger.
