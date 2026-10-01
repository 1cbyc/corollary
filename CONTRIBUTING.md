# Contributing to Corollary

Thank you for your interest in Corollary. The project is early, which makes this the best time to shape
it: the belief schema, the claim contract and the verifier suite are all still open to change.

This guide covers how to propose changes, set up a development environment, and get a pull request merged.
Everyone who takes part is expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

You don't need to write kernel code to make a difference:

- **Discuss the design.** Comment on the belief schema, the contract, or the open problems in
  [Discussions](https://github.com/gabe-santana/corollary/discussions).
- **Propose a demo scenario** from your domain (finance, law, science, operations): a task where one input
  gets corrected, and the downstream conclusions should repair themselves.
- **Write a verifier.** A [`Check`](docs/guides/verification.md#writing-a-check) is a small, self-contained
  class. Unit conversions, date arithmetic and table lookups are all good candidates.
- **Add a model adapter.** An adapter implements a single method, `complete(system, prompt) -> str`.
  See [Models](docs/guides/models.md).
- **Improve the docs.** If something confused you, it will confuse the next person too.
- **Report bugs** with a minimal reproduction (see below).

For larger changes (new public APIs, changes to labeling semantics, a new dependency policy), please open
an issue or discussion first, so we can agree on the design before you spend time on code.

## Development setup

Corollary supports Python 3.10 and later. The core has no runtime dependencies.

```bash
git clone https://github.com/gabe-santana/corollary.git
cd corollary
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                 # optional: run the linters on every commit
```

## Running the checks

Every pull request must pass the same checks CI runs:

```bash
pytest                             # tests and doctests
pytest --cov                       # with a coverage report
ruff check .                       # lint
ruff format .                      # format
mypy                               # strict type checking of src/corollary
```

To preview the documentation site locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```

## Writing tests

- Tests live in `tests/`, one file per module (`test_kernel.py`, `test_agent.py`, ...).
- **Never call a real model in tests.** Use `ScriptedModel` to replay the exact responses you want to
  exercise, including malformed ones. Every test must run offline and deterministically.
- **Use the `clock` fixture** for anything involving validity windows, never `time.sleep`.
- Test behavior through the public API where possible. Kernel invariants (labels, cascades, conflicts) are
  the most important things to cover: if you change labeling, add a test showing the before and after.
- Bugs get a regression test that fails before the fix.

## Code style

- Formatting and import order are enforced by `ruff format` and `ruff check`. Lines are at most 120 characters.
- The package is fully typed and checked with `mypy --strict`. New code needs type annotations.
- Public functions and classes need docstrings that say what they do and what they guarantee. Use the
  existing modules as a reference for tone and density.
- Keep the core dependency-free. Integrations with third-party libraries go behind an optional extra
  (see `[project.optional-dependencies]` in `pyproject.toml`) and import lazily.
- Prefer explicit errors to silent fallbacks. If the runtime can't guarantee something, it should raise a
  subclass of `CorollaryError` with a message that says what to do next.

## The one rule for kernel changes

Corollary's value comes from guarantees enforced by code outside the model, listed in
[docs/architecture.md](docs/architecture.md#guarantees). The most important one: **a retracted fact can never
silently survive in a conclusion** (over-retraction is acceptable, under-retraction is a bug).

A change that weakens a guarantee needs an explicit discussion in the pull request, and usually a new
opt-in setting rather than a changed default.

## Commit messages and pull requests

- Keep each pull request focused on one change. Small PRs are reviewed faster.
- Write commit messages in the imperative mood ("Add citation span offsets", not "Added ...").
- Fill in the pull request template, including how you tested the change.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) for any user-visible change.
- A maintainer will review your PR. Expect questions: they are about the design, never about you.

## Reporting bugs

Open an issue with the bug report template and include:

1. A minimal script that reproduces the problem. Most kernel bugs can be shown with a `BeliefBase` and a
   few `assert_` / `derive` / `retract` calls; agent bugs with an `Agent` and a `ScriptedModel`.
2. What you expected and what happened instead, including the full traceback.
3. Your Corollary version (`python -c "import corollary; print(corollary.__version__)"`), Python version and OS.

Security issues should **not** be reported publicly. See [SECURITY.md](SECURITY.md).

## Releasing (maintainers)

1. Update the version in `src/corollary/_version.py` and move the **Unreleased** changelog entries under the
   new version heading.
2. Merge to `main`, then create a GitHub release with a `vX.Y.Z` tag.
3. The `Release` workflow builds the distribution and publishes it to PyPI through trusted publishing.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers
the project.
