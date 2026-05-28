"""Verify I/R subprocess lifecycle: spawn, accept a TCP connection, terminate."""

from __future__ import annotations

import socket

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle


@pytest.mark.integration
def test_ir_daemon_accepts_tcp_connection(ir_daemon: IRDaemonHandle) -> None:
    """A bare TCP connection to the daemon's listener succeeds within timeout."""
    with socket.create_connection(("127.0.0.1", ir_daemon.port), timeout=10) as sock:
        # Just opening the socket and closing is enough for M0 step 1.
        assert sock.fileno() != -1


@pytest.mark.integration
def test_ir_daemon_process_is_alive(ir_daemon: IRDaemonHandle) -> None:
    """The subprocess is still running after the fixture set it up."""
    assert ir_daemon.process.poll() is None, (
        "I/R subprocess exited prematurely; "
        f"returncode={ir_daemon.process.returncode}"
    )
