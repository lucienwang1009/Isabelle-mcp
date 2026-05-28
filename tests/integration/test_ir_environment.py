"""Verify Isabelle 2025-2 is installed and reachable."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_isabelle_binary_exists(isabelle_bin: str) -> None:
    """The resolved isabelle binary exists on disk and is executable."""
    p = Path(isabelle_bin)
    assert p.is_file(), f"{isabelle_bin} is not a file"
    assert os.access(p, os.X_OK), f"{isabelle_bin} is not executable"


@pytest.mark.integration
def test_isabelle_version_is_2025_2(isabelle_bin: str) -> None:
    """Reject older Isabelle releases — I/R requires 2025-2 features."""
    result = subprocess.run(
        [isabelle_bin, "version"], capture_output=True, text=True, check=True
    )
    output = result.stdout + result.stderr
    assert "Isabelle2025-2" in output, (
        f"unexpected Isabelle version "
        f"(stdout={result.stdout!r}, stderr={result.stderr!r})"
    )


@pytest.mark.integration
def test_hol_session_is_built(hol_built: None) -> None:
    """The HOL session image is up to date (built via `isabelle build -b HOL`)."""
    # Reaching here means the fixture confirmed HOL is built.
    assert True
