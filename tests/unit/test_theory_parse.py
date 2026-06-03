"""Unit tests for the .thy outline parser and goal-state parser (no Isabelle)."""

from __future__ import annotations

from pathlib import Path

from isabelle_mcp.parsing import parse_goal_state
from isabelle_mcp.theory_parse import parse_theory_outline

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "example.thy"


def test_outline_header_name_and_imports() -> None:
    outline = parse_theory_outline(_FIXTURE.read_text(encoding="utf-8"))
    assert outline["name"] == "Example"
    assert outline["imports"] == ["Main", "HOL-Library.Multiset"]


def test_outline_entries_kinds_and_names() -> None:
    outline = parse_theory_outline(_FIXTURE.read_text(encoding="utf-8"))
    by_name = {(e["kind"], e["name"]) for e in outline["entries"]}
    assert ("definition", "square") in by_name
    assert ("lemma", "square_nonneg") in by_name
    assert ("theorem", "add_commute") in by_name
    assert ("datatype", "tree") in by_name
    assert ("fun", "mirror") in by_name
    # The anonymous lemma is captured with an empty name.
    assert ("lemma", "") in by_name


def test_outline_line_numbers_are_one_based() -> None:
    outline = parse_theory_outline(_FIXTURE.read_text(encoding="utf-8"))
    square = next(e for e in outline["entries"] if e["name"] == "square")
    # `definition square` is on line 7 of the fixture.
    assert square["line"] == 7


def test_outline_ignores_keywords_in_comments() -> None:
    outline = parse_theory_outline(_FIXTURE.read_text(encoding="utf-8"))
    assert all(e["name"] != "not_a_real_lemma" for e in outline["entries"])


def test_outline_handles_no_header() -> None:
    outline = parse_theory_outline('lemma foo: "P"\n  by auto\n')
    assert outline["imports"] == []
    assert outline["entries"][0]["name"] == "foo"


def test_parse_goal_state_single() -> None:
    parsed = parse_goal_state("proof (prove)\ngoal (1 subgoal):\n 1. 1 + 1 = 2\n[timing] 0s")
    assert parsed == {"goal_count": 1, "subgoals": ["1 + 1 = 2"]}


def test_parse_goal_state_multiple_and_multiline() -> None:
    body = "goal (2 subgoals):\n 1. A x\n 2. B y\n    && C\n[timing] 0s"
    parsed = parse_goal_state(body)
    assert parsed["goal_count"] == 2
    assert parsed["subgoals"] == ["A x", "B y && C"]


def test_parse_goal_state_no_open_goals() -> None:
    assert parse_goal_state("theorem t: 1 + 1 = 2\n[timing] 0s") == {
        "goal_count": 0,
        "subgoals": [],
    }
