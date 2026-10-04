"""The claim contract: the only thing a model is allowed to say.

A model response must be a JSON object ``{"actions": [...]}``. Each action is parsed into one of
:class:`ToolCall`, :class:`Cite`, :class:`Claim` or :class:`Answer`. Anything else is rejected,
and the rejection is fed back to the model on its next turn. Parsing is purely syntactic; the
:class:`~corollary.Agent` then checks every action against the belief base (dependencies exist
and are ``IN``, formulas reproduce values, quotes appear in documents) before accepting it.
"""

from __future__ import annotations

import ast
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import ContractViolation

__all__ = [
    "CONTRACT_SCHEMA",
    "SYSTEM_PROMPT",
    "Action",
    "Answer",
    "Cite",
    "Claim",
    "ParsedResponse",
    "ToolCall",
    "extract_json",
    "parse_response",
]

SYSTEM_PROMPT = """\
You are the reasoning engine inside Corollary, a runtime that stores state as a graph of beliefs \
instead of a conversation. You never see a chat history. Each turn you receive the task and the \
beliefs the runtime currently holds, and you respond with a single JSON object and nothing else:

{"actions": [ ... ]}

Each action is one of:

1. {"type": "call_tool", "tool": "<name>", "args": {...}, "key": "<belief key for the result>"}
   The runtime executes the tool and records the result as a belief under "key". You will see it \
next turn. Never guess a tool result.
2. {"type": "cite", "document": "<name>", "quote": "<text copied exactly from the document>", \
"key": "<key>", "value": <the value the quote states>, "claim": "<one sentence>"}
3. {"type": "claim", "key": "<new key>", "value": <value>, "claim": "<one sentence>", \
"follows_from": ["<key>", ...], "formula": "<optional>", "confidence": <optional, 0 to 1>}
4. {"type": "answer", "text": "<final answer>", "follows_from": ["<key>", ...]}

Rules:
- "follows_from" may only list keys shown under "Beliefs" in this turn, or keys you claim earlier \
in the same response. A claim cannot use the result of a tool called in the same response.
- For every computed number give a formula over beliefs, using {key} placeholders, for example \
"({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100". The runtime re-executes it and rejects \
the claim if it does not reproduce "value".
- Take numbers from beliefs, never from memory. If a fact is missing, call a tool or cite a document.
- Keys are short and contain no spaces, "@" or braces, e.g. "growth:Q3_vs_Q2". Never reuse a key \
that already holds a different value.
- Keep each claim atomic: one fact or one computation.
- Never use keys listed under "Conflicts".
- If the runtime reports rejected actions, correct them.
- When the task is answered, emit exactly one "answer" action whose "follows_from" lists the \
beliefs it rests on.
"""

ACTION_TYPES = ("call_tool", "cite", "claim", "answer")

CONTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(ACTION_TYPES)},
                    "tool": {"type": "string"},
                    "args": {"type": "string", "description": "JSON-encoded object of tool arguments"},
                    "key": {"type": "string"},
                    "document": {"type": "string"},
                    "quote": {"type": "string"},
                    "value": {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "boolean"}, {"type": "null"}]},
                    "claim": {"type": "string"},
                    "follows_from": {"type": "array", "items": {"type": "string"}},
                    "formula": {"type": "string"},
                    "confidence": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["actions"],
    "additionalProperties": False,
}
"""JSON Schema of a response, for adapters that support schema-constrained output. ``args`` is a
JSON-encoded string here because strict schema modes reject free-form objects; the parser
accepts either form."""


@dataclass(frozen=True)
class ToolCall:
    tool: str
    args: Mapping[str, Any] = field(default_factory=dict)
    key: str | None = None
    claim: str = ""


@dataclass(frozen=True)
class Cite:
    document: str
    quote: str
    key: str
    value: Any
    claim: str = ""


@dataclass(frozen=True)
class Claim:
    key: str
    value: Any
    claim: str = ""
    follows_from: tuple[str, ...] = ()
    formula: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Answer:
    text: str
    follows_from: tuple[str, ...] = ()
    confidence: float | None = None


Action = ToolCall | Cite | Claim | Answer

