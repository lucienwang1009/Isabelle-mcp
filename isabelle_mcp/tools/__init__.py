"""MCP tool registry across Layer A (file-anchored), B (REPL), C (automation).

``run_tool`` is the shared adapter every tool callback uses: it runs a blocking
``IRManager`` operation in a worker thread and wraps the result (or a
:class:`ToolError`) in a standard MCP envelope.
"""

from __future__ import annotations

import logging
import secrets
import time
from collections.abc import Callable
from typing import Any

import anyio

from isabelle_mcp import metrics
from isabelle_mcp.errors import ToolError, error_envelope, ok
from isabelle_mcp.logging import log_tool_call

logger = logging.getLogger(__name__)

__all__ = ["run_tool"]


async def run_tool(
    fn: Callable[[], dict[str, Any]], *, tool: str = "?"
) -> dict[str, Any]:
    """Run a blocking IRManager op in a thread and wrap it in an envelope.

    Times the call, emits one structured log line, and bumps metrics.
    """
    correlation_id = secrets.token_hex(6)
    started = time.monotonic()
    error_code: str | None = None
    try:
        payload = await anyio.to_thread.run_sync(fn)
        return ok(**payload)
    except ToolError as exc:
        error_code = exc.code
        return error_envelope(
            exc.code,
            exc.message,
            correlation_id,
            hint=exc.hint,
            server_event=exc.server_event,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as an envelope, not raised
        error_code = "internal_error"
        logger.exception("unexpected error in tool", extra={"tool": tool})
        return error_envelope("internal_error", str(exc), correlation_id)
    finally:
        latency_ms = (time.monotonic() - started) * 1000.0
        metrics.increment("tool_calls")
        if error_code is not None:
            metrics.increment("tool_errors")
            metrics.increment(f"tool_errors_{error_code}")
        log_tool_call(
            logger,
            tool=tool,
            correlation_id=correlation_id,
            latency_ms=latency_ms,
            ok=error_code is None,
            error_code=error_code,
        )
