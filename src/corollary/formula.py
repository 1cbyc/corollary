"""A small, safe arithmetic evaluator for claim formulas.

Formulas reference beliefs with ``{key}`` placeholders::

    ({revenue:Q3} - {revenue:Q2}) / {revenue:Q2} * 100

Only numeric literals, placeholders, ``+ - * / // % **``, unary minus and a fixed set of
functions are allowed. There is no attribute access, no subscripting and no names other than
placeholders, so evaluating an untrusted formula cannot execute code.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from collections.abc import Callable, Mapping
from typing import Any

from .errors import FormulaError

_PLACEHOLDER = re.compile(r"\{([^{}\s]+)\}")

_BINARY: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
}

_MAX_EXPONENT = 64
_MAX_LENGTH = 2_000


def formula_keys(formula: str) -> list[str]:
    """Belief keys referenced by ``formula``, in order of first appearance."""
    seen: dict[str, None] = {}
    for match in _PLACEHOLDER.finditer(formula):
        seen.setdefault(match.group(1), None)
    return list(seen)


def evaluate(formula: str, values: Mapping[str, Any]) -> float:
    """Evaluate ``formula`` substituting ``values[key]`` for each ``{key}`` placeholder.

    Raises :class:`FormulaError` if the formula is invalid, references a key missing from
    ``values``, uses a non-numeric value, or uses a forbidden construct.
    """
    if len(formula) > _MAX_LENGTH:
        raise FormulaError(f"formula is longer than {_MAX_LENGTH} characters")
    names: dict[str, float] = {}

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise FormulaError(f"formula references {{{key}}}, which is not available")
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FormulaError(f"{{{key}}} has non-numeric value {value!r}")
        name = f"_v{len(names)}"
        names[name] = float(value)
        return name

    expression = _PLACEHOLDER.sub(substitute, formula)
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"invalid formula {formula!r}: {exc.msg}") from None
    try:
        result = _eval(tree.body, names)
    except FormulaError:
        raise
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise FormulaError(f"cannot evaluate {formula!r}: {exc}") from None
    if isinstance(result, complex) or not isinstance(result, (int, float)):
        raise FormulaError(f"formula {formula!r} did not produce a real number")
    return float(result)


def _eval(node: ast.AST, names: Mapping[str, float]) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError(f"only numeric literals are allowed, got {node.value!r}")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        raise FormulaError(f"unknown name {node.id!r}; reference beliefs as {{key}}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        left, right = _eval(node.left, names), _eval(node.right, names)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise FormulaError(f"exponent {right} exceeds the limit of {_MAX_EXPONENT}")
        return _BINARY[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand, names))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
            allowed = ", ".join(sorted(FUNCTIONS))
            raise FormulaError(f"only these functions are allowed, with positional arguments: {allowed}")
        return FUNCTIONS[node.func.id](*(_eval(arg, names) for arg in node.args))
    raise FormulaError(f"unsupported syntax in formula: {type(node).__name__}")
