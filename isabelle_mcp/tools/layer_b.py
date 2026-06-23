"""Layer B — REPL / snapshot tools (passthrough to I/R with opaque repl_id).

Registers six MCP tools on a FastMCP instance, each delegating to an
:class:`~isabelle_mcp.lifecycle.IRManager`. Blocking socket I/O runs in a worker
thread so the asyncio event loop is never blocked. Every tool returns an
envelope: success ``{"ok": True, ...}`` or
``{"ok": False, "error": {...}, "hint"?}``.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from mcp.server.fastmcp import FastMCP

from isabelle_mcp.errors import error_envelope
from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.tools import run_tool

logger = logging.getLogger(__name__)

__all__ = ["register_layer_b"]


def register_layer_b(mcp: FastMCP, manager: IRManager) -> None:
    """Register the Layer B REPL tools on ``mcp``, backed by ``manager``."""

    @mcp.tool(
        name="isabelle_open_repl",
        description=(
            "Open a stateful Isabelle REPL and return an opaque `repl_id`. "
            "Provide `theory` (e.g. \"Main\" for plain HOL) to anchor a fresh "
            "REPL, OR `parent_repl_id` to branch from an existing REPL's "
            "current state. To open on a locally built session image, also pass "
            "`session` (its name) and `session_dirs` (the ROOT dir(s)) with a "
            "`theory` from that session — the daemon switches to it (this "
            "invalidates existing repl_ids). Build the session first. "
            "Pass the returned repl_id to every other isabelle_* tool. "
            "Example: isabelle_open_repl(theory=\"Main\")."
        ),
    )
    async def isabelle_open_repl(
        theory: str | None = None,
        parent_repl_id: str | None = None,
        session: str | None = None,
        session_dirs: list[str] | None = None,
    ) -> dict[str, Any]:
        if parent_repl_id is not None:
            at: dict[str, object] = {"parent_repl_id": parent_repl_id}
        elif theory is not None:
            at = {"theory": theory}
            if session is not None:
                at["session"] = session
            if session_dirs is not None:
                at["session_dirs"] = session_dirs
        else:
            return error_envelope(
                "invalid_argument",
                "provide either `theory` or `parent_repl_id`",
                secrets.token_hex(6),
            )
        return await run_tool(lambda: manager.open(at), tool="isabelle_open_repl")

    @mcp.tool(
        name="isabelle_step",
        description=(
            "Run ONE Isar command in the REPL and return the resulting proof "
            "state plus `at_end_of_proof`. Use one command per call, e.g. "
            "isabelle_step(repl_id, isar='theorem t: \"1+1=(2::nat)\"') then "
            "isabelle_step(repl_id, isar='by simp'). On failure see error.code "
            "(parse_error / tactic_failed / timeout)."
        ),
    )
    async def isabelle_step(
        repl_id: str, isar: str, timeout_s: int = 60
    ) -> dict[str, Any]:
        return await run_tool(
            lambda: manager.step(repl_id, isar, timeout_seconds=float(timeout_s)),
            tool="isabelle_step",
        )

    @mcp.tool(
        name="isabelle_undo",
        description=(
            "Undo the last `n` steps in the REPL (default 1), returning the "
            "number undone and the current goal summary. Use to backtrack a "
            "wrong tactic. Example: isabelle_undo(repl_id, n=1)."
        ),
    )
    async def isabelle_undo(repl_id: str, n: int = 1) -> dict[str, Any]:
        return await run_tool(lambda: manager.undo(repl_id, n=n), tool="isabelle_undo")

    @mcp.tool(
        name="isabelle_state",
        description=(
            "Return the REPL's step history, current goals, and "
            "`at_end_of_proof`. Use to inspect where a proof stands without "
            "changing it. Example: isabelle_state(repl_id)."
        ),
    )
    async def isabelle_state(repl_id: str) -> dict[str, Any]:
        return await run_tool(lambda: manager.state(repl_id), tool="isabelle_state")

    @mcp.tool(
        name="isabelle_fork_repl",
        description=(
            "Fork the REPL at its current state into a new independent REPL, "
            "returning a new `repl_id`. Use to try an alternative proof line "
            "without losing the current one. Example: isabelle_fork_repl(repl_id)."
        ),
    )
    async def isabelle_fork_repl(repl_id: str) -> dict[str, Any]:
        return await run_tool(lambda: manager.fork(repl_id), tool="isabelle_fork_repl")

    @mcp.tool(
        name="isabelle_close_repl",
        description=(
            "Close the REPL (and any REPLs forked from it), freeing resources. "
            "Call when you are done with a proof. Example: "
            "isabelle_close_repl(repl_id)."
        ),
    )
    async def isabelle_close_repl(repl_id: str) -> dict[str, Any]:
        return await run_tool(lambda: manager.close_repl(repl_id), tool="isabelle_close_repl")
