"""Integration tests driving the Layer B MCP tools end-to-end against real I/R.

These prove the acceptance criterion that `1 + 1 = (2::nat)` closes *through the
MCP tool layer* (not just ir_client), and that the server starts over stdio and
advertises its tools.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.server import build_server

# Distinct ports so these daemons never collide with the session-scoped M0
# daemon (9147) or with each other.
_INPROC_PORT = 9150
_STDIO_PORT = 9151

_EXPECTED_TOOLS = {
    "isabelle_open_repl",
    "isabelle_step",
    "isabelle_undo",
    "isabelle_state",
    "isabelle_fork_repl",
    "isabelle_close_repl",
}


async def _call(mcp: Any, name: str, **arguments: Any) -> dict[str, Any]:
    """Invoke a FastMCP tool and parse its JSON envelope."""
    result = await mcp.call_tool(name, arguments)
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, dict):
            return structured
        result = content
    return json.loads(result[0].text)  # type: ignore[index]


@pytest.fixture(scope="module")
def mcp_server(
    isabelle_bin: str, ir_dir: Path, hol_built: None
) -> Iterator[Any]:
    """A built FastMCP server backed by a started IRManager (own port)."""
    manager = IRManager(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        port=_INPROC_PORT,
        startup_timeout_seconds=120.0,
    )
    manager.start()
    try:
        yield build_server(manager)
    finally:
        manager.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prove_one_plus_one_through_mcp(mcp_server: Any) -> None:
    """Open a REPL, prove 1+1=2, and confirm at_end_of_proof — via MCP tools."""
    opened = await _call(mcp_server, "isabelle_open_repl", theory="Main")
    assert opened["ok"], opened
    repl_id = opened["repl_id"]

    stepped = await _call(
        mcp_server,
        "isabelle_step",
        repl_id=repl_id,
        isar='theorem t: "1 + 1 = (2::nat)" by simp',
    )
    assert stepped["ok"], stepped
    assert stepped["at_end_of_proof"] is True

    closed = await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)
    assert closed["ok"], closed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_state_undo_fork_and_errors(mcp_server: Any) -> None:
    """Exercise state, undo, fork, and the repl_not_found error path via MCP."""
    repl_id = (await _call(mcp_server, "isabelle_open_repl", theory="Main"))["repl_id"]

    # Open a goal but do not close it yet.
    s1 = await _call(
        mcp_server, "isabelle_step", repl_id=repl_id, isar='theorem t: "1 + 1 = (2::nat)"'
    )
    assert s1["ok"] and s1["at_end_of_proof"] is False

    state = await _call(mcp_server, "isabelle_state", repl_id=repl_id)
    assert state["ok"]
    assert any("theorem t" in line for line in state["history"])
    assert state["at_end_of_proof"] is False

    # Fork the in-progress proof.
    fork = await _call(mcp_server, "isabelle_fork_repl", repl_id=repl_id)
    assert fork["ok"] and fork["repl_id"] != repl_id

    # Close the goal, then undo the closing step.
    closed_step = await _call(mcp_server, "isabelle_step", repl_id=repl_id, isar="by simp")
    assert closed_step["at_end_of_proof"] is True
    undone = await _call(mcp_server, "isabelle_undo", repl_id=repl_id, n=1)
    assert undone["ok"] and undone["steps_undone"] == 1

    # Unknown repl_id -> structured error envelope.
    err = await _call(mcp_server, "isabelle_step", repl_id="nope", isar="by simp")
    assert err["ok"] is False
    assert err["error"]["code"] == "repl_not_found"

    # A false goal -> tactic_failed.
    bad_id = (await _call(mcp_server, "isabelle_open_repl", theory="Main"))["repl_id"]
    await _call(mcp_server, "isabelle_step", repl_id=bad_id, isar='theorem f: "1 + 1 = (3::nat)"')
    bad = await _call(mcp_server, "isabelle_step", repl_id=bad_id, isar="by simp")
    assert bad["ok"] is False and bad["error"]["code"] == "tactic_failed"

    for rid in (repl_id, fork["repl_id"], bad_id):
        await _call(mcp_server, "isabelle_close_repl", repl_id=rid)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stdio_server_starts_and_lists_tools(
    isabelle_bin: str, ir_dir: Path, hol_built: None
) -> None:
    """`python -m isabelle_mcp.server` starts over stdio and advertises tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = os.environ.copy()
    # isabelle_bin is .../<root>/bin/isabelle; ISABELLE_HOME is <root>.
    env["ISABELLE_HOME"] = str(Path(isabelle_bin).resolve().parents[1])
    env["ISABELLE_MCP_PORT"] = str(_STDIO_PORT)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "isabelle_mcp.server"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = {t.name for t in listed.tools}
    assert _EXPECTED_TOOLS <= names, _EXPECTED_TOOLS - names
