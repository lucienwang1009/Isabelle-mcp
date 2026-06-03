"""Integration tests for Layer C automation tools against real I/R.

Drives the MCP tool layer (call_tool) with the Bash.Server enabled so
sledgehammer's ATPs are available.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.server import build_server

_PORT = 9152


async def _call(mcp: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = await mcp.call_tool(name, arguments)
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, dict):
            return structured
        result = content
    return json.loads(result[0].text)  # type: ignore[index]


@pytest.fixture(scope="module")
def mcp_server(isabelle_bin: str, ir_dir: Path, hol_built: None) -> Iterator[Any]:
    manager = IRManager(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        port=_PORT,
        bash_server=True,
        startup_timeout_seconds=180.0,
    )
    manager.start()
    try:
        yield build_server(manager)
    finally:
        manager.close()


async def _open_goal(mcp: Any, goal: str) -> str:
    repl_id = (await _call(mcp, "isabelle_open_repl", theory="Main"))["repl_id"]
    res = await _call(mcp, "isabelle_step", repl_id=repl_id, isar=goal)
    assert res["ok"], res
    return repl_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_theorems(mcp_server: Any) -> None:
    repl_id = (await _call(mcp_server, "isabelle_open_repl", theory="Main"))["repl_id"]
    res = await _call(mcp_server, "isabelle_find_theorems", repl_id=repl_id, query="name: conjI", max_results=3)
    assert res["ok"], res
    assert res["count"] >= 1
    assert any("conjI" in t for t in res["theorems"])
    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_try0_finds_tactic(mcp_server: Any) -> None:
    repl_id = await _open_goal(mcp_server, 'theorem t: "rev (rev xs) = xs"')
    res = await _call(mcp_server, "isabelle_try0", repl_id=repl_id)
    assert res["ok"], res
    assert res["found"] is True
    assert res["tactic"] and res["tactic"].startswith("by ")
    # The diagnostic must not have changed the proof: still one open goal.
    state = await _call(mcp_server, "isabelle_state", repl_id=repl_id)
    assert state["history"] == ['theorem t: "rev (rev xs) = xs"']
    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_quickcheck_finds_counterexample(mcp_server: Any) -> None:
    repl_id = await _open_goal(mcp_server, 'theorem q: "rev xs = xs"')
    res = await _call(mcp_server, "isabelle_quickcheck", repl_id=repl_id)
    assert res["ok"], res
    assert res["found_counterexample"] is True
    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nitpick_finds_counterexample(mcp_server: Any) -> None:
    repl_id = await _open_goal(mcp_server, 'theorem n: "x + y = y + (x::nat) + 1"')
    res = await _call(mcp_server, "isabelle_nitpick", repl_id=repl_id, timeout_s=60)
    assert res["ok"], res
    assert res["result"] == "counterexample"
    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)


@pytest.mark.integration
@pytest.mark.heavy
@pytest.mark.asyncio
async def test_sledgehammer_returns_one_liner(mcp_server: Any) -> None:
    repl_id = await _open_goal(mcp_server, 'theorem s: "rev (rev xs) = xs"')
    res = await _call(mcp_server, "isabelle_sledgehammer", repl_id=repl_id, timeout_s=60)
    assert res["ok"], res
    assert res["found"] is True
    assert res["one_liner"] and res["one_liner"].startswith("by ")
    # Apply the discovered one-liner to actually close the goal.
    applied = await _call(mcp_server, "isabelle_step", repl_id=repl_id, isar=res["one_liner"])
    assert applied["ok"] and applied["at_end_of_proof"] is True
    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)
