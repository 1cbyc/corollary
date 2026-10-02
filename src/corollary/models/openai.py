"""OpenAI-compatible adapter (``pip install "corollary[openai]"``).

Also works with any server exposing the Chat Completions API (vLLM, Ollama, LM Studio, ...)
through ``client=openai.OpenAI(base_url=...)``.
"""

from __future__ import annotations

from typing import Any

from ..errors import ModelError, ModelRefusalError


class OpenAIModel:
    """Calls a Chat Completions endpoint.

    Args:
        model: Model id served by the endpoint.
        json_mode: Request ``response_format={"type": "json_object"}``. Disable for servers that
            don't support it; the runtime parses and validates the response either way.
        client: A pre-configured ``openai.OpenAI`` client. Created from the environment when omitted.
        **options: Extra keyword arguments forwarded to ``chat.completions.create``.
    """

    def __init__(self, model: str, *, json_mode: bool = True, client: Any = None, **options: Any) -> None:
        self.model = model
        self.json_mode = json_mode
        self.options = options
        self._client = client

    @property
    def name(self) -> str:
        return self.model

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ModelError('the OpenAI adapter needs the SDK: pip install "corollary[openai]"') from exc
            self._client = openai.OpenAI()
        return self._client

    def request(self, system: str, prompt: str) -> dict[str, Any]:
        """The keyword arguments sent to ``chat.completions.create`` (exposed for inspection and tests)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            **self.options,
        }
        if self.json_mode and "response_format" not in self.options:  # an explicit format wins
            kwargs["response_format"] = {"type": "json_object"}
        return kwargs

    def complete(self, system: str, prompt: str) -> str:
        kwargs = self.request(system, prompt)
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ModelError(f"chat completion failed: {exc}") from exc
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ModelError("the completion contained no choices")
        choice = choices[0]
        finish = getattr(choice, "finish_reason", None)
        refusal = getattr(choice.message, "refusal", None)
        if refusal or finish == "content_filter":
            raise ModelRefusalError(f"{self.model} declined the request" + (f": {refusal}" if refusal else ""))
        if finish == "length":
            raise ModelError("response truncated by the token limit")
        text = choice.message.content
        if not text:
            raise ModelError("the model returned no text content")
        return str(text)

    def __repr__(self) -> str:
        return f"OpenAIModel({self.model!r})"
