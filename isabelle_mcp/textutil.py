"""Small text helpers shared by the IRManager and its operation mixins."""

from __future__ import annotations

import logging
import os

__all__ = [
    "max_preview_chars",
    "state_at_end_of_proof",
    "strip_timing",
    "truncate",
]

logger = logging.getLogger(__name__)

_DEFAULT_MAX_PREVIEW_CHARS = 4000


def max_preview_chars() -> int:
    raw = os.environ.get("ISABELLE_MCP_MAX_PREVIEW_CHARS")
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning("invalid ISABELLE_MCP_MAX_PREVIEW_CHARS=%r; using default", raw)
    return _DEFAULT_MAX_PREVIEW_CHARS


def strip_timing(body: str) -> str:
    """Drop I/R's trailing ``[timing] Ns`` lines from a response body."""
    lines = [ln for ln in body.split("\n") if not ln.startswith("[timing]")]
    return "\n".join(lines).rstrip("\n")


def truncate(text: str) -> str:
    limit = max_preview_chars()
    if limit and len(text) > limit:
        return text[:limit] + "\n… [truncated; use isabelle_state for full output]"
    return text


def state_at_end_of_proof(body: str) -> bool:
    """True when a state body shows no open proof (no remaining goals)."""
    if "subgoal" in body and "goal (" in body:
        return False
    return not body.lstrip().startswith("proof (")
