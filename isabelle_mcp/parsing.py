"""Pure parsers for I/R Layer C plain-text output.

These take the raw response body from a Layer C command and extract structured
fields. They are side-effect-free and unit-tested without a running Isabelle.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "parse_find_theorems",
    "parse_nitpick",
    "parse_quickcheck",
    "parse_sledgehammer",
    "parse_thm_deps",
    "parse_try0",
    "strip_trailing_state",
]

# A diagnostic step's body is "<output>\n<echoed proof state>\n[timing] Ns".
# The echoed state begins with "proof (..." or "goal (N subgoal...".
_STATE_START = re.compile(r"^(proof \(|goal \(\d+ subgoal)")
_TRY_THIS = re.compile(r"Try this:\s*(.+)")
_TRAILING_MS = re.compile(r"\s*\(\d[^()]*ms\)\s*$")
_THEOREM_COUNT = re.compile(r"(\d+)\s+theorem")


def strip_trailing_state(body: str) -> str:
    """Return the diagnostic output, dropping the echoed proof state and timing."""
    kept: list[str] = []
    for line in body.split("\n"):
        if _STATE_START.match(line):
            break
        kept.append(line)
    kept = [ln for ln in kept if not ln.startswith("[timing]")]
    return "\n".join(kept).strip("\n")


def _clean_tactic(text: str) -> str:
    return _TRAILING_MS.sub("", text).strip()


def parse_try0(body: str) -> dict[str, Any]:
    """Extract the first ``Try this:`` tactic suggestion from ``try0`` output."""
    diag = strip_trailing_state(body)
    match = _TRY_THIS.search(diag)
    tactic = _clean_tactic(match.group(1)) if match else None
    return {"found": tactic is not None, "tactic": tactic, "output": diag}


def parse_sledgehammer(body: str) -> dict[str, Any]:
    """Extract prover ``Try this:`` one-liners from sledgehammer output."""
    diag = strip_trailing_state(body)
    suggestions = [_clean_tactic(s) for s in _TRY_THIS.findall(diag)]
    # Preserve order, drop duplicates.
    seen: dict[str, None] = {}
    for s in suggestions:
        seen.setdefault(s, None)
    unique = list(seen)
    return {
        "found": bool(unique),
        "one_liner": unique[0] if unique else None,
        "suggestions": unique,
        "output": diag,
    }


def parse_nitpick(body: str) -> dict[str, Any]:
    """Classify nitpick output as counterexample / none / unknown."""
    diag = strip_trailing_state(body)
    if "found a counterexample" in body:
        result = "counterexample"
    elif "no counterexample" in body:
        result = "none"
    else:
        result = "unknown"
    return {"result": result, "output": diag}


def parse_quickcheck(body: str) -> dict[str, Any]:
    """Detect whether quickcheck found a counterexample."""
    diag = strip_trailing_state(body)
    return {
        "found_counterexample": "found a counterexample" in body,
        "output": diag,
    }


def parse_find_theorems(body: str) -> dict[str, Any]:
    """Parse the ``Ir.find_theorems`` listing into count + theorem lines."""
    lines = [ln for ln in body.split("\n") if ln and not ln.startswith("[timing]")]
    if not lines:
        return {"count": 0, "theorems": []}
    tally, *rest = lines
    match = _THEOREM_COUNT.search(tally)
    count = int(match.group(1)) if match else len(rest)
    return {"count": count, "theorems": rest}


def parse_thm_deps(body: str) -> dict[str, Any]:
    """Parse ``thm_deps`` output (``dependencies: N`` + one name per line)."""
    diag = strip_trailing_state(body)
    lines = [ln.strip() for ln in diag.split("\n") if ln.strip()]
    if lines and lines[0].startswith("dependencies:"):
        lines = lines[1:]
    return {"dependencies": lines}
