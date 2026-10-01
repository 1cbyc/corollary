# Related work

Corollary is not a new theory. It combines well-established ideas from knowledge representation and
incremental computation, and applies them to LLM agents. This page credits that work and explains where
Corollary differs from tools you may already use.

## Foundations

**Truth maintenance systems.** Jon Doyle's *A Truth Maintenance System* (1979) introduced the
justification-based TMS: beliefs labeled `IN` or `OUT` from recorded justifications, with
non-monotonic "out-lists" and dependency-directed backtracking. Corollary's kernel is a JTMS in this
tradition: well-founded labeling, `unless` (out-list) justifications, and retraction cascades.

**Assumption-based TMS.** Johan de Kleer's ATMS (1986) labels each belief with the sets of assumptions
under which it holds, which lets a reasoner explore alternatives in parallel. Corollary doesn't implement
an ATMS yet. It is on the roadmap for exploring competing hypotheses.

**Belief revision.** The AGM theory (Alchourrón, Gärdenfors and Makinson, 1985) formalizes how a rational
agent should revise its beliefs when it learns something that contradicts them. Corollary's conflicts and
resolvers are a practical, policy-driven take on the same question: when sources disagree, which belief
gives way, and on what grounds.

**Why TMSs didn't spread.** Classic truth maintenance required every justification to be written by hand
or derived from a hand-built rule base. That was the bottleneck. Language models can now propose claims
and justifications at scale, while the TMS keeps them consistent. That pairing is the bet behind Corollary.

## Incremental computation

**Spreadsheets and build systems** (Make, Bazel, Salsa, Adapton) recompute only what depends on a changed
input, and stop when a recomputed result is unchanged (*early cutoff*). Corollary applies the same
discipline to an agent's conclusions. A useful one-line description of the project is *incremental
recomputation for agent reasoning*. The difference is that some of Corollary's "build steps" are model
calls, so their dependencies must be inferred conservatively rather than declared exactly.

**Data provenance and lineage**, in databases and data pipelines, records where each value came from.
Corollary records provenance too, and also uses it: the provenance graph drives retraction, repair and
verification.

## Agent memory and frameworks

**Message-log agent frameworks** store state as a growing transcript. They are simple and flexible, but a
wrong fact remains in the log. Corollary keeps a log only as a view (`kb.transcript()`) and builds every
model context from the belief base instead.

**Memory layers and temporal knowledge graphs** for agents store facts or summaries, often with
timestamps, and some can invalidate facts that are contradicted or outdated. Zep's Graphiti, for
example, tracks the validity intervals of facts in a temporal knowledge graph. These systems are close to
Corollary on *expiry* and *contradiction*. The main differences:

| | Memory layers | Corollary |
|---|---|---|
| What is stored | Facts, entities, summaries | Beliefs **and the justifications between them** |
| When a fact is invalidated | That fact is marked invalid | That fact and **everything derived from it** go `OUT`, then are re-derived |
| What the model sees | Retrieved memories, plus the conversation | Only `IN` beliefs; no transcript |
| Conflicts | Often resolved by recency | A first-class `Conflict`; resolved by policy or a person |
| Output | An answer | An answer with a proof and a deterministic verifier |

The two are complementary. A memory layer is a good *source* of premises for a Corollary belief base.

**Prompted reasoning tracking** (asking a model to cite its sources, rate its confidence, or "keep track
of its assumptions") improves outputs, but the guarantees live in the prompt, and a model can ignore a
prompt. Corollary's guarantees live in the runtime.

**Retrieval-augmented generation with citations** grounds answers in documents and often checks that
citations exist. Corollary's `cite` goes further on two points: the cited value must be stated in the
quote, and a cited fact keeps its place in the dependency graph, so revising the document can revise
the conclusions built on it.

## Neuro-symbolic research

There is active research on combining LLMs with symbolic reasoners, logic programming, belief revision
and verification. Corollary is an engineering contribution rather than a research claim: a
small, tested, model-agnostic runtime that makes these ideas usable in everyday agent code. If you know of
closely related work that should be cited here, please open an issue or a pull request.

## References

- Jon Doyle. *A Truth Maintenance System.* Artificial Intelligence 12(3), 1979.
- Johan de Kleer. *An Assumption-based TMS.* Artificial Intelligence 28(2), 1986.
- Carlos Alchourrón, Peter Gärdenfors, David Makinson. *On the Logic of Theory Change: Partial Meet
  Contraction and Revision Functions.* Journal of Symbolic Logic 50(2), 1985.
- Kenneth Forbus and Johan de Kleer. *Building Problem Solvers.* MIT Press, 1993.
- Andrey Mokhov, Neil Mitchell, Simon Peyton Jones. *Build Systems à la Carte.* ICFP 2018.
