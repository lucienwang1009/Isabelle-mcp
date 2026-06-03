"""Integration test for I/R crash recovery (kill the daemon, recover)."""

from __future__ import annotations

from pathlib import Path

import pytest

from isabelle_mcp import metrics
from isabelle_mcp.errors import ToolError
from isabelle_mcp.lifecycle import IRManager

_PORT = 9156


@pytest.mark.integration
def test_crash_recovery_invalidates_ids_and_restarts(
    isabelle_bin: str, ir_dir: Path, hol_built: None
) -> None:
    metrics.reset()
    manager = IRManager(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        port=_PORT,
        bash_server=False,
        startup_timeout_seconds=120.0,
    )
    manager.start()
    try:
        repl_id = manager.open({"theory": "Main"})["repl_id"]

        # Hard-kill the daemon to simulate a crash.
        assert manager._handle is not None
        manager._handle.process.kill()
        manager._handle.process.wait(timeout=10)

        # The stale id is no longer valid; the call triggers a restart.
        with pytest.raises(ToolError) as exc:
            manager.step(repl_id, "by simp")
        assert exc.value.code == "repl_not_found"

        # After restart a fresh REPL works again.
        new_id = manager.open({"theory": "Main"})["repl_id"]
        assert new_id != repl_id
        proved = manager.step(new_id, 'theorem t: "1 + 1 = (2::nat)" by simp')
        assert proved["at_end_of_proof"] is True

        assert metrics.snapshot().get("ir_restarts", 0) >= 1
    finally:
        manager.close()
