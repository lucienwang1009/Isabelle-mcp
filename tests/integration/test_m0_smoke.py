"""The M0 acceptance test: prove `1 + 1 = (2::nat)` end-to-end."""

from __future__ import annotations

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle, IRSession, proof_closed


@pytest.mark.integration
def test_proves_one_plus_one_equals_two(ir_daemon: IRDaemonHandle) -> None:
    """Drive I/R to prove a trivial lemma and confirm the proof closes."""
    with IRSession.connect(ir_daemon) as session:
        repl_id = session.init(repl_id="R_m0_smoke", theories=["Main"])
        try:
            response = session.step(
                repl_id,
                isar='theorem m0_smoke: "1 + 1 = (2::nat)" by simp',
                timeout_seconds=60.0,
            )
        finally:
            session.remove(repl_id)

    assert proof_closed(response), (
        f"expected the lemma to close; got response={response!r}"
    )
