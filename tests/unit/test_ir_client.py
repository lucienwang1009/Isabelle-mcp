"""Unit tests for pure I/R client formatting helpers."""

from __future__ import annotations

from isabelle_mcp.ir_client import _ml_escape


def test_ml_escape_preserves_framing_characters() -> None:
    text = 'line 1\nline\t"two"\r\\<and>'
    assert _ml_escape(text) == 'line 1\\nline\\t\\"two\\"\\r\\\\<and>'
