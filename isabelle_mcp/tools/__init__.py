"""MCP tool registry across Layer A (file-anchored), B (REPL), C (automation).

``run_tool`` is the shared adapter every tool callback uses: it runs a blocking
``IRManager`` operation in a worker thread and wraps the result (or a
:class:`ToolError`) in a standard MCP envelope.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Callable
from typing import Any

import anyio

from isabelle_mcp.errors import ToolError, error_envelope, ok

logger = logging.getLogger(__name__)

__all__ = ["run_tool"]


async def run_tool(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run a blocking IRManager op in a thread and wrap it in an envelope."""
    correlation_id = secrets.token_hex(6)
    try:
        payload = await anyio.to_thread.run_sync(fn)
        return ok(**payload)
    except ToolError as exc:
        return error_envelope(exc.code, exc.message, correlation_id, hint=exc.hint)
    except Exception as exc:  # noqa: BLE001 - surfaced as an envelope, not raised
        logger.exception("unexpected error in tool")
        return error_envelope("internal_error", str(exc), correlation_id)
