"""The model protocol and provider-independent adapters."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..errors import ModelError


@runtime_checkable
class Model(Protocol):
    """Anything that turns a system prompt and a user prompt into text.

    A model in Corollary is a stateless proposer: it receives one context assembled by the
    projector and returns one response in the claim contract. It never sees prior turns, so an
    adapter only needs a single-shot completion call.
    """

    @property
    def name(self) -> str:
        """Identifier recorded as the source of every belief this model proposes."""
        ...

    def complete(self, system: str, prompt: str) -> str: ...


@dataclass
class Call:
    """One recorded call to a model."""

    system: str
    prompt: str
    response: str


Response = str | dict[str, Any] | list[Any] | Callable[[str], Any]


class ScriptedModel:
    """Replays prepared responses in order. For tests, demos and offline examples.

    Each response may be a string, a JSON-able ``dict``/``list`` (serialized for you), or a
    callable receiving the prompt and returning either. Every call is recorded in ``calls``.

    >>> model = ScriptedModel([{"actions": [{"type": "answer", "text": "hi", "follows_from": []}]}])
    >>> model.complete("system", "prompt")
    '{"actions": [{"type": "answer", "text": "hi", "follows_from": []}]}'
    """

    def __init__(self, responses: Iterable[Response] = (), *, name: str = "scripted") -> None:
        self.responses: list[Response] = list(responses)
        self.name = name
        self.calls: list[Call] = []

    def add(self, *responses: Response) -> ScriptedModel:
        self.responses.extend(responses)
        return self

    @property
    def remaining(self) -> int:
        return len(self.responses)

    def complete(self, system: str, prompt: str) -> str:
        if not self.responses:
            raise ModelError("ScriptedModel has no responses left")
        item = self.responses.pop(0)
        if callable(item):
            item = item(prompt)
        text = item if isinstance(item, str) else json.dumps(item)
        self.calls.append(Call(system, prompt, text))
        return text


@dataclass
class CallableModel:
    """Wrap any ``(system, prompt) -> str`` function as a model, e.g. a LiteLLM or local-model call."""

    fn: Callable[[str, str], str]
    name: str = "callable"

    def complete(self, system: str, prompt: str) -> str:
        result = self.fn(system, prompt)
        if not isinstance(result, str):
            raise ModelError(f"model function returned {type(result).__name__}, expected str")
        return result


def resolve_model(spec: Model | str) -> Model:
    """Accept a :class:`Model`, or a string such as ``"anthropic:claude-opus-5-5"`` or
    ``"openai:<model>"``. Bare ``claude-*`` ids select the Anthropic adapter."""
    if not isinstance(spec, str):
        if not isinstance(spec, Model):
            raise TypeError("model must implement complete(system, prompt) -> str and have a name")
        return spec
    provider, sep, model_id = spec.partition(":")
    if not sep:
        provider, model_id = ("anthropic", spec) if spec.startswith("claude") else ("", spec)
    if provider == "anthropic":
        from .anthropic import AnthropicModel

        return AnthropicModel(model=model_id or AnthropicModel.DEFAULT_MODEL)
    if provider == "openai":
        from .openai import OpenAIModel

        if not model_id:
            raise ValueError("specify an OpenAI model, e.g. 'openai:<model-id>'")
        return OpenAIModel(model=model_id)
    raise ValueError(f"cannot resolve model {spec!r}; pass a Model instance or use 'anthropic:<id>' / 'openai:<id>'")
