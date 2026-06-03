"""Unit test: the server builds and advertises the Layer B tools (no Isabelle)."""

from __future__ import annotations

import asyncio

import pytest

from isabelle_mcp.server import build_server

_EXPECTED = {
    "isabelle_open_repl",
    "isabelle_step",
    "isabelle_undo",
    "isabelle_state",
    "isabelle_fork_repl",
    "isabelle_close_repl",
}


def test_build_server_registers_layer_b_tools() -> None:
    mcp = build_server()
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert _EXPECTED <= names, _EXPECTED - names


def test_build_server_loads_skill_instructions() -> None:
    mcp = build_server()
    assert mcp.instructions is not None
    assert "isabelle-mcp" in mcp.instructions
    # Frontmatter must be stripped (no leading YAML marker).
    assert not mcp.instructions.lstrip().startswith("---")


def test_disabled_tools_are_unregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ISABELLE_MCP_DISABLED_TOOLS", "isabelle_nitpick, isabelle_run_code")
    names = {t.name for t in asyncio.run(build_server().list_tools())}
    assert "isabelle_nitpick" not in names
    assert "isabelle_run_code" not in names
    assert "isabelle_step" in names
