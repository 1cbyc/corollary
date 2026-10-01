# Getting started

This page takes you from installation to a self-repairing analysis in a few minutes. The first two
sections need no API key: they use the kernel directly and a scripted model.

## Installation

Corollary requires Python 3.10 or later. The core has **no runtime dependencies**. Model SDKs are
optional extras.

```bash
pip install corollary                 # the kernel and the agent runtime
pip install "corollary[anthropic]"    # + the Claude adapter (official Anthropic SDK)
pip install "corollary[openai]"       # + the OpenAI-compatible adapter
```

To work from source:

```bash
git clone https://github.com/gabe-santana/corollary.git
cd corollary
pip install -e ".[dev]"
```

## 1. A belief base that repairs itself

A `BeliefBase` stores beliefs and the justifications between them. Premises come from sources
(tools, documents, people). Conclusions are derived from other beliefs.

```python
from corollary import BeliefBase, rule


@rule
def growth(previous: float, current: float) -> float:
    """Percent growth from previous to current."""
    return (current - previous) / previous * 100


@rule
def trend(g: float) -> str:
    return "strong" if g >= 8 else "modest" if g >= 3 else "flat"


kb = BeliefBase()
kb.assert_("revenue:Q2", 4.3e9, source="tool:sec_filings")
kb.assert_("revenue:Q3", 4.5e9, source="tool:sec_filings")
kb.assert_("fx:exposure", 0.31, source="tool:treasury")

kb.derive("growth:Q3_vs_Q2", growth, "revenue:Q2", "revenue:Q3")
kb.derive("trend:Q3", trend, "growth:Q3_vs_Q2")
kb.derive("risk:fx", lambda e: e > 0.25, "fx:exposure")

print(kb.value("trend:Q3"))  # modest
kb.changes()  # read (and clear) the change log, so the next diff starts here
```

Now the Q2 figure is restated. Retract it, assert the corrected value, and propagate. `propagate()`
re-derives what lost support and returns every status change since the change log was last read:

```python
kb.retract("revenue:Q2", reason="restated in 10-K/A")
kb.assert_("revenue:Q2", 4.1e9, source="tool:sec_filings")

for change in kb.propagate(include_kept=True):
    print(change)
```

```text
OUT  revenue:Q2               (retracted: restated in 10-K/A)
OUT  growth:Q3_vs_Q2          (lost support: revenue:Q2)
OUT  trend:Q3                 (lost support: growth:Q3_vs_Q2)
IN   revenue:Q2               (asserted by tool:sec_filings)
IN   growth:Q3_vs_Q2          (re-derived: 9.7561)
IN   trend:Q3                 (re-derived: 'strong')
KEPT risk:fx                  (independent of revenue:Q2)
```

Nothing was re-run from scratch. Only the two conclusions that depended on Q2 were recomputed, and
`risk:fx` was never touched. Ask why the trend is what it is:

```python
print(kb.proof("trend:Q3"))
```

```text
trend:Q3 = 'strong'  [IN 0.95]  rule:trend
└── growth:Q3_vs_Q2 = 9.7561  [IN 0.95]  rule:growth
    ├── revenue:Q2 = 4,100,000,000  [IN 0.95]  tool:sec_filings
    └── revenue:Q3 = 4,500,000,000  [IN 0.95]  tool:sec_filings
```

The old revisions are not deleted. `kb.explain("growth:Q3_vs_Q2@1")` still tells you what the old
value was and why it is `OUT`.

## 2. An agent, offline

An `Agent` puts a model in front of the belief base. The model proposes actions in the
[claim contract](guides/contract.md): call a tool, cite a document, make a claim, or answer. The runtime
executes tools itself, validates every claim, and records everything as beliefs.

`ScriptedModel` replays responses you write by hand, which is ideal for tests and for learning what a
model is expected to send:

```python
from corollary import Agent, ScriptedModel, tool


@tool(trust="high")
def get_revenue(quarter: str) -> float:
    """Quarterly revenue in USD."""
    return {"Q2": 4.3e9, "Q3": 4.5e9}[quarter]


model = ScriptedModel(
    [
        {
            "actions": [
                {"type": "call_tool", "tool": "get_revenue", "args": {"quarter": "Q2"}, "key": "revenue:Q2"},
                {"type": "call_tool", "tool": "get_revenue", "args": {"quarter": "Q3"}, "key": "revenue:Q3"},
            ]
        },
        {
            "actions": [
                {
                    "type": "claim",
                    "key": "growth",
                    "claim": "Q3 revenue grew 4.65% over Q2",
                    "formula": "({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100",
                    "follows_from": ["revenue:Q2", "revenue:Q3"],
                },
                {"type": "answer", "text": "Q3 revenue grew 4.65% over Q2.", "follows_from": ["growth"]},
            ]
        },
    ]
)

agent = Agent(model, tools=[get_revenue])
report = agent.run("Compare Q2 and Q3 revenue.")

print(report.answer)  # Q3 revenue grew 4.65% over Q2.
print(report.verify().ok)  # True
```

The runtime re-executed the formula and confirmed it reproduces the growth figure. If the model had
stated a different number, the claim would have been rejected and the error fed back to it on the next
turn. A complete version of this example, including a repair after a correction, is in
[`examples/agent_offline.py`](https://github.com/gabe-santana/corollary/blob/main/examples/agent_offline.py).

## 3. An agent with Claude

Install the extra and make credentials available (`ANTHROPIC_API_KEY`, or `ant auth login`):

```python
from corollary import Agent, AnthropicModel

agent = Agent(AnthropicModel("claude-opus-5-5"), tools=[get_revenue])
report = agent.run("Compare Q2 and Q3 revenue and assess the growth trend.")

print(report.answer)
print(report.proof)
print(report.verify())
```

When an input changes, `agent.repair()` re-derives the affected beliefs, including the answer. Each
re-derivation is one model call that sees **only the current values** of that belief's inputs:

```python
agent.kb.retract("revenue:Q2", reason="restated in 10-K/A")
agent.kb.assert_("revenue:Q2", 4.1e9, source="tool:get_revenue")

for change in agent.repair():
    print(change)

print(report.answer)  # the repaired answer; `report` reads the belief base live
```

## Next steps

- [Core concepts](concepts.md): what beliefs, revisions, justifications and labels are.
- [The belief base](guides/belief-base.md): everything the kernel can do without a model.
- [Agents](guides/agents.md): the run loop, dependency policies, repair, re-verification and narrowing.
- [`examples/self_repairing_report.py`](https://github.com/gabe-santana/corollary/blob/main/examples/self_repairing_report.py):
  a 20-conclusion report that repairs itself when one input is corrected.
