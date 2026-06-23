"""Layer A — file/utility tools composed over Layer B.

M3 surfaces file utilities plus REPL-composed helpers. Position-anchored
``goal_at``/``diagnostics``/``hover`` are deferred — see
``docs/superpowers/plans/2026-06-03-m3-file-anchored.md``.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from isabelle_mcp.afp_index import afp_status, search_index
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
            return parse_theory_outline(read_theory_file(path, trusted=True))

        return await run_tool(_outline, tool="isabelle_file_outline")

    @mcp.tool(
        name="isabelle_check_file",
        description=(
            "Load/check a .thy file by its theory header and return whether "
            "Isabelle accepted it, plus parsed imports/entries and diagnostics. "
            "By default this uses the configured I/R session. If session or "
            "session_dirs is provided, it checks the containing ROOT project "
            "with `isabelle build` instead. Use after editing a theory file. "
            "Example: isabelle_check_file(path='src/Foo.thy', timeout_s=120)."
        ),
    )
    async def isabelle_check_file(
        path: str,
        timeout_s: int = 120,
        session: str | None = None,
        session_dirs: list[str] | None = None,
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.check_file(
                path,
                timeout_seconds=float(timeout_s),
                session=session,
                session_dirs=session_dirs,
            ),
            tool="isabelle_check_file",
        )

    @mcp.tool(
        name="isabelle_check_project",
        description=(
            "Run `isabelle build` for a ROOT directory or named session and "
            "return structured build diagnostics. Use this for new/local proof "
            "projects, session-aware checking, or when a .thy file is not "
            "visible in the current I/R session. Examples: "
            "isabelle_check_project(root='examples/foo'); "
            "isabelle_check_project(root='examples/foo', session='Foo')."
        ),
    )
    async def isabelle_check_project(
        root: str,
        timeout_s: int = 300,
        session: str | None = None,
        session_dirs: list[str] | None = None,
        jobs: int | None = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.check_project(
                root,
                timeout_seconds=float(timeout_s),
                session=session,
                session_dirs=session_dirs,
                jobs=jobs,
                verbose=verbose,
            ),
            tool="isabelle_check_project",
        )

    @mcp.tool(
        name="isabelle_afp_search",
        description=(
            "Search the local AFP source index for lemmas/declarations. This is "
            "for discovery only: results may not be citable until the matching "
            "AFP session/profile is built and loaded in I/R. Build/download "
            "the index first with `isabelle-mcp afp-bootstrap` or "
            "`isabelle-mcp afp-index --afp-root /path/to/afp/thys`. "
            "Supports text plus filters like name:foo, entry:Cook_Levin, "
            "theory:Satisfiability, kind:lemma. Example: "
            "isabelle_afp_search(query='finite automata', max_results=10)."
        ),
    )
    async def isabelle_afp_search(
        query: str, max_results: int = 20, db_path: str | None = None
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: search_index(query, db_path=db_path, max_results=max_results),
            tool="isabelle_afp_search",
        )

    @mcp.tool(
        name="isabelle_afp_status",
        description=(
            "Report whether the local AFP source cache and SQLite source index "
            "are present. This is read-only and does not download or build AFP. "
            "Use before isabelle_afp_search when unsure whether the index is ready."
        ),
    )
    async def isabelle_afp_status(db_path: str | None = None) -> dict[str, Any]:
        return await run_tool(
            lambda: afp_status(db_path=db_path),
            tool="isabelle_afp_status",
        )

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
            lambda: manager.run_code(code, timeout_seconds=float(timeout_s)),
            tool="isabelle_run_code",
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
            ),
            tool="isabelle_multi_attempt",
        )
