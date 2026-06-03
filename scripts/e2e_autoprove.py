"""Deterministic end-to-end auto-prover over fixture lemmas.

Exercises the whole stack (open REPL -> state goal -> try0 -> sledgehammer ->
apply one-liner) with no LLM in the loop, so it is reproducible in CI. Used both
as a standalone script and by tests/integration/test_e2e.py.

Usage:
    ISABELLE_HOME=... uv run python scripts/e2e_autoprove.py
Exits 0 iff at least THRESHOLD lemmas close.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from isabelle_mcp.errors import ToolError
from isabelle_mcp.lifecycle import IRManager

LOGGER = logging.getLogger("e2e_autoprove")
THRESHOLD = 7

# Lemmas a general prover should close via try0 or sledgehammer.
LEMMAS: list[tuple[str, str]] = [
    ("add_comm", "a + b = b + (a::nat)"),
    ("mul_comm", "a * b = b * (a::nat)"),
    ("add_assoc", "(a + b) + c = a + (b + (c::nat))"),
    ("zero_add", "0 + n = (n::nat)"),
    ("le_refl", "(n::nat) \\<le> n"),
    ("rev_rev", "rev (rev xs) = xs"),
    ("append_nil", "xs @ [] = xs"),
    ("length_append", "length (xs @ ys) = length xs + length ys"),
    ("map_id", "map (\\<lambda>x. x) xs = xs"),
    ("set_un_comm", "A \\<union> B = B \\<union> A"),
]


@dataclass
class Outcome:
    name: str
    closed: bool
    method: str
    proof: str | None


def autoprove_one(
    manager: IRManager, name: str, statement: str, *, sledgehammer_timeout: int = 60
) -> Outcome:
    """Try to close one lemma via try0 then sledgehammer. Cleans up its REPL."""
    repl_id = manager.open({"theory": "Main"})["repl_id"]
    try:
        manager.step(repl_id, f'theorem {name}: "{statement}"')

        try0 = manager.try0(repl_id)
        if try0["found"] and try0["tactic"]:
            if _apply_closes(manager, repl_id, str(try0["tactic"])):
                return Outcome(name, True, "try0", str(try0["tactic"]))

        ham = manager.sledgehammer(repl_id, timeout_seconds=sledgehammer_timeout)
        one_liner = ham.get("one_liner")
        if ham["found"] and one_liner:
            if _apply_closes(manager, repl_id, str(one_liner)):
                return Outcome(name, True, "sledgehammer", str(one_liner))

        return Outcome(name, False, "none", None)
    except ToolError as exc:
        return Outcome(name, False, f"error:{exc.code}", None)
    finally:
        try:
            manager.close_repl(repl_id)
        except ToolError:
            pass


def _apply_closes(manager: IRManager, repl_id: str, tactic: str) -> bool:
    """Apply a tactic; True if it closes the proof. Reverts a partial step."""
    try:
        applied = manager.step(repl_id, tactic)
    except ToolError:
        return False  # tactic failed; I/R left the state unchanged
    if applied.get("at_end_of_proof"):
        return True
    try:
        manager.undo(repl_id, n=1)
    except ToolError:
        pass
    return False


def run(manager: IRManager) -> list[Outcome]:
    """Auto-prove every fixture lemma; return outcomes."""
    return [autoprove_one(manager, name, stmt) for name, stmt in LEMMAS]


def _find_isabelle() -> str:
    env_home = os.environ.get("ISABELLE_HOME")
    if env_home:
        candidate = Path(env_home) / "bin" / "isabelle"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    found = shutil.which("isabelle")
    if not found:
        raise SystemExit("error: isabelle not found on PATH or ISABELLE_HOME")
    return found


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    repo_root = Path(__file__).resolve().parents[1]
    manager = IRManager(
        isabelle_bin=_find_isabelle(),
        ir_dir=repo_root / "vendor" / "AutoCorrode" / "ir",
        session="HOL",
        bash_server=True,
        startup_timeout_seconds=180.0,
    )
    manager.start()
    try:
        outcomes = run(manager)
    finally:
        manager.close()

    closed = sum(1 for o in outcomes if o.closed)
    print(f"\n{'lemma':<16} {'result':<8} method")
    print("-" * 48)
    for o in outcomes:
        print(f"{o.name:<16} {'CLOSED' if o.closed else 'open':<8} "
              f"{o.method}{(' :: ' + o.proof) if o.proof else ''}")
    print("-" * 48)
    print(f"closed {closed}/{len(outcomes)} (threshold {THRESHOLD})")
    return 0 if closed >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
