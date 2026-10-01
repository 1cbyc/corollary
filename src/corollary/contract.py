"""The claim contract: the only thing a model is allowed to say.

A model response must be a JSON object ``{"actions": [...]}``. Each action is parsed into one of
:class:`ToolCall`, :class:`Cite`, :class:`Claim` or :class:`Answer`. Anything else is rejected,
and the rejection is fed back to the model on its next turn. Parsing is purely syntactic; the
:class:`~corollary.Agent` then checks every action against the belief base (dependencies exist
and are ``IN``, formulas reproduce values, quotes appear in documents) before accepting it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .errors import ContractViolation

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
    """Find the JSON payload in a model response (bare, fenced, or embedded in prose)."""
    stripped = text.strip()
    candidates = [stripped]
    candidates += [m.group(1).strip() for m in _FENCE.finditer(text)]
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            pass
    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch in "{["):
        try:
            payload, _ = decoder.raw_decode(text, start)
            return payload
        except json.JSONDecodeError:
            continue
    raise ContractViolation('response is not valid JSON; reply with a single JSON object {"actions": [...]}')


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
            errors.extend(f"action {i + 1}: {e}" for e in exc.errors)
    return ParsedResponse(tuple(actions), tuple(errors))


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
        action = Answer(text=text_field("text"), follows_from=keys_field("follows_from"), confidence=confidence_field())
    if errors:
        raise ContractViolation(errors)
    return action
