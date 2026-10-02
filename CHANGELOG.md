# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may contain breaking changes.

## [Unreleased]

## [0.1.0a1] - 2026-10-02

First public pre-release.

### Added

- **Kernel.** `BeliefBase`: a justification-based truth maintenance system over versioned beliefs.
  Incremental labeling restricted to the affected region, well-founded support (cycles alone never keep a
  belief `IN`), non-monotonic `unless` justifications with odd-loop detection and rollback, retraction and
  restoration, and a change log with reasons for every transition.
- **Re-derivation.** `propagate()` re-runs rules automatically and model-derived beliefs through a
  re-deriver, with early cutoff when a recomputed value is unchanged.
- **Rules.** The `@rule` decorator for deterministic derivations, replayable by the verifier.
- **Conflicts.** Value conflicts and user-defined `Constraint`s are first-class `Conflict` objects
  carrying both support chains. `resolve()`, plus the resolvers `PreferHigherConfidence`, `PreferNewest`,
  `PreferSource` and `AskHuman`.
- **Time.** Validity windows (`ttl`, `valid_until`) on evidence, `refresh()`, `stale()`, and in-place
  renewal that avoids needless cascades.
- **Documents.** `add_document()` and `cite()` with span-checked quotes and value checks.
- **Proofs.** `Proof` snapshots with tree rendering, Mermaid and Graphviz export, JSON round-trip and diffs.
- **Verification.** `Verifier` with structure, grounding, arithmetic (formula and rule replay), citation,
  temporal and numeric-provenance checks, plus a `Check` protocol for custom checks.
- **Agent runtime.** `Agent` with the claim contract, runtime-executed tools that emit premises, a
  projector that builds every context from `IN` beliefs only, conservative and declared dependency
  policies, `repair()`, `reverify()` and ablation-based `narrow()`.
- **Models.** `AnthropicModel` (Claude, via the official SDK), `OpenAIModel` (any Chat Completions
  endpoint), `CallableModel` and `ScriptedModel`.
- **Learned reliability.** `TrustLedger` records when sources turn out right or wrong and re-estimates
  their reliability from the trust policy's prior, optionally forgetting old outcomes
  (`memory_half_life`). Ledgers can be shared across belief bases and are saved with a base that owns one.
- **Outcomes.** `retract(..., fault="source")`, `resolve(..., learn=True)`, `AskHuman` decisions,
  independent confirmations, `record_outcome()`, and the agent's verified formulas and citations
  (`learn_from_checks`) all feed the ledger.
- **Corroboration.** Agreeing premises from independent origins combine by noisy-OR. Sources declare a
  shared origin with `origin=` (on `assert_`, `Source` and `@tool`); `TrustPolicy(corroboration=False)`
  turns it off.
- **Evidence decay.** `half_life=` on `assert_` and `@tool` fades confidence without changing status.
  `faded()` lists faded premises, and `Agent.reverify()` now refreshes them too.
- **Self-consistency.** `Agent(self_consistency=k)` samples unverified claims `k` times and uses the
  agreement rate as the step's certainty.
- A confidence guide in the documentation.
- **Persistence.** JSON snapshots with `save()` / `load()`, including the trust ledger.
- Examples: a 20-conclusion self-repairing report, an offline agent, and a Claude agent.

[Unreleased]: https://github.com/gabe-santana/corollary/compare/v0.1.0a1...HEAD
[0.1.0a1]: https://github.com/gabe-santana/corollary/releases/tag/v0.1.0a1
