"""Integration tests for Layer A tools (run_code, multi_attempt) and the pure
file_outline tool, driven through the MCP tool layer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from isabelle_mcp.lifecycle import IRManager
from isabelle_mcp.server import build_server

_PORT = 9153
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "example.thy"


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
        bash_server=False,  # Layer A tools don't need ATPs
        startup_timeout_seconds=120.0,
    )
    manager.start()
    try:
        yield build_server(manager)
    finally:
        manager.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_file_outline(mcp_server: Any) -> None:
    res = await _call(mcp_server, "isabelle_file_outline", path=str(_FIXTURE))
    assert res["ok"], res
    assert res["imports"] == ["Main", "HOL-Library.Multiset"]
    names = {(e["kind"], e["name"]) for e in res["entries"]}
    assert ("theorem", "add_commute") in names
    assert ("datatype", "tree") in names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_file_outline_missing_file(mcp_server: Any) -> None:
    res = await _call(mcp_server, "isabelle_file_outline", path="/no/such/File.thy")
    assert res["ok"] is False
    assert res["error"]["code"] == "file_not_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_code_proves_lemma(mcp_server: Any) -> None:
    res = await _call(
        mcp_server, "isabelle_run_code", code='lemma "1 + 1 = (2::nat)" by simp'
    )
    assert res["ok"], res
    assert res["at_end_of_proof"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multi_attempt_distinguishes_tactics(mcp_server: Any) -> None:
    repl_id = (await _call(mcp_server, "isabelle_open_repl", theory="Main"))["repl_id"]
    await _call(mcp_server, "isabelle_step", repl_id=repl_id, isar='theorem t: "rev (rev xs) = xs"')

    res = await _call(
        mcp_server,
        "isabelle_multi_attempt",
        repl_id=repl_id,
        tactics=["by blast", "by simp", "by auto"],
    )
    assert res["ok"], res
    by_tactic = {a["tactic"]: a for a in res["attempts"]}
    assert by_tactic["by simp"]["ok"] and by_tactic["by simp"]["closes_goal"] is True
    assert by_tactic["by auto"]["closes_goal"] is True
    assert by_tactic["by blast"]["ok"] is False

    # The original REPL is untouched: its single step is still the open theorem.
    state = await _call(mcp_server, "isabelle_state", repl_id=repl_id)
    assert state["history"] == ['theorem t: "rev (rev xs) = xs"']
    assert state["goals"]["goal_count"] == 1

    await _call(mcp_server, "isabelle_close_repl", repl_id=repl_id)
