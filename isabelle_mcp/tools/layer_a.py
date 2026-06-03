"""Layer A — file/utility tools composed over Layer B.

M3 surfaces three tools: ``isabelle_file_outline`` (pure ``.thy`` parse, no
daemon), ``isabelle_run_code`` (one-shot Isar in a transient REPL), and
``isabelle_multi_attempt`` (try several tactics on an open-proof REPL). Position-
anchored ``goal_at``/``diagnostics``/``hover`` are deferred — see
``docs/superpowers/plans/2026-06-03-m3-file-anchored.md``.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.sandbox import read_theory_file
from isabelle_mcp.theory_parse import parse_theory_outline
from isabelle_mcp.tools import run_tool

logger = logging.getLogger(__name__)

__all__ = ["register_layer_a"]


def register_layer_a(mcp: FastMCP, manager: IRManager) -> None:
    """Register the Layer A tools on ``mcp``, backed by ``manager``."""

    @mcp.tool(
        name="isabelle_file_outline",
        description=(
            "Parse a .thy file and return its imports and top-level declarations "
            "(theorems, lemmas, definitions, datatypes, …) with line numbers. "
            "Use to navigate a theory before editing. Returns {imports, entries}. "
            "Example: isabelle_file_outline(path='src/Foo.thy')."
        ),
    )
    async def isabelle_file_outline(path: str) -> dict[str, Any]:
        def _outline() -> dict[str, Any]:
            return parse_theory_outline(read_theory_file(path))

        return await run_tool(_outline)

    @mcp.tool(
        name="isabelle_run_code",
        description=(
            "Run a single Isar/HOL command in a throwaway REPL on Main and "
            "return its output (and whether it closed a proof). Use for quick "
            "checks; for an ongoing proof use isabelle_open_repl + isabelle_step. "
            "Example: isabelle_run_code(code='lemma \"1+1=(2::nat)\" by simp')."
        ),
    )
    async def isabelle_run_code(code: str, timeout_s: int = 30) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.run_code(code, timeout_seconds=float(timeout_s))
        )

    @mcp.tool(
        name="isabelle_multi_attempt",
        description=(
            "Try several tactics on the current goal of an open-proof REPL, each "
            "on an isolated fork, and report which close or advance it (the REPL "
            "itself is left unchanged). Use to compare candidates cheaply. "
            "Returns {attempts: [{tactic, ok, closes_goal, remaining_goals}]}. "
            "Example: isabelle_multi_attempt(repl_id, tactics=['by simp','by auto'])."
        ),
    )
    async def isabelle_multi_attempt(
        repl_id: str, tactics: list[str], timeout_s: int = 15
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.multi_attempt(
                repl_id, tactics, timeout_seconds=float(timeout_s)
            )
        )
