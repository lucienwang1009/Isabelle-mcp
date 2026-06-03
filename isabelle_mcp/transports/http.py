"""HTTP transports (SSE / streamable-http) with a Prometheus ``/metrics`` route.

Binds to loopback by default (``ISABELLE_MCP_HOST``/``ISABELLE_MCP_PORT_HTTP``).
A full bearer-token/OAuth layer is out of M4 scope; rely on loopback binding.
"""

from __future__ import annotations

import logging
import os

from mcp.server.fastmcp import FastMCP

from isabelle_mcp import metrics

logger = logging.getLogger(__name__)

__all__ = ["add_metrics_route", "run_http"]


def add_metrics_route(mcp: FastMCP) -> None:
    """Register a Prometheus-style ``GET /metrics`` endpoint on the app."""
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    @mcp.custom_route("/metrics", methods=["GET"])
    async def _metrics(_request: Request) -> PlainTextResponse:
        return PlainTextResponse(metrics.render_prometheus())


def run_http(mcp: FastMCP, transport: str = "streamable-http") -> None:
    """Serve over an HTTP transport (``sse`` or ``streamable-http``).

    Host/port come from ``ISABELLE_MCP_HOST`` (default 127.0.0.1) and
    ``ISABELLE_MCP_PORT_HTTP`` (default 8000).
    """
    if transport not in ("sse", "streamable-http"):
        raise ValueError(f"unsupported HTTP transport: {transport}")
    mcp.settings.host = os.environ.get("ISABELLE_MCP_HOST", "127.0.0.1")
    port_raw = os.environ.get("ISABELLE_MCP_PORT_HTTP")
    if port_raw:
        mcp.settings.port = int(port_raw)
    add_metrics_route(mcp)
    logger.info(
        "serving MCP over %s on %s:%s", transport, mcp.settings.host, mcp.settings.port
    )
    mcp.run(transport)
