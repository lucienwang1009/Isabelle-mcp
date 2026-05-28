"""Verify Isabelle 2025-2 is installed and reachable."""

from __future__ import annotations

import subprocess

import pytest


@pytest.mark.integration
def test_isabelle_binary_exists(isabelle_bin: str) -> None:
    """The `isabelle` binary is on PATH or pointed to by ISABELLE_HOME."""
    assert isabelle_bin, "no isabelle binary located"


@pytest.mark.integration
def test_isabelle_version_is_2025_2(isabelle_bin: str) -> None:
    """Reject older Isabelle releases — I/R requires 2025-2 features."""
    result = subprocess.run(
        [isabelle_bin, "version"], capture_output=True, text=True, check=True
    )
    assert "Isabelle2025-2" in result.stdout, (
        f"unexpected Isabelle version: {result.stdout!r}"
    )
