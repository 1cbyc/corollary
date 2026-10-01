"""Claude adapter, built on the official ``anthropic`` SDK (``pip install "corollary[anthropic]"``)."""

from __future__ import annotations

from typing import Any, ClassVar

from ..contract import CONTRACT_SCHEMA
from ..errors import ModelError, ModelRefusalError


class AnthropicModel:
    """Calls Claude through the Messages API.

    Args:
        model: Model id. Defaults to ``claude-opus-5-5``.
        max_tokens: Output cap per call. One step of the contract is small, so the default is ample.
        effort: ``output_config.effort`` (``"low"`` .. ``"max"``). Claude Opus 5.5 defaults to
            ``"medium"``; Corollary sets ``"high"`` because each call carries reasoning that the
            runtime will hold the model to.
        structured: Constrain the output to the contract's JSON schema with structured outputs.
            Off by default; the runtime validates every response either way.
        fallbacks: Server-side refusal fallback mode, sent with the
            ``server-side-fallback-2026-07-01`` beta. ``"default"`` lets the API route a declined
            request to a fallback model. Available on the Claude API; set ``None`` on platforms
            that don't support it (Bedrock, Vertex AI, Foundry).
        client: A pre-configured ``anthropic.Anthropic`` client (or a platform client such as
            ``AnthropicBedrockMantle``). Created from the environment when omitted.
    """

    DEFAULT_MODEL: ClassVar[str] = "claude-opus-5-5"
    FALLBACK_BETA: ClassVar[str] = "server-side-fallback-2026-07-01"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        max_tokens: int = 16_000,
        effort: str | None = "high",
        structured: bool = False,
        fallbacks: str | None = "default",
        client: Any = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.structured = structured
        self.fallbacks = fallbacks
        self._client = client

    @property
    def name(self) -> str:
        return self.model

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on the environment
                raise ModelError('the Anthropic adapter needs the SDK: pip install "corollary[anthropic]"') from exc
            self._client = anthropic.Anthropic()
        return self._client

    def request(self, system: str, prompt: str) -> dict[str, Any]:
        """The keyword arguments sent to ``messages.create`` (exposed for inspection and tests)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        output_config: dict[str, Any] = {}
        if self.effort:
            output_config["effort"] = self.effort
        if self.structured:
            output_config["format"] = {"type": "json_schema", "schema": CONTRACT_SCHEMA}
        if output_config:
            kwargs["output_config"] = output_config
        if self.fallbacks:
            kwargs["betas"] = [self.FALLBACK_BETA]
            kwargs["fallbacks"] = self.fallbacks
        return kwargs

    def complete(self, system: str, prompt: str) -> str:
        kwargs = self.request(system, prompt)
        try:
            if "betas" in kwargs:
                response = self.client.beta.messages.create(**kwargs)
            else:
                response = self.client.messages.create(**kwargs)
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Anthropic API call failed: {exc}") from exc

        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise ModelRefusalError(f"{self.model} declined the request" + (f" ({category})" if category else ""))
        if response.stop_reason == "max_tokens":
            raise ModelError(f"response truncated at max_tokens={self.max_tokens}")
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if not text:
            raise ModelError("the model returned no text content")
        return text

    def __repr__(self) -> str:
        return f"AnthropicModel({self.model!r})"
