"""Unit tests for the error taxonomy and envelopes (no Isabelle required)."""

from __future__ import annotations

import pytest

from isabelle_mcp.errors import (
    ERROR_HINTS,
    ToolError,
    error_envelope,
    map_ir_error,
    ok,
)


def test_ok_envelope_sets_flag_and_fields() -> None:
    env = ok(repl_id="abc", output="state")
    assert env == {"ok": True, "repl_id": "abc", "output": "state"}


def test_error_envelope_shape_and_correlation_id() -> None:
    env = error_envelope("timeout", "step timed out", "corr-123")
    assert env["ok"] is False
    assert env["error"] == {
        "code": "timeout",
        "message": "step timed out",
        "correlation_id": "corr-123",
    }
    # timeout has a curated hint, which should be attached automatically.
    assert env["hint"] == ERROR_HINTS["timeout"][0]


def test_error_envelope_explicit_hint_overrides() -> None:
    env = error_envelope("parse_error", "bad syntax", "c1", hint="custom")
    assert env["hint"] == "custom"


def test_error_envelope_omits_hint_when_none_available() -> None:
    env = error_envelope("internal_error", "boom", "c2")
    assert "hint" not in env


def test_error_envelope_can_include_server_event() -> None:
    env = error_envelope(
        "repl_not_found",
        "stale",
        "c3",
        server_event="ir_restarted",
    )
    assert env["server_event"] == "ir_restarted"


def test_tool_error_defaults_hint_from_table() -> None:
    err = ToolError("repl_not_found", "no such repl")
    assert err.code == "repl_not_found"
    assert err.hint == ERROR_HINTS["repl_not_found"][0]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Step timed out after 10s", "timeout"),
        ("Failed to finish proof:\ngoal (1 subgoal):", "tactic_failed"),
        ('No REPL "R"', "repl_not_found"),
        ("Inner syntax error at ...", "parse_error"),
        ("Type unification failed", "parse_error"),
        ("something we have never seen", "internal_error"),
    ],
)
def test_map_ir_error(body: str, expected: str) -> None:
    assert map_ir_error(body) == expected
