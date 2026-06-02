"""Stdio MCP transport — default for Claude Code / Cursor / VS Code MCP.

FastMCP already implements the stdio framing; this is a thin, named wrapper so
the transport choice is explicit and easy to swap (HTTP+SSE arrives in M4).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

__all__ = ["run_stdio"]


def run_stdio(mcp: FastMCP) -> None:
    """Run the server over stdio (blocking until the client disconnects)."""
    mcp.run("stdio")
