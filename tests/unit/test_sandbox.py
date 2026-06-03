"""Unit tests for the path sandbox and timeout clamping (no Isabelle)."""

from __future__ import annotations

from pathlib import Path

import pytest

from isabelle_mcp.errors import ToolError, clamp_timeout
from isabelle_mcp.sandbox import read_theory_file, resolve_in_sandbox


def test_clamp_timeout_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ISABELLE_MCP_MAX_TIMEOUT_S", raising=False)
    assert clamp_timeout(5) == 5.0
    assert clamp_timeout(10_000) == 600.0
    assert clamp_timeout(0) == 1.0


def test_clamp_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISABELLE_MCP_MAX_TIMEOUT_S", "30")
    assert clamp_timeout(120) == 30.0


def test_sandbox_rejects_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ISABELLE_MCP_ALLOWED_DIRS", raising=False)
    with pytest.raises(ToolError) as exc:
        resolve_in_sandbox("/etc/hosts")
    assert exc.value.code == "file_not_found"


def test_sandbox_allows_cwd_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    thy = tmp_path / "Foo.thy"
    thy.write_text("theory Foo imports Main begin\nlemma a: \"True\" by simp\nend\n")
    text = read_theory_file("Foo.thy")
    assert "lemma a" in text


def test_sandbox_allowed_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    extra = tmp_path / "ext"
    extra.mkdir()
    thy = extra / "Bar.thy"
    thy.write_text("theory Bar imports Main begin\nend\n")
    monkeypatch.chdir(tmp_path / "ext" if False else tmp_path)  # cwd is tmp_path
    monkeypatch.setenv("ISABELLE_MCP_ALLOWED_DIRS", str(extra))
    assert "theory Bar" in read_theory_file(str(thy))


def test_sandbox_non_thy_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.txt").write_text("hi")
    with pytest.raises(ToolError) as exc:
        read_theory_file("notes.txt")
    assert exc.value.code == "invalid_argument"


def test_sandbox_missing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolError) as exc:
        read_theory_file("Nope.thy")
    assert exc.value.code == "file_not_found"