_MISSING = object()


@dataclass(frozen=True)
class ParsedResponse:
    """Actions that parsed, and an error message for each one that did not."""

    actions: tuple[Action, ...]
    errors: tuple[str, ...] = ()


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Find the JSON payload in a model response (bare, fenced, or embedded in prose).

    A response may contain several JSON values, for example a list of numbers in a sentence
    before the actions. An object with ``actions`` wins; otherwise the first single action or list
    of actions does. Python-style literals (single quotes, ``True``, ``None``) are accepted as a
    last resort, as long as they hold only JSON values.
    """
    stripped = text.strip()
    blocks = [stripped, *(m.group(1).strip() for m in _FENCE.finditer(text))]
    found: list[Any] = []
    error: json.JSONDecodeError | None = None
    for block in blocks:
        try:
            found.append(json.loads(block))
        except json.JSONDecodeError as exc:
            error = error or exc
        except (ValueError, RecursionError):  # an integer with thousands of digits, absurd nesting
            continue
    whole_block_decoded = bool(found)
    if not any(_shape(p) < _NOT_A_RESPONSE for p in found):
        found += _embedded_json(text)
    if not any(_shape(p) < _NOT_A_RESPONSE for p in found):
        found += _python_literals(blocks)
    if not any(_shape(p) < _NOT_A_RESPONSE for p in found) and not whole_block_decoded:
        # Only fragments decoded (say, the "[]" inside a malformed object): the parse error of the
        # response itself tells the model more than "each action must be a JSON object" would.
        found = []
    if not found:
        detail = f" ({error.msg} at line {error.lineno}, column {error.colno})" if error else ""
        raise ContractViolation(
            f'response is not valid JSON{detail}; reply with a single JSON object {{"actions": [...]}}'
        )
    return min(found, key=_shape)  # min() keeps the first of equally shaped candidates


_NOT_A_RESPONSE = 3


def _shape(payload: Any) -> int:
    """How much ``payload`` looks like a contract response; lower is better."""
    if isinstance(payload, dict):
        return 0 if "actions" in payload else 1 if "type" in payload else _NOT_A_RESPONSE
    if isinstance(payload, list) and payload and all(isinstance(item, dict) for item in payload):
        # A list of actions is as good as a single one, so an example action quoted later in the
        # prose can't displace the real list that came first.
        return 1 if any("type" in item for item in payload) else 2
    return _NOT_A_RESPONSE


_MAX_DECODE_ATTEMPTS = 200


def _embedded_json(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    found: list[Any] = []
    position = 0
    failures = 0
    while (start := _next_bracket(text, position)) != -1:
        try:
            payload, end = decoder.raw_decode(text, start)
        except (ValueError, RecursionError):
            # Each failed attempt can scan to the end of the text, so a response full of brackets
            # ("[[[[...") would take quadratic time. Real responses need only a few attempts.
            failures += 1
            if failures > _MAX_DECODE_ATTEMPTS:
                break
            position = start + 1
            continue
        found.append(payload)
        position = end  # Skip the inside of a decoded value, so its parts aren't candidates too.
    return found


def _next_bracket(text: str, position: int) -> int:
    hits = [i for i in (text.find("{", position), text.find("[", position)) if i != -1]
    return min(hits, default=-1)


def _python_literals(blocks: list[str]) -> list[Any]:
    found: list[Any] = []
    for block in blocks:
        try:
            payload = _json_values(ast.literal_eval(block))
        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
            continue
        if _shape(payload) < _NOT_A_RESPONSE:
            found.append(payload)
    return found


def _json_values(value: Any) -> Any:
    """``value`` with tuples as lists, or ``TypeError`` if it holds anything JSON can't (a set,
    bytes, a complex number), so a Python literal can't put an unsaveable value in the base."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_values(v) for v in value]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: _json_values(v) for k, v in value.items()}
    raise TypeError(f"{type(value).__name__} is not a JSON value")


