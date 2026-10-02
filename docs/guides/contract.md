# The claim contract

The claim contract is the only thing a model is allowed to say to Corollary. It is a JSON object with a
list of actions:

```json
{"actions": [ ... ]}
```

The runtime parses every response, validates every action against the belief base, and applies only the
actions that pass. Rejections are reported back to the model on its next turn. A model can't write state
directly, can't fabricate a tool result, and can't make a claim depend on something it was not shown.

The full instructions sent to the model are in `corollary.SYSTEM_PROMPT`.

## Actions

### `call_tool`

```json
{"type": "call_tool", "tool": "get_revenue", "args": {"quarter": "Q2"}, "key": "revenue:Q2"}
```

| Field | Required | Notes |
|---|---|---|
| `tool` | yes | Name of a registered tool |
| `args` | no | Object of arguments, or a JSON-encoded string of one; validated against the signature |
| `key` | no | Belief key for the result; defaults to `tool:arg1,arg2` |
| `claim` | no | Natural-language description stored with the result |

The runtime executes the tool. Its return value becomes a **premise** with source
`tool:get_revenue(quarter='Q2')`, visible to the model from the next turn.

### `cite`

```json
{"type": "cite", "document": "10-K", "quote": "Total revenue for Q2 was $4.3 billion",
 "key": "revenue:Q2", "value": 4300000000, "claim": "Q2 revenue"}
```

| Field | Required | Notes |
|---|---|---|
| `document` | yes | Name of a registered document |
| `quote` | yes | Text copied from the document |
| `key` | yes | Belief key |
| `value` | yes | The value the quote states |
| `claim` | no | Natural-language description |

The quote must appear in the document (case- and whitespace-insensitive), and a numeric or string value
must be stated in the quote. Numbers match at the scale their unit states, so `4.3 billion` states `4300000000`.
See [Documents and citations](documents.md).

### `claim`

```json
{"type": "claim", "key": "growth:Q3_vs_Q2", "value": 4.651162790697675,
 "claim": "Q3 revenue grew 4.65% over Q2",
 "follows_from": ["revenue:Q2", "revenue:Q3"],
 "formula": "({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100",
 "confidence": 0.95}
```

| Field | Required | Notes |
|---|---|---|
| `key` | yes | A new key, or an existing key with the same value |
| `value` | yes, unless `formula` is given | Any JSON value. With a formula and no value, the computed value is used |
| `claim` | no | One-sentence statement. Also used as the instruction when the belief is re-derived |
| `follows_from` | no | Keys the claim rests on |
| `formula` | no | Arithmetic over `{key}` placeholders, re-executed by the runtime |
| `confidence` | no | 0 to 1; scales the step's confidence |

### `answer`

```json
{"type": "answer", "text": "Q3 revenue grew 4.65% over Q2: modest growth.",
 "follows_from": ["growth:Q3_vs_Q2", "trend"]}
```

The answer is stored as a belief (key `answer`, or `answer:2`, ... on later runs). It is validated like a
claim, so it goes `OUT` when its support is retracted and is re-derived by `repair()`. Actions after an
accepted answer in the same response are ignored.

## Validation rules

| Rule | Rejection message (abridged) |
|---|---|
| The response must contain JSON with an `actions` list | `response is not valid JSON` |
| Each action must have a known `type` and the required fields | `unknown action type`, `claim requires 'value'` |
| Keys may not contain whitespace, `@` or braces | `invalid belief key` |
| `follows_from` keys must be **visible in this turn's context**, or claimed earlier in the same response | `not in this turn's context`, `unknown key` |
| A claim may not use a tool result from the **same** response | `the result of a tool called in this same response` |
| A formula must reproduce the stated value (relative tolerance 1e-6) | `evaluates to X, but the claim states Y` |
| A key that already holds a different value may not be reused | `already holds X; use a new key` |
| Tools must exist and accept the arguments | `unknown tool`, `invalid arguments` |
| Tool exceptions are reported, not raised | `tool 'x' raised KeyError: ...` |
| Quotes must appear in the document and state the value | `quote not found`, `not stated in the quoted text` |
| In `declared` mode, an answer must list its support | `an answer must list the beliefs it rests on` |
| Under the conservative policy, the context must not have changed mid-turn | `beliefs in this turn's context changed during the turn` |

A malformed action does not invalidate the rest of the response: valid actions are applied, and each
problem is reported individually (`action 2: claim requires 'key'`).

## Formulas

Formulas reference beliefs with `{key}` placeholders:

```text
({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100
max({cash} - {debt}, 0)
round({margin}, 2)
```

Allowed: numeric literals, `+ - * / // % **` (exponents up to 64), unary minus, parentheses, and the
functions `abs`, `min`, `max`, `round`, `sqrt`, `log`, `exp` with positional arguments.

Not allowed: names other than placeholders, attribute access, subscripts, strings, comprehensions, keyword
arguments, or any other syntax. Formulas are evaluated by a restricted AST interpreter, never by `eval`,
so an untrusted formula can't run code. Every number is a float, and every intermediate result must be a
finite real number, so a formula can't hang the process with huge powers either: overflow, `inf`, `nan`,
complex numbers and nesting deeper than 100 levels are errors, fed back to the model like any other.

A claim with a formula gets rule-level confidence, because the step was checked mechanically. The verifier
re-executes every formula again when it checks a proof.

## Leniency

Models don't always produce clean JSON. The parser accepts:

- a bare JSON object, or one inside a Markdown code fence, or embedded in surrounding prose. When the
  response contains several JSON values, the first one shaped like a response wins, so a list of numbers
  in a sentence before the actions is skipped;
- a single action object (`{"type": "answer", ...}`) or a bare list of actions;
- `args` as an object or as a JSON-encoded string;
- `follows_from` as a list or a single string;
- `confidence` as a numeric string (`"0.9"`) or a percentage (`"90%"`), and an answer `text` that is a
  bare number;
- Python-style literals (single quotes, `True`, `None`) when nothing else parses.

Everything else is strict. When nothing parses, the feedback says where the JSON broke.

## Structured output

For providers that support schema-constrained generation, `corollary.contract.CONTRACT_SCHEMA` is the
JSON Schema of a response. `AnthropicModel(structured=True)` sends it as `output_config.format`. Strict
schema modes reject free-form objects, so the schema declares `args` as a JSON-encoded string. The runtime
validates every response either way, so structured output only reduces retries, never weakens checks.

## Using the parser directly

```python
from corollary import parse_response

parsed = parse_response(model_text)
parsed.actions  # tuple of ToolCall | Cite | Claim | Answer
parsed.errors  # one message per action that failed to parse
```

`parse_response` raises `ContractViolation` only when nothing usable can be read.
