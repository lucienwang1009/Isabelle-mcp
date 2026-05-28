"""Shared fixtures for integration tests.

These all require a working Isabelle 2025-2 install. Each fixture
skips the test (rather than erroring) when prerequisites are not met,
so unit tests still pass on CI without an Isabelle install.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from isabelle_mcp.ir_client import IRDaemonHandle, launch_ir_daemon

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def isabelle_bin() -> str:
    """Locate the `isabelle` binary. Skip the test if not found.

    Resolution order:
      1. $ISABELLE_HOME/bin/isabelle (if executable)
      2. `shutil.which("isabelle")`
    The test environment is expected to export ISABELLE_HOME (e.g. via
    `export ISABELLE_HOME=/Applications/Isabelle2025-2.app`) before
    running pytest. We do NOT auto-source .env.
    """
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if found:
        return found
    pytest.skip(
        "isabelle binary not found; export ISABELLE_HOME=<install-root> "
        "or add isabelle to PATH"
    )
    raise AssertionError("unreachable: pytest.skip raises")


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def ir_dir(repo_root: Path) -> Path:
    """Absolute path to vendored I/R directory."""
    path = repo_root / "vendor" / "AutoCorrode" / "ir"
    if not (path / "ir.ML").is_file():
        pytest.skip(
            "vendor/AutoCorrode/ir/ir.ML missing; "
            "run git submodule update --init --recursive"
        )
    return path


@pytest.fixture(scope="session")
def hol_built(isabelle_bin: str) -> None:
    """Skip the test unless `isabelle build -n -b HOL` reports nothing to do.

    A built HOL image is required for I/R to start in reasonable time.
    Building HOL from scratch takes 5–15 minutes; we never build it
    inside a test.
    """
    import subprocess

    result = subprocess.run(
        [isabelle_bin, "build", "-n", "-b", "HOL"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(
            "HOL session image not built. Run "
            f"`{isabelle_bin} build -b HOL` "
            "(takes 5–15 minutes the first time). "
            f"stderr: {result.stderr.strip()!r}"
        )


@pytest.fixture(scope="session")
def ir_daemon(
    isabelle_bin: str, ir_dir: Path, hol_built: None
) -> Generator[IRDaemonHandle, None, None]:
    """A long-lived I/R subprocess for the whole test session.

    Starting I/R is slow (~30s after HOL is prebuilt), so this is
    session-scoped and reused across all tests that need it.
    """
    handle = launch_ir_daemon(
        isabelle_bin=isabelle_bin,
        ir_dir=ir_dir,
        session="HOL",
        startup_timeout_seconds=120.0,
    )
    try:
        yield handle
    finally:
        handle.terminate()
