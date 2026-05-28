"""Round-trip tests for the minimal I/R command set used in M0."""

from __future__ import annotations

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle, IRSession


@pytest.mark.integration
def test_open_and_close_repl(ir_daemon: IRDaemonHandle) -> None:
    """We can open a REPL with theory `Main` and remove it cleanly."""
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(repl_id="R_open_close", theories=["Main"])
        assert repl_id == "R_open_close"
        session.remove(repl_id)


@pytest.mark.integration
def test_step_returns_response(ir_daemon: IRDaemonHandle) -> None:
    """A theorem-opening Isar step returns a response we can parse.

    We don't yet assert proof closure — Task 8's smoke test does that.
    This verifies the request/response framing round-trips end to end.
    """
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(repl_id="R_step", theories=["Main"])
        try:
            response = session.step(
                repl_id,
                isar='theorem ir_smoke: "True"',
                timeout_seconds=30.0,
            )
            assert isinstance(response, dict)
            assert response.get("ok") in (True, False), (
                f"unexpected step response shape: {response!r}"
            )
            assert "body" in response, (
                f"response missing body: {response!r}"
            )
        finally:
            session.remove(repl_id)
