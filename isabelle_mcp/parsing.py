"""Pure parsers for I/R Layer C plain-text output.

These take the raw response body from a Layer C command and extract structured
fields. They are side-effect-free and unit-tested without a running Isabelle.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "parse_find_theorems",
    "parse_goal_state",
    "parse_nitpick",
    "parse_quickcheck",
    "parse_sledgehammer",
    "parse_theory_diagnostics",
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
_GOAL_HEADER = re.compile(r"goal \((\d+) subgoals?\):")
_SUBGOAL_SPLIT = re.compile(r"(?m)^ *\d+\. ")
_LINE_RE = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)
# Leading glyphs of a wrapped term fragment in an SMT warning continuation.
_TERM_GLYPHS = "⟦⟧⟹⟶⋀∀∃¬∧∨"


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


def _filter_smt_noise(text: str) -> str:
    """Drop ``SMT: Warning: dropping assumption`` blocks (with their wrapped
    term continuations) from sledgehammer output — pure noise that buries the
    found/one_liner signal.  A trailing marker records how many lines were cut.
    """
    kept: list[str] = []
    dropped = 0
    skipping = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("SMT:"):
            skipping = True
            dropped += 1
            continue
        if skipping:
            # A wrapped continuation of the SMT warning: indented, blank, or a
            # bare term fragment (starts with logic/bracket glyphs). Anything
            # else ends the block.
            if not stripped or line[:1].isspace() or stripped[:1] in _TERM_GLYPHS:
                dropped += 1
                continue
            skipping = False
        kept.append(line)
    out = "\n".join(kept).strip("\n")
    if dropped:
        suffix = f"[{dropped} SMT warning line(s) filtered]"
        out = f"{out}\n{suffix}" if out else suffix
    return out


def parse_sledgehammer(body: str) -> dict[str, Any]:
    """Extract prover ``Try this:`` one-liners from sledgehammer output."""
    diag = _filter_smt_noise(strip_trailing_state(body))
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


def parse_goal_state(body: str) -> dict[str, Any]:
    """Parse a pretty proof state into ``{goal_count, subgoals}``.

    Returns ``goal_count == 0`` and an empty list when no open subgoals are
    shown (e.g. the proof just closed and the body is a ``theorem`` line).
    """
    header = _GOAL_HEADER.search(body)
    if not header:
        return {"goal_count": 0, "subgoals": [], "structured_subgoals": []}
    count = int(header.group(1))
    tail = body[header.end() :]
    # Drop the trailing "[timing] Ns" line, if present.
    tail = tail.split("\n[timing]")[0]
    parts = _SUBGOAL_SPLIT.split(tail)[1:]  # parts[0] is the bit before "1. "
    subgoals = [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    return {
        "goal_count": count,
        "subgoals": subgoals,
        "structured_subgoals": [_structure_subgoal(s) for s in subgoals],
    }


def parse_thm_deps(body: str) -> dict[str, Any]:
    """Parse ``thm_deps`` output (``dependencies: N`` + one name per line)."""
    diag = strip_trailing_state(body)
    lines = [ln.strip() for ln in diag.split("\n") if ln.strip()]
    if lines and lines[0].startswith("dependencies:"):
        lines = lines[1:]
    return {"dependencies": lines}


def parse_theory_diagnostics(body: str) -> dict[str, Any]:
    """Best-effort diagnostic extraction from an I/R theory-load response."""
    text = "\n".join(ln for ln in body.split("\n") if not ln.startswith("[timing]"))
    stripped = text.strip()
    if not stripped:
        return {"errors": [], "warnings": []}
    if stripped.startswith("Loaded theory "):
        return {"errors": [], "warnings": []}

    bucket = "warnings" if "warning" in stripped.lower() else "errors"
    diag: dict[str, Any] = {"message": stripped}
    match = _LINE_RE.search(stripped)
    if match:
        diag["line"] = int(match.group(1))
    return {
        "errors": [diag] if bucket == "errors" else [],
        "warnings": [diag] if bucket == "warnings" else [],
    }


def _structure_subgoal(text: str) -> dict[str, Any]:
    hypotheses: list[str] = []
    conclusion = text
    for arrow in ("⟹", "==>"):
        if arrow in text:
            left, conclusion = text.rsplit(arrow, 1)
            hypotheses = _split_hypotheses(left)
            conclusion = conclusion.strip()
            break
    return {"raw": text, "hypotheses": hypotheses, "conclusion": conclusion}


def _split_hypotheses(text: str) -> list[str]:
    text = text.strip()
    if text.startswith("[|") and "|]" in text:
        text = text[2 : text.index("|]")]
    return [part.strip() for part in text.split(";") if part.strip()]
