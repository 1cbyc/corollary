# Corollary documentation

**Corollary is an agent runtime where the unit of state is a belief, not a message.**

Every conclusion an agent reaches is stored with the evidence it follows from. When a piece of evidence
is corrected, everything that depended on it is retracted and re-derived, and nothing else is touched.
Every answer ships with a proof that a deterministic verifier can check.

```python
from corollary import Agent, tool


@tool(trust="high")
def get_revenue(quarter: str) -> float:
    """Quarterly revenue in USD."""
    ...


agent = Agent("anthropic:claude-opus-5-5", tools=[get_revenue])
report = agent.run("Compare Q2 and Q3 revenue and assess the growth trend.")

print(report.answer)
print(report.proof)  # the graph of beliefs the answer follows from
print(report.verify())  # deterministic checks over that graph

agent.kb.retract("revenue:Q2", reason="restated in 10-K/A")
agent.kb.assert_("revenue:Q2", 4.1e9, source="tool:get_revenue")
agent.repair()  # only what depended on Q2 is re-derived
print(report.answer)  # the repaired answer
```

## Where to start

| If you want to... | Read |
|---|---|
| Install Corollary and run your first belief base and agent | [Getting started](getting-started.md) |
| Understand beliefs, justifications, labels and proofs | [Core concepts](concepts.md) |
| Use the kernel directly, with deterministic rules | [The belief base](guides/belief-base.md) |
| Build an agent on top of a model | [Agents](guides/agents.md) |
| See exactly what a model is allowed to say | [The claim contract](guides/contract.md) |
| Check answers without trusting the model | [Verification](guides/verification.md) |
| Understand and tune how much each belief is trusted | [Confidence](guides/confidence.md) |
| Handle sources that disagree | [Conflicts and resolution](guides/conflicts.md) |
| Ground beliefs in documents | [Documents and citations](guides/documents.md) |
| Make facts expire and refresh them | [Time and validity](guides/time.md) |
| Connect Claude, an OpenAI-compatible endpoint, or your own model | [Models](guides/models.md) |
| Save and reload a belief base | [Persistence](guides/persistence.md) |
| Learn how the kernel works and what it guarantees | [Architecture and guarantees](architecture.md) |
| Look up a class or method | [API reference](api.md) |
| See how Corollary relates to prior work | [Related work](related-work.md) |
| Get quick answers | [FAQ](faq.md) |

## The idea in one paragraph

Agent frameworks store state as a message log. A hallucination at step 3 is just text, and at step 40
the agent reads it with the same trust as a verified tool result. Corollary replaces the log with a
**belief base**: a dependency graph in which every belief records what supports it. Underneath sits a
truth maintenance system (Doyle, 1979). The model is a stateless *proposer*: it never sees a transcript
and never writes state directly. It receives a context built from currently believed facts, and it can
only answer with structured claims that the runtime validates before accepting. Every guarantee is
enforced by code outside the model.

## Status

Corollary is **pre-alpha** (`0.1.0a1`). The kernel, the agent runtime, verification, conflicts, validity
windows and persistence are implemented and tested. Interfaces may still change before 1.0. See the
[roadmap](https://github.com/gabe-santana/corollary#roadmap) and the
[changelog](https://github.com/gabe-santana/corollary/blob/main/CHANGELOG.md).
