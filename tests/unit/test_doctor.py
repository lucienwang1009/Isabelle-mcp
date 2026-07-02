"""Unit tests for the preflight doctor output."""

from __future__ import annotations

from pathlib import Path

from isabelle_mcp import doctor
from isabelle_mcp.doctor import Check, check_ir_submodule, render_checks


class _OpenSocket:
    def __enter__(self) -> "_OpenSocket":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def test_check_ir_submodule_reports_missing_files(tmp_path: Path) -> None:
    check = check_ir_submodule(tmp_path / "missing-ir")
    assert check.status == "fail"
    assert "git submodule update" in (check.fix or "")


def test_check_ir_port_allows_busy_default(monkeypatch) -> None:
    monkeypatch.delenv("ISABELLE_MCP_PORT", raising=False)
    monkeypatch.setattr(doctor.socket, "create_connection", lambda *_args, **_kwargs: _OpenSocket())

    check = doctor._check_ir_port()

    assert check.status == "ok"
    assert "fall back" in check.message


def test_check_ir_port_fails_when_explicit_port_busy(monkeypatch) -> None:
    monkeypatch.setenv("ISABELLE_MCP_PORT", "9999")
    monkeypatch.setattr(doctor.socket, "create_connection", lambda *_args, **_kwargs: _OpenSocket())

    check = doctor._check_ir_port()

    assert check.status == "fail"
    assert "9999" in check.message


def test_render_checks_includes_summary() -> None:
    text = render_checks(
        [
            Check("one", "ok", "good"),
            Check("two", "warn", "careful"),
            Check("three", "fail", "broken", "fix it"),
        ]
    )
    assert "[OK  ] one: good" in text
    assert "[WARN] two: careful" in text
    assert "[FAIL] three: broken" in text
    assert "summary: 1 failed, 1 warnings" in text


def test_main_returns_nonzero_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(doctor, "run_checks", lambda: [Check("x", "fail", "bad")])
    assert doctor.main([]) == 1
    assert "x: bad" in capsys.readouterr().out
