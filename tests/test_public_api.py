from __future__ import annotations

from types import ModuleType

import pytest

import corollary
import corollary.contract as contract
import corollary.formula as formula
import corollary.verify as verify


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        (
            verify,
            {
                "DEFAULT_CHECKS",
                "ArithmeticCheck",
                "Check",
                "CheckResult",
                "CitationCheck",
                "GroundingCheck",
                "NumericProvenanceCheck",
                "Severity",
                "StructureCheck",
                "TemporalCheck",
                "VerificationContext",
                "VerificationReport",
                "Verifier",
            },
        ),
        (formula, {"FUNCTIONS", "evaluate", "formula_keys"}),
        (
            contract,
            {
                "Action",
                "CONTRACT_SCHEMA",
                "SYSTEM_PROMPT",
                "Answer",
                "Cite",
                "Claim",
                "ParsedResponse",
                "ToolCall",
                "extract_json",
                "parse_response",
            },
        ),
    ],
)
def test_submodule_public_api(module: ModuleType, expected: set[str]) -> None:
    assert set(module.__all__) == expected
    assert all(not name.startswith("_") and hasattr(module, name) for name in module.__all__)


def test_action_is_exported_from_package_root() -> None:
    assert corollary.Action is contract.Action
    assert "Action" in corollary.__all__
