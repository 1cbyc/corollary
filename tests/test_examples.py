"""The offline examples are part of the documentation, so they must keep working."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_self_repairing_report(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(EXAMPLES / "self_repairing_report.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "Built a report with 20 conclusions from 11 premises." in out
    assert "Outlook is now: negative." in out
    assert "KEPT risk:fx" in out
    assert "Model calls: 0." in out
    assert "Verification PASSED" in out


def test_agent_offline(capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(EXAMPLES / "agent_offline.py"), run_name="__main__")
    out = capsys.readouterr().out
    assert "ANSWER: Q3 revenue grew 4.65% over Q2" in out
    assert "the result of a tool called in this same response" in out
    assert "REPAIRED ANSWER: Q3 revenue grew 9.76% over Q2, which is strong growth." in out
    assert "Verified: True" in out