def parse_response(text: str) -> ParsedResponse:
    """Parse a model response into actions. Raises :class:`ContractViolation` only when nothing
    usable could be read; per-action problems are returned in ``errors``."""
    payload = extract_json(text)
    if isinstance(payload, dict) and "actions" in payload:
        items = payload["actions"]
    elif isinstance(payload, dict) and "type" in payload:
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ContractViolation('response must be a JSON object with an "actions" list')
    if not isinstance(items, list):
        raise ContractViolation('"actions" must be a list')
    actions: list[Action] = []
    errors: list[str] = []
    for i, item in enumerate(items):
        try:
            actions.append(parse_action(item))
        except ContractViolation as exc:
            # The model never sees its previous response, so say which action this was.
            errors.extend(f"action {i + 1}{_label(item)}: {e}" for e in exc.errors)
    return ParsedResponse(tuple(actions), tuple(errors))


def _fraction(text: str) -> float | None:
    """``"0.9"`` -> 0.9 and ``"90%"`` -> 0.9; ``None`` when ``text`` isn't a number."""
    text = text.strip()
    percent = text.endswith("%")
    try:
        number = float(text.rstrip("%").strip())
    except ValueError:
        return None
    return number / 100 if percent else number


def _label(item: Any) -> str:
    """A short reminder of what an action was, e.g. ``(claim, key 'growth')``."""
    if not isinstance(item, dict):
        return ""
    parts = [str(item["type"])] if isinstance(item.get("type"), str) else []
    for name in ("tool", "key", "document"):
        value = item.get(name)
        if isinstance(value, str) and value:
            parts.append(f"{name} {value[:60]!r}")
    return f" ({', '.join(parts)})" if parts else ""


def parse_action(item: Any) -> Action:
    if not isinstance(item, dict):
        raise ContractViolation("each action must be a JSON object")
    kind = item.get("type")
    if kind not in ACTION_TYPES:
        raise ContractViolation(f"unknown action type {kind!r}; expected one of {', '.join(ACTION_TYPES)}")
    errors: list[str] = []

    def text_field(name: str, required: bool = True) -> str:
        value = item.get(name, _MISSING)
        if value is _MISSING or value is None:
            if required:
                errors.append(f"{kind} requires {name!r}")
            return ""
        if not isinstance(value, str):
            errors.append(f"{name!r} must be a string")
            return ""
        return value

    def keys_field(name: str) -> tuple[str, ...]:
        value = item.get(name) or []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"{name!r} must be a list of keys")
            return ()
        return tuple(value)

    def confidence_field() -> float | None:
        value = item.get("confidence")
        if value is None:
            return None
        if isinstance(value, str) and (number := _fraction(value)) is not None:
            value = number  # "0.9" and "90%" are common slips; accept what is unambiguous
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            errors.append("'confidence' must be a number between 0 and 1")
            return None
        return float(value)

    action: Action
    if kind == "call_tool":
        args = item.get("args", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                errors.append("'args' is not valid JSON")
                args = {}
        if args is None:
            args = {}
        if not isinstance(args, dict):
            errors.append("'args' must be an object")
            args = {}
        action = ToolCall(
            tool=text_field("tool"),
            args=args,
            key=text_field("key", required=False) or None,
            claim=text_field("claim", False),
        )
    elif kind == "cite":
        if "value" not in item:
            errors.append("cite requires 'value'")
        action = Cite(
            document=text_field("document"),
            quote=text_field("quote"),
            key=text_field("key"),
            value=item.get("value"),
            claim=text_field("claim", required=False),
        )
    elif kind == "claim":
        formula = text_field("formula", required=False) or None
        if "value" not in item and formula is None:
            errors.append("claim requires 'value' (or a 'formula' to compute it)")
        action = Claim(
            key=text_field("key"),
            value=item.get("value"),
            claim=text_field("claim", required=False),
            follows_from=keys_field("follows_from"),
            formula=formula,
            confidence=confidence_field(),
        )
    else:
        text = item.get("text")
        if isinstance(text, (int, float)) and not isinstance(text, bool) and math.isfinite(text):
            item = {**item, "text": str(text)}  # a bare number is a fine answer text
        action = Answer(text=text_field("text"), follows_from=keys_field("follows_from"), confidence=confidence_field())
    if errors:
        raise ContractViolation(errors)
    return action
