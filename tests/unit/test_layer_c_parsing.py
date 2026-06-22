"""Unit tests for Layer C output parsers (no Isabelle required).

Bodies below are trimmed from real Isabelle2025-2 output captured during the
M2 spike (see docs/ir-protocol-notes.md).
"""

from __future__ import annotations

from isabelle_mcp.parsing import (
    parse_find_theorems,
    parse_nitpick,
    parse_quickcheck,
    parse_sledgehammer,
    parse_theory_diagnostics,
    parse_thm_deps,
    parse_try0,
    strip_trailing_state,
)

_STATE = "proof (prove)\ngoal (1 subgoal):\n 1. P\n[timing] 0.0s"


def test_strip_trailing_state_removes_echo_and_timing() -> None:
    body = f"line one\nline two\n{_STATE}"
    assert strip_trailing_state(body) == "line one\nline two"


def test_parse_try0_found() -> None:
    body = (
        'Trying "simp", "auto"...\n'
        "Found proof: by simp (0 ms)\n"
        "Try this: by simp\n"
        "(simp: 0 ms)\n" + _STATE
    )
    parsed = parse_try0(body)
    assert parsed["found"] is True
    assert parsed["tactic"] == "by simp"


def test_parse_try0_not_found() -> None:
    body = "No proof found.\n" + _STATE
    parsed = parse_try0(body)
    assert parsed["found"] is False
    assert parsed["tactic"] is None


def test_parse_sledgehammer_dedups_and_strips_ms() -> None:
    body = (
        "simp: Try this: by simp (0.3 ms)\n"
        "auto: Try this: by auto (0.1 ms)\n"
        "metis: Try this: by simp (1 ms)\n"
        "[timing] 2.0s"
    )
    parsed = parse_sledgehammer(body)
    assert parsed["found"] is True
    assert parsed["one_liner"] == "by simp"
    assert parsed["suggestions"] == ["by simp", "by auto"]


def test_parse_sledgehammer_none() -> None:
    parsed = parse_sledgehammer("Sledgehammering...\nNo proof found.\n[timing] 30s")
    assert parsed["found"] is False
    assert parsed["one_liner"] is None


def test_parse_sledgehammer_keeps_compound_tactic() -> None:
    body = (
        "cvc4: Try this: by (metis append_assoc rev_rev_ident) (17 ms)\n"
        "[timing] 1.0s"
    )
    parsed = parse_sledgehammer(body)
    assert parsed["one_liner"] == "by (metis append_assoc rev_rev_ident)"


def test_parse_nitpick_counterexample() -> None:
    body = "Nitpick found a counterexample:\n  x = 2\n" + _STATE
    assert parse_nitpick(body)["result"] == "counterexample"


def test_parse_nitpick_none() -> None:
    body = "Nitpick found no counterexample.\n" + _STATE
    assert parse_nitpick(body)["result"] == "none"


def test_parse_nitpick_unknown() -> None:
    body = "Nitpick ran out of time.\n" + _STATE
    assert parse_nitpick(body)["result"] == "unknown"


def test_parse_quickcheck() -> None:
    found = "Quickcheck found a counterexample:\n xs = [a]\n" + _STATE
    none = "Quickcheck found no counterexample.\n" + _STATE
    assert parse_quickcheck(found)["found_counterexample"] is True
    assert parse_quickcheck(none)["found_counterexample"] is False


def test_parse_find_theorems() -> None:
    body = (
        "displaying 2 theorem(s):\n"
        "HOL.conjI: ⟦?P; ?Q⟧ ⟹ ?P ∧ ?Q\n"
        "Foo.bar: ?x = ?x\n"
        "[timing] 0.0s"
    )
    parsed = parse_find_theorems(body)
    assert parsed["count"] == 2
    assert parsed["theorems"] == ["HOL.conjI: ⟦?P; ?Q⟧ ⟹ ?P ∧ ?Q", "Foo.bar: ?x = ?x"]


def test_parse_find_theorems_empty() -> None:
    parsed = parse_find_theorems("displaying 0 theorem(s):\n[timing] 0.0s")
    assert parsed["count"] == 0
    assert parsed["theorems"] == []


def test_parse_thm_deps() -> None:
    body = "dependencies: 3\nallI\nmp\nimpI\n" + _STATE
    assert parse_thm_deps(body)["dependencies"] == ["allI", "mp", "impI"]


def test_parse_theory_diagnostics_error_with_line() -> None:
    parsed = parse_theory_diagnostics("Outer syntax error at line 12: bad command")
    assert parsed["errors"] == [
        {"message": "Outer syntax error at line 12: bad command", "line": 12}
    ]
    assert parsed["warnings"] == []


def test_parse_theory_diagnostics_warning() -> None:
    parsed = parse_theory_diagnostics("Warning: legacy feature")
    assert parsed["errors"] == []
    assert parsed["warnings"] == [{"message": "Warning: legacy feature"}]
