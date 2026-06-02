"""Unit test: the server builds and advertises the Layer B tools (no Isabelle)."""

from __future__ import annotations

import asyncio

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
