"""Stable error taxonomy, hint table, and MCP response envelopes.

Every MCP tool returns a JSON-able dict with a top-level ``ok`` flag. Success is
``{"ok": True, ...}``; failure is
``{"ok": False, "error": {"code", "message", "correlation_id"}, "hint"?}``.
The ``code`` values are stable so an LLM can branch on them (design spec §6).
"""

from __future__ import annotations

import os
from typing import Any

__all__ = [
    "ERROR_HINTS",
    "ToolError",
    "clamp_timeout",
    "error_envelope",
    "map_ir_error",
    "ok",
]

_DEFAULT_MAX_TIMEOUT_S = 600.0


def clamp_timeout(requested: float) -> float:
    """Clamp a per-call timeout to ``[1, ISABELLE_MCP_MAX_TIMEOUT_S]`` (default 600)."""
    ceiling = _DEFAULT_MAX_TIMEOUT_S
    raw = os.environ.get("ISABELLE_MCP_MAX_TIMEOUT_S")
    if raw:
        try:
            ceiling = float(raw)
        except ValueError:
            pass
    return max(1.0, min(float(requested), ceiling))

# Stable error codes the LLM can branch on (design spec §6).
ERROR_HINTS: dict[str, list[str]] = {
    "file_not_found": ["Check the path is inside the project sandbox."],
    "session_not_started": [
        "The HOL image is not built. Run `isabelle build -b HOL` once."
    ],
    "parse_error": [
        "Check the Isar/HOL syntax of the command.",
        'Inner terms must be double-quoted, e.g. `lemma foo: "P x"`.',
    ],
    "tactic_failed": [
        "The tactic ran but did not close or change the goal.",
        "Inspect the remaining goals with isabelle_state, or try other tactics.",
    ],
    "timeout": ["Increase timeout_s, or simplify the step."],
    "repl_not_found": [
        "The repl_id is unknown or was invalidated; open a new REPL."
    ],
    "repl_in_proof": ["The REPL is past `qed`; open a new REPL to continue."],
    "proof_not_open": ["This tactic needs an open `proof` block."],
    "ir_unavailable": ["The I/R daemon is not reachable; it may have crashed."],
    "ml_disabled": ["Raw ML is disabled; set ISABELLE_MCP_ALLOW_ML=1 to enable."],
    "afp_index_missing": [
        "Build a local AFP source index first with `uv run isabelle-mcp afp-bootstrap` or `uv run isabelle-mcp afp-index --afp-root /path/to/afp/thys`."
    ],
    "invalid_argument": ["Check the tool arguments against the schema."],
    "internal_error": [],
}


class ToolError(Exception):
    """An error mappable to a stable code and surfaced as an MCP envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        server_event: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.server_event = server_event
        # Fall back to the first curated hint for the code, if any.
        if hint is None:
            hints = ERROR_HINTS.get(code, [])
            hint = hints[0] if hints else None
        self.hint = hint


def ok(**fields: Any) -> dict[str, Any]:
    """Build a success envelope ``{"ok": True, **fields}``."""
    return {"ok": True, **fields}


def error_envelope(
    code: str,
    message: str,
    correlation_id: str,
    *,
    hint: str | None = None,
    server_event: str | None = None,
) -> dict[str, Any]:
    """Build a failure envelope per the cross-cutting contract (spec §4)."""
    if hint is None:
        hints = ERROR_HINTS.get(code, [])
        hint = hints[0] if hints else None
    envelope: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id,
        },
    }
    if hint is not None:
        envelope["hint"] = hint
    if server_event is not None:
        envelope["server_event"] = server_event
    return envelope


# Substring → code rules, checked in order. The I/R protocol is plain text, so
# we pattern-match on Isabelle / I/R error bodies. Conservative: anything
# unrecognized stays ``internal_error``.
_IR_ERROR_RULES: list[tuple[str, str]] = [
    ("timed out", "timeout"),
    ("Timeout", "timeout"),
    ("Failed to finish proof", "tactic_failed"),
    ("Failed to apply", "tactic_failed"),
    ("Failed to refine", "tactic_failed"),
    ("empty result sequence", "tactic_failed"),
    ("No REPL", "repl_not_found"),
    ("Outer syntax error", "parse_error"),
    ("Inner syntax error", "parse_error"),
    ("Inner lexical error", "parse_error"),
    ("Malformed", "parse_error"),
    ("Undefined", "parse_error"),
    ("Type unification failed", "parse_error"),
    ("Bad name binding", "parse_error"),
    ("not in proof", "proof_not_open"),
    ("Illegal application of proof command", "proof_not_open"),
]


def map_ir_error(body: str) -> str:
    """Map an I/R error body to a stable error code.

    Returns ``internal_error`` when nothing matches, so the raw message still
    reaches the LLM via the envelope.
    """
    for needle, code in _IR_ERROR_RULES:
        if needle in body:
            return code
    return "internal_error"
