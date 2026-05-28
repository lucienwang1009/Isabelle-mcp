"""Shared fixtures for integration tests.

These all require a working Isabelle 2025-2 install. Each fixture
skips the test (rather than erroring) when prerequisites are not met,
so unit tests still pass on CI without an Isabelle install.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest

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


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Absolute path to the repository root."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def ir_dir(repo_root: Path) -> Path:
    """Absolute path to vendored I/R directory."""
    path = repo_root / "vendor" / "AutoCorrode" / "ir"
    if not (path / "repl.py").is_file():
        pytest.skip(
            "vendor/AutoCorrode/ir/repl.py missing; "
            "run git submodule update --init --recursive"
        )
    return path
