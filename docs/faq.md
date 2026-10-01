# FAQ

### Is Corollary a prompting strategy?

No. Corollary doesn't ask a model to track its reasoning. Every guarantee is enforced by code outside the
model: the kernel computes what is believed, the projector decides what the model sees, the runtime
executes tools and validates every claim, and the verifier checks answers deterministically.

### Is it a memory plugin?

No. The belief base *is* the agent's state. Memory, context, tool results and the transcript are all
projections of it. You can feed a memory layer's facts in as premises.

### Which models does it work with?

Any model that can follow instructions and emit JSON. Corollary ships adapters for Claude
(`AnthropicModel`) and any OpenAI-compatible Chat Completions endpoint (`OpenAIModel`), plus
`CallableModel` for anything else. See [Models](guides/models.md).

### Do I need a model at all?

No. The kernel (`BeliefBase` with rules) is useful on its own for any computation where inputs get
corrected and conclusions must stay consistent. The flagship example runs with zero model calls.

### Does it cost more than a normal agent?

Running a task costs about the same: one model call per step. The savings come later. After a correction,
a normal agent re-runs everything, while Corollary re-derives only the affected beliefs, with one call per
affected model belief and none for rules or for values that come out unchanged. Conservative
dependencies can over-retract, and `narrow()` costs one call per antecedent, so use it selectively.

### What happens if the model ignores the contract?

Its response is rejected, partly or entirely, and the errors are shown to it on the next step. Nothing
invalid reaches the belief base. If it never complies, `run()` stops at `max_steps` with
`report.completed == False`.

### Can the model still hallucinate?

It can propose a wrong claim, but the claim can't use facts it wasn't shown, can't misreport a tool
result, can't misquote a document, and can't get arithmetic wrong if it gives a formula. Numbers that
appear from nowhere are flagged by `NumericProvenanceCheck`. A wrong judgement from the model's own
knowledge can still slip through. See [limits](architecture.md#limits-stated-honestly).

### Why is my claim's dependency list so long?

Under the default conservative policy, a claim depends on everything visible when it was generated.
That's what guarantees a retracted fact can't survive in it. Use `dependencies="declared"` for sharper
cascades, or `agent.narrow(key)` to prune dependencies by ablation.

### Why did `propagate()` list beliefs I created earlier?

`propagate()` and `kb.changes()` report net changes since the change log was last read. Call `kb.changes()`
once after building a base, and the next diff shows only what your correction changed. `Agent.run()` does
this automatically.

### Can I use it in production?

Corollary is pre-alpha. The core is tested (`mypy --strict`, 95% branch coverage), but interfaces will
change before 1.0, and the belief base is in-memory and single-threaded. It is ready for experiments,
prototypes and research. Pin the version if you build on it.

### How do I contribute?

See [CONTRIBUTING.md](https://github.com/gabe-santana/corollary/blob/main/CONTRIBUTING.md). Verifiers,
model adapters, demo scenarios from your domain, and work on the open problems are especially welcome.
