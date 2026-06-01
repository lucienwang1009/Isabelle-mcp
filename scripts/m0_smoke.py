"""Standalone M0 smoke: prove `1 + 1 = (2::nat)` without pytest.

Usage:
    uv run python scripts/m0_smoke.py

Exits 0 on success, non-zero on failure.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

from isabelle_mcp.ir_client import IRSession, launch_ir_daemon, proof_closed

LOGGER = logging.getLogger("m0_smoke")


def _find_isabelle() -> str:
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if not found:
        raise SystemExit("error: isabelle binary not found on PATH or ISABELLE_HOME")
    return found


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    repo_root = Path(__file__).resolve().parents[1]
    ir_dir = repo_root / "vendor" / "AutoCorrode" / "ir"
    if not (ir_dir / "repl.py").is_file():
        raise SystemExit(
            "error: vendor/AutoCorrode/ir/repl.py missing; "
            "run git submodule update --init --recursive"
        )
    isabelle_bin = _find_isabelle()

    handle = launch_ir_daemon(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        startup_timeout_seconds=120.0,
    )
    try:
        with IRSession.connect(handle) as session:
            repl_id = session.init(repl_id="R_m0_smoke", theories=["Main"])
            response = session.step(
                repl_id,
                isar='theorem m0_smoke: "1 + 1 = (2::nat)" by simp',
                timeout_seconds=60.0,
            )
            session.remove(repl_id)
    finally:
        handle.terminate()

    if not proof_closed(response):
        LOGGER.error("PROOF FAILED: response=%r", response)
        return 1
    print('PROOF CLOSED: lemma "1 + 1 = (2::nat)" by simp')
    return 0


if __name__ == "__main__":
    sys.exit(main())
