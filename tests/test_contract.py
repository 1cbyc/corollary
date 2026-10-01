from __future__ import annotations

import pytest

from corollary import Answer, Cite, Claim, ContractViolation, ToolCall, parse_response
from corollary.contract import CONTRACT_SCHEMA, extract_json


def test_parses_all_action_types() -> None:
    parsed = parse_response(
        """{"actions": [
            {"type": "call_tool", "tool": "get_revenue", "args": {"quarter": "Q2"}, "key": "revenue:Q2"},
            {"type": "cite", "document": "10-K", "quote": "Revenue was $4.3B", "key": "rev", "value": 4.3e9},
            {"type": "claim", "key": "g", "value": 4.65, "claim": "growth", "follows_from": ["a", "b"],
             "formula": "{a} + {b}", "confidence": 0.9},
            {"type": "answer", "text": "done", "follows_from": "g"}
        ]}"""
    )
    assert parsed.errors == ()
    tool_call, cite, claim, answer = parsed.actions
    assert tool_call == ToolCall("get_revenue", {"quarter": "Q2"}, "revenue:Q2")
    assert isinstance(cite, Cite) and cite.value == 4.3e9
    assert claim == Claim("g", 4.65, "growth", ("a", "b"), "{a} + {b}", 0.9)
    assert answer == Answer("done", ("g",))


@pytest.mark.parametrize(
    "text",
    [
        'Sure! Here you go:\n```json\n{"actions": [{"type": "answer", "text": "x"}]}\n```',
        'Thinking... {"actions": [{"type": "answer", "text": "x"}]} hope that helps',
        '{"type": "answer", "text": "x"}',
        '[{"type": "answer", "text": "x"}]',
    ],
)
def test_lenient_json_extraction(text: str) -> None:
    (action,) = parse_response(text).actions
    assert action == Answer("x")


def test_args_may_be_json_string() -> None:
    (action,) = parse_response('{"actions": [{"type": "call_tool", "tool": "t", "args": "{\\"q\\": 1}"}]}').actions
    assert action == ToolCall("t", {"q": 1})


def test_claim_may_omit_value_when_formula_given() -> None:
    (action,) = parse_response('{"actions": [{"type": "claim", "key": "k", "formula": "1 + 1"}]}').actions
    assert isinstance(action, Claim) and action.value is None


@pytest.mark.parametrize(
    ("action", "message"),
    [
        ('{"type": "fly"}', "unknown action type"),
        ('"just a string"', "must be a JSON object"),
        ('{"type": "call_tool"}', "requires 'tool'"),
        ('{"type": "call_tool", "tool": "t", "args": "not json"}', "not valid JSON"),
        ('{"type": "call_tool", "tool": "t", "args": [1]}', "must be an object"),
        ('{"type": "cite", "document": "d", "quote": "q", "key": "k"}', "requires 'value'"),
        ('{"type": "claim", "key": "k"}', "requires 'value'"),
        ('{"type": "claim", "key": "k", "value": 1, "follows_from": [1]}', "list of keys"),
        ('{"type": "claim", "key": "k", "value": 1, "confidence": 2}', "between 0 and 1"),
        ('{"type": "claim", "key": 5, "value": 1}', "must be a string"),
        ('{"type": "answer"}', "requires 'text'"),
    ],
)
def test_per_action_errors(action: str, message: str) -> None:
    parsed = parse_response('{"actions": [' + action + ', {"type": "answer", "text": "ok"}]}')
    assert parsed.actions == (Answer("ok"),)
    assert len(parsed.errors) >= 1 and message in parsed.errors[0]
    assert parsed.errors[0].startswith("action 1:")


@pytest.mark.parametrize("text", ["no json here", '{"foo": 1}', '{"actions": 5}', "42"])
def test_unusable_responses_raise(text: str) -> None:
    with pytest.raises(ContractViolation):
        parse_response(text)


def test_extract_json_prefers_whole_text() -> None:
    assert extract_json('{"a": {"b": 1}}') == {"a": {"b": 1}}


def test_schema_shape() -> None:
    item = CONTRACT_SCHEMA["properties"]["actions"]["items"]
    assert item["properties"]["type"]["enum"] == ["call_tool", "cite", "claim", "answer"]
    assert item["additionalProperties"] is False
