"""Layer C — automation wrappers (sledgehammer, try0, find_theorems, …).

Registers the automation tools on a FastMCP instance, backed by
:class:`~isabelle_mcp.lifecycle.IRManager`. ``isabelle_thm_deps`` is registered
only when ``ISABELLE_MCP_EXPOSE_ADVANCED=1`` (design spec §4).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.tools import run_tool

logger = logging.getLogger(__name__)

__all__ = ["register_layer_c"]


def register_layer_c(mcp: FastMCP, manager: IRManager) -> None:
    """Register the Layer C automation tools on ``mcp``, backed by ``manager``."""

    @mcp.tool(
        name="isabelle_try0",
        description=(
            "Try Isabelle's standard tactics (simp, auto, blast, …) on the "
            "current goal and report the first that closes it. Cheap; try this "
            "before sledgehammer. Returns {found, tactic}. Example: "
            "isabelle_try0(repl_id)."
        ),
    )
    async def isabelle_try0(repl_id: str, timeout_s: int = 10) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.try0(repl_id, timeout_seconds=float(timeout_s))
        )

    @mcp.tool(
        name="isabelle_sledgehammer",
        description=(
            "Run sledgehammer: external automated provers search for a proof of "
            "the current goal and return one-liner tactics ('Try this: by ...'). "
            "Use a 60-120s budget when try0 fails. Returns {found, one_liner, "
            "suggestions}. Example: isabelle_sledgehammer(repl_id, timeout_s=120)."
        ),
    )
    async def isabelle_sledgehammer(
        repl_id: str, timeout_s: int = 120, minimize: bool = True
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.sledgehammer(repl_id, timeout_seconds=float(timeout_s))
        )

    @mcp.tool(
        name="isabelle_find_theorems",
        description=(
            "Search the loaded theory database for theorems matching a query "
            "(e.g. 'name: conjI', '\"_ + _ = _ + _\"', 'intro'). Use to find "
            "lemmas to cite. Returns {count, theorems}. Example: "
            "isabelle_find_theorems(repl_id, query='name: rev')."
        ),
    )
    async def isabelle_find_theorems(
        repl_id: str, query: str, max_results: int = 20
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.find_theorems(
                repl_id, query=query, max_results=max_results
            )
        )

    @mcp.tool(
        name="isabelle_nitpick",
        description=(
            "Search for a counterexample to the current goal (the goal may be "
            "false!). Returns {result: counterexample|none|unknown}. Run when a "
            "goal resists proof. Example: isabelle_nitpick(repl_id)."
        ),
    )
    async def isabelle_nitpick(repl_id: str, timeout_s: int = 30) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.nitpick(repl_id, timeout_seconds=float(timeout_s))
        )

    @mcp.tool(
        name="isabelle_quickcheck",
        description=(
            "Randomized/exhaustive test for a counterexample to the current "
            "goal — faster than nitpick. Returns {found_counterexample}. "
            "Example: isabelle_quickcheck(repl_id)."
        ),
    )
    async def isabelle_quickcheck(
        repl_id: str, timeout_s: int = 10
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.quickcheck(repl_id, timeout_seconds=float(timeout_s))
        )

    if os.environ.get("ISABELLE_MCP_EXPOSE_ADVANCED") == "1":

        @mcp.tool(
            name="isabelle_thm_deps",
            description=(
                "List the axioms and theorems a named theorem depends on. "
                "Advanced/diagnostic. Returns {dependencies}. Example: "
                "isabelle_thm_deps(name='conjI', repl_id=repl_id)."
            ),
        )
        async def isabelle_thm_deps(name: str, repl_id: str) -> dict[str, Any]:
            return await run_tool(lambda: manager.thm_deps(name, repl_id))
