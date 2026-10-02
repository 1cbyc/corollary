from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from corollary import AnthropicModel, CallableModel, Model, ModelError, ModelRefusalError, OpenAIModel, ScriptedModel
from corollary.contract import CONTRACT_SCHEMA
from corollary.models import resolve_model


def test_scripted_model_replays_and_records() -> None:
    model = ScriptedModel(["one", {"actions": []}, lambda prompt: prompt.upper()])
    assert model.complete("s", "p") == "one"
    assert model.complete("s", "p") == '{"actions": []}'
    assert model.complete("s", "shout") == "SHOUT"
    assert [c.response for c in model.calls] == ["one", '{"actions": []}', "SHOUT"]
    with pytest.raises(ModelError, match="no responses left"):
        model.complete("s", "p")
    assert model.add("again").remaining == 1
    assert isinstance(model, Model)


def test_callable_model() -> None:
    model = CallableModel(lambda system, prompt: f"{system}|{prompt}", name="echo")
    assert model.complete("a", "b") == "a|b"
    with pytest.raises(ModelError):
        CallableModel(lambda s, p: 42).complete("a", "b")  # type: ignore[arg-type, return-value]


def test_resolve_model() -> None:
    assert isinstance(resolve_model("anthropic:claude-opus-5-5"), AnthropicModel)
    assert resolve_model("claude-sonnet-5-5").name == "claude-sonnet-5-5"
    assert resolve_model("anthropic:").name == AnthropicModel.DEFAULT_MODEL
    assert isinstance(resolve_model("openai:some-model"), OpenAIModel)
    scripted = ScriptedModel()
    assert resolve_model(scripted) is scripted
    with pytest.raises(ValueError):
        resolve_model("mystery-model")
    with pytest.raises(ValueError):
        resolve_model("openai:")
    with pytest.raises(TypeError):
        resolve_model(object())  # type: ignore[arg-type]


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def anthropic_client(response: Any) -> SimpleNamespace:
    messages = FakeMessages(response)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))


def message(text: str = '{"actions": []}', stop_reason: str = "end_turn", **extra: Any) -> SimpleNamespace:
    blocks = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=blocks, stop_reason=stop_reason, **extra)


def test_anthropic_request_shape() -> None:
    client = anthropic_client(message())
    model = AnthropicModel(client=client)
    assert model.complete("system prompt", "user prompt") == '{"actions": []}'
    sent = client.messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["system"] == "system prompt"
    assert sent["messages"] == [{"role": "user", "content": "user prompt"}]
    assert sent["output_config"] == {"effort": "high"}
    assert sent["betas"] == ["server-side-fallback-2026-07-01"] and sent["fallbacks"] == "default"
    assert "thinking" not in sent and "budget_tokens" not in str(sent)


def test_anthropic_structured_and_plain_options() -> None:
    model = AnthropicModel("claude-sonnet-5-5", structured=True, fallbacks=None, effort=None)
    request = model.request("s", "p")
    assert request["output_config"] == {"format": {"type": "json_schema", "schema": CONTRACT_SCHEMA}}
    assert "betas" not in request and "fallbacks" not in request
    assert repr(model) == "AnthropicModel('claude-sonnet-5-5')"


@pytest.mark.parametrize(
    ("response", "error", "match"),
    [
        (message(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")), ModelRefusalError, "cyber"),
        (message(stop_reason="max_tokens"), ModelError, "truncated"),
        (message(text=""), ModelError, "no text"),
        (RuntimeError("boom"), ModelError, "boom"),
    ],
)
def test_anthropic_errors(response: Any, error: type[Exception], match: str) -> None:
    model = AnthropicModel(client=anthropic_client(response), fallbacks=None)
    with pytest.raises(error, match=match):
        model.complete("s", "p")


def openai_client(content: str | None, finish_reason: str = "stop") -> SimpleNamespace:
    choice = SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish_reason)
    completions = FakeMessages(SimpleNamespace(choices=[choice]))
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def test_openai_adapter() -> None:
    client = openai_client('{"actions": []}')
    model = OpenAIModel("m", client=client, temperature=0)
    assert model.complete("s", "p") == '{"actions": []}'
    sent = client.chat.completions.kwargs
    assert sent["messages"][0] == {"role": "system", "content": "s"}
    assert sent["response_format"] == {"type": "json_object"} and sent["temperature"] == 0
    assert "response_format" not in (OpenAIModel("m", client=client, json_mode=False).request("s", "p"))
    assert repr(model) == "OpenAIModel('m')"


@pytest.mark.parametrize(("content", "finish"), [(None, "stop"), ("x", "length")])
def test_openai_errors(content: str | None, finish: str) -> None:
    with pytest.raises(ModelError):
        OpenAIModel("m", client=openai_client(content, finish)).complete("s", "p")


def test_anthropic_platform_clients_skip_server_side_fallbacks() -> None:
    class AnthropicFoundry(SimpleNamespace):
        pass

    messages = FakeMessages(message())
    model = AnthropicModel(client=AnthropicFoundry(messages=messages, beta=SimpleNamespace(messages=messages)))
    assert "betas" not in model.request("s", "p") and "fallbacks" not in model.request("s", "p")
    assert model.complete("s", "p") == '{"actions": []}'


@pytest.mark.parametrize(
    ("message_fields", "finish", "error", "match"),
    [
        ({"content": None, "refusal": "I can't help with that."}, "stop", ModelRefusalError, "can't help"),
        ({"content": None}, "content_filter", ModelRefusalError, "declined"),
    ],
)
def test_openai_refusals(message_fields: dict[str, Any], finish: str, error: type[Exception], match: str) -> None:
    choice = SimpleNamespace(message=SimpleNamespace(**message_fields), finish_reason=finish)
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeMessages(SimpleNamespace(choices=[choice]))))
    with pytest.raises(error, match=match):
        OpenAIModel("m", client=client).complete("s", "p")


def test_openai_empty_choices_and_explicit_response_format() -> None:
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeMessages(SimpleNamespace(choices=[]))))
    with pytest.raises(ModelError, match="no choices"):
        OpenAIModel("m", client=client).complete("s", "p")
    schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {}}}
    assert OpenAIModel("m", response_format=schema).request("s", "p")["response_format"] == schema


def test_platform_detection_follows_subclasses() -> None:
    class AnthropicBedrock(SimpleNamespace):
        pass

    class TracedClient(AnthropicBedrock):
        pass

    assert "fallbacks" not in AnthropicModel(client=TracedClient()).request("s", "p")


def test_mocked_openai_clients_are_not_refusals() -> None:
    from unittest.mock import MagicMock

    client = MagicMock()
    client.chat.completions.create.return_value.choices = [MagicMock(finish_reason="stop")]
    client.chat.completions.create.return_value.choices[0].message.content = '{"actions": []}'
    assert OpenAIModel("m", client=client).complete("s", "p") == '{"actions": []}'
