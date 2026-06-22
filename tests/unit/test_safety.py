"""Unit tests for user Isar command safety checks."""

from __future__ import annotations

import pytest

from isabelle_mcp.errors import ToolError
from isabelle_mcp.safety import first_isar_command, validate_isar_safe


def test_first_command_skips_whitespace_and_nested_comments() -> None:
    text = "  (* outer (* inner *) end *)\nlemma foo: \"True\""
    assert first_isar_command(text) == "lemma"


def test_validate_blocks_raw_ml_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ISABELLE_MCP_ALLOW_ML", raising=False)

    with pytest.raises(ToolError) as exc:
        validate_isar_safe('ML "writeln \\"hi\\""')

    assert exc.value.code == "ml_disabled"


@pytest.mark.parametrize("command", ["ML_file", "setup", "method_setup"])
def test_validate_blocks_other_ml_entry_points(
    command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ISABELLE_MCP_ALLOW_ML", raising=False)

    with pytest.raises(ToolError):
        validate_isar_safe(f"{command} something")


def test_validate_allows_normal_isar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ISABELLE_MCP_ALLOW_ML", raising=False)
    validate_isar_safe('lemma ML_named_fact: "True"')


def test_validate_allows_raw_ml_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISABELLE_MCP_ALLOW_ML", "1")
    validate_isar_safe('ML "writeln \\"hi\\""')
