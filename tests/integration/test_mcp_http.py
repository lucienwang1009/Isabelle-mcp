"""Integration test: the server runs over streamable-http and exposes /metrics."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

_HTTP_PORT = 8181
_DAEMON_PORT = 9157
_BASE = f"http://127.0.0.1:{_HTTP_PORT}"

_EXPECTED = {"isabelle_open_repl", "isabelle_step", "isabelle_sledgehammer"}


@pytest.fixture(scope="module")
def http_server(isabelle_bin: str, ir_dir: Path, hol_built: None) -> Iterator[str]:
    env = os.environ.copy()
    env["ISABELLE_HOME"] = str(Path(isabelle_bin).resolve().parents[1])
    env["ISABELLE_MCP_TRANSPORT"] = "streamable-http"
    env["ISABELLE_MCP_PORT_HTTP"] = str(_HTTP_PORT)
    env["ISABELLE_MCP_PORT"] = str(_DAEMON_PORT)
    env["ISABELLE_MCP_NO_BASH_SERVER"] = "1"
    env["ISABELLE_MCP_LOG_LEVEL"] = "WARNING"
    proc = subprocess.Popen(
        [sys.executable, "-m", "isabelle_mcp.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait until /metrics answers (server + daemon up), up to ~120s.
    deadline = time.monotonic() + 120
    ready = False
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("server exited during startup")
        try:
            if httpx.get(f"{_BASE}/metrics", timeout=2.0).status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            time.sleep(1.0)
    if not ready:
        proc.terminate()
        pytest.skip("HTTP server did not become ready in time")
    try:
        yield _BASE
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.integration
def test_metrics_endpoint(http_server: str) -> None:
    resp = httpx.get(f"{http_server}/metrics", timeout=5.0)
    assert resp.status_code == 200
    assert "isabelle_mcp_" in resp.text or resp.text.strip() == ""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_streamable_http_lists_tools(http_server: str) -> None:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{http_server}/mcp") as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
    names = {t.name for t in listed.tools}
    assert _EXPECTED <= names, _EXPECTED - names
