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

## Commit messages

Every commit message follows [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/),
the convention most open source projects use. It starts with a type, an optional scope in parentheses, and a
short summary:

```text
<type>(<scope>): <summary>

<body: what changed and why, wrapped at 72 characters>

<footer: Closes #123, BREAKING CHANGE: ...>
```

Only the first line is required. Use one of these types:

| Type | When | Example |
|---|---|---|
| `feat` | A new feature or capability | `feat(agent): add instructions for domain guidance` |
| `fix` | A bug fix | `fix(kernel): roll back a failed assertion completely` |
| `docs` | Documentation only | `docs: describe the dependency order of propagate()` |
| `test` | Adding or correcting tests only | `test(proof): cover deep proofs in render()` |
| `refactor` | A code change that neither fixes a bug nor adds a feature | `refactor(agent): share formula checking` |
| `perf` | A performance improvement | `perf(kernel): compute confidence in linear time` |
| `style` | Formatting only, no change in behavior | `style: apply ruff format` |
| `build` | Packaging and dependencies | `build: pin mkdocs below 2` |
| `ci` | Continuous integration | `ci: skip the Pages deploy while private` |
| `chore` | Maintenance that fits no other type, including releases | `chore(release): 0.1.0a5` |
| `revert` | Reverting an earlier commit | `revert: feat(agent): add instructions` |

- **Scope** is optional. When you use one, name the module or area you changed: `kernel`, `agent`,
  `contract`, `projector`, `tools`, `models`, `verify`, `proof`, `formula`, `textmatch`, `ledger`,
  `examples` or `release`.
- **Summary:** the imperative mood ("add", not "added" or "adds"), lowercase after the colon, no period at
  the end, and at most 72 characters for the whole first line.
- **Body:** explain *why* the change is needed and what it affects, not only what the diff shows.
- **Breaking changes:** add `!` after the type or scope (`feat(agent)!: return errors in the report`) and
  a `BREAKING CHANGE:` footer that tells users how to migrate. Until 1.0, minor versions may break the API,
  but every break is still marked.
- **Issues:** close them from the footer, for example `Closes #52`.

A pull request's **title** follows the same format, because a squash merge uses it as the commit message.

## Pull requests

- Keep each pull request focused on one change. Small PRs are reviewed faster.
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

1. Update the version in `src/corollary/_version.py`, move the **Unreleased** changelog entries under the
   new version heading, and commit it as `chore(release): X.Y.Z`.
2. Optionally, do a dry run: **Actions → Release → Run workflow** publishes to
   [TestPyPI](https://test.pypi.org/p/corollary).
3. Merge to `main`, then create a GitHub release with a `vX.Y.Z` tag matching the version (`v0.1.0a1`
   for `0.1.0a1`). Mark alpha, beta and release-candidate versions as a pre-release.
4. The `Release` workflow runs the tests, checks that the tag matches the version, builds the
   distribution, publishes it to PyPI through trusted publishing and attaches it to the GitHub release.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers
the project.
