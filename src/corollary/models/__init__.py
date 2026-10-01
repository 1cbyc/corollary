"""Model adapters. A model only has to implement ``complete(system, prompt) -> str``."""

from .anthropic import AnthropicModel
from .base import Call, CallableModel, Model, ScriptedModel, resolve_model
from .openai import OpenAIModel

__all__ = ["AnthropicModel", "Call", "CallableModel", "Model", "OpenAIModel", "ScriptedModel", "resolve_model"]
