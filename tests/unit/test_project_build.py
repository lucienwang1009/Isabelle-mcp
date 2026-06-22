"""Unit tests for Isabelle project build diagnostics."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.project_build import (
    check_isabelle_project,
    discover_project_root,
    parse_build_diagnostics,
)


def test_discover_project_root_finds_nearest_root(tmp_path: Path) -> None:
    root = tmp_path / "proof" / "Foo"
    nested = root / "A" / "B"
    nested.mkdir(parents=True)
    (root / "ROOT").write_text("session Foo = HOL + theories T\n", encoding="utf-8")
    thy = nested / "T.thy"
    thy.write_text("theory T imports Main begin end\n", encoding="utf-8")

    assert discover_project_root(thy) == root


def test_parse_build_diagnostics_extracts_failed_command() -> None:
    output = """
Running Foo ...
*** Failed to finish proof (line 42 of "~/repo/Foo.thy"):
*** goal (1 subgoal):
***  1. P
*** At command "by" (line 42 of "~/repo/Foo.thy")
""".strip()

    parsed = parse_build_diagnostics(output)

    assert parsed["warnings"] == []
    assert parsed["errors"] == [
        {
            "message": "Failed to finish proof",
            "line": 42,
            "file": str(Path("~/repo/Foo.thy").expanduser()),
            "command": "by",
        }
    ]


def test_check_isabelle_project_builds_root_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Project"
    dep = tmp_path / "Dep"
    root.mkdir()
    dep.mkdir()
    (root / "ROOT").write_text("session Project = HOL + theories T\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 12.0
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = check_isabelle_project(
        isabelle_bin="/bin/isabelle",
        root=root,
        session_dirs=[dep],
        timeout_seconds=12,
        jobs=2,
        verbose=True,
    )

    assert result["checked"] is True
    assert calls == [
        ["/bin/isabelle", "build", "-v", "-j", "2", "-d", str(dep), "-D", str(root)]
    ]


def test_check_isabelle_project_named_session_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "Project"
    root.mkdir()
    command_seen: list[str] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        command_seen[:] = command
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr='*** Failed to finish proof (line 7 of "~/P.thy"):\n'
            '*** At command "qed" (line 7 of "~/P.thy")\n',
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = check_isabelle_project(
        isabelle_bin="/bin/isabelle",
        root=root,
        session="Project",
    )

    assert result["checked"] is False
    assert command_seen == ["/bin/isabelle", "build", "-d", str(root), "Project"]
    assert result["errors"][0]["command"] == "qed"
