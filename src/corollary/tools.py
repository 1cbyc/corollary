"""Tools: functions the runtime executes on the model's behalf, recording results as premises."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import re
import types
import typing
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, overload

from .errors import ContractViolation

_JSON_TYPES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}
_UNSAFE_KEY_CHARS = re.compile(r"[\s@{}]+")


@dataclass
class Tool:
    """A function the agent may ask the runtime to call.

    The model never produces tool results itself: it names a tool and arguments, the runtime
    executes the function, and the return value becomes a *premise* with a ``tool`` source. That
    is what makes it impossible for the model to fabricate a tool result.

    Attributes:
        trust: A level from the trust policy (``"high"``, ``"medium"``, ``"low"``) or a number.
        ttl: How long a result stays valid. Expired results are hidden from the model and can be
            refreshed with :meth:`Agent.reverify`.
        half_life: Make each result's confidence fade, halving every ``half_life``, without
            changing its status. Faded results are refreshed by :meth:`Agent.reverify` too.
        origin: Independence group, e.g. ``"sec_database"`` for every tool reading that database.
            Tools sharing an origin count once when they agree.
    """

    name: str
    fn: Callable[..., Any]
    description: str = ""
    trust: str | float = "high"
    ttl: timedelta | None = None
    half_life: timedelta | None = None
    origin: str | None = None
    signature: inspect.Signature = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.signature = inspect.signature(self.fn)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.fn(*args, **kwargs)

    def bind(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """Validate ``args`` against the signature and return them with defaults applied.

        Arguments annotated ``str``, ``int``, ``float`` or ``bool`` (or optional versions of them)
        are checked, and coerced when the intent is unambiguous: ``"3"`` for an ``int`` becomes
        ``3``, ``"true"`` for a ``bool`` becomes ``True``. Anything else is a contract violation the
        model sees, instead of an exception from inside the tool.
        """
        try:
            bound = self.signature.bind(**dict(args))
        except TypeError as exc:
            raise ContractViolation(f"invalid arguments for tool {self.name!r}: {exc}") from None
        bound.apply_defaults()
        hints = _type_hints(self.fn)
        arguments = dict(bound.arguments)
        for name, value in arguments.items():
            if name in hints and self.signature.parameters[name].kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                try:
                    arguments[name] = _coerce(value, hints[name])
                except (TypeError, ValueError):
                    expected = _type_name(hints[name])
                    raise ContractViolation(
                        f"invalid arguments for tool {self.name!r}: {name!r} must be {expected}, got {value!r}"
                    ) from None
        return arguments

    def invoke(self, args: Mapping[str, Any]) -> Any:
        """Call the function with arguments from :meth:`bind`. An ``async`` tool is run to completion
        (on a worker thread with its own event loop when the caller is already inside one)."""
        result = self.fn(**args)
        return _resolve(result) if inspect.isawaitable(result) else result

    def default_key(self, args: Mapping[str, Any]) -> str:
        """Belief key used when the model doesn't name one, e.g. ``get_revenue:Q2``."""
        if not args:
            return self.name
        parts = ",".join(_UNSAFE_KEY_CHARS.sub("_", str(v)) for v in args.values())
        return f"{self.name}:{parts}"

    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema of the tool's parameters, derived from type annotations."""
        hints = _type_hints(self.fn)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, param in self.signature.parameters.items():
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            properties[name] = _json_schema_for(hints.get(name, Any))
            if param.default is param.empty:
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}

    def describe(self) -> str:
        """One-line signature and description, as shown to the model."""
        hints = _type_hints(self.fn)
        params = []
        for name, param in self.signature.parameters.items():
            annotation = hints.get(name)
            text = f"{name}: {_type_name(annotation)}" if annotation is not None else name
            if param.default is not param.empty:
                text += f" = {param.default!r}"
            params.append(text)
        returns = hints.get("return")
        signature = f"{self.name}({', '.join(params)})" + (f" -> {_type_name(returns)}" if returns is not None else "")
        return f"{signature}: {self.description}" if self.description else signature


@overload
def tool(fn: Callable[..., Any], /) -> Tool: ...


@overload
def tool(
    *,
    name: str | None = None,
    trust: str | float = "high",
    ttl: timedelta | None = None,
    half_life: timedelta | None = None,
    origin: str | None = None,
    description: str | None = None,
) -> Callable[[Callable[..., Any]], Tool]: ...


def tool(
    fn: Callable[..., Any] | None = None,
    /,
    *,
    name: str | None = None,
    trust: str | float = "high",
    ttl: timedelta | None = None,
    half_life: timedelta | None = None,
    origin: str | None = None,
    description: str | None = None,
) -> Tool | Callable[[Callable[..., Any]], Tool]:
    """Declare a tool. Works bare (``@tool``) or with options (``@tool(trust="high", ttl=...)``).

    The docstring's first paragraph becomes the description shown to the model.
    """

    def wrap(func: Callable[..., Any]) -> Tool:
        doc = description if description is not None else inspect.cleandoc(func.__doc__ or "").split("\n\n")[0]
        return Tool(
            name=name or func.__name__,
            fn=func,
            description=doc.replace("\n", " "),
            trust=trust,
            ttl=ttl,
            half_life=half_life,
            origin=origin,
        )

    return wrap(fn) if fn is not None else wrap


_TRUE = {"true", "yes", "1"}
_FALSE = {"false", "no", "0"}


def _coerce(value: Any, annotation: Any) -> Any:
    """Check ``value`` against a simple annotation, converting unambiguous strings and numbers.
    Raises ``TypeError`` or ``ValueError`` when it doesn't fit; annotations it doesn't know pass."""
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        options = typing.get_args(annotation)
        if value is None and type(None) in options:
            return None
        simple = [a for a in options if a is not type(None)]
        return _coerce(value, simple[0]) if len(simple) == 1 else value
    if annotation is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        raise TypeError
    if annotation is int:
        if isinstance(value, bool):
            raise TypeError
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        raise TypeError
    if annotation is float:
        if isinstance(value, bool):
            raise TypeError
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        raise TypeError
    if annotation is str:
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        raise TypeError
    return value


def _resolve(awaitable: Any) -> Any:
    async def wait() -> Any:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(wait())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, wait()).result()


def _type_hints(fn: Callable[..., Any]) -> dict[str, Any]:
    try:
        return typing.get_type_hints(fn)
    except Exception:
        return {}


def _type_name(annotation: Any) -> str:
    # On Python 3.10, isinstance(list[str], type) is True, so rule out generic aliases first.
    if typing.get_origin(annotation) is None and isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _json_schema_for(annotation: Any) -> dict[str, Any]:
    if annotation in _JSON_TYPES:
        return {"type": _JSON_TYPES[annotation]}
    origin = typing.get_origin(annotation)
    if origin in (list, tuple, set, frozenset):
        args = typing.get_args(annotation)
        return {"type": "array", "items": _json_schema_for(args[0])} if args else {"type": "array"}
    if origin is dict:
        return {"type": "object"}
    if origin is typing.Literal:
        return {"enum": list(typing.get_args(annotation))}
    if origin in (typing.Union, types.UnionType):
        options = [_json_schema_for(a) for a in typing.get_args(annotation) if a is not type(None)]
        return options[0] if len(options) == 1 else {"anyOf": options}
    return {}
